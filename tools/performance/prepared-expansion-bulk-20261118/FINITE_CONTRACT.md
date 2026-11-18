# Authored finite fixture contract (NOT RUN)

Main.hs compares original Bootstrap.Graph.Solver with Prototype.BulkExpansion in the same process. The candidate module must be the isolated Solver candidate with ONLY its module name changed for hosting. Both use unchanged original Graph and IntMap.

There are 11 cases; each runs prepare, expandedGraphPrepared with strictGraph forcing, and complete instantiateExpandedPrepared with strictGraph forcing independently on A and C. Five total-success cases additionally compare full expansion and final Solver physical snapshots. The full path always explicitly calls instantiateExpandedPrepared, so it cannot be bypassed by groundGraft/groundInstance; this is not evidence those unchanged public routes were tested.

Known literal gates from 74fc2a5 fixture evidence:
- original total prepare/expansion/full success;
- NameProbe expansion succeeds but full call observes sibling Probe;
- Mismatch full call returns exactly `type constructor mismatch: TyCon "New" (*) versus TyCon "Old" (*)` before sibling Probe.

Translated/signed/gapped/alias/exhaustion statuses are authored expectations, NOT claimed observed goldens. TwoProbes compares A/C first demanded named exception without asserting which must win. It is differential coverage, not an independently fixed semantic oracle. Exhaustion matching deliberately normalizes only exceptions containing `identity supply exhausted`, removing stack-location variation; all other unexpected exception classes fail.

Total snapshots include Graph nextId, physical IntMap count/prefix/tree and Node descriptions/child IDs/binder/flag, full alias map, physical structural-parent and binding-child maps with complete IntSet count/prefix/bitmap trees, ScopeIndex intervals and every jump-map tree. Poison cases are not deep-snapshotted, so collector demand is separated from normal strictGraph observation.

Successful run output:
- stdout exactly `PASS bulk-publication finite 11 cases\n` (38 bytes).
- stderr expected empty (compiler warnings belong to build outputs, not target stderr).
- exactly 88 target cwd files: 86 `case.phase.A.txt`/`case.phase.C.txt` files, events.tsv and complete.txt.
- events.tsv header `case\tphase\tside\toutcome\n` plus 86 rows, in source case and phase order.
- complete.txt exactly `PASS bulk-publication finite 11 cases\n`.
- each observation sidecar is status + LF + optional value snapshot/error text; bounded to 16,384 Unicode chars (at most 65,536 UTF-8 bytes). Events is fixed bounded row count.
- every A observation must byte-equal its matching C observation, and all corresponding output files must byte-equal across O0 and O2.

The bound is enforced during target rendering. Controller must run fresh empty dirs per level and inventory all cwd outputs, no additional output files allowed. No runtime resource/time measurement is a benchmark.

Not covered by this fixture: full GraphDense corpus, GHC main build, native backend, ProjectCase sequence, standalone public malformed-raw behavior, higher-kinded diverse source corpus or semantic equivalence theorem. Additional controls may be needed before broad qualification.
