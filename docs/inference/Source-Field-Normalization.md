# Source-owned field normalization

## Scope and boundary

Fresh source datatype declarations use one canonical field layout for inference,
emitted xMLF declarations, source-query keys and saved crate metadata. The
canonicalizer recursively removes a `Quantified` field binder only when its name
is not free in the already-normalized body. It preserves live quantifiers,
lexical shadowing, datatype parameters and kinds, constructor identity/order,
field order and runtime arity.

Original declarations are validated before any syntax is removed. Invalid kinds,
unknown constructors or unbound variables therefore cannot disappear through
normalization. Checked imported declarations participate in that validation but
are never rewritten. Generic target checking, target equality, imported object
parsing and `CompilerCore.finishCompilation` remain unchanged.

The source-only entry points are:

- direct/legacy/linked source compilation, before class lowering;
- a crate's own resolved declarations, before combining them with checked
  imports and before creating its `SourcePlan` or query inventory;
- the freshly compiled builtin source crate.

This is a source declaration normalization, not a new xMLF arrow-congruence rule
or a cast inserted around constructor values. The canonical declaration is used
consistently by constructor-as-value, partial application, construction and
pattern elimination. No eta expansion or computational wrapper is introduced.

## Validation checkpoint

The first datatype-only candidate was built cleanly at GHC O2. Its producer
receipt SHA256 is
`d9f00320ab07575ccf488d762fefa8cf2004cee8b0847129970a2cd5e4c45c37`.
The focused `--recursive-inference` mode passed in 148.55 seconds with all three
expected completion banners and empty stderr. This includes both target
checkers, serialized target roundtrips, erasure comparisons, 15 added source
positives, five added source negatives, and pure normalization/idempotence tests.
This is an intermediate implementation checkpoint, not a claim that later edits
have the same validation identity.

## Explicit boundaries

The live field `forall a. a` is not a dead quantifier. The existing bare-constructor
case `data Abs = Abs (forall a. a); Abs` remains a named rejection control for a
separate graph/constructor normalization mismatch.

The initial datatype-only transformation did not fix freshly generated class dictionaries.
Both a leading unused method quantifier and an unused quantifier in a method's
arrow result have independently reproduced the analogous mismatch. Their repair
requires canonicalizing only freshly owned source class headers after original method
and superclass validation, consistently before selector/dictionary generation
and saved metadata. Imported class headers and dictionary ABI reconstruction must
remain untouched. The source-class follow-on below implements that boundary.

Opening known polymorphism supplied through an ordinary datatype parameter is a
separate graph scheduling/evidence change. It must distinguish an exact rigid
interface from a flexible unknown with a polymorphic-looking lower bound, and
must not infer polymorphic recursion or retroactively import a later application's
argument information into an earlier unannotated lambda body.

## Source class headers

The follow-on canonicalizer validates the original class declarations using the
existing declaration/implicit-variable rules, method and superclass kind checks,
method Field admissibility, superclass Field conversion and superclass-cycle
checks. Only then does it normalize freshly owned headers. It never rewrites
`dictionaryDecl` or checked imported headers. Fresh selectors, instances,
dictionaries and exported metadata therefore all see the same source signature.

SType liveness includes qualified predicate arguments and retained dependent
bounds. A forall binds its name in the body, not in its own bound. Only unused
flexible bottom-bounded quantifiers are removed; unsupported rigid, bounded or
qualified method syntax is still rejected by the original validation first.

A development-only object overlay passed both original class failures and the
ordinary control, then the frontend-repair suite with eight class positives,
eight rejection controls and pure scope/provenance checks. Its complete run took
80.15 seconds. A ninth nominal-result positive is included in the subsequent
clean combined candidate, whose execution is not implied by the earlier result.

## Known parameter-field projection

Ordinary datatype parameters remain shared unknown types unless the case
scrutinee's completed instantiation has already established an exact rigid
polymorphic interface. Raw graph classification excludes flexible unknowns and
rigid abstract skolems. It admits exact rigid bottom separately, and otherwise
requires a reachable, non-inert flexible quantifier bound directly at the field
root. Quantifiers only below an arrow domain do not make that root a leading
polymorphic interface.

The constraint work stream represents instantiation and case projection as
distinct typed actions. All alternatives' field proxies/descriptors are prepared
before any alternative body is generated. One projection action follows the
scrutinee edge and classifies every descriptor against the same incoming graph.
This ordering is necessary because an unsigned recursive group in the first
alternative may flush pending constraints before later alternatives are visited.
Both that flush and final solving use the same ordered evaluator.

An eligible field copies only its own scope region into its preallocated local
scheme owner. The original root, captured outer variables and skolem identities
remain unchanged. Structural/binding indexes are updated, and the completed case
is audited without normalizing the active graph. Elaborated evidence must start
at the exact substituted pattern-field type; the new parameter path permits only
alpha-equal interface adaptation before the ordinary checked instantiation. No
target rule, abstract-bound opening, value wrapper or eta expansion is added.

