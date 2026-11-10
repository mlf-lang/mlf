# Next allocation-attribution experiment: sparse source cost centres

Status: source-only design, not implementation or execution admission. No compiler,
installation, download, timing sample or production-source edit ran in this task.
Three-day sprint still starts November 10. Do not resume native A/B or fixed point.

## Decision and reason

Prefer one complete foundation14 **profiling diagnostic** with sparse manual GHC
SCCs to extra ordinary demand-window timers. It can follow delayed thunk work to
its originating semantic operation, which timers at `Right` cannot do. The
workspace official GHC 9.14.1 already has the required profiling libraries:
23 registered units in the transitive closure of the builder's six root packages
have every declared `_p.a`; the installation has 53 profiling archives and 2,212
`.p_hi` files. This is read-only presence evidence, not a successful profiling link.
No toolchain download is needed. See `toolchain-profiling-inventory.json`.

Sparse SCCs do inhibit some optimization and profiling changes object layout,
ABI, allocation and GC. Choose this knowingly for source attribution, **not** to
measure ordinary cost percentages or prove that any check is unnecessary.
Do not combine `-fprof-auto` or `-fprof-late` with the sparse pass: the historical
late profile already answered the broad function-hotspot question, but not these
particular delayed boundaries. No graph-operation counters or per-node logging.

The newly completed ordinary D allocated 60,546,927,152 bytes and copied
4,299,126,432 bytes; its sampled maximum residency was 36,197,520 bytes over 59
major samples. GC CPU 5.413 / total CPU 32.230 = about 16.8%; MUT was 26.817 CPU.
Raw RTS memory-in-use was 105 MiB, not MB. Keep raw `%GC 0.0` as an inconsistent
reported field; do not propagate it as measured zero GC. These whole-process
numbers motivate allocation attribution; they neither show unnecessary features
nor justify prioritizing GC tuning. Q 32.939s/D 34.017s are qualification only.

## Exact build scope, identity, and what is reused

- Frozen semantic source and target root: `compiler-audit-source-20261111` at
  f9bdb40a659bfdff4cbb782d438afbb0417dd2e1, clean. No production edits.
- Private, invertible GHC-only source mirror. Insert only named SCC annotations
  and syntactic grouping parentheses. Record original/annotated SHA256, occurrence
  counts, full patch, and an exact inverse transform that restores every original
  byte. Keep target files, builtin source identity and canonical file at frozen f9.
  This is host instrumentation of f9 semantics, not a new shared-language source
  snapshot or a normal producer receipt. Do not run the MLF parser on SCC copies.
- Ordinary full producer remains separately authenticated using its original
  helper, complete object inputs, builtin-verification receipt, runtime and
  alias identities. Its success does not authenticate the new profile binary.
- Build the **95 non-Main diagnostic home-module union**: emlf's 90 shared + 4
  host modules plus `MLF.Entry.BuiltinPrelude`. Generator closure is 60 non-Main
  modules. These static identities are in `proposed-build-closure.json`; actual
  GHC compile logs must match. It is NOT the 137-shared/4-host/13-program producer.
- Fresh `-prof` object/interface directories for the whole union; no ordinary
  `.o`/`.hi` mixing. Use GHC `--make -j1 -fforce-recomp -O2`, original package,
  demand-preserving and exhaustiveness flags. Build emlf and builtin-prelude with
  separate Main directories; preserve Main provenance through both links. C
  transports are rebuilt by original commands and must equal ordinary objects.
  Ordinary reference build and profile build are not performance observations.
- The original build driver cannot simply be used or called authenticated after
  an overlay is added: it rejects alternate module resolution. Make a small
  diagnostic controller with its own schema, explicit dual source mapping,
  observed GHC module provenance and complete input/output receipts. Reuse audited
  authentication functions against ordinary inputs without weakening them.
