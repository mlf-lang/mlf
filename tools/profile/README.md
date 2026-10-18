# Native self-compilation profiling

## Published release seed bootstrap — 2026-10-19

Three alternating cold build pairs on identical v0.1.1 sources measured a
**16.326% lower median complete bootstrap time** with the published v0.1.1 seed
than v0.1.0: **362.97s → 303.71s**. Both compiler and package manager are built;
MLF emission, fresh runtime C, Clang O2 LLVM compilation and linking are included.
MLF phase medians are 338.40s → 266.36s; Clang LLVM/link medians are
17.89s → 30.64s. All samples, variation, source/tool hashes, fixed-point checks,
reproduction commands and the hosted-memory limitation are in the
[seed comparison report](results/2026-10-19-seed/README.md).

This establishes a local improvement for the stock release seeds. It does not
attribute the historical hour-long CI build or measure a hosted speedup. The
ordinary PGO comparison below retains its narrower source-to-LLVM boundary.

## Ordinary self-compilation — 2026-10-18

Three alternating ordinary self-compilation pairs on identical frozen compiler
sources measured a **29.280% reduction in median wall time**:

| Compiler | Wall samples (s) | Median (s) | Range (s) | MAD (s) |
| --- | --- | ---: | --- | ---: |
| Original | 257.289, 257.535, 254.577 | 257.289 | 254.577–257.535 | 0.246 |
| Optimized | 182.307, 181.955, 181.335 | 181.955 | 181.335–182.307 | 0.352 |

The percentage uses the unrounded medians, 257.289087 s and 181.955334 s.
Each measurement covers a fresh compiler process from source loading through
complete compact LLVM emission. Runtime C compilation, LLVM compilation and
linking remain included in the separate nine-workload benchmark gate.

LLVM output is identical across all three repetitions of each compiler.
Between compiler versions, compact LLVM changes with the new representation,
allocation and thunk-force paths; the emitted modules are retained for review.
The earlier 270.03 s / 279.94 s observations remain historical measurements.

