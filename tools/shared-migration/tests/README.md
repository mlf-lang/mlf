# Focused one-time codemod checks

These synthetic fixtures exercise the offline migration tool. They are not part of the compiler guest qualification corpus. The normal compiler and package builds must never invoke the codemod.

From the repository root, with an installed GHC:

```sh
mkdir -p /tmp/mlf-migration-tool-objects
ghc -O0 -itools/shared-migration \
  -outputdir /tmp/mlf-migration-tool-objects \
  -o /tmp/mlf-migrate-shared tools/shared-migration/Main.hs
GHC=ghc MIGRATOR=/tmp/mlf-migrate-shared \
  tools/shared-migration/tests/run.sh
```

`GHC`, `MIGRATOR`, and `OUT` may be overridden. `OUT` defaults to a fresh temporary directory. The script migrates the checked-in `.emlf` fixtures, reparses the output, compiles the transformed code at `-O0`, and runs it. No generated fixture `.hs` is checked in or used as an input. The tiny handwritten support facade uses Haskell strings solely for these isolated matching tests and a custom `Monad` class with no `Prelude.Monad` superclass requirement; it does not qualify production runtime string/IO semantics.

Coverage:

- Poisoned-tail case, equation, and lambda-body matrices
- First-row demand with a poisoned string head
- Fallback variable aliases and nested outer constructors
- Required tail failure on a matching tag
- Outer and function-name capture, repeated shadows, and sequential forward-name capture
- Inner lambda/case binders excluded from capture detection
- Do-local shadowing, constructor-bound continuation, and ignored lazy payloads
- Explicit closed local recursion and mutual recursion
- Fixed primitive equality despite local `eqString` or `eqInt` shadowing
- Nested block/line comments, escaped quotes, and a string gap ending immediately before its closing quote
- Negative Double bit patterns, including negative zero, helper involution at zero, and the `negateInt` rename
- Rejection of a non-exhaustive literal lambda, an unreachable literal row, and unsigned/open recursive groups

The timeout bounds these tiny deterministic regression programs; it is not a qualification-performance assertion. Any failed assertion fails the script. Compiler warnings are retained in the output.
