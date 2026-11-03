# MLFBIN wire version 1

This is a binary bitstream, not an encoding of the old artifact text.
All byte positions below are absolute. Fixed header words are unsigned
32-bit little-endian. All payload bits are LSB-first, including multibyte
unsigned quantities. No alignment is inserted inside the node stream.

## Header: exactly 80 bytes

| Offset | Bytes | Meaning |
|---:|---:|---|
| 0 | 8 | magic ASCII `MLFBIN\r\n` |
| 8 | 4 | version = 1 |
| 12 | 4 | mandatory flags = 0; any other value rejected |
| 16 | 4 | schema ID, exact match to caller's expected ID |
| 20 | 4 | header size = 80 |
| 24 | 4 | total file byte length, exact including header |
| 28 | 4 | symbol count |
| 32 | 4 | symbol offset = 80 |
| 36 | 4 | symbol byte length |
| 40 | 4 | node count |
| 44 | 4 | node offset = symbol offset + symbol byte length |
| 48 | 4 | node byte length |
| 52 | 4 | total child-edge count, excluding root references |
| 56 | 4 | root count |
| 60 | 4 | root offset = node offset + node byte length |
| 64 | 4 | root byte length |
| 68 | 4 | node reference width |
| 72 | 4 | symbol reference width |
| 76 | 4 | CRC32/ISO-HDLC |

CRC is the standard reflected CRC32 polynomial `0xedb88320`, initial
`0xffffffff`, final XOR `0xffffffff`. It covers the entire file, treating
bytes 76..79 as zero. CRC is corruption detection, **not authentication**.
SHA256 remains the artifact-layer content address; the storage
byteArrayDigest primitive hashes the same raw read snapshot, not this CRC.

`width(count) = max(1, ceil(log2(count)))`, with width(0)=width(1)=1.
Both widths must be exactly canonical. Sections are contiguous, with no
overlap, gaps, or trailing bytes. Total = root offset + root byte length.
Node and root sections are individually padded with zero bits to the next
byte; a whole extra padding byte is forbidden.

## Canonical unsigned and signed varints

An unsigned varint consists of 8-bit groups: low seven bits are payload;
bit seven signals another group. Groups are least significant first and
may start at any bit position in the node stream. There are at most ten
groups. The tenth has at most one payload bit and cannot continue. The
final payload must be nonzero except for the one-group zero encoding.
All 64 bits are representable; values above signed Int64 max retain their
two's-complement bit pattern in MLF Int. Counts/tags/lengths separately
reject a negative Int representation and quantities above their limit.

Signed Int64 uses zigzag: `(n << 1) XOR (n >> 63)` with arithmetic final
right shift. Decoding is `(u >>> 1) XOR -(u & 1)`. MinInt64 and MaxInt64
are losslessly representable; no absolute value or signed negation of
MinInt64 is used.

## Symbol section

For each symbol in table order: unsigned canonical varint UTF-8 byte
length followed by exactly that many UTF-8 bytes. Empty symbol is valid.
UTF-8 must encode Unicode scalars canonically: no overlong forms, surrogate
code points, lone continuations, truncation, or values above U+10FFFF.
NUL is valid. Symbols are unique by complete string equality, numbered
from zero in first-use order. A text node using each newly encountered
symbol must use the next sequential symbol ID. Every symbol must be used.

## Node section

Nodes are numbered from zero. Each begins with an unsigned two-bit kind:

* 0: VInt; canonical unsigned varint zigzag Int64.
* 1: VBits; exactly 64 raw bits, preserving NaN payloads and signed zero.
* 2: VText; symbol ID in exactly symbol-reference-width bits.
* 3: VNode; unsigned canonical varint constructor tag, then unsigned
  canonical varint child count, then that many node IDs, each in exactly
  node-reference-width bits.

Constructor tags are 0..2147483647. The caller's closed typed schema
validates allowed tags, arities and field types. Full names, metadata and
types are represented by that schema, not reconstructed from a pretty
string by this layer.

Every child ID must be strictly smaller than its parent ID. VInt, VBits,
VText and VNode are distinct keys. Duplicate nodes with equal complete
shallow keys are rejected; VNode keys are tag plus ordered child IDs.
There is no hash-only admission. Symbols and nodes are deterministically
first-use interned by the encoder, nodes in postorder.

## Root section and canonical graph

Each ordered root is a node ID in exactly node-reference-width bits.
Root byte length is exactly ceil(root count * width / 8). Zero roots are
valid only with no nodes/symbols; all table entries must be reachable.
Walk roots in order; recursively walk ordered children, skipping already
visited nodes. Each first postorder visit must encounter the next node ID
starting at zero. This rejects reordered or unused table entries without
re-encoding or keeping a second file-sized buffer.

## Resource validation and APIs

`Limits bytes symbols singleSymbolBytes totalSymbolBytes nodes edges depth
expandedWork` is explicit. Defaults: 256MiB, 1,048,576, 16MiB, 128MiB,
4,194,304, 16,777,216, 16,384, 67,108,864 respectively. Roots are also
bounded by the edge limit. All integer caps are at most 2147483647;
depth is 1..65536, byte cap >=80, and single <= total <= byte cap.

Expanded work per node is 1 for Int/Bits, 1+UTF-8-byte-length for Text,
and 1+sum(child work) for VNode, counting repeated edges repeatedly.
Each node's work and depth are checked, and ordered root work is summed
and checked before roots are exposed. The sum uses subtraction-before-
addition checks, so arithmetic cannot overflow or admit a DAG bomb.
Decoding never recursively expands a shared subtree. Canonical walking
and encoder AST visiting use explicit task stacks.

Public APIs:

* `Value = VInt Int | VBits Int | VText String | VNode Int ([] Value)`
* `encode :: Limits -> Int -> [] Value -> IO (Either String ByteArray)`
* `decode :: Limits -> Int -> ByteArray -> IO (Either String ([] Value))`
* `Graph` is opaque; `GraphNode = GInt Int | GBits Int | GText String |
  GNode Int ([] Int)` exposes only scalar fields and ordered child IDs.
* `decodeGraph :: Limits -> Int -> ByteArray -> IO (Either String Graph)`
* `graphRoots :: Graph -> [] Int`
* `lookupGraphNode :: Graph -> Int -> Either String GraphNode`
* `magic :: String`
* `hasMagicPrefix :: String -> Bool` (exact full 8-byte ASCII prefix)
* `hasMagic :: ByteArray -> IO Bool`
* `strictUtf8 :: Int -> ByteArray -> IO (Either String String)` (bounded
  strict legacy decoding only after new-magic dispatch)

The second encode/decode argument is the artifact schema ID. Integration
allocates 1=context, 2=query, 3=interface, 4=object. IDs must be nonnegative
and <=2147483647; decode expects an exact match. Recognized binary magic
plus any decode error is terminal and must never fall back to legacy text.

The additive Graph reader reuses the exact validated postorder table and
root IDs. It performs the same checksum, framing, canonicality and resource
validation as decode, without changing a single wire byte. Value decoding
is now a projection of this validated graph. A typed adapter must memoize
by (expected decode shape, node ID) so shared types/ASTs are constructed
once per shape rather than expanding a small DAG into millions of equal
tree nodes. Graph is validated raw syntax, **not checked typing evidence**.

ByteArray has an existing mutable-only IO API. The encoder constructs one
exact-size private zero-filled buffer and never mutates it after returning.
The caller must not mutate it, or mutate a decode input concurrently.
No unsupported freeze primitive or textual byte serialization is used.

Status: authored implementation; compiler/runtime tests intentionally not
run until the parent opens the integrated verification gate.
