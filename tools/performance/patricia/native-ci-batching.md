# Bounded native Patricia CI fixtures

The standalone native gate keeps the original independent Python dict/set model,
all 199 distinct full-width signed keys, 9 map cases, 7 set cases, 35 rank-view
checks, 9 lazy-payload checks, and the selected-payload failure. Its complete
successful output remains the same 4,107 lines, byte for byte.

## Why the native entry point is partitioned

The original monolithic entry point failed on Linux in both
[PR25 CI220](https://github.com/mlf-lang/mlf/actions/runs/41248576977) and
[PR29 CI218](https://github.com/mlf-lang/mlf/actions/runs/41247895317).
The captured `standalone-good-emit` process exited 251 with
`emlf: out of memory`. GHC good/bad execution and runtime compilation had passed.
The process's 6 GiB address-space limit remained in force; an empty outer
watchdog reason did not mean the child could allocate more memory.

Eight fixed native entry points now partition **observations**, not their input
collections. Each operation retains its original complete input definitions;
binary collection operations still combine the original full maps/sets.
Lazy probes and the selected-payload error retain their relevant within-process
evaluation order. GHC still compiles and executes the original complete fixture.

Every native batch is compared with its exact model segment, then the ordered
native stdout concatenation is compared with the complete original model.
Normal and optimized-Python contract tests pin the old full source/model/error
fixture hashes, action order, complete data definitions and batch coverage.
Per-command 600-second, 6 GiB address-space, 5 GiB sampled-RSS and 2 GiB work
limits, plus the enclosing CI watchdog, are unchanged. No retry, smaller key
sample, relaxed oracle, or compiler optimization flag is introduced.

## Deliberate remaining gap

This is test organization, **not a compiler-memory fix**. It no longer qualifies
the whole 4,107-line test as one native compilation/execution unit, nor preserves
cross-batch runtime sharing. Each batch still checks its original operation
semantics. The full source remains available from `fixture()` and as `Main.hs`
in every run, with `expected`, for a separately guarded monolithic stress probe.

The precise stage causing the allocation amplification remains unestablished.
A falsifiable next diagnostic is the exact full fixture through `emlf --type`
under the same limits: failure would rule out a solely LLVM-stage explanation.
If that passes, source-to-checked and checked-to-LLVM can be separated without
relaxing either checker. Empty LLVM stdout alone does not identify the stage.
