# Benchmark performance recovery, 2026-10-26

This investigation starts at `2957dd08321c38dbf94a75cb275a5f48e897f58e`.
The requested gate is **compilation <= 3x C and runtime <= 2x C**, using the
unchanged ten-workload manifest, correctness inputs, fixtures, default inputs,
C programs, and C flags. Recovery is still in progress; the measurements below
are not a claim that the final ten-workload gate passes.

## 2026-10-27 checkpoint

The normal compiler entry now selects the prepared builtin route for eligible
standalone roots and retains the ordinary fallback. Canonical generated data
uses builtin identity v9, exact source witnesses and independent startup/final
checking. The frozen production candidate passed fresh regeneration, 33 semantic
comparisons, 36 native O0/O2 executions, 46 direct-import controls, 39 context
mutation controls and 15 builtin artifact checks. All 231 qualification input
pins remained unchanged. Evidence is `production-controls-1/receipt.json` under
`.mlf-build/performance-recovery/`. This is finite macOS correctness evidence;
production timing, native-host qualification and the complete performance gate
remain pending.

The generic imported-library adapter and its tooling are included as unfinished
drafts. They are not registered or selected by the normal entry, no fixed library
data has been generated, and complete semantic/native/performance qualification
has not run. Imported roots still use the ordinary compiler. The accepted Regex
source is the inline41 version described below; replacement, weighted-credit,
streaming-join and additional solver experiments have not been promoted.

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

Complete fresh-source frontend/runtime measurements, wider semantic
qualification, and the final ten-workload three-sample gate are still required.
The installed-Prelude experiment is not silently selected: its whole-root
inference, imported source schemes, declaration order, and independent checking
must be preserved and verified before a production reuse path can replace
repeated Prelude inference.
