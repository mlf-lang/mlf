# Source-only owned-spine variant

**Disposition: narrow experimental alternative, uncompiled, unrun, and unapplied.** This variant retains the original guard's full owned-list-spine demand before `Open.check` returns `Right`, but does not repeat the free-variable predicate. It is not a claim of identical heap, allocation, stack, timing, or optimized evaluation behavior.

Base source: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. The existing source pin record also establishes identical relevant files at main snapshot `fc300bc9fdc389b585cbef0630fc8915d53e89c5`, not at an uninspected later revision. The old delete-only patch and its review remain unchanged. **Both patches are alternatives against the original base, not successive patches to apply together.**

## 1. Candidate

`OpenFragment-spine-only.patch` changes only the final repeated guard / return in `libraries/mlf-crates/Bootstrap/OpenFragment.hs:76–81`:

```haskell
mapM_ (Check.termType ds M.empty) (map snd ps);
answer <- Check.inferDeclarationSpine ds scope term;
owned <- snd answer;
-- Inventory admission already checked each type; retain only the old
-- guard's demand on the complete owned list spine before returning Right.
seq (all (\_ -> True) owned) (Right (make env ps term owned))
```

The parameter checks, complete inference action, first inventory guards, exact owned pairs/order, and lazy `make` fields are unchanged. No new helper, exported API, type scan, boolean closedness algorithm, or independent-checker removal is introduced. The wildcard deliberately does not pattern-match or evaluate an owned element.

The patch was checked by matching the original hunk exactly once and replacing it **in memory only**:

- Original: 35,625 bytes; SHA256 `e392aae043afc2c13cda16e00caa6a3562dc5180d78dce27f699da7046c57c8b`.
- Hypothetical variant: 35,712 bytes; SHA256 `76539b0c774841050c591d258ec3ed34b050bcf8bb727ca018cea50d2118671c`.
- Patch SHA256: `c6031fa96b0e2ecdfdcf51b2731efac3476a1f7db80239a921404f7214d195a4`.

`SPINE-PATCH-CHECK.json` records those checks. No compiler source was written, no Haskell compiler/test ran, and source syntax/type correctness is not a compiled result.

## 2. Why Bool WHNF here means full list spine, not full elements

Pinned `libraries/mlf-foundation/Bootstrap/Std.hs:146–151` defines:

```haskell
all f xs = case xs of
  [] -> True
  x : rest -> f x && all f rest
```

For the candidate's `f = \_ -> True`, this specializes semantically to:

```text
spineBool []         = True
spineBool (_ : rest) = spineBool rest
```

To obtain the final Bool constructor for a finite list, evaluation must inspect every cons cell and the final empty-list constructor. `seq` demands that Bool to WHNF before allowing the `Right` constructor to be observed. Since Bool has no field inside `True`, this is sufficient to complete the traversal. It does **not** demand element constructors, names, types, or other payloads through the wildcard.

These distinctions matter:

| Expression before the return | What it guarantees |
|---|---|
| `seq owned result` | Only the first list constructor; a nonempty tail can remain unevaluated. Insufficient. |
| `let pending = all (\_ -> True) owned in result` | Nothing if `pending` is unused. Haskell let-binding is lazy. |
| An ignored `Right (all (\_ -> True) owned)` action | `Either` binding need not force the Right payload (`Std.hs:470–475`). Insufficient. |
| `seq (all (\_ -> True) owned) result` | Full finite spine before `result` can be observed; no predicate over elements. Chosen variant. |
| `seq (length owned) result` | Also traverses the spine, but adds unnecessary numeric accumulation/strict arithmetic (`Std.hs:69–79`). Not selected. |
| `seq (foldr (\_ rest -> rest) () owned) result` | Another spine-only recursion for finite lists, but a different formulation/optimization target. Not implemented this round. |

The source-level `seq` cannot be replaced by a claim that a Bool is “obviously True”: on a bottom tail or infinite list the traversal does not return True. An optimizer may specialize/fuse the worker or exploit proven domain facts while preserving its supported semantics, so source recurrence counts are not measured runtime work.

## 3. The admitted-list restriction is essential

The invariant from `REVIEW.md` is unchanged. `Check.inferDeclarationSpine` first completes its outer inference `Either`; then `owned <- snd answer` admits a separate inventory. Each `XLet`/`XLetRec` inventory chunk passes the original `S.null . freeVars` predicate before its child inventory is admitted (`libraries/mlf-xmlf/Bootstrap/X/Check.hs:278–307`). The terminal successful inventory is empty.

