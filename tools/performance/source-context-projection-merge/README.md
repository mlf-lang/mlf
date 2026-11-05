# Source-context / projection-view composition

This layer composes PR29's source-query representation and normal-return scratch cleanup (`2c3ce0ee4d13cf8d2da19e745189cb85005d3cad`) with PR25's projection-view optimization (`9dfcd6625775819568eaaa5065f8dd1431df52f8`). Their common parent is `5172c4ade3b3141da2e64593c383892575b36699`.

Production `CrateSession` contains both changes. `CrateQuery`, CACHE3 bytes, full query-key semantics, legacy CACHE1/CACHE2 readers, raw prepared-group storage and cleanup behavior are unchanged from the PR29 parent. The lock file records the combined Session hash; it does not substitute a historical source identity.

## Frozen proof paths

The historical source-query-context, query-key-scratch and full-compiler contracts are byte-for-byte retained. The new test-only diamond has two independently pinned, whole-owner inverse/forward paths:

- Combined Session -> PR29 Session -> scratch inverse -> context inverse -> common Session.
- Combined Session -> PR25 Session -> projection inverse -> the same common Session.

Both full 128-module registry paths must agree exactly. The left transition changes only Session; the right changes Query and Session. Unknown, partial or reordered owners and stale/mixed live registries remain rejected; explicitly pinned historical owners are accepted only by replay adapters. The inverse adapters construct historical test inputs; they do not change the production compiler or serialized artifacts.

## Verification scope

The combined physical source view passed 192 Python checks: Patricia 50, A1 34, validation 7 and the unchanged full-compiler arithmetic suite 5, each under normal Python and `-O`. All parent methods are retained; four projection and four diamond methods extend the PR29 suite. The guarded run checked all 246 input files before and after, and the complete copied view remained unchanged.

This small unit run is not a combined compiler build, native qualification or performance result. The earlier local producer/31-runtime-control results remain pinned to the PR29 parent, not this combined Session. Exact-head hosted CI will separately build and exercise the merged code, retaining both source-context and full-compiler gates with their original limits. No timing or storage figure is newly inferred from the merge.
