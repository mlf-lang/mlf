# Prepared expansion bulk-publication candidate: source-only, unqualified

Pinned main: fc300bc9fdc389b585cbef0630fc8915d53e89c5.
Solver blob: ac4807fa23c0763ba83a0f9c52c1c734cc059720.
See source-pins.json and candidate.patch. No GHC or benchmark was run; no remote branch changed.

## Existing evidence / why this path

Historical E 051d12e9d14a89254bf10255347bbd6a4e99b5ac already attributes 11,186 ms of solvePrepared's 15,764 ms to evaluateSteps on the Foundation15 fresh-crate diagnostic. These are natural lazy boundaries, not exclusive CPU. A distinct Root+Foundation --type profile attributes 14,134 ticks to prepared fallback, including 5,445 projection, 6,983 local unification, 1,327 restore. Neither identifies expansion insertion cost or predicts this patch's gain. No new localization run is warranted.

Exact main currently expands at Graph.hs:2258: expansionVisitCached, kindsAt, allocateCopies, then a strict fold calling setNode for every original. setNode (line 325) resolves the fresh identity, strict-forces the node, inserts into the full current map and makes a strict Graph wrapper. In Solver.hs:1912 expandedGraphPrepared calls this even though prepare has established allocation separation. The prepared transaction subsequently extracts the fresh range, builds compact projected nodes and later republishes survivors.

This candidate replaces ONLY the prepared expansion's publication fold with nodesFromDistinctAscList plus structural IM.union. It still builds the complete expanded Graph; it does not attempt virtual expansion, drop the local validation/rebinding or bypass fallbackPrefixRejected. Current IntMap.hs:263-280 has true Patricia structural union (not an insertion fold). This is distinct from stopped depth cursor, resolve memo, unchanged-binding, owner/LCA and cross-call projection-reuse candidates. Recovery-page search found no prior bulk-publication attempt, but is not a complete repository-history proof.

## Proposed equivalence argument and outstanding review

Required domain is the internal Constraint.evaluatePreparedSteps path after Solver.prepare/solverUnify, with all earlier operations preserving canonical live fields and every live/alias key below nextId. Total well-formed Patricia structure is an ADDITIONAL invariant supplied by standard constructors and the internal generation/solver chain; prepare alone does not validate arbitrary raw Patricia metadata. Do NOT replace public G.expand/G.expandWithScopes or claim arbitrary raw Solver equivalence.

1. Keep the exact source/generalization traversal, kindsAt error prepass, ascending originals, allocation routine, fresh IDs/copy map and frontier ordering.
2. IS.toList visited is finite distinct ascending. allocateCopies retains its ascending and advanceIdentity guards. New keys are a contiguous range beginning at the old nextId, hence absent from both old live nodes and aliases. Public setNode's fresh-ID resolve is the identity.
3. Every value is the exact unchanged G.expansionNode expression over the SAME old graph, copy map, kinds and scopes, not a progressively mutated graph. Node production is independent across entries.
4. G.nodesFromDistinctAscList forces strictNode in entry order. Original insertNodeMap also forces strictNode before insertion. mkNode only forces tag IDs, binder constructor and flag, not opaque constructor-name/kind payloads. Keep that behavior; never deepseq, force Eq, or precompute kinds again.
5. New ordering defers old-map structural search until the fresh map is built. This is the principal proof obligation: prepared input has total valid trie keys/prefixes/counts/spines and prior expansion only inserts total fresh keys; map insertion does not force old Node payloads. Thus removed/deferred structural accesses cannot supply a prior error/bottom in the admitted domain. Arbitrary raw malformed/partial maps need not be equivalent and remain on public old routes.
6. New helper retains all allocation prepasses. nodesFromDistinctAscList additionally traverses entry spine length, but originals/copies already completely traverse finite originals in allocateCopies; this must be explicitly checked for empty case and value demand in finite tests.
7. Disjoint union with fresh on left gives the same bindings, IDs, links, nextId and canonical Patricia shape as repeated insert. Existing structural union returns untouched subtrees without forcing their payloads. Verify full physical map/scope/index snapshots, not only extensional Eq.
8. No certificate survives the transaction. The exact prepared consumer still strict-forces current, runs old eligibility/prefix guards, unifies, preserves scopes and restores. No change to error boundaries outside publication.

This is a conditional source argument, NOT a completed Haskell semantic proof.

## Saved work, not promised speedup

For m newly copied nodes and old trie depth h, old publication rebuilds the insertion path and Graph wrapper m times and performs m known-fresh alias lookups. New publication builds the fresh Patricia tree linearly, then structurally joins it with old nodes. For separated ordered key ranges, only boundary/prefix paths require joining; shared untouched old subtrees remain shared. Precise signed-boundary operation counts must be checked against P.relation; do not advertise a formal O(m+h) theorem or a wall speedup before that check. Node creation, traversal, kinds, full local Graph validation, rebind, projection and restore remain. The saved profile does NOT isolate this cost. Added entries list/fresh map may increase peak residency; m=0/1 may be worse. This candidate is lower implementation risk than virtual expansion, but high leverage is still a hypothesis.

## Required finite actual tests before performance

Compare complete original G.expandWithScopes against candidate helper only on graphs obtained by real Solver.prepare and actual complete prepared Solver calls. Run O0 and O2; require literal expected errors and byte-equal complete results, including links, nextId, physical IntMap metadata, structuralParents, bindingChildren and ScopeIndex.

- empty/minimal source; one copy; many-copy branching source; sharing diamond.
- root inside scope vs outside frontier; mixed internal and external references; multiple frontier entries.
- bottom/GArr/GTyApp/GCon/GTyCon/GSkolem/kinded source combinations; original kind error first.
- prepared graph with existing aliases, signed/gapped old IDs and fresh range crossing Patricia prefix boundaries; near identity-limit failure exactly preserved.
- delayed constructor-name/kind poison in untouched old nodes and copied nodes; error before later poison; original entry ordering between two possible poisons.
- actual prepared fallback from existing real total/name tests: successful binder movement retained; constructor mismatch priority retained; opaque nonlocal name appears only at original restore boundary.
- ProjectCase then Instantiate, ground-graft and ground-instance routes; prove unchanged routes never call helper.
- deliberately invalid raw fresh counter/partial trie stays public old route; don't count it as prepared-domain success.
- compare public old helpers unchanged byte-for-byte and confirm only one private callsite selected.

Then a single bounded paired fair whole-crate screen, after async_audit's alias-free batch releases resources, may decide STOP/CONTINUE. Do not combine candidate with alias-free optimization in that comparison. Do not repeatedly profile or enlarge sampling to rescue an insignificant signal. Native fixed point remains paused.