The decision is one-shot. Information supplied by a later application argument
does not retrospectively reopen an unknown lambda parameter's earlier case.
Checked declaration types also propagate through an ordinary let's continuation:
its bound expression is still inferred/generalized normally, while the same
expected type reaches the body. This repairs the independently reproduced
transparent-let higher-rank false negative without crossing expression coercions,
recursive-let groups, applications or cases. Explicit lambda annotations remain
authoritative. This is not a general bidirectional propagation algorithm through
arbitrary expression wrappers, nor a claim that other inference algorithms must
have the same remaining boundaries.

## Imported contracts and independent coverage

The first saved-crate fixture passed 44 authored checks against the datatype-only
producer: source and fallback query routes, cold/warm caches, saved metadata-only
consumers, production/frozen target checking, serialization/erasure, and
bidirectional well-typed forged-layout rejection. Fresh canonical producer and
consumer linked and evaluated to 42. Exact manually checked legacy quantified
datatype/class layouts survived import and no-entry library linking unchanged.

The unchanged imported-entry re-elaboration path can still drop a vacuous
quantifier from a legacy selector scheme and reject the exact ABI comparison.
That attempted entry link remains an explicit rejection control; it is not
reported as repaired. The final fixture includes an ordinary imported-selector
entry positive as a paired compatibility control. Neither target equality nor cache,
object or linker validation is weakened to accommodate legacy mismatches.

The first combined candidate compiled cleanly, passed the authenticated 45-case
saved-crate gate and 18 authored graph controls, and accepted the known-interface
CLI probes. Its full focused mode stopped on a provisional negative diagnostic
string: a captured skolem correctly failed with an explicit type-constructor
mismatch instead of the predicted protected-variable wording. The captured and
abstract skolem controls were pinned to the observed skolem mismatch category;
they still require inference rejection. The transparent-let and complete
parameter-field focused development probe subsequently passed. These intermediate
results are superseded for final-source identity by the clean producer below.

## Final-source local verification

The clean GHC 9.14.1 O2 producer includes the datatype, class, parameter projection
and transparent-let changes together: 108 shared modules, 31 host inputs and 19
configuration inputs. Its receipt SHA256 is
`d9fc1579cf65a8558cc06908acffc3d70dc692e863ba8af7f93c8f5c4a04adaa`;
the compiler executable SHA256 is
`321b42f92a3303a392c602333d329a2dd90ddbfb528b6d9aaffe0033954d1071`.

- The strict direct wrapper passed all 12 commands. Frontend mode passed all
  four exact completion banners in 216.24 seconds; native-first/native-second
  host checks took 114.68/101.49 seconds. Every command retained exact stdout,
  empty stderr and expected status. Accepted compilation cases check production
  and frozen targets, serialization and erasure; rejected controls remain
  rejection controls.
- The authenticated graph runner passed all 18 authored copy/frontier/index,
  classifier and malformed-input checks. Receipt SHA256:
  `8ba418617350424caee6b865be19eafca9fd7376cb8848dffe9cfd9075009c20`.
- The saved-layout runner passed 55 ordered checks: the original 45 plus ten
  fresh source-class method/header/cache/consumer checks. Both leading and nested
  method quantifiers normalize before source inventory; a metadata-only saved
  consumer links, checks and evaluates both methods to 42. Receipt SHA256:
  `f59614c9b763c88af228e2bc14b5d862a1fbb490f8b3c49c2c96adc80517b48b`.
- Independent review reran all 55 layout checks with a fresh cache and ran 17
  additional CLI accept/reject probes, authenticating sources and held artifacts
  before and after. The CLI probes use production validation, not an additional
  frozen-checker run.
- The faithful Figure12 gate passed its unchanged 43 labels/41 distinct
  expressions, 29 assumption controls, four principal-type assertions and three
  annotation repairs. Receipt SHA256:
  `bfa29a4784b97dcb8d61704c01f3a393ecb962508a79862cd8b2229fc9391173`.
- Existing recursive/managed-evidence compatibility passed 17 raw, six parsed
  and one source-contract control, including cold/warm query parity and
  independent target/roundtrip/erasure checks. Receipt SHA256:
  `6981e0d40876a25b8eb6bc8c67724f9aa07f51485bd08fcb4a219a18bb272de4`.
- Release metadata, fixed-inventory adversarial controls and manifest snapshot
  checks passed. The new two host fixtures are durable O2 CI steps; they do not
  enable bootstrap or full native qualification.

The existing TupleList default/framework compatibility gate is still running at
this documentation checkpoint. Hosted O0 execution and
exact published-head CI remain required; the prior green CI164 belongs to the
immutable pre-residual checkpoint, not these new compiler bytes.

The durable additions can be reproduced from a completed authenticated O2 build:

```sh
python3 tools/shared/test_parameter_field_graph.py --build-receipt BUILD/receipt.json --output FRESH-GRAPH-DIR
python3 tools/shared/test_source_field_layouts.py --build-receipt BUILD/receipt.json --output FRESH-LAYOUT-DIR
```

