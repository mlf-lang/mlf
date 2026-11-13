# Graph.unify: measured boundary, unresolved interior

Source pin: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
All Graph line references below are to
`libraries/mlf-inference/Bootstrap/Graph.hs` at this pin. This is static review;
the new four-interval mirror has not been executed. No optimization is proposed
for immediate application before those intervals are measured.

## Evidence that justifies this measurement

The completed r16 raw-derived fine report has 61,004,563,264 total bytes and
35,598,383,104 SOLVE bytes. Its SOLVE / LOCAL_UNIFY cell is 16,834,404,240 bytes:
47.289800% of SOLVE, 27.595320% of the total. The fine-report SHA256 is
`2dac87e2e40424f4833aa04157c988c27cdf154bdc9e7903ab615deaa333092a`.
These numbers were read back from that report; its genuine execution and byte
control were established by the separate r16 stage chain. They do not distinguish
input validation, first-order work, rebinding or output validation inside the
cell, and do not measure ordinary exclusive CPU.

## Four existing operations and information lifetime

1. **Input validation, 780–1029.** `validateGraph` chooses dense or sparse by
   `denseBounds` (755–770). Dense validation creates node/descendant tables,
   colours, kinds, binding start/end intervals and structural-visit marks in one
   `runST` (797–829). It loads the nodes, checks root/binder conditions, traverses
   binding intervals, then validates kinds and every structural edge
   (903–1020, 2803–2858). Its kind/interval tables do not escape. Sparse validation
   computes `kindsAt graph (IM.keys (nodes graph))`, then `bindingIntervals`, node
   binders and edges (1022–1029), but returns `()` and discards both maps.
2. **First order, 1247–1254.** This is already specialized. Alias-free inputs with
   `simpleKinds` use full endpoint admission before `firstOrderValidated`, whose
   kind lookup uses validated tag premises (1153–1188, 1202–1242). The simple-tree
   predicate also checks routing edges, not merely the absence of `GTyApp`
   (1189–1201). Other inputs compute a fresh `kindsAt` over all equation endpoints,
   then use its shared cache during merging (383–462, 1093–1137). It is therefore
   false that every call blindly rebuilds the all-node kind map. Whether the
   fallback accounts for significant measured allocation is still unknown.
3. **Canonicalize and rebind, 1138–1144 and 1473–2106.** Canonicalization rewrites
   structural children through the new aliases and strictly rebuilds nodes.
   Rebinding uses the old graph for permission checks and the merged skeleton
   for classes, parents, grafted nodes and new binders. Dense rebinding creates
   twelve scratch tables, loads old/new nodes and classes, places binding nodes,
   computes raised binders and checks old/raised permissions and merge legality
   (1507–1629). Sparse rebinding constructs analogous persistent indexes
   (2040–2106). Neither is just a repeat of input binding-interval validation.
4. **Output validation, 1262.** The graph now has changed aliases, tags, node set,
   binders and possibly flags. Calling the same validator is not validating the
   same immutable value twice. The final check cannot be removed solely because
   the input succeeded or an internal solver caller usually supplies valid data.

`Graph`, `Node`, `Solver` and their maps have public constructors
(`Bootstrap.Types:322–326`); `Bootstrap.Graph` exports all definitions. Existing
map/tree routing guards must not be replaced with an assumption of opaque
receipts or well-formed producer-only inputs. `Graph.Solver` transactions call
`G.unify` on projected graphs at 1050–1061 and 2146–2147, but the public API also
accepts arbitrary host-constructed graphs. Preserve both domains.

## Concrete repetition, but not yet a safe or valuable cache patch

- The sparse input kind map is indeed discarded before the fallback endpoint
  kind map may be computed. Reusing it would still need the complete original
  endpoint checks, in their original order, including aliases and public
  malformed-map cases. A cache hit is not proof that a required endpoint was
  admitted in the new query. Error precedence and lazy kind payloads matter.
