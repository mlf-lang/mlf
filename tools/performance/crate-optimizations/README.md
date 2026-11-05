# Finite P1–P3 integration controls

These are maintained correctness controls, not a benchmark or general semantic
proof. They run against the **current checkout's** complete authenticated GHC
9.14.1 O2 producer. They neither select a historical compiler nor rebuild one.
Run serially with appropriate process-tree resource limits:

```sh
python3 -B tools/performance/crate-optimizations/run_controls.py \
  --producer /absolute/path/to/producer --output /absolute/fresh/controls
```

The literal Haskell oracle bodies and original control inventories come from
the reviewed P1–P3 milestones, retained at
`875e483de49655030c4ffba1995b60610a50273a`:

* P1: 154,072 selector differential, ordered identity/error and lazy-demand checks.
* P2: 2,503 fingerprint byte/error/lazy and write-order checks.
* P3: 922 prefix byte/digest/error/lazy checks, including signed seeds, mismatched
  declarations and unused interface summaries.

Only necessary test inputs are carried forward, not old execution receipts,
machine paths or the historical performance archive. Provenance manifests use
repository-relative paths. Oracles are never regenerated from candidate output.

P2's original outside-region check still compares the old source against the
exact P2 source from `9b64a23860477ddcb37f8b264d279deee43b8d9b`. The integrated
P3 source (or the exact historical projection described below) must match its
separately reviewed full-file pin; the P2 fingerprint region must be
byte-identical except for one explicit comment correction.
P3's additional encoders receive their separate 922-control gate. This is not a
blind update of P2's original pin or a claim that P2 alone tests all P3 behavior.

## Native-library integration compatibility

The later native-library integration changes collection operations and adds
serialization helpers. Historical oracle bodies, excerpts, P2/P3 manifests and
the old-to-P2 fingerprint boundary remain frozen; their hashes are not simply
replaced with current source hashes.

* P1 now uses exact historical Map and Set implementations under test-only
  module names. Only the frozen selector's collection imports are adapted;
  nominal datatypes stay shared. Its 154,072 selector controls remain, with
  6,162 additional independent list-expectation collection controls. See
  [the dependency audit and demand limits](p1/DEPENDENCY-AUDIT.md).
* P2/P3 verify an explicit source-compatibility projection before admitting
  current dependencies. Historical Separate sources and fingerprint-region
  checks remain in force. P2 also runs separately authored controls for the
  changed distinctness helper, chunk printers and native summary encoders.
  These are additional checks, not replacement expected output learned from
  the candidate. See [the compatibility audit and partial-input
  limits](p2/NATIVE-COMPATIBILITY-AUDIT.md).

Cheap mutation tests enforce these compatibility boundaries in the release
checker. The original 2,503 P2 and 922 P3 runtime assertions remain separate
from the new controls. No historical receipt is relabeled as current execution.

Each runner authenticates the producer before/after, preserves copied producer
objects, checks exact test module/output inventories and retains failure logs.
P3 refuses Python optimization because its inherited checks use assertions.
All recorded receipts are local outputs, not repository inputs. These finite
controls do not run native compiler bootstrap or make a performance claim.

## F1 host dependency re-audit

The later F1 integration changes only GHC host arithmetic (addition-only) and
public INLINE pragmas. P1/P2 manifests retain the prior host pins and record the
explicit re-audit; schema, collections and all literal oracle bodies remain
unchanged. P2's `FrozenFingerprint` alone now compiles with
`-fno-enable-rewrite-rules -fomit-interface-pragmas` and Core lint; a retained rewrite dump must contain no
F1 rule. The normal candidate producer stays O2 with F1 enabled. This prevents
the same new fingerprint rule from silently optimizing both differential sides,
including later inlining of oracle unfoldings into the harness.
The independent [F1 controls](../fingerprint-fusion/README.md) separately compare
host arithmetic to an O0 Prelude-Integer oracle, including error/demand behavior.