Both compile only a small host fixture and authenticated transports, reuse the
held shared compiler objects, require the exact authored completion inventory,
and reauthenticate before and after. Their cheap adversarial controls run in
the normal release-metadata gate.

A sequential O2 comparison of the same 466-byte Applicative Box workload took
17.216 seconds on the datatype-only candidate and 19.126 seconds on the first
combined candidate (11.1% additional wall time). Both produced identical checked
output and 42 with empty stderr. This includes compilation, target checking,
serialization roundtrip and host interpretation; it is one workload, not an O0
full-suite bound or a generated-program performance claim.

The legacy actual-import graph test route was also attempted. A tiny existing-API
Helpers.eq control reproduces the same pre-test failure on immutable 4af89535 and
the combined tree: default implicit Prelude conflicts with Helpers' custom Eq;
--no-prelude instead leaves its existing == references unresolved. The Helpers
source is byte-identical. Those attempts did not execute graph tests and are not
counted as passes. The durable authenticated host graph fixture executes the
authored copy/frontier/index/malformed-input checks against the actual shared
Graph/Solver/Constraint objects, separately from that legacy import limitation.

## CI166 execution-budget finding

The published residual head `9c4937c5531f9536260a3a72c76736016bc97265`
passed the complete hosted O2 job, including all eight authenticated receipt
routes and the new 18/55-check fixtures. Its O0 default shard also passed all
305 observations in 2293.36 seconds, and its O0 framework shard passed all 105
cases and associated controls in 3240.79 seconds. Their official artifacts match
the exact published source tree and linked receipts. CI166 was allowed to finish
without cancellation. The O0 direct shard did **not** pass:
`--frontend` reached 2400.017 seconds, emitted only the qualified-recursion
completion banner, and was terminated with empty stderr and complete owned
process cleanup. Later direct modes and Figure12 did not execute in that shard.
The banner proves the prefix completed; it does not identify a particular
unfinished repair subgroup or demonstrate an assertion failure.

Between CI164's source and this residual source, literal recursive compilation
helper calls in `SharedFrontend.hs` increased from 90 to 163: 74 added calls and
one old Box rejection replaced by an acceptance case. This excludes other
parser/pure assertions, and differently priced calls do not establish a runtime
model. Applying that ratio to the earlier 1528-second frontend result yields
2768 seconds only as a rough workload-size comparison, not a predicted duration.

The narrow correction raises only the authenticated O0 frontend default/maximum
to 3600 seconds. O0 native modes stay at 1200 each; O2 limits, default/framework
limits, every assertion and full-mode ordering remain unchanged. CI166 setup,
producer and smoke took about 820 seconds. Combining the new frontend allowance
with earlier measured native modes and Figure12 gives approximately 99 minutes;
allowing normal overhead gives a provisional 99–102-minute planning estimate.
Using both native ceilings instead gives about 114 minutes before small helpers
and upload. The unchanged 120-minute job deadline remains an independent hard
failure bound, not a promise that every command's maximum can fit simultaneously.

Real CLI dispatch controls verify authenticated optimization selection, the
3600 ceiling, rejected larger overrides, unchanged O2/native limits and strict
output/status/stderr/cleanup behavior. The failed 2400-second attempt remains
failed. Only a subsequent completed exact-head run can establish O0 success;
the policy adjustment itself is not a pass or a compiler-performance claim.

## CI167 unchanged-binary O2 margin finding

CI167's O2 frontend passed all four exact banners in 242.88 seconds, but the
next `native-first` command exhausted its unchanged 120-second cap (120.11s).
Both output streams were empty, owned-process cleanup completed, and subsequent
O2 gates did not run. The failed attempt remains failed. Its producer records
exactly the same 108 shared, 31 host and 19 configuration inputs, 226 object/
interface entries, 12 executable identities and 44 flags as CI166's passing O2
producer. That run completed native-first in 102.15s; the final local run took
114.68s. These digest comparisons use official receipts, not locally downloaded
hosted binaries.

The preceding identical frontend took 194.97s in CI166 versus 242.88s in CI167,
a 24.58% difference. This supports allowing run-to-run execution margin but does
not identify a CPU/load cause or prove a compiler-wide performance regression.
Native-first contains six independent closed compile/evaluate checks with fresh
runtime preparation; no test depends on clocks, randomness or shared files.

The smallest correction changes only authenticated O2 native-first to a finite
180-second limit. O2 native-second remains 120; O0 remains 3600/1200/1200, and
frontend override bounds, all other suite budgets and the 120-minute job ceiling
are unchanged. Real dispatch and negative controls require that exact policy;
every test, completion banner, stderr/status assertion and cleanup rule is
unchanged. CI167's O0 jobs are allowed to finish before publishing this correction.
If the new native-first bound is also exhausted, per-case progress/cost diagnosis
is required before considering another policy change.
