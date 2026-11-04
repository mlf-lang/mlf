# FinishScc fragment receipts

The previous #43 compiler ran class and evidence finalization and serialized the complete final fragment of every SCC to compute its version. The same fragment also went into the formal object. The new compiler records the group, a SHA-256 commitment to the checked fragment and its ordered environment, and the hashes of the exported contracts. The generation index binds the group key, ordered dependency versions and receipt address. A change in reads can update the graph while an equal result keeps its version.

Finalization explicitly returns either the original checked raw body or a checked replacement. The original fragment with its original environment already has a verified content address from `InferScc`. An adapted fragment or a different environment is hashed using the same canonical encoding. Both ICH and semantic audit rehash retained content. Each visit constructs the small receipt from current checked inputs. Its contract digests refer to the exact buffers published as `Binding` results. The final object continues to carry the actual fragment.

## Foundation compilation

Two complete GHC 9.14.1 `-O2` installations compiled the same 14 Foundation modules from `c5928b5b` on an Apple M1 Max on 2026-11-05. The reference compiler is #43 at `537fd9ad` (implementation `320844cb`). The candidate compiler sources are `10779b42`. Times are mean elapsed seconds per fresh `emlf --compile-crate` invocation. Order alternated between arms and each arm restored its own seed snapshot. OS filesystem caches were warm.

| State | Paired rounds | Previous #43 | Finish receipts | Change | Faster pairs |
| --- | ---: | ---: | ---: | ---: | ---: |
| Warm, unchanged | 12 | 3.810 | 3.156 | -17.16% | 12/12 |
| Edit to Bootstrap.Version | 12 | 4.012 | 3.446 | -14.12% | 12/12 |
| Cold queries with installed Prelude | 3 | 19.413 | 18.885 | -2.72% | 3/3 |

In three separately profiled rounds per state, the mean `finish_ms` timer went from 698 to 134 ms warm and from 733 to 137 ms after the edit. Cold runs inferred 504 groups. Warm runs reused all 504. Editing `Bootstrap.Version` inferred one and reused 503.

All 66 profiled and unprofiled samples produced byte-identical interfaces, formal objects and query reports between arms within each state. An independent reader compared 3,403 query keys and 19,277 ordered reads across both installed compilers in the seed and edited snapshots. Finish result hashes and corresponding read versions changed with the receipt format. All other result hashes matched. Of the 504 receipts, 496 directly referenced the retained raw content and 8 required a new digest. Reconstructing the content from the emitted object and current environment matched every receipt. The result store grew from 6.078 to 6.740 MB (504 additional files, decimal bytes). Filesystem allocations for those result files grew by 2.064 MB on this host.

## Recovery and compatibility

The query controls exercised swapped owners, a stale digest for the same owner, reordered reads, mismatched node and payload addresses, a final receipt presented as raw, and the previous cache configuration. Missing or damaged receipts were repaired with all raw groups reused. Failure injection and concurrent writers preserved atomic publication. The source tests independently compared final bodies, exported contracts and runtime results for source and lowered programs. Five xMLF programs and four old/new producer and client combinations passed cross-checking.

The additional MLF build inferred 1,715 groups of `mlf-crates`, wrote its interface and object, then failed to publish the query graph with `binary expanded-work limit exceeded`. The [earlier self-build receipts](selfhost.json) show this limit on #29 and on the first #43. The performance comparison uses the installed GHC-hosted compilers.

To reproduce, build both revisions with `python3 -B tools/shared/build.py --build-dir INSTALL` in separate checkouts. Run the harness against the 14-module `c5928b5b` fixture with the following arguments.

```sh
python3 -B tools/performance/dense-decode/foundation.py \
  BEFORE/bin/emlf AFTER/bin/emlf FOUNDATION_DIR FRESH_OUTPUT \
  --warm-rounds 12 --profile-rounds 3 --cold-rounds 3
```

The [raw results](finish-receipts.json) retain all elapsed, CPU and peak RSS samples, paired deltas, build and source hashes, output hashes, graph comparison and test receipts.
