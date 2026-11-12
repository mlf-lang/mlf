# Checked open projection and closedness studies

These are **source-only experiments and small Python specification models**
for the MLF compiler. They do not modify compiler code, remove an independent
checker, establish Haskell compilation success, or demonstrate a speedup.
Source analysis is pinned to `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.

## Checked open projection fixture

`checked-open/CheckedOpenProjection.hs` is the r3 standalone fixture.
The previous r2 negative cases compared a baseline with an inventory
observation but did not check the complete safe adapter. A faulty extraction
could replace an invalid integer body with unit, while the original receipt's
inventory error masked the corruption. R3 asserts the full adapter's first
error on negative cases, including unchanged `Open.check` and ownership.

The exact-root inventory observation is still separate from the real Fragment.
The safe adapter continues to call `Open.check`. The 39 synthetic Haskell terms
plus 4 demand/raw controls are **uncompiled and unrun**. `CASE-MAP.json` preserves
the missing production, demand, and artifact qualification gates.

The separate Python model passed 15 tests, including 810 finite structural
cases. It demonstrates that test blind spot and checks extraction/cut/demand
properties in the model only, not real xMLF typing or Haskell strictness.

## Boolean closedness candidate

`closedness/ClosednessCandidate.hs.txt` asks whether the two consumers that
only need `null (freeVars type)` can avoid constructing a complete result set.
The finite-tree invariant is `closedIn scope ty == (freeVars ty subsetOf scope)`.
For `forall a bound body`, test `bound` in the old scope and `body` in scope
extended with `a`. The draft uses an immutable Set, not a linear binder list.
Kind validation and the independent checker must remain unchanged; a closed
type need not have kind `*` or be otherwise valid.

The Python model passed 12 tests and 7,104 type/scope comparisons in a bounded
grammar. These are not complete MLF types, a Haskell proof, or a benchmark.
The draft is **not a general Haskell drop-in replacement**: a short-circuiting
Boolean traversal with empty scope and defined `a` can return False on
`XArrow (XVar a) undefined`, whereas the original strict set construction must
inspect the undefined subtree. A bound Set can also introduce *more* demand:
an unused undefined outer binder ID may be forced by insertion/comparison even
when the original free-variable result deletes it from an empty set without
inspecting it. Real call-site demand/retention and profiling evidence are
required before adoption. A linear binder-list alternative can be quadratic
on deep closed types; even the Set version can lose to the baseline on sparse
variable-use families. Neither alternative is selected for production.

No production optimization is installed here. Operation counts in a symbolic
model are not allocated bytes, native timings, or end-to-end compiler gains.
Native generation A/B and fixed-point measurements remain outside this work.

## Follow-up: demand and adverse families

The follow-up static call-site review and `scope_cost_model.py` narrow the next
qualification questions. The new model distinguishes a lazy scope-extension
expression from a membership-forced Set construction. Sixty-four unused
binders need zero materialized scope inserts in that model, whereas one use of
the innermost binder forces the entire chain. A rejected linear-list variant
needs 4,096 equality comparisons for 64 uses of the outermost binder under 64
nested binders. These are modeled events, not measured compiler costs.
See `closedness/SCOPE-COST-NOTES.md` and `closedness/CALLSITE-REVIEW.md`.

## Narrow candidate: remove only the duplicate guard

`duplicate-guard/` contains an unapplied one-line patch, static review, and a
10-test pure admission-protocol model. It keeps all first inventory guards and
independent inference. In 6,342 bounded protocols, modeled results and all
non-repeated observation traces agree. Fault injection also demonstrates the
required producer invariant: removing or bypassing the first guards would make
the proposed removal unsafe. This is not a production edit or measured speedup.

A second unapplied patch preserves complete owned-list-spine demand before
returning Right, without rerunning the type predicate. Twelve additional pure
lazy-list tests cover 259 bounded chunk protocols and distinguish Either WHNF,
Fragment WHNF, shared pairs and lazy names. They do not establish actual
Haskell heap/stack behavior or a performance improvement.

## Prepared real-host qualification source, not execution results

`duplicate-guard/host-fixture/` now contains one public-API Haskell Main with
24 planned cases for future baseline/delete/spine builds. All 24 are uncompiled
and unrun. It includes exact error-priority controls, total-fragment encoded
observations and narrowly scoped partial-host probes, with unimplemented
heap/spine-timing/full-artifact coverage explicitly deferred.
The separate output comparison utility passed 16 synthetic-record tests; it
does not run Haskell or authenticate an execution just because records agree.

## Tiny model checks

Run each suite from its own directory with ordinary Python standard library:

```text
cd checked-open
python3 -B -m unittest -v test_projection_model

cd ../closedness
python3 -B -m unittest -v test_closedness_model
python3 -B -m unittest -v test_scope_cost_model

cd ../duplicate-guard
python3 -B -m unittest -v test_admission_model
python3 -B -m unittest -v test_lazy_spine_model

cd host-fixture
python3 -B -m unittest -v test_validate_host_outputs
```

No compiler invocation or CI workflow is added. `VERIFICATION.json` records
exact published source hashes and limited evidence. `SOURCE-PINS.json` records
the original repository files inspected, without machine-specific locations or
private recovery links. Further source-only experiments should retain the
independent baseline and distinguish modeled results from real compiler tests.

## Real host build boundary

`duplicate-guard/host-fixture/BUILD-FEASIBILITY.md` and `IMPORT-INVENTORY.json` record the pinned source import closure and ordinary-host requirements. The planned 24-case fixture imports 11 project modules directly and reaches 47 project modules (1,318,860 source bytes) in a static header scan, including C/FFI host support. This is not a base-only microprogram, a completed build, or a timing measurement. A separately admitted source-closure build could avoid the monolithic package component, but requires the real toolchain and host link dependencies; substituting stubs or copied model types would not test the same public APIs. No Haskell was compiled or run for this review.
