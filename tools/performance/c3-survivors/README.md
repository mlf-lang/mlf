# Reuse fresh survivors from the retained C3 delta

Baseline is PR #25 at `ffa3d201e4ea9c08109ff00df3f4fd66b56f3ab2`, whose
production sources equal the accepted C3 implementation. This change only
replaces successful C3 fallback publication's second fresh-ID interval lookup.

## Owned delta and demand boundary

Full expansion, projection, unification, scope/stub checks, restoration and
`projectionChanges` remain unchanged. Restoration returns only selected original
identities; it cannot introduce a new real ID. Its ascending `removed` list
contains every changed and deleted node; `changed` contains all replacements.
The complete initial fresh list is already retained by C3's failure branch.

A sorted merge uses these three lists. An unchanged fresh identity keeps its
original Node; a changed identity uses the exact restored replacement; a deleted
identity emits nothing. This includes unchanged fresh descendants. No final
node-map lookup, new Node comparison or payload inspection is added. All output
identities keep their original ascending publication order. The helper is
private and relies on these owned, finite, sorted-delta invariants; it does not
accept arbitrary forged patches.

The old first interval lookup forced the strict `mkGraph` result before any
fresh index publication, including when every fresh ID was deleted. An explicit
`seq patched` retains that graph-materialization boundary. Old index patching
still happens at its original point. The failure branch, full-fresh replay,
ordinary fallback, public API and Session layout remain unchanged. No state or
cache crosses operations. Sorted merging and retaining the input list also cost
work; a net wall or allocation benefit is not presumed.

## Closed fixed screen — 2026-11-01

The protocol fixed eight compiler executions before sampling: ABBA then BAAB,
two adjacent pairs per block. The primary estimand is the mean of block-average
paired log B/A wall ratios. The user's structural-change rule requires strictly
positive **unrounded** point gain. Two conditional guard cells were also fixed;
a guard rejects only when both ratio exceeds 1.05 and absolute geometric delay
exceeds 0.1 seconds. No sample was excluded, replaced or added.

| Input | Runs A / B | Geometric A / B seconds | Point time reduction |
| --- | ---: | ---: | ---: |
| Frozen 711-group compiler | 4 / 4 | 49.327 / 47.212 | 4.29% |
| flat_functions-512 | 2 / 2 | 4.147 / 4.102 | 1.07% |
| higher_order_chain-128 | 2 / 2 | 0.949 / 0.977 | -2.88% |

The first baseline compiler sample was 57.525s, substantially slower than its
other samples; the primary estimate is sensitive to it. ABBA improved about
8.52%, while BAAB slowed about 0.15%. Descriptive compiler medians were
47.230 / 47.020 seconds, about 0.44% lower for B; these are not the chosen primary
estimand. Higher-order's roughly 0.027s delay did not trigger the predefined
guard. The results meet the positive-point engineering rule but do **not**
establish a stable 4.29% speedup, statistical significance, portability or
absence of regressions in other shapes. The slow first sample remains included;
no extra runs were used to seek a cleaner result. Prior C3/C1 gains are not
pooled or added.

All compiler executions inferred 711 fresh / 0 reused groups, checked ordered
group identities and directly compared checked artifacts as raw bytes with the
independent retained reference. Both shape cells retained all three closed-form
native output checks. Both ordinary producers were built once with GHC 9.14.1
O2 and the original demand flags. Clang stays serial ordinary O2. Fixed
libraries/toolchain are reused; target inference is fresh. Preparation,
diagnostics and correctness tests are outside ordinary timing. This is the
frozen checked-crate compiler slice, not a current-source self-bootstrap or a
new GHC timing comparison.

## Mechanism and finite controls

A separate diagnostic producer recompiled the affected closure with private ST
counters and CSE/full-laziness disabled. Its complete 711-fresh / 0-reused task
and independent raw-byte comparison passed. It observed 65,750 successful C3
publications of the same 444,691 survivors. Summing each successful interval's
`stop-first` gives 666,491 steps that the retained old interval loop would have
queried; the new merge has no final-map query. Its sorted old-delta prefixes
contribute 259,552 extra merge steps. These are source-level counts derived from
the observed valid intervals/deltas, not ordinary exclusive CPU, physical
allocation or a time breakdown. Earlier C3's discarded-publication saving is
an inherited invariant, not a second gain from this patch.

O0 and O2 controls compile the local owners separately against authenticated O2
dependencies. They retain the entire previous C3 Main, with a pinned, reversible
module-header rename: all 63 physical graph/index/scope traces, exact errors and
failure Store epochs, repeated instantiations, expansion descriptors, full
selection and eight partial-value/demand observations. The new wrapper compares
the complete frozen accepted-C3 owner with the complete candidate. The original
C3 gate continues independently against its earlier full owner.

The added independent `Data.Map.Lazy` model covers 29,160 valid patch combinations:
729 unchanged/deleted/changed choices, five signed/wide offsets, two dense/gapped
ID layouts and four old-prefix patch shapes. Expected outputs come from deleting
and installing model entries, with independent agreement from the old interval
reader. Local StableName observations check exact unchanged/replacement Node
reuse; an opaque-payload probe verifies that the merge itself inspects only IDs.
These finite observations do not prove all partial values equivalent or measure
ordinary physical allocations.

The source-admission chain adds exactly one owner and preserves the other 127
shared identities. A fixed one-block inverse recovers the complete accepted C3
owner for historical source proofs only; runtime candidates remain complete.
All prior manifests and semantic oracles remain intact. No builtin regeneration
is needed because the complete canonical preparation closure is unchanged.
The source lock is refreshed and actual locked-plan qualification is retained.

All 14 scheduled integration checks passed: retained P1–P3, graph/transaction,
Map balance, validation boundary, builtin, parsed-file comparisons through both
entries, native library, native containers, fingerprint, direct entry/compiler
tests, frozen optimizer, native IO, actual locked plan and static snapshot.
The original C3 O2 gate also passed independently against its earlier full
owner. Source adapters passed 31 methods normally and with Python O; A1's 34
and validation's seven passed in both modes. Native-batching's seven,
historical-metadata's 20, CI/IO-policy's 17 and CI execution-budget's five passed.
[Summary data](results-20261101.json) binds the closed plans and receipts.

Focused reproduction against an authenticated ordinary producer:

```sh
python3 -B tools/performance/c3-survivors/run_controls.py \
  --producer .mlf-build/shared-ghc --producer-source "$PWD" \
  --optimization 2 --output .mlf-build/c3-survivors-20261101/ci-controls
```

Use a different fresh directory for `--optimization 0`. Full Git history is
required. CI retains the O2 source copies, receipts and logs. Raw plans,
ordinary samples, diagnostics, source archives and authentication are under
`.mlf-build/c3-survivors-20261101/`.

A preparation reuse attempt was rejected because the old producer receipt's
resolved input paths did not match the archived source root. No receipt was
rewritten. A fresh baseline was built from its frozen archive instead; this
failure is retained in `reuse-attempt.json` and is not a timing sample.

An additional guest-framework policy check exposed existing macOS portability
issues, reproduced independently from the unmodified baseline: a `/var` versus
`/private/var` temporary-root comparison and the documented Linux-only watchdog's
`/proc/meminfo` dependency. A test-only follow-up resolves the temporary root
and marks its two watchdog methods Linux-only. Its 14 portable methods now pass
normally and with Python O; those two methods remain enabled on Linux and are
explicitly skipped on macOS. The runtime watchdog and all actual compiler
resource guards are unchanged. Initial baseline/current failures are preserved
in `guest-platform-audit/`.
