# Narrow reference writer: reviewed local allocation screen

The fixed local screen passed its source, actual raw/control/lifecycle and
complete same-shot Core/STG reviews. This is **prepared whole `encodeTables`
including CRC**, not whole-compiler cost, a stable wall-time result, reference-only
exclusive attribution, Foundation-workload coverage, current-main qualification
or GHC parity. No production merge is made. Later ordinary qualification is a
separate task; no future result is included here.

## Actual observations

One bounded run completed 24 commands in 48.474862 seconds with its cleanup
confirmed. Both sides compiled fresh Bitstream and common Main before controls.
The order was A-controls, B-controls, A-measure, B-measure. Each controls process
passed all eight exact groups, and each measurement process performed just one
ordered pass over the same four saved inputs. No warmup, retry or extra sample
was added. Both encoded outputs equalled the original complete input bytes.

| Payload bytes | A allocated bytes | B allocated bytes | Saved |
| ---: | ---: | ---: | ---: |
| 91 | 82,784 | 82,152 | 632 (0.7634%) |
| 1,510 | 906,016 | 904,336 | 1,680 (0.1854%) |
| 56,187 | 42,561,304 | 40,034,640 | 2,526,664 (5.9365%) |
| 406,975 | 290,357,728 | 268,553,088 | 21,804,640 (7.5096%) |

The predeclared gate was no allocation regression on any input, with savings
of at least `ceil(A / 100)` separately on the two largest. Positive writer
allocation, zero empty-window allocations, controls, byte equality and independent
emitted review were all required. Nothing is subtracted from the raw values.
The smallest differences are below approximately 4 KiB counter precision and
must not be overinterpreted. The sum over these selected shapes is descriptive,
not a weighted compiler workload estimate.

All eight raw observations, including nanoseconds, are retained. The largest
B writer time was **39,760,064 ns versus A's 38,861,605 ns**, slightly slower.
One observation per side/input cannot establish stable time improvement.
The candidate's Bitstream object also grew **13,728 bytes**, from 699,320 to
713,048 bytes. Current-thread heap savings exclude that static-code cost,
foreign buffer allocation and RSS.

## Source change and semantics

The baseline is the previously qualified ordinary putVar source, provenance
commit `250e495d93de5fad975fb61c6e23a1ad1a964640`, not pristine F25 or current main.
Its Bitstream SHA256 is
`9fc2fe7f8d8e38bb7209233980a6d6b05b529acce8152502df31b84637ba7c2b`.
Candidate SHA256 is
`066815fb9d74be16a5aed0f0b836d405b9bef8a9dddd5cc15057d9a9f2b83572`.
Both full files and the exact patch are included. Applying the one lexical
change in reverse recovers every baseline byte.

The sole production delta adds private `putReferenceBits` and changes its one
caller inside the existing `putReferences` list loop. Public exports, generic
`putBits`, putVar helpers and `putEntry` remain unchanged. Widths outside 1..16
fall back before demanding position. Negative positions or positions above
Int64 maximum minus 16 also fall back. The empty-list case bypasses all guards.
Inside the narrow domain, up to three byte fragments retain full overwrite
versus partial read/OR/write, masking arbitrary signed indices and preserving
partial writes and original error ordering. The unchanged next-reference list
recursion and bounded closures remain; this is not allocation-free writing.

Finite controls include 256 valid cases with an independent byte oracle,
1,344 bounds/fallback combinations, partial writes, poisoned operands/tails,
action WHNF versus execution versus forced result, and ENode prefix effects.
They are actual finite controls, not exhaustive semantic or async-error proofs.

## What the emitted review establishes

The actual A/B Main Core and final STG are alpha-equivalent after the declared
consistent compiler-generated identifier renaming and header timestamp removal,
not merely assumed equal because the source matches. All four compile bindings
tie source, complete dumps, object/interface and successful command together.
Each link uses its own fresh Bitstream/Main plus twelve unchanged authenticated
home objects and two original C objects. No old target or cross-side object is
substituted.

Preparation fully reads/decodes and forces Values, Tables and all twelve Layout
fields outside the observation. Actual output buffer creation, writing, CRC
calculation and stored-CRC writing occur inside the delayed `encodeTables`
action. Full output equality and formatting are outside. A small action closure
is constructed outside identically on both sides; no output warming or equivalent
carrier-building shift was found.

The private helper is inlined into the active `putReferences` path. In-domain
generic per-fragment recursive dispatch is removed; original generic fallback
workers survive, with no eager operand checks before original buffer operations.
The actual inputs' node widths are 2, 3, 12 and 14 and their bounds fit the fast
domain. This is source/header/byte-equality evidence, not dynamic branch counts.
The complete raw and emitted reviews plus composition hashes and bounded
conclusions are in `evidence/review-summary.json`.

## Reconstructing the source and inputs

The public archive parent is `12a27355827acc360b21b18ee717c4513baca2ff`.
Use its exact
`tools/performance/codec-putvar-byte-screen-20261114/ordinary-qualification/`
source reconstruction instructions for **variant B**, which reconstructs the
baseline source tree `703052cd990d7f8e7d68cef856f6417cafbf0ffc` from public
commit `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. That prior archive includes
the real regenerated canonical builtin and full-tree verification. Archive
ancestry is not a qualified binary/producer and does not replace rebuilding
and checking the toolchain/dependency closure.

Create separate baseline/candidate copies of this reconstructed source. Use the
included `baseline/Bitstream.hs` or `candidate/Bitstream.hs` at
`libraries/mlf-crates/Bootstrap/Bitstream.hs`, checking the hashes. This archive
changes only the direct local target for the candidate; it does **not** ship a
newly regenerated candidate builtin or qualify a complete candidate compiler.

The four actual binary inputs are shipped losslessly as base64 text. Recover
and validate them with `python3 decode-inputs.py`, then run the fixture from
this archive directory. The published `Main.hs` differs from the measured source
**only in four absolute input path strings**, now `inputs/00.bin` through
`inputs/03.bin`. Original and public fixture hashes are separately recorded;
the sanitized fixture was not recompiled during publication. The exact four
line locations and private reverse-substitution byte check are recorded in
`evidence/fixture-sanitization.json`; original machine paths are intentionally
not recoverable from this archive. Its source-only
header describes drafting history, not the completed original measurement.

`build-command-templates.json` retains the actual target/Main compile and link
argument structure with path placeholders. Use the identical GHC 9.14.1 ordinary
flags in `source-pins.json`, isolated per-side output/interface directories, the
listed twelve home dependencies and two C objects from the coherent baseline.
Compile each fresh target and common fixture; capture Core/STG in those same
invocations. Run each fixture's `controls` mode first, then a separate `measure`
process in the frozen A/B order. The controls stdout must exactly match the
archived files. Require all four measurement identities, lengths and equality
flags, zero empty allocations and the terminal summary in `output-contract.json`.
Source-only base64 decoding and patch/hash verification during publication are
not reruns of these commands.

No objects, executables, large IR, installed package/toolchain image or private
controller state are bundled. The evidence hashes identify the reviewed large
IR artifacts but cannot reconstruct those omitted files. Source and fixed
inputs are reconstructible, but
this is not a one-command reproduction of an authenticated machine environment.
No compiler, target test, loader or new measurement was run for publication.
Production integration would require a separate current-main source/toolchain
comparison and whatever fresh validation that comparison requires.
