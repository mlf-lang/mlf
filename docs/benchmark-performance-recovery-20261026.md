# Benchmark performance recovery, 2026-10-26

This investigation starts at `2957dd08321c38dbf94a75cb275a5f48e897f58e`.
The requested gate is **compilation <= 3x C and runtime <= 2x C**, using the
unchanged ten-workload manifest, correctness inputs, fixtures, default inputs,
C programs, and C flags. Recovery is still in progress; the measurements below
are not a claim that the final ten-workload gate passes.

The user requested a pause after this round's testing and PR #25 push. See the
[handoff](benchmark-performance-handoff-20261027.md) and
[compact closeout evidence](benchmark-performance-recovery-evidence-20261027.json).
The full performance goal remains incomplete.

## 2026-10-27 checkpoint

The normal compiler entry now selects the prepared builtin route for eligible
standalone roots and retains the ordinary fallback. Canonical generated data
uses builtin identity v9, exact source witnesses and independent startup/final
checking. The frozen production candidate passed fresh regeneration, 33 semantic
comparisons, 36 native O0/O2 executions, 46 direct-import controls, 39 context
mutation controls and 15 builtin artifact checks. All 231 qualification input
pins remained unchanged. Evidence is `production-controls-1/receipt.json` under
`.mlf-build/performance-recovery/`. This is finite macOS correctness evidence;
native-host qualification and the complete performance gate remain pending.

The subsequent uncontended production CLI cohort compares three fresh-process
samples per root with the same-v9 ordinary path: binary-trees **7.36478 to
0.290610 s**, n-body **7.80210 to 0.725261 s**, and pidigits **7.19062 to
0.237781 s**. Full startup context checking is **0.076243 s**, down from the
prototype's 0.2028 s restoration. All 21 commands pass, LLVM is byte-identical
between routes, and pinned inputs remain unchanged. These are frontend-through-
LLVM-output measurements, not full native compilation. The receipt is
`production-builtin-timing-1/receipt.json`; n-body remains dominated by solving.

The maintained build now verifies the builtin source identity and compares the
canonical literal with fresh ordinary-generator stdout before publishing a
completed build receipt. The direct-test authenticator requires this matching
evidence. Focused verifier/provenance controls pass **82 executed tests**, with
four existing Linux `/proc` controls skipped on macOS; immutable inputs remain
unchanged. The initial fixture-only failed run is retained, followed by the
successful `builtin-verifier-controls-2/receipt.json`. This validates the
verification machinery, not a new compiler build or native qualification.

The generic imported-library adapter and its tooling are included as unfinished
drafts. The checkpoint committed at `24a777e` left them unregistered and unwired;
subsequent source registration uses an empty fixed registry, which retains the
ordinary fallback. No populated production library registry has been generated.
A separately generated fixture registry has now passed all 33 finite cases,
including 50 interpreter and 100 LLVM O0/O2 executions in 366 commands, with
unchanged input postchecks. Loader order, cycles, diamonds, exact diagnostics,
ambiguity, provenance, independent ordered layouts, private class scope,
managed callstack locations and an actual same-schema builtin-body mutation are
covered. The retained earlier failures were fixture-oracle errors; their
receipts are not relabeled as passes. Evidence is
`.mlf-build/prepared-library-fixture-results-3/receipt.json`. Fresh same-path
regeneration, actual foundation-library admission, native-host qualification
and complete performance qualification remain pending. Imported production
roots still use the ordinary compiler. The accepted Regex source now adds the
measured weighted-credit and ASCII suffix-membership changes to inline41, as
recorded below. Fused replacement, streaming-join and additional solver
experiments have not been promoted.

## Reproduced starting point

The retained complete three-sample run at
`/Users/ares/.codex/worktrees/f4e3/mlf/.mlf-build/benchmark-game-ghc/results/results.json`
uses the starting source revision and GHC-hosted compiler. Candidate and baseline
compiler hashes are identical, so it establishes the C comparison, not an A/B
compiler improvement. All correctness checks pass; compilation passes 0/10 and
runtime passes 8/10.

