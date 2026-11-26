# Map policy controls

This suite compiles the current Map implementation beside independent reference
algorithms and checks contents, key representatives, balance, counts, exception
order and value demand. Both `-O0` and `-O2` lanes are retained, with fresh Haskell
and C objects, bounded execution and owned-process-tree cleanup.

```sh
python3 -B tools/testing/run.py python-map-policy-prepare-map-policy
python3 -B tools/testing/run.py map-policy -- \
  --source "$PWD" --producer .mlf-build/shared-ghc \
  --output .mlf-build/map-policy-controls
```

The producer must be a complete current `-O0` or `-O2` GHC producer. Its receipt still
checks the current build inputs and toolchain. Preparation follows local Haskell
imports and quoted project C includes, copies that closure and the controls, and
records their actual digests. It checks these same inputs and outputs again after
execution. An edit before preparation creates a new run identity; an edit during
the run or a stale snapshot fails. There is no source-revision allowlist.

## Reference fixtures

`fixtures/HistoricalMap.hs` preserves the Map implementation from
`fc300bc9fdc389b585cbef0630fc8915d53e89c5`, with its module header renamed for direct
compilation. `FrozenMap.hs` and `BaselineMap.hs` preserve the independent balance
and baseline implementations used by the previous Map controls. The two balance
control modules preserve their previously prepared Int64 source bodies, including
all 24,649 raw-shape pairs, 400 mutation steps and 30 explicit demand/order cases.
They are ordinary Haskell source files; the runner performs no source rewriting,
inverse transformation, old-commit lookup or history certification.

The current policy checks retain the separate association-list model, the full
step-21 shape witness, the 400-step current/reference/model trace, and 25 demand
observations. Shape equality with the older algorithm is already false at step
21; both trees must still have the expected contents and satisfy the invariants.
The literal old/current shapes are a specific regression witness, separate from
the association-list contents and invariant checks.

Before this retirement, the reference/control material was in
`tools/performance/map-policy/fixtures/fc300-Map.hs`,
`tools/performance/map-balance/{BalanceControls,BaselineMap}.hs`, and
`tools/performance/a1-private-index/controls/FrozenMap.hs`. Commit
`496dcae024cae1a93096d9bdb9d6b93e57359dc0` retains the old preparation procedure for
historical reproduction. Current runs need only the checked-in fixtures and can
prepare from a source copy without `.git`.