- Dense kind information is held in region-scoped arrays. Exporting an immutable
  snapshot adds a copy/retention obligation; fusing validation with first order
  and rebinding changes a much wider ST lifetime. `freezeSTArray` copies boxed
  cells without forcing contents (`host/ghc/MLF/Host/Base.hs:184–188`), so it is
  not a free transfer or a proof that all kind payloads are total.
- Input binding intervals describe the original binding tree. Rebinding derives
  a new tree after quotienting/grafting, and raised permissions concern a
  different binder view. Those are not interchangeable indexes. Existing
  `raisedDensePermissions` already shares the old permission view only after
  checking all relevant flexible binding edges for equality (1888–1912).
- On a successful route using dense input/output validation and dense rebinding,
  source structure contains 7 input-validation, 12 rebinding, 4 old-permission,
  0 or 4 additional raised-permission, and 7 output-validation `newSTArray`
  invocations. This is **30 or 34 source-level array constructions**, not measured
  objects, bytes, peak-live arrays or a cost attribution. The spans differ;
  early errors do not execute the entire route. Host arrays are boxed
  (`MLF.Host.Base:166–183`), despite comments referring to the seed's unboxed
  scratch integers. Do not infer allocation savings from the call count.
- `denseBounds before` is also recomputed for rebinding (781–785 versus
  1474–1478), on the same immutable input. Lexically sharing that query is a
  smaller possible follow-up than exporting a validation cache, but its cost
  is unmeasured and it is not a justified explanation for 16.8 GB.

No hash-based equivalence, dropped validation, altered inference or global
scratch/cache lifetime is warranted by the current evidence. First choose the
substage from real r17 allocation, then propose a narrowly bounded candidate.

## Error, demand and public-input constraints on any later candidate

`bindE` (109–115) evaluates the prior `Either` constructor before entering its
continuation. All four intervals preserve this order. In particular:

- Input rejection must precede touching a poisoned equation list.
- All equation endpoints are checked before any merge (1244–1254). On a valid
  graph with incompatible constructors at 1/2, equations `[(1,2),(99,1)]` must
  report the missing node 99 before the earlier constructor mismatch.
- Dense and sparse validators do not have the same first-error order. Dense
  checks binders before kinds; sparse computes kinds first. As a static example,
  give a root `GGen` an arrow child whose argument is a higher-kinded type
  constructor, and give that argument a missing binder. Compact IDs 0/1/2 select
  dense validation and the missing-binder check; well-spaced IDs 0/10/100 select
  sparse validation and the arrow-kind check. This is a host-constructible
  example, **not executed here**, not a claim about source-program reachability.
  Reordering or forcing the same global kind pass in both routes can change the
  public error result.
- Rebinding's protected/rigid-variable and merge checks are semantically
  distinct from graph-shape/kind checks. A known kind cache cannot replace them.
- Kind fields, constructor names, unused node payloads and equation tails can
  be partial host values. Do not claim equivalence for them solely from finite
  successful cases, or introduce `deepseq`/strict receipts to hide a difference.
- SCCs can affect optimization, thunk attribution and async-exception/resource
  behaviour. Token-only inversion is not operational equivalence or an
  asynchronous-exception timing guarantee. Retain the original semantic/demand
  controls and operational guard/cleanup tests when running this mirror.

Before applying a later optimization, use actual public `G.unify` comparisons
against the frozen function: dense/simple, sparse/signed/extreme IDs, aliases,
higher-kinded applications, empty/self equations, duplicate endpoints, late
missing endpoints versus early mismatches, rigid/protected rejection, invalid
binding/structural cycles and partial-host observation boundaries. Compare exact
errors and complete successful graph contents/aliases/fresh IDs, not hashes as
substitutes for structural equality. No such new fixture is claimed passed here.

## Measurement decision

The four new SCCs wrap only the existing argument expressions in `unify`; the
outer LOCAL_UNIFY remains. If validation dominates, study scratch construction
and the exact successful data that can be returned without moving an error or
demand. If first order dominates, distinguish its existing fast/fallback routes
before changing kind caching. If rebind dominates, investigate its indexes and
permission/scratch work, not the unrelated input cache. These are decision rules,
not predictions. No new protocol, build flags or large solver rewrite is needed.
