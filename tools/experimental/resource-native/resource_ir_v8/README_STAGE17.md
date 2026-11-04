# Stage17: reuse authenticated span and layout facts within a scan

This is a small runtime change in the opt-in IR8 route. Later rows of one
pointer-authentication scan reuse the packet span, element identity and element
size established by that call and its first successful row. The span and
directory are local values, not persistent caches. No callback or mutation runs
inside the scan. Independent calls start from the current view again.

Public reads, public references, the first authentication row and empty-domain
behavior remain unchanged. Every later row still checks reader validity, its
row bound, domain/directory agreement, compiled layout and size, multiplication,
object bounds, alignment and the table row ID. Every preceding table ID is
checked before accepting a later pointer. Final pointer equality and output
reservation are unchanged. This is not an address-arithmetic membership shortcut.

## Exact removed work

For each later row reached by authentication, including a row that fails its ID
check, the implementation omits two repeated span classifications and the first
layout lookup. The remaining layout check still executes in the normal finish
path. On the tested ABI, the removed charges are:

- table rows: `2 * (6 + sizeof(Ir8PacketSpan)) + 40 = 68`;
- descriptor rows: `2 * (13 + sizeof(Ir8PacketSpan)) + 40 = 82`.

The formulas, rather than ABI-specific literals, drive the differential tests.
Stage15 already removed later directory reloads; Stage12 removed an earlier
duplicate directory lookup. The test runner distinguishes all three frozen
historical baselines and accounts for only the changes since each baseline.

With sufficient work, statuses, diagnostic coordinates, returned bytes and
failure output sentinels remain exact. Lower work budgets can reach a different
failure coordinate because fewer checks consume work. All budgets below each
new successful cost are still checked for failure and unchanged output.

## Validation

The portable reader suite exercises all 20 table and six descriptor domains at
O0 and O2. It has 4,085 displayed cases per build, including every below-success
budget for selected first/middle/final authentications, malformed spans and
layouts, wrong prefix/target IDs, foreign/interior/one-past pointers, empty/short
spans and span-object mutation/restoration between completed calls.

Fourteen actual compiler calls and fourteen reader runs pass. Reports match
across optimization levels. Aggregate removed guard units in the displayed
comparison cases are 81,256 against Stage15, 293,636 against Stage14 and 660,306
against Stage11. These counts are not runtime durations or allocation savings.

The real runtime suite passes all 22 cases at each of O0/O2, including stress.
Each mode has 40 actual process records: 39 exit 0 and the expected D8 fault
exits 2. All 22 full reports match across optimizers.

Fourteen retained source-program conditions were freshly checked, emitted,
compiled and run against the new runtime. All report fields match their actual
Stage15/16 baselines except strictly lower dynamic `guard_work_used` and
`guard_work_total`. Binding admission, events, allocations, RC, memory peaks and
all seven ledgers remain exact. Four O0 ASan/UBSan conditions pass with LSan off
and full report equality to the new ordinary runs. The preselected fuel 24 pair
preserves the same filled cycle, fault 4 and 5,568 retained/explicitly retired
bytes; only those two work fields change. No threshold search was performed.
The pending-step coarse workload now uses 60,311,455 work units rather than
65,683,773, still under the unchanged 67,108,864 cap. This does not promise that
arbitrary larger graphs fit the bound.

## Finite same-program timing

A fixed uninstrumented comparison uses the existing repository native host
measurement transport and the same three retained coarse-placement programs.
Both lanes share generated programs, headers, six common runtime objects,
driver, compiler and O2 flags. Only the binding translation unit differs.
Compilation is outside measurement. Eighteen trace/repeat/quiet qualifications
pass against actual prior Stage15 reports, followed by six warmups and exactly
42 alternating samples: seven pairs per case, 100 fresh entries per batch.
The full binding report, semantics, graph events, allocation/RC and ledger
contracts remain equal. There was no concurrent local compiler/source/test or
archive cohort during sampling and no retries or replacement samples.

In this finite cohort, the median paired optimized/baseline wall-time ratio is
0.9421 for the shared-callable-field case (about 5.8% less time) and 0.9340 for
the curried-field case (about 6.6% less). Corresponding lane batch medians are
1.0016→0.9402 seconds and 1.6623→1.5261 seconds. These are descriptive measurements,
not population guarantees. The scalar-box result is inconclusive: its batches
are below 250 ms and the paired variability does not meet the predeclared rules.

This optimization does not reduce the compared allocation, RC or requested-byte
peaks; those are exact between lanes. The process RSS samples are retained, but
no RSS improvement is inferred. Startup, one admission and final JSON remain in
each measured process. Earlier stage timing cohorts are separate observations,
not numbers to multiply into a claimed end-to-end improvement. Neither lane is
the original compiler/GC backend or Perceus.

## Reproduce

```sh
python3 -B tools/experimental/resource-native/tests/test_binding_readers.py \
  --cc cc --output /absolute/new/reader-output
python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --optimization O0 --stress --output /absolute/new/native-o0
python3 -B tools/experimental/resource-native/tests/test_stage05_runtime_native.py \
  --optimization O2 --stress --output /absolute/new/native-o2
```

Optional `--baseline-root` enables reader differential checking against one of
the exact supported old binding sources. Current-only expectations, sentinels
and all selected sub-success budgets require no old checkout. Existing CI runs
those portable readers and the real O0/O2 runtime; no new job or timeout is added.

The packet ABI, allocator ledger, source language slice, CLI flags, work cap,
fault policies and coarse placement default are unchanged. This does not enable
the experiment by default, complete general GC replacement or establish a fair
comparison with Perceus or the original compiler's GC backend.
