# Independent review: remove only Open.check's repeated closure guard

**Accepted as a source-only patch candidate for later qualification, not as a production change or performance result.** The patch is not applied to the compiler, compiled, or run. No first inventory guard, type/kind check, independent inference, receipt boundary, or fragment-construction rule is removed.

Pinned source: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. `SOURCE-PINS.json` also records a full nine-file byte/hash comparison at main snapshot `fc300bc9fdc389b585cbef0630fc8915d53e89c5`; the relevant source files are identical there. This is source applicability evidence, not execution qualification or a claim about an uninspected later revision.

## 1. Minimal proposed change

`OpenFragment-remove-duplicate-guard.patch` deletes only this line from `libraries/mlf-crates/Bootstrap/OpenFragment.hs:79`:

```haskell
ensure (all (\p -> S.null (T.freeVars (snd p))) owned) "open fragment exports an open type";
```

It preserves, in order:

```haskell
mapM_ (Check.termType ds M.empty) (map snd ps);
answer <- Check.inferDeclarationSpine ds scope term;
owned <- snd answer;
Right (make env ps term owned)
```

Parameter uniqueness and scope construction immediately before these lines remain unchanged. There is no replacement boolean closedness traversal, new forcing, constructor exposure, normalization, or checker bypass. Set and Type imports are retained because other code still uses them.

Static patch checks, performed in memory only:

- Original `OpenFragment.hs`: 35,625 bytes, SHA256 `e392aae043afc2c13cda16e00caa6a3562dc5180d78dce27f699da7046c57c8b`.
- The seven-line original hunk matches exactly once; the resulting bytes differ by exactly the single 97-byte line.
- Hypothetical patched file: 35,528 bytes, SHA256 `2fce9e0bc418994b321ea453034b5e2ee69b3ca2b4e5b929f0f826fea62c09ae`.
- No compiler file was written and no build command was executed.

## 2. The inference and inventory stages must stay separate

All line references in this review refer to the pinned original files.

`libraries/mlf-xmlf/Bootstrap/X/Check.hs:286–307` returns:

```text
Either typecheck-error (result-type, Either inventory-error owned)
```

Those two `Either` layers are not interchangeable.

### Stage A: inference succeeds before inventory admission begins

- `XLet`, lines 289–293: infer the RHS, recursively infer the body, then return the result type together with a **deferred** guarded inventory.
- `XLetRec`, lines 295–298: validate the recursive scope and all RHSs, recursively infer the body, then return its deferred inventory.
- Recursive-scope details at lines 261–270 include duplicate IDs, scope collisions, all annotation checks, and RHS checks before entering the body.
- Terminal branches, lines 300–307: independently infer the terminal term before returning a deferred fragment-shape answer.

Thus a later RHS/body type error can beat an earlier declaration's deferred open-type inventory error. “Inference succeeds” here means its outer `Either` has returned successfully. It does **not** mean every inferred type payload, ignored field, or syntax graph is deeply evaluated.

### Stage B: inventory guards are admitted outer-to-inner

`closedBindingInventory`, lines 278–284, does:

1. `all` of the original closure predicate over this declaration/group's entries;
2. fail with `inference binding has an open type` if any entry is open;
3. demand the child inventory;
4. return `append entries rest`.

Consequently an outer open-type inventory error beats a later fragment-shape inventory error or a later inventory bottom, but does **not** beat a Stage A type error already discovered before any inventory was admitted. Within a recursive group, the first closure failure follows entry order. Empty recursive groups still admit their child inventory.

`Open.check:77–78` preserves this exact sequence: first bind the outer inference result, then bind its `snd`. The patch touches neither operation. It does not move closure checks into RHS inference or certificate construction.

## 3. Source induction over every inventory-producing branch

Let `P(ty) = S.null (T.freeVars ty)`. At this revision the two guards use the **same** Set and Type functions; `L.all`/`L.snd` in Check and unqualified `all`/`snd` in OpenFragment are the same `Bootstrap.Std` functions. There is no intervening type transformation.

For a successfully admitted inventory `Right xs`, prove that every returned pair has already passed `P` on its identical type value:

| Source branch | Inventory construction | Successful-return fact |
|---|---|---|
| `XLet name rhs body` | `closedBindingInventory [(name,ty)] child` | The new pair passed `P`; the child passed its own admission. |
| `XLetRec definitions body` | `closedBindingInventory (map bindingPair definitions) child` | Every annotation pair passed `P` in definition order; the child passed its own admission. |
| Terminal unit constructor | `Right []` | Vacuous. |
| Any other terminal term | Shape `Left` | It cannot supply a successful owned list. |

