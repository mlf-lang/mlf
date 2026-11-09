# PR22 inheritance of the actual PR19 squash

This candidate reconciles the existing shared-source PR22 head
`33804e720af071350941cd87d9f010ef5e09ef28` with the actual main commit
`afbe7219806881301831d79f43596811eca3279d`. It does not merge PR22.
The precursor has those two ordered parents. Its seal child changes only the
`SOURCE_ANCHOR` literal in `tools/testing/history_refs.py`.

## Source and history boundaries

PR19 was squash-merged with sole parent
`5d4310381a119c4136a1b9664e2c532ad76323f7` and tree
`46bc6787b3833cde8ef81ddb078a1848ef7f47cd`. This tree exactly matches its tested
source `33abccb3055efca34608810bc3b5d4010e98ef46`; that source is not an ancestor
of the squash. GitHub deleted the old PR19 branch and retargeted PR22 to main.

The actual merge reports 51 conflicts, partly because squash integration does
not carry the original source ancestry. A three-way comparison against the
identical PR19 source tree was used only as a conflict-resolution aid. It
identified 18 overlapping semantic conflicts while preserving the shared-source
file moves/deletions. The final commit still records the actual main squash as
its second parent. No synthetic ancestry is asserted.

All ten historical revision mappings and the four PR25 transport pins remain
unchanged. The completed PR19 event has independently fixed source, precursor,
main parent and whole-tree identities. PR22's new seal is a separate event.
A future PR22 squash must have exactly the sealed source tree and main parent;
PR25 integration is authenticated inside the PR22 precursor rather than falsely
required to remain a direct ancestor after that squash. Fetch refs are only
locators, and a rejected fetch cannot authorize a later retry through objects
it happened to install.

The seal checks exact raw Git tree identity, not only parsed path dictionaries.
Controls reject duplicate records, reordered records, noncanonical modes,
changed bytes/modes/parents, shallow or grafted history, moved locators and
repeated rejected fetches. The historical PR19 frozen checks inspect that
completed snapshot, while current shared-source framework audits remain active.

## Preserved behavior

- Keep PR22's shared implementation, manifests, lock and direct-host CI shards.
  Do not resurrect deleted legacy `.emlf` implementation modules.
- Keep PR19's verified original Actions-artifact seed transport and unchanged
  archive/compiler hashes. Its temporary artifacts still expire on 2026-11-21;
  this reconciliation creates no release or tag and does not solve durable
  distribution.
- Keep main's reviewed-history preparation, qualification uploads and guards
  parity fixture, with its entry annotation and type oracle using shared `IO ()`.
  Its guards, branches and expected runtime output are unchanged. The white-box task suite continues to import the committed
  `Async.Task.Core` module, without an export-header overlay.
- Preserve the existing shared-framework repairs and benchmark object access.
  Port main's typed-result/raw-evidence assertions to the current guest syntax,
  and canonicalize the package test cache path after creating it.
- Select the timed bootstrap by source architecture: shared-source checkouts
  pass original seed bytes into the frozen shared bridge and use its produced
  compiler; legacy checkouts retain main's real primitive-aware stage-2 bridge.
  Both routes include their cold transition in the timing/RSS budget and publish
  no candidate after a failed transition, invalid tool or failed resource gate.

## Verification scope

The 13 bounded timed-bootstrap controls exercise both routes and their failure
paths with fake tools; they are orchestration tests, not native qualification.
Static manifest validation checks 12 packages and 128 source hashes without
rewriting the lock; it is not a native build-plan result.

Final publication requires the real P/Q seal tests, a fresh synthetic squash
checkout, the release checks and the exact-head PR CI. Direct GHC and mixed-guest
checks must be reported separately from complete native qualification. PR22
remains a draft, and neither this document nor a skipped qualification job
claims a complete native release pass.
