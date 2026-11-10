# Bounded prerequisite restoration failed

The single admitted new baseline prerequisite phase exhausted its original
300-second total deadline during xmlf. No retry, resume, limit increase, inference11,
GC diagnostic, native generation or fixedpoint followed. Raw data is unchanged.

Completed and fully checked within the phase:

| Prerequisite | Modules | Fresh / reused | Wall seconds | Child user seconds | Child system seconds | Max individual child RSS bytes | Sampled tree peak RSS bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| builtin-fixture | 1 | 1 / 0 | 0.35148401 | 0.30297599999999997 | 0.048503 | 22343680 | 22343680 |
| mlf-foundation | 14 | 475 / 0 | 29.536470839 | 29.105504 | 0.501854 | 124719104 | 124719104 |
| mlf-language-core | 4 | 74 / 0 | 64.695432391 | 60.622696 | 2.401562 | 169050112 | 170098688 |
| mlf-frontend | 11 | 763 / 0 | 164.217328011 | 167.013712 | 3.033297 | 336084992 | 336568320 |

All four successful commands exited0 with empty stdout/stderr, exact fresh query
counts, unique group IDs, no cached groups, ordinary public interface ownership/
dependency checks and query-lock release. The first row is the tiny Fixture used
to prepare the separate fixed builtin pair, not a compiler library.

Xmlf received only26.855082599 seconds of the remaining phase budget. Its command
receipt is incomplete. Its two raw `.mlfci/.mlfco` files exist, but `.queries` is
missing and no completed query/interface checks were recorded. Its final wall,
CPU, RSS and exit status are unavailable; they must not be fabricated as zeros.

The launcher stopped work at300 seconds. Its reported300.441334943 seconds includes
termination cleanup. Original watchdog elapsed299.9209265069994 seconds and reports
`RuntimeError: watchdog interrupted by signal 15` because the launcher's absolute
deadline fired first. Peak monitored phase RSS was361492480 bytes. The unchanged
ceilings were RSS5GiB, per-process AS6GiB, diskfree5GiB, hostavailable3GiB and output4GiB.

Cleanup found no remaining owned PID/starttime identities. Shared and both original
inner orchestration locks were reacquired, and an independent postfailure read-only
inspection confirmed no owned survivors and reacquired all five query locks.

Final producer authentication and runtime-after snapshot did not run. Therefore
there is NO completed dependency handoff, despite the successfully checked prefix.
The retained5221 dependency/cache files total42014642 bytes. No old artifact
availability, current throughput, compiler/GHC ratio or GC conclusion is claimed.

`phase-summary.json` contains exact commands, original receipt/code/admission/plan
identities, all successful prefix output hashes, partial xmlf hashes, missing fields
and cleanup proof. Its paths consistently substitute `${WORKSPACE}` for the private
absolute workspace root; raw original receipts retain the actual paths.
