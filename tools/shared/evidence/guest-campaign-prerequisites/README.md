# Additional guest-campaign source prerequisites

Based on PR #22 snapshot `68220836a1b63005db8fb658eec89fce5bc6c294` plus the seven exact source/test files in `reviewed-inputs.json`. The published base's CI run `40074901235` passed; that result does not qualify this later follow-up. The shared compiler implementation and authenticated O0/O2 producers are unchanged.

Three additional manifest-derived MLF `--compile-crate` checks passed, with zero query reuse:

| Crate | Modules | Fresh groups | Seconds | Peak RSS bytes |
|---|---:|---:|---:|---:|
| test-tools library | 2 | 68 | 32.74 | 320053248 |
| tests library | 14 | 356 | 69.01 | 337666048 |
| test-framework target, including entry | 9 | 128 | 59.38 | 453992448 |

These are **25 additional module entries / 552 fresh groups**, separate from the previously proven root graph. The real manager's tests-manifest plan agrees with the independent source snapshot (13 packages / 212 source hashes); `plan-coverage.json` matches the three checked identities, entries and module sets. **Not all targets in that larger tests plan were checked.** This plan was read without creating a new lock file; the repository's existing root lock audit still passes.

Repairs stay in legacy guest files: explicit standard Monad imports for shared Either/Test.Assert.Test; a reserved `exists` local renamed `present`; an exact closed signature for recursive `superviseBudget`; and two Either-specific `S.mapEither` calls in `traverseIntEntries`. Public legacy `H.fmap` remains unchanged. There are no compiler changes, new instances, fixture-string/expected-type/label changes, or source translation. Failed parse, missing-signature and class-boundary probes are retained under `failures/`.

The Helpers change was independently reviewed: `mapEither` preserves Left without applying its mapper, maps Right lazily, and leaves traversal/error ordering unchanged. Figure12 does not call the changed traversal helpers. Its old semantic digest correctly rejected the change (`figure12-pre-review.stderr`); only after review was the exact new digest pinned. Thirteen decoder tests pass, including independent mutations reverting either repaired call. The faithful direct-GHC Figure12 suite then passed at both O0 and O2: 41 distinct expression checks, 29 assumptions, four principal types and three annotation repairs, preserving 43 labels through two explicit aliases. These are host executions, not guest-native executions. Full release/static controls also passed.

Each source probe records exact specs/commands, before/after input hashes, resource receipts and required checked-artifact hashes. Full local query/object inventories remain in cloud scratch; no binaries, checked objects or query caches are published here. Producer authentication includes its object inventory. Probe-driver copies document this evidence collection and are not a new normal-build route or maintained CI gate.

Still pending: execution of the full guest/Core/unit campaigns, remaining tests targets' source checks, full manager cache/stamp/closure qualification, native LLVM/link stages, the released-seed frozen bridge and native compiler-plus-manager fixed point. No native/LLVM stage ran for these prerequisite checks.
