# Owned dense LCA depth cursor

Experimental snapshot on main `fc300bc9`, 17 November 2026. **CONTINUE SIGNAL ONLY. Do not merge on this evidence.** This is not the earlier unboxed-array candidate and not cross-call caching.

The fresh-owned rebinding path carries the two completed binder depths through one LCA traversal instead of re-reading both depth arrays at every climb. Parent lookups, placement of both candidate and structural parents, validators and first-error ordering remain. Original public raw `densePlace`/`denseCommon` entrypoints stay byte-identical. New helpers have a call-discipline precondition, not language-enforced privacy. Total parent traversal remains O(h); only repeated depth reads change from O(h) to O(1) per LCA.

## Historical Foundation screening result

One ordinary GHC candidate producer, same 95 home-module closure and non-path optimization/package flags as the authenticated baseline. The only source change is the Graph patch. Builds use separate input/output layouts; this measures the whole candidate, including the cloned Owned DFS, not an isolated attribution to one array read.

| Pair | A wall s | C wall s | A peak RSS KiB | C peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| A1 / C1 | 21.239459188 | 19.627271401 | 696820 | 575856 |
| A2 / C2 | 20.872034636 | 19.677588483 | 696668 | 575856 |

Fixed execution order A1 C1 C2 A2, after separate A/C qualification. Wall ratios are 0.924095 and 0.942773, geometric ratio 0.933387. Peak RSS ratios are 0.826406 and 0.826586. The pre-registered continuation gate required both wall ratios <= 0.97, geometric ratio <= 0.95 and both RSS ratios <= 1.05. It passed. These are only two pairs, not a statistical or stable-speedup claim. Wall is parent-observed Popen-to-wait4 time and includes polling delay. Peak RSS is not allocation or retained heap. The full C ELF grew 10,512 bytes, 0.052060%; this is not a text-section measurement.

## Async checking screen after exact recovery

The cloud workspace was replaced after the completed Foundation batch. Original A/C binaries and their evidence were recovered byte-for-byte, with all four runtime libraries matching; no producer was rebuilt. A new independent lease and new paths were used. First both producers requalified on Foundation, then on the nine-module Async checking input. These four qualification calls are excluded from all paired statistics. Historical Foundation timings are not pooled with the new-machine data.

| Pair | A wall s | C wall s | A peak RSS KiB | C peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| A1 / C1 | 12.519230173 | 12.612190850 | 457136 | 413028 |
| A2 / C2 | 12.624205359 | 12.003465056 | 457136 | 413028 |

Fixed order C1 A1 A2 C2. C/A wall ratios 1.00742543 and 0.95082936 mean one pair was 0.7425% slower and the other 4.9171% faster; the geometric reduction was 2.1282%. Both OS peak RSS values were 9.6488% lower. The separately pre-registered cross-workload screen required each wall ratio <= 1.03, geometric ratio <= 1.00 and each RSS ratio <= 1.05. It passed only as **CONTINUE SIGNAL ONLY**. Mixed timing direction and two pairs do not establish stable improvement.

All ten steps exited zero. Both runtime inspections plus eight semantic invocations completed, with exact Bool LF, empty target stderr and empty semantic working directories. The Async root imports Async.Task but checks the source only, not asynchronous runtime behavior. Original output, cleanup, new-lock receipts and admission evidence have complete private Library readback. This does not retrospectively prove termination of the replaced platform's entire execution scope.

## Historical initial qualification and limits

The one O2 focused executable compiles baseline and candidate Graph modules together, sharing real Types. All 21 cases / 84 files match A=C=expected including physical IntMap representation. A 12-node Bot/Bot merge reaches the actual owned two-climb route (6,4) -> (3,2) -> (1,1). The old six-node success fixture did not establish that coverage and was replaced before any execution; its original draft is preserved privately. This is not non-Bottom graft coverage. Raw alias, colour, initial-depth demand and parent-error cases remain. Signed raw LCA is not complete signed/sparse graph qualification.

