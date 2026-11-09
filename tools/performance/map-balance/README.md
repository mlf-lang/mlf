# Map balance direction controls

`Bootstrap.Map.balance` keeps its initial total-size guard, then compares the two child sizes and tests the only possible heavy side. If `L + R > 1` and `L < R`, then `R > 0` and `L <= 3R`. If `L >= R`, then `L > 0` and `R <= 3L`. The selected `node`, `rotateL` or `rotateR` call therefore stays the same for every Integer size, including negative or inconsistent cached sizes. The unchanged total guard already demands both sizes; keys, values and descendants retain the selected branch's demands.

This removes one multiplication from the old balanced and left-heavy paths and adds a comparison to the right-heavy path. It adds no representation, cache or fallback. The ordinary benchmark and integration evidence are described in [the performance report](../../../docs/performance/map-balance-20261030.md).

## GHC controls

Run against an ordinary GHC 9.14.1 `-O2` producer built from this exact checkout:

```sh
python3 -B tools/performance/map-balance/run_controls.py \
  --producer /absolute/path/to/producer \
  --output /absolute/path/to/new/controls
```

The runner authenticates the complete producer and copies its ordinary objects. It compiles only the independent fixtures and test Main, then verifies that the dependency objects did not change. The original frozen A1 Map is authenticated through its unchanged historical runner and fixture hash. `BaselineMap.hs` is the complete Map at `823f3060`, with only its module declaration renamed; reversing that rename must reproduce SHA-256 `1fdf24d3b3874c76d246f098ee9361a7f93e7eb01f741e064347452976cdaf0a`.

The suite compares 24,649 unfiltered pairs of raw trees against the original frozen balance implementation, 400 mixed mutation steps against the qualified pre-change physical tree, and 30 handwritten demand/error-order probes. It covers negative, huge and inconsistent cached counts, both rotations, double rotations, partially defined fields and lazy stored values. Finite tests supplement the branch proof; they do not prove every possible partial-value observation.

The complete pre-change snapshot is needed for mutation traces because an earlier `unionWith` optimization already changed physical tree construction relative to the older A1 snapshot. The older oracle remains intact and is still used for direct balance and demand comparisons. No candidate helper computes an expected result.

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