- Retain `-rtsopts=ignoreAll`. Compile in `-pj`, `-po<absolute-private-active-base>`
  and `-s<absolute-private-active-stats>`; never append runtime arguments to CLI.
  Both active paths must be absent, regular parent directories, never symlinks.
  After each terminated invocation, archive raw files under that command's unique
  directory before any subsequent invocation. Refuse stale paths or uncertain
  process shutdown; do not truncate unarchived results. Generator has its own
  fixed destinations. Keep existing foundation D/used-once contract untouched.
  Profile options do not change nursery, capabilities or GC policy.

## Sparse attribution map

Use SCCs on the exact RHS expressions below, not on artificial forcing wrappers.
A function RHS annotation covers naturally deferred result fields; annotate the
actual producer of a lazy field, not only a later getter. Keep no AST in reports.

1. CompilerCore.finishCompilation: distinct call-expression labels for
   `C.generateProgram`, `C.solvePrepared`, `E.prepareTypes`,
   `E.resolveEvidenceIn`, `E.elaboratePreparedIn`, and `E.schemeTypeIn`.
2. `X.Checked.check` full RHS: CLOSED_CHECK. In CompilerCore, separate the
   inferred-type `T.alphaEq` and the complete source/target `X.equalErased`
   predicate into TYPE_AGREEMENT and ERASURE_AGREEMENT.
3. InferenceUnit.finishOpenGroup: OPEN_ENV around `Open.environment`, OPEN_INITIAL
   around the complete `Open.check env parameters implementation` call. Ownership
   comparison gets OPEN_OWNERSHIP. No replacement with Open.fromChecked.
4. X.Check.inferDeclarationSpine: INVENTORY on each **deferred**
   `closedBindingInventory ...` RHS and terminal inventory RHS, retaining the
   outer CLOSED_CHECK / OPEN_INITIAL / OPEN_NORMALIZE context. Never pull this
   independent Either out of its pair. Generic annotation without that calling
   context cannot distinguish closed and open inventory.
5. SourceInference.canonicalOpen: CANONICAL_PLAN on `Wire.prepareGraphPlan ...`
   including the Structure.toXTerm thunk; CANONICAL_REALIZE on
   `Wire.realizeGraphPlan plan`; CANONICAL_SYNTAX on `finalSyntaxRun ...`;
   CANONICAL_RESULT on `finalSyntaxTerm`; OPEN_NORMALIZE on the changed branch's
   existing `Open.normalize object result`. Keep every limit and branch intact.
6. OpenFragment.stamp full RHS: STAMP, covering the actual lazy pretty/pack/hash
   expression even when first demanded by encoding. OpenFragment.make's
   free-name field and fresh's corresponding producer get FREE_NAMES if present
   in this run; never force them eagerly.
7. QueryGraph.encodeHashed: ENCODE around the existing `Storage.encode 6 [value]`
   IO action; CONTENT_SHA around existing `byteArrayDigest bytes`. Publish gets
   PUBLISH. Keep nested STAMP and other producer tags distinguishable; ENCODE's
   inherited cost includes its children, not just the codec. This encoding scope
   covers query payloads/indexes, not every output encoder. Residual output
   serialization remains explicitly unclassified, not silently assigned to ENCODE.
8. Elaborate.edgeComputationIn: WITNESS_FALLBACK on the existing Solver.witness
   call. This measures actual fallback demand. Do not infer exact logical edge
   counts from SCC entries or turn an absent label into universal zero fallback.

Preflight confirms source locations and exact match counts against the pinned
files; an independent reviewer checks expression grouping and inverse identity.
No new seq/deepseq, tuple destructuring, bottom test on production values,
unsafePerformIO, NOINLINE, CAF switches, or altered evaluation order.

## Laziness contract and reporting

`CheckedTerm` contains an independent deferred inventory Either. A successful
Closed.check/Right/WHNF is not completion of that inventory. Existing consumers
must decide whether it is evaluated. Open.check consumes its own inventory but
leaves stamp/free-name fields lazy. Do not force these early to make charts tidy.
GHC's documented SCC rule stores the creation stack in a thunk and restores it
when evaluated. This is why STAMP and inventory annotations belong at their RHSs.
Shared thunks/CAFs and code outside annotated expressions can remain unattributed;
include that residual and report actual stacks rather than inventing ownership.

