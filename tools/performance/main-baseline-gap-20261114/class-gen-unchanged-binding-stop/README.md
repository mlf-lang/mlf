# Stopped unchanged binding trial

This is a test-only, stopped candidate on main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. No production Graph or Solver source was modified, and no ordinary compiler performance sample or native A/B was run.

## Result and decision

The corrected O2 fixture completed 11 inputs and 135 fixed output files. Independent actual review verified all 232 artifacts. Seven cases had equal complete physical results; four matched only their demand or error observation boundary. **Finite qualification is UNQUALIFIED**, because the two real prepared-Solver total/name inputs took `CERT_REJECT`, not the required `ACCEPT` branch. Artificial signed and dense-to-sparse inputs did take the candidate, which does not establish real workload eligibility or speedup. Do not merge or deploy this version.

The cycle input recorded the trial validator's `infinite type (occurs check)` failure, then the untouched fallback returned the original `cyclic structure/binding dependencies` error. The nonlocal-name input still raised `NameProbe` on the complete prepared path. The dense-to-sparse poison input returned successfully and only its separate encoder raised `NameProbe`. In that poison case, actual dispatch/keys are checked inside Main; the external parser can validate necessary conditions but cannot reconstruct the poisoned Graph from its unavailable snapshot.

## Why the real path rejects

Source tracing, supported by the earlier fixture's raw copies and this run's final physical snapshot, shows that expansion binds fresh non-root nodes 13 through 16 to fresh root12, an Arr rather than a Gen. Projected local7 therefore has a non-Gen binder. Later merge classes also have different old binders. The precise first rejected node is a source derivation; this run itself records only `CERT_REJECT`. The original final result binds nodes15 and16 to Gen0, proving the rebinder does real work here. Simply weakening the guard is not valid.

Existing prefix aggregate counts, graph digests and scope-query captures lack the local Graph flags/tags/links, fresh copies/equations and canonical merge-class binders needed to compute this certificate's actual-workload coverage. Scope request counts are not an eligibility denominator. This version stops without a larger compiler run. A distinct fresh-root binder-cluster transformation would require a new proof of the original LCA, graft/raise/permission and error-demand behavior; it has not been implemented.

## Scope and preserved failure

The prototype retains the original initialization and both load passes. It uses the original map reconstruction and validates the candidate; a validator Left goes back to the original rebinding continuation without rendering the trial error first or catching arbitrary exceptions. Projection, scope checks and restoration remain in the fixture. Complete snapshots encode physical maps/sets and ScopeIndex, not only logical lists. A/B/O share the explicit input value within each case, so this is not a general no-sharing or demand-equivalence theorem.

Run01 failed to compile at the Main case/do layout shown in `layout-repair.patch`; it never started the fixture. Run02 used a new output directory and charged run01 wall/compile time to the original budget. All original failure files and raw outputs are retained privately with full backup readback. Both builds preserve 17 baseline warnings; run02 fixture stderr was empty. Process cleanup and the original cooperative locks were verified; no global machine-isolation or benchmark claim is made.

`frozen-fixture-contract.json` is the pre-execution input contract; its historical no-execution field is not the outcome. `results.json`, `summary.tsv` and `qualification.txt` record the actual outcome. Supervision timings in results are not performance measurements.
