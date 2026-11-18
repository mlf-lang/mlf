# Inferred dependency chain: hashing and framing diagnostics, 2026-11-18

No compiler change is retained from this investigation. The current family is
still `inferred_chain`, without explicit signatures. The authenticated producer
remains `.mlf-build/inferred-chain-metadata-structure-20261117/producer-candidate`.
The [preceding current-source cohort](compiler-inferred-chain-metadata-2026-11-17.md)
remains authoritative: five of six original checks pass; the confidence interval
for the fitted exponent difference still includes zero. No unchanged-source GHC
acceptance cohort was repeated, and this shape has not been accepted or committed.

Evidence is under `.mlf-build/inferred-chain-string-hash-20261118`. All three
implementations were private source shadows; the tracked compiler, primitive
ABI, builtin bytes/identity, lockfile, native runtime and persisted formats were
unchanged by this task. Preexisting edits are preserved.

## Fresh attribution

Six separate profiles (two each at N=0/256/1024) use the current source and
preserve exact interface, object and LLVM bytes. At N1024 minus N0, inclusive
`preparedValueCached` costs about 11.25 ms / 43.057 MB; its nested
`preparedSyntax` costs about 4.30 ms / 18.220 MB. `hashRebuiltValue` costs about
5.80 ms / 15.652 MB, including 0.40 ms / 6.281 MB in the temporary byte-array
constructor and 2.25 ms / 0.860 MB in the digest wrapper. These are overlapping
profile scopes, not additive complete-build measurements.

## Private implementations and controls

`immutable-text` borrows immutable UTF-8 for synchronous SHA-256, removing the
intermediate mutable byte array and the snapshot needed by the public mutable
digest operation. Only two immutable-text call sites change. The public mutable
operation retains its snapshot behavior. This diagnostic has no portable
primitive registration, opcode or native qualification; it must not be adopted
as a new compiler primitive on the strength of host-only tests.

It passes 137 independent Python hashlib vectors, including Unicode, NUL,
SHA-block boundaries, sliced and reused strings and scalar-length-framed fields;
deferred IO, failure/effect ordering, mutable-array mutation, concurrent hashes
and GC controls also pass. The controls are repeated with a threaded two-capability
runtime. Fixtures use coherent `ghc --make` source closures.

`direct-fields` preserves the existing framing preflight and prefix cache, then
copies the reversed validated chunks backwards into one exactly sized Text
array. This removes the list reversal and the repeated length traversal. Its
first implementation unexpectedly adds about 39.9 MB allocated at N1024.
Generated Core shows that under the unchanged `-fno-state-hack` option,
`copyBackwards` inspects each list cell before returning a state lambda and
allocates a deferred recursive action. A planned confirmation was canceled
before execution when this memory regression became available.

`saturated-fields` supplies the state token explicitly. Its Core is a saturated
recursive loop with `copyByteArray#`, without the deferred action chain. It saves
about 13.3 MB allocated at N1024, but maximum live heap increases about 0.7% and
GC copies about 1.19 MB more. The compiler-only screen gain is just 0.352 ms.

Each framing variant passes the existing 241 independent framing cases in three
paths and demand controls, 2,236 prefix cases in four paths, 65 nested/shared
cases plus demand/bounds controls, and 31 sliced/large-list/nested cases plus
32 concurrent GC cases. Checks cover scalar lengths, UTF-8 bytes, cached scalar
indexing, Unicode boundary values and empty fields. All control builds use Core
lint and the same pedantic-bottom and state-hack settings as the producer.

## Diagnostic timing

Screens use one warmup plus six alternating measured pairs at each size; the
immutable-text confirmation is a separate fixed twelve-pair cohort. Each pair
uses fresh output/query directories. All 204 compiler-plus-Clang runs reproduce
the reference interface/object/LLVM bytes and pass 612 generated-program output
checks. These are subprocess diagnostics, not the formal complete-worker GHC
endpoint. Warmups remain in the receipts but are excluded from the medians.

Compiler-only medians in milliseconds, before / candidate:

| Variant and cohort | N=0 | N=256 | N=1024 |
| --- | ---: | ---: | ---: |
| immutable-text screen | 127.952 / 133.464 | 168.513 / 168.340 | 305.673 / 304.900 |
| immutable-text confirmation | 132.458 / 132.856 | 170.581 / 171.486 | 304.684 / 305.007 |
| direct-fields screen | 129.224 / 127.944 | 162.606 / 163.972 | 289.679 / 287.439 |
| saturated-fields screen | 126.710 / 125.943 | 158.896 / 158.896 | 279.016 / 278.664 |

The immutable-text screen's roughly 7 ms total improvement at N1024 contains
only 0.773 ms of compiler improvement. Its independent confirmation instead
shows a 0.323 ms compiler regression. The saturated-fields screen's roughly
2.8 ms total improvement contains only 0.352 ms of compiler improvement. Do not
attribute the Clang differences to these compiler changes or pool these cohorts.

## Separate memory measurements

