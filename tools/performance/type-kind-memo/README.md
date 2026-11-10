# Bound-kind investigation: negative result and restart checkpoint

**The memo candidate is stopped. No compiler speedup was established.** This
branch retains a reproducible, private diagnostic and its bounded observations,
not a merge-ready optimization. The production `Bootstrap.X.Type` owner is
restored byte-for-byte to baseline `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`.
The rejected candidate remains in `archive/memo-candidate.patch` and in the
[original experimental checkpoint](https://github.com/mlf-lang/mlf/commit/64ee679848211034a3cb1e2c1b44f8f600861ab0).

## Decision and observation limits

One combined F1/R2 diagnostic ran against the frozen 90-module, 5,233,364-byte
compiler source closure. At its last live snapshot, 119.098 diagnostic seconds:

- `kindOf` had completed 1,590,641 roots, with no active root in that snapshot.
- 620,367 recursive variable visits equalled 620,367 per-root unique variables.
- No observed root repeated a variable; the maximum was 15 visits in one root.
- 957 SCCs had started and 956 fresh SCCs had finished. The last fixed label was
  `scc.raw-infer.await-whnf`.
- The final eight snapshots advanced from 893 to 957 started SCCs and from
  1,354,455 to 1,590,641 roots. The observed tail did not remain in one SCC.

Per-call memoization therefore had no repeated bound traversal to eliminate in
the observed prefix. This is sufficient to stop this candidate in this sprint.
It is not a claim that every unseen suffix or other program has no repetition.
Do not add synthetic microbenchmarks to turn this negative result into a win.

The existing guard stopped the compiler at 120.126 wall seconds with exit -9
and reason `wall limit`. `harness_complete` is true because evidence collection,
input reauthentication and child cleanup succeeded; `compiler_complete` and
`complete` remain false. There were 80 readable snapshots and no final `.mlfci`,
`.mlfco` or `.queries` output. The separate ordinary baseline had already timed
out at 600 seconds, so no independent complete checked reference existed.
No checked-byte/group-identity comparison, complete semantic qualification,
ordinary performance comparison or CI qualification is claimed here.

Instrumentation changes demand and allocation behavior. Its wall time is not
an ordinary compiler sample, and the labels do not establish exclusive phase
costs. In particular, an IO return or `Either` WHNF does not force all lazy
parsing, resolution, lowering or inference. `scc.raw-infer.await-whnf` identifies
a demand window, not a completed inference pass. All reported counters are
monotone observations of the executed prefix.

## What is preserved

- `instrument.py` transforms only the frozen baseline Type owner. It wraps the
  original algorithm, never the rejected memo implementation. Exact inverse
  reconstruction is checked before building.
- `progress.py` is the separately owned reversible Session/CrateGraph transform.
  It adds sparse IO boundary labels and fixed per-SCC events. It contains no
  legacy query-writer optimization and no `Crate.hs` pure-stage probes.
- `Counters.hs` stores only numbers, variable-ID sets and fixed labels in one
  atomic state. The reporting thread reads that state every two seconds and
  does not retain or force compiler syntax. Event updates also update the last
  label; sparse boundaries flush immediately.
- `locate.py` assembles and builds one private diagnostic, authenticates the
  unchanged ordinary producer, checks the exact input closure and fixed
  dependencies, runs controls and entry preflight, then runs one guarded
  120-second source-to-checked attempt. It records all transforms and hashes.
- `evidence/combined-localization/` retains every snapshot, both attempt
  receipts, commands, stdout/stderr, workload/setup manifests, generated entry
  wrappers and owner patches. `manifest.json` hashes the preserved files and
  diagnostic sources. Executables and object files are intentionally excluded.

The query directory inventory contains `.lock` and
`query-graph-v2/{generations,results,staging}`. Lack of published payload files
cannot locate execution before graph initialization: publication follows all
SCCs, while the observed events prove inference was already underway.

## Executed attempts and controls

Attempt 01 built the counter-control executable, then failed before executing
controls because its filename collided with the guard output directory. It did
not build the complete diagnostic compiler or run the complete workload. Its
receipt and reconstructed, hash-verified original `locate.py` are retained.
The only change for attempt 02 was naming the executable `controls-probe`.

Attempt 02 passed all of the following before the one bounded complete-workload
invocation:

- Exact reversible transforms of the three private owners.
- Four original-algorithm value/demand controls, with the exact expected counts:
  4 roots, 12 visits, 7 per-root unique variables, maximum 9, 2 repeated roots.
- An immediate zero-count snapshot, a live periodic snapshot after controls,
  and a final reporter-stop snapshot with the same expected counts.
- Complete diagnostic build and an `emlf 0.3.0` entry preflight with immediate
  zero-count output.

The final guard recorded no live descendants. Both the coordinator resource
lock and the baseline reproduction lock were independently acquired after the
run to verify release. Ordinary producer/source/input hashes were rechecked.
No further CPU experiments were run for this candidate.

Earlier candidate O0 and O2 finite screens each passed 5,184 generated
environments, 17 diamond DAGs and 9 authored kind/demand controls. Those controls
remain historical evidence, not a universal partial-value proof or full compiler
qualification. `run.py` now rejects a non-candidate Type owner so it cannot
silently compare the restored baseline with itself. No synthetic timing was
run. `diagnose.py` is the superseded, unexecuted full-reference proposal; it is
not the harness that produced the result above.

## Restart safely

Read `checkpoint.json` and the evidence before scheduling more work. The memo
candidate is not active and does not need another producer or benchmark run.
Use the team coordinator's persisted plan for the next optimization decision.
This branch and the exact baseline commit are sufficient to recover the code;
old absolute build paths in historical receipts are evidence, not reusable
inputs on another machine.

If the coordinator specifically requests reproducing this localization:

1. Restore a separate checkout at baseline
   `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. Rebuild and authenticate its ordinary
   producer, 90-module workload and fixed builtin through the baseline team's
   plan. Keep this diagnostic branch separate. Do not substitute newer main or
   relabel old receipts.
2. Verify the frozen Type, CrateSession and CrateGraph hashes against
   `evidence/combined-localization/manifest.json`. The diagnostic must still
   transform the original algorithms exactly and reversibly.
3. Acquire the single coordinator CPU window and a fresh output directory. Run
   the following with local paths supplied by the recovered baseline setup:

       flock -n /shared/sprint/resource.lock \
         python3 -B tools/performance/type-kind-memo/locate.py \
           --producer /baseline/producer --producer-source /baseline/source \
           --workload /baseline/workload.json --setup /baseline/setup.json \
           --output /fresh/F1-R2-localization

The driver also holds the baseline `.mlf-build/.reproduction.lock` and uses the
existing process guard and scope supervisor. Do not run concurrent heavy work,
raise limits to hide failure, or repeat a timeout without a changed diagnostic
question. Preserve failure/timeout receipts. Inspect the separate compiler and
harness completion flags, verify child cleanup and both locks, then return the
resource window. The current checkpoint is diagnosis only and is not ready to
merge as a compiler optimization.
