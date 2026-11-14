# Fixed48 observations: actual review PASS

The independent fixed48 actual review passed, followed by a 66-check descriptive reduction against every independently reviewed observation. The separate independent summary review also passed, with all 48 values, 12 groups and 16 gradients checked. Original SEMANTIC still remains FAIL; the separate completion/composite gate was not rewritten.

12 cells retained the fixed M,G,G,M order. Every endpoint/cell has **two observations only**. All 48 same-binary raw output comparisons matched without normalization or exceptions. No retry, discarded sample, hidden warmup or added target.

## Foundation14

|Metric|MLF frontend, both observations|GHC typed-only, both observations|Ratio of two-observation means M/G|
|---|---|---|---|
|RTS Total CPU s|20.564 / 21.129|0.544 / 0.546|38.25×|
|RTS MUT CPU s|16.833 / 17.366|0.244 / 0.241|70.51×|
|RTS GC CPU s|3.729 / 3.762|0.297 / 0.300|12.55×|
|Child guard elapsed s|20.807319 / 21.378982|0.683273 / 0.695035|30.61×|
|Allocated bytes|60,608,900,384 / 60,608,900,384|511,558,192 / 511,553,264|118.48×|

MLF mean Total CPU is 20.8465 s, approximately 82% MUT and 18% GC. This gap is therefore not solely GC time, but MUT is all non-GC runtime work, not attribution to any specific compiler algorithm.

## Size ladders

For n=16,32,64,128,256, mean Total CPU seconds are:

- flat/M: 0.279,0.339,0.461,0.850,1.4535. Endpoint growth n16→256:5.21× CPU,6.10× allocation.
- flat/G: 0.136,0.1625,0.1255,0.176,0.197. Growth:1.45× CPU,2.57× allocation.
- chain/M: 0.265,0.3105,0.3135,0.388,0.5445. Growth:2.05× CPU,2.39× allocation.
- chain/G: 0.1205,0.1225,0.1425,0.138,0.1365. Growth:1.13× CPU,1.19× allocation.

These five sizes and two observations do not prove linearity, asymptotic complexity or stable differences. Baseline CPU M0.242/0.240 s and G0.141/0.085 s is shown separately, not subtracted. Baseline0 and Foundation None have no per-n division. All pairs, means, source-byte normalizations and adjacent gradients are in `results/results.json`.

## Interpretation limits

MLF emits checked/published frontend artifacts; GHC does typed-only compilation and writes interfaces. Same source inputs do not make equivalent complete-compiler endpoints. These are descriptive endpoint ratios, **not GHC parity, stable speedup, significance or production claims**.

RTS times are rounded; guard elapsed includes supervision and is not exact target wall. Maximum residency is sampled major-GC live memory, not RSS; copied bytes mean GC copying, not compiler graph-copy counts. No graph/visit/constraint counters were measured. Fresh query/application state does not mean cold OS caches. Lifecycle 1099.706496775 s includes failed qualification/completion/authentication/cleanup and is not compiler performance.

Current status comes from `results/report.json` and `evidence/combined-final-review.json`. The generated JSON's generic pending placeholder is intentionally retained, not the current gate status. Raw values are in both observations CSVs and `evidence/all48-rts-redacted.json`; large raw trees and binaries are private, explicitly not present.
