# Stage12: avoid duplicate directory validation within one read

This change affects only the opt-in IR8 native runtime. It does not enable IR8
by default or alter the maintained v7 route, packet format, planner, source
admission, allocation strategy, reference counting or terminal fault policy.

## Safety boundary

`domain_location` already obtains and validates an object-directory entry before
resolving its element. It now passes that same local entry to
`object_location_checked` instead of making a second identical `directory` call.
`object_location` still validates its directory once before using the helper.

This is local reuse inside a single synchronous call, not a persistent cache.
The existing immutable-root and no-concurrent-mutation assumptions still apply.
Every element type/size, row bound, multiplication/addition, object/root extent
and alignment check remains. Owner/domain/count checks and authentication scans
also remain, including validation of preceding table row IDs. No access check is
replaced by a caller assertion or removed to obtain the lower cost.

Only work actually repeated by the old path is no longer charged. Consequently,
a valid operation can succeed with a smaller work budget than before. Tests use
each implementation's own success threshold and check every smaller budget;
they do not require the obsolete higher threshold to remain a failure. Failures
must preserve caller output sentinels. On the current ABI, each removed duplicate
examination costs 185 work units; tests derive that cost rather than assuming a
universal constant.

## Standalone reader checks

From a repository checkout with Python 3 and a C11 compiler:

```sh
python3 -B tools/experimental/resource-native/tests/test_binding_readers.py \
  --cc cc --output /absolute/new/reader-results
```

The output directory must not exist. This compiles the current reader and the
same bounded C driver at O0 and O2, checks 3,701 rows in each build, and requires
the two optimization levels to agree. The fixture is typed bounded storage used
to exercise readers; it is not a substitute for binder or runtime admission.

Coverage includes all 20 table and six descriptor domains; first, middle and
last reads, reference translation and authentication; foreign, interior and
one-past pointers; corrupt preceding and target row IDs; directory type, size,
alignment, range, owner, count and null-root failures; and output preservation
for budgets below successful final-row operations. This is finite coverage,
not comprehensive runtime-guard qualification.

An optional `--baseline-root /absolute/old/repository` enables differential mode
against an explicitly supplied old checkout. It compares successful output and
failure diagnostics and verifies the expected removed work. CI uses the
standalone current-only mode and needs neither a hidden old source tree nor a
Git-history lookup. Current-only mode cannot establish equivalence to an older
implementation by itself.

## Additional validation

The existing real-runtime suite passed at O0 and O2, 22 cases each, including
stress. Six retained genuine-source programs (finite self-family SUM nested and
lazy-tail cases in both placement modes, and scalar SUM Number and Empty cases)
were checked and emitted again, with exact agreement of the four generated
files, then compiled and run with the changed runtime at O2. Their complete
reports matched the previous reports except for three strictly lower work
fields: `guard_work_used`, `guard_work_total`, and `binding.work_used`.
`binding.packet.work_used`, scalar results, full events, RC and allocator ledger
fields were unchanged. These were retained captures, not six new compiler
captures.

Two of those programs additionally passed ASan and UBSan with reports identical
to their new ordinary runs. LeakSanitizer was disabled. Default fault retention
and explicit terminal retirement remain distinct; neither the reader test nor
these finite cases qualifies general GC replacement.

The existing IR8 emitter CI job also runs the standalone reader check and retains
its outputs. Other native and fresh-source jobs retain their existing coverage
and limits. Exact-head CI is required to establish its results after publication.

## Performance scope

The optimization removes duplicate checks, but work counters alone are not a
wall-time measurement. A separate fixed comparison uses the repository's native
host-support benchmark transport and the same three retained coarse-placement
programs in both lanes. Runtime compilation is excluded; entry creation and
retirement remain inside each measured program. The controlled result is
reported separately with its workload, sample and noise limits. It is not a
comparison with the original GC or with Perceus.

The fixed local cohort completed all 18 qualifications, six warmups and 42
samples: seven alternating baseline/optimized pairs for each workload, 100 fresh
graph entries per sample, same O2 flags, generated code, coarse placement,
headers, common objects and benchmark driver. Only the binding object changed.
No source/compiler/native work ran concurrently in this task. All samples are
retained, with no retries or post-hoc sample selection.

- `shared-field`: median paired optimized/baseline elapsed ratio 0.7222, about
  27.8% less time in this cohort. Lane medians were 1.5924 and 1.1520 seconds.
- `curried-field`: ratio 0.7165, about 28.3% less time. Lane medians were 2.7863
  and 1.9710 seconds.
- `scalar-box`: inconclusive. Batches were shorter than the predeclared 250 ms
  minimum and optimized relative median absolute deviation exceeded 5%.

The first two cases pass the predeclared duration/noise/effect-size checks;
they are descriptive results for these two finite workloads, not a generalized
performance guarantee. The paired ratio is the median of seven paired ratios,
not the ratio of the two lane medians. All allocation counts, requested-byte
peaks and RC counts stayed exactly equal between lanes. Fresh-entry graph
allocations were respectively 19, 124 and 157 for scalar, shared and curried
cases; their peaks including the single shared context were 4,088, 7,744 and
9,512 bytes; RC increments/decrements were 9, 66 and 81 per entry. Context
allocation occurs once per process and is excluded from the graph-allocation
counts. Requested-byte accounting is not RSS.

One-time packet admission, process startup and final report serialization are
included in each timed process; compilation is excluded. Quiet mode retains
runtime guards and counters but disables event tracing. The genuine traced
one-/three-entry qualifications check semantics separately. No original-GC or
Perceus workload was run, so these numbers establish neither replacement of
the whole GC nor an advantage over Perceus.
