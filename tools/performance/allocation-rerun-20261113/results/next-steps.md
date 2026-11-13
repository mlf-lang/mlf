# Allocation-guided next steps

## Measured boundary

Source revision: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. This review parsed the archived qualification and final attribution reports with the unchanged r13 `profile.py`. It launched no compiler and changed no compiler source.

The final foundation14 attribution completed with 475 fresh groups, zero reused groups, all 14 owners and the builtin checked, and exact equality of the three output artifacts against the fresh ordinary reference. The installed writer and real allocation control established **bytes**, including an observed and expected control delta of 65,536. No additional word-to-byte multiplier applies.

| Disjoint source-demand group | Final allocated bytes | Share of final report |
| --- | ---: | ---: |
| SOLVE | 35,598,371,704 | 58.355229% |
| ENCODE | 10,496,368,840 | 17.206349% |
| Both | 46,094,740,544 | 75.561578% |
| All groups | 61,002,882,600 | 100% |

These are **profiled source-demand allocation**, not ordinary exclusive CPU, peak/live heap, or predicted savings. The partition charges each stack node's self allocation once to its nearest semantic label; inherited totals must not be added again. Sparse labels do not identify which inner solver or encoder routine dominates.

SOLVE and ENCODE allocations exactly match the earlier qualification run. The whole report does not: qualification total was 61,004,702,240 bytes. Its excess of 1,819,640 comprises PUBLISH 1,422,024, RESIDUAL/RTS 393,096, and RESIDUAL/UNKNOWN 4,520. Timing/ticks are not identical either.

Final raw profile SHA256: `2d18e2e46e69d249ab70b812ab803782853d0510c67f0c3a3a26b3dc5dc04031` (4,269,446 bytes). Qualification raw profile SHA256: `283c25f93465c4cbf1afe2982e2b13a58a65a78bfdc250818cfb8341a0850520` (4,269,473 bytes).

The three INVENTORY buckets sum to **950,432 bytes**: OPEN_INITIAL 664,816, OPEN_NORMALIZE 282,752, UNRESOLVED 2,864. That is approximately 0.00156% of this report. This is not evidence that removing any checker is safe, nor proof that every inventory-induced demand is isolated by this label. It does mean the previous inventory micro-optimization is not the leading allocation target here.

## First bounded candidate: reuse one fresh encoding for an input and its derived node

Concrete duplicate work exists in `libraries/mlf-crates/Bootstrap/CrateGraph.hs`:

- `recordInitialBindings`, lines 49–58: `input ... (contractValue contract)` is immediately followed by `G.record ... (contractValue contract)`.
- `recordDatatypes`, lines 59–68: `input wanted value` is immediately followed by `G.record wanted ... value`.
- `input`, line 48, delegates to `G.record` with `persist=False`; that flag does **not** suppress encoding.
- `libraries/mlf-crates/Bootstrap/QueryGraph.hs:41–50,121–133`: each record runs `encodeHashed`, including `Storage.encode 6 [value]` and the digest, before updating the session.
- `libraries/mlf-crates/Bootstrap/ArtifactStorage.hs:58–59` reaches `Bitstream.encode`; its planning/layout/writing path is at `libraries/mlf-crates/Bootstrap/Bitstream.hs:218–229,272–321,544–573`.

Small candidate: compute `encodeHashed value` once at each of these two paired call sites. On success `(digest,bytes)`, use the existing `recordDigest` first for the current nonpersistent Input (no payload/location), then for the persistent Binding/Datatype (the same digest and bytes), retaining exactly the derived node's `[edge inputNode]` dependency and the original session-update order. This is a local reuse of a freshly computed result, not a new cache or a stale-node shortcut. `CrateGraph.recordFinish:333–344` already uses `encodeHashed` plus `recordDigest` to publish the same contract bytes and digest together.

Required premises and limits:

- The exact same finite, admitted value and schema must be encoded. Keep `Separate.normalType`, class/protection fields, declarations, node identities, and ordered dependencies unchanged.
- Always refresh the authoritative Input from the current value, even when an old node has the same key. Do not use an old digest to avoid evaluating changed input.
- The returned byte array is an immutable snapshot by convention. Do not mutate it after hashing or introduce an independently supplied digest/bytes pair.
- Preserve first-encoding failure and avoid publishing any session update on that failure. Reusing success intentionally removes a second encode/hash IO execution; identical transient IO-failure/resource-exhaustion behavior is not established. Host partial values and exception/demand order need explicit treatment, not a universal equivalence claim.
- This does not justify suppressing `finishContentHash` verification/audit rechecks (`CrateGraph.hs:313–325`). Nor should publication be described as redundantly encoding every payload: `QueryGraph.hs:119–120` already retains the original encoding for publication.
- The report cannot assign the whole 17.206349% ENCODE group to these two sites. Their frequency and savings remain unmeasured.

Minimum actual regressions before accepting a candidate:

1. Compare original and candidate sessions for empty, singleton and multiple initial bindings/datatypes, including repeated values with distinct identities, Unicode, higher-kinded/bound types, class order, and protection differences. Compare node keys, hashes, ordered reads, payload locations, and pending bytes, not merely final success.
2. Exercise old matching nodes, changed authoritative values and changed/deleted inputs. Publish, reopen, and validate; compare exact payload/generation bytes and dependency invalidation.
3. Compare first failure on an invalid/over-budget value, ensure no partial publication, and include deliberately partial host values separately. Do not fake a second-IO failure equivalence claim.
4. Retain the existing query, codec and semantic checks, then repeat the same fresh foundation14 ordinary/profile artifact and query oracles. Measure before/after allocation under identical labels. Ordinary performance claims require a separate, paired unprofiled measurement under the existing user authorization; native-generation A/B and fixed-point remain paused.

## SOLVE: preserve checks; narrow the experiment first

The label encloses `C.solvePrepared` at `libraries/mlf-inference/Bootstrap/CompilerCore.hs:50`. Its actual route is `Constraint.hs:1255–1261`: prepare, initial solver unification, ordered prepared steps, then `finishNormalized`. Prepared instantiation is `Graph/Solver.hs:2185–2190`. Local projection paths reach unchanged `G.unify` at `Graph/Solver.hs:1055–1063,2144–2156`; `Graph.hs:1255–1262` retains validation, first-order work, rebinding and final validation. Do **not** conclude those validations are removable from a coarse allocation label.

One very small testable candidate is endpoint admission in `Graph/Solver.hs:1091–1093` and `2137–2139`. Both construct `concatMap G.equationNodes canonical` solely to check every endpoint's existence. `Graph.equationNodes:1145–1146` builds a two-element list, and the project `Std.concatMap:123–124` appends those lists. A dedicated pair loop can check `a`, then `b`, then the remaining pair list without constructing the flattened endpoint list.

Keep canonicalization and every membership/error check. Complete **all** endpoint admission before filtering self-equations or starting unification. Preserve `missing graph node <id>`, left-to-right order, and early failure without forcing the later endpoint/tail. In particular, an earlier equation's possible constructor/kind conflict must not outrank a later missing endpoint. Test aliases, self-equations, a missing first/second/later endpoint, a conflict preceding a missing endpoint, partial pairs/tails, and the prepared fallback route; compare complete resulting graph/index behavior on successes.

This is exploratory, not an attribution of 58.355229% to list construction. GHC may already remove some intermediates, and the change may be too small to matter. If it does not reduce allocation, stop pursuing it. Before a larger solver change, use narrow diagnostic labels around preparation, ground fast-path tests, expansion, component/scope projection, local unification and restoration/final validation. Keep their disjoint accounting and original correctness gates; do not replace the real target with a synthetic model.