| Workload | MLF compile, s | Compile / C | MLF runtime, s | Runtime / C |
| --- | ---: | ---: | ---: | ---: |
| binary-trees | 14.885233 | 110.411 | 0.223306 | 0.648 |
| pidigits | 14.755915 | 106.331 | 0.604200 | 1.644 |
| n-body | 16.435901 | 104.507 | 0.123325 | 1.137 |
| fannkuch-redux | 15.871114 | 105.280 | 0.236181 | 1.097 |
| spectral-norm | 15.139687 | 105.047 | 0.165459 | 0.801 |
| fasta | 15.708057 | 103.695 | 0.368200 | 1.499 |
| mandelbrot | 15.080532 | 112.464 | 0.640028 | 0.676 |
| reverse-complement | 15.213884 | 108.710 | 0.308346 | 2.152 |
| k-nucleotide | 15.396884 | 96.787 | 0.285558 | 1.676 |
| regex-redux | 27.928690 | 186.818 | 56.657393 | 100.537 |

The historical 2026-10-18 3x/2x pass located during this audit covered nine
workloads, with a native PGO compiler and explicitly configured low-latency LLVM
and linker helpers. It did not establish a ten-workload regex-redux pass. This
distinction does not explain the present frontend regression.

## Compilation diagnosis

There is a concrete source-path change from local `main` (`fde9e41`): its
`bootstrap/Bootstrap/Prelude.emlf` conditionally adds only the `Monad` class and
the IO/ST instances when needed. Commit `83e5c31` introduced the canonical
standalone facade and changed `compileProgramWithPrelude` to call
`Standalone.normalize`, whose ordinary mode selects the complete builtin
Prelude. Once a genuine facade reference is used, all its values, classes and
instances enter lowering and inference. The later benchmark syntax migration
`b985cc6` preserved the workloads while updating canonical unit/collection
syntax. The full canonical semantics must be retained; switching to the
experimental demanded-scope mode would not establish an equivalent repair.

The ordinary standalone path expands the complete canonical Prelude. The
starting binary-trees profile reaches 6,429 general expansion/unification calls;
repeated component projection, binding reconstruction, permission checking and
index restoration dominate. Almost 98% of projected component volume comes from
expansions with external type references. A separate suspected unsigned-SCC
flush path had zero calls in this profile and is not a measured cause.

The profiling build allocates about 129 GB in total over its execution. Its
instrumented times are not used as normal compiler performance measurements.
The profile and source/tool records are under
`.mlf-build/performance-recovery/{profile,baseline-source-record.json}`.

Host selection was isolated by building the original revision into a native
compiler through the ordinary package manager in an immutable source snapshot.
One warmup and three rotating binary-trees frontend samples give:

| Same original source | Median LLVM emission, s |
| --- | ---: |
| GHC-hosted compiler | 15.340652 |
| Native-hosted compiler | 15.047342 |

All eight emitted LLVM files are byte-identical. The 1.9% difference rules out
GHC versus native hosting as the explanation for the large regression. This
is a stage-A functionality and performance comparison, not native A/B fixed-point
release qualification. The complete receipt is
`.mlf-build/performance-recovery/native-baseline/host-comparison/receipt.json`.

The retained exact graph shortcuts admit only cases where the ordinary
unifier's final structure, identities, binders, flags and allocation counter can
be reproduced. They preserve the general unifier as fallback and the final
whole-graph validation. The initial controls include 79 boundary cases and 2,291
real binary-trees instantiations compared against the unchanged unifier and both
complete `finish` validations. These cases eliminate 58.8% of the previous
projected-node volume. Cross-scope raising remains on the general path.

The frontier-only intermediate implementation emitted binary-trees in 10.2869 s
versus 15.4788 s for the earlier closed-only candidate, with identical LLVM.
These are single diagnostic samples, not a complete performance gate. A later
uncontended comparison, with one warmup and three alternating samples for each
compiler, measured the current congruence/host-array/checker candidate at
**7.360190 s versus 14.847906 s** for the starting compiler (49.57% of the old
time). Every candidate LLVM output matches the independently validated
frontier implementation. This includes several changes together and is not an
isolated attribution to the congruence shortcut. See
`.mlf-build/performance-recovery/candidate-congruence/comparison/receipt.json`.

