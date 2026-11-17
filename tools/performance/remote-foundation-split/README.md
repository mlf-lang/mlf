# Foundation15 record boundary diagnostic

Build exact main A fc300bc9 and instrumentation-only P sequentially on fresh official GHC 9.14.1. P modifies two staged modules after original pin validation; original and instrumented hashes and exact patch are retained. Do not call P exact main or an optimization. Seed/qualification use A; one fresh-cache profile call uses P. Complete CI/CO/query and all 1653 result-file bytes must match A.

raw_record_ms is a nested subset of infer_ms around G.record, excluded from six-phase totals. It includes encoding/hash and possibly deferred fragment evaluation; residual is NOT pure solver time. No speedup or GHC comparison. Native fixed-point A/B remains paused.

Retain 900s whole build cap, 600s outer screen, each compiler 60s, all cleanup receipts, exact source/toolchain/workload pins, 256MiB artifact cap and hidden files.