Three alternating instrumented pairs at N0 and N1024 per variant preserve the
same artifacts and LLVM. Their RTS-instrumented times are excluded from timing
claims. The following are medians at N1024, in bytes, before / candidate:

| Variant | Total allocated | Maximum live heap | Individual peak RSS |
| --- | ---: | ---: | ---: |
| immutable-text | 848,842,592 / 845,489,112 (-0.395%) | 10,609,608 / 10,586,336 (-0.219%) | 60,833,792 / 60,735,488 (-0.162%) |
| direct-fields | 848,841,624 / 888,764,136 (+4.703%) | 10,609,600 / 10,680,840 (+0.671%) | 60,604,416 / 60,424,192 (-0.297%) |
| saturated-fields | 848,844,464 / 835,548,152 (-1.566%) | 10,609,624 / 10,680,760 (+0.670%) | 60,588,032 / 60,440,576 (-0.243%) |

Small RSS changes in these individual measurements do not establish a reliable
process-memory benefit. Lower cumulative allocation alone is not the same as
lower peak live memory.

## Decision and next investigation

Reject the immutable-text interface expansion: its independent timing result
does not justify a new cross-backend primitive for a 0.4% allocation reduction.
Reject the first direct builder because of the allocation regression. Reject
the saturated builder because its small allocation saving brings neither a
useful observed compiler improvement nor a peak-live improvement, while adding
handwritten low-level copy code. Do not repeat these unchanged candidates.

There is no new root implementation to qualify through a full regression suite
or a formal GHC cohort. Existing native compiler self-bootstrap and installed
CLI qualification gaps remain unchanged. Finite fitted exponents are empirical
scaling diagnostics, not proofs of asymptotic complexity.

Continue on this same shape. The next investigation should extend diagnostic
sizes beyond N1024 to reveal larger growth costs, while preserving the original
acceptance range, model, confidence gates and current formal cohort. Do not
substitute or pool a larger diagnostic cohort into acceptance evidence.

## Evidence receipts

- `profile-current/receipt.json`: `5bfedcc06734c515b33ca1f5186c1b3a71ed6f8f703f826259ed5ac95fd8f1b3`
- `analysis.json`: `3bc5cd4a3454feeb4709398f9d69c654299118f8181faecabbbed64fb5f200cf`
- `attribution.json`: `378c0fef2dadca3eab13a61950c783ee5eab58649585cfe77ba778c00d86f419`
- `immutable-text/receipt.json`: `bc8363ded1cd5dd8056337e2ce7eef7af4031754f825bbe70fb73dc6f89f5a0b`
- `direct-fields/receipt.json`: `75b471ed4ce7fbb853f99015d5083fbad90ef715416731aa4770f2c5dcad684e`
- `saturated-fields/receipt.json`: `b12109e6eb27ab76c1b77e458b35cb46f7768a17430d08989f0ffee1696dad4a`
- `immutable-text-controls/receipt.json`: `359f787e32f0e64ed220931ae59cbee08109db983f3e7e1ffda5faf1343a7794`
- `immutable-text-screen/receipt.json`: `33b50a3a93ae36aa56af385444f2db54f91fc9dbff65a8adbaa0806fdc8af71c`
- `immutable-text-memory/receipt.json`: `f0907dc60bba65a51c1c56e72b5b1d8805dd6360ff81fc7806e0816e7d95a0ac`
- `direct-fields-controls/receipt.json`: `9123ae0f197707c0e619f554789184c424165cc2af37e3652fe11890d9108c48`
- `direct-fields-screen/receipt.json`: `e89e722888fe5020fc4c4aba65dbef7aa8285824264a3347af5a50efce37cf89`
- `direct-fields-memory/receipt.json`: `66f73d184d915b6e592e9e7985524d3caf4b164a0acad7f6e7c7662bcd86a76d`
- `saturated-fields-controls/receipt.json`: `c3104353a35234c36e5ac9af68c0891996a07c8ec2afbad8b43cc622c2677610`
- `saturated-fields-screen/receipt.json`: `11649eba5678d911aef02ce711d44af23271a0146c6a1b433e73d6d8f590ebe3`
- `saturated-fields-memory/receipt.json`: `2b2c340d0ff796b2f2f58100b845ce8f9a2d08af1b66645a03f2dd76af1fbcd5`
- `immutable-text-controls-concurrent/receipt.json`: `011770005cbfe8f33a1ad31ee89402e362ec6a47ff81bdc8ef7519aab16a587a`
- `immutable-text-confirmation/receipt.json`: `202bdc120921f6bdfd0d351a2446b8a4252201886bec2d6cdbc4925ea0bc5901`
- `immutable-text-decision.json`: `4c222a7c7b63dbd849473bd52b857ff34cae18cc730471bb80bc6b6319cb7fe3`
- `direct-fields-decision.json`: `dae4717d3aba2a6f6c50b8618514f28855de952e1b170c7911e61b2ac91530eb`
- `saturated-fields-decision.json`: `8829b14b3f7fbb06c448aa7b724a5ab0f8b5913a33558c3280f04a52675c0039`
