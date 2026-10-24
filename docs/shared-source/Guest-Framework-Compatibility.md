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