Broader current-source GHC O2 validation also passed all three maintained
shared-frontend modes and the Figure12 campaign (41 distinct expressions, 29
assumptions, four principal types, three annotation repairs, and 13 decoder
controls). All 86 commands succeeded, and the immutable source snapshot still
matches its original inputs. This is a macOS diagnostic using the maintained
test bodies, not a Linux builder receipt or a native Core-suite qualification:
`.mlf-build/performance-recovery/maintained-qualification-1/receipt.json`.

The congruence shortcut itself initially repeated `kindAt` with a fresh cache
for each node in a type spine. Batching these queries retains every admission
condition and fallback while sharing only equivalent kind results. All 84 graph
controls pass. Instrumented cache misses for 64/128/256-arrow spines fall from
4,290/16,770/66,306 to 130/258/514. The isolated compiler changes only Solver
relative to the congruence snapshot and emits identical binary-trees LLVM.
These counts establish the quadratic traversal. A controlled developer-tools
package build then measured 144.623634 CPU seconds with the starting GHC
compiler versus 491.633993 CPU seconds with the batching candidate. The exact
same frozen source/dependency inputs produce byte-identical interface and
object files. Batching therefore does not remove this separate 3.40x package
regression introduced by the candidate changes. Restoring only the original
Solver in that exact candidate reduces the same build to **140.093 CPU seconds**
and **142.693 wall seconds**, again with byte-identical interface and object
files. This isolates the regression to the graft optimization rather than the
host arrays or checked-binding inventory. Profiling identified repeated sparse
validation of small temporary graphs whose identities span a much larger range.
The repair rejects incompatible congruence shapes before validation and densely
relabels only the temporary validation graph, preserving every identity in the
actual result. All 146 graph controls pass, including 62 independent sparse/dense
validity comparisons with malformed graphs and extreme identities. The exact
same package build now takes **135.347 CPU seconds / 138.170 wall seconds**,
again producing byte-identical interface and object files. These single samples
establish removal of the large regression; they do not establish a meaningful
speedup over the 140.093-second Solver ablation. The corrected implementation
has now completed the entire 6,429-instantiation comparison: all 2,291 accepted
grafts match the unchanged simultaneous unifier's complete graph, links,
allocation counter and both full finish results; 4,138 cases take the original
fallback. LLVM is byte-identical and frozen inputs are unchanged. See
`dense-fragment-comparison/comparison.json` under the same evidence directory.
Evidence: `.mlf-build/performance-recovery/developer-2x2/`.

An isolated prepared-Prelude prototype retains runtime artifact validation,
independent fragment checks, whole-user-root inference and the final complete
linked-term checker. Its 29 source controls and 36 native O0/O2 fixture runs
pass. Three rotating pairs measure binary-trees emission at 0.672641 s versus
7.752934 s ordinary, n-body at 1.150459 s versus 8.326108 s, and pidigits at
0.618849 s versus 7.710367 s. Context restoration alone costs 0.236148 s. This
is neither a production integration nor the complete compilation gate; imported
module roots and native compiler packaging remain outside the prototype.
Evidence: `.mlf-build/performance-recovery/prepared-{controls-6,native-1,timing-1}/`.

A later prototype removes unused synthetic import bindings only after complete
class/instance lowering and translation of every import signature. Its dependency
scan retains evidence candidates and references in unused local RHSs. All 33
ordinary-versus-prepared source controls pass. In the same binary, three paired
full-prefix versus selected-prefix samples measure 0.61950 to 0.56066 s for
binary-trees, 1.10104 to 1.05924 s for n-body, and 0.62055 to 0.56615 s for
pidigits; all emitted LLVM files are identical. The full prefix has 76 bindings,
of which 47–48 remain for these roots. This is a modest improvement, not the
requested full compile-time recovery. See `prepared-controls-7/` and
`prepared-parameter-timing-1/` under the same evidence directory.

The next experiment declares the authenticated import signatures directly and
omits only their synthetic panic RHS/proof graphs. It still infers the complete
user continuation, independently checks a closed typed import wrapper, verifies
its exact user result scheme and erasure, and checks the final linked term.
All 33 source controls, 46 direct-boundary controls and 36 native O0/O2 fixture
executions pass. Three fresh-process samples per route in the same binary give:

| Root | Full synthetic prefix, s | Selected prefix, s | Direct imports, s |
| --- | ---: | ---: | ---: |
| binary-trees | 0.616467 | 0.563499 | 0.438754 |
| n-body | 1.025720 | 0.982635 | 0.851472 |
| pidigits | 0.560747 | 0.509084 | 0.389557 |

All emitted LLVM outputs are identical. Context restoration alone is 0.202759 s.
These are frontend measurements, not full native compilation times; in
particular n-body still needs a substantial additional reduction. The receipt
is `prepared-direct-timing-1/receipt.json`. Direct generation preserves the exact
signature allocation while reducing binary-trees graph nodes from 6,804 to
2,864, n-body from 11,676 to 7,785, and pidigits from 6,462 to 2,522. Production
integration and imported-library roots remain under development.

## Runtime and build-pipeline changes under validation

The generic regex library now compiles admitted regular-expression structures
into bounded search plans, retaining the original ordered Thompson matcher for
other expressions. Differential controls use a frozen original implementation,
Unicode and ordering cases, explicit accelerator admission checks, and the
unchanged benchmark's independent oracle. Intermediate complete regex runs fell
from 56.657 s to 6.138 s, then 3.917 s and 2.884 s as character lookup and delimiter
scanning improved. A subsequent uncontended three-pair run of the bounded skip
search measured 2.599569 s versus C's 0.562116 s. Subsequent guarded loop
optimizations measure **1.798913 s versus C's 0.565295 s**, a ratio of
**3.182255**, in another uncontended three-pair cohort. All outputs and
input/binary hashes passed verification. This remains above 2x C; see
`.mlf-build/regex-runtime-pairs-17/receipt.json`.

An allocation-only diagnostic of that exact frozen program attributes
3,360,887 concatenations and 707,071,543 copied bytes to the replacement
phase. A general String-list joining primitive now replaces the balanced
repeated-copy join, with explicit source-order demand, Unicode, overflow and
GC-root controls. Its two-pass implementation retains the list through the
copy pass. A separate single-pass growing-buffer experiment has passed semantic
controls but has not yet been measured or promoted into the runtime.

Demand-order controls exposed an existing native worker bug in both the old
balanced join and the new primitive: unordered eventual-demand sets could force
a later parameter before an earlier nested operation failed. Worker entry
analysis now admits only the next proven variable demand, preserving barriers
for partial operations, container traversal, conditionals, case and unknown
calls. All 58 interpreter and 116 native O0/O2 controls pass; 13 new non-seq
counterexamples were independently reproduced with the prior compiler. Existing
ready-total arithmetic/conditional allocation improvements remain, and both
tested accumulator allocation counts are unchanged. A subsequent three-pair
regex run nevertheless regressed to **3.033928 s versus C's 0.559870 s**
(**5.41899x**), despite passing all outputs and provenance checks. Both counting
and replacement slowed, so the conservative analysis requires a more precise
ordered argument-demand implementation before it is an acceptable performance
repair. This cohort is `.mlf-build/regex-runtime-pairs-26/receipt.json`; native
compiler execution still needs measurement. Correctness evidence is under
`.mlf-build/performance-recovery/first-demand-{controls-1,baseline-evidence-1}/`.

The replacement worker analysis carries an ordered demand prefix and stops at
any unproved partial/deep operation. Calls force that prefix in source order
before assembling the unchanged worker ABI. In total, 68 interpreter and 136
native O0/O2 controls pass. A same-compiler library change then makes the skip
scanner's existing cap/credit/shift/arithmetic demand order explicit, removing
immediately forced local thunks. Three uncontended pairs measure **2.942717 to
2.184546 seconds**, against **0.557479 seconds** for C (still **3.9186x**).
All unchanged benchmark outputs pass. A further explicit raw-arithmetic demand
removes the remaining mismatch-path thunk and passes the full differential and
native controls; it has not yet been timed. See
`.mlf-build/regex-ordered-pairs-34/receipt.json`, `regex-fast-audit-37/`, and
`native-regex-controls-38/`.

A further general let optimization advances past earlier demand-prefix names
only when their WHNF is already known on the current dominating path. Missing
bindings and semantic barriers still stop the prefix. All 76 interpreter and
152 native O0/O2 executions pass in one completed 305-command run. The two new
allocation controls remove one thunk each; excluded multiplication, ordinary
accumulator laziness and all prior error-order controls remain intact. Its
effect on the unchanged regex workload has not yet been measured:
`.mlf-build/performance-recovery/ready-let-controls-1/receipt.json`.

