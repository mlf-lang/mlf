# Stage14: scalar and complete-view captures in recursive functions

This extends the opt-in single monomorphic recursive-function experiment. It
changes source replay/planning only, not the runtime, packet ABI, allocator,
source CLI arguments, maintained v7 route or defaults.

## Capture boundary

Stage13's one retained singleton concrete group, closed monomorphic arrow,
function-introduction wrapper spine and coarse knot construction remain. A
nonempty capture record now admits only:

- ordinary owners with the exact closed Int or Bool type, including pending
  values which must not be forced merely to capture them;
- a lexical shared definition plus a complete ordered closed Int/Bool vector,
  identified using the existing independently replayed shared-use rows.

Every free RHS occurrence must belong to one of those classes. A view is not
identified by its resulting arrow type: different definitions and different
unused vector coordinates remain distinct. No bare Scheme is published. Ordinary
callable/nominal captures, open/partial/foreign views, mutual or generic recursion
and a second recursive group remain unsupported. At most 64 actual captures are
allowed, including self when used. The new evidence is conditional; capture-free
Stage13 plans, generated files and work counts remain byte-identical.

The planner reconciles this inventory with its independent free-owner and
complete-view analysis. It carries existing outer references and saved views
into construction of the unchanged whole RHS, then adds ticket-free self. It
does not invent strictness, Below or origin facts. An Int view is acquired once
from its lexical Scheme, or retained from an already captured view; recursive
callbacks retain it from their stored environment without re-instantiating it.
Every ordinary annotation lambda/application remains in the graph.

## Origin and observation

The recursive host closure has a concrete/E0 Code scope. Its captures keep their
own actual Access, capsule and origin. In particular, the shared callable must
not be relabeled E0 because its host is concrete. Existing runtime capture and
activation operations preserve the stored Access and enforce its type/support
contracts; no new runtime instrumentation or shortcut is introduced.

The observer joins the exact source uses, full vectors, instantiated contracts,
metadata, generated Code, physical capture slots, acquisition events, owner
handoffs and dynamic guards. Current handoff events expose owner IDs, not an
Access row for every restored owner. Per-callback Access preservation is
therefore established by that code/metadata/guard correspondence, not claimed
as a newly observed per-owner Access trace.

## Genuine fixture

The authored source defines pending `bonus = addInt 20 1` and `sumBonus`, which
captures bonus and the shared function's Int view. Each Cons arm adds
`sharedId bonus` to the recursive tail result. Main first uses the same shared
function at Bool, then adds `sumBonus Nil` to the result on Cons/Cons/Nil.

The real trace checks:

- four calls of one recursive closure/Code: Nil, Cons, Cons, Nil;
- the initial Nil result completes as zero before any bonus demand or Int-view
  invocation, followed by recursive result 42 and final addition 0 + 42;
- one bonus evaluation/memo, and shared calls in Bool, Int, Int demand order;
- one physical shared node/body, complete views, unchanged capture targets and
  no callback-local instantiation;
- Int42, fault0, untruncated events and seven balanced zero-live categories.

The Int use occurs lexically before Bool and can be acquired before Bool demand.
Use-list/acquisition order must not be confused with invocation order. Two Nil
nodes are distinct source allocations; two repeated Cons activations use the
same static case code but distinct selected factory nodes.

## Completed local matrix

All four coarse/groups by O0/O2 conditions passed. The first actual coarse-O0
pair was reused after exact plan/generated-file and terminal-status checks;
only three additional pairs were launched. Complete O0/O2 reports match in each
placement mode, and 76 copied-report/plan/C controls reject altered joins.

Fuel 19 was fixed before the fault pair using the actual coarse entry and tick accounting,
not searched experimentally. Fill consumes tick 19; the next drop attempts tick
20 and faults. The real retained fault has a live recursive knot and 4,848 live
bytes. Explicit terminal destruction retires exactly those bytes with equal
per-category accounting and the same fault4. It is not rollback or successful
evaluation. The existing copied close_group control rejects a false live-knot
claim.

The existing work limit remains 67,108,864. This small healthy workload uses
65,540,230 units coarse and 64,949,552 with groups, so it is close to the limit.
The cap was not raised and no work fields were ignored. This is not deep or
large-data recursion qualification. Peak requested bytes were 20,416 coarse and
19,544 with groups; RC increments/decrements were 242 and 268 respectively.
These finite memory/overhead observations are not RSS or a timing improvement.

Both modes also passed ASan/UBSan at O0, with complete reports equal to ordinary
execution and 19 copied controls each. LeakSanitizer was disabled. Eight earlier
program conditions, including capture-free recursion and the undemanded-tail
case, were freshly replayed/checked/emitted with exact plans and generated
files; their Stage12/13 native reports were retained, not relaunched.

The final fresh portable source run passed and its complete healthy native
report equals the initial coarse-O0 report. Its 10 process records contain eight
successful exits and the two expected fault exits, without cleanup errors.
The combined planner regression suite passed all 83 tests, including five
native fragments and every available historical-capture check. The broad module
suite passed 309 tests with three pre-existing artifact-dependent skips. These
local results do not substitute for exact-head CI after publication.

## Reproduce

With the existing official GHC 9.14.1 and a C11 compiler:

```sh
python3 -B tools/experimental/resource-native/tests/test_source_v8_recursive_captures.py \
  --ghc /absolute/path/to/ghc --cc cc --output /absolute/new/capture-results

python3 -B tools/experimental/resource-native/tests/test_planner_v8_recursive_captures.py
```

The portable integration uses one fresh source/compiler/native run, followed by
two fixed fault calls on the same binary. It does not rebuild/capture separately
for each failure policy. Source snapshots, complete checked capture/replay,
generated files and actual process reports remain separate from diagnostic JSON
admission. CI adds the new planner step and one fresh source case, for 24 fresh
cases in total. It preserves all earlier jobs and limits, including the
60-minute source-job ceiling; fault policies reuse the new binary. Exact-head
CI remains pending until publication.

This adds bounded recursive closure capture, not general MLF, polymorphic
recursion, arbitrary graph-cycle collection, full GC replacement or superiority
over Perceus. No new timing experiment was performed in this stage.
