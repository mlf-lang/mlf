# Stage03: host-only static metadata closure

## Status and boundary

These are new isolated implementation sources. They have not been imported,
compiled, or tested during their preparation. The exact source, helper, fixture,
and execution plan still require independent preexecution review. This README
is not an execution receipt or an acceptance claim.

The governing Stage03 revision-3 plan has SHA256
`1c2568f62f006f6d5f756c0688ae783d01d209d1a9ed6279d96ad3b97b208c8f`.
The immutable core contract has SHA256
`0c54e24fe48deda73547e0dd3a7e9eb285ba0b36d5d938ee8c35a312d509ee83`.
The isolated source-copy/design ACK permits only these new host implementation
files. All 3,652 accepted Stage02 source files remain unchanged.

## Public API

Import explicitly from `resource_ir_v8.metadata`; package `__init__.py` stays
unchanged and declaration-only.

- `check_metadata(data)` accepts only an exact raw plain-JSON IR8 program.
- `loads_metadata(text)` uses the pinned raw parser, including duplicate-key,
  nonfinite, size, depth, and integer restrictions, then calls `check_metadata`.

Every invocation calls the unchanged Stage02 resource checker afresh. Its raw
canonical and derived strings are decoded only after a charged bounded lexical
prepass has reserved all new parsed container headers and memberships. There is
no caller-supplied ResourceCheck, DeclarationIndex, expected hash, producer-table,
source-map, emitter, model, or runtime admission route. Existing declaration and
resource exceptions keep their original layer/code/path unchanged.

The frozen, slotted, equality-disabled `MetadataClosure` contains exactly these
public data fields: canonical_json, ir_sha256, declaration_sha256,
resource_sha256, metadata_json, metadata_sha256, counts. Its private cached
immutable `_report` is built once; `report()` returns that same tuple. The
resource hash binds the fresh Stage02 derived artifact, separately from the raw
IR hash. A Python dataclass constructor is not an unforgeability mechanism.
Any later emitter must recheck raw IR and reproduce the closure.

## Derived tables

`metadata_types.py` builds the fresh flat integer type DAG, exact full callable
contracts, remaps, full environments, and required type resolutions. All legal
scoped roots, including unused callbacks, intermediate types and closed-looking
roots in a scheme, receive their lawful substitutions. Full vectors and exact
scheme identities survive even when result types coincide. The new target is
Repeat-only, including unused and nested arrow positions. Stage02's separate
Once behavior is unchanged.

`metadata_representations.py` derives physical descriptor plans, nominal fields,
ShapeTyping, representations, CodeExecution and lawful SiteExecution classes.
Legacy closed callable aliases remain physically distinct and retain their full
contract. Neutral scoped arrows use OPEN even when structurally closed; neutral
intrinsic scalars retain their exact scalar representation. A Generic projection
does not retag a node. Introduction sites are Generic-only; scoped callback sites
also permit Instance allocations. Context comes from actual raw paths and fresh
allocated provenance, never an SSA name or free-variable count.

`metadata_edges.py` derives slots, Access, identity/same-scheme projection
transport, exact Boundary predicates and complete Coverage. SUM slots contain
only the actual constructor variant's fields, while Family/NominalField retain
all variants and factory sites retain all arms. Opaque captures, parameters,
fields and Force cursors preserve their actual Access rather than guessed E0 or
a first type-compatible site.

Generic-projected and Instance function captures have distinct entry keys and
predicates. Generic THUNK execution follows its neutral principal environment,
including for a closed incoming request. Deferred THUNK, APPLICATION and
HOLE-origin INDIRECT rows retain each exact request Access separately from the
principal environment. Reverse-pending and memo-publish retain their distinct
validation/acquisition ordering predicates. These are static premises, not
executed native events.

The Access ledger is additive to unchanged operand ownership, loan/anchor,
ticket, readiness, linear discharge, support, and identity contracts. In
particular, an Access predicate does not authorize a loan where Force or an
ordinary owning source requires an owner. Key drops have no Node/Access
Boundary or instruction Coverage; their fresh Fact.kind remains a key.
Scheme value-owner drops do have release-actual rows without Mono erasure.

## Verification and mutation controls

The type helper performs a charged independent forward equation pass and a
complete fresh-source reconstruction. Public orchestration reconstructs the
representation/edge/coverage/inventory document from fresh raw and lower-stage
sources, then compares complete strict trees. Candidate rows do not provide
scope, expected key sets, physical associations, or coverage authority. This is
source-derived equation replay, not a claim that executing the same builder twice
constitutes an independent implementation or a correctness proof.

