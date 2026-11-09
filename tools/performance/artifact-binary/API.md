# Bootstrap.Bitstream v1 API

`Value = VInt Int | VBits Int | VText String | VNode Int ([] Value)`.
MLF `Int` is signed Int64. `VBits` stores all 64 bits, including negative
bit patterns and distinct NaN payloads; use `doubleToBits`/`doubleFromBits`.

`Limits = Limits Int Int Int Int Int Int Int Int` fields, in order:
maxBytes, maxSymbols, maxSymbolBytes, maxTotalSymbolBytes, maxNodes,
maxEdges, maxDepth, maxExpandedWork. `defaultLimits` is exported.

`encode :: Limits -> Int -> [] Value -> IO (Either String ByteArray)`
`decode :: Limits -> Int -> ByteArray -> IO (Either String ([] Value))`

Additive shared-graph reader (same wire bytes and validation):

`Graph` is opaque. `GraphNode = GInt Int | GBits Int | GText String |
GNode Int ([] Int)` exposes child IDs without recursively expanding values.

`decodeGraph :: Limits -> Int -> ByteArray -> IO (Either String Graph)`
`graphRoots :: Graph -> [] Int`
`lookupGraphNode :: Graph -> Int -> Either String GraphNode`

IDs are the validated first-use postorder table indices. Typed adapters
must memoize by (expected decode shape, node ID), not only by node ID, to
retain physical raw-AST/type sharing without accepting a node at the wrong
schema shape. This Graph is raw syntax, never checked typing evidence.
All previous exported Value API helpers remain exported; the new Graph
constructor and unchecked internal graph helpers are not exported.

The second argument is the nonnegative schema ID (at most 2147483647),
which decode matches exactly. VNode tags have the same numeric range;
the upper closed schema must validate tags, arities and field types.
Roots are ordered. No source-text pretty printing forms a binary payload.
Only Primitive, Types, Std, Map and IntMap are imported by the codec.

The existing ByteArray API is mutable and IO-only. Encode constructs an
exact-size privately owned buffer and never mutates it after return; callers
must not mutate an encoded blob or an input during decode. No unsafe freezing
or additional primitive is assumed. Raw file IO uses the bounded byte-file primitives.

Wire v1 has an 80-byte fixed little-endian header, strict canonical UTF-8
symbols, a two-bit-kind node stream and width-packed node references.
Nodes are first-use postorder interned by complete shallow-key comparison;
symbols are first-use interned. Child indices must be smaller than parent
indices. Integers use canonical unsigned/zigzag varints, raw bits use 64 bits.
Explicit section offsets/counts/lengths and canonical bit widths are checked;
sections are contiguous, padding is zero and trailing bytes are rejected.
CRC32 is corruption detection, NOT authentication. Cryptographic SHA256
content addressing remains the artifact layer's responsibility (using the
byteArrayDigest primitive on the same immutable read snapshot).

Decode enforces configured caps before table allocation, UTF-8 expansion,
edge traversal or root expansion. It checks graph depth and a saturating
expanded-work recurrence (including symbol bytes) to reject DAG bombs before
exposing roots to the typed adapter. The independent reference and GHC/native corpus controls exercise this format;
qualification of one platform does not qualify every backend and platform.