The explicit raw-arithmetic demand was then measured at **1.736942 seconds**
versus 2.131889 seconds for the preceding schedule, with C at 0.550008 seconds
(**3.158x**, still failing). The same-source ready-let compiler comparison
shows no demonstrated additional gain: 1.727428 versus 1.770040 seconds, with
overlapping sample ranges. Its correctness and targeted allocation controls
pass independently of that result. A same-object streaming join comparison
measures 1.719739 to 1.618448 seconds, but peak RSS stays approximately 583 to
581 MB and both variants collect five times. Streaming increases allocation
from 2.025 to 2.143 GB and recopies another 75.10 MB. This supports a modest
traversal benefit, not the proposed memory-reclamation explanation; production
promotion remains undecided. Counting and replacement each take about half the
remaining runtime. Evidence: `regex-raw-pairs-39/`, `regex-ready-let-pairs-43/`,
and `regex-concat-streaming-29/raw-cohort/` under `.mlf-build/`.

Forcing the replacement accumulator's list spines passed semantic controls but
slowed the measured cohort slightly (1.738569 to 1.764657 s), so that experiment
was not promoted. Inlining the small private first reverse-transition helper
instead removes a per-candidate offset thunk while retaining the same search
algorithm. This passed the differential corpus, 46 native O0/O2 cases and all
six unchanged benchmark checks, then improved 1.740177 to **1.655151 s** versus
C at 0.551548 s (**3.001x**, still failing). It is now the production Regex
source, pinned as `045de04069a158c5ff55d61e7d604a3f01aea7a034ac58c63dd8d80d67dcb8da`.
Counting falls from about 0.868 to 0.761 s; replacement remains about 0.855 s.
The cost-only diagnostic observes 9,593,822 progressed reverse entries that
previously used the extra helper thunk. Further generic replacement dispatch
and search-credit experiments are separate, unpromoted candidates.

The first plan-specific replacement experiment then passed correctness but
showed no reliable runtime gain (1.653621 to 1.672707 s with overlapping ranges),
so it remains unpromoted. A separate backend comparison holds accepted inline51
LLVM and runtime object fixed: ordinary Clang O2 runs in **1.637524 s**, while
the configured low-latency helper takes **2.166388 s**, 32.30% longer (C is
0.560278 s). Both counting and replacement slow down. The helper's generic pass
pipeline omits `always-inline` and retains local force/allocation helper calls
that Clang O2 inlines; an isolated pipeline experiment is pending. The prior
Clang-O2 runtime improvements therefore do not establish the configured backend's
runtime gate. Receipts: `.mlf-build/regex-plan-replacement-pairs-64/receipt.json`
and `.mlf-build/regex-backend-helper-pairs-65/receipt.json`.

Adding the generic `always-inline` pass recovers **16.09%** in the next quiet
same-LLVM cohort: 2.228857 to **1.870202 s**, while Clang O2 takes 1.690155 s
and C takes 0.562994 s. However, LLVM-to-object compilation rises from
**0.231080 to 0.551597 s** and the object grows from 207,352 to 356,544 bytes.
All six workload correctness checks and 152 native demand-order executions
pass. This establishes a real compile/runtime tradeoff, not a gate pass; the
full-inlining backend is not promoted. Receipts are
`regex-alwaysinline-backend-66/`, `regex-alwaysinline-pairs-67/` and
`regex-alwaysinline-compile-68/` under `.mlf-build/`.

Accounting for both reverse comparisons and the per-candidate shift lookup in
the bounded skip-search credit improves the separate Clang-O2 cohort from
**1.669404 to 1.488272 s** (10.85%). Counting falls from approximately 0.762 to
0.584 s. The unchanged outputs, independent differential corpus and native
demand controls pass. This change is promoted alone; the production Regex hash
is `5f32f5f2ef89b7238356227f7ba1fa1e3b184a6e2c3083eaaf1e7f0998419e31`.
The receipt is `regex-index-credit-pairs-70/receipt.json`. A separate fused
Span replacement candidate shows no meaningful gain, 1.716344 to 1.715179 s,
and is not promoted (`regex-span-replacement-pairs-75/receipt.json`). These
library timings use Clang O2 and do not qualify the selected low-latency backend.