The private `metadata._verify_derived(raw, candidate_document)` exists solely for
honest derived-invariant mutation controls. It freshly checks raw IR, reconstructs
all expected tables, and returns None on equality. It never returns a successful
MetadataClosure or grants execution authority. Raw-program and private-derived-
invariant fixtures must be labeled separately.

Deterministic private mutation errors use path `metadata.<table>`:

- Type/remap/environment/contract/type-resolution tables:
  `metadata-type / TYPE_EQUATION`.
- Code/CodeExecution/Site/SiteExecution/Intro/Use tables:
  `metadata-origin / ORIGIN`.
- Shape/ShapeTyping/Representation/NominalField/Family/representation-resolution:
  `metadata-representation / REPRESENTATION`.
- Boundary or Coverage: `metadata-closure / COVERAGE`.
- Storage inventory: `metadata-closure / STORAGE_INVENTORY`.
- Slots, Access, Transport, counts, native status, and bindings:
  `metadata-closure / TABLE_EQUATION`.
- Unknown or missing document keys: `metadata / metadata-schema / SCHEMA`.

Earlier fresh raw/resource failures and immediately exhausted budgets take
precedence. Tree comparison distinguishes bool from integer, checks exact
fields/null domains, array order, and complete row sets, not merely plausible
individual rows. The private verifier is not a producer-table bypass API.

## Bounds, inventory, and report

The semantic row quota separately counts TypeResolution,
RepresentationResolution, Access, and every identity/projection Transport row,
with combined maximum 65,536. Host limits remain 262,144 serialized JSON records,
2,097,152 monotonic construction units, 16,777,216 examination units, and
33,554,432 streamed UTF-8 metadata bytes. Temporary verification copies still
consume host creation and work; they do not double-count prospective native rows.
Canonical serialization appends chunks of at most 4,096 bytes. Final JSON-object
census is distinct from creation work, and shared logical objects count at every
serialized occurrence.

The retained-record clarification is separately bound at SHA256
`dc4d864d3bdb6bf8e2cd7aadbe01f1dabf9d35fa51b80ede5432e524f95aef5a`.
Provisional builder objects consume creation/work; they are not claimed to stay
below the serialized record cap. The canonical root is reserved first, then
each structurally complete table/subtree is counted and atomically retained
before output attachment. No attached subtree is structurally mutated. The
counts.metadata_records scalar replacement changes no object occurrences;
independent census must equal the retained counter. Verifier copies cannot
change that counter. The lower-JSON bridge design is separately bound at SHA256
`a6b092063efcad1787bfdb63bf3960e1b463050d951d11f389a1f4341254f0c7`.

The exact prospective storage inventory contains all 20 native-oriented tables
and their membership registries, six physical descriptor arrays and registries,
every specified per-owner vector (including zero-length entries), the exact
string/path pool, and program/typed/digest headers. Host-only remaps, Boundaries,
Coverage, raw FactRefs, JSON snapshots and reports are not silently emitted.
A zero-count inventory entry denotes no actual storage object and no hidden
sentinel. Shapes and their physical descriptors are distinct prospective arrays.

The cached report status is `checked-static-metadata-only`. Row cardinalities
are `planned-native-row-cardinality`; native bytes remain `abi-unbound` with
measured_bytes null and actual_emitted_rows_verified false. All 27 guards are
reported in frozen order as not-present or derived-pending-runtime. The report's
fixed immutable graph and final checks are reserved before its counters freeze;
subsequent report calls perform no new lookup, copy, or accounting.

Pending gates always include actual native ABI/sizeof and the 4 MiB limit,
emitter/storage correspondence, dynamic origin/representation/edge guards,
model/native/lifecycle, source proof/lowering, single code emission, complete GC
replacement, and performance. JSON bytes are not native sizeof. No callback,
Force, allocation, compiler, model, or native graph is executed by this API.

Future integration must independently verify and absorb the separately reported
PR28 one-file CI repair at head prefix d54cd247. This isolated copy must not
overwrite it. That reported push does not establish green CI or readiness to
integrate this stage.

### Current SUM field boundary

The unchanged declaration gate permits intrinsic scalar or nominal-family SUM fields, not callable signatures such as @ClosedI. Callable DATA fields and external projected-callable captures into factory thunks are covered separately. The run01 callable-SUM positive was an invalid fixture premise and is retained as an exact lower FIELD_SHAPE negative; the corrected factory positive stores Int and captures the callable externally. This stage does not admit callable-valued SUM storage. Extending that lower declaration domain and validating its eventual strong edges remains separate work.
