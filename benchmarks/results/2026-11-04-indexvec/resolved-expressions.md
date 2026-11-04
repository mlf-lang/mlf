# Declaration references in resolved expressions

The resolver assigns a declaration slot to each top-level value or method. A resolved global occurrence contains only that slot. The canonical spelling lives in the declaration table. Both SCC construction and instance helper capture traverse the same expression, including the two method slots of an overloaded string pattern. Changing a single leaf changes both its graph edge and the name selected when projecting that expression.

The file query driver selects each SCC's members from an indexed declaration table and restores their original source order for inference. Named class lowering and xMLF still consume a projected view. Serialized crate references and query keys use canonical spellings. Each new resolution is free to assign different slots.

## Foundation query benchmark

Three GHC 9.14.1 `-O2` installations compiled the same 14 Foundation modules from `c5928b5b` on an Apple M1 Max. The previous #43 code was `44c64957` and the indexed expression implementation is `14a7c1ce`. The table gives mean elapsed seconds per new `emlf --compile-crate` process. Percentage changes and faster-round counts compare the new implementation with the previous #43 in this run.

| State | Paired rounds | #29 | Previous #43 | Indexed expressions | Change | Faster rounds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Unchanged, warm | 12 | 3.759 | 3.515 | 3.528 | +0.38% | 6/12 |
| Edit to Bootstrap.Version | 12 | 3.862 | 3.807 | 3.826 | +0.50% | 5/12 |
| Cold queries with installed Prelude | 3 | 18.253 | 18.803 | 18.715 | -0.47% | 3/3 |
| Both stores empty | 3 | 19.166 | 18.569 | 18.352 | -1.17% | 2/3 |

The candidate was 13 ms slower on the warm mean and 19 ms slower after the edit. It was faster in six and five of the twelve paired rounds respectively. Cold means fell by 88 ms with an installed Prelude and 217 ms with both stores empty, over three rounds per state.

Every query report contains 504 groups and 511 members. The largest group has four members. The previous driver's two full-list filters tested membership for 257,544 rows over the compilation. The indexed path selects the 511 members directly, inspects the first slot to classify each group, and sorts only its members. These counts describe member selection. The elapsed times include parsing, resolution, class analysis, cache admission and publication.

Warm builds reused 504 groups. Editing `Bootstrap.Version` inferred one group and reused 503. Cold builds inferred 504 groups. Across all four states, the interfaces, objects, query reports, logical query graph and retained payloads matched the previous #43. Compiler order rotated, each run restored its arm's own seed where applicable, and OS filesystem caches stayed warm.

A separate development build carried checked predecessor overloads, protection and reserved names incrementally between groups. In six paired rounds per state, mean warm time went from 3.766 to 3.761 s and mean edit time from 4.046 to 4.040 s. That 5–6 ms difference did not justify the additional query-driver state. The released implementation uses ID-based member selection. The raw results include these 24 trials separately from the installed comparison.

## Identity controls

A two-crate fixture gives the same exported declaration different slots in producer and client. The defining crate's canonical spelling agrees in both tables. All four old/new producer and client combinations generated identical interfaces, objects and cold query reports. Each linked program printed `42` under both readers. A native resolver probe also checked a qualified reference and a shadowing local, and five xMLF outputs matched the previous compiler and passed checking in both directions.

The optional MLF build of the compiler libraries completed six dependencies, including the changed frontend. It checked all 1,696 groups of `mlf-crates` and wrote the interface and object. Publication then failed with `binary expanded-work limit exceeded` and produced no current query generation. The [earlier self-build receipts](selfhost.json) record the same publication error for #29 and the initial #43. The Foundation timings above use the installed GHC-hosted compiler.

Use the [Foundation procedure](foundation-graphs.md) with the #29, previous #43 and indexed-expression installations as the three arms. Pass `--warm-rounds 12 --cold-rounds 3 --profile-rounds 0`. The [raw results](resolved-expressions.json) include all 90 trials, paired deltas, CPU and peak RSS, binary and corpus hashes, output hashes and test receipts.
