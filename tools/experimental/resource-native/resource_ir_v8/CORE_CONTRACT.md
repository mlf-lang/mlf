# Shared rank-1 callable core — final design contract

**READ-ONLY DESIGN CONTRACT. NOT implementation acceptance or release permission.**
Identity proposed:
`resource-ir-shared-callable/1`, IR8. One final hash must be ACKed by author, source
owner and independent design reviewer before semantic edits or registered probes.
This contract implements neither code nor source recognizers. Its exact-hash ACKs
settle the bounded design only; the base-adoption, source-evidence and preregistration
gates below remain mandatory before their corresponding semantic edits or probes.

## Stage25 amendment: closed Instance scalar computation

Stage25 narrowly extends the scoped-body opcode boundary, not the introduction
body allowlist. See `README_STAGE25.md` for current qualification status. Closed
intrinsic Int/Bool dependencies may be explicitly forced and used by the five
existing saturated scalar primitives and an Int-result conditional in a direct
generalized lambda. Open/rigid arithmetic and unsupported primitive forms reject.
The source checker and planner preserve the original Scheme scope in every body,
branch and allocation carrier. Original proof checking and graph sharing remain.

An effectful Scheme requires a derived `instance-only-scoped-scalars/1` closed-entry
proof: a unique introduction seals one direct closure, with an exact root Site/Code
and the complete same-Scheme allocation/Code closure and effect inventory. Extra
neutral allocations, pending application roots, unreachable scoped declarations
and `new_below` in this introduction reject in this bounded slice. This proof is
not inferred from observed reachability. The metadata layer independently checks
raw and derived Code inventories and reconstructs the proof. It retains neutral
CodeExecution/SiteExecution typing and representation rows; only lawful invocation
coverage is Instance-only. No new packet table or native per-Code whitelist is
introduced, and old no-effect programs retain their exact prior coverage.

For the new scoped operation allowance, native FORCE/PRIM2/SELECT entry requires
an authenticated Instance execution with
its actual Code, closed Env, Scheme, capsule, activation, home and no active
introduction. Public FORCE in that Instance execution additionally authenticates
the actual operand's closed
intrinsic scalar Type, principal Type and physical representation. This does not
restrict the enclosing callable's full signature, alter private callable forcing,
or permit evaluation in a neutral Generic frame. Construction stays non-evaluating.
The original imported concrete node/Access/memo remains unchanged, while new body
allocations use the selected closed Instance Env. Global publication, neutral memo
and Fill rules, terminal policy and allocator ledger remain unchanged.

Below, the original equal introduction/scoped-body opcode lists are historical:
only a freshly proved closed-entry scoped body gets this scalar-operation extension.
The Stage24 external scalar-import amendment otherwise remains in force. This is
not general polymorphic effects, arbitrary captured values or a source-admission
claim for fabricated diagnostic JSON.

## Stage24 amendment: explicit closed scalar imports

The original contract below records the initial no-external-capture boundary.
Stage24 narrowly supersedes that boundary for the opt-in IR8 route as specified
here. This amendment is a contract, not evidence that all validation or CI passed;
see `README_STAGE24.md` for actual execution status. Old no-import programs retain
their prior construction, metadata and accounting. No default route is enabled.

A concrete top-level generalized source let may capture ordinary closed intrinsic
Int/Bool values when its actual checked body, after its type prefix, is a direct
lambda. Independent replay and planning must agree on every lexical free binder,
checked type and occurrence. At most64 explicit bindings are admitted; aliases
count separately. Open/rigid/higher-rank, Scheme/view, callable and nominal captures,
nested or recursive generalization, and generic primitive operations remain outside
this source slice. Full proof witnesses, ordinary checking, outer-first substitution,
erasure and the actual lambda/application/let graph remain required.

`generalize` may have a nonempty canonical `imports` map. Every child name maps to
exactly `{value: parentName, layout: '^T', relation: 'down'}`. Fresh checking requires
an owned MONO parent with no tickets, exact intrinsic scalar type, allocated
unscoped concrete Site provenance, no projection and proven Down to the introduction
authority. Forced/UNKNOWN/foreign callback or INSTANCE provenance is insufficient.
After `generic_begin`, existing retain acquires a distinct child capability/storage
for every entry, preserving the actual node, group, readiness, type and Access.
The parent remains live. The child sees only `$home` and its explicit imports.
Imported aliases are discharged before seal; the result is still a fresh local
generic allocation, never an imported owner. Existing post-begin handle watermarks
check discharge. No support relation is invented: full imported References enter
placement support and can require coarse fallback in `--data-groups` mode.

The sealed result remains `generalize.outputs[0]`. Additional outputs are acquisition
facts at roles `['imports', child]`, joined to parent inputs at
`['imports', child, 'value']`; they are not allocation Sites. The emitter checks
these exact associations, fresh capabilities/storage, unchanged copy equations and
intrinsic type before using the existing retain/drop machinery.

Only the registered CAPTURE construction, stored-slot validation, read and transport
paths gain an alternative to the existing same-neutral-capsule/PROJECT rule. This
alternative authenticates exact Code, capture name/position and intrinsic Type,
then requires actual CONCRETE origin, E0, capsule/activation0, MONO Access and exact
Type/ShapeTyping/ShapeSpec/Representation. SCALAR denotes the intrinsic result
descriptor, not READY state: a pending THUNK or APPLICATION remains pending. Capture
adaptation retains the original Reference and uses the existing null-projection
identity Transport. A generic-owned closed scalar still follows the old same-neutral
capsule/PROJECT path. This is not a global concrete-to-generic publication rule.
Neutral arguments, return, application operands, memo and Fill retain their existing
restrictions. Global publication/transport and public ABI/packet tables are unchanged.

Boundary/Coverage records the complete static premise closure of the freshly checked
program, including unused callbacks. It is not a runtime whitelist or a list of
observed executions. Imported-Scheme capture obligations include both the existing
same-neutral-capsule/project and concrete-E0-intrinsic-scalar/identity cases. Native
capture safety does not depend on an extra per-introduction import table. Exact
source import correspondence is proved by fresh static checking and registered
generated Code. Old no-import programs cannot construct these external concrete
captures and retain their stronger neutral-only static premises byte-for-byte.

For the old clauses below, read "no external captures" as "no external captures
except this explicit scalar-import slice", and "neutral captures" as allowing
this capture-only alternative. All noncapture rules, complete-vector checks,
curried views, original Env/capsule/memo identity and allocator-ledger obligations
remain in force. Whole-Scheme capture and open `g = f` remain rejected.

## 0. Base and phase gates

Phase A is independently owned by the source owner and main source auditor. It
reconciles accepted module2/multiple-data-view source3568 with the accepted terminal
policy/observer/runner/native gate, preserving three module-package custody checks,
compiler closure and IR7. Neither old runner replaces the other wholesale.
Phase B waits for A's fresh acceptance AND durable readback, THEN the separately
parent-required latest-PR25 integration/requalification (target currently reported
c5928b5, not independently requalified by this design). That integrated-A stage must
be accepted/durable before B semantic edits. Record its exact source/implementation/
native/receipt hashes in BASE_INPUTS with source/reviewer readback ACK before copying
into a NEW root. These future hashes are not invented here; no receipt is inherited
merely because native files appear unchanged. The old source proof/binder numbers
below are historical motivating evidence, not hardcoded latest-compiler identities. Terminal C/H currently underlying A
are C01e37374c17e32e155296d244cede59c78fa844a857ee2f4c884d4b8733d3728 and
H218b05aaf832b0be3cf5eaa2c20624c21cb383b0899c1ee03a1c062c5c01d35c.

