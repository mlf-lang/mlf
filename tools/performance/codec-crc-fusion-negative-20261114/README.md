# CRC step-fusion screen: reviewed negative result

Independent actual-run and same-build emitted reviews passed their finite control
and phase/action-boundary checks. This candidate is rejected for promotion.
A uses ordinary F25 Bitstream; B changes exactly the local crcRange advanceCRC
call into its read-table/shift/xor body. No primitive, algorithm, flags, global
Int representation or array representation change is included. The public API
and advanceCRC helper and its other call sites remain unchanged.

One bounded ordinary run completed: 20 commands, outer elapsed about 38.0087 s.
Both sides passed authored controls, then each ran four fixed unweighted payloads
and seven phase observations per payload once. No retries or added repetitions.
The largest payload standalone CRC allocation rose from 104,236,736 to
117,259,784 bytes; writer-plus-CRC rose from 307,142,432 to 320,165,480 bytes.
Plan allocation was unchanged. Reject promotion: this does not show a practical
improvement. Raw stdout and all numeric observations are preserved unchanged.

Counters are current-thread bytes (approximately 4 KiB resolution), not process
RTS totals or RSS; times are monotonic nanoseconds, not repeated benchmark
estimates. Never subtract later warm standalone CRC as exact writer-exclusive
cost. Four unweighted payloads do not represent full compiler workload weights.
Phase action/forcing boundaries were confirmed by the same-build emitted review.
Action/thunk closure construction remains outside measured intervals. Zero
forcing-control allocation must not be equated with free traversal.

For source reconstruction apply candidate.patch to the pinned F25 Bitstream.
Compile identical Main.hs independently against each side's freshly compiled
Bitstream interface and coherent ordinary dependencies. Run mode controls then
phases, with the four frozen payload filenames in the prior codec phase screen
order. Require controls stdout to match exactly and all payload roundtrip/CRC
checks to pass. The fixture includes independent reference CRC and finite
boundary/error-order controls, not complete codec qualification. Source-only
headers in preserved files refer to their drafting time.

This archive excludes payload bytes, generated builtin, object closure and
machine-specific runner; it is not a self-contained one-command reproduction
kit. No full compiler performance claim or mainline promotion is made. Native
A/B fixed-point testing remains paused. Publication preparation did not rerun
or compile anything.

## Reviewed generated-code explanation

Main Core/STG are byte-identical except dump timestamps, and Main.o is identical
across A/B. The baseline large checksum path is checksum12, a specialized
state-threaded loop with unboxed position. B's fused path goes through
$wcrcRange and a local specialized worker: CRC arithmetic is fused and CRC is
unboxed, but boxed position, next-position thunk and byte-read/action closures
remain. This code-shape change supports investigating the lost specialization;
it does not establish exact closure-by-closure heap attribution.

For the three measured large payloads the observed allocation increase matches
32 * payload_bytes - 152. This is a finite observation, not a universal formula,
and is NOT proven to be one 32-byte closure per byte. No Cmm/complete heap
accounting was performed. The fixed controls are not exhaustive semantics,
full codec qualification, a compiler-wide benchmark or stable timing evidence.
Review report hashes and source/object pins are recorded in results.json.
