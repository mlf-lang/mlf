# Compact declaration identities

Crate definition names use the versioned `c1` component encoding. This changes
storage spelling, not declaration identity: the complete crate identity and
`Separate.entityEncoding` (module, spelling, role and parent) remain present.
Nothing is replaced by a hash, ordinal or display name.

An ASCII letter or digit is copied, except lowercase `z`, which becomes `zz`.
Every other Unicode scalar becomes `z`, its minimal lowercase hexadecimal code,
and a terminating `z`. For example, `:` becomes `z3az`, `_` becomes `z5fz`, NUL
becomes `z0z`, and `😀` becomes `z1f600z`. There is no Unicode normalization or
case folding. The scanner emits a fragment after at most 256 consecutive ASCII
characters, bounding the scan before the native concatenation loop resumes. This
does not change the encoded bytes. A component contains only ASCII letters and digits, so underscore
unambiguously separates components. The escape grammar is injective: after `z`,
either the next `z` denotes a literal `z`, or hexadecimal digits end at `z`.

Ordinary generated names are:

- Terms: `module_c1_<crate-component>_<entity-component>`.
- Types and constructors: `Module_c1_<crate-component>_<entity-component>`.

The `c1` prefix cannot collide with the former decimal-scalar prefix. Managed
builtins, canonical Prelude names, the legacy standalone-unit name function and
instance dictionary names retain their existing rules. The crate resolver,
export/entry validation and envelope metadata projection use the same component
encoder. Each encoded scalar occupies at most eight ASCII bytes; metadata
reservation includes the ten-character versioned prefix and one separator.

## Group owners

Current writers emit
`pack(["MLF-OPEN-GROUP-3", crate, pack(member-records)])`. `pack` uses Unicode
scalar length framing. Sort complete names first. A name beginning exactly with
`module_c1_ + encode(crate) + _` uses `pack(["value", suffix])`; the corresponding
capitalized prefix uses `pack(["type", suffix])`. All other names use
`pack(["raw", complete-name])`. The complete crate and entity components remain
recoverable. Membership, duplicates, namespace and original canonical ordering
are preserved.

Readers also recognize the exact version-2 decimal-prefix owner, version-1 full
owner and legacy query owner for the same complete member inventory. This owner
compatibility does not make old declaration names interchangeable with `c1`
names. Dependencies compiled with the old definition-name convention must be
rebuilt. The compiler rejects their inconsistent exports; it does not silently
reinterpret their binders. Regenerate the builtin data and package lock when
changing the compiler sources.

The MLFBIN layout, typed syntax tags and primitive codes are unchanged. The name
and owner markers version these two representations independently. Source and
producer hashes still authenticate the actual builtin and cache inputs.

## Validation

`tools/shared/fixtures/OwnerEncodingControls.hs` checks the actual host APIs
against an independent hexadecimal/scalar oracle, including ASCII, Unicode
boundaries, NUL, literal escape-looking strings, namespace/parent identity,
component separation, long inputs, rendering bounds and old/new owner forms.
It runs in the signed-chain regression path.

`tools/shared/test_compact_names.py` additionally isolates the exact production
component-function bodies, records their source hash and runs them through the
interpreter and generated native code. The extraction changes only the fixture
module and IO driver; expected bytes come from an independent Python oracle.
This tests the portable codec algorithm, not a native compiler self-bootstrap.

The scale study compares original interface/object pairs using the independent
wire and typed readers. After reversible name expansion it compares complete
bodies, identities, types, scope inventories and interface semantics. The actual
reader independently rechecks content stamps with semantic audit enabled, and
its LLVM output must match the fused compiler. See
[the signed-chain study](compiler-dependency-chain-2026-11-15.md) for measured
results and the qualification boundary.
