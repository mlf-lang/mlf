# Inferred chain: private body-template writer, 2026-11-18

No compiler change is retained. A bounded body-template writer reduces object
size and live heap, but its independent confirmation does not establish faster
full compilation or lower growth. It remains a private, writer-only experiment;
production readers do not accept its format. The current `inferred_chain`
(unsigned monomorphic dependency chain) remains at five of the original six
acceptance checks. The fitted-exponent confidence gate is still open.

Evidence is under `.mlf-build/inferred-chain-body-templates-20261118`. The maintained
producer and prior source/evidence pins were reauthenticated before this work.
The [current formal GHC cohort](compiler-inferred-chain-metadata-2026-11-17.md)
was neither rerun nor supplemented with these diagnostic samples.

## Representation and scope

The existing writer emits a complete generic syntax body in every final fragment.
The earlier layout-only estimate was refreshed against the current producer and
then implemented in an isolated source shadow, `matched-pool-v2`. Its schema 9
and `MLF-OPEN-CRATE-TEMPLATE-DIAGNOSTIC-1` marker are private diagnostic choices,
not a published format or a claim of compatibility.

The prototype recognizes exact `(XName ID, hint)` pairs, assigns slots in first
occurrence order and stores a normalized body once. All other syntax, including
type-variable identities, tags and floating-point bits, stays exact. Matching
uses at most 32 templates, each with at most 128 generic values and 16 name slots;
eligible strings have at most 4096 UTF-8 bytes. Cache hits move to the front
without changing serialized template IDs. Ineligible bodies and new shapes
after the cap keep their complete raw row. Hits avoid allocating another
normalized body. No hash-only equality or ID-only name comparison is used.

This changes only the final package writer. Checked fragments, reference hashes,
metadata receipts and query payloads retain their existing meaning. The fused
endpoint uses its checked in-memory package and therefore exercises the writer
without exercising a schema 9 reader. That distinction is material: the measured
candidate has no production reader, projected restoration-work admission,
native self-bootstrap qualification or package/cache compatibility qualification.

The actual output differs slightly from the earlier layout-only model because
the diagnostic format marker has a different length:

| N | Fragments / templates | Old object bytes | Prototype bytes |
| ---: | ---: | ---: | ---: |
| 0 | 3 / 3 | 1,338 | 1,387 |
| 256 | 259 / 5 | 74,257 | 70,714 |
| 1024 | 1,027 / 5 | 302,673 | 286,916 |

At N1024 the reduction is 15,757 bytes, about 5.21%; the N0 object grows.

## Verification and timing

An independent Python model and a coherent GHC-built writer fixture check 20
documents containing 1,526 fragments. Cases include repeated and renamed names,
same IDs with different hints, different IDs with the same hint, Unicode, NUL,
empty hints, integer boundaries, distinct NaN payloads, signed zero, exact
type-variable identities, the 16/17-name and 128/129-value boundaries, 32/33
templates, 4096/4097 UTF-8 bytes, deep raw fallback and interleaved cache hits.
Three documents are the actual N0/256/1024 objects. Every transformation restores
the complete canonical schema 8 bytes exactly and matches the independently
constructed expected template layout. These are transformation controls, not
untrusted artifact-admission controls.

One smoke pair, a fixed one-warmup/six-measured-pair screen at each N0/256/1024,
and a separate one-warmup/twelve-measured-pair confirmation give 122 compiles and
366 correct native outputs. Every run preserves LLVM exactly and restores the
old object exactly. All interface fields except the separately verified object
SHA match. Independent generation decoding verifies each actual compiler SHA
and equality of all other configuration fields and query rows; raw generation
bytes are not claimed equal between different compiler binaries.

Times below are compiler and Clang subprocess measurements, not the formal
full-worker GHC acceptance boundary. The cohorts are kept separate.

| N | Screen compiler before / prototype (ms) | Confirmation compiler before / prototype (ms) | Confirmation compiler + Clang before / prototype (ms) |
| ---: | ---: | ---: | ---: |
| 0 | 131.586 / 129.492 | 127.319 / 125.793 | 262.633 / 262.700 |
| 256 | 168.351 / 163.825 | 167.770 / 168.244 | 305.239 / 306.421 |
| 1024 | 295.541 / 294.002 | 283.470 / 282.745 | 413.028 / 413.492 |

