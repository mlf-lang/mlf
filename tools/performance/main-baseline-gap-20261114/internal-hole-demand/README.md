# Internal-hole demand probe: finite capture

Baseline: fc300bc9fdc389b585cbef0630fc8915d53e89c5. This single GHC O2 fixture uses unchanged Graph and Solver. It is a demand diagnostic, not an optimization or a production/native/performance qualification.

Three handwritten inputs exercise a total control, a sibling type-constructor name carrying a typed Probe, and the same Probe plus a concrete type mismatch. Each has 13 ordered events: the explicit staged path plus an independent original complete call and a total-only snapshot observation. Capture completion does not require the research hypothesis to be true.

## Actual observations

- Total: all 13 events OK. Staged and independent full-call snapshots are byte-identical.
- Probe: prepare through scope-check are OK under the fixture's stated demands; restore/result forcing and the independent full-call produce Probe. Snapshot is skipped.
- Probe plus mismatch: first-order and independent full-call produce exactly the same Left: type constructor mismatch: TyCon "New" (*) versus TyCon "Old" (*). The later staged phases are skipped.

The selected sibling is node 3 in all three projections. These observations show a concrete error/demand ordering that a proposed shortcut must preserve. They do not prove a direct-graft algorithm correct or show removable work.

The phase names include explicit fixture forcing. strictGraph forces graph/map outer constructors and next ID, not every payload; restore PROBE is observed under forceSolver, not necessarily at pure function construction. Left-text rendering has a separate catch boundary. Probe inputs are not deep-rendered. The no-CSE/full-laziness options do not establish a general theorem that input thunks never share.

## Evidence and scope

The tested Main and contract, events.tsv and one total.snapshot are archived byte-exact. Both original 844-byte snapshot copies have the same SHA recorded in results.json. This is a logical view of nodes/tags/binders/flags, aliases, next ID and two inverse indices. It excludes ScopeIndex and physical IntMap tree shape, so it is not complete Solver equality.

Independent actual review checked 144 output files, 39 events and 50 sidecars. The original private backup included 148 files, including external records; those counts are not interchangeable. Seventeen compiler warnings were preserved; fixture stderr was empty. Only O2 ran. Compilation/fixture/whole limits were 120/15/180 seconds with 4 GiB address space; recorded elapsed values are supervision budgets, not performance measurements.

Source v1 was blocked before execution: the hidden-stub comparison used the solved graph rather than the original local graph, and expansion-edge forcing preceded the eligibility guard. The preserved v2 corrects both. These were source-review defects, not failed experimental runs; only v2 was executed.

The fixture requires the pinned baseline's normal GHC host modules and C support. No new public build recipe has been executed. The original Graph/Solver remain unchanged. Cooperative locks do not imply formal machine isolation. No optimization, full semantic-equivalence, native or production admission follows.
