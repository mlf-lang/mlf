# Main Foundation15 phase diagnostic

This isolated fresh-runner diagnostic uses exact main fc300bc9 only. It does not
rerun or rescue the stopped depth-cursor candidate. No main code is changed.
The official GHC 9.14.1 archive, 95 producer modules, 16 support files, 15 workload
sources, runtime identities and output contract are pinned as in screen a8f247d.
One sequential producer build is followed by seed, normal qualification and one
MLF_QUERY_PROFILE=1 call. Application caches are fresh at the same path. Outputs
and all 1653 result files must match the uninstrumented qualification bytewise.
Only the instrumented call may add unit.query-profile. Six nonnegative integer
phase counters with positive sum are required; preserve exact counters and raw
wall time without calling them performance samples or GHC comparisons.

Counters are existing coarse scopes: infer_ms includes inference, canonicalizing,
validation and result recording/serialization; it is not pure solver CPU.
Milliseconds are wall clocks and instrumentation overhead/GC/lazy evaluation can
shift attribution. Unmeasured setup and timer overhead can leave a residual;
never force counters to sum to whole-program wall time. Use this to choose the
next finer diagnostic, not as a speedup result or complexity proof.

Retained bounds are install 300 s, build 900 s, outer diagnostic 600 s plus cleanup,
each compiler call 60 s, AS 4 GiB, output file 16 MiB. Fresh GitHub runner and
concurrency group isolate old task scopes; no old leases are cleared. Synthetic
preflight and selftests run before building. Complete evidence upload is bounded
256 MiB/20,000 files with hidden files included to retain empty cache locks.
No native fixed-point A/B, merging, or Library upload is performed.
