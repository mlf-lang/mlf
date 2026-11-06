# Verified-context reuse: controlled 64-group observations

This is a **single fixed synthetic workload**, not a corpus benchmark or a
statistical speedup claim. All old and new evidence is retained, including
the original compact-reader slowdown that motivated the memo.

## Workload and identities

`SourceContext64.hs` constructs 64 independent typed Int definitions:
`v000..v063 = 1000..1063`. One update changes only `v000` to 2000.
The fixture and `run_workload64.py` are **byte-identical in both runs**.

The earlier producer is cleanup head `2c3ce0ee`. The new producer is based on
merge `6a82267e` (which also contains PR25's `9dfcd662` projection change)
plus verified-context reuse. They are separately authenticated, fresh
producers; this is **not a one-source-change causal experiment**.

Each sequence runs cold compact A, materializes real self-contained CACHE-1
B with the same binary, then warm A/B/B/A, a one-value update in each arm and
a changed warm read in each arm. Materialization is not an old-compiler cold
build or a measurement of legacy compilation time.

All ten commands passed. Nine query invocations each independently checked
and interpreted all 64 expected values (576 results). Original and changed
final-object bytes each agree across arms **and across both runs**; the
changed bytes differ from the original. Each update inferred 1 group and
reused 63; those 63 prior active record identities and bytes were preserved.

## Complete storage, not just compact records

Both runs produced exactly the same directory accounting:

| Snapshot | All file contents | Full pathname allocation |
| --- | ---: | ---: |
| Cold compact A: 64 records + 1 shared context | 158,065 B | 397,312 B |
| Materialized CACHE-1 B: 64 self-contained records | 7,661,697 B | 7,876,608 B |
| A after one change, retaining its old orphan record | 158,674 B | 401,408 B |
| Mixed B after one change, retaining old records | 7,781,398 B | 8,003,584 B |
| Final A + B, including both orphans | 7,940,072 B | 8,404,992 B |

This highly shared synthetic population reduces cold content by about
97.94% and pathname allocation by 94.96%. Those numbers are **not** estimates
for real projects; the separate historical 12-record screen found 22.30%
less complete reachable content.

The one-change snapshots added 609 bytes to A, and 119,701 bytes to B
(a new 609-byte record plus its first 119,092-byte context). No existing
file was rewritten or deleted. This is retained snapshot growth, **not
cumulative I/O**: full-key scratch and staging writes still occur.
The retained orphan records are 608 and 119,714 bytes; no GC or in-place
reclamation is claimed. Build outputs and evidence are additional storage.

## Raw warm-read observations

Seconds, in the fixed A/B/B/A order:

| Producer | A1 wall | B1 wall | B2 wall | A2 wall |
| --- | ---: | ---: | ---: | ---: |
| Earlier, no memo | 0.466501 | 0.114419 | 0.164927 | 0.365241 |
| New memo candidate | 0.114603 | 0.164517 | 0.164756 | 0.164651 |

The earlier compact reader was slower in this observation. In the repeat,
that large compact warm-time gap was no longer observed. Do not convert
these two observations into a generalized speedup factor.

The narrower query-action CPU observations were:

| Producer | A1 CPU | B1 CPU | B2 CPU | A2 CPU |
| --- | ---: | ---: | ---: | ---: |
| Earlier, no memo | 0.429336 | 0.095282 | 0.108218 | 0.336717 |
| New memo candidate | 0.103171 | 0.108462 | 0.119910 | 0.116255 |

Raw cold/change/materialization timings, exact source/binary/receipt hashes
and complete retained/reachable accounting are in
[`results-20261101.json`](results-20261101.json). Cold A was 0.465143 seconds
earlier and 0.515657 seconds in the memo run; cold behavior is not presented
as a measured improvement.

Wall time includes subprocess startup, final semantic checks and output.
The query CPU timer has a narrower forcing/child scope. There was no OS-cache
flush, and complete post-stage file hashing can warm subsequent reads.
There is one sequence per producer, not independent repetitions or a
statistical estimate. The sources, system state and scheduling differ
between the producer runs.

## Reproduction boundaries

The committed Haskell fixture and Python runner are the exact tested bytes.
Compile/link the fixture using the authenticated producer's object closure,
the maintained source-context gate's package/strict-warning flags and the
same two host C objects; authenticate that producer and pin its inputs
before and after the run. The standalone runner is not itself a replacement
for those build/authentication and process-tree resource checks.

With that separately qualified executable and an **external bounded guard**:

```sh
python3 -I -B tools/performance/source-context-read-reuse/run_workload64.py \
  --fixture /absolute/path/to/qualified/source-context-64 \
  --output /absolute/path/to/fresh/workload64-output
```

The runner requires a fresh output, ten fixed commands and a 180-second
per-command timeout. It checks both whole cache trees against a 24 MiB
post-stage content/allocation bound. This is not a continuous hard peak cap.
The recorded local outer guard retained 1800 seconds, 6 GiB address space,
5 GiB tree RSS, 8 GiB complete experiment ROOT accounting and the existing
memory/free-disk floors. Its resource observations are sampled.

The maintained `test_source_context_cache.py` executes the **34 directed
controls**, not this 64-group study. Those controls separately cover
invalidations, real-lock lifecycle and raw/PreparedRaw rejection. This
64-group study is not silently added as a new mandatory hosted CI benchmark.
Neither experiment establishes native-backend, Windows, crash or hostile
filesystem qualification.
