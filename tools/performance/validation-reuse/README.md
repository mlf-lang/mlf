# Generated graph validation boundary

`CrateSession.finishCompilation` receives `Constraints` only after
`Constraint.generateProgram` has successfully validated its `initialGraph`.
The graph is immutable and unchanged between that success and `solveGenerated`.
Repeating the same pure validation cannot add a new demand or first error after
the first validation has returned success. The new private entry therefore
starts with the remaining admission checks and shares the existing solve body.

The arbitrary-constraint `solvePrepared` entry retains `prepareGraph` and its
initial validation. Alias/live-identity exclusion, fresh-counter bounds,
canonicalization, index admission, solving, final validation, checked terms,
type equality and source erasure checks are retained. No public export or state
representation changes. `prepareValidatedGraph` is reached either after
`prepareGraph` validates or from the successful generation boundary.

The complete previous private owner is reconstructed with three exact inverse
source edits in `source-contract.json`. Its SHA-256 must equal the previously
pinned A1 owner. The reconstruction changes no historical oracle or expected
output. A1 extends its source inventory by this one owner; C4 extends only its
candidate dependency. The complete earlier C4 manifest, before-source inventory
and algorithm hashes remain unchanged.

`BoundaryControls.hs` keeps 20 authored programs with explicit acceptance or
rejection expectations, exact checked term/type/error comparisons and physical
presolution comparisons. Successful generation also compares both solve entries
against the complete previous owner, including unused-skeleton demand. Three
malformed raw graphs and four partial-value/exception-order cases supplement
the full retained A1/C4 suites. These finite checks are not a proof for every
partial value. Three negative GHC imports must fail because the new helpers are
not exported; missing-module errors do not qualify.

Run against a completed ordinary O2 producer:

```sh
python3 -B -m unittest discover -s tools/performance/validation-reuse -p 'test_*.py'
python3 -B -O -m unittest discover -s tools/performance/validation-reuse -p 'test_*.py'
python3 -B tools/performance/validation-reuse/run_controls.py \
  --producer .mlf-build/shared-ghc --output .mlf-build/validation-reuse-controls
```

The compiled runner authenticates the producer, compiles controls against copied
ordinary interfaces, checks the frozen source inverse and preserves failure
receipts. It retains the existing memory/disk/process limits and serial lock.
The O2 CI gate runs these controls in addition to the existing suites.

The preceding eight-run discovery window did not meet its performance rule.
This change removes redundant work without claiming a measured speedup or
statistical noninferiority. See the integration report for the recorded scope.
