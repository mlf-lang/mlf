# Qualified ordinary recursion: implementation addendum

Date: 2026-10-24. This addendum records the implementation strategy following the ordinary unsigned-recursion core. It does not replace or change the original Chinese design report.

## Scope and current status

The new `Bootstrap.ClassDemand` module implements finite dictionary-interface planning. `Bootstrap.Classes` collects lexical demand equations and materializes the resulting dictionary lambdas/applications. The ordinary constraint solver, export materialization, xMLF evidence rules, and independent target checkers retain their existing roles.

Final local validation is complete for the bounded scope recorded in `Unsigned-Recursion-Final-Validation.md`: clean O0/O2 interface-audited builds, the 53-case recursive mode plus planner checks, frontend/source smoke, 78 existing class tests, terminating interpreter fixtures, and exact module/saved-crate compatibility. Production and unchanged frozen target checkers remain mandatory. One redundant legacy nested-interpreter saved-crate attempt was interrupted after the exact direct-GHC route passed; it is not counted as a guest pass.

The implementation is **arity-only planning**, not class-instance search before type inference and not a two-pass speculative discharge algorithm. It does not establish principal completeness for the combined MLF/class language.

## 1. Stable origins and lexical interfaces

The planner inputs are:

```
Frame id parent finishRank
Seed id classId ownerFrame
Use id bindingFrame receiverFrame
Demand = Empty | SeedNode seed | UnionNodes nodes
       | RefNode node | InstantiateNode use inputNode
```

Every known overloaded occurrence/context position has a distinct seed. Every unsigned inference SCC has one shared owner frame. Ordinary let RHSs and checked boundaries have their own abstraction frames. Source names are not identities.

An interface slot records its class, owner, and full origin path:

```
SeedOrigin seedId
InstantiatedOrigin useId sourceSlotId
```

The path is a DAG of slot references. It must not be collapsed to `(class, lastUse)` or `(originalSeed, lastUse)`: a later binding may instantiate two distinct earlier uses of the same seed.

Ordinary let remains a dictionary abstraction barrier. Its RHS demands describe the local binding's interface, while only actual uses in the continuation propagate demand outward. Thus an unused `let k = f in true` does not automatically export f's context. Dictionary abstraction is separate from type-variable generalization: `\y -> let k = inspect y in true` can abstract a dictionary whose argument remains captured from y.

Active recursive references transport their shared slots unchanged. A use of a completed binding copies only slots owned by that binding's frame or descendants. Captured ancestor-owned slots keep their identities. The solver rejects an unrelated sibling owner appearing as a supposed capture; the collector remains responsible for wiring each instantiation to the correct lexical input and receiver.

## 2. Finite-universe argument

Frames have unique finish ranks. Validation requires:

1. A parent finishes strictly after each child.
2. An instantiation's receiving frame finishes strictly after the bound frame.
3. All referenced frames, seeds, uses, and demand nodes exist.

If a copied slot's owner lies below the bound frame, then:

```
finish(owner) <= finish(binding) < finish(receiver)
```

Every origin-changing step therefore strictly increases the owner's rank. A captured-slot transport creates no origin. The rank order covers both nested child-to-parent moves and earlier-completed sibling-to-later-sibling moves; lexical depth alone would not suffice.

With F frames, a changing origin path has at most F−1 steps. There are finitely many seeds and syntactic uses, so the origin-path universe is finite. A coarse bound branches over uses at each step; worst-case growth is exponential, not claimed polynomial.

The implementation avoids enumerating every unrelated seed/use combination. `discoverUniverse` starts at actual `SeedNode` facts and follows reverse demand edges. It visits each `(node, slot)` fact once, allocating a memoized `(use, inputSlot)` transition only when that slot reaches the relevant `InstantiateNode`. Unused lexical paths therefore do not create a Cartesian expansion.

After discovery, `saturate` receives an immutable universe. It performs only set union and transition lookup and cannot allocate new slots. Missing transitions are errors. Its least fixed point must equal the independently computed discovery facts. There is no arbitrary iteration limit.

A representative feedback equation is:

```
Q_h = {q_h} union Q_f
Q_f = instantiate(h, U, Q_h)
```

The local q_h becomes q_U owned by f. When q_U reenters h it is a captured ancestor slot, so it is not copied again. Stable interfaces are Q_h={q_h,q_U} and Q_f={q_U}. Two source uses U/V retain distinct local descendants q_U/q_V.

## 3. Argument order and multiplicity

Slot-set membership and actual dictionary argument lists are different.

For a completed-binding call, materialization must:

1. Read the source interface's slots in its original deterministic order.
2. Apply `instantiateSlot plan useId` to each source slot individually.
3. Emit one actual dictionary application per source parameter, preserving order and multiplicity.

In the feedback example, h's two source parameters q_h and q_U both map to q_U at U. The caller still emits **two** dictionary applications, although its outward demand set contains only one slot. Iterating the deduplicated result demand instead would produce a partial application.