B retains default diagnostic retention, explicit post-unwind terminal destruction,
transactional aggregate/category free preflight, complete raw allocation registry,
external immutable fault report and separate destruction receipt. All enlarged
objects still use the registered allocator; no new untracked allocation/cache.
No old native/source receipt is reused as acceptance of the changed ABI.

## 1. Admission, and explicit exclusions

One outer rank-1 prefix per nonrecursive generalized term let, 1..8 distinct
bottom-Star parameters; body monotype is an arrow. Monotypes within that definition:
Int, Bool, its own rigid parameters, and arrows. Terms: variables, typed lambdas,
ordinary applications, monomorphic nonrecursive lets, Int/Bool literals. Every
ordinary lambda/application/let/coercion survives; no identity recognizer, body
cloning, inlining or type-application wrapper node. The retained historical binder38887 RHS has
3 lambdas,2 applications,1 let; that historical OUTER application is its shared cursor.
The future integrated compiler may elaborate the same source differently. Preserve
its ACTUAL newly checked RHS (ready closure OR pending application/other admitted
cursor), actual sharing and term skeleton; never recognize/require the old counts,
IDs or outer node category. Fresh extraction is a separate mandatory base/source gate.

Initially a generic definition has NO external value captures (authority/group
capabilities are not values). Nested generalized definitions, bare/escaping schemes,
scheme term arguments, partial type-prefix elimination, polymorphic recursion,
nonbottom bounds, higher kinds, impredicativity, unknown proof constructors, open
nominal operations and shared polymorphic data reject. Monomorphic term partial
application IS supported: k[Int,Bool]41 may escape as Bool->Int with a live capture.

Each actual TypeApp fully eliminates its exact prefix at ordered closed Int/Bool
arguments, including dead parameters. Source bridge replays every actual raw proof,
lexical occurrence and declaration; K.check/root alpha/erasure/term-skeleton equality
remain independent authorities. Core scheme labels are NOT proof of source origins.
The bridge binds source binder IDs/resolver entities/proof paths to IR introductions
and use IDs; IR checker independently establishes the generic typed/resource rules.

The stress case `f:forall a.a->a; g:forall b.b->b=f` is OUTSIDE this first boundary:
g's definition captures external f and uses an open instantiation. This rejection
must be explicit and tested, not silently specialized or called a general invariant.
Closed higher-order calls across lexical schemes are supported after instantiation;
the callee's lexical environment is never replaced by the caller's.

## 2. Logical types and exact IR surface

IR8 retains layouts/families/signatures/functions/codes and existing ownership
instructions. It adds these top-level maps (all keys unique, exact schemas):

```
"types": {
  "I": {"tag":"closed", "layout":"#i64"},
  "B": {"tag":"closed", "layout":"#bool"},
  "A": {"tag":"rigid", "scheme":"S", "index":0},
  "AA": {"tag":"arrow", "argument":"A", "result":"A",
         "protocol":"repeat", "result_identity":"unknown"}
},
"schemes": {"S":{"parameters":1,"body":"AA"}},
"instantiations": {"use_int":{"scheme":"S","arguments":["I"]}}
```

Closed atoms denote exact existing scalar/DATA/SUM identities; closed callable
layouts expand structurally into arrow types, not an opaque interchangeable atom.
Recursive nominal declarations stay atomic: type normalization does not unfold them.
Rigid identity is (S,index), never a reused integer from a different scheme. An
arrow is invariant/exact structural equality INCLUDING its callable contract
(protocol and result_identity recursively); no variance/subtyping/forgetting rule.
`closed` never names a callable or an unregistered/#reserved/%malformed layout.
Within S all free rigid variables must belong to S and be in bounds. Global code
cannot contain free rigid variables. Alias type IDs normalize canonically; cycles
in the type DAG reject. Complete scheme parameters remain present even if unused.

Existing signature/capture/hole result layout positions may use `^T` in IR8 to refer
to a logical type ID. Physical DATA/SUM declarations themselves remain fully closed;
no open field declarations are admitted.
Entire `^` namespace is reserved against physical layouts/signatures/families.
Existing ordinary layouts remain accepted as their exact derived closed type.
Generic functions/codes add `type_scope:"S"`; their signature argument/result and
capture layout entries use these scoped types. Concrete functions/codes have
`type_scope:null` (mandatory explicit field in v8). A callback belongs to
one lexical scope, is checked once under rigid variables, and emitted ONCE.

New instructions:

```
{"op":"generalize", "out":"shared", "in":"home", "scheme":"S",
 "body":[ ...ordinary ownership/allocation instructions...,
          {"op":"seal", "value":"outer_application"}]}
{"op":"instantiate", "out":"atInt", "value":"occurrence_owner",
 "instantiation":"use_int"}
```

`generalize` is an INLINE lexical resource/type block, not a callback, thunk,
closure or application allocation. The block imports ONLY its nonconsumed authority
under `$home`. No outer value handle is in scope. It can create fresh ordinary
owners/builders/loans using existing group rules. All locals except the result and
borrowed authority must be discharged at its `seal` terminator. No nested generalize and no generalize while executing code scoped under another
(or the same) scheme; its enclosing definition context must be concrete.
There is exactly one syntactic introduction per S. Its result type equals S.body.
The inline construction body cannot explicitly Force/invoke/case/prim2: it builds the
admitted lazy lambda/application/let/literal graph, not an eager evaluation region.
Later ordinary Force of this graph executes its callbacks as specified below.
The output owner/group/node is exactly its result's owner/group/node, with scheme
view, not a fresh group or extra shared memo. Resource support is its proven actual
support, with no stronger order relation inferred from polymorphism.

`seal` is legal ONLY as that block terminator. It consumes one ordinary owned,
ticketless, zero-outstanding-loan result and produces the enclosing scheme owner.
Raw HOLE rejects; unready THUNK/APPLICATION/INDIRECT and ready callable are allowed
when their certified origin/type satisfies the introduction. No Force/state change.
`instantiate` moves ONE live owner or anchored loan to a new local binding with the
same node/group/id/role/anchor/storage and no outstanding dependent loans. The old
name becomes unavailable. It does not retain/drop/allocate/Force. The input must be
that exact S's scheme view; the registered use's complete vector derives its result.
Distinct independently usable occurrences require ordinary retain/borrow first.
Scheme views may be retained/dropped/borrowed, but cannot be forced, passed as a
term argument, filled into a hole, or published as a value capture/data field.

One operation tick at generalize entry and one at instantiate; seal is its checked
terminator, no extra tick. Bounded validation/trace work is not called zero CPU cost.
No ready flag is fabricated: view moves preserve the prior readiness knowledge.

## 3. Static metadata closure — no runtime type allocator

The CHECKER derives, rather than trusting producer-asserted tables:

* Canonical type DAG and each legacy layout's closed logical type.
* Immutable allocation-site descriptors: owner lexical scheme/null, principal type,
  permitted node category, code descriptor for closures/thunks, source-map site.
