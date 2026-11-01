# Delayed fresh indexes in the private A1 session

This is a narrow adaptation of historical C3 on PR #25 baseline
`e123603d00f6f64e20e4d771836e49ddd808320f`. The original C3 patch was not
recovered; its historical measurements are not included in this experiment.

## Ownership and retained work

`expandedGraph` performs the same source/target checks and complete expansion
as the previous `expanded`, returning an immutable Graph rather than a Session
with incomplete reverse indexes. The original `expanded` helper still builds
all indexes and retains its original descriptors and behavior.

Only an owned, prepared Session can take the new route. Allocation is monotone,
the fresh fragment is connected through the copied root and has no Gen boundary.
The retained `fallbackStageEligible` and ordered `fallbackPrefixRejected`
checks establish that the earlier graft routes must decline. Empty, wrapping,
noneligible and nonrejected expansions use the original indexed path.

On this admitted route, the complete old Store discovers old components from
old equation endpoints and old edges of the fresh fragment. Its selected map
is combined with **every** fresh node. This is the same ascending projection
as discovery through the fully expanded indexes. Ordinary `unifyProjection`
and `restoreProjectionPlan` perform all unification, scope checks, node
comparisons and error construction, including comparisons of unchanged fresh
survivors. Expansion-edge demand is retained before admission.

A successful plan patches old index entries and first-publishes all surviving
fresh nodes, including unchanged descendants. Deleted/aliased fresh nodes never
receive transient reverse indexes. No incomplete expanded Session escapes.
On `Left`, the original full fresh-index publication is replayed before returning
the error, preserving the legacy Store epoch visible through retained old
handles. Final frozen graph, aliases, counters, canonical Patricia index trees
and scopes retain their exact original representation. Internal empty-page
allocation history is not an exposed Session observation.

These obligations rely on private preparation/ownership, not arbitrary forged
Stores. Persistent bucket roots remain immutable. No reuse crosses operations
or graph mutations. Admission, the fresh map union and survivor enumeration also
cost work; the change does not establish a better global asymptotic bound.

## Closed ordinary screen — 2026-11-01

Before sampling, the protocol fixed eight compiler executions in two balanced
blocks: ABBA, then BAAB. The primary estimand is the mean of the block-average
paired log B/A wall-time ratios. The user's structural-change rule requires a
strictly positive unrounded point gain. The window was not extended or replaced.
Two conditional guard cells were also fixed before sampling; rejection requires
both a slowdown over 5% and a geometric delay over 0.1 seconds.

| Input | Runs A / B | Geometric A / B seconds | Point time reduction |
| --- | ---: | ---: | ---: |
| Frozen 711-group compiler | 4 / 4 | 46.973 / 46.207 | 1.63% |
| flat_functions-512 | 2 / 2 | 4.287 / 4.157 | 3.02% |
| higher_order_chain-128 | 2 / 2 | 0.985 / 0.969 | 1.67% |

Both compiler blocks improved: ABBA by 2.15%, BAAB by 1.10%.
Descriptive medians were 46.926 / 46.206 seconds;
medians are not the primary estimand. These small, fixed local samples meet the
point-gain rule; no independent confirmation, confidence interval, statistical
significance or portable-gain claim is made. Historical C3/C1 gains are not
pooled or added to this result.

Each target execution inferred all 711 groups with zero reused groups, checked
ordered identities, and compared checked artifacts directly as raw bytes with
the independently retained reference. Both shape cells additionally passed all
three closed-form native output checks with serial ordinary Clang O2. Producers
were each built once with GHC 9.14.1 O2, `-fpedantic-bottoms` and
`-fno-state-hack`. Toolchain and fixed dependencies are reused; user target
queries are fresh. Preparation, verification and diagnostic runs are outside
the ordinary timer. The compiler endpoint is the frozen checked-crate workload,
not a self-bootstrap of the edited compiler or a new comparison with GHC.

## Mechanism and correctness

