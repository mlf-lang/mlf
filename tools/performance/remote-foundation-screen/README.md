# Independent-runner Foundation15 screen

This is a new experiment, not a relaunch of the frozen local Foundation screen.
It leaves all old batches and their unresolved execution-scope records unchanged.
Native fixed-point A/B remains paused. This screen compares two ordinary
GHC-hosted MLF producers; it does not measure MLF versus GHC end-to-end speed.

One fresh ubuntu-24.04 GitHub job checks out exact main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`
and Graph candidate `954d89971b732eabc1d0730ac11c03f478d11850`.
The frozen 95-home/16-support byte inventory is checked independently on each
checkout before staging. The only production-input difference is Graph.
The actual GHC compilation closure must contain exactly those 95 modules.
Official GHC 9.14.1 archive SHA-256 is pinned in install.py. Full installed
inventory is compared before and after both builds; GCC executable identity
and version, commands, resulting ELF hashes and runtime libraries are retained.
Both producers use identical options, packages, C support and sequential builds.
No old executable, builtin, query cache or reference result is transferred.

The fresh A producer creates a shared builtin using a Version seed. A fresh
qual-A establishes this runner's reference. qual-C and fixed A1/C1/C2/A2 must
match full interface/object/query-report bytes and every result-file name and
byte, with schema/SHA/CRC/key decoding checks. All inputs use shared paths.
Every call gets a fresh application cache at the same pathname, preserved by
rename afterward. OS caches are not flushed. Seed and qualifications are
retained but excluded from paired metrics.

Exact-child wait4 measures fork/exec-to-exit wall time and Linux peak RSS, not
allocation or process-tree peak memory. Hashing/output scans occur outside
timed calls. Two pairs are exploratory only: continuation requires each wall
C/A <= 1.03, geometric wall C/A <= 1.00 and each RSS C/A <= 1.05. A failure
stops with no rescue samples or altered workloads. Shared-host variability
remains a limitation even though the old local worker cannot use this runner.

Bounds: job 35 minutes; installation 300 seconds (1 GiB file limit), builds
900 seconds total (each GHC <=420 seconds, 256 MiB file limit), screen outer
600 seconds plus 10 cleanup (each target <=60 seconds plus cleanup, 4 GiB AS,
80 CPU seconds, 16 MiB file limit). Build CPU cap is 600 seconds per child;
installation retains 240. Screen requires >=4 GiB available memory and >=16
GiB free disk. The outer subreaper must establish terminal cleanup before
success can be reported. Artifact upload is bounded at 256 MiB/20,000 files;
failure artifacts are retained when within this bound. No Library upload.

The 19 existing synthetic checker/supervisor controls and 10 screen-specific
synthetic controls run before building. Final package is independently reviewed
before publication. Any control or experiment failure remains a separate batch.