Every lexical abstraction allocates fresh term binder names even if the same SlotId already exists outside. A stable slot identity is not permission to capture an outer term dictionary instead of introducing the local let's dictionary parameter.

## 4. Full predicate types are inferred afterward

The stable plan supplies dictionary arity and provenance, not type arguments. Classes emits real dictionary lambdas and applications into the ordinary source/Core representation. Known selector/signature types then constrain their complete types through the existing MLF graph.

The unsigned shared root contains the complete dictionary-arrow interface:

```
Dict_C1 args1 -> ... -> Dict_Cn argsn -> valueType
```

Recursive references apply dictionaries before acting as source-level values, including when a recursive function is passed as a first-class argument. Ordinary equality constraints share this complete root inside the SCC. Completed exports can instantiate independently outside it.

Different origins remain distinct even when their solved predicates coincide. In particular, the planner never merges `Inspect Int` with `Inspect Bool`, or ignores later arguments of a multi-parameter class. Redundant equal-predicate dictionary parameters are allowed; context minimization is not part of this patch.

Generic constructed predicates such as `Inspect (Box a)` remain attached to their lexical origin. Their argument/bound ownership is established by ordinary graph inference, not inferred from the spelling `Box`, class labels, or a promising instance candidate. The same applies to higher-kinded and captured arguments. There is no first inference pass that replaces a formal slot with `SWanted` and then reruns inference under changed ownership.

`SWanted` remains a final discharge hole at the existing checked/outer boundaries. It is not used to stand in for generalizable formal parameters: its existing outermost argument allocation has a different scope purpose.

## 5. Export and evidence obligations

The existing export materializer operates on the full dictionaryful root. Predicate-only variables are therefore structurally reachable, and dictionary arguments that capture outer variables preserve their frontier identities. Freezing the value-only result and prepending dictionary arrows later would be incorrect.

The existing recursive closure stores old-to-export provenance. The group telescope supplies dictionary-only and peer-only variables while elaborating each RHS, and the existing projection removes variables not needed by that member's export. Target syntax/checking rules are not relaxed.

Givens, superclass projections, instance visibility, and ambiguity remain typed evidence responsibilities. `Evidence.resolveDictionary` checks complete predicate argument types, honors exact given scopes, and uses one-way instance matching. Having one concrete instance does not authorize choosing it to determine an unknown predicate argument.

Dictionary wrappers are present in the translated-source skeleton itself. Existing target checking, inferred-type comparison, and source/target erasure comparison remain required; extra value wrappers must not appear solely during elaboration.

## 6. Module visibility: verified boundary, not hypothetical policy change

`Module.candidateScope` uses transitive import reachability. Ordinary importers therefore receive defining-module instances even through empty exports/imports. The earlier design concern that a private defining-module instance necessarily disappears at a caller was not established and is not an outstanding language-policy decision for this implementation.

The actual visibility invariant is that signed/checked and instance-body boundaries retain their defining candidate scope. A downstream orphan instance must not leak backward into an imported signed definition or an import cycle. Existing regressions for these cases, plus the transitive empty-import positive control, must remain unchanged.

Unsigned inference follows the established ordinary-let dictionary abstraction model. It does not widen the candidate inventory or run definition-site instance reduction to remove syntactic slots.

## 7. Tests and remaining limits

`MLF.Tests.ClassDemand` supplies focused planner checks for:

- Seedless recursive cycles and distinct same-class origins.
- Nested owner reentry and duplicate actual arguments after set deduplication.
- Two separately instantiated nested uses.
- Full origin lineage through completed sibling bindings.
- Captured ancestor slots and rejection of unrelated sibling captures.
- No unrelated-use universe expansion.
- Equal/backward rank rejection and missing references.

Integrated acceptance tests cover generic self/mutual recursion, two concrete uses outside an SCC, unused local let controls, captured predicate arguments, predicate-only ambiguity, first-class recursive values, multi-parameter/higher-kinded classes, nested h with local and inherited demands, mixed signed/unsigned recursion, superclass evidence, and module candidate seals. Declaration reorderings and alpha-renamings should preserve acceptance and externally observed types.

Positive compiler cases use production and frozen target checking, target serialization round-trips, erasure comparison, and relevant O0/O2 execution. Negative target mutations demonstrate rejection of missing/wrong dictionary applications or invalid scopes.

The finite-rank proof depends on correct lexical collection and frame assignment. The planner validates its structural inputs, but does not independently reconstruct source scoping. Retaining redundant origins is deliberate; minimal contexts and a principal-completeness theorem are not claimed. Exact runtime coverage and bounded aggregate validation are recorded separately; this does not claim the full native campaign.

## Historical integration checkpoint

The first incremental optimized build passed the recursive and direct frontend
modes before the final clean builds. Final receipt identities, compatibility
routes, independent reruns, and remaining limits are recorded in
`Unsigned-Recursion-Final-Validation.md`, rather than treating the earlier
incremental result as authenticated final-build evidence.
