# Foundation solvePrepared boundary localization (diagnostic E)

One instrumented ordinary-GHC compiler E ran the unchanged normal Foundation library boundary: 15 baseline modules, 211763 source bytes, NoEntry, a fresh query cache and the existing read-only builtin dependency. This is not the full 90-module workload or a native/package build.

The run passed original A's raw CI/CO byte equality and the original ordered 532 fresh groups / 539 members / 14 value-owner witnesses. The complete query report was also byte-identical. Independent actual review passed. All 1,670 actual files (12,007,767 bytes) were privately archived and read back with exact bytes and modes.

## Observed result

Direct-child wait4: wall 25.477982665s, CPU 25.520441s, maxRSS 139692 KiB. These are diagnostic statistics, **zero performance samples**. Do not compare A/C/D/E times as a speedup.

The inclusive solvePrepared interval was 15764 ms. Its four natural children were:

| Natural boundary | Wall ms | Scope |
| --- | ---: | --- |
| prepare | 638 | Graph/live-alias/fresh-ID checks to the original Either constructor; index payload may remain deferred. |
| unify | 2339 | Canonicalization, node-existence validation and pending-equation unification. |
| evaluatePreparedSteps | 11186 | Original ordered Instantiate/ProjectCase fold; may demand deferred earlier work. |
| finishNormalized | 1596 | Full graph/index/scope audit before returning a lazy normalized graph payload. Neither normalization cost nor exclusive audit cost. |

The evaluatePreparedSteps boundary is the largest observed child, about 70.96% of solvePrepared. This localizes the next source boundary to inspect; it does not isolate per-step operations, justify removing checks, or establish causal CPU costs.

## Minimal source change

Baseline main is `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. Fresh compiler E uses ordinary GHC 9.14.1 -O2 and 95 Haskell modules, with baseline IntRank. Its ELF SHA-256 is `aebbc19f0922a1437c1b94c1c4be5f484171ab90ad3dd2fedd17934321199379` (20232104 bytes).

The full baseline-relative `diagnostic.patch` contains the four-module diagnostic overlay. Relative to D, `from-D.delta.patch` changes only CompilerCore and QueryGraph. InferenceUnit and CrateGraph retain D's exact bytes. Constraint, Solver and original pure APIs remain untouched.

CompilerCore mirrors exactly Constraint.solvePrepared's four ordered binds. The existing explicitly polymorphic local observer receives clock/elapsed callbacks, observes only the required Either constructor, preserves Left short-circuiting and the caller's atPhase Inference mapping. No deep forcing, extra normalization, audit removal, new module/import edge or pure API replacement is used.

## Nested 23-field accounting

`summary.json` retains all 23 actual integer wall-ms values. The original six top-level buckets remain. Infer contains compile-open/canonical/prepared-validation/record; compile-open contains its seven D children; solve-prepared contains the new four children; record contains encode/digest. **Parents and descendants are not disjoint costs and must not be summed together.**

Five signed residuals: CLI 860982665 ns; infer 2 ms; compile-open 13 ms; solve-prepared 5 ms; record 3 ms. Residuals are retained without clamping. Integer-ms truncation, clock/callback overhead, lazy work migration and changed generated code can affect attribution. In particular, normalization returned by finishNormalized may be demanded later in evidence/elaboration. These labels are neither exclusive CPU cost centres nor proof of natural causality.

## Boundaries and retained history

Exactly one target, 180 s target / 300 s phase allowance, AS 4 GiB, no retries or extra samples. Raw equality is workload-specific, not an independent typed decoder or proof for all inputs. wait4 maxRSS is not a measured simultaneous process-tree peak.

Main is unchanged; native generation and fixed point remain paused. The earlier full 90 A-only OOM251 phase remains INCONCLUSIVE, not a B regression. Its observed error under the existing 4 GiB limit does not establish that the precise cap was exceeded. No performance/merge decision follows this localization.

This public snapshot contains only this README, sanitized data, two repository-relative patches and a checksum manifest. No private paths, execution/storage IDs, controller code or binary payloads are included.
