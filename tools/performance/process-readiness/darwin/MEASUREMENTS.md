# Darwin process-wait optimization: local evidence

The macOS `runProcess` path slept for 10 ms while waiting for short children.
The fixed compiler workload publishes 711 fresh query groups through `/bin/mv`.
A private child-exit kqueue removes most of this polling latency; `waitpid`
continues to determine status and reap the child. Production changes are
26 additive lines in three Darwin-only arms of `runtime/mlf_system.h`.

## Fixed protocol and result

Baseline: `d96f67726599fa4e21f236462886106434c8e417`. Ordinary GHC 9.14.1 `-O2`,
single-job builds, ordinary Clang `-O2`; no runtime tuning or target inference
cache reuse. This is a **15-module / 711 fresh-group mlf-crates workload**,
not the earlier 14-module / 544-group study and not the complete compiler build.
The two workloads and their measurements must not be pooled.

A two-block ABBA/BAAB discovery screen passed its predeclared >2% condition
in both blocks (10.719%, 10.914%). Those eight runs are excluded below.
The frozen candidate then used **24 new runs in six blocks**, with three ABBA
and three BAAB orders shuffled using seed 20261030. The fixed budget ended at
24; there were no dropped/replaced samples or sample extensions.

The predeclared estimand is the mean of six block log ratios. Each block
averages its two adjacent `log(B/A)` paired ratios. The nominal two-sided 95%
t interval is calculated on these six values, then transformed to improvement
as `[1-exp(U), 1-exp(L)]`. SciPy 1.16.3 supplies the t interval and quantile;
an independent direct standard-error calculation checks the transformation.
The libraries and all raw numbers are in [MEASUREMENTS.json](MEASUREMENTS.json).

| Metric | Baseline A | Candidate B |
| --- | ---: | ---: |
| Arithmetic mean wall seconds | 79.523439 | 71.012170 |
| Arithmetic mean child CPU seconds | 69.898571 | 69.659542 |

**Paired block improvement: 10.703946%; nominal 95% interval:
10.255786%–11.149868%.** This passes the predeclared point >=3% and lower-bound
>1% decision rule. AB pairs improved 10.573011%; BA pairs improved 10.834689%.
CPU is nearly unchanged, consistent with the intended wait reduction. Wall
minus CPU is not interpreted as an exact I/O-time account; no new GC claim is made.

| Block | Actual order | Wall seconds in execution order | Block improvement |
| --- | --- | --- | ---: |
| 1 | BAAB | 70.613096 / 79.323709 / 79.409491 / 71.001626 | 10.785% |
| 2 | ABBA | 79.746935 / 72.007605 / 71.298385 / 79.395357 | 9.952% |
| 3 | BAAB | 70.838743 / 79.621047 / 79.496323 / 70.812831 | 10.977% |
| 4 | ABBA | 79.369909 / 70.707701 / 70.729008 / 79.625839 | 11.044% |
| 5 | ABBA | 79.359491 / 71.089166 / 71.404839 / 79.778671 | 10.459% |
| 6 | BAAB | 70.762491 / 79.619918 / 79.534575 / 70.880547 | 11.003% |

These are conditional results for fixed binaries, this input, and this host.
Six successive blocks do not prove independence or eliminate persistent
machine/layout bias; the interval is nominal, not a search-wide guarantee.
Two host objects in the isolated candidate embed different source-location
strings; the other 128 non-Main Haskell objects match baseline bytes.

## Correctness and integration

Every confirmation run completed **711 fresh / 0 reused**, with no cached
source group, and compared `.mlfci` and `.mlfco` **raw bytes** to the frozen
qualified artifact. Ordinary baseline A independently produced the same bytes.
This historical local 15-module reference is not relabeled as a newly executed
whole-target P3 reference. The original P3 reference commit remains
`875e483de49655030c4ffba1995b60610a50273a` for the retained semantic oracle lineage.

The frozen candidate passed the complete existing A1 gate, P1 154,072 controls,
P2 2,503 plus 1,243 supplemental controls, P3 922 original plus seven bridge
controls, and 54 query-encoding controls. Frozen oracle files and expectations
were not changed for this optimization. The [Darwin suite](README.md) additionally
passed 40 real transport cases, 27 syscall fault/order cases, 33 actual GHC
readiness calls without descriptor growth, four descendant-cleanup cases, and
ten native Clang `-O2` ABI cases. Removing the three Darwin arms recovers the
baseline header verbatim; this is not a claim that Linux runtime tests ran on macOS.

The actual integrated producer was rebuilt in the branch checkout: its host
object matches the confirmed candidate, while **all 130 non-Main Haskell
objects match baseline bytes**. A separate preplanned four-run ABBA integration
check passed 711/0 and raw-byte checks on every run. Its point improvement is
10.820251% (mean 79.494206 → 70.892790 seconds). These four runs are a targeted
integration check and are excluded from the six-block confirmation interval.
The actual integrated producer also passed the complete A1, P1, P2 and P3
oracle gates and all 54 query-encoding controls. Their receipt identities are
recorded in `MEASUREMENTS.json`.

## Resource and provenance boundary

The existing exact-child runner is unchanged. Each active leg uses its own
512 MiB work cap; at most four active legs consume 2 GiB. The 5 GiB global disk
floor, sampled 5 GiB process-tree RSS, 3 GiB available-memory floor and timeout
guards remain active. macOS does not enforce the requested address-space cap;
this retains the existing sampled-RSS qualification. Between blocks, retain raw
checked outputs, group reports, stdout/stderr, receipts and per-cache-file
size/SHA256 inventories, then remove only that block's disposable query cache.
No archive work overlaps a timed leg.

Source, toolchain, producer, ordinary objects, workload, actual execution order
and output identities are retained in the local evidence directory
`.mlf-build/compiler-next-20261030/darwin-ready/`. Screening and qualification
runner bytes were recovered and checked against their original receipt hashes;
the final confirmation runner is saved separately. The short-child microprobe
and the initial invalid `/bin/true` attempt are retained as discovery evidence,
not ordinary compiler samples. Native installation/cache contracts already
fingerprint runtime headers; this change does not bypass them.

Full macOS release qualification is not claimed: the existing release suite
has Bash 3.2 and Linux `/proc` assumptions. No complete compiler/GHC ratio, C
benchmark-game runtime result, or all-program speedup is inferred from this study.