A successful admission therefore provides finite traversed chunks, exact original pairs, and a finite append-built owned spine. It does not provide deep-normal-form names, types, kinds, or arbitrary metadata. The original predicate has already forced each entry pair enough for `snd` and the closure query. The new traversal adds no head/pair/type demand beyond admission.

The original second guard also traverses the complete flattened spine on this domain because every repeated predicate is True. The proposed `all (\_ -> True)` traverses that same finite spine at the same **return boundary**, without repeating those predicates. It leaves the two-stage error order intact: parameter checks → all outer inference actions → outer-to-inner inventory admission → final return-boundary traversal.

This is **not** a generally equivalent replacement for `ensure (all P owned)` on arbitrary lists:

- An unadmitted open element makes the original guard return its error; the spine-only form does not validate it.
- A bottom element can be ignored by the wildcard although an arbitrary `P` would force it.
- A bottom or infinite list tail prevents the spine-only traversal from returning; delete-only or `seq owned` can return earlier on an arbitrary nonempty list.
- If a producer regression skips first guards or forges inventory after admission, both new candidates lose the old second guard's defensive rejection. Existing protocol fault-injection controls remain mandatory.

Those examples delimit the helper's meaning. They are not claimed to be reachable successfully admitted inventories of the unchanged producer. No first guard is removed to make them reachable.

## 4. Three different observation points and three alternatives

`Open.check` returns an `Either String Fragment`. Observing its outer `Right` is not the same as evaluating the Fragment payload to its data constructor, and neither is the same as demanding `Open.bindings`.

`OpenFragment.hs:69–70` builds a Fragment whose bindings, free-name discovery, and stamp fields remain lazy. The candidate's `seq` runs **before the outer Right can be observed**; it does not use Fragment field strictness as a substitute.

For a successfully admitted nonempty inventory with deferred append construction:

| Observation | Original repeated guard | Delete-only candidate | Spine-only candidate |
|---|---|---|---|
| First inventory admission | Original local predicates; append result can remain lazy | Same | Same |
| Outer `Right` available | Flattened owned spine traversed; repeated closure probes performed | No extra flattened-spine traversal required | Flattened owned spine traversed; no repeated closure probes |
| Fragment payload WHNF | Constructor available; no new fields forced merely by construction | Same; owned spine can still be deferred | Same; owned spine already traversed |
| Bindings list WHNF | Spine was traversed already | At least first resulting list constructor demanded; empty chunks may be skipped | Spine was traversed already |
| Head pair / selected head payload | Whatever that specific consumer needs; first guards already evaluated the pair for `snd` | Same distinction | Same distinction |
| Full bindings traversal | Already constructed spine is visited | Remaining append spine is demanded now | Already constructed spine is visited |

`Std.append:83–87` creates the flattened list lazily. The spine-only variant targets the specific demand-scheduling difference identified for delete-only; it is not a separate declaration validator.

**No heap-equivalence conclusion follows.** Removing repeated Set construction changes intermediate work and garbage-collection opportunities. Bool recursion, eliminated `Either ()` work, specialization, inlining, retained closures, stack use, and observer order may differ. Even if both alternatives reach the same spine observation boundary, exact time/order of allocations and lifetime of temporary values can differ. Do not call this “preserving all laziness,” “allocation-free,” or “performance-equivalent.”

## 5. What is and is not validated now

Completed lightweight checks so far: restored source hashes matched the saved pins; the old delete-only artifact hashes remained unchanged; the new hunk matched exactly once; the hypothetical replacement bytes were computed without applying it to a compiler tree. Only this source-level candidate and associated review are being added.

The independent lazy-list observation model is reviewed in section 7 below. Such a model can check its specified memoized force-event protocol, not prove actual Haskell runtime traces. In particular it must keep these categories distinct:

- previously admitted entry chunks/pairs versus newly forced flattened append cons cells;
- the outer Either's WHNF versus Fragment payload WHNF;
- a pair's WHNF versus its name/type/metadata fields;
- full spine traversal versus element validation;
- observer-triggered forcing versus initial return-boundary forcing.

A modeled poison head/list tail outside the admitted domain is a useful helper-discriminator, not a real checker admission result. Actual host demand tests, compilation, artifacts, and profiling remain pending and separately gated.

## 6. Future qualification, without widening this patch

