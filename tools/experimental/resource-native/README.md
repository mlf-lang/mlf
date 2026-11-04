# Additive IR8 experiment

The opt-in IR8 route now includes [static checks and metadata packets](resource_ir_v8/README_STAGE04.md)
and a [real C body emitter and experimental native runtime](resource_ir_v8/README_STAGE05.md).
The Stage05 guide gives reproducible host and native test commands.
[Stage12 directory-reader reuse](resource_ir_v8/README_STAGE12.md) removes one
same-call duplicate validation while preserving the remaining checked readers,
with portable O0/O2 reader regressions. [Stage15 auth-scan reuse](resource_ir_v8/README_STAGE15.md)
reuses that directory only within one authentication call while preserving every
preceding-row check. [Stage17 span/layout reuse](resource_ir_v8/README_STAGE17.md)
also reuses only call-local facts while keeping every row safety check. Each
stage documents its own finite same-program timing and limits. A separate
[controlled shared-source fragment experiment](source_v8/README.md) connects a
fresh ordinary compiler capture to independent replay, IR8 planning and the real
runtime for a bounded scalar/callable fragment, now extended with closed
single-constructor DATA and closed callable fields, plus
[bounded scalar-field SUMs](source_v8/README.md#stage10-closed-scalar-field-sums) and
[finite self-family SUM graphs](source_v8/README.md#stage11-finite-self-family-sum-graphs).
SUM cases check every arm but allocate only the selected arm's lazy factory.
[One closed monomorphic recursive function](resource_ir_v8/README_STAGE13.md)
can traverse such a family using the existing checked hole/fill and ordinary
Force machinery, with its original annotation applications preserved.
[Scalar and complete shared-view captures](resource_ir_v8/README_STAGE14.md)
retain their own Access/origin through that concrete recursive closure.
[Ordinary closed callable captures](resource_ir_v8/README_STAGE16.md) now retain
their complete scalar-arrow contracts and pending owners too, whether the actual
value becomes a concrete closure or a complete shared callable view.
The [source-only CLI](source_v8/README_CLI.md)
adds fresh bounded module snapshots and an explicit native fault policy; it
does not import diagnostic JSON. Its diagnostic capture is not a general
source-admission format. The full source bridge, comprehensive guard coverage,
general nominal support, GC replacement and performance remain unqualified.
The explicit [experimental `--data-groups` strategy](source_v8/README.md#stage09-opt-in-data-group-placement)
can retire eligible DATA containers earlier. Finite comparisons reduced peak
tracked bytes in two callable-field cases but increased them in a scalar case,
with extra allocation and reference-count work. This is a memory/overhead
tradeoff, not a speedup or GC-replacement claim; the default remains coarse.
This does not enable mixed-type shared-term execution in the
maintained v7 source route below or
change default behavior. Earlier integration records retain their historical
scope.

---

# Local current-PR25 integration (qualification recorded separately)

This source tree composes the exact PR25 target
`c5928b5be73cd78d194405e734aa012415570e1a` with the preserved PR28 history
`ae680d2e8698b2a99f1957114b76394a1d6b39f5` and the reconstructed Phase A
module/terminal-lifecycle implementation. It is a **local integration**, not a
published, merged, default-runtime or fully CI-qualified release.

The current maintained builder and both exporter routes now use the exact
`provenance/current-target-source.json` baseline and separately pinned
`current-compiler-inputs.json`, `current-transition.json` and source-loaded
`current-producer.py`. The two older provenance JSON files remain unchanged
historical evidence, not a fallback current producer. Export `source_commit`
identifies the ordinary dependency baseline; the fresh build receipt binds the
actual modified source, tools, compile logs, resolved modules and inferred types.
The target's generated builtin was genuinely regenerated from the combined
nongenerated source closure; no source-identity string was manually patched.

`validation/compiler-build.json` is generated and gitignored. A fresh checkout
must run the maintained `build_compiler.py` with the already available official
GHC9.14.1 and a fresh `--build-dir`; copying an old receipt is not a compiler.
Immutable tracked-source inventories exclude this generated file. Full ordinary
producer qualification uses `tools/shared/build.py --bootstrap-only` explicitly;
without that switch the upstream installer selects additional native-stdlib
requirements, which are not part of this local integration recipe.

The resource logical IR remains **v7**. Module export/2 and standalone export/6
retain their existing strict admission and original-check/proof custody. The
terminal policy remains diagnostic by default; only explicit `destroy-terminal`
requests physical retirement after terminal evaluation. It does not turn a
failed evaluation into success or claim ordinary rollback. Current integration
receipts distinguish those policies and the physical observer from model evidence.
Historical test counts below describe earlier source identities only. They are
not current-target passes. Current-target reference builds, finite source cases,
release-metadata controls and relocated public endpoints are qualified separately;
consult the exact external integration receipt. Imported Std remains UNKNOWN on
its historical producer; there is no new Std run, general shared-term polymorphic
runtime, complete GC replacement or measured speedup claim here.

---

# Earlier additive module route: exact multiple concrete family views

The module envelope is **`mlf-checked-module-export/2`**, with inventory policy
`normalized-concrete-family-views/1`. Resource IR v7, the audited field-sum native
runtime, and the standalone export/6 admission remain unchanged. This is bounded
module-only concrete data instantiation, not general MLF polymorphism or TypeViews.

Every runtime view is keyed by the actual full original declaration index, resolved
nominal identity, and ordered closed intrinsic Int/Bool argument vector. Multiple
views of one sum declaration are allowed; even phantom/nullary identical layouts
remain nominally distinct. Complete variants and all positional fields are retained.
Closure edges bind both source and target views, with bounded FIFO discovery and
canonical declaration-index/Int-before-Bool vector order for final family IDs.
Limits:64 total sum views,8 Star formals,64 variants,32 fields per variant. Sum fields
remain Int/Bool/registered sum; parameterized records, arrows and new runtime kinds
are not admitted. Existing monomorphic record/Unit lowering stays separate.

Case witnesses use the ordinary scoped checker on the actual scrutinee, then the
transport independently reconstructs exact logical types from normalized syntax;
supplied case rows are never inference premises. Wildcard fields retain their full
types. Full original module checking and declaration evidence precede unchanged
whole-spine projection and type-only proof normalization. The term-binder rule is
still **one closed vector for every use of a shared generalized let**, preserving
its RHS, ID, applications, lazy memo and ownership graph. No cloning or inlining.

The preregistered finite stage has three normal42 cases, one demanded-field BUSY
terminal, one ordinary unused-type-error rejection and one retained mixed TERM-use
rejection. Five new original cases plus one exact prior original42 adoption precede
six candidate calls. An infrastructure-interrupted original attempt remains UNKNOWN;
one explicitly authorized replacement is separately counted, not erased. Consult
fresh stage receipts for qualification; implementation notes are not a pass claim.
No full Std import, full GC replacement, allocation reduction or measured speedup
is claimed. Source restoration uses the actual `source-baseline/` extraction root.

---

## Prior accepted module route (export/1)

# Current additive route: checked real modules and lazy outer-spine projection

The standalone export/6 route below remains separate. The opt-in module route uses
`mlf-checked-module-export/1`, unchanged resource IR v7 and the same field-sum C
runtime. Invoke `run_native.py --module-root DIR --no-prelude --coarse --owned
DIR/Main.emlf` with a headerless root and named legacy `.emlf` imports. This is a
bounded small-module route, **not full Std import support**: the original Std.min
observation remained UNKNOWN at its explicit CPU limit.

One real loader/resolver captures exact source bytes, complete loaded syntax,
entity namespace/owner allocations and actual checked binder associations. Full
ordinary inference and checking precede any projection, including unused values
and declarations. Only the contiguous outer let/whole-letrec spine is projected;
retained bindings, RHSs, IDs, order and lazy shared memo graph stay unchanged.
Projected terms are ordinarily rechecked, with root type equality and a separately
replayed erased projection (not a false original/projected erasure equality).
Then checked type-only normalization precedes a complete normalized executable
layout census. Whole unused families may remain evidence-only; selected families
retain every variant and positional field, including wildcard fields. The Python
transport independently replays these witnesses and fails closed on unsupported
syntax, lowering, identity, proof or representation; no fallback route is used.

The cooperative source snapshot bounds the **entire** `.emlf` inventory, including
unimported files: 32 files, 1 MiB/file, 8 MiB total. Symlinks, escaping canonical
paths, special files and `.hs` ambiguity reject. This is reproducibility custody,
not a hostile-filesystem sandbox. Actual compiler calls have explicit 180 CPU /
240 wall seconds and 1.5 GiB bounds; timeout means UNKNOWN, not type rejection.

The finite author plan has seven cases: shared42, private capture, two distinct
same-spelling nominal families (all return42), demanded typed knot (BUSY, retained
terminal heap), ordinary unused type error, retained String and retained mixed
instances (pre-target rejection). The initial shared42 public call failed at a
conservative metadata replay bug; its preserved completed export was used in one
explicitly approved, separately labelled continuation, never relabelled as a fresh
CLI. A fresh restored public endpoint is separately required. Consult exact final
stage receipts for completed status; these notes alone grant no acceptance.

No semantic optimization, general module/library coverage, tracing-GC replacement,
measured speedup or new mode qualification is claimed. Portable reconstruction
uses the actual durable `source-baseline/` root. Legacy producer source-commit
anchors are historical dependency provenance, not the modified compiler identity.

---

## Prior standalone route (export/6)

# Current frontend: one checked closed instance per shared binding

**Export/6; unchanged resource IR v7 and field-sum C runtime.** This additive
experimental route admits a bounded generic closed-use mechanism, initially with
intrinsic Int/Bool type arguments. It does not implement general MLF polymorphism.
The exact standalone production `Maybe` declaration and `Std.maybe` signature/body
are retained; `fixtures/closed-instance/std-maybe-int.emlf` returns Int42. This is
not an imported-module or full-library claim.

Presence of a parameterized user sum deterministically selects
`single-closed-instance/1`; failed proof/occurrence/template admission never falls
back to an erased or historical route. The producer checks original and transformed
terms with the ordinary checker, requires root type alpha-equality and exact
erasure equality, and retains complete generic declarations plus an unchanged
term/binding/use skeleton. Transport independently replays every substitution,
complete lexical occurrence table and nominal instance projection.

A nonrecursive generalized let is specialized **once, in place**, only when ALL
uses fully instantiate its leading bottom-Star forall prefix to one identical
closed Int/Bool vector. The existing let, RHS, variable IDs, applications, coercion
lambdas and lazy shared memo graph remain. No inlining, cloning, term beta-reduction,
DCE, extra Force or optimization occurs. Mixed/open/bare/escaping uses, unresolved
aliases, recursive polymorphism, unknown proof forms, unsupported bounds and
unused unresolved generic bindings fail closed. Standard elimination recognizes
only explicit Then/Refl compositions of Inner(Bottom target)/Elim pairs; original
proof association is preserved. Limits:64 generalized lets,8 prefix binders,
256 occurrences per binder,64 proof atoms per enclosing proof tree.

Complete generic DataEnv templates retain declaration identity/order, formal kinds
and every variant/positional field. A separate complete instance view records one
exact closed vector PER DECLARATION, not merely per term binder. Thus Maybe[Int]
and Maybe[Bool] in the same program reject even through distinct monomorphic lets.
Unused unresolved parameterized declarations reject. Finite regular same-instance
recursion is allowed; expanding/mixed/open closure rejects. Instantiated fields
still admit only Int, Bool or registered concrete sums (32 fields/variant), never
Unit/record/arrow/existential widening. Cases remain exhaustive and Int-result;
selected-field factories and all ownership/HOLE/OOM rules remain exactly v7.

The finite original-first source plan is7 normal,2 demanded-bottom terminal and6
prebuild rejection cases, plus separate proof/schema controls. Consult the fresh
stage source acceptance and raw receipts for completed qualification, rather than
historical sections below. Retained BUSY allocations are not cleanup; separate
model ownership ledgers are not native per-owner telemetry. No full GC replacement,
measured speedup, general modules/DCE, Text/IO/ST or broad-mode qualification follows.

The additive artifact recipe uses the actual base extraction root
`source-baseline/` (directory containing `upstream/`, `CLOSURE.json`, and
`source-git-objects.tar.gz`) and a new output directory. Legacy producer
`source_commit=7bf7ac6…` denotes the historical ordinary-dependency anchor, not a
commit identity for this modified exporter; the actual compiler input/binary hashes
and restored upstream ae680d2e… are recorded separately.

---

## Historical field-stage documentation (export/5)

The sections below describe prior qualified stages. Where a version/admission
boundary differs, the current export/6 contract above is authoritative for this
working source; prior snapshot bytes and receipts remain unchanged.

# Recursive field sums: current experimental stage (2026-11-02)

This additive candidate uses **export/5 and IR v7**, with the exact independently
reviewed `resource-ir-field-sum/1` contract. Complete validated `DataEnv` families,
constructor order, every positional field type, and both original and normalized
raw declarations are retained and reconciled. No unused variant or wildcard field
is pruned. The new sum-field grammar is closed intrinsic **Int, Bool or a registered
parameterless nominal sum** only: at most 32 fields per variant. Unit, record,
function, parameterized or existential fields are not admitted. Existing separate
record lowering and the conservative builtin-shadow identity guard remain.

`construct_sum` publishes one owning slot per declared field position without
forcing a field. Filled indirections and cycles retain their actual nodes. A demanded
exhaustive Int-result case forces its nominal scrutinee once. The checked
`case_fields_i64` factory validates every callback/capture descriptor and all external
owners, authenticates the complete selected payload (including wildcard slots), and
rejects raw HOLE payload slots before projection or allocation. This is a raw-HOLE
construction barrier, **not evaluation of ignored fields**. Filled indirect/BUSY
nodes and cycles remain lazy. Only selected field bindings are retained, in
independent temporary owners; the parent stays owned while one selected whole-AST
branch thunk acquires its owning capture slots. Temporary field owners are released
before factory success, then ordinary outer Force demands the returned lazy thunk.
Unselected branch ASTs remain ordinarily checked and compiled but are not allocated
or executed by that invocation. Callback limits are 32 field bindings plus 32 external
bindings (64 total), in addition to the emitter's existing pointer budget.

This allocating factory is **not** the old nullary case's zero-allocation selected-
owner transfer. Allocation failure is terminal poisoned state; retained anchors or
partial allocations are not described as rollback or successful cleanup. Native
raw events, exact checked emitter/runtime identity, and separately labeled captured-
model ownership observations provide bounded evidence, not invented native telemetry.

The first genuine fixture is an explicit-case standalone restatement of the actual
`Bootstrap.Types.Kind` declaration and `Bootstrap.Kind.kindArity` body:
`data Kind = Star | KArrow Kind Kind;` with the right-spine arity recursion. It is
not a claim of importing or compiling the whole production module. The registered
source gate has 6 normal cases, 2 direct typed-self-thunk terminal controls, and 7
unsupported/ordinary-check rejection controls. The normal corpus includes ignored
left typed bottom, a real structural left cycle, exact right-field order, and aliased
payload fields. Productive unbounded right-spine recursion is not mislabeled BUSY
and is not probed here. Actual originals run before candidate calls. Fresh source
acceptance is pending until completed raw evidence and a separate independent receipt.

For reconstruction the durable base archive extracts under **`source-baseline/`**.
Pass the directory containing `upstream/`, `CLOSURE.json` and
`source-git-objects.tar.gz` as `--base-stage`; all output directories must be new.
No general polymorphism, default patterns, module/DCE layer, Text/IO/ST, complete
GC replacement or performance improvement is claimed.

---

# Historical nominal nullary sums stage (export/4, IR v6)

This candidate stage uses **export/4 and IR v6**. `representation.custom_sums`
is projected from the complete actual checked `DataEnv`, independently reconciled
against both retained original and normalized raw declaration inventories. Nominal
family shape `%F` is distinct from a variant descriptor and from intrinsic Bool.
The IR pins finite family tables and declaration-order variant IDs; there is no
hardcoded `Flag` spelling or two-constructor limit in the core. The source sum
boundary admits closed, parameterless, zero-field multi-constructor declarations;
existing single-constructor records retain their representation and lowering.
Admission is deliberately narrower for internal builtin constructor shadows:
this version rejects names such as `MLFStackFrame` even where the ordinary
DataEnv map could shadow a builtin. This new conservative identity guard is not
a change to the ordinary checker, nor a claim of exact old record admission.

Exhaustive constructor-only sum case currently requires **Int** result. No default
patterns, fields/parameters on sums, foreign or omitted constructor arms, or Bool
case/result shortcut is admitted. The original compiler checks complete declarations
and every branch before export. On demand the case thunk forces its scrutinee once,
creates whole-AST lazy alternative thunks in validated declaration order, then
transfers the selected exact owner and drops the others without forcing them.
Outer normal Force demands and memoizes the chosen cursor. No physical group fact
is invented for the selected result. All core/source identities and acceptance
receipts must be refreshed for this stage; previous conditional receipts do not
admit the new implementation automatically.

The first genuine fixture uses the exact `Bootstrap.Types` declaration
`data Flag = Flexible | Rigid;`, not a fabricated builtin or a module import.
Original reference returned20 and the previous exporter correctly rejected sums.
The current preregistered source gate comprises five normal cases, two terminal
BUSY controls and six pre-build rejections; source acceptance is pending until its
actual completed raw evidence and fresh independent receipt are available.
No field-bearing recursive sums, module/DCE layer, general polymorphic case,
Text/IO/ST, full GC replacement or performance improvement is claimed.

For additive checkpoint reconstruction the durable base archive extracts under
**`source-baseline/`**: pass the directory containing `upstream/`, `CLOSURE.json`
and `source-git-objects.tar.gz` as `--base-stage`. Do not guess a workspace-directory
name from a historical command. New output directories only; frozen stages remain
unchanged.

---

## Historical checked Int conditional stage (export/3, IR v5)

# Checked-source intrinsic-Int conditional stage — experimental

## Current stage: export/3 and resource IR v5

This additive stage is based on restored PR28
`ae680d2e8698b2a99f1957114b76394a1d6b39f5` plus the separately identified scalar
checkpoint. Its current transport is **`mlf-checked-recursion-export/3`** and its
resource IR is **version 5**. The export/2, IR-v4 and overflow-only descriptions
below are retained as historical scalar-stage documentation, not the current
format or an acceptance claim for these new bytes.

The new source admission is the actual checked `PIfThenElse` primitive, code
**13**, directly saturated with **three term operands** and exactly **one checked
intrinsic `Int` type argument**. A source spelling or erased application shape
cannot authorize it. The condition is Bool; both alternatives and the result
must have the admitted closed intrinsic Int representation. Partial/first-class
conditionals and Bool-result conditionals remain outside this stage.

### Checked evidence, not erase-and-guess

The original supplied term first undergoes the full unchanged ordinary
`K.check`; its fresh root type must be alpha-equivalent to the supplied checked
type. When a conditional is present, the exporter applies only the bounded
`closed-int-standard-instantiation/1` syntactic normalizer:

- Reflexivity type-application wrappers may be removed.
- A syntactic type abstraction with a bottom-Star binder bound may be instantiated
  at closed intrinsic Int only through the standard
  `XThen (XInner (XBottom Int)) XElim` witness shape.
- Unsupported proof/type-application forms or unresolved/non-Int conditional
  instantiations reject. This is not general proof normalization, term
  beta-reduction, unconstrained specialization, branch pruning or runtime-shape inference.

The transformed term undergoes ordinary **`K.check` again**. Original and
transformed root types must satisfy **`alphaEq`**, and their complete ordinary
source erasures must satisfy **exact `X.equalErased` equality**. The transport
retains the original checked type/term view, raw original and normalized
annotations, original erasure and each exact normalization/proof witness. These
are retained evidence, not fabricated checked constructors or an erase-and-guess
substitute for checking. Ordinary parser/inference/checker/erasure implementations
are unchanged.

Both conditional alternatives remain present, are checked and planned, and stay
lazy as whole alternatives. Demand evaluates the condition and selects one
alternative; it does not evaluate the unselected branch. An unsupported or
ill-typed dead branch is not silently discarded to make a program acceptable.

### Current bounded observations and reproduction

The first genuine source fixture uses the maintained `Bootstrap.Std.min` body
`if (a < b) then a else b` in a concrete standalone `Int -> Int -> Int` binding:
`min 20 22` returns Int64 **20**. It is not a claim of named-module/import support.
The separate finite risk set records **7 normal values, 2 terminal BUSY outcomes
and 4 rejection controls** (including one original type-check rejection).
Author evidence and independent source/proof/trace reviews are retained; the
**final independent source-stage acceptance receipt is pending**. These bounded
observations do not replace that receipt. BUSY is a terminal machine outcome,
not successful cleanup or exact equality with the original host's diagnostic.

With an existing official GHC 9.14.1, GCC, Python and binutils, set TMPDIR to a
workspace directory and use fresh build/output directories:

```sh
python3 -B tools/experimental/resource-native/build_compiler.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc \
  --build-dir /absolute/path/to/a-new-empty-build-directory
python3 -B tools/experimental/resource-native/run_native.py \
  --no-prelude --no-model --coarse --owned \
  --build-parent /absolute/path/to/a-new-native-output-directory \
  tools/experimental/resource-native/fixtures/int-conditional/std-min.emlf
```

The native profile requires the documented 8192 KiB soft stack limit. Omitting
`--no-model` separately executes the Python reference and checks complete common
ordered observations; the public no-model path still requires the real source
compiler, checked evidence, resource checker and fresh native C build.

No general normalization, Bool-result conditional, sum/default-pattern,
named-module/import graph, Text, IO/FFI or ST support is added. There is no
performance, universal leak-freedom, full-language or whole-GC-replacement claim.
Historical scalar/core receipts do not qualify changed implementation bytes.

---

## Historical scalar-only checkpoint — export/2 and resource IR v4

Everything below records the preceding scalar-only checkpoint, including its
format identifiers, counts and one-overflow-fixture acceptance boundary. Consult
the current-stage section above for this candidate's changed contract.

This is a NEW bounded implementation based on restored PR28
`ae680d2e8698b2a99f1957114b76394a1d6b39f5`. It is not restoration of missing M1–M6
files, a default backend replacement, or a whole-language GC/performance claim.
The ordinary CLI dispatch/checker/inference/erasure sources remain unchanged.

### Public reproduction

Use the official **GHC 9.14.1**, its global base/array/bytestring/text/containers/
directory packages, existing GCC and Python. No Clang or BDWGC is required here.
Set TMPDIR to a workspace directory. From this repository root:

```sh
python3 -B tools/experimental/resource-native/build_compiler.py \
  --ghc /absolute/path/to/ghc-9.14.1/bin/ghc \
  --build-dir /absolute/path/to/a-new-empty-build-directory
python3 -B tools/experimental/resource-native/run_native.py \
  --no-prelude --no-model --coarse --owned \
  --build-parent /absolute/path/to/a-new-native-output-directory \
  tools/experimental/resource-native/fixtures/scalar-foundation/overflow.emlf
```

The actual complete source is `addInt 9223372036854775807 1`. Expected typed result:
`{"kind":"i64","value":-9223372036854775808}`. `--no-model` disables the Python
reference evaluator only: actual source compilation, ordinary CheckedTerm
production, transport validation, independent resource checking, fresh static C
compilation, exact runtime/source pins, native allocation and link checks remain
mandatory. Omit it to run the model separately and compare actual results and
complete common ordered observations. Native-only explicit-Force location
markers are individually validated against the preceding actual payload and the
checked frame's Force instruction/order; all raw events are retained.

### Narrow admitted source contract

- Legacy standalone eMLF, exact source <=64 KiB; no named modules/import graph.
- Builtin Unit, actual intrinsic signed wrapping Int64 and Bool; closed concrete
  arrows; the existing single-constructor records, closures, lazy applications,
  recursive knots and cases. Final result must be Unit, Int64 or Bool.
- Five actual checked primitive constructors only: addInt(8), subInt(9),
  eqInt(10), ltInt(11), mulInt(14). Primitive applications must be directly
  saturated. Local source names never authorize primitive selection.
- Int literals preserve the real compiler's already-wrapped Int64 representation;
  malformed/out-of-range resource-IR literals reject rather than silently narrow.
  Bool comes from XBoolTerm and the compiler's intrinsic kind inventory, never a
  user constructor named True/False. Primitive thunks Force left before right
  only when demanded, retaining separate owners for aliased operands.
- Partial/first-class primitive values, polymorphic representations, Double,
  arbitrary-precision Integer, text, IO/FFI, ST and default/sum patterns remain
  outside this stage. Unsupported constructs reject at their actual stage.

Transport is `mlf-checked-recursion-export/2`; resource IR is version4. The legacy
export `producer.source_commit` field and PINNED_COMMIT name the historical
ordinary dependency base7bf7…, NOT the new exporter's commit. The new exact
compiler-input contract, real GHC build commands/binary, resolved-module sources
and actual inferred-interface dumps separately bind current modified code.
No checked constructor is forged, and matching transport identity alone never
proves genuine source origin.

### Fresh evidence boundary

This first source/native milestone qualifies the one overflow fixture through
both a fresh original interpreter and a relocated public native-only endpoint.
There are also15 synthetic transport/planner controls,10 exporter source guards,
9 full producer preflight controls,8 trace corruption controls,25 unchanged
ordinary CLI comparisons, and28 original-first source/model cases. The broader
source/model cases are NOT advertised as a native corpus pass. One named-module
original-reference attempt timed out at15 seconds and remains unknown; the new
standalone exporter rejects that module before elaboration. No cap was raised.
The old full native integration matrix has not been replayed for this revision.

Fresh independent scalar-core acceptance receipts are local under provenance;
old kernel/runtime receipts do not qualify new bytes. The generated target uses
C group ownership and its actual linked image excludes GC/GHC/Python symbols;
the GHC compiler host itself uses GC. Zero requested managed blocks does not
mean zero libc overhead/RSS. There is no source/native speed claim, no LSan claim,
and no claim to have replaced the whole target runtime's GC.

Focused source guards after a fresh compiler build:

```sh
python3 -B tools/experimental/resource-native/tests/test_scalar_transport.py -v
python3 -B tools/experimental/resource-native/tests/test_preflight.py -v
python3 -B tools/experimental/resource-native/tests/test_scalar_event_contract.py \
  --receipt /absolute/path/to/fresh-model-comparison-receipt.json -v
```

A trace test without an explicit fresh receipt is skipped, not reported passed.
All subsequent widening needs a new source/test identity, fresh verification and
another durable checkpoint; historical pass receipts cannot be carried forward.


## Explicit terminal policy on the bounded module2 route

The current additive `module-terminal-source/1` composition preserves `--module-root`
and its full ordinary checking/snapshot guards while exposing `--failure-policy
diagnostic|destroy-terminal`. Default remains diagnostic. Explicit destruction
surrenders the quiescent generated runtime domain after terminal evaluation; it does
not rewrite the fault report, resume exceptions, run finalizers or claim general GC.
`--observe-allocations` is a pinned qualification-only physical allocator observer.
Fresh acceptance is source-identity specific; consult the delivered stage contract,
source acceptance and retained raw evidence, not old component pass counts. No shared
polymorphic callable/TypeView semantics are added; logical resource IR remains v7.