Read raw JSON cost-centre tree. Validate unique IDs, known references, acyclic
traversal, nonnegative integer self allocation/ticks, and sum of self fields.
Confirm JSON allocation units with a tiny known-allocation control plus the
installed RTS definition before converting words/bytes. Keep raw units too.
Profile allocation excludes profiling bookkeeping in its own accounting and is
not identical to RTS total allocated bytes. Reconcile each report internally;
never force profile sum = RTS bytes or ordinary D bytes.

Produce both (a) raw self/inherited stacks and (b) one disjoint partition assigning
each tree node's self allocation to the nearest semantic tag in its stack, with
INVENTORY preserving its nearest checking context and residual/CAF/RTS buckets.
Sum each self node once. Never sum parent and child inherited rows. If a stack
cannot establish closed/open ownership, label it unresolved. Time ticks may be
reported as profiled sampling only. No exclusive ordinary CPU, wall-time savings,
causal necessity, native cost or multiplication of profile shares by the 60.55GB
ordinary total. The actionable result is a ranked request for a semantics-preserving
optimization proof, not authorization to remove checks.

## Independently admitted gates and one actual diagnostic

No phase automatically launches the next. All phases use the current shared
`<WORKSPACE>/.astra-resource-locks/heavy.lock`, same inode,
nonblocking flock, required reproduction lock, actual descendant tracking across
sessions, and post-exit independent reacquisition. Never use the old shared path.
All retain tree RSS <=5GiB, per-process AS <=6GiB, free disk >=5GiB, available host
memory >=3GiB, bounded output <=4GiB. No endpoint exceeds 600s. No continuation
from a timeout, partial cache, shortened target or opportunistic second sample.

A. BUILD, <=600s: once separately admitted, compile the diagnostic union and two
   Mains, pin full profiling package/interface/toolchain closure and code identity.
   Runtime/library/alias checks and cleanup must pass. Source-only design has not
   proved the build fits; failure stops rather than enlarges the window.
B. QUALIFY, <=180s: unchanged original `--check-shared` over **all 137 frozen
   shared target source files**, CLI version/implementation identity, original
   literal 42/Unicode positives and type negatives. Run unchanged
   `verify_builtin_prelude.py --root FROZEN --compiler PROFILE_EMLF
   --generator PROFILE_BUILTIN --output NEW` under the outer guard. It must really
   execute check-candidate and fresh-literal, compare exact original banner and
   full canonical bytes, require empty stderr, then authenticate its receipt.
   Default RTS stats go to files, never verifier stderr. Do not substitute the
   ordinary generator's old output or annotate/rewrite canonical identity.
   Qualification controller uses the same annotated objects and exact binaries
   subsequently measured; outer timeout controls verifier-created sessions.
C. PROBE-CONTROLS, <=120s: retain archived real supervisor-child cancellation,
   compiler POSIX-lock ownership/reacquisition, ordinary exit124 rejection,
   hard-kill/missing-profile rejection and real nonzero JSON profile controls.
   Add delayed producer/consumer toy: SCC A builds a thunk consumed under B;
   confirm source allocation belongs to A without forcing it at A's return.
   Add exact closed-type-success/deferred-inventory-Left and no-demand-bottom
   cases, independent open-owned/export-type failure, and unchanged invalid-type
   and source-erasure controls from maintained fixtures. Test ignored literal
   +RTS/-RTS argv, stale/symlink/profile-missing failures, and zero instrumentation
   output changes. Require reviewer to identify actual fixture paths, expectations
   and complete test coverage before admission; do not claim these tests ran here.
