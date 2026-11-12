# Call-site demand review of the closedness candidate

Pinned source: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
Status: **static call-site analysis plus separately labeled tiny Python tests; no Haskell execution, production change, or performance result**. This is not a claim about a later main branch.

## Conclusions

1. Full equivalence on every `undefined`-containing Haskell value is not necessary to optimize a documented total-input production domain. Finite type structure with defined variable/binder IDs is a sufficient domain for the earlier extensional proof.
2. The real callers provide more evidence than an arbitrary XType, but not a blanket deep-evaluation guarantee. In particular, successful checking of an inferred RHS does not imply its entire newly assembled type has undergone `kindOf`.
3. A stronger, useful local boundary is successful `Check.termType ds M.empty ty` on the **exact same type**. Its kind-checking traversal covers the persistent-Set candidate's relevant bound-key lookups. Explicit root recursive annotations satisfy this boundary; all inferred nonrecursive let types do not.
4. A concrete partial **host value** can pass the existing public checker and both old closedness guards while the proposed bound-Set traversal forces a latent binder ID. It is given below. This is a static construction, **unexecuted and not shown producible from source text**.
5. At this pinned revision, the second closedness guard in `Open.check` is logically redundant with the successful inventory it just consumed. Keeping the first guard and investigating only that repeated guard is a narrower possible follow-up, not an installed optimization.

## What is checked, and when

Repository paths below are relative to the pinned commit:

- `libraries/mlf-xmlf/Bootstrap/X/Check.hs:278–298`: `closedBindingInventory` checks every entry with `S.null (T.freeVars ty)`, then demands the remaining inventory. `XLet` supplies its inferred RHS type; `XLetRec` supplies its explicit annotations.
- `Check.hs:261–270`: recursive annotations already pass `termType`, and each RHS is checked against its annotation.
- `Check.hs:256–259,159–182`: a nonrecursive RHS is inferred. Lambdas construct an `XArrow`, and type abstractions construct an `XForall`; there is no uniform final `termType` call on each assembled result.
- `Check.hs:310–329`: ordinary closed checks begin with empty type scope. Declaration-spine recursion extends term scope only, so root declaration annotations are checked in empty type scope.
- `libraries/mlf-crates/Bootstrap/OpenFragment.hs:72–80`: raw parameters pass `termType ds M.empty`; declaration inference runs; `owned <- snd answer` admits its guarded inventory; only then does line 79 repeat the closedness predicate.
- `libraries/mlf-xmlf/Bootstrap/X/Checked.hs:23–28,41–45`: ordinary opaque receipts contain the independent result, not a deep-normal-form certificate. Composed receipts at `Checked.hs:278–283,347–351` defer another independent inventory query.
- `libraries/mlf-foundation/Bootstrap/Std.hs:470–475,510–519`: `Either` binding distinguishes `Left`/`Right` without generally forcing the `Right` payload.

### Exact annotation boundary

`libraries/mlf-xmlf/Bootstrap/X/Type.hs:161–165` first enumerates `freeVars ty`, resolves their kinds, and then runs `kindIn`. With an empty incoming type environment, a successful result cannot leave a free variable unresolved (`Type.hs:174–185`). The `kindIn` traversal therefore starts with an empty kind map.

`kindIn`'s forall insertion and variable lookup (`Type.hs:191–220`) then follow the same bound-key structure as the candidate's persistent Set. Both use the same Map insertion/comparator; stored kind values versus unit values do not control Map shape or key comparisons (`Bootstrap/Map.hs:9–16,73–109`). All seven constructors' relevant children are traversed to successful results. Thus, under these pure source semantics, prior successful exact-type `termType ds M.empty ty` supplies a static termination/key-demand argument for the candidate returning True. It does **not** say the whole type, kind payloads, names, or syntax graph are in normal form, and it does not predict allocation/retention.

The distinction matters: checking a closed sub-annotation while an unused outer binder is in the ambient environment does not check the later type formed by wrapping that sub-annotation in a new outer forall.

## Concrete partial-host-value construction

Host-only pseudocode, not an added or executed Haskell fixture:

```haskell
bad  = XTyVar (error "latent outer binder ID")
good = XTyVar 7
x    = XName 1 "x"
m    = XName 2 "m"
p    = XForall good XBot (XArrow (XVar good) (XVar good))
rhs  = XTypeAbs bad XBot (XAbs x p (XVarTerm x))
body = XLet m rhs (XConstructor "()" [])
```

`error` here denotes a host exception/bottom, **not** the MLF constructor `XBot`. All type/term constructors are finite; only the unused outer binder's Int field is partial. No private receipt or fragment constructor is used.

### Why ordinary inference does not force `bad`

1. `XTypeAbs` runs `fresh` on empty type scope (`Check.hs:176–182,44–47`). Map lookup on empty ignores its wanted key (`Map.hs:73–76`), so this does not force `bad`'s ID.
2. Its bound is the ordinary `XBot`, which passes `wellFormedIn`.
3. The inner lambda checks annotation `p` under an ambient environment containing `bad` (`Check.hs:159–164`). But `FV(p)` is empty. `kindOf` resolves no free variables from that ambient environment and checks `p` using a newly empty kind map (`Type.hs:161–165`). Only the defined `good` ID is used.
4. The term-variable lookup returns `p`; inference constructs `XArrow p p`, then `XForall bad XBot (XArrow p p)`. No final kind check is applied to this combined type. The unit tail does not use the let-bound type.