1. Keep the exact producer and first-guard tests from `REVIEW.md`, including the two-stage error priorities and invariant-breaking negative controls. The spine-only form is not a replacement for those guards.
2. Compile and compare the unchanged baseline, delete-only, and spine-only alternatives separately against the same authenticated ordinary source/toolchain setup. Do not layer the two alternative patches or mix profiled objects into ordinary qualification.
3. Observe `Open.check` outer WHNF, Fragment WHNF, body/parameters, bindings WHNF, selected head payloads, and full bindings traversal separately before comparing fully demanded outputs. Do not force extra fields in production merely to simplify the test.
4. Include empty inventories, empty recursive chunks between nonempty chunks, multiple let/rec chunks, repeated consumers, and the previously documented partial-host unused-binder-ID case. Require unchanged exact errors, owned order/types, body, fingerprint/encoding, and downstream artifacts.
5. Pure value equality alone cannot reveal allocation timing of a finite total append spine. Any real force-event/retention instrumentation must be an explicitly test-only, bounded, separately admitted setup, not an exposed production inventory constructor or an unlabelled performance build. Instrumented traces are not ordinary-build performance measurements.
6. Measure end-to-end cost and retention under representative consumer demand only after semantic qualification. The spine-only form intentionally retains an O(number-of-exports) source-level traversal; the removed repeated type queries may or may not have meaningful measured cost.

No Haskell/GHC, heavy process/guard test, cleanup operation, execution-quarantine bypass, or native A/B/fixed-point run is authorized or performed by this work. A future check decides which candidate, if either, is worth adopting.

## 7. Independent lightweight model review and rerun

I read the complete `lazy_spine_model.py` and `test_lazy_spine_model.py` before executing only their pure standard-library suite:

```text
python3 -B -m unittest -v test_lazy_spine_model.py
```

Observed: **12 tests passed in 0.032 seconds**. No Haskell, compiler, process/guard test, benchmark, or native execution ran.

The finite protocol generator uses six group shapes and lengths zero through three: `1 + 6 + 6^2 + 6^3 = 259` protocols. The suite compares original/delete/spine alternatives under the specified sequential observations, not every possible Haskell consumer. Dedicated controls additionally cover empty groups, separate Either/Fragment WHNF, first-guard pair forcing, partial name payloads, shared memoized spine consumers, a weak `seq owned` analogue, and unadmitted bad-head/bad-tail cases.

No correction to the model code was required by this review. Its scoped result is:

- Original and spine-only have the same modeled force/flatten events after removing the original's repeated-closure events.
- Delete-only defers flattening from the return boundary to bindings consumers while preserving these protocols' value outcomes.
- First admission already forces the shared pair wrappers; asking for the head pair does not invent a second previously untouched pair.
- Full spine traversal does not force the separate name payload. The unadmitted poison-head control correctly demonstrates why spine traversal is not validation.
- Source-tail poison is reached by first admission in all three variants, before flattened append construction is demanded.

### Boundaries of that result

1. The model starts at inventory admission. It does not independently reproduce parameter checks or the complete inference stage; the previous admission-protocol model and unchanged source control flow address those separate obligations.
2. Closure values are immutable symbolic states, not XTypes or actual `freeVars` evaluation. The model cannot validate the partial-host type construction or real type-field strictness.
3. `append` explicitly forces its right operand when an empty left chunk is demanded, matching the pinned lazy append's WHNF behavior. Its events describe this specified thunk protocol, not instruction counts or allocations.
4. Python `Thunk` objects keep `compute` and event references even after becoming ready, and `walk` uses a loop rather than Haskell recursion. Their retention, stack use, exception caching, and object layouts are not a simulation of a GHC/runtime heap.
5. Fixed observation sequences and memoized event equality are not proof of arbitrary-context Haskell equivalence. Instrumentation and compiler optimization can change actual traces. Infinite-list nontermination is source reasoning here, not an attempted model run.

Exact independently reviewed/run hashes:

- `lazy_spine_model.py`: `ea732ed48b4a899434cf1d44caf589abec34e823c7a091f8f2280158dd2f22b8`
- `test_lazy_spine_model.py`: `02cf238d93a47e9e33735151ba2f45691a77fe1c9a1ad6e013be0b53b17660a4`

**Final status:** the source patch and model support a precise spine-only experimental alternative on the unchanged finite admitted-inventory domain. They do not establish Haskell compilation, exact runtime demand/heap equivalence, or a compiler speedup. Both patch alternatives remain unapplied.
