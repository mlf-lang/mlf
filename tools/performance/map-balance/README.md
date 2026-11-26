# Map balance direction controls

`Bootstrap.Map.balance` keeps its initial total-size guard, then compares the two child sizes and tests the only possible heavy side. If `L + R > 1` and `L < R`, then `R > 0` and `L <= 3R`. If `L >= R`, then `L > 0` and `R <= 3L`. The selected `node`, `rotateL` or `rotateR` call therefore stays the same for every Integer size, including negative or inconsistent cached sizes. The unchanged total guard already demands both sizes; keys, values and descendants retain the selected branch's demands.

This removes one multiplication from the old balanced and left-heavy paths and adds a comparison to the right-heavy path. It adds no representation, cache or fallback. The ordinary benchmark and integration evidence are described in [the performance report](../../../docs/performance/map-balance-20261030.md).

## Current Map controls

Use the maintained [Map policy runner](../map-policy/README.md). It compiles
ordinary control and independent reference modules at O0 and O2, checks Map
content, balance, cached counts, the recorded mutation trace and demand/error
order, and verifies this run's inputs remain unchanged.

The former GHC `run_controls.py` admitted current sources through the old A1
source-migration chain. It is archived at
`496dcae024cae1a93096d9bdb9d6b93e57359dc0`; use that tree when reproducing its
historical report. The current Map policy fixtures preserve the independently
specified raw-tree and demand cases without that preparation machinery.

## Native controls

```sh
python3 -B tools/performance/map-balance/run_native.py \
  --compiler /absolute/path/to/emlf \
  --gc-prefix /absolute/path/to/bdw-gc \
  --output /absolute/path/to/new/native-controls
```

Optionally pass `--baseline-compiler` to compile the frozen source with a separate compiler. Otherwise both source versions use the selected compiler. The runner copies the complete production Map/Types/Std sources, restores the exact frozen Map body for the reference side, preserves the existing `MapFolds.emlf` assertions, and adds `NativeCases.emlf.fragment`.

Both versions are freshly emitted and linked with ordinary Clang `-O2`. Checks include all original 1,024 subset pairs and key/laziness controls, nine literal complete tree shapes, one unused-value probe, and four first-error cases. Literal expected shapes are stored in `native-expected.txt`. Inputs, LLVM, runtime objects and executables remain pinned between operations.

This is a focused native behavior gate. It records the selected binary, source/header closure, BDWGC archive and GMP flags; it does not authenticate an entire native compiler/toolchain closure or establish runtime performance.

## Recalculate the confirmation summary

From the repository root, with SciPy available, this reads the committed chronological rows and recomputes the six independent block means and their nominal interval. The separate integration block is deliberately excluded.

```python
import json, math, statistics
from scipy.stats import ttest_1samp

with open("docs/performance/map-balance-20261030-evidence.json") as source:
    rows = json.load(source)["confirmation"]["chronological_runs"]
assert len(rows) == 24
assert len({r["command_receipt"]["path"] for r in rows}) == 24
blocks = []
for block in range(6):
    legs = [r for r in rows if r["block"] == block]
    assert [r["index"] for r in legs] == [0, 1, 2, 3]
    assert all(math.isfinite(r["wall_seconds"]) and r["wall_seconds"] > 0 for r in legs)
    pairs = []
    for start in (0, 2):
        pair = {r["side"]: r["wall_seconds"] for r in legs[start:start + 2]}
        assert set(pair) == {"A", "B"}
        pairs.append(math.log(pair["B"] / pair["A"]))
    blocks.append(statistics.mean(pairs))
ci = ttest_1samp(blocks, 0).confidence_interval(confidence_level=0.95)
print("improvement:", 1 - math.exp(statistics.mean(blocks)))
print("nominal 95% interval:", 1 - math.exp(ci.high), 1 - math.exp(ci.low))
```
