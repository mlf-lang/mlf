# Independent bulk-publication source review

Verdict: GO FOR FINITE SEMANTIC TESTS ONLY, with the domain correction below. NOT semantic qualification, production admission or benchmark admission.

Reviewed exact Solver original and candidate, candidate.patch, Graph setNode/strictNode/nodesFromDistinctAscList/allocateCopies/expandWithScopes, and immutable fc300 Std.advanceIdentity and IntMap construction/union source via GitHub. No Haskell test or heavy job was run.

## Source observations

- The patch reverses exactly to pinned Solver by removing one new helper and reverting exactly one callsite. Existing public evaluateStep/evaluateSteps and Graph.expand/expandWithScopes are untouched. New helper is internal by call convention, not hidden by a Haskell export list.
- Source traversal, kind error prepass, copy allocation and frontier construction are textually equivalent to baseline. allocateCopies guards the complete identity increment before returning its strict pair, so a new fresh-map length pass cannot move identity exhaustion past expansion payload demand.
- Both old insertNodeMap and new ordered builder force strictNode of each expansionNode in ascending originals order before using that entry key for map insertion. The additional entries-spine pass does not demand entry values. Original allocation already consumes the finite originals spine.
- Fresh IDs are absent from old links/nodes under prepared allocation separation; resolving them is the identity. Since old expansion only changes nodes, each later fresh alias lookup is also the identity.
- IntMap.union is structural Patricia union on current main, not a fold. Disjoint maps cannot invoke the combining function on values. Reordering structural traversal is safe only if trie metadata and spines are total and valid. Union and insert constructors force count/prefix structure but do not deep-force old Node payloads.
- Kind/name/flag/binder demands inside expansionNode are unchanged; no assertion allows opaque payload evaluation or skipping original restore. No validation, scope gate, full graph materialization, rebind or restoration was removed.

## Required domain correction before qualification

Solver.prepare does NOT call IM.validTree and cannot alone establish total well-formed Patricia metadata for arbitrary graphs made with raw IntMapTree constructors. It validates graph relations and key/fresh separation; canonicalize preserves some raw tree count/prefix fields. The proof must additionally cite standard total IntMap constructors in the actual internal generation/prepared-operation chain. Do not say every result of arbitrary prepare input is admitted. Preserve public raw helpers. Keep raw malformed/partial-map controls explicitly outside the optimized private-domain equivalence claim, and check exported helper conventions in documentation.

## Finite tests required

1. Complete ordinary prepared Solver transactions, not only helper output: compare physical graph tree/count/prefix, links/nextId, reverse indexes and ScopeIndex after success, plus literal original errors.
2. At least one actual prepared fallback (not a test that groundGraft/groundInstance exits before candidate); binder-changing real total/name and mismatch/poison cases must execute this route.
3. Internal/external frontier, shared DAG, higher-kinded structure, existing aliases, signed/gapped identity ranges, fresh ranges straddling Patricia masks, and identity exhaustion.
4. Ascending two-poison ordering, delayed constructor names and kinds, nonlocal restore poison, earlier constructor failure before later poison; compare O0 and O2.
5. Public raw Graph expansion remains identical source and behavior. Do not claim arbitrary manufactured Solver input equivalence.

Performance unknown. The expansion publication fold cost is not isolated by existing broad evaluateSteps/fallback profiles, and fresh-map retention/list allocation can negate saved path copies. No high-leverage or asymptotic wall-time claim is established. Stop if finite controls fail; do not overlap alias-free measurement.