The final library candidate adds the same bounded ASCII membership table to
Span suffixes while retaining `contains` for Unicode. A quiet combined cohort
measures credit54 versus this suffix76 candidate at **1.514192 to 1.398310 s**
with Clang O2 (7.65%), and **2.014418 to 1.928656 s** with the existing configured
helper (4.26%). C is **0.563403 s**, so the suffix candidate still takes
**2.482x C** with Clang and **3.423x C** with the configured helper. LLVM-to-object
compile medians rise by about 26 ms and 6 ms respectively. The measured runtime
sample ranges for these two comparisons do not overlap. This candidate is
promoted as `016cda4d5a9cd2ed0161976ab4150d74c1b2843cb6a5a046aef72eccc1945b0d`;
it contains the accepted credit change and excludes the rejected fused
replacement experiment. Evidence: `.mlf-build/regex-force-screen-{pairs-89,compile-90}/`.
Final production-source checks without a source override pass in
`regex-production-suffix-ghc-93/` (70 literal, 17 demand, 12 scheduler and
82,948 differential pairs) and `regex-production-suffix-native-94/` (56 native
O0/O2 executions). The test harness exposes private helpers only; these native
programs use the pinned ready-let compiler, not an exact-final native-bootstrap
qualification.

That same cohort retains the unpromoted backend tradeoffs. For suffix76,
allocator-inlinehint/full-force policy takes 1.640911 s runtime / 0.468786 s
object compilation; direct-WHNF force takes 1.718778 / 0.301663 s; one-hop peek
takes 1.639321 / 0.376328 s. The latter two are explicitly IR-only experiments,
with independent ABI/output controls, not source-compiler qualification. The
production backend and force code generation remain unchanged this round.

The string code generator uses a guarded ASCII byte lookup only after the
original operand evaluation. Unicode, uncached strings, large or invalid indexes
use checked runtime helpers. Sixty native O0/O2 controls cover value and error
behavior, including lazy unused expressions and evaluation order.

The byte-line runtime reuses only libc's scratch buffer; every returned ByteArray
still owns an independent copy. Large pointer-free buffers use atomic GC storage.
Reverse-complement diagnostics show improvement, but a fresh full gate is still
required. Runtime controls cover retained lines, binary data, growth, EOF,
collection, cleanup and reuse.

Keeping infrequent filesystem/process helpers out of line reduced runtime C
compilation about 7% in paired diagnostics. Independently compiling the core and
process supervisor reduced the measured fresh-object critical path about 23%.
`MLF_BENCH_SPLIT_RUNTIME=1` exposes this optional general build path. Both objects
are freshly compiled at O2 and both are linked; process support is retained.
Both candidate and baseline use the same selected build configuration.

The actual pipeline passed success, producer-failure, timeout/cleanup-related
and freshness controls in all three scheduling modes. Native embedded/split
runtime checks cover GC configurations, 1,330 completion-representation checks
and 31 process tests. A real compiler/LLVM/linker integration also passed with
identical LLVM and output, three nonempty split objects and three successful
producer markers. Evidence is under `.mlf-build/runtime-compile-split/`.

The benchmark runner now fingerprints every runtime C/header input, records its
build environment, and hashes the additional supervisor object when selected.
No workload input, C implementation, C optimization flag or gate threshold was
relaxed.

The appended String-list primitive also requires coherent artifact freshness:
the primitive inventory is now `mlf-primitive-108-v5`, and the builtin
interface/crate identity is v9. Existing constructor layouts and opcodes 0–106
are unchanged. Maintained stale-artifact fixtures now exercise rejection of v8
through metadata decoding, filesystem loading and dependency selection. The v9
builtin-artifact fixture has passed; the full separate-crate loader campaign
remains pending.

## Remaining work