* Environments E0 (concrete), ES (S's own rigid vector), and ES[theta] for every
  complete admitted closed vector for S. No cross-scheme open substitution in B.
* Every needed resolve(type,env), representation, access and transport row for all
  callback argument/result/capture, allocation, application, Fill, memo and return
  transitions, across those environments. Structural arrow substitutions (including unchanged resource contracts) included.
* Instantiation rows and permitted scope-introduction descriptors.

Bounds: schemes<=16; parameters<=8; type DAG nodes<=4096/depth<=32; environments<=1024;
allocation/code sites<=2048; access/transport/resolution rows combined<=65536;
new static typed metadata<=4MiB by exact emitted sizeof accounting. Existing source,
term/occurrence, family/variant, capture, frame-pointer and stack limits remain.
A deterministic closure worklist reaches a fixed point or rejects on ANY bound.
Missing rows are errors, never lazy interning, a heap cache or dynamic fallback.
All actual use vectors are included before closure. Closed higher-order arguments
retain their own registered rows; they do not require rewriting a foreign scheme.

Native open validates table membership BEFORE dereferencing unknown descriptors,
unique IDs/canonical equations, all counts/pointers, type DAG acyclicity/depth,
complete parameter vectors, derived substitutions/rows, allocation-site/code
association and static byte accounting. Scans are explicitly bounded, not assumed
constant time. Table pointers are program-owned immutable static storage with the
same lifetime precondition as descriptors/program strings. The checked emitter emits
all such tables in program-owned static storage. Registered-pointer membership proves
identity and table association, NOT the storage duration of arbitrary C-host memory.
An unregistered stack Env pointer rejects before dereference. A C host that registers
short-lived tables and later ends their lifetime violates the explicit program-metadata
lifetime precondition; native guards do not promise to detect that dangling-pointer
misuse. No generated table row, node, edge, access or closure contains a pointer to
an ephemeral C Frame, generic-scope token or stack dictionary.

A row existing in a table is NOT authority to cast an arbitrary capability. Only
(1) a checked matching seal+instantiate transition or (2) the runtime's specified
internal edge transport may change its access. No public set-view/cast API.

## 4. Immutable node origin, per-capability access, per-edge access

Each node permanently stores an allocation-site descriptor and origin:

* Concrete: E0, no generic capsule.
* Generic(S,capsule): ES, fresh nonzero capsule identity for that evaluation of the
  matching generalize block; activation0. Capsule identities are monotonic checked
  integers, not heap dictionaries. They distinguish repeated evaluations of one
  syntactic definition. This is a scoped provenance restriction, NOT type equality.
* Instance(S,theta,capsule,activation): ES[theta], originating capsule and ordinary
  call's nonzero activation ID. Returned closures preserve this immutable origin.

Origin is separate from mutable state and `n->code`: memo publication may clear
active code but NEVER origin/site/env/capsule/activation. Node principal logical
type is resolve(site.type,origin.env). A principal type or code name alone is not
proof of generic origin. Instance closures can never be sealed, even if their
closed type happens to resemble a substitution of the scheme body.

Every value handle carries one registered immutable Access pointer. Every strong
slot (ordinary field, closure/thunk capture, application operands, Fill, memo) stores
(target Node*, Access*) BY VALUE, never a handle or frame-local dictionary pointer.
Home/pin/builder handles with no value have no Access. Owner promotion copies Access
as part of the existing single-owner move; no ownership duplication.

An Access row is keyed by allocation site, origin environment, and permitted use
projection, and supplies its logical type and mono/scheme classification:

* Concrete/Instance nodes: monomorphic access preserves their own origin env.
  Structural type agreement never replaces a foreign callee's saved environment.
* Generic nodes: neutral access uses ES; a checked closed projection uses ES[theta].
  Both refer to the same node and immutable principal origin. A scheme access is
  available only for a node of S.body at that S's matching introduction.
* Capsule/activation values are checked dynamically where origin rules require
  them; they are NOT part of canonical logical type equality or static table keys.

Public instantiate requires scheme access plus exact scheme descriptor/use vector.
Internal adaptation of captures/memo edges is permitted only by an already valid
callee/request projection and the registered transport equation. Retain/borrow,
field projection and slot acquisition copy the specific Access; they may not
reconstruct it from Node.shape or a guessed first instance.

## 5. Inductive publication and physical representation guards

For ANY strong edge, first validate target capability/loan anchor, exact registered
Access-site/env association, physical representation provenance and expected logical
type. Then apply existing ownership/group-support constraints and acquire the owning
edge before release of its source/anchor. A type environment contributes NO value
ownership and NO extra group-order fact.

A Generic(S,capsule) host accepts only neutral Access to a Generic(S,same capsule)
target of the exact expected type. This restriction follows from B's no-external-
value-capture admission; it is NOT a general theorem of polymorphism. Neutral scalar
literals created INSIDE the capsule have Generic origin too. The same rule covers
intermediate application operands, captured values, Fill and memo edges, not merely
the final closure. Instance/Concrete hosts accept equal CLOSED logical types from
ANY valid target origin, preserving the target's own Access. E.g. id[Int] returns
and memoizes the original concrete Int argument, not a relabeled Instance node.

Physical safety is not replaced by type rows. For closed scalar, DATA and SUM,
existing exact shape/family/discriminator/payload-size guards remain. A neutral
open arrow/variable gets a registered symbolic representation descriptor associated
with its type/site; it cannot be allocated as ordinary READY DATA or read as scalar.
READY closure requires registered FUNCTION origin/site/code and arrow logical type;
READY scalar requires its intrinsic payload allocation and exact scalar type.
No READY value with an unresolved rigid-variable representation is admitted.

A projected generic callable can physically retain its original open-arrow descriptor
while logically being Int->Bool etc. This is the ONLY new callable compatibility
branch: authenticate its immutable function origin and Access equation. It is not
an equality-by-size test or global Any. In v8 ALL callable boundaries, including Concrete-to-Concrete, use the SAME exact
canonical full-contract arrow equality PLUS representation-origin validation. A
consumer's nominal signature pointer is not an additional callable type identity.
The actual node must still match ITS OWN allocation-site/physical-shape/code proof;
no node is retagged. Scalar/DATA/SUM identities remain exact and nominal.
DATA/field guards use this full-contract callable rule and preserve Access for closed
callable values too. This explicitly admits a projected generic callable, or an
ordinary Concrete closure at legacy @B, through a structurally equal monomorphic
consumer expecting legacy @A when their FULL recursive contracts match.
The frozen A/v7 backend retains its original opaque-signature/pointer behavior.
B's native/emitter admission is IR8-ONLY: it does not execute old IR7 artifacts or
promise that old generated C links with the changed ABI. Closed regression controls
are explicitly re-emitted as v8; this is a new reviewed type boundary, not a covert
weakening of an old acceptance receipt.

Allocation sites and code templates determine lawful origin/category. Generic body
code cannot apply an Int primitive to rigid a, even if every observed vector happens
to select Int. Old scalar/case operations outside generic code retain exact types.
Unknown/foreign row/scheme/env/site or wrong payload kind fails BEFORE demand or
payload interpretation. This is checked-emitter/runtime defense, not a hostile-C
sandbox for arbitrary forged/dangling Node addresses.

## 6. Callback entry/exit and higher-order lexical environments

RtBody receives one extra `const RtEnv *env` argument; it always points to registered
static metadata. Frame saves its execution origin by VALUE. Allocation helpers use
that current origin and verify each registered allocation site's lexical scope.
A short-lived generic-scope token can save/restore Frame execution fields during
inline generalize; it must never be stored in a node/slot/handle. It authenticates
current frame, intro descriptor and fresh capsule ID at seal; unmatched/reused token
rejects. Poison leaves it unusable, and terminal destroy does not follow it.

Invoking a neutral Generic(S) closure through neutral Access executes in Generic(S,
same capsule), with symbolic parameter/result/capture equations. Through a closed
Access theta it executes in Instance(S,theta,same capsule,new call activation),
with captures internally adapted from neutral S to theta. The passed argument must
have the exact resolved parameter type and valid physical provenance. A NEUTRAL call
requires neutral Generic(S,same capsule) argument/capture origins even when their
type happens to be closed Int. Only CLOSED invocation permits a concrete scalar/
function or a closed callable from another scheme/activation. This rule is checked
at invocation too, not merely at application-slot publication.

Invoking an Instance closure uses ITS stored lexical env/capsule and a fresh call
activation; capture owners retain their stored views, even from an earlier activation.
Invoking a Concrete closure uses E0. Do not substitute the caller's env merely because
parameter arrows compare equal. The callee's function code is emitted once; no
per-vector body variants. Callback return validates expected resolved type, physical
origin and ordinary ownership/support; identity-argument checks remain where proved.

A returned curried closure holds static env pointer plus inline immutable provenance
and explicit owned capture edges. After caller-frame exit it is independently callable.
It is monomorphic, including when created from a fully instantiated generic function.
`k[Int,Bool]41` cannot be sealed as forall a b.b->a. Activation IDs record origin but
same-typed values may cross activations and schemes through ordinary closed arguments.

Thunk execution always uses the thunk's OWN origin env, never requesting closed view.
Internal Generic applications likewise execute neutrally. Whole-scheme external
value captures are rejected at declaration/bridge/IR check, not guessed independent
from a closed-looking runtime layout.

## 7. Force and neutral path compression — exact continuation algorithm

Force accepts a monomorphic Access, never a bare scheme owner. It consumes the
same value capability as before. Each pending continuation stores destination node,
existing pin, requested Access at entry, and later the principal memo Access; all
pointers stored there are nodes/handles with ownership or registered static rows.
No stack dictionary escapes. Extend existing Pending with previous link for reverse
validation; all storage remains the registered pending category.

For each unready node n, validate its request and save that request in Pending.
Dispatch its computation under n's PRINCIPAL env/type, not the request projection:
Generic(S) executes at ES, Instance at its ES[theta], Concrete at E0. Capture
acquisition restores each saved edge Access; application uses its function slot's
specific use view and argument slot. Record each node's own expected principal
result type, rather than one expected shape from the outermost requester.

The returned raw cursor may be unready and may have a different origin. Validate
its logical type/publication rule against the current node, then continue Force
with the returned cursor's OWN Access. BUSY/HOLE remain one state per node, never
per-instance states. No first caller's projection is written into n or its slots.

Memo fast path reads a stored PRINCIPAL edge, authenticates it, then transports it
using n's incoming requested Access: Generic(S) neutral target -> same S/theta
projection; Concrete/Instance -> preserve stored target Access. Acquire target with
that transported Access before releasing cursor. No retagging of the target node.

When a final ready cursor is reached, walk Pending LAST-to-FIRST without publishing:
1. Current cursor Access must satisfy this destination's principal expected type
   and publication-origin rule. For Generic S this is exact SYMBOLIC equality in ES
   using the retained target site/original neutral Access, BEFORE applying theta.
   Save the exact target Access as this Pending.memo_access; never reconstruct it
   by inverting a closed projection or selecting a row by resolved type alone.
2. Transport that Access to this destination's saved incoming request. For Generic S
   a closed theta projection adapts the neutral same-capsule target using a registered
   row; a neutral request is identity. For Instance/Concrete preserve target Access.
3. The resulting cursor view is what the preceding continuation requested. Continue.

Only after ALL pending-edge equations validate, publish FIRST-to-LAST, preserving
existing event/release order: every destination points at the same final Node but
stores its OWN saved memo_access. Then unpin/release in existing order. The final
returned owner has the outer request's composed Access. Thus an outer concrete
application can memoize a closed view of a shared Generic result while inner Generic
nodes memoize neutral edges. No inverse substitution, heap graph scan, first-instance
memo, per-vector cache or guessed node-shape reconstruction is needed.

All memos preserve immutable origin/site/env/capsule after clearing active code.
Fill similarly checks both logical equality and the host-origin edge rule; ticket
and raw-HOLE restrictions remain separate, not erased by a type view. Native and
model must use the SAME publication/owner/loan/event order, no filtering away type
or ownership events to claim parity.

## 8. ABI/accounting/lifecycle changes requiring new qualification

Proposed concrete fields (final packing/sizeof measured, not promised):
* Handle adds Access*; existing128-byte typed-local-storage bound remains mandatory.
* Slot adds Access* alongside target/name; all acquisition/publication paths update.
* Node adds immutable origin site*, env*, capsule ID, activation ID. Mutable code
  pointer remains separate. Scalar/Sum embedding follows enlarged Node base.
* Pending adds previous*, requested Access*, memo Access*; pin/next/node unchanged.
* Frame stores execution env/capsule by value; RtBody extra static env* argument.
* RtCode/RtProgram gain registered typing/site/type/env/access/intro/use tables.
* Context gains checked capsule identity counter and no dynamic metadata map.

No new allocator category is necessary: larger Nodes/Slots/Handles/Pending/Context
are already counted; static tables are separate exact descriptor bytes. Counter or
allocation failure before/after publication poisons under existing policy; no rollback
claim. Terminal destroy walks ONLY MemHeader registry and context last, never the new
type, origin, frame, slot or memo metadata. Default diagnostic report remains historical;
opt-in separate receipt must physically retire every registered enlarged block.
New ABI invalidates old native receipts and old size totals; no old pass is inferred.

## 9. Observation and finite gates to freeze AFTER contract agreement

No target/original/model/native probes have been executed for B. Before any, register
exact fixture bytes, bounds, expected outcomes/source custody, command count and
finite test plan with reviewer. Do not improvise an80-second source matrix.

Required core witnesses (combine controls, not a cross product):
* HISTORICAL core-stress graph with three lambdas/two applications/one let; Int-first
  and Bool-first plus repeated use; shared existing outer-application node and one
  neutral memo target; no wrapper. These counts/category are NOT a mandatory shape
  for the new-base source. Its separate fresh source gate preserves the ACTUAL checked
  RHS and sharing, whether its root is ready or pending.
* Curried const at [Int,Bool]/[Bool,Int], caller ends then captured returned closure
  called/repeated; distinct activation origins but legitimate closed value crossing.
* Higher-order apply with foreign concrete/instantiated callee, lexical env preserved.
  Include the concrete @B -> ^Arrow consumer -> @A consumer positive when @A/@B
  have the same FULL arrow contract; no pointer retagging or hybrid equality rule.
  Its same-arrow constant/unknown -> identity-refined consumer counterpart rejects.
* Ignored/demanded typed self-thunk argument; TypeApp zero Force/allocation/RC, exact
  fault prefix; diagnostic versus opt-in physical release separated.
* Owner/loan view movement, slot publication before anchor release, promotion and
  same-node distinct owners across before/after memo. Old concrete normal/fault control.
* Dead parameter vector, table/depth boundaries and one-over rejection.
* Public B generation/target rejects IR7 before native generation; no old generated-C
  linking or hidden runtime fallback. Verify the frozen accepted integrated-A input
  hashes before and after B work, with concrete v8 controls re-emitted/rechecked rather
  than silently treating old acceptance as an ABI regression pass.

Host/checker negatives: wrong scheme/use/rigid scope/vector order/arity; illegal
primitive on rigid var; callback/capture type swap hidden by Int/Int; external generic
capture/open g=f; bare/partial/polyrec/nested/unknown proof; reseal Instance closure;
foreign capsule neutral edge; missing intermediate application Access; first-instance
memo overwrite; duplicate owner derivation; forged stronger support; unregistered
metadata row, including an unregistered stack Env pointer. Reject without evaluating deferred values. Registered
short-lived C metadata misuse remains outside the lifetime precondition stated in §3.

Native defensive controls: registered-but-inapplicable row (not just unknown pointer),
foreign capture/return/memo principal equation, equal-size Int/Bool, physical READY
forgery, owner/view copy omission, and precise allocation-failure windows for the
new generic application/curried capture/Force/promotion path. Observer checks actual
malloc/calloc/free and terminal zero after unwind; do NOT replay every prior matrix.

Source gate separately preserves actual module resolver/custody and full proof/erasure
maps, first existing SharedPoly original42 only by verified adoption; register any new
curried/higher-order/laziness source and original work BEFORE running. One restored
fresh compiler/public no-model gate then independent acceptance and durable readback.

Trace fields should identify allocation site, origin env/capsule/activation, Access/use,
source binder/proof occurrence, function lexical env, and each memo edge Access. Scheme
seal/instantiate events prove unchanged owner/node and no allocation/retain/Force.
No performance, fullGC, general rank1-data, impredicative, IO/ST/FFI/finalizer or resumable
exception claim follows from this bounded callable extension.

## 10. Final design adoption and remaining execution gates

1. Author, source owner and independent design reviewer ACK this exact final file
   hash. An ACK is design agreement, not evidence that any implementation/probe passes.
   Structured generalize/seal, exact callable contracts, neutral reverse-validation /
   forward-publication, all-v8 representation equality and all appendices are one
   inseparable contract; no implementation may select conflicting prior draft rules.
2. Bind the separately requalified latest-PR25 integrated-A base in BASE_INPUTS with
   exact source/implementation/native/acceptance/durable-readback identities and obtain
   explicit source/reviewer base-adoption ACK. No B semantic edits before this gate.
   Phase A alone, even after acceptance/readback, is not that newer integrated base.
3. Before producer/bridge semantic edits, source owner freezes the exact source export /
   proof-occurrence / capture-conversion evidence contract on that integrated compiler.
   Re-extract actual binders, proof forms and term skeleton; no historical ID/count
   recognizer, fabricated specialization, or dependency on old outer-APP elaboration.
4. Before B original/model/native probes, freeze a finite plan satisfying §9, exact
   fixture bytes/custody, expected layer-specific rejection, bounded commands and failure
   retention. If implementation reveals a substantive contract change, stop that path
   and obtain a revised exact-hash design ACK rather than widening the accepted scope.
5. New implementation/source receipts and independently read-back source/tests/raw
   checkpoints are required before any new stage. No performance, complete GC removal,
   generic parametricity, unsupported source form or old-ABI compatibility claim follows
   from these design ACKs or from unchanged input-file hashes alone.

## Appendix A — derived tables and ABI boundary (normative)

These are conceptual C layouts/algorithms, not source edits. Native structs may
choose equivalent checked-width indexes instead of pointers, but cannot omit a
field's authority or introduce a runtime allocator. The final implementation
manifest must record concrete sizes/alignment and every new static table byte.

### A1. Canonical table contents

`Type` rows are `Closed(physical_atom_shape)`, `Rigid(scheme,index)`, or
`Arrow(argument_type,result_type,protocol,result_identity)`. Closed arrow references are expanded; nominal
atoms keep exact declared family/argument-instance identity. Canonical ordering is
structural topological order of normalized JSON tuples; closed shape identities and
scheme identities use the checked canonical names, not source hints. Aliases may
share one canonical row; foreign rigid scopes may not. No table cycles.

`Env` is `(scheme-or-null, mode, ordered vector)` with mode CONCRETE/NEUTRAL/CLOSED.
E0 is index0. Neutral S's vector is exactly Rigid(S,0)..Rigid(S,n-1); closed S's vector
has exactly n Int/Bool rows. Remaining ordering is scheme ID then mode then vector.
No partial vector and no foreign neutral variable. All use rows retain the full
vector, even for dead parameters. Instantiation count<=1024 in addition to the
previous worklist/row bounds.

`Site` is `(canonical allocation path, lexical scheme-or-null, principal Type,
category, code-or-null, legacy physical descriptor-or-null)`. Canonical allocation
path is (entry/function/thunk, code ID, nested generalize path, instruction index),
not a producer-supplied "trusted" flag. Categories are the actual allocation opcode
classes. A closure/thunk site has that exact registered Code and type; an application
site has the derived result type; a scalar site has its literal's intrinsic type.
Legacy physical descriptors are retained where old concrete IR specified them.

`CodeTyping` is `(code ID, lexical scope, argument Type-or-null, result Type,
sorted capture name/Type/relation vector)`. It is derived from checking the entire
body, not accepted instead of body checking. Native guards use it for actual
handoff/return values; structural function type equality does not equate code IDs.

`Access` is `(site ID, origin Env ID, mode MONO|SCHEME, use Env ID-or-null,
logical Type ID, scheme ID-or-null)`. It authenticates target site+origin env.
MONO Concrete/Instance accesses use that same principal env. MONO Generic accesses
use neutral S or one registered closed S vector. SCHEME accesses use neutral origin,
no use env, and exact S body type; they remain a separate classification, not a
monotype whose forall was ignored. Dynamic target capsule/activation is NOT in the
row. Type equality checks MONO before comparing its canonical type.

`Intro` is `(S, enclosing concrete code-or-entry, checked result origin-site set,
body/result type)`. Result-site set is recomputed from the inline construction's
SSA provenance; in the retained historical fixture it contains the outer application allocation
site; the fresh compiler's actual RHS site/category must be rederived. It is not a runtime result-of-Force prediction. It binds the allowed seal,
but not a secret unforgeable C token: checked emission remains part of the trust base.

`Use` is `(use ID, S, full ordered closed vector, target Env, closed result Type)`.
Source bridge separately binds use ID to exact source occurrence/proof. Checker
recomputes target env/result; native verifies row equations and matching input SCHEME.

Resolution rows are `(Type,Env)->resolved Type` and `(Type,Env)->physical rep`.
Access/transport rows sort by `(site,originEnv,mode,useEnv,scheme)`. The only
nonidentity transport is a same-scheme neutral target Access under an authorized
closed request/callee projection. It produces a row for THAT target's own site.
Instance and Concrete edge transport is identity preserving foreign target access.
Closure acquisition never gives a foreign callee the current caller's env.
The full recursive arrow contract participates in EVERY row equality/transport.

### A2. Finite closure construction

1. Check all schemes, source-independent rigid typing, callback/resource bodies,
   introductions and complete uses. Reject undeclared/missing/malformed entries.
2. Intern principal type DAG plus all exact legacy closed types. Add E0, one neutral
   env per S and every distinct full closed use vector; no speculative runtime inputs.
3. For each code/site type and each legal environment of its lexical scope, recursively
   substitute and intern the resulting arrow/atom type and physical representation.
4. For each site in S, add its neutral principal Access, each admitted closed projection
   of that neutral origin, and principal accesses for allocations in every closed env.
   Add SCHEME rows only for sites in that intro's recomputed result-site set.
   Concrete sites get only concrete principal Access. Add the corresponding same-S
   projection/identity transport rows. Application/capture/return edges copy a target's
   existing row; there is no cross-product of caller and callee lexical environments.
5. Iterate type/representation/row dependencies to a fixed point. All counters and
   maximum depth checked on insertion; any missing closure or bound overflow rejects
   before native execution. Environments are not synthesized from values on the heap.
6. Serialize tables canonically with a derived-table SHA bound into CheckedProgram,
   codegen binding and executable receipt. Raw IR SHA remains separately bound. Model
   uses checked immutable tables; native open replays structural row equations.

Multiple descriptors for closed vectors are NOT cloned lambda bodies or extra value
nodes. Their static bytes/counts are reported, with no speed/zero-cost inference.

### A3. Physical representation relation

Concrete atoms resolve to the exact preexisting scalar/DATA/SUM descriptor. An arrow
with fully closed children has a registered fixed Repeat representation (legacy
physical aliases may remain distinct, while v8 callable equality uses the full contract).
A type containing rigid variables has a new registered `RT_OPEN` descriptor linked
to its exact Type+S; names occupy a reserved internal `^` namespace. Ordinary DATA,
Repeat, intrinsic and family declarations cannot masquerade as this kind/name.

Instance allocation resolves its site's principal type in its saved closed env;
its physical scalar/arrow representation can therefore be concrete even though its
CodeTyping remains symbolic. Its full callable contract is independently bound to
the actual FUNCTION Code protocol and result_identity_argument flag; domain/result
pointers or a row name alone cannot manufacture that guarantee. Generic neutral arrow allocations retain RT_OPEN.
A view of that same Generic node at Int never rewrites RT_OPEN to fixed Repeat.
RT_OPEN is lawful only for typed deferred cursors or typed closure origins; no
ordinary allocator can produce READY DATA/scalar storage under RT_OPEN. Its size
never authorizes reading a scalar/variant payload.

`Rep(node,Access,expected)` checks registered site/env/row, exact node physical rep
as allocated, valid state/category/code provenance, and expected logical type.
For a callable, ready means authenticated FUNCTION closure; deferred thunk/app/hole
retains a typed result obligation, not a claim that it is already callable. For
noncallables, the old exact physical identity/payload checks still apply at demand.
At all closed callable handoffs, including a monomorphic higher-order consumer,
authenticated typed-callable interoperability is explicit; equal pointer size alone
never passes. Invalid registered rows fail as well as unregistered pointers.

### A4. Dynamic fields and inline scope token

Conceptual additions:

```
Handle:  const Access *access;                    // NULL for authority-only handles
Slot:    Node *target; const Access *access;      // together with existing name
Node:    const Site *origin_site; const Env *origin_env;
         uint64_t capsule_id, creation_activation;
Pending: Pending *previous; const Access *requested, *memo_access;
Frame:   const Env *exec_env; uint64_t capsule_id;
         const Intro *active_intro;              // static pointer, never token ptr
Body:    (...old arguments..., const Env *env);   // program-static pointer only
```

Code/Program contain or reference the typed tables; no owner hides in a table.
Capsule and frame IDs use existing checked identity/overflow discipline. Instance
creation_activation is current call Frame.id; Generic activation0. Different
activations may share same-typed values. Site/env/capsule/activation never mutate
when a node becomes BUSY, INDIRECT or MEMO.

`generic_begin` verifies registered Intro belongs to current concrete frame/code,
no active intro, and zeroed local token; reserves one fresh capsule ID, records the
old frame typing values in a caller-stack token BY VALUE, sets frame exec_env=ES,
capsule and active_intro. It does not call frame_enter, allocate, retain or Force.
`seal` requires the same frame ID/current active intro/token/capsule, a node from
that capsule and permitted result site, body type, normal ownership/ticket checks;
sets only this handle's SCHEME Access, deactivates token and restores frame typing.
No token pointer is stored in persistent objects. Return with an active intro rejects.
Any fault unwinds/poisons; diagnostic reentry is forbidden and raw terminal destroy
never follows the stale Frame/token. Reusing a token rejects.

Nested IR lexical scope must NOT cause a handle cell to escape C automatic storage:
the emitter reserves all child-body typed handle cells in the enclosing function's
existing checked storage plan, or keeps exactly equivalent enclosing lifetime.
Generalize's result aliases its existing parent-lifetime handle cell; no extra owner
promotion/heap allocation merely for TypeAbs. Instantiation likewise aliases the
same handle under a new SSA name, not an owning struct copy. Enclosing frame's512
pointer-cell and128-byte handle budget plus GCC stack limits remain checked.

## Appendix B — resource-contract, schema and API decisions (normative)

### B1. Exact callable contracts; no free-theorem owner facts

Every arrow carries protocol and result_identity recursively, including arrow
arguments, results, captures and fields. NEW generic scope/types/views admit ONLY
`repeat`/`unknown` contracts at every arrow position. The actual source planner
already emits this pair. There is NO subtyping or automatic forgetting in B:
identity->unknown conversion may conservatively reject too. This is explicit
bounded incompleteness, not a claim such forgetting is unsafe in general.

Legacy closed `result_identity:argument` semantics retain their required symbolic
body proof and identity/group guarantee when explicitly represented in v8. The old
A/v7 backend itself remains frozen; old artifact execution is not part of B. A generic/unknown/constant Int->Int value cannot enter
an identity-refined Int->Int parameter/field/capture simply because domain/result
are equal. Rejection occurs before the consumer may derive identity/group/lifetime
facts. Native FUNCTION CodeTyping, origin Site and Code.result_identity_argument
must agree exactly on that contract; Repeat/Once must agree too. Once remains
outside the native subset. A thunk promising a callable type must return an Access
with that full callable contract; a FUNCTION ready target then validates its code
association, not the thunk's unrelated identity flag.

Do not infer cursor identity, owner identity, support-group equality or loan facts
from `forall a.a->a` or a parametricity theorem. The real coercion application/let
can return deferred wrapper cursors. Generic direct results remain unknown-identity
Down(home). Existing explicit capture relations (same/down/strict-below) and owner/
loan/anchor rules are independent premises, unchanged by type equivalence. Native
refinement guards complement the symbolic checker; they do not replace its static
partial-order proof. The old native group record does not independently store a
complete type-level order relation, and this stage does not claim otherwise.

Mandatory negative: a constant Int->Int callable behind a same-domain/result view
must NOT enter a consumer whose callable parameter promises argument identity.
Also reject protocol mismatch at any nested arrow position. Valid legacy concrete
identity remains separately bounded, never silently downgraded or upgraded.

### B2. Non-injective substitution trust split

Use S[a,b] with theta=[Int,Int] and a dead-parameter variant as explicit witnesses.
A neutral a->a target and neutral b->b target remain DIFFERENT canonical types in
ES. Generic callback/publication/pending guards compare those exact retained symbolic
Access/site types BEFORE outward projection. Swapping them must fault/reject even
when both closed views resolve to Int->Int. Retain the actual target row and code/site
publication witness; no inverse substitution, guessed preimage or first-match row.

An Instance-only callback can legitimately accept concrete Int nodes in either
formal at [Int,Int]. Native closed-type checks cannot detect EVERY wrong same-typed
C callback/operand choice. The all-path IR checker under rigid a,b plus checked
emitter/source binding supplies that proof. Do not claim runtime table membership
establishes arbitrary C parametricity. Negative tests identify the rejection layer:
wrong symbolic return/capture rejects in checker; forged neutral edge rejects before
memo publication; a collapsed Instance-only source mistake is not promised a native
fault solely from its equal closed payload types.

### B3. Exact schemas and allowed instruction sets

Version8 top-level keys are exactly the version7 keys plus `types`, `schemes`,
`instantiations`; maps may be empty for regenerated concrete controls. Each type tag
has exactly the fields shown above: closed(tag,layout); rigid(tag,scheme,index);
arrow(tag,argument,result,protocol,result_identity). Scheme exactly parameters/body;
use exactly scheme/arguments. Integer counts reject bool-as-int. All user names obey
existing nonempty/NUL/native namespace guards plus the new reserved ^ prefix.

In v8 every functions entry has exactly signature,parameter,captures,body,type_scope;
every codes entry exactly result,captures,body,type_scope. type_scope is explicitly
null or one declared S, no inferred/default scope. Capture entries remain exactly
layout/relation with relation same/down/below. Signature entries remain exactly
argument/result/protocol/result_identity. Generic signature/capture/result references
may use ^T only if T is well formed in that exact S. Concrete callbacks may use ^T
only when it is closed. Physical layouts/family fields contain no open ^type.

Intro body exact allowlist: new_below, scalar, closure, thunk, application,
application_borrow, retain, drop, borrow, end_borrow; final seal only. No root/loop,
hole/fill, force/call, case/select/choose, prim2, DATA/SUM allocation/projection,
finish, nested generalize or instantiate. Generic scoped function/thunk bodies have
the SAME list with return instead of seal. These blocks construct the admitted lazy
lambda/application/monomorphic-let/literal graph; internal runtime Force of their
application nodes remains supported. Recursion through scoped Code allocation graph
is rejected for this first fragment (no self/mutually recursive closure creation).
The source still emits exactly its term graph, never an extra generic thunk.

Concrete entry/functions/codes retain the existing checked native subset plus the
new generalize/instantiate operations. Existing old checker operations unsupported
by the emitter (Once/direct call/loops etc.) do not become native-supported merely
by this draft. Native B rejects non-v8 artifacts before generation; no ambiguous
legacy/new metadata dispatch is introduced. Generic native invoke is the ordinary internal application evaluator;
it still enforces the explicit neutral direct-entry capsule guard for defense.

Source maps preserve every actual ordinary lambda/application/let and proof occurrence.
Generic external value capture, including a closed-looking captured global, rejects
before code generation. Monomorphic curried instance capture is NOT such a capture
and remains required. Physical DATA callable publication uses full recursive contract
plus representation validation and saves Access; no unknown guarantee is discarded.

### B4. Structured linear export

Let parent state be (Gamma,Order) and its authority be group H. Child starts with
one non-value `$home` authority alias of H and a COPY of justified Order facts; no
parent value names are visible. It does not create an owner/loan/key or runtime
activation. New child SSA identities/groups remain globally fresh in the checker.
No use of `$home` in a value/capture/argument position is allowed even if the actual
parent authority handle happens also to refer to a node.

At seal, require one result owner, ticket discharged, no outstanding loans, group
G proven Down(H), principal type S.body, matching neutral capsule/site. All other
child capabilities except `$home` must be discharged. Consume that child result
binding and export the SAME value identity/group/readiness, with Scheme classification,
under the parent out name. Merge new Order facts needed for G and its supports;
never replace G by H, invent strict descent, or treat distinct group symbols as
physical inequality. Parent Gamma and all existing anchors/loans are unchanged.
Other child local names remain unavailable and cannot appear in parent instructions.

Native token records current frame ID, static Intro, authority handle, fresh capsule,
prior execution fields, handle-identity watermark and active bit. At seal all guards
precede Access mutation. Current frame/intro/capsule/token must match; authority
remains live. Scan the existing live HANDLE registry for handles created since that
watermark: only the result may remain. Parent handles predate the watermark. This
is the ordinary linear-capability export guard, NOT a reachability/type cast scan
of nodes/slots/memos. It is bounded by live capabilities and not called constant cost.
No callbacks execute during the restricted construction block, so sequential watermark
ownership is unambiguous. Capsule/handle counter overflow poisons before publication.
Seal restores prior execution fields and deactivates token only after validation.
On fault no recovery/unwind restoration is claimed: poison prohibits continuation;
terminal destruction ignores stale token/frame/semantic lists.

View move on an owning handle requires no loans anchored to the old owning name;
view move on a loan requires its exact live anchor and no dependent loans. In both
cases delete the old SSA binding, preserve mode/id/node/group/storage/anchor and all
anchor counters, install only the new immutable Access, and bind the new name.
Native instantiate edits Access in place; it MUST NOT call owned-only move_owner on
a loan. End-borrow of the moved loan decrements its original anchor exactly once.
Retaining a loan remains the existing independently checked owner acquisition with
its Access copied before the anchor can be released.

### B5. Public/internal C API boundary

Exact new view-operation signatures (names frozen here, implementation pending):

```
void rt_generic_begin(RtContext*, RtGenericScope *zeroed_local,
                      const RtIntro*, RtHandle *authority);
RtHandle *rt_generic_seal(RtContext*, RtGenericScope*, RtHandle *owned_result,
                         const char *out);
RtHandle *rt_instantiate(RtContext*, RtHandle *owner_or_loan,
                         const RtInstantiation*, const char *out,
                         const char *source_variable);
```

Scope storage is enclosing-frame-local only; none of its addresses can be persisted.
seal/instantiate return the SAME handle pointer, not a copied owning struct/new handle.
Both reject Scheme/Mono/mode misuse before payload interpretation; raw HOLE does not
become a safe cursor because a view row exists. Force on Scheme remains forbidden.

V8 allocation entry points add an explicit `const RtSite*` after the authority
argument to the scalar/closure/thunk/application/hole/ordinary DATA/SUM/factory helpers
(and their `_into` forms). Code pointer remains explicit for closure/thunk; site.code
must be that exact pointer. Site type/category/scope, current Frame execution env,
actual operands and all capture/access equations are validated BEFORE allocation.
This includes rt_prim2 (its scalar-result Site is passed through the private scalar
allocator), construct_nullary/construct_sum and ordinary alloc. Group-only creation
has no Node origin Site, and pure owner-transfer select/case keeps the chosen Access.
A case_fields_i64 instruction derives ONE Site PER ARM (instruction path, declared
variant index), carried in the extended RtFactoryArm beside its exact code. Validate
ALL arm/site/code/type associations before selected payload access or temporary
allocation; the chosen thunk receives that arm's Site. Temporary field-owner
acquisition copies the actual payload edge Access; it does not invent a new Node Site.
No site is guessed from a printed out-name. Exact existing resource arguments/order
are otherwise preserved. Emitter supplies only the checker's derived site for that
instruction. These new-ABI allocation signatures REQUIRE a nonnull registered Site; private
allocation also rejects absent Site. The old site-less prototypes are not a fallback
entry to typed allocation. Standalone old-C ABI compatibility
is not claimed; concrete regression controls are regenerated against the new ABI.

Nonallocation APIs retain their external ownership contract while internally copying
Access: retain/borrow/field acquisition, application capture handoff, case factory
selected-field temporary owners, Fill, Force and return. Callback RtBody's final
argument is the registered static Env*. Return uses the current Frame CodeTyping,
full result contract and origin rule; no caller-provided cast parameter.

Internal `transport_access` is private to capture adaptation, memo read and reverse
pending validation. It takes the validated host/request plus the ACTUAL target edge
(Node*,Access*), never just a desired closed Type. It validates the applicable symbolic
or closed equation and looks up the already derived row. It cannot be called as a
public arbitrary retype/retag operation. Slot publication stores that exact target
Access after the usual ownership acquisition; field/capture acquisition recovers it.
All metadata membership checks precede pointer dereference. Static registered rows
and checked emitter/IR proofs are complementary trust components, not C sandboxing.

## Appendix C — source proof inventory and closed-view capture conversion (normative)

This is explicit source admission/lowering, not a new core cast or a hidden
specialization. It applies to ordinary monomorphic lambdas AND existing compiler-
created lazy primitive/conditional/case/factory thunks/callback carriers. Scheme
values still cannot be captured or passed as term arguments.

For each carrier's actual checked source subtree, collect lexical free Scheme uses
transitively through nested ordinary lambdas/thunks, with exact original binder IDs
and occurrence paths. Respect every term binder/shadowing boundary and stop at a
new generalize boundary. Do not infer free-variable identity from display names.
Every such occurrence must be a recognized COMPLETE checked instantiation at an
ordered CLOSED Int/Bool vector. Check its full proof separately, even if another
occurrence has the same resulting vector. Bare/open/partial/unknown/malformed uses
reject; do not silently convert only the convenient subset.

Key a captured view by (actual Scheme-binding ID, FULL ordered vector), including
dead parameters. Repeated same-vector occurrences share one view capture per carrier;
different vectors use distinct ordinary capture owners/edges of the SAME shared RHS
node, not a cloned RHS or per-type memo. No key by merely resolved result type:
[Int,Int], dead parameters and noninjective substitutions must remain distinguishable.

At carrier creation where the Scheme binding is available, emit ordinary retain
then nondemanding instantiate for each required pair; publish its monomorphic view
as an ordinary owning capture with the existing support relation proof, then release
temporary owners. The extra ordinary captures/retains are measured implementation
work, not falsely charged as zero-cost TypeApp. Instantiate itself still changes
only the one handle's Access, no RC/node allocation/Force. Lazy branch bodies and
function bodies are not evaluated. Whole-branch checking is not weakened.

Within that carrier, each original proof occurrence reads/retains the corresponding
captured MONO view. It does not pretend the capture is a Scheme or instantiate it a
second time. Existing source-to-code mapping must bind occurrence proof -> exact
binding/vector -> capture name -> IR Access/use row. Multiple proofs may deduplicate
one capture only AFTER each is independently validated. The term lambda/application/
let skeleton and raw binder associations remain unchanged by closure conversion;
only erased type evidence placement/capture schema changes. Original/normalized
source evidence and independent erased projection remain preserved.

Nested carriers thread the available pair->monomorphic-view environment. A nested
carrier takes an ordinary retained owner of the outer saved view, rather than
reconstructing a Scheme, inventing another vector or hoisting a definition out of
scope. Schemes introduced inside a monomorphic body become available only after
that exact introduction. Never hoist across a generalize boundary: a generic
definition referring to an outside Scheme/value is still an external-capture
rejection, even if its occurrence can be instantiated at a closed vector.

The conversion must be used by every existing lazy carrier constructor (primitive
thunks, conditional/case outer thunks, each case arm/factory callback and lambdas),
or that source form explicitly rejects before native compilation. No silent fallback
to the old free_vars-by-term-binder capture map when it would carry Scheme values.
Initial source qualification remains coarse-owned; core loan-view controls are
separate and do not imply a new generic source borrow-mode qualification.

Finite controls must include one ordinary carrier with both Int and Bool occurrences,
repeated same vector (one capture per pair), a nested carrier, and a bad proof/dead-
parameter omission in a lazily unselected body. They may share a small registered
fixture/control family rather than multiply expensive original module runs. Record
exact source/proof/capture maps and owning-edge IDs; final scalar equality alone is
not sufficient. A first actual SharedPoly result42 does not alone qualify every
carrier variant; unexecuted carrier forms remain source-review coverage only until
an explicitly bounded test/acceptance states otherwise.

## Appendix D — coherent v8 callable representation and base-proof limits (normative)

The v8 equality policy is uniform, not conditional on `^` syntax, physical origin,
or whether an earlier consumer happened to accept a structural view. If concrete
closures @A and @B have the SAME recursively complete arrow contract, either can
pass through h expecting ^Arrow and then k expecting @A. The actual node retains
@B physical representation; Rep authenticates @B against that node's own immutable
Site/CodeTyping. Comparing to k's nominal pointer would be the rejected hybrid rule.

If @A requires argument identity and @B/Generic/Instance supplies unknown, full
contract equality fails. The caller may not acquire identity/group facts and no
runtime callback is entered. Identical domain/result types or payload sizes do not
repair that failure. Exact protocol/capture/resource premises are checked separately.
No argument-identity guarantee is inferred from a scheme or chosen [Int,Int] vector.

Add an explicit derived `ShapeTyping(shape pointer, canonical Type)` table. Native
validates exact scalar/nominal identity and Repeat/Once kind against this mapping.
RtShape's old domain/result pointers alone do not encode result_identity: a FUNCTION
Site/CodeTyping must additionally bind its full arrow contract to the actual Code's
protocol/result_identity_argument flag. Thunk/application result obligations and
all edge Access rows carry the same full type contract through Force. Every new
physical representation row is derived from this mapping or from the exact scoped
RT_OPEN Type; no row can grant a stronger callable contract than the checked body.
Native validation checks descriptor/code association; the IR checker + checked emitter
remain responsible for the body proof, not a self-asserted native function pointer.

The new B native/emitter takes IR8 only and creates all required typing/site tables,
including for fully concrete programs. Old v7 inputs must either remain on the frozen
A backend or be explicitly transformed/rechecked into v8 before B generation. There
is NO ABI-compatible fallback that links old C or dispatches a hidden old runtime.
Pure concrete source regression coverage is newly qualified after this re-emission;
no full old matrix/acceptance inheritance is asserted. Recursive callable signature
cycles that cannot normalize into the bounded type DAG reject; recursive nominal
DATA/SUM remains atomic and does not require unfolding the type graph.

Fresh latest-PR25 integrated-A extraction is mandatory before B source work: inspect
actual complete checked term, resolver/binder association, root scheme/proofs and
term erasure. Historical numeric IDs/counts/outer application are regression stress
evidence only. If the fresh producer yields a ready closure at the RHS, seal THAT
existing closure without adding an application; if it yields a pending application,
seal THAT existing cursor without forcing/wrapping it. Unknown new proof/term forms
reject or require a new reviewed contract, not an old-shape recognizer or fabrication.

This core contract does not invent the later compiler export/transport wire schema.
Before producer/bridge semantic edits, the source owner freezes a matching exact
source-evidence contract on the integrated base: all lexical proof occurrences,
scoped-formal/binder map, complete declarations, erasure/sharing identity, and every
closed-view capture movement. Core design ACK is not source admission/acceptance.
