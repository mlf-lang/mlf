# Per-call bound-kind memo investigation

**Experimental restart checkpoint, not a merge-ready optimization.** Candidate
based on `f9bdb40a659bfdff4cbb782d438afbb0417dd2e1`. No actual compiler hotspot
or compiler speedup has been established. Full endpoint qualification and CI
for this candidate have not run.

`Bootstrap.X.Type.kindOf` currently re-traverses a type-variable bound every
time it is reached through another dependency path. A bounds DAG can therefore
require exponentially many recursive visits. The candidate stores successful
kinds in one map owned by one `kindOf` call. It retains sorted free-variable
traversal, active-path cycle rejection and the original `kindIn` checks. No
memo crosses a call or changes a bounds environment. Errors are not cached.

The existing public `kindBinding` and `visitKind` retain their historical
algorithm. The diagnostic's explicit old entry calls those helpers and is
compared with the candidate. The generated finite cases cover shared bounds,
cycles, unbound references and higher kinds. Authored cases also cover shadowing,
closed types, unused bottom bindings and first-error order. These finite controls
are not a universal partial-value equivalence proof.

Run the small isolated GHC dependency closure with the standard demand flags,
without constructing a new full producer or invoking a native fixed point:

    python3 -B tools/performance/type-kind-memo/run.py --ghc /path/to/ghc \
      --optimization 2 --controls-only --output /fresh/output

Repeat with optimization 0 in a separate directory for demand controls. The
four old/memo/memo/old observations measure only the synthetic depth-20 bounds
DAG. They are mechanism diagnostics, not ordinary compiler timings. The runner
preserves commands, source hashes and existing resource-watchdog receipts.
Current-corpus profiling and ordinary compilation comparison remain required
before deciding whether to retain this production candidate.

## Initial semantic screen

The isolated GHC 9.14.1 O0 and O2 closures both passed 5,184 generated
environment comparisons, 17 diamond graphs and nine authored kind/demand
controls on Linux. Microtimings were disabled while the shared baseline
producer was being built. This does not yet qualify current-corpus performance
or the complete compiler regression suite.

## Restore and continue F1

The checkpoint is on branch `perf/frontend-20261110`. There are deliberately
two separate paths:

1. The production file `libraries/mlf-xmlf/Bootstrap/X/Type.hs` contains the
   unaccepted memo candidate. `Main.hs` and `run.py --controls-only` exercise
   that candidate. The complete compiler's ordinary regression and performance
   qualification remain pending. Do not merge this file merely because the
   finite controls passed.
2. `instrument.py` reads the frozen baseline owner from Git and emits a private
   diagnostic copy. `diagnose.py` instead receives the authenticated baseline
   producer and its unchanged source checkout explicitly. It instruments the
   original algorithm, never the memo candidate. The original owner hash must
   be `5ae7191adc5df556b83901682ee17e3de889a99e9fe35e97d7370ec2443d0d3d`.

Resume only after the team coordinator grants the CPU window, following its
persisted plan. Recreate or authenticate the ordinary baseline producer,
90-module frozen workload, fixed dependencies and independent checked
reference through that plan. Local build outputs are conveniences, not durable
inputs or proof. Then run exactly one fresh diagnostic:

    python3 -B tools/performance/type-kind-memo/diagnose.py \
      --producer /baseline/producer --producer-source /baseline/source \
      --workload /baseline/workload.json --setup /baseline/setup.json \
      --reference-prefix /baseline/accepted/unit --output /fresh/F1-diagnostic

The driver uses the existing resource guard, copied authenticated ordinary
objects and GHC's downstream invalidation. It records all private source edits
and compares complete checked raw bytes and ordered group identities with the
independent reference. Its elapsed times are diagnostic only. At this checkpoint
the full driver is **prepared but unexecuted**; preserve and diagnose any failure
rather than replacing it with a successful sample or raising resource limits.

The next decision is based on actual `kindOf` roots, recursive visits and
per-root unique variables, not the synthetic diamond timing. If repetition
cannot materially affect the complete path, retain the diagnosis and stop the
memo candidate. Do not add more microbenchmarks to manufacture a positive result.
Any later ordinary performance comparison is scheduled by the baseline owner.
