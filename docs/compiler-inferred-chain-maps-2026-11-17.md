# Inferred chain: map workers and bounded query updates

This investigation retains no additional compiler change. The unsigned
monomorphic `inferred_chain` shape remains unaccepted under the original
[fixed GHC comparison](compiler-inferred-chain-2026-11-17.md): MLF/GHC OLS
slopes are 0.164411/0.158357 ms/function, and the endpoint slope and paired
OLS interval also fail. No unchanged-source formal cohort was rerun.

Evidence is under `.mlf-build/inferred-chain-map-construction-20261117`.
Authentication verifies the current ordinary producer and the preceding final
audit's 302 maintained-source and 2,827 evidence pins. Builds, controls, elapsed
screens, confirmation and memory runs are serialized. Earlier uncommitted work
and unrelated lifecycle files are preserved.

## Existing profile, newly attributed

Reanalysis of the six authenticated current-source profiles reconciles all own
ticks and allocation with their original totals. Map's N=1024-minus-N=0 growth
is 20.2 sampled ms and 87.176 MB allocated. These are diagnostic profile costs,
not a fresh elapsed experiment. Map allocation under several callers is:

| Caller / route | Additional allocated MB |
| --- | ---: |
| Bitstream symbol interning | 10.253 |
| QueryGraph.recordDigest / insertWith | 7.288 |
| LLVM.Optimize.copy / insertWith | 4.142 |
| CrateArtifact.linkOpenFragment / insertWith | 4.081 |
| Module.interface / insertWith | 3.950 |

Much of this work is incremental insertion, so the already retained bulk
`fromList` optimization does not remove it.

## Direct map workers

The private `map-workers` candidate specializes overwrite insertion instead of
passing a generic combining function, and returns default/required values or
membership directly instead of constructing and inspecting `Maybe`.
`lookup`, balancing, `fromList` and arbitrary `fromListWith` combinations are
unchanged. Full frozen tree shapes, newest equivalent key representatives,
comparison order and tested lazy-value/error behavior are preserved.

The first fixed screen uses one warmup and six alternating measured pairs per
size. Its promising large-case signal receives exactly one separately declared
confirmation: one warmup and twelve alternating measured pairs per size.
The two cohorts are not pooled. All numbers below are compiler-plus-Clang
subprocess sums, excluding the formal worker's launch overhead.

| Size | First screen before / after, s | Confirmation before / after, s |
| ---: | ---: | ---: |
| 0 | 0.269348 / 0.266721 | 0.268563 / 0.268345 |
| 256 | 0.325061 / 0.313461 | 0.305110 / 0.306784 |
| 1024 | 0.454221 / 0.444073 | 0.442924 / 0.442628 |

The first screen's N1024 compiler-only median falls from 0.316303 to
0.308120 s. The confirmation falls only from 0.304820 to 0.304393 s;
N256's compiler median rises slightly. The initial gain is not reproduced.
The candidate is rejected, without another confirmation or a formal GHC retry.

Controls pass 19,611 independent ordered-map cases, 16,745 union pairs,
3,936 frozen complete-tree/representative cases and 36 demand/error checks
across those three suites. The unchanged generated Prelude is explicitly
admitted by the candidate. Eight host-control actions pass. No interpreter or
native execution of the changed Map bodies is claimed for this rejected shadow.

## Bounded query updates

The independent `query-buffer32` candidate starts from the unchanged maintained
source, not from the direct-worker candidate. A query session holds a stable
map and a recent map with fewer than 32 distinct keys. On reaching 32 keys,
the recent map is merged on the left and cleared. Lookup checks recent values
before the base; deletion removes a key from both; materialization preserves
the newest complete node and sorted key order. With a fixed buffer bound,
lookup visits at most two balanced maps and retains O(log n) worst-case lookup.
This statement is about the data structure, not full-compiler complexity.

Four production callers use a session lookup method instead of materializing
the whole current map. All query keys, hashes, ordered read lists, authority
validation, payload checks, cycle/depth limits and publication remain intact.
The candidate changes the private Session current-index field, so its two
direct-constructor declaration fixtures are adapted explicitly. It is not
presented as a drop-in public constructor change or a maintained API.

One fixed screen has one warmup and six measured alternating pairs per size:

| Size | Before / after subprocess sum, s |
| ---: | ---: |
| 0 | 0.271820 / 0.272170 |
| 256 | 0.305234 / 0.305707 |
| 1024 | 0.457015 / 0.454946 |

At N1024 the compiler-only median changes from 0.314164 to 0.311675 s.
Small/middle combined medians rise. The approximately 2 ms large-case combined
gain and small allocation reduction do not justify retaining a second index
representation and its API changes. The fixed threshold is not swept or retuned.

Ten host-control actions pass. Independent Data.Map comparison checks 41,888
complete dictionary states across 104 update/delete/overwrite sequences,
including 31/32/33 and 63/64/65-key boundaries, seeded bases, Unicode keys,
long keys and four lazy-value checks. Existing declaration/cache tests pass
slot drift, candidate changes, current authority/read-list guards and direct
finalization. Existing query-index tests pass depth/work boundaries, cold/warm
publication, failpoints and retained payload/generation hashes. These are
host controls; no portable native compiler qualification is claimed.

## Separate memory and output checks

Each candidate has three separate alternating RTS pairs at N=0/1024 with
`-s -F4`. N1024 median values below are bytes:

| Candidate | Allocated before / after | Maximum live heap before / after | Process RSS before / after |
| --- | ---: | ---: | ---: |
| map-workers | 862,886,696 / 860,643,208 | 11,233,248 / 11,134,560 | 61,472,768 / 61,505,536 |
| query-buffer32 | 862,888,464 / 860,758,248 | 11,233,248 / 11,269,848 | 61,685,760 / 61,718,528 |

Allocation falls by 2,243,488 bytes (0.26%) and 2,130,216 bytes (0.25%),
respectively. These are cumulative allocation savings, not RSS savings.
They do not establish the requested growth advantage.

All 162 screen/confirmation compiles preserve exact interface, object and LLVM
bytes, with 486 exact native arithmetic results. All 24 separate memory
compiles preserve the same bytes. No failed run or sample is removed.

Both candidates remain private experiments. There is no additional maintained
compiler, builtin, ABI, wire-format or lock change, and no acceptance commit
or push. Native self-bootstrap, installed CLI and the previously recorded
native-codec/QuerySnapshotProbe gaps remain outside qualification. Finite-range
fitted exponents remain distinct from asymptotic proofs.

The next investigation should target larger representation costs, such as
numeric query columns currently expanded into generic value nodes and interned
again. That is an untested design direction, not an established optimization.
It must retain complete typed decoding, resource admission and cache semantics.
