# Finite P1–P3 integration controls

These are maintained correctness controls, not a benchmark or general semantic
proof. They run against the **current checkout's** complete authenticated GHC
9.14.1 O2 producer. They neither select a historical compiler nor rebuild one.
Run serially with appropriate process-tree resource limits:

```sh
python3 -B tools/performance/crate-optimizations/run_controls.py \
  --producer /absolute/path/to/producer --output /absolute/fresh/controls
```

The literal Haskell oracles/harnesses come unchanged from the reviewed P1–P3
milestones, retained at `875e483de49655030c4ffba1995b60610a50273a`:

* P1: 154,072 selector differential, ordered identity/error and lazy-demand checks.
* P2: 2,503 fingerprint byte/error/lazy and write-order checks.
* P3: 922 prefix byte/digest/error/lazy checks, including signed seeds, mismatched
  declarations and unused interface summaries.

Only necessary test inputs are carried forward, not old execution receipts,
machine paths or the historical performance archive. Provenance manifests use
repository-relative paths. Oracles are never regenerated from candidate output.

P2's original outside-region check still compares the old source against the
exact P2 source from `9b64a23860477ddcb37f8b264d279deee43b8d9b`. The integrated
P3 source must match its separately reviewed full-file pin; the P2 fingerprint
region must be byte-identical except for one explicit comment correction.
P3's additional encoders receive their separate 922-control gate. This is not a
blind update of P2's original pin or a claim that P2 alone tests all P3 behavior.

Each runner authenticates the producer before/after, preserves copied producer
objects, checks exact test module/output inventories and retains failure logs.
P3 refuses Python optimization because its inherited checks use assertions.
All recorded receipts are local outputs, not repository inputs. These finite
controls do not run native compiler bootstrap or make a performance claim.