The recursive step follows from `closedBindingInventory:280–284`: its successful `Right` cannot be reached before both the local `all` and the child `Either` succeed. Its append preserves the exact pairs and order. This covers every constructor branch of `inferDeclarationSpine`, not just the intended production-shaped terms.

Therefore `owned <- snd answer` in `Open.check:78` already establishes that every pair returned to line 79 passed the identical predicate. The second diagnostic `open fragment exports an open type` is unreachable through this current successful-inventory path in the pure implementation. Removing that repeated check cannot turn a first-guard rejection into acceptance, because the first guard is untouched and still precedes fragment construction.

This argument depends on the current producer. It is not a license to accept an independently supplied claimed inventory or to delete the first guard later.

## 4. Partial values, lazy receipts, and the important demand limitation

The argument is stronger than merely checking finite set equality, but weaker than claiming identical runtime demand or heap behavior.

- If a first closure guard diverges/throws on a type, both versions still reach that unchanged first guard. Removing the second guard does not skip it.
- A successful first guard may leave irrelevant names, kinds, or unused binder IDs partial. Repeating **the same deterministic successful predicate on the same immutable type** does not introduce the bound-scope comparisons of the separate Set-based closedness candidate.
- In particular, the partial host value documented in `closedness/CALLSITE-REVIEW.md` passes the original FV predicate while a new bound-Set traversal can force an unused ID. This patch adds no such traversal; both its first guard and the former second guard use the original FV predicate.
- No claim is made about impure/unsafe field effects, arbitrary asynchronous exceptions, stack/heap exhaustion, or foreign corruption. Those are not established equivalent by this source induction.

**The flattened inventory spine has a real scheduling difference.** The first guards traverse each entries chunk, but `Right (append entries rest)` can retain lazy append thunks. The old second `all` forces the concatenated `owned` list spine before returning the Fragment; the proposed version can defer that spine until ownership or another consumer demands bindings. `Bootstrap/Std.hs:83–87` defines append as the ordinary lazy list constructor recursion. On the successfully admitted finite chunks it cannot add a new target error or force a new type field, but its allocations, lifetime, and forcing point can change. Retention and actual consumer-demand tests therefore remain required; “no extra type-field demand” must not be reported as “identical demand/heap.”

Opaque receipts are not assumed strict:

- `Checked.hs:23–28,41–45` store ordinary inferred type/inventory projections without deep forcing.
- `Checked.hs:103–111` accessors expose those separate fields.
- `Checked.hs:278–283,347–351` composed receipts defer an independent inventory query.

None of these functions changes. `Open.check` itself still independently infers its raw body; it does not replace that work with a receipt's asserted inventory.

## 5. Caller and boundary coverage

The local proof covers **every invocation of the unchanged public `Open.check` signature**: callers provide environment, parameters, and body, never a substitute `owned` list. Its owned inventory is always bound from its own `Check.inferDeclarationSpine` result.

Inspected direct routes:

- `InferenceUnit.hs:383–391`: fresh open-group compilation calls `Open.check`, then performs member ownership. Both independent checking and the later ownership step remain.
- `OpenFragment.hs:94–98`: `normalize` and `audit` re-enter `check`; their independent rechecking and audit fingerprint comparison remain.
- The standalone r3 safe-adapter fixture also calls public `Open.check`; the patch does not enable inventory reuse.

Other constructors/adapters are outside the changed path:

- `OpenFragment.hs:82–88`, `fromChecked`, obtains `Checked.declarationBindings` and calls private `make`; it does not execute line 79 before or after this patch.
- Freshening and trusted decoding have their own unchanged evidence/boundary paths. The patch neither adds admission there nor weakens their checks.
- Direct public `Check.inferDeclarationSpine` / `closedBindingInventory` callers and deferred composition queries are unchanged, including nonempty-type-scope raw controls.

No exhaustive repository-wide alias/call-graph enumeration is claimed. It is unnecessary for this local invariant because every call to this function executes the same fixed internal producer/admission sequence, but downstream integration tests are still required.

## 6. Independent admission-protocol model review

I read `admission_model.py` and `test_admission_model.py` completely, then independently ran only:

```text
python3 -B -m unittest -v test_admission_model.py
```

Observed: **10 tests passed in 0.027 seconds**. The bounded enumeration contains **6,342 admission protocols**, not 6,342 xMLF programs or types. Its construction has 32 declaration protocols, declaration lengths 0–2, three terminal protocols, and two precheck outcomes: `(1 + 32 + 32^2) * 3 * 2 = 6342`.

