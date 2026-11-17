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

## Qualification and limits

The one O2 focused executable compiles baseline and candidate Graph modules together, sharing real Types. All 21 cases / 84 files match A=C=expected including physical IntMap representation. A 12-node Bot/Bot merge reaches the actual owned two-climb route (6,4) -> (3,2) -> (1,1). The old six-node success fixture did not establish that coverage and was replaced before any execution; its original draft is preserved privately. This is not non-Bottom graft coverage. Raw alias, colour, initial-depth demand and parent-error cases remain. Signed raw LCA is not complete signed/sparse graph qualification.

Two real `--type` qualifications and all four timed executions on the identical Root plus Foundation15 paths returned exact `Bool` plus LF, empty stderr and no cwd artifacts. There were 15 actual focused and 95 actual ordinary home modules. GHC compilation warnings remain in the raw record, rather than being mislabeled empty stderr. Original source, controls, actual objects/interfaces, binaries, output and failed preparation/audit attempts are retained privately with complete Library readback. No native A/B, production qualification, main/PR change or merge occurred.

## Next decision

Do not add more identical short timing samples. The next minimal gate must extend real Graph coverage to non-Bottom grafts, signed/gapped dense and sparse dispatch, aliases, first-error ordering and lazy demand. The current cross-workload screen permits that investigation, not production promotion or merge. Semantic gaps remain blocking.

See `DESIGN.md`, `candidate.patch`, `Focused.hs`, `PINS.json`, `foundation-screen.json` `async-screen.json` and `audit-summary.json`. The focused source is compiled beside unchanged Bootstrap.Graph and a Candidate.Graph module made by renaming the patched Graph module; flags include `-O2 -fpedantic-bottoms -fno-state-hack`, explicit global package database, and the same real host C implementation. This archive is an experiment, not an executable claim of complete CI qualification.