See the [detailed comparison](RESULTS.md#ordinary-self-compilation),
[raw samples and statistics](results/2026-10-18-compile3/summary.json), and
[compiler/source hashes and execution order](results/2026-10-18-compile3/ordinary/context.json).
The [frozen source archive](results/2026-10-18-compile3/frozen-self-source.tar.gz)
preserves the exact inputs used by both compilers. The measured optimized
compiler has SHA-256
`0bc6f35450ec7bf03df75a1dbebedea3d5de5ed692aabb69e97ed2dbb364806d`.

## Diagnostic profiling

This diagnostic driver uses the production parser, module linker, class
translation, solver, elaborator, independent xMLF checker and LLVM backend.
`Force.emlf` traverses the complete result of each phase before recording its
end. The following `*-forced-again` checkpoint reports a traversal of the
already evaluated result. No serialization or additional graph validation is
used to force values. The final LLVM must match the ordinary compiler's output.

The diagnostic runtime intercepts only `MLF_PHASE` stderr markers. It records
monotonic wall time, cumulative BDWGC allocations and collection time, heap
size, collection count and process peak RSS. Instrumentation is confined to the
diagnostic build.
`max_rss` uses the host's `getrusage` units (bytes on macOS, KiB on Linux).

```sh
export MLF_GC_PREFIX="$PWD/dist-newstyle/bootstrap-deps/bdwgc-8.2.12-install"
tools/profile/build.sh /path/to/native/emlf "$PWD" "$PWD/.mlf-build/profile"
/usr/bin/time -l .mlf-build/profile/profile \
  "$PWD/bootstrap/Main.emlf" "$PWD/bootstrap" \
  > .mlf-build/profile/self.ll 2> .mlf-build/profile/phases.jsonl
/path/to/native/emlf -i bootstrap --emit-llvm-gc bootstrap/Main.emlf \
  > .mlf-build/profile/ordinary.ll
cmp .mlf-build/profile/self.ll .mlf-build/profile/ordinary.ll
```

Build the driver from both revisions, then profile the **same frozen input
source tree** to compare solver implementations. Run measured processes alone.
The driver has an explicit extra `recheck` phase to quantify the cost of checking
an already evaluated term. Its raw LLVM API also checks input, so diagnostic
wall time is not ordinary compiler wall time. Full forcing and longer-lived
intermediate results can change collection and evaluation order; compare fresh
ordinary compiler processes separately for the end-to-end result. A repeated
forcing checkpoint can trigger an IO-boundary collection; its time includes
that collection rather than representing traversal alone.

No GHC, Python, Cabal, or package download is used. The shell script only builds
and links the diagnostic executable using a supplied native MLF compiler,
Clang, GMP and BDWGC.

For native stack attribution, run `build-names.sh` with the same three arguments
after `build.sh`. It generates a diagnostic copy of the optimizer that retains
source display hints while allocating the same numeric identities. `Workers.emlf`
maps those identities to source names. `name-workers.awk` annotates worker symbols
in the original LLVM and retains internal function symbols for native sampling.
The source tree and driver must match the earlier profile build. Run from the
repository root. On macOS, `sample PID 60 10 -file solver.sample` captures stacks
for sixty seconds at ten-millisecond intervals. Start it at the
`unify-forced-again` checkpoint to inspect instantiation. Use this binary for
attribution only; use the ordinary compiler for performance measurements.

## Separate phase and ordinary measurements

The finer phase driver can be built through the native package manager:

```sh
export MLF_PACKAGE_MANAGER=/absolute/path/to/native/mlfpkg
export MLF_GC_PREFIX=/absolute/path/to/bdwgc-install
tools/profile/build-stages.sh /absolute/path/to/native/emlf \
  "$PWD/.mlf-build/stage-profile"
.mlf-build/stage-profile/build/bin/stages \
  "$PWD/benchmarks/n-body/mlf/main.emlf" "$PWD/bootstrap" standard \
  > .mlf-build/stage-profile/n-body.ll \
  2> .mlf-build/stage-profile/n-body.jsonl
```

Use `compact` instead of `standard` for the compact GC layout. The build freezes
and fingerprints the production runtime with the diagnostic marker interceptor.
Check the emitted LLVM against the ordinary compiler for the same input/layout.
Phases distinguish loading, parsing, inference, independent checking, agreement
checks, erased optimization, representation optimization when applicable, code
generation and output. Forced phases and their repeated traversals remain
diagnostic; they are not additive estimates of ordinary compilation latency.
The benchmark pipeline supplies the actual frontend, runtime C, LLVM compilation
and linking intervals, including their overlap.

For three alternating ordinary self-compilation pairs on identical frozen inputs:

```sh
tools/profile/ordinary-pairs.sh \
  /absolute/path/to/original/emlf /absolute/path/to/candidate/emlf \
  /absolute/path/to/frozen/bootstrap \
  /absolute/path/to/native-bench-results/host-support \
  "$PWD/.mlf-build/ordinary-pairs"
```

This preserves the earlier source-to-LLVM boundary for the secondary measurement.
Each fresh process retains its output, status, wall/CPU time and RSS; LLVM equality
is required between repetitions of the same variant. Compare variants separately
and account for intentional backend representation changes. The benchmark gate
continues to include runtime compilation, LLVM compilation and linking.

## Compiler-only profile guided optimization

Build an instrumented compiler, train it on a frozen compiler source tree, and
build a profile-use compiler through the native package manager:

```sh
export MLF_PACKAGE_MANAGER=/absolute/path/to/native/mlfpkg
export MLF_GC_PREFIX=/absolute/path/to/bdwgc-install
bash tools/profile/build-pgo.sh /absolute/path/to/native/emlf \
  /absolute/path/to/frozen/bootstrap /absolute/path/to/llvm-install \
  "$PWD/.mlf-build/compiler-pgo"
```

Training uses one complete `--type` and one `--emit-llvm-gc` compilation of
`Main.emlf`, combined with weights 4 and 1. No benchmark programs or inputs
participate. The resulting executable is `candidate/bin/emlf`. Preserve the
raw profiles, merged profile, package build reports and `provenance.json`;
warnings for stale or missing profile entries are errors. Profile generation
is compiler construction work, outside subsequent workload timing; workload
outputs, runtime objects, LLVM compilation and linking are still rebuilt in
every timed benchmark sample.

When starting from a compiler that predates backend representation changes,
first build two native generations from the current source. The first contains
the new compiler logic; the second also uses that logic to compile the compiler
itself. Supply the second generation to `build-pgo.sh`:

```sh
"$MLF_PACKAGE_MANAGER" --compiler /absolute/path/to/native-seed \
  --build-dir "$PWD/.mlf-build/reproduce-stage1" --timeout 21600 \
  build --target emlf
"$MLF_PACKAGE_MANAGER" \
  --compiler "$PWD/.mlf-build/reproduce-stage1/bin/emlf" \
  --build-dir "$PWD/.mlf-build/reproduce-stage2" --timeout 21600 \
  build --target emlf
```

Use fresh directories. Build the current `mlfpkg` executable as well before
running the six `compiler-test` groups, so their coverage checks come from the
same source snapshot as the compiler and tests.