The model correctly separates declaration/terminal inference outcomes from delayed outer-to-inner inventory probes. It tests body-type-error precedence, outer-open versus terminal-shape/inner-bottom precedence, recursive entry order, unchanged first-guard bottoms, export order, and the absence of the repeated probe on the proposed route. No model code defect requiring correction was found in this review.

Important limits:

- Closure states are immutable/idempotent symbolic answers (`closed`, `open`, `bottom`), not real XTypes or free-variable computations. Modeled bottom is a test exception, not a general Haskell semantics.
- One `inference_error` summarizes a declaration's outer `Either` failure. The model does not reproduce recursive annotation/RHS checking, kind checking, or arbitrary lazy inferred-type computations.
- Python tuple concatenation in `admit` is eager. It does **not** validate the lazy flattened-list-spine scheduling discussed in section 4.
- Precheck is one abstract phase, not independent validation of parameter uniqueness, parameter types, datatypes, or CompilerCore errors.
- Successful N-export protocols reduce **symbolic predicate invocations** from 2N to N. This is not a claim of halving compiler work, allocated bytes, or actual optimized calls.

Two fault-injection tests deliberately break the premise: skipping the first guards, or appending forged exports after admission. In each case the old and proposed routes differ because the old second guard catches the corrupted inventory and the proposed route does not. These are useful negative controls, **not real reachable compiler states**. They expose the maintenance cost of deleting defensive redundancy: a future producer regression must be caught by explicit first-guard/contract tests, not assumed harmless. No unsafe constructor or mutation is proposed for production.

Reviewed model hashes:

- `admission_model.py`: `0b3516a6e7d1c5e43e4ef9829f99b0408d5224c479798708cf3fa0c2c62b8da0`
- `test_admission_model.py`: `f2778c0fd6106ff0dc4cc9f4a8ab3b51eb2586468636f620e16e4d04c2d297ae`

## 7. Required future actual Haskell qualification

No command or admission is granted by this list. Do not run these checks until the separately required environment cleanup/admission is established.

1. **Ordinary build and source identity:** compile the exact one-line candidate against the authenticated ordinary closure, without mixing profiled artifacts or stale producers. Retain complete diagnostics and exact build inputs.
2. **Independent old/new public checker comparison:** cover empty/unit fragments, ordinary lets, recursive groups including empty groups, mixed let/rec spines, local RHS binders, polymorphic/higher-kinded annotation shapes, datatype contexts, and signed/spaced IDs. Compare ordered parameters/owned pairs, bodies, used parameters, fingerprint, encoded body, and downstream interface/object/query bytes.
3. **Unchanged front-end failure order:** duplicate parameters before bad parameter type, bad parameter type before body checks, duplicate/colliding recursive binders and invalid RHSs, invalid datatypes/constructors, and typed nonfragment tails. Retain exact existing error strings and production phase prefixes.
4. **Two-layer raw-checker controls:** using public `Check.inferDeclarationSpine` with a deliberately nonempty valid type environment, let an earlier RHS infer an open type. A later unbound/type-invalid tail must win at Stage A; with a well-typed nonfragment tail, the earlier first inventory guard must win at Stage B. This is a raw checker control, not a claim that Open's empty-type-scope parameters admit an open type. Do not forge an opaque receipt to manufacture the case.
5. **Partial/lazy host controls:** retain the previous genuine partial-host construction; first-guard bottom/failure controls; type-only and pending-inventory access; and lazy names/stamp/free-name fields. Separately observe Fragment WHNF/body/parameters versus owned-spine demand, then compare fully demanded outputs. Test-only forcing must not be moved into production or timing paths.
6. **API routes:** exercise named and indexed fresh open-group compilation, `normalize`, `audit`, existing `fromChecked`/composition controls, and the r3 positive/negative safe-adapter fixture. Keep complete original CheckedBindings and relevant scope/context/artifact suites; a new small fixture is not their replacement.
7. **Producer-contract regression:** preserve a real test that the first `closedBindingInventory` rejects open types and precedes child inventory errors. The symbolic fault injections demonstrate why this is mandatory if the second guard is removed.
8. **Cost and retention:** measure actual time/allocation/live retention under representative consumer demand, especially direct Open.check consumers that do not immediately demand bindings versus InferenceUnit ownership consumers that do. The symbolic 2N→N count and deletion of one source line do not establish an end-to-end benefit. If the changed flattening point matters, a separate future comparison may consider a spine-strict variant that forces only the owned list spine without rerunning freeVars. No such variant is implemented or included in this minimal patch, and its own demand/cost behavior would need qualification.

**Decision:** the current source induction justifies a narrowly scoped experiment deleting only the repeated guard, with first guards and independent checking intact. Operational validation, defensive-invariant regression coverage, and measured benefit remain pending. No production optimization has been installed.
