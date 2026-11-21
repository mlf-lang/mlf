# Two-stage compiler phase study, 2026-11-15

This study continues from `590b8317059f1759e006b32cdf1857d26e0a0fb0` on
`codex/flat-functions-performance`, preserving the earlier uncommitted compiler,
package-manager and fused-driver work. It measures the original disk-backed
`crate-bootstrap-v1` endpoint. The default `crate-fused-v1` endpoint remains a
separate comparison; its samples never substitute for the original entry.

After three qualified rounds, the requested time/slope/exponent target is still
not met. The old entry wins every positive-size median, but its final OLS
slope is 21.4% higher than paired GHC and its fitted exponent is higher over
this measured range. The default fused entry is faster, while its final slope
and exponent differences are not established by the paired intervals.
Finite-range fitted exponents do not establish either compiler's asymptotic complexity.

## Workload and measurement

The same unsigned polymorphic dependency chain as
[the preceding study](compiler-polymorphic-chain-2026-11-15.md) is compiled at
N=32,64,128,256,512,1024, plus the empty baseline. Every generated function is
reachable, and the chain is used at both `Int` and `Bool`. Both compilers receive
identical source bytes. Three independent closed-form runtime oracles check each
result. All target and query caches are fresh; OS caches are not flushed.

The primary comparison uses 12 alternating paired repetitions per size;
the supplemental fused comparison uses six. GHC is 9.14.1, `--make -j1 -O2
-fforce-recomp`; MLF is an authenticated GHC-hosted O2 producer followed by
Clang O2. This is not a native self-hosted compiler qualification. Builtin,
primitive-package and runtime setup remain outside both timed target legs.
The existing resource guards remain unchanged.

Before the formal runs, `final-analysis-plan.json` fixed these requirements:
all positive-size MLF medians lower; endpoint and OLS slopes lower; and the
upper ends of paired 95% bootstrap intervals for both the OLS difference and
fitted exponent difference below zero. The model is
`T(N) = a + b * (N / max(N))^p`, with nonnegative a/b and p in [0.1,3].
Linear, N log N, quadratic, source-byte and restricted-range fits are also saved.
Bootstrap resampling preserves per-size compiler pairs (2,000 draws, seed
20261115). Twenty-six synthetic controls recover known powers and linear/
quadratic coefficients. An unqualified claim of lower Big-O cannot follow from
these measurements, even if all finite-range conditions pass.

N=1536 and N=2048 probes fail with the existing `cyclic/deep query graph` limit.
A source dependency chain expands into multiple query nodes per function.
The 4096 query-depth guard was not relaxed; failed commands are retained and
excluded from fits. The observed range therefore cannot support extrapolation
to arbitrarily large programs.

## Exclusive phase clocks and retained changes

