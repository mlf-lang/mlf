# Declaration IDs from name resolution

The module resolver assigns IDs by defining entity after import and re-export resolution, before walking declaration bodies. Each top-level binding retains the IDs seen in its RHS. Source binding, crate planning and the resolved module linker consume those exact IDs. The class pass appends new vertices and redirects method IDs to generated selectors. Lexical ranks preserve the existing visit order. Serialized artifacts continue to use canonical names.

## Foundation compilation

Three installed GHC 9.14.1 `-O2` compilers compiled the same 14 Foundation modules from `c5928b5b` on an Apple M1 Max. The comparison of interest is the preceding #43 installation (`8dc22c96`) against resolver-issued IDs (`44c64957`). Times are mean elapsed seconds per new compiler process. The percentage is relative to the preceding #43 in this window.

| State | Paired rounds | #29 | Previous #43 | Resolver IDs | Time change | Faster rounds |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Warm, unchanged | 12 | 4.066 | 3.777 | 3.768 | -0.25% | 5/12 |
| Edit to Bootstrap.Version | 12 | 4.104 | 4.042 | 4.032 | -0.25% | 5/12 |
| Cold queries with installed Prelude | 3 | 19.532 | 20.265 | 19.336 | -4.58% | 3/3 |
| Both stores empty | 3 | 19.598 | 19.512 | 19.628 | +0.60% | 1/3 |

The warm and edited means each fell by about 10 ms, with the candidate faster in five of twelve paired rounds in each state. The cold result with an installed Prelude was faster in all three rounds. The first-install mean rose by 116 ms. The paired graph measurements below isolate the change in grouping work.

Each compiler used its own seed snapshot. Warm and edited runs restored that snapshot before timing. The process order rotated and the OS filesystem caches stayed warm. The interface, object, query report, logical graph and retained result bytes matched the preceding #43 in all four states. Warm runs reused all 504 groups and the edit inferred one and reused 503.

## Isolated graph work

A separate diagnostic compiler ran both algorithms on the same resolved Foundation inputs, checked the exact ordered memberships and alternated timing order over eight warm processes. The source-binding comparison also checked recursive binding mode. The namespace and RHS resolution that produced the inputs sits outside these timers.

| Graph operation per compile | Declarations | Before (ms) | After (ms) | Before (MB allocated) | After (MB allocated) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Bind resolved source values | 502 | 7.98 | 1.60 | 24.15 | 5.67 |
| Plan source and dictionary groups | 511 | 11.48 | 10.44 | 37.69 | 33.60 |

The controls exercise imported aliases and re-exports, local shadowing, equal emitted spellings for distinct entities, implicit pattern methods, synthetic entries, dictionary edges and recursive declarations. The MLF package compiler checked the frontend library. A linked native executable then reported `B.copy → A.value` and an empty row for its shadowing neighbour. Five xMLF outputs matched the preceding compiler byte for byte and passed checking in both directions.

Use the procedure from the [preceding Foundation study](foundation-graphs.md), supplying the `8dc22c96` installation as the middle arm and `44c64957` as the last arm. Use `--warm-rounds 12 --cold-rounds 3 --profile-rounds 0`. [All samples, hashes and output checks](resolver-ids.json).