The confirmation's endpoint slopes are 0.152492 / 0.153274 ms per function for
the compiler and 0.146870 / 0.147257 for compiler plus Clang. Neither point
estimate is lower. Diagnostic paired bootstrap intervals, 2000 draws with seed
20261115, include zero for every elapsed difference. At N1024, after-minus-before
95% intervals are [-4.407, 2.648] ms for the compiler and [-8.094, 4.467] ms for
compiler plus Clang. No power fit is inferred from this three-size diagnostic.

The initial smoke candidate took 1.253 s versus 0.318 s, while their child CPU
times were approximately 0.295 and 0.298 s. The wall-clock delay was not reproduced
by the fixed measured cohorts. Its cause is not established, and the smoke record
is preserved separately rather than relabeled or folded into an acceptance fit.

## Memory result and decision

Three separate alternating RTS pairs at N0/1024 give 12 additional compiles;
their timings are excluded. All object reconstruction, interface, query and LLVM
checks also pass on these instrumented binaries. N1024 medians are bytes:

| Measurement | Before | Prototype | Difference |
| --- | ---: | ---: | ---: |
| Cumulative allocation | 848,839,000 | 833,283,192 | -15,555,808 (-1.83%) |
| Maximum live heap | 10,609,600 | 9,315,984 | -1,293,616 (-12.19%) |
| GC copied | 90,752,816 | 88,060,152 | -2,692,664 |
| Individual peak RSS | 60,719,104 | 57,606,144 | -3,112,960 |

At N0 allocation rises by 56,832 bytes and maximum live heap rises by 28,080
bytes. Allocation, sampled live heap and process RSS are distinct measurements.

The storage and memory savings are useful findings. Do not retain this default
format for the current shape: the confirmation does not demonstrate the required
elapsed/growth improvement, and a writer-only result is insufficient to justify
format migration. This is not evidence that a fully qualified implementation
cannot improve memory; that implementation and its read-path costs were not
measured. No production change, acceptance commit/push, next-shape transition or
unchanged-source formal retry occurred.

Before any future adoption, both writing and reading must account for the fully
restored body, including repeated long name hints, per-root and aggregate work,
typed decode limits and malicious alias expansion. Exact template/slot/use rules,
old-format reads, cache reuse, semantic audit, current regression and native
qualification remain necessary. The existing schema 7/8 limits and query-depth
contract were not weakened by this experiment.

Initial failed attempts are retained: the first shadow helper conflicted with
`Bootstrap.Std.compareName`; the first fixture used nonexistent byte-file APIs;
a screen driver had a Python parse error before execution; and a smoke preflight
incorrectly expected formal-cohort temporary query directories to be retained.
Separate corrected variants use the actual APIs and compare newly emitted
generations. None of these failures is counted as a successful compiler sample.

Continue this shape by attributing other growing construction costs before a new
private prototype. The retained profile has 11.25 ms / 43.06 MB under
`preparedValueCached`, including 4.30 ms / 18.22 MB under `preparedSyntax`;
these inclusive figures must not be added. Prior direct-framing and prepared-value
experiments are negative evidence to check before proposing another version.
The large unattributed profile total includes GC and profiling overhead, so it
must not be treated as one optimizable business function.

## Evidence receipts

- `matched-pool-v2/receipt.json`: `400e1190055fdbcffa81206cdfb259816c160629da455398983ac96dbbe696d9`
- `pool-controls-v2/receipt.json`: `4165b5efa71170749e23d75aecfb707d17c07db930c89e905c4bd491b0afd454`
- `pool-smoke-v2/receipt.json`: `3d5d5f87e563f0e0dba6f7044055bd5f8798be795edf7fb22a15945fe49aa4b6`
- `pool-screen-v2/receipt.json`: `7ee159562cba7c4e94fa0cb2f6c9ee52233726abec9cddd2e4ce5b5f2a666f5a`
- `confirmation-plan.json`: `1ffb2995dd588fc555aa3f0f7cfc2472da3b4e416f5792503e13e3ba0caffe12`
- `pool-confirmation/receipt.json`: `8ddfd212507ffc999170468b4aac0ad27839da1fed698236de491573706751ce`
- `pool-memory-v2/receipt.json`: `590073f095b39fe6409a027d59f7c19b59d1c65493bf4d459dc9ceeabad26da4`
- `pool-decision.json`: `a7e619edd800df5068262921c903e2a51be784e9b37e8ce061feed0ae5a14b7e`
