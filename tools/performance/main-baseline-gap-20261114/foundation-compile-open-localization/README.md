# Foundation checked compile-open localization

This follow-up diagnostic builds a new compiler **D** from baseline main `fc300bc9fdc389b585cbef0630fc8915d53e89c5`. It preserves baseline IntRank and all original pure compilation APIs. The full four-module patch and a smaller delta from diagnostic C are included. Existing A/B/C results are not replaced.

The previous localization pointed inside the inclusive compile-open interval. D adds explicit IO observation entries in CompilerCore and InferenceUnit, with callbacks for the existing clock and elapsed counters. It does not pass a polymorphic observer as an ordinary parameter or import QueryGraph back into inference. CrateGraph routes the diagnostic cold path to these entries; QueryGraph appends seven counters.

## Nineteen fields form a hierarchy

- Original six: graph, load, infer, finish, output, publish.
- Inside **infer**: compile-open, canonical, prepared validation, raw record.
- Inside **raw record**: encode and digest.
- Inside **compile-open**: prepare, generate, solve-prepared, evidence/elaboration, closed check, type/erasure agreement, open admission.

These are not nineteen disjoint costs. Keep inclusive parents and report four signed unclassified residuals separately: CLI minus the original six, infer minus four children, compile-open minus seven children, and record minus encode/digest. Never add parents and descendants, clamp negative residuals or demand exact conservation.

The observers select only Either constructors already needed by the original binds. Original checks, failure ordering and lazy successful payloads remain; there is no deep forcing to manufacture timing boundaries. Later checks or serialization can force earlier work, and IO instrumentation can change GHC optimization. These are instrumented wall intervals, not exclusive CPU costs or natural causal attribution.

In particular, **solve-prepared includes validation**: prepare, unification, prepared steps and finishNormalized, whose finish path audits the full graph and indexes. Generation includes its own validation; open admission includes the parameter/body adapter, datatype environment and independent declaration-spine checking. Labels do not remove those costs.

## Fixed diagnostic contract

Use exactly the baseline normal Foundation15 library sources (211763B), crate `mlf-foundation/0.3.0/library`, NoEntry, the existing read-only builtin dependency and a fresh query cache. Compiler overlay files are not workload sources. One D target is allowed, with a 180 s target / 300 s phase cap and the unchanged 4 GiB per-process address-space limit. There are zero performance samples, no retries, no A/B/C rerun or extra Solver samples, and no native/fixed-point run.

Success requires original A Foundation raw CI/CO byte equality, original ordered 532 fresh groups / 539 members / 14 value-owner witnesses. Complete queries are retained and equality is additionally reported. Direct-child wait4 supplies target wall/CPU/maxRSS; maxRSS is not simultaneous process-tree peak.

## Actual result

The sole D target passed: 24.077424109 s wall, 24.113987 s CPU (23.879555 user + 0.234432 system), wait4 maxRSS 137320 KiB; whole phase 42.758155343 s. Original A raw CI/CO, original ordered 532 fresh groups / 539 members / 14 owners and complete queries all matched. Post-input checks, cleanup and lock reacquisition passed. Independent actual-run review passed, including all 1670 recorded actual files and the reference comparisons. Complete actual bytes/modes were also privately archived and read back; storage identifiers are omitted.

The inclusive compile-open interval was 19516 ms. Its seven child observations were:

| Child interval | ms |
| --- | ---: |
| prepare |64 |
| generate |1749 |
| solve-prepared (includes audit) |14902 |
| evidence/elaboration |2307 |
| closed check |317 |
| type/erasure agreement |6 |
| open admission |159 |

Signed residuals were CLI 785.424109 ms, infer 4 ms, compile-open 12 ms and record 3 ms. All 19 original numeric fields are retained in `summary.json`. Within this instrumented observation, solvePrepared accounted for about 76.36% of compile-open; the remaining question is how much belongs to its prepare/unify/evaluation/final-audit boundaries. It is not evidence to remove checks or a pure-solver attribution.

A/C/D times must not be compared as an optimization gain. This is one workload-specific localization with zero performance samples, not general semantic proof or whole-package qualification.

Patch paths are repository-relative. Private runners, local paths, storage/access identifiers and raw binaries are excluded.