### Why both old guards pass, but the candidate adds demand

Each occurrence of `p` has an empty free-variable set. Consequently the combined arrow has empty FV, and deleting `bad` from that empty set does not inspect `bad` (`Map.hs:137–140`). The old closedness guard returns True.

The Set candidate instead extends the scope with `bad`, then reaches `good` inside `p`. Its membership requires the map for `insert good (insert bad empty)`. Building that map compares the two IDs (`Map.hs:98–109`), forcing the latent Int and raising/diverging.

Two public paths expose this distinction:

- `Checked.check body`, then `Checked.declarationBindings`: the current receipt and old inventory can succeed; substituting the candidate at `Check.closedBindingInventory` introduces the extra demand.
- `Open.environment []`, then `Open.check env [] body`: the current independent inference and first inventory guard can succeed, and the existing repeated guard also succeeds. Replacing **only** `Open.check` line 79 with the candidate still introduces the extra demand, even though the first old guard has already passed.

These are static reductions using the pinned code, **not observed execution results**. They show that public successful-check receipts do not themselves rule out this partial-host-value shape. They do not show that parsing or compiling any real source program generates such a value.

## Where the earlier generic bottom examples do and do not apply

- For an exact annotation `XArrow (XVar a) undefined` or `XVar undefined`, preceding `termType` itself visits `freeVars` and cannot succeed. These examples must not be presented as already passing the real parameter/recursive-annotation path.
- Supplying the bad-forall type directly as an annotation also subjects the complete type to `kindIn`, which forces the problematic scope map before the closedness guard. The construction above instead **infers a new outer forall around a closed checked annotation**.
- Passing arbitrary entries directly to public `Check.closedBindingInventory`, or supplying an unvalidated raw `XEnv` to `inferDeclarationSpine`, has a broader domain. Such paths can witness generic bottom changes but are not the ordinary `Checked.check` / `Open.check` admission path.
- At `Open.check` line 79, a successful prior inventory proves that the old FV predicates terminated true on every owned type. It does not prove that a different scope-building predicate cannot demand additional IDs.

A practical sufficient domain is finite, well-founded type constructor/list structure with defined XTyVar values and defined IDs for every occurrence and forall binder. Constructor-name and kind payloads need not be fully forced merely for the two closure predicates. Establishing this domain for a source/parser/transform pipeline is a reasonable production obligation; universal equivalence on all partial host values is not the only possible gate. The inspected files alone do not prove that whole-pipeline property.

## Narrower follow-up: the repeated Open guard

A source induction over all `inferDeclarationSpine` branches at this revision gives:

- `XLet`: `closedBindingInventory` guards the one new pair, then the child inventory.
- `XLetRec`: it guards every annotated pair, then the child inventory.
- The terminal success inventory is `Right []` for the unit constructor; every other terminal inventory is `Left`.

For `owned <- snd answer` to yield `Right owned`, every contributing first guard has already succeeded and every child inventory has been admitted. Therefore every pair returned to line 79 has already passed **the identical predicate** `S.null (T.freeVars ty)`. The error `open fragment exports an open type` cannot arise at that repeated guard through these branches in the current pure implementation.

This is stronger than mere finite set equality: re-evaluating the same deterministic successful predicate on the same immutable types adds no new type-field demand that was absent from its first successful evaluation. The partial-host example above also passes both identical old guards; the problem arises from changing the predicate, not from its repetition.

Accordingly, studying removal of **only** line 79 while retaining all first inventory guards and independent inference is a narrower candidate than replacing both guards with the new Set traversal. No code change is made or authorized by this report. It still needs exact behavior/error/artifact tests, genuine host demand controls, cost attribution, and review against the revision actually targeted. Allocation/resource behavior and later checker changes are not proved by the source induction; if inventory admission ever changes, the redundancy argument must be revisited.

## Independent scope-cost model review

I read the complete `scope_cost_model.py` / `test_scope_cost_model.py` before independently running only:

```text
python3 -B -m unittest -v test_scope_cost_model.py
```

Observed: **9 tests passed in 0.046 seconds**. This includes 720 six-key insertion permutations with every prefix checked, the 888-type grammar at empty scope, duplicate/signed keys, recipe sharing, and the three adverse families. No Haskell or compiler ran.

The insertion/balance subset agrees by inspection with pinned `Map.hs:31–71,95–109`. Recipe forcing correctly distinguishes scope-extension expressions from materialized insertions and memoizes shared parents. This is not a general Haskell evaluator or proof of the whole Map module.

I independently regenerated the D=64 events and confirmed the table in `SCOPE-COST-NOTES.md`: unused has zero materialized inserts; innermost-once has 64 inserts, 367 insertion and 7 membership comparator events; outer-repeated has 367 insertion, 384 membership events, and 4,096 list equality events.

Its reference innermost-once reasoning is also correct: one singleton, one nonempty delete, then empty deletes; only **one invocation of the type-variable key comparator** occurs in that reference family. This does not mean one primitive integer comparison or one machine instruction. Comparator events, recipe events, Map-node equations, object allocations, bytes, and timings remain different quantities.

## Qualification gate

The concrete Set replacement remains source-only. Before a production change, qualify the actual allowed input domain, retain every checker and inventory-order invariant, and add a bounded real host test of the construction above under a separately admitted setup. If the supported API intentionally excludes partial host values, state and justify that scope rather than claiming they were already eliminated by checking. Benchmark only after correctness and demand gates; none of these findings establishes that closedness is an end-to-end bottleneck.
