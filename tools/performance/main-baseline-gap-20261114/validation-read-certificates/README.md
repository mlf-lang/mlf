# Validation read certificates: finite mechanism model

This is a **synthetic Python dependency model**, not a translation of MLF Graph validation, a production patch or a performance result. The only executed version is v2. Version v1 is an unexecuted earlier draft, retained through the exact `v1-to-v2.patch`; the update improved finite controls and accounting rather than repairing a confirmed executed semantic failure.

The single controlled execution reports **17 named checks passed and three deliberately defective dependency policies caught**. `results.json` is the exact original stdout, not a reformatted summary or a second run. The broken modes omit absent-cell reads, control reads or subfact dependencies. The control mutant and repair/redirect/cycle cases have aggregate reports rather than separately printed intermediate outcomes; their exact assertions remain in the pinned source. “Caught” means the test exposed disagreement with fresh evaluation; it does not mean those policies are supported.

## What the counters show

For the synthetic balanced tree (63 Arrow/Leaf nodes plus one Gen root):
- Cold construction records 192 facts and 573 dependency edges.
- One rightmost leaf kind write invalidates six facts.
- Subsequent evaluation computes six facts, compared with 130 for fresh evaluation of the changed cells.
- **Both evaluations end with the same `Left:arrow-kind` error.** This is an early-failing toy case, not a full successful validation or a speedup.
- After warm failure, 187 facts / 548 dependency edges remain, versus 125 / 300 after fresh failure. Reuse has a retained-state cost.

The small all-fields-written case invalidates all 12 cold facts with 33 invalidation visits, then computes all 12 again. Equal-value writes still invalidate. The unchanged case replays the entry checks, performs two reads and eight hits, with no new fact computation.

These are logical operation and retained-cardinality counts, **not elapsed time, CPU, heap bytes or peak residency**. Forward and reverse edge counts describe separate indexes over the same logical relation; neither is a byte estimate. Cold construction, writes and invalidation are not free and must not be omitted from a future comparison.

## Files

- `model_validation_certificate.py`: exact v2 source.
- `v1-to-v2.patch`: exact source delta; no MLF production file is changed.
- `results.json`: exact single-run stdout.
- `DESIGN.md`: one proposed transaction-local validation direction and its unmet assumptions.
- `EVALUATION.md`: minimal qualification, cost accounting and stop contract.
- `PINS.json`: exact source/result and independent-review identities without private locations.

The source uses only Python's standard library, creates synthetic cells in memory and prints JSON. It has its own 30-second alarm and finite size limits. No repository, real graph input, compiler, network, binary or production wrapper is required by the model. This archive does not authorize or include another execution.

## Current decision

The finite mechanism is demonstrated within this toy semantics. **No real shadow producer is admitted by this result.** The production dependency set, write log, Haskell demand/error equivalence and end-to-end accounting remain unproved. The immediate next step, if separately approved, is a Haskell full-field/per-edge dependency observer design and finite gate, not a real shadow run. Existing validation, placement and rebinding remain unchanged. Native work remains paused; no main/PR change or merge is part of this archive.