D. TARGET-QUALIFICATION, <=420s total, <=180s each compile: fresh ordinary Q and
   fresh profiled P against the same frozen14 modules/173,594bytes, same ordered
   builtin pair and crate id, distinct empty caches. Use fully successful current
   foundation14 setup/builtin receipts after reauthentication, not failed
   inference11 prefixes. Require475fresh/0reuse, full ordered query JSON and all
   three raw files (.mlfci/.mlfco/.queries) byte-identical to each other and retained
   ordinary-Q reference. Ordinary show-crate checks all14 owners/builtin identity;
   before/after pins, runtime and query locks remain mandatory. P's profile is
   explicitly qualification evidence, not the selected attribution observation.
E. ATTRIBUTION, <=240s outer / <=180s compile: one newly claimed fresh foundation14
   run of the exact P binary after D passes, unchanged flags/source/dependencies.
   Same complete raw oracles and475/0 gate against Q; preserve raw .prof and RTS
   files plus command/guard/outcome receipts. No extra warmups or repeat. Timeout
   retains an incomplete prefix only and fails the planned complete attribution.
   Compare ordinary/profiled total allocation and wall descriptively to disclose
   perturbation, not as a speed experiment. Build/controls are outside this run.

## Existing infrastructure: reuse only what is true

The reachable Git checkpoint fa7df4c39897a7dad4d21a44087c5927a12dc8d4 contains
`tools/performance/full-compiler/late-profile-20261110/source/{ProfileMain.hs,
p1.py,owned_child.py,run-phase.sh}`. Its 95-home-module profiled emlf build,
shutdown outcome protocol and six negative controls are useful precedents.
Its 320.047s build is historical feasibility, not current admission or a bound.
Do not run it unchanged: old absolute paths/receipts/locks, 90-module workload,
-fprof-late, runtime -rtsopts parsing, weak tiny .queries comparison and old wrapper
comments do not describe this experiment. Raw old .prof/binaries are not recovered.
Use current foundation controller's full-query/raw-three-artifact, alias, actual
runtime and descendant-resource checks. The installed QueryGraph phase clocks
measure graph/load/infer/finish/output/publish wall demand and are not SCC-source
allocation attribution. Leave MLF_QUERY_PROFILE and semantic audit switches in
ordinary state; never change a semantic gate for profiling.

## Fallback if profiling libraries/link/build are unavailable

Stop that admission and report exact missing unit/link failure. Do not silently
install, enlarge budgets or fall back within the same failed run. A separately
reviewed ordinary diagnostic may wrap only existing CrateGraph/QueryGraph IO and
existing seq/case demand boundaries with the current thread's
`GHC.Conc.getAllocationCounter` reads (before-minus-after; never enable the quota,
reset it midwindow or spawn another thread for the measured work). A private
host adapter records small numeric totals and counts after windows, not ASTs.
Include empty-window and allocating controls, thread-identity checks, raw counter
values, wrapper-allocation disclosure and process-wide RTS residual. Use the same
foundation qualification/raw oracles and resource gates. No new deep forcing.
Do not use short-window RTS allocated_bytes readings as exact per-operation
allocation: GC update granularity/runtime bookkeeping require separate validation.

This fallback measures actual allocation **demand windows** (raw-demand,
record/encode, finish, publication), including any earlier lazy work they demand.
It cannot honestly separate closed checking from solving/canonicalization inside
raw demand or late stamp work from encoding. Name that unresolved question;
do not label windows after presumed exclusive phases or subtract one from another
to fabricate the missing source partition. Its lower build cost does not make it
the highest-value first choice while the profiling toolchain is available.

## Recovery inputs

`recovery-inputs.json` pins exact local successful producer, builtin, foundation
receipts, original raw Q/D artifacts, RTS text and controller sources. The older
source audit is referenced, not duplicated. `proposed-build-closure.json` fixes
all95 names/paths; actual build must verify it. `toolchain-profiling-inventory.json`
records read-only availability and configuration hashes, not full library pins.
Controller-owned plan files remain untouched. Parent owns publication. This
checkpoint contains no executable launcher and grants no heavy-work admission.
