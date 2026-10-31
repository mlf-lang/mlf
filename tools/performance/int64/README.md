# Haskell Int64 numeric ABI

Language `Int` is signed 64-bit on every supported target. Literals, decimal
`readInt`, addition, subtraction, multiplication and negation wrap as Haskell
`Data.Int.Int64` does. `readInt` retains the existing optional-sign/ASCII-digit
grammar; this change does not add Haskell `Read` whitespace or syntax.
`minBound quot -1` raises integer division overflow; `minBound rem -1` is zero.
Division by zero remains an error. Identity supplies use checked advancement;
wrapping a language value must not silently recycle compiler identities.

Explicit `Integer` primitives retain unbounded arithmetic where required,
including pidigits and exact float conversion. Native Int64 values use the
existing signed-63-bit immediate representation when possible and a distinct
full-width box otherwise. Integer has its own GMP-backed tag. The runtime
ABI sentinel and builtin/primitive identities were advanced together.

`run_controls.py` separates host, native, compiler, legacy, existing, and
end-to-end suites. The native corpus is produced by independent GHC Int64
code and compared byte-for-byte with direct and curried ordinary/UBSan native
execution. Demand and error-order probes are separate from value checks.
The legacy suite keeps 43 literal success/failure cases, checks an actual LLVM
numeric region against 217 independent outputs, and tests both minimum-Int64
division cases inside actual specialized workers.

`--source` binds authentication to an installed producer's owned snapshot;
`--producer` alone defaults to the current repository. Dependency paths are
explicit `--gc-prefix` and `--gmp-prefix`. Production compilation remains
single-lane ordinary Clang -O2. These controls do not establish a performance
benefit, and diagnostic/UBSan executions are never ordinary timing samples.