Two real `--type` qualifications and all four timed executions on the identical Root plus Foundation15 paths returned exact `Bool` plus LF, empty stderr and no cwd artifacts. There were 15 actual focused and 95 actual ordinary home modules. GHC compilation warnings remain in the raw record, rather than being mislabeled empty stderr. Original source, controls, actual objects/interfaces, binaries, output and failed preparation/audit attempts are retained privately with complete Library readback. No native A/B, production qualification, main/PR change or merge occurred.

## Parser23 checking screen (same recovered environment)

Unchanged A/C binaries checked22 exact main-fc300 source modules plus a Bool root,422605 bytes. This is the Parser import closure, not the entire frontend crate or parser action execution. Two A/C qualifications preceded four samples. All six returned exact Bool LF, empty stderr and empty cwd. No rebuild, retry or pooling with historical-machine timings.

| Pair | A wall s | C wall s | A peak RSS KiB | C peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| A1 / C1 | 47.081033420 | 46.387380631 | 1311272 | 1305068 |
| A2 / C2 | 47.945652118 | 46.300146119 | 1311144 | 1305068 |

Fixed A1 C1 C2 A2. Wall ratios 0.9852668317 and 0.9656797660, geometric 0.9754241351. The each-wall<=1.03 / geometric<=1.00 / each-RSS<=1.05 screen passed as CONTINUE SIGNAL ONLY. Two pairs do not prove stable speedup or significance. Qualification excluded. Raw evidence and independent audit have complete local readback but the Parser ZIP is local-only, not yet in Library. See parser-screen.json, parser-source-pins.json and ParserWorkloadRoot.hs.

## Additional finite Graph qualification

CI run44112484188 passed the independent29-case/124-file Graph gate under both O0 and O2, including fixed expectations and qualification sidecars. This is finite graft/dispatch/error qualification only, not arbitrary-state Solver, production, native or performance qualification. Earlier failed installation attempts remain retained.

## Additional finite Solver qualification

CI run44123639110 at commit a55a27d7262bf3ef46da1e3449be1bac9760a512 passed independent raw-artifact review. Each O0/O2 build had17 actual homes,17 objects and17 interfaces from33 source inputs. The four real Solver transaction groups together produced 32 exact sidecars per mode: full raw A=C=literal expected, all original snapshots unchanged across A/C before/after, and every result PASS. Snapshot strings were fully forced, including each Char, before transactions. This extends the separate29-case Graph O0/O2 qualification, but does not establish arbitrary unforced payload demand, independent hidden-stub, captured prepared-fallback, full Constraint, production or native-backend qualification.

Installation131.349210347s and focused32.506865752s are control/resource costs, not performance evidence. Aggregate compilation22.847628831s/120 and targets0.212144429s/20 stayed within bounds. GHC stderr retained8561 bytes and17 warnings per mode; configure stderr retained41098 bytes. Only the two target stderr streams were empty. Earlier run44121981308's30-second configure timeout remains a separate failure. The corrected configure allowance60s stays within installer300s whole/280s work; focused limits and all source inputs were unchanged.

The original Solver ZIP contains193 entries/22354351 uncompressed bytes and was independently audited. Its identity is recorded in PINS.json; no Library upload is claimed. The unchanged parser-screen.json is the historical Parser-only snapshot: its solver_next pending text reflects that earlier preparation and is superseded by this audited Solver result and the next decision below.

## Next decision

The experimental candidate may continue to qualification testing, not merge or promotion. Next is one new A reference and one C qualification on the mature Foundation15 whole-crate raw-artifact endpoint, with strict original artifact checks. This is not a timing experiment and has not started. Parser's identical Bool output is not equivalent to full checked-artifact equality. Do not add identical short timing samples, change main/PR or resume native A/B. Remaining semantic gaps continue to limit claims.

See `DESIGN.md`, `candidate.patch`, `Focused.hs`, `PINS.json`, `foundation-screen.json` `async-screen.json` and `audit-summary.json`. The focused source is compiled beside unchanged Bootstrap.Graph and a Candidate.Graph module made by renaming the patched Graph module; flags include `-O2 -fpedantic-bottoms -fno-state-hack`, explicit global package database, and the same real host C implementation. This archive is an experiment, not an executable claim of complete CI qualification.
