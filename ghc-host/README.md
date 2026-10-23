# GHC host for the MLF compiler

This work builds the existing `.emlf` compiler implementation with GHC. The
MLF inference algorithm, checked xMLF pipeline, interpreter, LLVM backend and
guest runtime remain the language implementation. GHC does not infer the types
of MLF input programs.

## Baseline

The implementation branch starts at PR #19's fixed code snapshot
`8a3e69b165765931c3ff762379a78db9659b2cd8`. Its main baseline is
`77ac8a7bc551ac71747b38c79fc5812d385165e3`, which was still the current main when
this work began. The documentation follow-up
`2f8584423fa3055ca96d1479734357f742c9b3df` adds no compiler code. PR #19 is a
dependency and is not modified by this implementation branch.

The implementation follows the reviewed Chinese design produced for PR #19:
a restricted implementation dialect, deterministic source-to-Haskell generation,
and explicit host primitive adapters. Original source and independent oracles
remain authoritative. Generated files and build outputs belong in a separate
build directory, with source and tool hashes in the evidence.

## Progress

- [x] M0: pin the code and documentation baselines; create an isolated branch.
- [ ] M1: converter and foundation adapters; deterministic generation.
- [ ] M2: frontend and checked target representations.
- [ ] M3: original inference pipeline; independent type golden tests.
- [ ] M4: executable compiler, interpreter and LLVM/crate paths.
- [ ] M5: package manager and typed async APIs.
- [ ] M6: GHC H0 -> native N1 -> native N2 bootstrap and native fixed point.
- [ ] M7: full qualification, independent review and performance evidence.

The first offline Cabal build has compiled all 84 implementation/test modules
and the four host adapter modules, and linked `emlf`, `mlfpkg`, `compiler-tests`
and `tuple-list`. The original inference/compiler sources are unchanged and
compile without `ImpredicativeTypes` or unsafe coercions. The focused Tuple/List
suite has passed. Full qualification, cross-bootstrap and independent review
remain pending; a successful build is not a semantic qualification claim.

## Build and focused checks

Use installed GHC (tested initially with 9.14.1), Cabal (3.18.1.0), Python 3 and
Clang. All Cabal dependencies come from the installed package database; the
build disables package repositories and uses workspace-local configuration.

```sh
python3 ghc-host/build.py --optimization 2
python3 ghc-host/test.py
python3 ghc-host/test.py --optimization 2 --native-reference /absolute/path/to/native-n1/bin/emlf
python3 ghc-host/test_async.py
.mlf-build/ghc-host/bin/tuple-list
# Run serially in a fresh directory after focused tests; this can take hours.
MLF_GC_PREFIX=/path/to/bdwgc python3 ghc-host/qualify.py --output "$PWD/.mlf-build/ghc-qualification"
```

The generated Haskell, Cabal package, binaries and hash receipts live under
`.mlf-build/ghc-host/`. `build-evidence.json` pins every input and generated
module, the converter and executable hashes, and the installed compiler versions.
The converter uses its own typed syntax tree, preserves source locations, lowers
guards/do explicitly, and gives sequential nonrecursive local bindings fresh
names. It is a compiler implementation dialect translator, not a replacement
MLF language checker. Guest MLF continues through the original parser, solver,
evidence elaborator and checked target pipeline.

Host strings use strict UTF-8 Text with cached scalar counts and lazy scalar
index tables. Host ST uses boxed arrays with lazy elements. Typed completion
cells retain their payload types, and only homogeneous `IO Unit` resumptions
enter queues. The OS/process FFI adapter exchanges bytes and bounded integers;
it reuses the native OS/protocol code without linking the MLF heap, GMP allocator
hooks, or BDWGC into the GHC executable.

Host build receipts explicitly identify GHC. Existing package build reports keep
their source implementation label `MLF`; that label alone is not evidence that
their producer executable was a native MLF binary. Cross-bootstrap qualification
must identify each producer by path/hash and record the GHC H0 -> native N1 ->
native N2 chain separately. Existing native qualification must not be claimed
for H0 merely because a package report contains that inherited label.

## Acceptance boundaries

Keep Boolean patterns, nonrecursive `let`, recursive groups, custom Monad/do,
pattern demand, primitive forcing order, arbitrary-precision integers, Unicode
scalars, lazy ST cells and cold typed async actions explicit. No `unsafeCoerce`,
inference weakening, blanket Strict/StrictData, or replacement of MLF semantics
with Haskell's accepted-program set is permitted.

The six native compiler campaigns do not include the separate `tuple-list` and
`tuple-list-native` root targets. Release qualification does not automatically
consume a sibling `async-language` job. Both gaps require explicit execution and
receipt verification. The 339 pending entries in the documentation inventory are
planning records, not completed infrastructure or failed test counts.

The `tests/fixtures/async-gate/counterexample/incorrect-quantifier.emlf` fixture
is compile/check-only and must never be interpreted or executed natively.
Independent type and runtime oracles must not be regenerated from the candidate.

Heavy local campaigns run serially and are coordinated with other Mac tasks.
No system toolchain installation or global configuration change is part of the
host build. The GHC heap and the generated program's BDWGC/GMP runtime stay
separate.
