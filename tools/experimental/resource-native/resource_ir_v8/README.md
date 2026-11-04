# IR8 declaration kernel

For the current additive experiment, its other opt-in layers and the explicit
host-only test entrypoint, see [README_STAGE04.md](README_STAGE04.md). The default
resource IR v7 source/runtime path remains separate.

The declaration entrypoints described below check **declarations only**. It does not import `resource_ir`, accept
an executable program, construct `CheckedProgram`, expose a v8 dispatcher, execute
or clone bodies, lower source proofs, emit native code, or modify the frozen v7
mixed-use rejection. Its result does not establish ownership, all-path resource
validity, allocation sites, Access, ABI safety, source acceptance, or performance.

## Exact interface

`loads_declarations(text)` accepts a plain string containing duplicate-key-free
JSON. `check_declarations(data)` accepts the same exact six-map object using plain
Python JSON values. Both return a frozen, slotted `DeclarationIndex` with no
caller-owned containers, mutable records, persistent lookup caches, or builder
state. Invalid input raises `DeclarationError(path, code, message)`.

The exact top-level maps are `layouts`, `families`, `signatures`, `types`,
`schemes`, and `instantiations`. All may be empty. No version, functions, codes,
entry, executable body, producer-asserted authority, or extra key is accepted.
Names are nonempty, NUL-free UTF-8 strings. Every user-declared name reserves
the leading `^` namespace, including type/scheme/use IDs, variant names, and DATA
field names (core Appendix B3). Physical DATA/signature/family names additionally
reserve leading `@`, `#`, and `%`. References such as `^T` remain legal and are
distinguished from names. Other declaration IDs retain arbitrary spelling and
are resolved using exact strings, not native symbols. A type ID spelled `#x`
is addressed as `^#x`, not as physical `#x`.

Canonical immutable types are:

- `('closed', physical_atom)` with exact scalar/DATA/SUM identity;
- `('rigid', scheme_name, parameter_index)`;
- `('arrow', argument_tuple, result_tuple, protocol, result_identity)`.

A closed declaration names only an intrinsic, registered DATA layout, or nominal
family. It cannot name `@signature` or `^type`. Aliases mean duplicate declared IDs
with the same normalized structure, not an additional alias tag. Signature
endpoints and DATA fields may use physical references or `^type`. Closed callable
references expand to their full recursive contract. Recursive nominal fields stay
atomic; recursive callable/type references reject.

`index.resolve(reference, scope=None)` accepts a physical DATA name,
`@signature`, `%family`, intrinsic `#i64`/`#bool`, or `^type`. It verifies the
explicit scheme scope before returning a canonical tuple. `index.same(left,
right, scope=None)` compares canonical IDs, never signature names or physical
sizes. `index.instantiated(use_name)` returns `(scheme, full_ordered_atom_tuple,
substituted_body_tuple)`. Complete vectors retain dead parameters. Type arguments
are declared IDs, never implicitly interpreted physical references.

Generic scheme bodies must be arrows made from Int, Bool, their own rigids, and
recursively repeat/unknown arrows. Every open type/signature also excludes nominal atoms and enforces the
recursive repeat/unknown contract, including otherwise-unused declarations.
Resolving any type in an explicit generic scope enforces both restrictions,
even when the queried legacy arrow is closed. Concrete closed legacy Once or
argument-identity types remain distinguishable; no contract forgetting or body
identity proof is supplied. Every argument-identity arrow must have exactly equal
canonical domain and result. A physical DATA field is fully closed and cannot
carry a root Once callable. Nominal family fields retain scalar-or-family only,
with the complete ordered variant inventory and all positional fields.

## Returned records and ordering

- `canonical_json`: exact admitted declaration data serialized with sorted object
  keys, no whitespace, and UTF-8 (`ensure_ascii=False`). It is not a rewritten or
  inferred declaration object. `sha256` hashes those UTF-8 bytes.
- `type_rows`: unique immutable type tuples sorted by logical depth, then the
  canonical JSON lexicographic order of their full structural tuples. The zero-
  based position is the canonical type ID. Intrinsics always have rows, even for
  the empty declaration set. Neutral rigids for all parameters and all derived
  substitution results count toward this same table.
- `schemes`: sorted `(name, keyed_record)` pairs. Record keys are `parameters`,
  `body`, and `body_type_id`.
- `instantiations`: sorted `(name, keyed_record)` pairs. Record keys are `scheme`,
  `arguments`, `body`, and `body_type_id`.
- `environments`: keyed records with `id` (`E0`, `E1`, ...), `scheme`, `mode`,
  `arguments`, and `argument_type_ids`. `E0` is concrete with an empty vector.
  Each scheme in name order has its complete neutral vector, then its distinct
  complete closed vectors sorted by canonical atom IDs. Identical body results
  do not merge vectors. Repeated uses of one vector share one environment.
- `report()`: an immutable keyed tuple labeled `declarations-only`, carrying the
  snapshot hash, counts, and explicit no-body/resource/native/source statement.

A keyed record is a tuple of `(key, value)` pairs, not a dictionary. Private query
indexes are also immutable tuples. `repr(index)` is count/hash-only. This is normal
Python immutability, not a sandbox against `object.__setattr__` or a forged manually
constructed data class. No executable consumer trusts this declaration result.

## Failure and work bounds

Admission caps serialized input at 4 MiB UTF-8 before JSON decoding. Direct Python
input is deep-copied with exact canonical-byte charging; unsupported values,
nonfinite/floating values, surrogate strings, active-path cycles and malformed
containers reject. An eight-container syntactic guard exceeds every legal schema
nesting and is checked before decoding/traversal. This is distinct from logical
type depth. No map/array may exceed 4096 entries during snapshot admission; semantic
maps/arrays have the tighter bounds below. Small count/index integers reject
booleans, and oversized Python integers reject before decimal conversion.

Bounds: declared type IDs 4096, canonical declared/derived types 4096, logical
depth 32 (atoms have depth 1), schemes 16, parameters 1..8, uses 1024, and total
concrete+neutral+distinct-closed environments 1024. Physical layouts and signatures
are each capped at 4096, families at 64, variants at 1..64, fields per family
variant at 32. DATA field dictionaries have the general 4096-map guard.

All normalization work is on an interned DAG with integer child IDs. Iterative
cycle checking has a depth bound. Interning/hash/equality never hashes recursive
tuples; ordering follows only the first unequal interned child and skips equal
subgraphs, at most 32 levels. Substitution visits each reachable canonical node
once per distinct environment (at most 4096 * 1024 node visits) and enforces the
4096 derived-node cap before adding a row. Returned arrow tuples share child
objects, so constructing rows takes linear space. External consumers must likewise
use DAG-aware traversal rather than recursively serializing these shared tuples;
the original canonical input JSON remains safely bounded.

The 4 MiB limit here is a schema-input guard, **not** the later exact emitted native
static `sizeof` accounting. Static type environments here grant no representation,
site, origin, capsule, activation, Access, transport, or body authority. Those
resource/runtime/source obligations remain separate later stages.

## Validation status

Written for independently reviewed Stage01 host-only validation. No import,
`py_compile`, test, compiler, model, native, source, or performance run is implied
by these files. `STATIC_REJECTION_EXPECTATIONS.json` records static guard-derived
expected failure classes for the parent's finite fixtures; it is not test output.
