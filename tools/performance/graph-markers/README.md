# Markers-only frontend localization

**Diagnostic checkpoint, no production optimization and no speedup claim.**
Frozen source: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`, with the exact
90-module / 5,233,364-byte workload. Type is byte-identical to that baseline.
This replaces per-call Type counters with low-frequency Session/Graph markers;
it does not replace or relabel the earlier bounded diagnosis.

## Result

One 120-second bounded run produced 79 snapshots. The guard stopped it at
120.480 seconds with exit -9, reason `wall limit`, no surviving descendants,
and no final checked artifacts. Both resource locks were verified free.
Evidence collection completed, but compiler completion and semantic
qualification did not. No ordinary performance samples were taken.

At the final snapshot, 119.372 diagnostic seconds:

- 957 SCCs started, 956 finished fresh, none reused. Total remained unknown.
- The current group had one member, numeric ID 5198, in the raw-demand window
  for 29.5 milliseconds. The final five snapshots advanced from 911 to 957
  started SCCs; execution was not stuck on one SCC.
- Closed wall-demand windows accumulated raw demand 91.768 seconds (956
  windows), prepared encoding 4.654 (957), raw recording 5.168 (956), and finish
  1.075 (956). These are diagnostic wall intervals, not exclusive CPU costs or
  a complete partition of compiler time.
- The slowest completed SCC was ordinal 834: 46 members, first IDs
  2793/2810/2776/2839, span 5.973 seconds, including 5.103 in raw demand.
  Next spans were 3.251 (ordinal 910, ID 3978), 2.015 (934, ID 3977),
  1.961 (15, IDs 5431/5432) and 1.463 (127, ID 5337).

The observations favor accumulated work across many raw demand windows over a
single stalled group. That broad window includes class lowering, constraint
creation/solving, evidence, elaboration, multiple checking steps, canonical
syntax reconstruction and ownership validation. It does not identify a solver
hotspot. A later independently approved profile must distinguish those costs.
Do not infer ordinary compiler speed from comparison with earlier diagnostics.

## Probe contract and controls

Only private CrateSession and CrateGraph copies change. The baseline Type and
all pure inference owners remain unchanged. `transform.py` composes the already
persisted reversible transform in `../type-kind-memo/progress.py` with the new
helper import and one metadata observation, checking inverse reconstruction.

Identity is captured only after successful ordinary Prepared encoding/digest,
which has consumed the owner IDs and stable-definition text. The main compiler
thread strictly copies member count, up to four numeric IDs and 96-character
stable-name previews. It does not revisit ASTs or project lazy sourceNode
fields. IDs plus the frozen input identify the observation; the truncated text
is only a preview and may not distinguish names. No scope or AST closure is
stored. New groups and completed groups clear current identity. Total is known
only when the original empty-groups branch is naturally reached.

Four windows close at existing IO boundaries: prepared record to scope
inventory; raw demand to raw record; raw record to finish; finish to successful
fresh/reused completion. An unfinished window retains a separate open age.
The helper stores only strictly evaluated bounded host data, including four
cumulative totals and five slowest completed groups. Periodic reporting does
not force compiler syntax or deferred statistical structures.

Before the full run, controls passed for zero state, fresh/reused completion,
partial failure without false completion, closed totals, open age, top-five
ordering/bounds, identity reset and retained last-completed identity. Poison
values beyond the fourth member and 96th character proved the preview bounds
do not force their tails. Live periodic and shutdown snapshots passed. This is
helper coverage, not a complete compiler semantic test.

The harness uses the authenticated ordinary GHC 9.14.1 flags, including `-O2`,
`-fpedantic-bottoms`, `-fno-state-hack`, and `-rtsopts=ignoreAll`. Control objects
are separate. The ordinary receipt did not hash its two standalone C objects;
the harness therefore rebuilt each with the exact recorded authenticated CC,
source and flags, and required byte equality with the copied ordinary object
before linking. Both comparisons passed. It passed only `.o` files to GHC,
without introducing global C include flags or Type optimization pragmas.
`MLF_QUERY_PROFILE`, semantic audit and failpoint overrides were unset.

## Durable evidence and limits

`evidence/markers-01/` contains the complete structured snapshots, live control
snapshots, summary and content hashes. Full local receipts, command/environment
metadata, complete tool/object tables and build logs are intentionally not
published here. Their SHA-256 values are retained, but those omitted files are
not recoverable from this checkpoint after machine loss. Do not describe the
summary as a full ordinary build qualification receipt.

The ordinary 600-second source-to-checked baseline did not produce an accepted
reference. Consequently this run did not compare complete checked bytes or
group identities. `harness_complete=true` and `compiler_complete=false` must
remain distinct. No native fixed-point work was run.

## Recovery

Do not automatically rerun this prefix. Read the coordinator's plan and the
summary before choosing another experiment. To reproduce after explicit CPU
scheduling, recover a separate exact-f9 baseline source checkout, authenticated
ordinary producer, matching 90-module workload and fixed builtin. Existing
baseline-team procedures own that setup. Keep this diagnostic checkout
separate; do not substitute newer main or rewrite old receipts.

Use fresh output and the coordinator resource lock:

    flock -n /shared/sprint/resource.lock \
      python3 -B tools/performance/graph-markers/locate.py \
        --producer /baseline/producer --producer-source /baseline/source \
        --workload /baseline/workload.json --setup /baseline/setup.json \
        --output /fresh/markers-localization

The runner also holds the baseline reproduction lock. It verifies all private
transforms, pins ordinary inputs, reauthenticates C objects, checks controls and
entry preflight, then invokes the full workload once under a 120-second guard.
Build guards remain 600 seconds with the original memory/disk/process limits.
Preserve failures and incomplete results; do not raise limits or automatically
repeat. Check descendant cleanup and both locks before returning the CPU slot.