The native stageA build and fresh builtin verification completed successfully:
`performance-recovery/native-prepared-current/revisions/diagnostic-121c/`.
All real offline locks/plans, the 121-module shared parser gate and independent
postflight pass. The native compiler hash is
`8c093562c511143a16640f650812d217609c8d515472883b2b53d777a007be10`.
The native build took 2044.774 s in a concurrent correctness session; this is
not a performance comparison. Its LLVM is 63.4 MB and the largest entry is
about 110,185 lines, versus 44.5 MB / 4,930 lines in the retained original
native LLVM. Concentrated literal construction is a plausible cause of the
long Clang optimization, but this is source inspection, not a causal profile.

A subsequent quiet CLI comparison emits byte-identical LLVM in all 30
invocations, but this prepared native compiler is slower than the earlier GHC
production compiler: tree 0.455878 versus 0.252897 s, n-body 0.925868 versus
0.697612 s, pidigits 0.437908 versus 0.220272 s, fasta 0.752508 versus 0.583807 s,
and k-nucleotide 0.931667 versus 0.699985 s. These snapshots also differ by the
empty imported-library adapter wiring and signature-adjacency repair; the
comparison does not isolate host implementation alone. A roughly 0.17--0.23 s
offset suggests a startup cost to investigate, not a demonstrated cause.
Evidence: `performance-recovery/native-frontend-closeout-1/receipt.json`.

The broader ground-leaf candidate passes all 212 controls and all five exact
LLVM comparisons, but its final quiet timing shows no convincing aggregate
benefit: CPU medians change by -3.94% for n-body, +0.36% for tree, approximately
zero for pidigits, +2.64% for fasta and +1.58% for k-nucleotide. It is not
promoted. See `performance-recovery/ground-leaf-{timing-9/receipt,handoff}.json`.

The first complete native-pipeline triage of the nine non-Regex workloads is
finished, with three fresh compilation/runtime samples per language and all
unchanged correctness checks. It uses the frozen production GHC compiler and
the original configured low-latency backend. Candidate and baseline compiler
hashes are identical. All input postchecks pass, but **compilation passes 0/9
and runtime passes 8/9**. This is retained as a failed diagnostic, not final
qualification: `production-nine-gate-1/{run.json,results/results.json,summary.json}`
under `.mlf-build/performance-recovery/`.

| Workload | Complete compile, s | Compile / C | Runtime / C |
| --- | ---: | ---: | ---: |
| binary-trees | 0.483299 | 3.3630 | 0.6971 |
| pidigits | 0.476916 | 3.1853 | 1.6731 |
| n-body | 0.820275 | 5.4297 | 1.2962 |
| fannkuch-redux | 0.484441 | 3.2284 | 1.6621 |
| spectral-norm | 0.490957 | 3.2557 | 0.9015 |
| fasta | 0.702412 | 4.7242 | 1.1839 |
| mandelbrot | 0.483156 | 3.4788 | 0.7530 |
| reverse-complement | 0.492406 | 3.3124 | 2.5480 |
| k-nucleotide | 0.871828 | 5.0847 | 1.6825 |

Fresh runtime C compilation dominates most rows at approximately 0.45--0.47 s.
The remaining frontend medians are 0.702 s for n-body, 0.599 s for fasta and
0.754 s for k-nucleotide. Streamed LLVM/link wall intervals include waiting for
their producers and cannot be added to frontend/runtime intervals. Reverse-
complement has pronounced I/O variation even for identical executable hashes:
C wall samples are 0.355/0.468/0.909 s and candidate samples are
0.384/1.192/1.216 s, with the same original input and input hash. The failed
runtime gate is retained; this variation is not evidence of a particular code
regression or a reason to mark it passed. Further quiet same-binary diagnosis
and a final complete run remain necessary.

A subsequent isolated five-pair repeat of the exact retained C/MLF binaries
and input gives wall medians 0.176312/0.346320 s (**1.964x**) and child CPU
medians 0.139992/0.316112 s (**2.258x**), with every output hash unchanged. This
uses the same measurement transport directly and does not replace the failed
nine-workload run or establish a full final gate. Evidence is
`performance-recovery/reverse-io-repeat-1/receipt.json`.

Complete full-native compilation/runtime measurements, wider semantic
qualification, and the final ten-workload three-sample gate are still required.
Production builtin preparation is qualified as described above. The imported
library registry remains empty pending its independent semantic/native controls
and fresh-source generation. Neither its draft wiring nor isolated backend and
library improvements establish the complete performance gate.
