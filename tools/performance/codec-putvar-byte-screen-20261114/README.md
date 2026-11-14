# putVar byte specialization: fixed allocation screen

**Experimental archive only.** The actual run passed the fixed A/B controls and
predeclared allocation conditions. Independent same-build emitted review also
passed its focused artifact, active-path and observer-boundary gates.
This is not a stable timing result, complete codec qualification,
full-compiler improvement, parity-to-GHC result or production promotion.
Only files in this archive directory are added; no production file is changed.

## Observed result

One corrected-fixture run completed 20 commands in 35.704454 seconds, with
cleanup complete. Baseline A was compiled, linked and passed all controls before
candidate B was compiled. Both controls passed before exactly one A then B
observation pair: four fixed payloads, ten windows, 40 numeric rows per side.
Every raw row, including nanoseconds and unchanged/changed other windows, is
retained in the stdout files and `observations.json`.

| Payload bytes | Whole writer A | Whole writer B | Reduction | Entries A | Entries B | Reduction |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 91 | 87,920 | 82,736 | 5.8963% | 16,496 | 11,312 | 31.4258% |
| 1,510 | 912,760 | 905,968 | 0.7441% | 24,856 | 20,320 | 18.2491% |
| 56,187 | 46,704,696 | 42,561,256 | 8.8716% | 20,698,992 | 16,693,168 | 19.3527% |
| 406,975 | 307,142,432 | 290,357,680 | 5.4648% | 114,738,576 | 99,175,448 | 13.5640% |

Values are current-thread allocation-counter bytes, not total process/native
allocation. The frozen conditions require complete byte/control equality on
both sides; `B <= A + 4096` separately for whole-writer and entries on all four
samples; `100 * B <= 99 * A` for whole-writer on samples 2 and 3; and `B < A`
for entries on samples 2 and 3. Independent actual-emitted review is a separate
required gate. Exact integer inequalities, not rounded percentages, decide the
numeric conditions. Time was not an advancement criterion.

Symbols also decreased by 0, 2,256, 137,616 and 1,221,624 bytes respectively.
The other seven windows were allocation-identical. These diagnostic windows
are not exclusive buckets to sum or subtract, and cannot prove exclusive
attribution of savings. Small changes and zeros have about 4 KiB counter
precision and must not be overinterpreted.

## Exact source and finite semantics

`candidate.patch` adds one unexported `putVarByte` helper and replaces one call
inside `putVar`. The exported generic `putBits` and all other pre-existing
definitions remain unchanged. The byte argument is defined by the existing
varint expression and lies in 0..255. An aligned byte is overwritten; an
unaligned byte retains the original read/write, read/write sequence and ORs
the two fragments into existing bytes. No zero-buffer assumption, second-index
precheck, atomicity or new strictness annotation is added. A second-index
failure must retain the first mutation. Negative positions and positions above
Int64 maximum minus eight fall back to unchanged generic `putBits`.

Both variants use the identical corrected v2 `Main.hs`. Controls include codec,
CRC and decoder rejection/demand checks; segmented output equality; 160 finite
putVar combinations covering eight offsets, ten lengths and two fill patterns;
nine boundary cases including partial writes, negative and overflow-risk
positions; and six labelled poison/demand cases plus lazy IO-action construction.
The generic reference and independent unsigned base-128 byte oracle are not
derived from candidate B. `results.json` records the precise coverage and
limited review conclusions. Finite controls are not universal bottom/error
equivalence or malformed-geometry proofs.

## Preserve the earlier failure

Run01 stopped at baseline A-controls after eight successful commands; the ninth
exited 1. B was never compiled or executed, and there were zero performance
observations. Its fixture incorrectly expected `PutDone 7` for the boundary
case `(buffer length 16, position -1, value 0)`. The original Host primitive
throws `integer shift overflow` for a negative shift even when the operand is
zero. The old pure model wrongly treated it as a right shift.

That is a known authored-oracle error, not evidence of candidate regression.
The old unlabeled `putVar outcome mismatch` log does not prove this was the
exact first failing assertion or the only possible failure. V2 corrects the
source-derived expected HostError and adds mismatch labels; the candidate and
finite runtime case list are unchanged. `failed-run01.json` and original stdout
plus path-sanitized stderr retain the failure honestly. The stderr changed only
by removing a machine-specific source-root prefix from its backtrace.

## Identity, review and reconstruction limits

Independent actual review verified 281 pins and all 20 command guards. The
separate emitted review verified 196 pins and read all eight same-build dumps.
Main Core/STG are exactly alpha-equivalent under verified bijective generated
identifier renamings plus timestamp removal, **not timestamp-only equal**.
All literals, primitives, constants, types, strictness and control-flow text
remain intact. There are 1,220 changed Core mappings and 3,834 STG mappings.
Every Main.o section is byte-identical except `.strtab`, whose seven differences
are local generated labels. Distinct full object/interface hashes are retained.

The private helper is actually inlined into the measured `putVar` path. Its
negative/overflow fallback retains generic writing, and the unaligned
read/write/read/write order and lazy action-WHNF checks survive. Public generic
`putBits` specializations remain alpha-equivalent. Actual writer calls and
return-position/CRC forcing occur inside their windows; surrounding setup and
action construction remain outside. This supports the focused diagnostic
screen, not universal semantics or exact per-closure heap attribution.

The measured baseline is ordinary F25 Bitstream SHA256
`f25fe195b5a287fd0c365286acb31839118edac2227f463ea5cc85eb26daedb8`.
The candidate is SHA256
`9fc2fe7f8d8e38bb7209233980a6d6b05b529acce8152502df31b84637ba7c2b`.
The recorded measured-base commit is
`bda8f9807c8b13b5ce14753d0320fa54772e4bc4`, which was not remotely resolvable
at archive preflight. The public archive parent is instead
`4c940cdcd16d820d808aaba0a0e24fc124c9e30b`, the prior writer-segments archive.
**Archive ancestry is not measured-source identity.** Do not treat the archive
parent checkout as a substitute for the authenticated F25 source/dependency
closure. Source, payload, linked-object, dump and evidence hashes are recorded
in `source-pins.json` and `results.json`.

Fresh A/B Bitstream and Main compilation used GHC 9.14.1 with `-O2`,
`-fpedantic-bottoms`, `-fno-state-hack` and the remaining identical semantic
flags in `source-pins.json`, twelve unchanged authenticated home dependencies
and two original C objects. Same-build Main and Bitstream Core/STG were
captured. No new compile, control, benchmark or runtime-loader invocation was
performed to prepare this archive. Main's source-only header describes its
draft origin, not whether the archived screen was run.

For reconstruction, obtain that coherent dependency closure and the four
payloads identified by hash, compile each fresh variant with the same common
Main, and run controls before observations in the documented order. Require
the exact controls stdout, 40 rows in the `observer-contract.json` order and
terminal `PASS codec-writer-segments`. The payloads, builtin, full producer
object closure, binaries, dumps and machine-specific plans are not bundled.
This is an evidence archive, not a self-contained reproduction kit.

Input IO/decode/forcing, plan and layout finish outside observation windows.
The whole reference uses each variant's `encodeTables` first. The segmented
writer allocates a fresh buffer, invokes public operations in original order,
and forces positions/CRC earlier. Action closure construction can be outside
the windows. Full byte and return-value comparisons are outside measurements.
Warm state and specialization may differ. Do not add/subtract segments to
estimate original writer cost or extrapolate to total compiler savings.
One ordered pass, four unweighted payloads, finite controls and limited emitted
checks establish neither stable speedup nor full compiler/native qualification.
