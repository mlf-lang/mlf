# Dense parent placement experiment

Status: small experimental candidate, O0/O2 correctness gate passed. No compiler
producer, benchmark or full endpoint has run, and no speedup is claimed.

Baseline: `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
Only production owner: `libraries/mlf-inference/Bootstrap/Graph.hs`.
Original SHA-256: `9df4833f55f0826181f8e1e974dc0672753e9462de0d134f64fc3f8c6f6e8a7f`.
Candidate SHA-256: `257c738b1c84446f02dda46b10139b2488e4ac95c8d353e6d0a1b77dca76110e`.

## Mechanism and limits

For a nonzero graft flag, `densePlace` first traverses `originals ++ ps`. Only
when that traversal succeeds does the changed branch skip the second traversal
of `ps`. Each parent is already complete (colour 2), and no intervening mutation
occurs. The first traversal still checks every dependency and detects cycles.
The zero-graft path, failures, and first-error ordering are unchanged. No array,
validation, graph operation, or host adapter is removed. No freeze optimization
is included.

The bounded profiling prefix assigned only 0.630% inherited time to
`densePlaces1`, and 1.622% to `densePlace`; this redundant traversal is a subset.
Those diagnostic proportions are not ordinary runtime shares or speedup bounds.
This patch is a small cleanup candidate, not the main compiler acceleration.

## Independent gate

`run.py` authenticates the ordinary baseline producer and frozen f9 Graph, then
creates LegacyGraph and CandidateGraph by reversible module-header changes.
All other modules are copied authenticated producer objects. Each C support
object is rebuilt privately with the original authenticated compiler, source,
and flags, and must byte-match the original before linking.

The gate covers exact validation errors for 12,000 finite graphs; complete
public graph results, Patricia shapes, links, counters and first errors for the
oracle-selected legal graphs with flag/equation combinations; 480 signed-Int64
and sparse layouts; 20 authored placement demand/error/state fixtures; and six
same-type scratch-array alias cases (five successful placements, one entry cycle). Poisoned unused input cells are not forced
by the observer. The graft-parent coverage count uses only the frozen oracle's
successful rebinds and is not an actual compiler frequency measurement.

The default `--optimization both` executes O0 then O2 in fresh subdirectories.
Both preserve `-fpedantic-bottoms -fno-state-hack`. The runner requires the sprint
outer resource lock and holds the frozen source's inner reproduction lock.
One outer Runner encloses both complete builds, controls, authentication and
postchecks in a shared 240-second hard wall budget and process group. No inner
command starts a new session or resets the budget. Standard memory/disk guards
apply to the entire scope.

Example (paths supplied by the caller):

```
flock -n "$SPRINT_LOCK" python3 -B tools/performance/dense-place/run.py \
  --producer "$PRODUCER" --producer-source "$FROZEN_SOURCE" \
  --optimization both --output "$FRESH_OUTPUT"
```

Optional `--bench-repetitions N` runs a synthetic public-unification corpus,
with two warm-ups and two fixed ABBA blocks. Each batch varies graph identities
from a runtime repetition index, consumes the entire serialized result, and
requires identical checksums. This is neither native A/B nor a generation or
fixed-point test: both functions run in the same ordinary GHC executable.
Its result must not be reported as source-to-checked/compiler speedup. No full
compiler producer or 600-second compiler endpoint is part of this runner.

## Recorded gate

Attempt 03 passed both O0 and O2 gates in a single 34.714-second scope. Each
reported 12,000 validation cases, 5,616 public unifications, 1,433 successful
frozen rebinds with 16 graft-parent edges, 480 layouts, 20 demand/failure cases,
and six alias cases (five successful placements and one entry cycle).
Input pins and the producer were reauthenticated, both C rebuilds matched,
no descendants remained, and both locks were free. No performance sample ran.

Attempts 01 and 02 remain failures: a Main layout parse error (11.418 seconds),
then a binary/log-directory name collision after successful O0 linking
(12.353 seconds). Neither executed controls. They are not semantic failures or
passed gates. Both harness defects are corrected in this checkpoint.

`results.json` is a safe summary with receipt hashes, not raw receipts. Full
local receipts, object tables, binaries and raw build logs are not committed
and have not been remotely persisted. Reproduction must create fresh outputs.
Results belong only to their exact owner and harness hashes.
