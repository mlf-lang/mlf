# Compiler compilation: timeout diagnosis and repair

PR #25 was fast-forwarded to `c4b0132a` before the final run. The compiler
now completes a fresh MLF package build with one worker and ordinary Clang
`-O2`. The per-action timeout remains 1,800 seconds.

The previous run stopped in `target-e-emlf`, before LLVM emission or Clang.
Compiler-owned generated modules contain approximately 1.2 MB of builtin data
and 19 MB of prepared-library data. Emitting these as monolithic constructor
expressions created excessively large inference problems. The generators now
emit ordinary signed helpers for target terms, unit/crate objects, and parsed
module memo entries. They retain the normal source checker and all consumer
artifact admission checks. The old structural printers remain available as
independent value-comparison oracles.

Splitting source definitions alone was insufficient: optimization folded their
initialization back into a function with 1,029,300 LLVM lines. Clang spent its
time in greedy register allocation. The backend now outlines large expressions
at their existing evaluation points and immediately calls the helpers. Large
recursive scopes retain function values and use entry-block pointer slots;
closure environments capture the loaded values. A capture-size guard prevents
environment loading from repeatedly outlining the same expression. The final
compiler's largest emitted function has 4,746 lines.

## Same-source measurements

Both runs consumed the same frozen `compiler-input` directory. This directory
copies the normal fixed-library installation's sources and generated data, with
the final capture guard applied to `Bootstrap.LLVM.Codegen`. Source hashes were
checked again after the MLF build. GHC 9.14.1 built both the reference compiler
and the MLF producer with `-O2`, one job, and fresh compiler object directories.
GHC reused host support objects. Fixed native standard-library installation was
outside the timed interval. The MLF build used a fresh package cache; all 15
build actions reported cache misses, and maximum parallel jobs was one.

| Path | Wall time |
| --- | ---: |
| GHC directly builds compiler | 163.30 s |
| GHC-built MLF builds compiler, entire package command | 2,740.75 s |
| MLF / GHC | 16.78x |

| MLF action | Wall time |
| --- | ---: |
| Compiler crate checking/construction | 1,630.33 s |
| LLVM emission | 429.80 s |
| Ordinary Clang `-O2` object compilation | 67.76 s |
| Native linking | 0.66 s |

The total also includes dependency crates, runtime compilation, planning and
publication. These are single local measurements, not medians or a speed
qualification. This establishes a completed first native compiler generation;
it does not establish a native-to-native fixed point. Compiler crate checking
remains the dominant performance cost.

## Validation

- All 126 shared-module inferred-interface audits pass.
- Builtin values, apart from the expected producer source-identity change,
  and complete prepared-library values match the previous literals; all 12
  parsed-module memo values match as well.
- 152 native demand/order checks, 76 interpreter checks, and 27 callback-sharing
  audit checks pass. The demand gate now recognizes existing `noinline` headers.
- `test_large_initialization.py` exercises large constructor data, recursive
  functions passed as values, and unused/failing branches. It passes through
  both the GHC producer and the newly MLF-compiled compiler. Its largest
  function falls from the old compiler's 33,458 lines to 4,962 lines.
- Separate backend controls execute 2,500 captured bindings and a closure
  escaping its initializing frame; they print `3126250` and `42` at Clang `-O2`.
- The new compiler reports `native-MLF`, infers `Int`, interprets a program that
  prints `42`, and compiles an ordinary `Bootstrap.Std` consumer that prints
  `3`. Its native-build receipt confirms fixed library/runtime reuse, fresh user
  compilation, one LLVM job, and ordinary Clang `-O2`.

Local evidence is under `.mlf-build/selfcompile-diagnosis-20261029/`:
`fix-evidence.json`, `ghc-fresh/timing.json`, `mlf-fresh-timing.json`,
`mlf-fresh-build/build-report.json`, and `native-user/.emlf-program-0/receipt.json`.

To run the focused end-to-end regression with an installed compiler/runtime:

```sh
python3 -B tools/shared/test_large_initialization.py \
  --compiler INSTALL/bin/emlf --runtime-object INSTALL/native/runtime.o \
  --clang CLANG --gc-prefix BDWGC_PREFIX --output FRESH_OUTPUT
```
