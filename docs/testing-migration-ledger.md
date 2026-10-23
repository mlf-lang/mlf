# Source-reviewed migration ledger

`tests/testing-migration-ledger.json` is the P0 role-review checkpoint, not campaign
qualification. The dated JSON/TSV planning inventories are immutable inputs and
are SHA-256 pinned in `tools/testing/migration_inventory.py`.

## Preserved sets

- 577 layered entry records, including 170 catalog families and 90 tuple/list
  observations. Facades, families and observations are not additive test counts.
- 202 external paths, including retained historical entries, with original blob
  and content hashes.
- 3,486 tracked asset provenance rows. Both `test/fixtures/figure12-a8.emlf` and
  `tests/fixtures/figure12-a8.emlf` retain separate path/blob identities.
- All 339 formerly unresolved entries have a source-role classification, owner,
  rationale and exact source evidence. This resolves their static role review,
  not their dynamic leaf export, dispatcher integration or execution acceptance.
  The original `unresolved_entries` is intentionally unchanged as historical data.

The static classifications are explicit in the audit implementation, not inferred
solely from file extensions or `main`. Every source/owner excerpt binds to commit
`8a3e69b165765931c3ff762379a78db9659b2cd8`. The ledger distinguishes test drivers,
fixtures, references, facades, build helpers, provisioning, diagnostics and real
publication. Asset classification notes are preserved provenance, not a claim
that each historical asset has a newly implemented framework dispatcher.

## Important boundaries

- `incorrect-quantifier.emlf` is intentionally accepted by compile/check to
  demonstrate the bad interface. It is not a source-rejection fixture and must
  never be interpreted or run natively.
- Async representation positive fixtures are compile/check-only; their gate is
  distinct from the actual opaque-completion interpreter/native gate.
- `runtime_force.c` is a standalone assertion/failure-mode probe. The current
  NativeABI source explicitly selects `runtime_inline_force.c`, not that probe.
- `async-task/typecheck.emlf` is a retained typing probe, not one of the current
  task driver's executable modes.
- Seven bootstrap diagnostic/stage/parser probes are outside the 25-fixture
  Port list. Their presence cannot increase Port qualification coverage.
- Publication stays outside tests. Provision/install/download operations are not
  passing tests; their contract paths need controlled destinations or mocks.

## Implementation status versus review status

The 90 tuple observations now point to `tests/Tests/TupleList.emlf`, with an explicit
`TupleListMain --framework` opt-in. The frozen legacy implementation remains the
default until executed equivalence is established. Each invocation runs exactly
one implementation. The audit checks the new exact literal ID multiset, opt-in
dispatch, unchanged legacy bytes and retained default, and pins implementation bytes. This is
source registration evidence only: compilation and runtime remain unverified.
All other rows retain frozen legacy implementation status; this checkpoint does
not assert whether another implementation phase has subsequently migrated them.

A source role of `scenario-driver` or `native-assertion-driver` does not close
internal assertion enumeration. Generated cases, native assertion events,
platform variants, cleanup receipts and required execution acceptance remain
explicit completion obligations. No umbrella script pass is accepted as their
replacement. Thus static role-review remaining count is zero; runtime migration
completion is deliberately false and cannot be derived by counting these rows.

## Reproduce the lightweight checks

From the repository root:

    python tools/testing/migration_inventory.py
    python tools/testing/test_migration_inventory.py

The audit only reads files and frozen Git blobs. The 18 focused fault controls
cover missing/duplicate/unknown identities, blank owners, unreviewed state,
fabricated source/hash evidence, counterexample runtime permission, publication
as a test, fake qualification/execution, external-path duplication, fixture
merging, double implementation ownership, schema/extra fields and altered frozen
input pins. They do not run a compiler, bootstrap, native campaign or network.

To intentionally refresh the ledger after reviewing implementation changes:

    python tools/testing/migration_inventory.py --write

Regeneration refuses modified frozen inventories. A future phase must update the
review policy and its evidence explicitly rather than silently relabeling a
legacy row. The validator requires the full expected ledger, not merely matching
headline counts.
