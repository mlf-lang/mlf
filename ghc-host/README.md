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

No completed compiler build or qualification is claimed by this initial scaffold.
Each milestone needs actual commands, source/tool identities and observations.

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
