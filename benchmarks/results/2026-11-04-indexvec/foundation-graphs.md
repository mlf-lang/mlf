# Foundation query compilation with indexed graph algorithms

Three installed `emlf --compile-crate` binaries compiled the same 14 Foundation modules from `c5928b5b` on an Apple M1 Max. All three report `MLF/shared-haskell-v1 GHC` and were built with GHC 9.14.1 and `-O2`. The optimized sources are at `8dc22c96`. The original #43 installation uses `ff7c8c6c`, which has the same compiler sources as `e0fb9a57`. The #29 baseline is `8c455641`.

## Whole compiler

Times are arithmetic mean wall seconds per fresh process. The percentage is the change in elapsed time from the original #43. The last column counts rounds where the optimized compiler beat that version.

| State | Rounds | #29 | Original #43 | Optimized #43 | Time change | Faster rounds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold queries with installed Prelude | 3 | 17.894 | 17.785 | 17.790 | +0.03% | 2/3 |
| Warm, unchanged | 12 | 3.638 | 3.668 | 3.455 | -5.80% | 12/12 |
| Edit to Bootstrap.Version | 12 | 3.730 | 3.736 | 3.681 | -1.47% | 11/12 |
| Both stores empty | 3 | 17.795 | 17.700 | 17.808 | +0.61% | 0/3 |

Each run starts a new compiler process. Warm and edit runs restore that compiler's own **identical** seed query store and Prelude before timing. Cold runs start with an empty query directory, and the empty-store series also omits the Prelude. Rounds rotate compiler positions. OS filesystem caches were left warm. There are three observations per arm in each cold series.

In three separately profiled warm runs per arm, publishing the query generation fell from 201.0 to 27.7 ms on average. After the edit a new generation was required and publication took 187.7 and 180.3 ms respectively. Mean peak RSS on the plain edit rose from 141 to 148 MiB. With both stores empty, the optimized compiler took 107 ms longer on average and was slower in all three rounds.

The cold runs inferred all 504 groups. All warm runs reused 504 and the edit inferred one and reused 503. Every optimized output at every state matched the original #43 interface, object and query report byte for byte. An independent wire reader compared all logical graph nodes, ordered dependency edges, digests and retained result bytes, omitting only the compiler identity from the generation configuration. The ordered graph, package, corruption and interrupted-publication controls passed. Five xMLF outputs matched #29 and passed checking by both versions.

## Graph work

During separate diagnostic runs both algorithms received the same Foundation inputs within one process. Six warm processes alternated which implementation ran first. The probes forced every output group or reach set and checked equality. Allocation counts come from the GHC thread allocation counter.

| Work per warm compile | Calls | Original #43 ms | Optimized ms | Original MB | Optimized MB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Declaration SCCs | 857 | 23.12 | 7.88 | 77.14 | 24.88 |
| Module cycle check | 1 | 0.04 | 0.03 | 0.13 | 0.08 |
| Module visibility | 2 | 0.11 | 0.11 | 0.49 | 0.46 |
| Datatype selection | 504 | 18.43 | 14.99 | 39.86 | 35.69 |

The persisted generation contains 3,403 query nodes and 19,277 dependency reads, but only 3,148 distinct key and digest pairs. After the wire graph had been decoded, admitting and checking it took 50.8 ms in the original algorithm and 24.7 ms in the optimized algorithm. The two admitted maps agreed in all twelve paired runs.

The SCC walk closes components in one pass without constructing a transpose. Modules in the same component share a reachable-ID set. The same table lets each of the 504 datatype queries union the sets for its actual roots. Persisted read pairs are checked once per physical ID. When a whole canonical generation is identical the writer reuses its digest and still verifies retained payloads. These diagnostic times measure separate boundaries and need not add up to the wall-time difference.

## Reproduction

Build all three revisions with the repository installer. Extract the Foundation fixtures into an empty directory, then run the comparison from the optimized checkout.

```sh
python3 -B tools/shared/build.py --build-dir "$PWD/.mlf-build/install"
git archive c5928b5b libraries/mlf-foundation | tar -x -C "$FIXTURES"
python3 -B tools/performance/foundation-query/indexed_graphs.py \
  "$INSTALL_29/bin/emlf" "$INSTALL_43/bin/emlf" "$OPTIMIZED/bin/emlf" \
  "$FIXTURES/libraries/mlf-foundation" "$NEW_STUDY"
```

The results include the binary and installation-receipt hashes, every sample with wall time, CPU and peak RSS, the stage timers for separately profiled runs and the output checks. [Machine-readable results](foundation-graphs.json).
