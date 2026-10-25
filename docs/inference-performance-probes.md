# Fast, fully checked inference probes

This opt-in diagnostic is separate from required CI and release-producer
qualification. It supports rapid local iterations without running LLVM,
bootstrap, or the full compiler test suites.

## Run

Use an already verified GHC 9.14.1 O2 producer receipt and the Git revision
whose source bytes it records. From the repository root:

    python tools/shared/perf_inference.py \
      --producer /absolute/path/to/producer/receipt.json \
      --baseline-ref BASELINE_COMMIT \
      --override Bootstrap.ClassDemand \
      --cycles 3 --controls

The default override is Bootstrap.ClassDemand. Supply repeated --override
arguments to substitute other explicitly selected candidate modules.
The command refuses unlisted implementation-source changes, authenticates
baseline source bytes against Git and toolchain hashes against the receipt,
then builds separate baseline/candidate source and object trees using GHC
--make. GHC compiles each complete dependency closure; no producer Haskell
objects or interfaces are linked. The host transports are rebuilt from their
authenticated C/header closure. It never modifies the producer, publishes
changes, or changes CI timeouts. Each run gets a
new directory under .mlf-build, with commands, source identities, outputs,
separate build/link timings, sample timings, and a machine-readable receipt.

Cold compilation is separate from sample timing. Two clean diagnostic closures
on the development host took approximately 36--40 seconds each, plus about one
second to link each probe. A no-change dependency-aware scratch recheck took
0.32 seconds. These are local observations, not runtime promises or CI budgets.
The driver always uses a new output tree. For warm iterations add:

    --reuse /absolute/path/to/previous-complete-run/receipt.json

The previous complete isolated build's source snapshots, object/interface files,
toolchain and flags are authenticated before copying. The baseline revision and
override inventory must match. Only recorded cache artifacts are copied, and
the previous run is never modified. Changed implementation, Main, control
entrypoint or focused-test source bytes invalidate that module's copied .o/.hi
regardless of mtime; GHC --make owns all downstream dependency decisions.
Mutable live worktree source paths from the old run need not remain unchanged.
The driver and local helper/probe source bytes are preserved within each new
run for later audit. Increase --cycles to 20 for order-balanced
comparisons; the smaller default is iteration feedback, not an established
speedup.

Both diagnostic arms retain the producer's optimization, demand and closed
package policy. The driver additionally suppresses three existing compile-only
warning categories (star-is-type, overlapping-patterns and deprecations), while
enabling incomplete-pattern errors. This is recorded in the receipt, not
described as the producer's exact warning policy. Probe/control execution still
requires exit zero and empty stderr.

The final one-cycle smoke included 40 observations and both focused-control
runs. Cold execution took 86.93 seconds; unchanged warm reuse took 17.73 seconds;
a semantics-neutral ClassDemand source-comment edit took 17.54 seconds.
The changed warm run discarded only the copied ClassDemand .o/.hi, then GHC
recompiled ClassDemand in 0.71 seconds; the baseline check took 0.30 seconds.
These smoke samples validate the harness, not compiler speed claims.

Build commands are capped at 180 seconds, links at 60 seconds, tiny probes at
30 seconds, and focused controls at 180 seconds. The shared command runner
performs bounded process-group timeout cleanup. Only cheap fake/pure harness
controls are registered in tools/release/check.sh; benchmarks are opt-in.

## What is timed

Ten closed no-Prelude fixtures cover:

- a class-free compilation control;
- empty, ordinary, and recursive lexical class demand;
- known-polymorphic and unknown/monomorphic parameter-field use;
- raw and canonical datatype fields;
- raw and canonical class methods.

Every observation is a new process reading the same fixture bytes. The timer
covers complete compilation, expected inferred-type equality, the current and
independent target checkers, target pretty/parse roundtrip checks, erasure
equality, an exact runtime result, and a strict checksum of the source-type
display. The mandatory compiler checks remain in place. This is a **total
checked bundle**, not exclusive compiler-phase timing. It cannot benefit from
reusing a previously evaluated compilation thunk.

Observations use baseline/candidate/candidate/baseline order. Build and link
costs are recorded separately. --controls additionally runs targeted planner,
recursive class, provenance, parameter capture/skolem, and raw-declaration
validation checks; it is not the full authorized verification suite.

## Interpretation and limits

- A microbenchmark improvement does not establish a whole-compiler improvement.
  The empty-demand fast path reduced the fully serialized 20,000-node synthetic
  planner bundle by 36.65% in one 40-sample-per-variant comparison, while the ten
  whole-compiler fixtures moved in both directions within about 2%.
- A separate four-run full-facade Applicative comparison observed a 1.74% lower
  candidate mean, but two observations per variant and the small affected work
  fraction do not establish that as a real end-to-end improvement.
- The original ClassDemand-only scratch comparison used held consumer objects.
  Its old/new solve interfaces had no unfolding and Classes.o retained external
  solve references. This narrow audit does not justify generic object overlays:
  a later instrumented Constraint overlay crashed a control, whereas clean
  closures passed. The durable driver therefore uses isolated dependency-aware
  source builds. The precise overlay crash cause was not established.
- A diagnostic closure is still not a qualified release producer. A promising
  compiler change needs the owner's full authorized checks before publication.
- Do not remove source validation, final target checking, erasure or result
  oracles to make a benchmark faster. Do not sum inherited parent and child
  profiler percentages. Profiling builds locate work; ordinary uninstrumented
  O2 comparisons establish performance claims.

The PlannerProbe.hs file beside the Main.hs probe is an optional synthetic
diagnostic entrypoint. It serializes every Plan field and forces every character
with a strict checksum. Its timed bundle includes lazy input construction,
solving, and serialization. It is not part of the default end-to-end comparison.

## PR25 investigation boundaries

Late-instrumented profiling of the full-facade Applicative fixture identified
solver work rather than source canonicalization or class-demand planning as the
dominant route. Final-stream bare parameter instantiations accounted for 563
calls and 10.4% inherited diagnostic profile time. Earlier recursive flushes
were unclassified, not counted as zero. Parent/child inherited percentages were
not added together.

A separate scratch-only duplicate-bottom solver experiment preserved ground
graft/ground instance priority, exact graph aliases and the fresh counter.
Prepared valid controls require graph/index equality and successful validation;
deliberately malformed Solver controls require exact fallback/error parity and
are not presented as accepted graphs. In particular, a Green target beneath a
type binder is not sufficient: the original expansion rejects one such graph
while unrestricted direct unification accepts it. The narrowed experiment
requires an exact Flexible Star bottom directly bound to a Gen.

The first clean same-instrumented four-run comparison observed a 3.05% lower
candidate mean with substantial spread. That was a diagnostic hypothesis test,
not an uninstrumented production speedup or approval to adopt the solver change.

The follow-up **uninstrumented** source comparison used clean baseline and
scratch Solver closures, two ABBA cycles, and all unchanged end-to-end oracles.
Four samples per arm averaged 18.502326 seconds baseline and 18.499521 seconds
candidate, a 0.015% difference with about 0.51--0.57 seconds standard deviation.
It did not establish an improvement. The solver shortcut was rejected for
adoption and remains scratch-only; only the narrow empty-demand planner
candidate and its exact controls are proposed as compiler changes.

That historical source experiment verified all input hashes when it completed.
Its Python orchestration helper was subsequently rewritten for the durable
driver, and that exact intermediate helper was not frozen. Its recorded digest
is retained, but its historical source cannot presently be independently
rehashed. Timed Haskell snapshots, binaries and command captures remain
preserved. Later durable runs preserve helper copies to avoid this limitation.
