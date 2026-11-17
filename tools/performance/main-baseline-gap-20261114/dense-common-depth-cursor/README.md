# Owned dense LCA depth cursor

Experimental snapshot on main `fc300bc9`, 17 November 2026. **CONTINUE SIGNAL ONLY. Do not merge on this evidence.** This is not the earlier unboxed-array candidate and not cross-call caching.

The fresh-owned rebinding path carries the two completed binder depths through one LCA traversal instead of re-reading both depth arrays at every climb. Parent lookups, placement of both candidate and structural parents, validators and first-error ordering remain. Original public raw `densePlace`/`denseCommon` entrypoints stay byte-identical. New helpers have a call-discipline precondition, not language-enforced privacy. Total parent traversal remains O(h); only repeated depth reads change from O(h) to O(1) per LCA.

## Foundation screening result

One ordinary GHC candidate producer, same 95 home-module closure and non-path optimization/package flags as the authenticated baseline. The only source change is the Graph patch. Builds use separate input/output layouts; this measures the whole candidate, including the cloned Owned DFS, not an isolated attribution to one array read.

| Pair | A wall s | C wall s | A peak RSS KiB | C peak RSS KiB |
| --- | ---: | ---: | ---: | ---: |
| A1 / C1 | 21.239459188 | 19.627271401 | 696820 | 575856 |
| A2 / C2 | 20.872034636 | 19.677588483 | 696668 | 575856 |

Fixed execution order A1 C1 C2 A2, after separate A/C qualification. Wall ratios are 0.924095 and 0.942773, geometric ratio 0.933387. Peak RSS ratios are 0.826406 and 0.826586. The pre-registered continuation gate required both wall ratios <= 0.97, geometric ratio <= 0.95 and both RSS ratios <= 1.05. It passed. These are only two pairs, not a statistical or stable-speedup claim. Wall is parent-observed Popen-to-wait4 time and includes polling delay. Peak RSS is not allocation or retained heap. The full C ELF grew 10,512 bytes, 0.052060%; this is not a text-section measurement.

## Qualification and limits

The one O2 focused executable compiles baseline and candidate Graph modules together, sharing real Types. All 21 cases / 84 files match A=C=expected including physical IntMap representation. A 12-node Bot/Bot merge reaches the actual owned two-climb route (6,4) -> (3,2) -> (1,1). The old six-node success fixture did not establish that coverage and was replaced before any execution; its original draft is preserved privately. This is not non-Bottom graft coverage. Raw alias, colour, initial-depth demand and parent-error cases remain. Signed raw LCA is not complete signed/sparse graph qualification.

Two real `--type` qualifications and all four timed executions on the identical Root plus Foundation15 paths returned exact `Bool` plus LF, empty stderr and no cwd artifacts. There were 15 actual focused and 95 actual ordinary home modules. GHC compilation warnings remain in the raw record, rather than being mislabeled empty stderr. Original source, controls, actual objects/interfaces, binaries, output and failed preparation/audit attempts are retained privately with complete Library readback. No native A/B, production qualification, main/PR change or merge occurred.

## Next decision

Reuse these exact A/C producers on a different real checking workload with fixed qualification and pair order. Do not add Foundation samples to rescue or inflate this result. A cross-workload failure or unresolved semantic boundary blocks promotion.

See `DESIGN.md`, `candidate.patch`, `Focused.hs`, `PINS.json`, `foundation-screen.json` and `audit-summary.json`. The focused source is compiled beside unchanged Bootstrap.Graph and a Candidate.Graph module made by renaming the patched Graph module; flags include `-O2 -fpedantic-bottoms -fno-state-hack`, explicit global package database, and the same real host C implementation. This seven-file archive is an experiment, not an executable claim of complete CI qualification.
