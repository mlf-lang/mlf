# Warm Foundation phase profile

Study the v7 driver at the fetched PR #29 head. Use the 14 Foundation modules
and original Version literal from the earlier study. Verify their individual
source hashes against results-20261103.json. Use one absolute source tree,
spec, cache, prelude prefix and final output prefix for every sample. The new
executable and paths can change the literal keys compared with the previous
10.682666 s probe. Reproduce that interval with a coarse arm in this run.

Build one GHC 9.14.1 -O2 executable with the usual demand flags. Plain uses
the actual session, Coarse uses the previous Probe boundaries, and Detail uses
host-only instrumented copies. The compiler SHA used by all arms is identical.
Warm here means a populated query cache, a new process and normal OS page
caching. Prepare the builtin and populate once with Plain. Preflight runs
Plain, Coarse, Detail, in that order. The fixed timed blocks are P/C/D, C/D/P,
D/P/C. Keep all samples and report arithmetic means and ranges. No concurrent
builds or performance runs, no cache eviction, and no sample selection.

Require 504/0 inferred/reused when populating and 0/504 for every warm process.
Compare the complete cold/warm interface and object bytes, the warm report
bytes, and all ordered keys, members and semantic fingerprints. Check the
prelude and the entire cache file set, content, and active-record inode/size/
mtime before and after each warm sample. Require 504 records and 83 context
carriers. Keep wall, user/system CPU and per-process maximum RSS. Require 504
observed hits, 504 finishGroup calls, one final artifact pair and one report.
Keep inclusive and exclusive clocks. Parent wall less its timed children is
explicit residual. No nested time is charged twice. Reconcile every hit and
session partition against its parent. Compare Detail total to Plain/Coarse and
its hit interval to Coarse. Flag a mean discrepancy above 10% for the whole
run or hit interval as material perturbation and limit attribution accordingly.

Time original computations at their normal demand sites. Match the coarse
hit endpoint by forcing the decoded Either. A pure clock observes WHNF when
demanded, never a full NF traversal or a re-encoding for measurement. Mark
deferred restored key text, fingerprints and final artifact assembly separately
when forced. finishGroup measures the actual return decision and work demanded
there. Label deferred final fields separately and report where their consumers
force them. Time bounded C file transport separately from conversion to the
host ByteArray. The C read call measures filesystem service time with normal OS page caching. Separate key handling, wire/typed decode, checksums,
syntax/domain admission, xMLF checking and binding re-inference. Track
file output encoding, byte writes and publication separately.

## Focused follow-up

The primary preflight placed most hit time in the wire symbol table and
revealed a separate large ensureBuiltin interval. Keep the primary run
unchanged. In a second executable add demand clocks around the UTF-8 reader
action, deferred text materialization, symbol-table lookup/insertion, the
actual builtin construction, CompilerCore phases and the builtin's split and
round-trip validations. Use the *same original absolute source tree and
already prepared builtin pair* from the primary run. Re-prime a fresh query
cache because this executable has its own real digest. Require byte-identical
artifacts to the primary run. Preflight P/C/D, then run P/C/D/D/C/P, all new
processes. Apply the same workload, partition and 10% perturbation checks.
Report focused component timings separately, not as addends to the primary run.
