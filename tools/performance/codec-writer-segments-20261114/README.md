# Ordinary F25 writer segment diagnostics, reviewed

Actual-run and same-build emitted independent reviews passed the finite control
and seven-segment action/forcing boundary checks. No production change, candidate
speedup or mainline promotion is claimed. A separate Main reuses the original
ordinary F25 Bitstream and dependency closure, not the rejected CRC-fusion code.

One bounded run completed 13 commands in approximately 15.338531 seconds.
Finite codec, CRC-boundary and segmented byte-equivalence controls passed. Exactly
40 numeric rows were read back in frozen order, four payloads by ten windows.
For the largest payload: entries 114,738,576 counter bytes; symbols 87,711,232;
CRC 104,236,736; whole-writer-reference 307,142,432. These are diagnostic
observations, NOT disjoint exclusive buckets to add or subtract.

Input IO/decode/forceValues, plan/forceTables and layout/forceLayout finish first.
The whole reference uses original encodeTables. Segmented actions write a
separate fresh zero-filled buffer via the public header/symbol/entry/root/CRC
APIs in original order, forcing returned positions/CRC earlier than the unsplit
writer. Complete output equality with reference and original payload is checked.

Do not sum segmented counters/times and call that original encodeTables cost.
Early demand boundaries and potentially different specialization change the
measurement. Action closure construction can lie outside observation. The whole
reference executes first, so warm state differs. Single-pass times do not prove
stable performance. Current-thread counters have about 4 KiB precision and do
not measure native ForeignPtr allocation bytes or peak RSS. Four fixed unweighted
payloads do not represent the whole compiler workload. Finite controls are not
universal malformed-geometry or bottom/error equivalence proofs.

For reconstruction compile Main.hs against a coherent ordinary F25 dependency
closure and capture Main Core/STG from that exact compile. Run controls then
segments with the four payload filenames from the codec phase screen in the
same order. Controls stdout must match controls.stdout; require 40 rows in
observer-contract.json order and terminal PASS codec-writer-segments. Payloads,
builtin, producer object closure, dumps and machine-specific actions plan are
not bundled, so this is not a self-contained reproduction kit. Source-only
headers in Main refer to drafting time. No new build or rerun was made during
publication preparation. Native A/B fixed-point work remains paused.

## Reviewed boundaries and next questions

The actual segments-mode entry and seven segment operations were checked in
same-build emitted code. Counter/time/action/time/counter order and returned
ByteArray/position/CRC forcing remain inside the respective windows. Outer
setup and action closures remain outside. Original F25 Bitstream is unchanged.
The review checked 211 pins, 13 commands and 40 rows without another run.

The roots segment covers only top-level roots, NOT child references handled
inside entry writing. Symbols already have an aligned ASCII text path; their
segment includes length prefixes and text work, not a missing ASCII fast path.
Entry bit/varint/child-reference work and symbol-writing internals are possible
investigation targets, not yet exclusive inner attribution. The earlier CRC
fusion regression remains rejected. Review hashes and bounded conclusions are
recorded in observations.json. No additive decomposition or whole-pipeline gain
is established by this diagnostic.
