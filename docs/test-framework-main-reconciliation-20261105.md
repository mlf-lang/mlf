# Test framework integration with main

This is a staged framework change, not a claim that the migration plan's later
execution and qualification phases are complete. The original dated inventories
remain immutable. Source-preservation checks are not runtime qualification.

## Integration inputs

- Framework branch: `e0f11f9c39b40f54f30e0eecbea7cebdf8cf0e74`.
- Main: `5d4310381a119c4136a1b9664e2c532ad76323f7`.
- Main's CI/async selection policy, qualification gates, timed-bootstrap checks,
  tuple/list qualification, Windows regression controls, and Guards/Task fixture
  are retained. `test_history_workflows.py` authenticates the reviewed owner
  bytes and the required history-preparation steps.
- The root and tests package graphs retain the framework dependencies, the
  tuple/list dispatcher, and the Core registry. The legacy tuple/list module's
  body is unchanged from main's original entrypoint.

The tuple/list and Core dispatcher migrations remain opt-in. The shared runner
and process driver do change by default: they validate the exact selected
identity inventory, distinguish typed outcomes, and retain raw process evidence.
Their legacy process receipts explicitly remain ineligible for qualification
because that transport does not prove cleanup/join completion.

## Narrow source repairs

Executing the original framework source with the authenticated legacy-format
seed exposed a reserved identifier, imported-name collisions, and three missing
type signatures. The repairs are limited to:

- Rename the local `exists` binding in `Test.Process.rawFile` to `present`.
- Hide `Phase`, `Binding`, and `Kind`/`Node` from the corresponding broad
  `Bootstrap.Types` imports.
- Add explicit signatures to `lookupDescriptor`, `validateNodes`, and
  `superviseBudget`.

No assertion bodies, independent oracles, or expected outcomes are changed.
`framework_recovery.py` reconstructs these exact edits from the pinned framework
commit. It permits only the three corresponding source-hash changes in the
frozen root lock. The original frozen inventory hashes are not replaced with
candidate-derived goldens. Negative controls reject additional source edits,
ambiguous transformations, wrong old hashes, missing modules, duplicate JSON
keys, and arbitrary lock changes. A separate live assertion checks the actual
current lock, rather than relying on synthetic fixtures alone.

## Squash publication proof

The repository uses squash integration. Historical branch ancestry alone cannot
survive that operation, so publication uses a two-commit seal:

1. Commit all reviewed source, tests, and documentation in precursor P, with the
   source-anchor literal zeroed. P has the exact ordered framework/main parents
   above, and contains all reviewed rewritten historical objects.
2. Make child Q whose only change is replacing that literal with P's full SHA.
   Q has exactly one parent, P. Its complete tree, paths, modes, and seal bytes
   are authenticated against P.
3. Before integration, accept only Q itself or a synthetic PR merge with exact
   parents `[main, Q]` and Q's complete tree. A moved base, extra source commit,
   or changed synthetic tree requires a newly reviewed seal.
4. After integration, require a first-parent squash boundary S with exactly the
   pinned main parent and Q's complete tree. Later main descendants may change
   normally while retaining this authenticated boundary.

`refs/pull/19/head` is only a source-object locator. A fresh checkout fetches it
when necessary and verifies the complete seal before retaining a local locator.
A moved ref or a rejected fetch cannot authenticate leftover objects. Replace
refs are disabled for proof operations; shallow and grafted history are rejected.
The ordinary source audits stay offline after explicit preparation.

Every workflow job invoking release metadata or SDK packaging prepares full
history before those checks. Recovery of an older source still uses that source's
own checks; new sources cannot silently skip their required proof.

## Validation boundaries

The original dated runtime records and previously successful CI are historical
evidence, not proof of this candidate. The authenticated GHC-hosted executable is
a bootstrap input, not a current-source compiler. Current-source native outputs
must be identified separately.

The direct interpreted lifecycle entrypoint completed all 22 checks. A bounded
interpreted framework attempt reached the contract checks but timed out before
the full entrypoint completed; it is not counted as a passing framework run.
Native validation is used for the affected executable paths.

Completed native checks include all 22 lifecycle controls, the default framework
contract/catalog/family entrypoint, and the full legacy and opt-in tuple/list
routes. The tuple/list comparison checks all 90 ordered names and the exact
90-ID list/execution inventory, not just matching counts. The process suite adds
independent assertions for typed outcomes, retained assertion diagnostics, raw
file paths/hashes, and explicitly unverified cleanup/qualification fields.
The complete native framework CLI/process suite passes these assertions.

The current-source native compiler also passes the tuple/list fixture's nine
interpreter and nine native results. Core verifies the preserved 35-family
legacy list, the 752-leaf physical inventory, and all 13 source-derived substring
leaves through the real process supervisor, including Unicode and NUL cases.
The Core run uses a 256 MiB stack, consistent with the Linux qualification
environment's requirement to raise its default stack. The default-stack attempt
terminated with SIGSEGV and remains a failed attempt. No assertion of all 739
legacy Core actions executing is made; the focused report stays partial and
unqualified, with cleanup explicitly unverified.

[Focused validation record and exact stdout captures](../tools/testing/evidence/pr19-main-20261105/validation.json)
include tool/binary identities, command arguments, exits, timings, failed
attempts, a 378-path source snapshot, and a 155-path source union derived from
the actual build cache receipts. Absolute producer paths in the summary are
replaced with documented placeholders. Other raw build/cache logs and binaries
remain local; their hashes are identities, not downloadable artifacts.

The current-source package manager rebuilt the root lock and accepted its
offline locked plan. The root graph has 12 packages and 96 source hashes; the
tests graph has 13 packages and 210 source hashes. The root lock SHA-256 is
`c30cf4260fe067472a2f23af31f6ca7b0e5be103d5f1151762b6b5dcbd4bd045`.

An interrupted framework build and an initial new-test expectation typo are
retained as incomplete/failed attempts. Neither is relabeled as a pass. The
recovered build reuses only manager-verified cache entries; completed outputs
and tool/source identities are checked again after environment recovery.

Publication requires rerunning the complete release checks on the sealed Q,
testing a synthetic PR merge and a fresh squash checkout without preinstalled
source refs, and checking CI for Q's exact SHA. A later base/head change
invalidates that combination and must be reconciled rather than ignored.
The ordinary GitHub squash API has an expected-head precondition, not an atomic
expected-base precondition. Recheck main and the synthetic merge immediately
before the action, then verify the actual squash's sole parent and complete tree
immediately afterward. An unexpected parent/tree stops dependent work. Existing
strict-up-to-date or merge-queue enforcement must not be assumed when it cannot
be inspected; no protection setting or direct main update is part of this work.

Main's existing [push run 40523855201](https://github.com/mlf-lang/mlf/actions/runs/40523855201)
is not a complete-qualification pass: its ordinary merge checks and Linux/macOS
async parity succeeded, but `mac-bootstrap` was cancelled, downstream complete
campaigns were skipped, and the complete qualification gate failed. This is
separate historical evidence for the pinned main, not a result for this candidate.
Ordinary PR source smoke also does not execute the complete unit campaign.

The dependent shared-source PR must retain its own source cutover and PR25
transport proof. It needs validation against the actual integrated main, not a
reuse of its prior CI result or an application of Q's whole-tree proof to a
different source tree.