`MLF_CRATE_PROFILE=FILE` records the uncached disk entry's read, decode,
validation, linking, checking, optimization and emission counters. See
[the command and field definitions](crate-compilation.md#profiling-the-disk-to-llvm-entry).
Nested phases are exclusive; the clock has millisecond resolution. Profiling
forces lazy results at diagnostic boundaries, so formal performance comparisons
leave both `MLF_CRATE_PROFILE` and `MLF_QUERY_PROFILE` unset. LLVM stdout and
checked artifact bytes remain separate from diagnostic output.

The retained compiler changes are:

- Compare canonical interface fields directly instead of encoding and
  checksumming two entire interfaces. The framing is injective and determines
  the trailing checksum, so the comparison has the same exact semantics.
- Decode valid 1–16 bit fields by reading the necessary 1–3 bytes and masking
  once. The original generic reader remains for the other domains. There are
  7,920 differential offset/width/value/bounds/error cases against that reader.
- Replace parser declaration-group `nubBy` membership scans with an ordered
  set, preserving the original values and source order. Reuse the module
  interface's namespace/spelling map for duplicate admission, including exact
  duplicate entities that would otherwise disappear in a set. Existing error
  messages and distinct type/term namespaces are preserved.
- Reuse the interface's admitted binding/protection sets for inventory equality
  and entry membership. This avoids sorting both inventories and rebuilding a
  value map after the same keys have already been checked. Eight maintained
  positive/negative cases preserve duplicates, diagnostic priority, missing/extra
  protection, reorder equivalence and entry ownership.

The last change removes three quadratic duplicate scans on this workload: one
in parsing and two calls to local-module admission. At 1024 generated functions,
the profiled lists have 1027 entries and each linear-membership scan performs
roughly 526,851 comparisons. Balanced maps reduce this admission's comparison
count to O(N log N); this statement is about those checks, not the entire
compiler. New maintained controls exercise order, separated and contiguous
function equations, 1024 distinct declarations, duplicates at both ends,
constructor/value collisions and type/class collisions.

The optional profiler, direct-equality controls and bit-reader controls also
check unchanged LLVM, native runtime results, unchanged `.mlfci`/`.mlfco` files,
corrupt-object rejection and missing-file errors. Canonicality, work/depth
bounds, independent checking, cache publication and source identities remain.

## Diagnostic evidence

For the initial detailed old-entry profile at N=1024, interface decoding costs
20 ms, open-object wire decoding 57 ms, typed reconstruction 11 ms and embedded
Prelude decoding 15 ms. Remaining admission costs 52 ms, metadata hashing
22 ms, reference checks 2 ms and fragment checks 9 ms. Independent Prelude and
final checks cost 22 and 11 ms, linking 15 ms, optimization 9 ms. Read and emit
counters round to zero; this does not mean no IO occurred.

After exact interface comparison and the small-bit reader, corresponding
wire/typed decoding medians are 48/6 ms and remaining admission is 49 ms.
These small diagnostic samples locate work; they are not the uninstrumented
acceptance result or an isolated causal estimate of whole-compiler speedup.

The source stage at N=1024 spends approximately 143 ms producing artifacts and
98 ms publishing queries, versus 14 ms in the measured inference region.
Other parsing/resolution and lazy work falls outside those source clocks.
A GHC late-cost-centre build separately identifies the three quadratic scans,
codec byte loops and persistent-map allocation. Instrumented allocation/time
figures are diagnostic only.

Rejected and reverted experiments retain their receipts: a wider combined
CRC/symbol scan, a 16 MiB GHC nursery, natural merge sorting and streaming long
UTF-8 symbol text. Their end-to-end benefits were absent or too small to justify
retention. Natural sorting passed 29,529 stable-order comparisons; correctness
alone was not treated as evidence of a compiler performance improvement.

## First formal round

| N | Old entry MLF, s | Paired GHC, s | Fused MLF, s | Its paired GHC, s |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.372583 | 0.493542 | 0.318401 | 0.490981 |
| 32 | 0.393347 | 0.519577 | 0.333703 | 0.510681 |
| 64 | 0.406659 | 0.536772 | 0.347689 | 0.526560 |
| 128 | 0.450518 | 0.558023 | 0.376314 | 0.549666 |
| 256 | 0.510388 | 0.611187 | 0.437967 | 0.604455 |
| 512 | 0.667737 | 0.735478 | 0.555579 | 0.726895 |
| 1024 | 0.992218 | 0.959658 | 0.830887 | 0.963144 |

Old-entry OLS slopes are 0.602504 versus 0.448906 ms/function. The paired 95%
interval for MLF minus GHC is [0.144860,0.159252] ms/function. Fitted exponents
are 1.073997 versus 0.980581; their paired difference interval is
[0.051860,0.128147]. All primary acceptance conditions fail.

Fused OLS slopes are 0.497762 versus 0.458082 ms/function; fitted exponents are
1.086121 versus 1.022265. It wins every positive-size median, but fails the
slope/exponent conditions. The earlier historical baseline also recorded
0.673118 versus 0.504145 ms/function; the simultaneous GHC change means its
difference from this round is not an isolated attribution to compiler changes.

## Second and third formal rounds

The second round removes the quadratic declaration scans. It wins all sampled
times, but its old-entry OLS slope is 0.570032 versus 0.448673 ms/function.
Its p estimates are 1.058880 versus 1.089144; the paired difference interval
[-0.083082,0.023456] does not establish a lower exponent. The second fused
cohort has a lower slope interval but not a lower exponent. These intermediate
results remain archived; the later cohort does not replace or pool them.

A separate eight-pair source-only comparison alternates the first and second
qualified producers using identical source paths and fresh query directories.
At N=32, median times are 113.174 and 113.115 ms; at N=512, 318.393 and
309.225 ms; at N=1024, 564.133 and 519.675 ms (7.9% lower). All 54
compilations, including warmups, produce identical `.mlfci` and `.mlfco` bytes.
The historical producer is pinned to its original receipt/binary, not
misrepresented as authenticating the current checkout.

The third round adds interface inventory reuse. An isolated 12-pair disk-entry
comparison at N=1024 measures 249.463 versus 243.275 ms; the empty baseline
is effectively unchanged (98.759 versus 98.790 ms). All 52 LLVM outputs,
including warmups, match the original endpoint exactly. This diagnostic result
does not imply that the whole-pipeline acceptance target passed.

Final uninstrumented medians are:

| N | Old entry MLF, s | Its GHC, s | Fused MLF, s | Its GHC, s |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 0.372980 | 0.493614 | 0.320098 | 0.490512 |
| 32 | 0.386895 | 0.516236 | 0.336527 | 0.528197 |
| 64 | 0.403768 | 0.525646 | 0.348814 | 0.534839 |
| 128 | 0.439408 | 0.549829 | 0.380900 | 0.558273 |
| 256 | 0.510022 | 0.621556 | 0.440184 | 0.611793 |
| 512 | 0.654246 | 0.734750 | 0.543056 | 0.734325 |
| 1024 | 0.955719 | 0.977829 | 0.782715 | 0.964751 |

| Final metric | Old entry | Default fused entry |
| --- | --- | --- |
| OLS slope, MLF / GHC (ms/function) | 0.570796 / 0.470343 | 0.448166 / 0.452002 |
| Endpoint slope, MLF / GHC (ms/function) | 0.569081 / 0.472866 | 0.451774 / 0.463124 |
| Fitted p, MLF / GHC | 1.045189 / 0.999571 | 1.012273 / 0.995662 |
| 95% paired interval, OLS MLF minus GHC | [0.092674, 0.108661] | [-0.014217, 0.040167] |
| 95% paired interval, p MLF minus GHC | [0.021120, 0.106545] | [-0.330810, 0.096245] |

The old entry's lower startup floor keeps it ahead through N=1024, but the
observed per-function cost remains higher. Its final finite-range exponent
difference is also positive. The fused point slopes are lower, with a paired
interval spanning zero in the last cohort. Neither endpoint meets all fixed
conditions. It would be incorrect to claim completion of the requested target
or to extrapolate a lower asymptotic class. The remaining measured work is
primarily artifact encoding/admission, query publication and disk-entry decoding;
the measured inference/optimizer regions are much smaller.

## Final validation and reproducibility

The final `producer-v3/receipt.json` authenticates the exact nongenerated source
identity, regenerated builtin preparation and implementation signatures. The
lockfile was updated and `mlfpkg --locked plan` passed.
`regression-v3-clean/receipt.json` records 14 successful top-level commands:
wire constructors/admission/Base64/source admission/typed bounds, diagnostic
profile parity (11 checks), chain/fused/codegen-cache controls (36 checks),
flat and inferred controls (26 each), package fused controls (30), cold/warm/
dependency package smoke cases, and all 12 direct-suite commands with their
expected statuses. The first fixture compilation emitted partial-list warnings;
the fixture was rewritten with explicit known elements and qualified afresh.
The failed receipt remains in `regression-v3/`.

Each of the three formal rounds has 336 compilations and 1008 independent
runtime checks, with no correctness failures. Performance acceptance fails
separately. The 84 benchmark contract tests also pass. The final phase receipt
compares 20 disk-entry runs with the original LLVM output.

The chart is `growth-and-phases.png` (also SVG) under the task evidence directory.
It uses only the third-round receipts; it displays paired slope intervals and
keeps instrumented phase measurements separate from end-to-end wall times.

Final receipt SHA-256 values:

- `producer-v3/receipt.json`: `bdb971da8ce9eb2fff49dbc424dbd3d8f72e3b3bf47380b8368d00a8bdbc3355`
- `regression-v3-clean/receipt.json`: `fb9cb01ec851480ccbd3877e7981228cd62b20df537d8c5fd54ee651a4f8daab`
- `round3-staged/cohorts/growth/receipt.json`: `40f301691bb854f4a4f5b5bb51a2a54efc93a50e218835f391549f52be888d1d`
- `round3-staged/cohorts/regression/receipt.json`: `ab0a34430ca9038bb23a5d0c977e0486d2b65d0fcf6f29d557032e8448172e38`
- `round3-fused/cohorts/growth/receipt.json`: `254071aefe7f7f2e3850e145ef8c403b70e520a21c322728192aba95718ce4bf`
- `round3-fused/cohorts/regression/receipt.json`: `59c5e4985fda5e22fa7917cd126be4bf6f9e8692c408b57be8fb9caf7b026bed`

## Evidence locations

All task evidence is retained under
`.mlf-build/two-stage-phases-20261115/`:

- `initial-snapshot.json` and `initial.patch`: worktree ownership boundary.
- `baseline/cohorts/old-entry/`: original six-pair baseline.
- `producer-v1/receipt.json`, `regression/receipt.json`: first qualified build
  and 14-command regression campaign.
- `final-staged/cohorts/`, `final-fused/cohorts/`: first growth and six-family
  regression cohorts, 336 compilations and 1008 runtime checks without failures.
- `final-*-analysis.json`, `final-analysis-plan.json`, `analysis-controls.json`:
  fixed plan, full statistics, sensitivity and synthetic checks.
- `profile-detailed/`, `profile-equality/`, `profile-bitreader/`: diagnostic
  decomposition and unchanged-LLVM checks.
- `source-phases/`, `source-gc16/`, `source-sort/`, `source-text/`,
  `source-duplicates/`, `cost-centres/`: source diagnostics and rejected probes.

The native installed compiler gate is unavailable in this checkout because
`.mlf-build/package-manager/mlfpkg` is absent. GHC-hosted producer authentication,
native generated-program execution and the focused regression receipts must
not be described as successful native compiler bootstrap or a fresh full
79-case package campaign.
