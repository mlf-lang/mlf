# Mixed guest framework compatibility and actual MLF source acceptance

The reconciled host snapshot `25129e97f9ac726c31d530884d83238e20cf3be7` passed
its exact GitHub CI run `40072478476`, including O0/O2 direct-host suites and the
PR aggregate. Expensive async parity was intentionally **not executed** under
the explicit-opt-in policy; full-main qualification was skipped. This is not
full native/unit/bootstrap qualification.

## Source acceptance beyond GHC

The authenticated O2-hosted MLF compiler then ran the maintained
`--compile-crate` operation on exact manifest-derived specs. All 72 core library
modules (11 crates, including the separate async package) and the actual emlf
and mlfpkg entries passed: 2,843 fresh inference groups, none reused. The earlier
foundation/language-core/frontend specs were rerun with the current producer;
checked interface/object bytes matched their preserved historical outputs.
See [compact evidence](../../tools/shared/evidence/modular-current/README.md) and the later [guest repair evidence](../../tools/shared/evidence/guest-framework-recovery/README.md).

Checking the remaining root graph found defects the shared-only GHC inventory
could not detect in guest files. `Test.Evidence` imported a conflicting `Binding`;
`Test.Plan` similarly conflicted on `Kind`/`Node`, and two recursive helpers lacked
required closed signatures. More importantly, legacy `Prelude.Monad` is an
independent guest API: it does not own the shared `Bootstrap.Std` Either instance.

The repair changes no compiler or inference rule. Three legacy guest modules
explicitly import `Prelude hiding (Monad, return, bind)` and
`MLF.Primitive (Monad, return, bind)`. The already-existing `bind` alias uses the
standard `(>>=)` dictionary. Local type-name hides and exact intended-domain
signatures preserve function bodies. No duplicate legacy instances, source
translation, shared RebindableSyntax, or artificial all-shared package marker
is introduced. The import inventory checker now recognizes this supported
explicit builtin import while retaining syntax-marker and reserved-source bans.

After that repair, the mixed test library's 14 modules and the TupleList/compiler
campaign targets' 5/9 private modules all passed actual MLF inference. Together
with the previous core/entry results, their identities, entry modules and module
sets match all **15 crates / 97 declared source modules** in the real manager's
locked root plan; the async package contributes another five separately checked
modules. Source and producer/tool/object hashes remain checked; guest-only edits
do not invalidate the unchanged O0/O2 compiler producer inputs.

## Maintained regression and remaining gates

The O2 CI job additionally runs a bounded actual-MLF source gate: foundation once,
the complete mixed test library, explicit-standard-class acceptance, and an
expected legacy-class rejection. It checks real checked artifacts and input
integrity; resource failures cannot satisfy the negative control. This is not
execution of the guest framework contracts or a full manager build.

Full manager cache/stamp/dependency-closure validation, separate full object
re-decoding, native LLVM emission/linking, full guest/Core/unit/async campaigns,
the released-native-seed frozen bridge and compiler-plus-manager native fixed
point remain distinct pending gates. The official Linux seed bundle was restored
and verified, but its seed-only receipt deliberately remains incomplete for
bootstrap. No native bootstrap stage was run as part of these checks.

## Additional guest campaign prerequisites

A later, separately scoped [prerequisite check](../../tools/shared/evidence/guest-campaign-prerequisites/README.md)
passed actual MLF source checking for test-tools (2 modules), the tests library
(14), and the test-framework target including its entry (9): 552 fresh groups,
none reused. This is not execution of those campaigns and does not cover all
212 source hashes in the larger tests-manifest graph.

The minimal guest repairs select the canonical Monad for shared Either/Test,
rename a legacy reserved-word local, supply a recursive helper signature, and
specialize two Either mappings without changing the public legacy `H.fmap` API.
The latter helper change received independent oracle-equivalence review before
the Figure12 semantic digest was deliberately updated. Old-pin rejection,
mutation controls, and fresh O0/O2 faithful Figure12 passes are retained. Shared
compiler producer inputs and the frozen bridge archive are unchanged.

The separately recorded [small-target batch](../../tools/shared/evidence/guest-small-targets/README.md)
checks Figure12, int-set-unions, check-target and pr-smoke through actual MLF
source inference: 19 module entries **including overlap**, 153 fresh groups,
zero reuse. Figure12 needed the same explicit guest class selection in its
assumption/program builders. Only imports changed; reviewed semantic-pin and
negative-control updates plus fresh O0/O2 host Figure12 passes preserve the
original fixture/oracle contract. These source checks do not execute the named
guest campaigns or complete native/bootstrap qualification.

## Core/backend checkpoint and next semantic revision

The [Core/backend compatibility checkpoint](../../tools/shared/evidence/core-guest-class-recovery/README.md)
adds six actual source checks (124 module entries including overlap, 1,627 fresh
groups), a reviewed standard-class test Graph state action, and a narrow
independent Oracle traversal repair. Existing strings, expected outcomes and the
frozen 35-family/739-action composition are preserved. An authenticated O2 CI
runner now checks the actual guest implementations with 18 focused behaviors
and two expected-failure controls; these do not execute the full campaigns.

This remains the current representation checkpoint. Standard list/tuple/unit
identities, overloaded-string patterns and MonadFail alignment are the next
semantic revision, not already-established properties of these receipts. Native
bootstrap/fixed-point work is held until that next contract is stable.
