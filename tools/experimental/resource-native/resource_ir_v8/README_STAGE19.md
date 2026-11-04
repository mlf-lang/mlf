# Stage19: binding-local reserve inlining with unchanged accounting

This change is confined to the opt-in IR8 binding reader. A private, ordinary
`static inline` helper contains the existing work-reservation implementation.
Binding-local calls use it directly; the external `rt8_work_reserve` ABI wrapper
remains available to other translation units and uses the same implementation.

All accounting preconditions, overflow checks, diagnostic precedence and charges
remain unchanged, including reservation before the guarded operation. There is
no cache, skipped check, charge discount, raised limit, header/ABI change or
default-route change. Unlike the earlier reader optimizations, Stage19 permits
**no work-counter difference**: binding admission, packet work and both dynamic
guard-work fields must match the preceding runtime exactly. The direct-linked
route does not promise interception of internal reservations through external
symbol interposition.

## Compiler effect and code-size cost

The inspected GCC 14 O2 binding object has 0 external reserve-call relocations,
down from 216, but still has 69 calls to the local helper. This is partial,
compiler-chosen inlining, not `always_inline` or a guarantee that all calls
disappear. The external ABI symbol remains defined.

Binding `.text` grows from **20,234 to 34,266 bytes**, an increase of 14,032 bytes
(about 69%). That is a substantial instruction-code cost, not an allocation
reduction. Different compilers, flags or workloads may make a different tradeoff.

## Local correctness evidence

- The [portable reader suite](../tests/test_binding_readers.py) passes 4,110
  displayed rows per build at each of O0/O2. These include 25 external-wrapper
  controls covering invalid state, limits, overflow and failure precedence.
  The Stage17/18 comparison preserves status, diagnostics, outputs and all work
  exactly. Current-only and the three older historical comparison modes also
  pass; their earlier stage-specific work differences are not Stage19 savings.
- The [native runtime suite](../tests/test_stage05_runtime_native.py) passes all
  22 tests, including stress, at each of O0/O2.
- Eighteen retained source-program conditions pass after fresh resource checks,
  emission, exact comparison of all four generated files, and O2 compilation
  against this runtime. Complete reports match their actual preceding baselines,
  including events, admission, every work field, allocation/RC and all seven
  balanced zero-live ledgers. There are no ignored report fields.
- Four nominal-capture O0 ASan/UBSan conditions pass with LSan disabled in this
  environment. Their full reports equal the new ordinary reports. This is not
  LeakSanitizer coverage.
- The fixed fuel-29 retain/destroy-terminal pair preserves fault 4 after Fill,
  the live recursive cycle and exactly **5,824 bytes** retained or explicitly
  retired. Both complete nested reports match the actual earlier pair. Explicit
  retirement does not turn the failed evaluation into success.

These are local results. They do not establish publication, merge or accepted
exact-head CI; final independent review and publication checks are separate.

## Fixed same-program timing design

Both lanes use the same three retained Stage09 coarse-placement programs:
`scalar-box`, `shared-field` and `curried-field`. Source workload, generated C,
headers, six common objects, driver, compiler and flags are identical. Only the
binding translation unit differs: the preceding Stage18 runtime versus Stage19.
The flags are `-std=c11 -O2 -g -Wall -Wextra -Werror -pedantic`, without LTO or
profiling instrumentation. Compilation is outside measurement.

Each cohort uses the existing native host measurement helper: 18 qualifications
(one-entry trace, three-entry trace and one-entry quiet for each lane/case), six
fixed warmups, then 42 samples in seven alternating pairs per case. Each sample
runs 100 fresh entries. Graphs and memo state are recreated, while Context and
admission occur once per batch. Repeat counters account for that fixed overhead.
Quiet mode suppresses event serialization, not guards, accounting or RC. Its
metrics are checked against trace qualifications; it is not a full event trace.
Startup and final JSON remain inside the measured process.

The unchanged rules require sufficiently long batches (250 ms) and at most 5%
relative median absolute deviation for the lanes and paired ratios. The paired
median must also differ from 1 by more than both 0.01 and three paired-ratio MADs.
Process wall time, CPU time, RSS and the requested-byte ledger are distinct
measurements.

### Cohort 01: all elapsed conclusions inconclusive

The first fixed cohort (`reserve-inline-run01/results.json`) completed all 42
samples, but **none of its three elapsed results qualifies**. Scalar batches are
too short and variable. Baseline lane relative MAD is 5.0355% for shared-field
and 5.8267% for curried-field, exceeding the unchanged 5% rule.

The raw median paired optimized/baseline ratios were 0.6725, 0.6590 and 0.6467
for scalar, shared and curried respectively. These are context only, not accepted
speedup results. This cohort remains inconclusive.

### Cohort 02: one independent, unchanged replication

A single replication was declared before its launch, retaining the same inputs,
schedule and thresholds (`reserve-inline-run02/results.json`). It also completed
all 42 samples. Its finite descriptive results are:

| Case | Median paired optimized/baseline wall ratio | Baseline / optimized batch median | Conclusion |
| --- | ---: | ---: | --- |
| scalar-box | 0.6458 | 0.04856 / 0.03134 s | Inconclusive: batches below 250 ms |
| shared-field | 0.6549237251 | 0.87920 / 0.57024 s | Descriptive finite cohort |
| curried-field | 0.6205817714 | 1.44691 / 0.89996 s | Descriptive finite cohort |

Ratios are medians of paired ratios, not ratios of lane medians. Shared-field
lane relative MAD is 2.3351% / 3.8930%; curried-field is 2.7336% / 1.4728%.
These observations support a local elapsed-time improvement for those two
workloads in this replication, with the code-size cost above. They are not
population guarantees. Scalar remains inconclusive.

The cohorts are reported separately: no pooling, sample substitution, discarded
first cohort or third cohort. Earlier stage ratios are not multiplied into an
end-to-end claim. Allocation, RC, requested-byte peaks and all work counters are
exact between lanes, so no improvement in those quantities is claimed. Retained
RSS observations do not establish an RSS reduction. Neither lane compares the
original compiler/GC backend or Perceus.

## Scope and entry points

The existing reader and native test files linked above are the repository
regression entry points; [Stage05](README_STAGE05.md) documents native options.
The fixed timing cohort uses retained external evidence, not a new default CI
benchmark or source-admission path. See the [source fragment guide](../source_v8/README.md),
[CLI limits](../source_v8/README_CLI.md) and
[nominal-capture observation limits](README_STAGE18.md) for the current bounded
language and runtime claims. General GC replacement, unrestricted source
admission and broad performance superiority remain unqualified.