A separate diagnostic binary recompiled the affected closure with private ST
counters and CSE/full-laziness disabled. In a complete 711-fresh / 0-reused
execution, it observed 65,750 admitted operations, 666,491 input fresh nodes and
444,691 published survivors. All observed plans succeeded; rejection replay is
covered separately by authored controls. This avoided 221,800 initial index
publications for nodes subsequently discarded. Its checked output also passed
the independent raw-byte comparison. These are diagnostic source-path counts,
not ordinary allocated-byte measurements, exclusive CPU shares or a percentage
of time saved.

O0 and O2 controls compare the full frozen baseline owner with the complete
candidate, using only reversible module/export-header adaptation. All 28
retained authored/renamed C4 fixtures and 35 offset variants are retained:
63 exact graph/index/scope traces, exact success/error outcomes, legacy failure
Store epochs, repeated instantiations, reflexive equalities, old expansion
descriptors, full component selection and handwritten fresh-survivor graphs.
Eight partial-value observations retain source/target exception order, prefix
and survivor Name demand, and unused Name/Kind/alias laziness. These finite
controls supplement the full retained oracle; they do not prove all partial
values equivalent.

The source-admission layer records the one-owner C3 transition after the
inherited canonical-carry layer for e123603d. Historical manifests and semantic
oracles remain intact. A fixed, reversible two-block
inverse recovers the entire previous owner for source-ownership proofs only;
runtime candidates are never projected. All 128 current shared source hashes
and corruption/partial-transition rejection are checked. CrateSession is
outside the canonical builtin preparation closure, so no builtin regeneration
is needed. The source lock snapshot is refreshed and the actual locked plan
is part of integration qualification.

All 14 scheduled integration checks passed: retained P1–P3, graph/transaction,
Map balance, validation boundary, builtin, nine parsed-file cases through both
entries against the independent baseline, native library, all native container
partitions, fingerprint, direct entry/compiler tests, frozen optimizer, all
18 native IO cases, the actual locked plan and the static source snapshot.
Patricia source-adapter tests passed 27 cases normally and with Python O; A1's
34 and fingerprint-fusion's 37 also passed in both modes. Validation's seven,
native-batching's seven, historical-metadata's 20, CI/IO-policy's 17, provenance's
86 (four platform-specific skips) and reconciliation's four checks passed.

Before commit, PR #25 advanced to `9b35151d`, adding only the canonical-carry
source-admission layer and its tests. Integration retains that complete layer
and all three added negative-test methods, appending C3 afterward. The complete
128-source final registry, ordinary producer and build identities were verified
unchanged. Only affected metadata tests were repeated; no ordinary performance
sample or production rebuild was added. [Summary data](results-20261101.json)
binds the closed plans, samples, controls and integration evidence.

Reproduce the focused controls against an authenticated ordinary producer:

```sh
python3 -B tools/performance/c3-delayed-index/run_controls.py \
  --producer .mlf-build/shared-ghc --producer-source "$PWD" \
  --optimization 2 --output .mlf-build/c3-delayed-index-20261101/ci-controls
```

Select O0 with `--optimization 0` and a different fresh output directory.
CI keeps the O2 source copies, receipts, stdout and stderr; the frozen oracle
requires full Git history. Raw experiment plans, timing legs, authentication,
controls and diagnostic sources are under `.mlf-build/c3-delayed-index-20261101/`.

Preparation failures are retained: the first O0 control build rejected a
MonadFail pattern; the next run passed all 63 structural cases but rejected an
authored source-first expectation. The original and candidate both demand the
target first when both arguments are poisoned. The expectation was corrected
and a separate source-only probe added. Neither fix changed production code.
Source-adapter tests initially rejected the newly changed owner until its exact
inverse was registered; an initial inventory assertion omitted shared testing
modules and was corrected to use the complete maintained inventory. The existing
validation and native-IO policy tests also needed consistent resolved macOS
temporary paths. None of
these failures is an ordinary timing sample.
