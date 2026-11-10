# Source-context binary encoding reuse (parked legacy experiment)

**Disposition:** this experiment is not on the current public `--compile-crate`
path and is not an optimization candidate for the complete 90-module endpoint.
Do not spend a complete producer/performance window on it without a new,
explicitly selected legacy workload. The source is retained only as an isolated
experimental checkpoint, not as a proposed main-branch change.

The current CLI enters `CrateSession.compileSpecFileUsingInstaller`, then
`compileGraphSources`, `compileGraphLocked`, `CrateGraph.compile` and
`QueryGraph.publish`. The writer modified here belongs to the older
`compilePreparedWithEncoding`/`compileSourceGroups` route. A source-level
repetition is not evidence that the measured endpoint executes that repetition.

The current graph writer accumulates pending payloads in memory. It publishes
only after all SCCs and the crate-output boundary succeed. No query payload files
therefore do not prove that inference has not run. `QueryGraph.begin` does create
`query-graph-v2/results`, `generations` and `staging` directories earlier, which
can be a separate trace clue but does not replace phase instrumentation.

This experiment targets repeated legacy cold-query publication work. The existing
source-query writer reconstructs the same binary datatype context and its SHA-256
for each fresh declaration group. The read-side context window does not cover
this work.

The candidate carries one immutable, structurally matched binary encoding through
one Query or CrateSession invocation. It retains at most 1 MiB of encoded bytes.
A changed datatype list uses the original serializer and digest operation. Empty,
changed, reordered, kinded and duplicate-name datatype lists remain supported.
Every publication still checks its destination, reads and compares all existing
bytes, repairs missing/corrupt contents, checks staging errors and atomically
publishes the context before the record. No publication result or validation
receipt is cached. Existing stateless helper APIs remain stateless.

## Controls

The standalone fixture checks 81 transitions among finite datatype lists against
fresh bytes from the unchanged structural serializer, then checks actual
bytearray identity on a hit, the retention-size boundary, unchanged file mtime,
missing/corrupt repair, directory destinations, staging failure/retry, complete
record byte identity and failure-state clearing. Filesystem controls hold the
real directory lock. The implementation's admission domain is the existing
finite parser/checked datatype lists, not forged memo entries or arbitrary
partial Haskell values.

Run the fixture with O0 and O2 owners against the exact unchanged dependency
closure of an authenticated ordinary GHC 9.14.1 producer:

```sh
python3 -B tools/performance/source-context-write-reuse/run_controls.py \
  --producer /absolute/baseline-producer \
  --producer-source /absolute/baseline-checkout \
  --output /absolute/fresh-controls --integration
```

The harness admits changes to only CrateQuery and CrateSession, recompiles both
at O0 and O2, retains command/resource evidence, and verifies the producer before
and after. This narrow gate is not a complete candidate compiler qualification.
`--integration` also compiles and runs the unchanged maintained source-context
campaign with the qualified O2 owners, including both Query and CrateSession
routes. A complete ordinary candidate build remains a separate required check.

With an idle-machine serial window, `--measure` additionally runs a fixed eight
leg ABBA/BAAB sequence of fresh versus reused encodings. Each process handles
1,000 identical 64-datatype contexts. Both modes must print the same final digest.
These are deliberately synthetic encoding timings, not compiler wall-time
speedups. There is no OS cache flush and no native A/B or bootstrap fixed point.

Current status: implementation and local O0 preflight controls pass. Authenticated
O0/O2 controls, maintained integration gates and end-to-end benefit are pending.
No compiler performance claim is made from the source-level work reduction.

## Restart checkpoint (experimental R1)

This branch is an experimental checkpoint, **not ready to merge**. Its baseline
is main `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. It changes only the Query and
CrateSession implementation owners plus this dedicated control directory.

Resume only if the coordinator explicitly selects a legacy control workload.
For the current compiler sprint, retain this checkpoint and prioritize tracing
the actual graph route instead. The historical validation plan below is not an
authorization to consume the shared-machine heavy-task window.

If the legacy experiment is selected, resume in this order:

1. Obtain GHC 9.14.1 and the ordinary host prerequisites. Build the exact baseline
   in its own checkout with `tools/shared/build.py --bootstrap-only
   --optimization 2 --build-dir /absolute/baseline-producer`.
2. Run this directory's `run_controls.py` with that producer, its exact source
   checkout and a fresh output, using `--integration`. The harness authenticates
   the producer and admits only the two changed owners.
3. Refresh `mlf.lock` using the ordinary baseline package manager. The checkpoint
   intentionally still contains the baseline lock because its refresh and
   validation have not run yet.
4. Build and authenticate a complete ordinary R1 producer in this checkout.
   Run its shared-source grammar check and maintained source-context gate.
5. Select and prove a workload that actually exercises the legacy writer.
   The current complete 90-module public endpoint does not exercise R1 and
   must not be used to claim its benefit. Keep all checks, resource limits,
   source/object identities and cold-target boundaries. Inspect exact artifacts,
   group coverage and every sample. Synthetic `--measure` remains separate.
6. Commit final receipts/summaries and the validated lock, then request independent
   review. Do not merge or run native A/B/bootstrap fixed points as part of R1.

The early local O0 preflight is diagnostic only. Final authenticated O0/O2
controls, maintained integration, source-lock refresh, complete candidate build,
end-to-end performance and independent review are all **unfinished** here.
