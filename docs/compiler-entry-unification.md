# Unifying compiler entry points

Status: shared checked-root finalization is implemented in this change; the
common incremental session described below is a follow-up design. Source
loading and checked root preparation were already shared in the baseline. The
three source routes do not yet use one incremental inference session. This
document distinguishes those changes and defines the conditions for the
remaining migration.

The baseline for this analysis is
`a619434b4b4233ea29ce1703ce01434a8765488c` (`Share checked root compilation and
build backend drivers as package targets`). This change additionally introduces
`CompilerCore.finishCheckedRoot` and routes closed and imported finalization
through it. Other existing API names refer to the baseline. Names explicitly
marked **proposed** describe interfaces to introduce, not interfaces available
today. Implementation does not by itself establish the acceptance or
performance results specified below.

## Decision

Retain the public ways of supplying a program and its dependencies. Consolidate
their compilation machinery behind a common request, a resolved root plan, and
one declaration-group engine. Treat persistent caching and installed native
linking as explicit execution and dependency policies.

A file, an expression, a package target, and a root linked against an installation
have different input and output requirements. They should not require different
implementations of MLF inference. Conversely, combining their command-line
spellings would not remove the duplicated implementation or make source
compilation incremental.

The target design must preserve the generic AST compiler as a compatibility and
reference API. Parsed, owned source may use the file-oriented group engine;
arbitrary `SProgram` values must not acquire its ownership assumptions merely
because a caller requests a faster policy.

## What is already shared

| Area | Current shared implementation | Remaining boundary |
| --- | --- | --- |
| Source input | `PreparedCompiler.Source`, `readSource`, `loadSourceRoot` | Ordinary source and native roots still select different compilation policies after loading. |
| Module resolution | `Module.resolveSourceRoot`, `linkResolvedForCompilation` | Package planning also assigns crate identities, exports, and an entry declaration. Those are not interchangeable with an ordinary root. |
| Source headers | `Classes.canonicalSourceHeaders` | Callers still supply their own checked imported data and class context. |
| Checked library root | `PreparedLibraries.checkLibraryRoot` | This shares prepared-source and installed-native root checking. The ordinary source fallback still calls `Compiler.compileResolvedRoot`. |
| Checked root finalization | `CompilerCore.finishCheckedRoot`, used by `finishSolvedCompilation` and `ImportedRoot.finishUsingSolver` | Constraint generation, solver policy, imported-parameter authentication, and result adapters retain their existing responsibilities. |
| Package session | `CrateSession.compileInSession`, `loadPlan` | The session accepts a crate specification and an output prefix, not an ordinary source request. |
| Artifact closure linking | `CrateArtifact.linkCheckedClosure` | Closing checked imports and retaining native imports remain different output operations. |

The relevant call paths are:

| Entry | Current inference path |
| --- | --- |
| Ordinary file/module source | `PreparedCompiler.compileSource` → `PreparedLibraries.compileLoaded` → prepared-library admission or `Compiler.compileResolvedRoot` → `CompilerCore.finishCompilation` |
| Standalone source/expression | `PreparedCompiler.compileSource` → `compileProgramWithPrelude`, including its existing prepared-Prelude admission and ordinary fallback |
| Package/crate | `CrateSession.compileInSession` → `Crate.prepareFileCrate` → `CrateGraph.compileFile` or `compileLoweredIn` → `SourceInference` and `InferenceUnit` |
| Installed native root | `PreparedCompiler.compileNative` → `PreparedLibraries.compileNativeRootUsing` → `checkLibraryRoot` → `ImportedRoot.finishSelected`; native emission retains authenticated external imports |

Backend drivers now being package targets changes the route used to build those
drivers. It does not by itself change the route selected by an unrelated
`emlf --emit-llvm-gc FILE` invocation.

Sources: [source orchestration](../bootstrap/MLF/PreparedCompiler.hs),
[ordinary compiler](../libraries/mlf-inference/Bootstrap/Compiler.hs),
[prepared libraries](../libraries/mlf-crates/Bootstrap/PreparedLibraries.hs),
[crate session](../libraries/mlf-crates/Bootstrap/CrateSession.hs),
[crate graph](../libraries/mlf-crates/Bootstrap/CrateGraph.hs).

## Placement and dependency direction

Place common request orchestration in `mlf-crates`, with CLI input acquisition
and installation discovery in `MLF.PreparedCompiler`. Keep reusable constraint,
solver, evidence, and elaboration operations in `mlf-inference`.

`mlf-crates` already depends on `mlf-inference`; `SourceInference`,
`InferenceUnit`, and `ImportedRoot` live in `mlf-crates`. Importing that engine
directly into `Bootstrap.Compiler` would reverse this dependency and create a
cycle. A common orchestrator above both routes avoids the cycle without moving
package artifacts, caches, or installation code into the inference library.

`Bootstrap.Compiler.compileProgramWithPrelude` and the other pure AST APIs can
remain thin compatibility adapters around the existing generic inference
policy. The production source frontend should invoke the common orchestrator
after it has established ownership of parsed input.

Sources: [inference package manifest](../libraries/mlf-inference/mlf-package.json),
[crate package manifest](../libraries/mlf-crates/mlf-package.json).

## Proposed request and root plan

Introduce a **proposed compilation request** with independent fields for input,
dependency admission, result kind, and storage policy. Do not encode these
choices in one Boolean such as `isCrate` or `useNative`.

| Request component | Required information |
| --- | --- |
| Source origin | File, expression, stdin, or package target; diagnostic source name; exact buffers used for parsing and import resolution |
| Language context | Prelude mode, explicit import search paths, and the existing module/instance visibility rules |
| Dependencies | Source modules, validated crate interfaces and objects, or an admitted installed library with its fixed native layout |
| Result | Checked closed program, package artifact, ordinary LLVM, or native root with checked external imports |
| Execution | Invocation-local storage or a persistent cache; compiler identity and requested profiling/reporting |

Then produce a **proposed resolved root plan** that owns:

- The resolver's declaration table, stable identities, display names, value
  scopes, and instance scopes.
- Canonical source data/class headers and admitted imported contracts.
- Declaration groups, their dependencies, and the original root continuation.
- The distinction between user result type and any compiler-introduced import
  or dictionary parameters.
- Evidence that the source is a finite, parsed, compiler-owned input when the
  file-oriented inference policy is selected.

Use the existing `Module.ResolvedCrate`, `SourceInference.SourcePlan`,
`SourceInference.sourcePlanUsing`, `initialContracts`, and checked contract
operations as the starting point. Extract only the missing root adapter; do
not invent a second SCC planner or a parallel declaration-identity scheme.

An ordinary root must not be converted into a temporary on-disk `CrateSpec`
without proving equivalence. `Crate.prepareCrateUsing` assigns crate-specific
names, constructs export metadata, and can append a generated entry binding.
Those choices can change scopes, printed names, grouping, or generalization
boundaries. The common root plan should carry an explicit root continuation
instead. If it internally represents that continuation as a declaration, tests
must establish that the representation neither introduces an annotation nor
changes the SCC and generalization boundaries of user declarations.

The plan must retain the exact resolved closure used for admission. Re-reading
files independently during inference would lose the relationship between the
checked source and its dependency evidence.

Sources: [module resolution](../libraries/mlf-frontend/Bootstrap/Module.hs),
[crate preparation](../libraries/mlf-crates/Bootstrap/Crate.hs),
[source inference](../libraries/mlf-crates/Bootstrap/SourceInference.hs).

## One group engine with explicit storage

Extract the existing `CrateGraph` group execution behind a session supplied by
the caller. Preserve `SourceInference` contract preparation, group order,
`InferenceUnit` checking, evidence finalization, and checked contract extension.
The source adapter and crate adapter should invoke these same operations.

### Invocation-local storage

Add a **proposed memory session** to `QueryGraph`. It must be a distinct mode,
not a disk session with an empty directory or a temporary path.

- Start with no previously published nodes. Keep current nodes and pending
  payloads for the lifetime of the request or explicitly retained invocation.
- Retrieve payloads through one operation that checks current pending bytes
  before consulting the configured backing store. A memory session has no disk
  backing store.
- Preserve query identity, dependency hashes, payload validation, and checked
  result admission. Memory storage is not permission to accept unverified
  fragments.
- Do not create cache directories, lock files, `CURRENT` pointers, or package
  artifacts for expressions and stdin merely to run inference.
- Make publication unavailable or explicitly a no-op for this mode. Avoid a
  path convention that could accidentally address `/results` or another
  unrelated directory.

Today `QueryGraph.begin` creates directories and reads the published index.
`CrateGraph.startGroupUsing` invokes it directly, while cached group and
evidence reads use `QueryGraph.payloadPath` and disk readers. A complete memory
policy must adapt those reads as well as session creation. Adding only a
`beginMemory` constructor would leave hidden filesystem operations in the
supposedly in-memory route.

### Persistent storage

Keep lock acquisition, source/tool identity validation, cache admission, output
publication, and reporting under `CrateSession` or its extracted storage
adapter. Reuse the existing graph engine with a persistent session.

Cache identity must include all semantic inputs already required by the
relevant query: compiler identity, query/checker format, dependency contracts,
source groups and their scopes, Prelude mode where relevant, and imported
layout identities where relevant. A matching filename or public symbol name
is insufficient. Installation or source changes must invalidate affected work.

`CrateSession.freshSession` currently means that plan dependencies are read from
disk rather than retained from a package plan. It does **not** mean an ephemeral
or cache-disabled compilation. Keep this distinction explicit in the new API.

Storage extraction alone establishes a common runner. It does not establish
that ordinary roots have equivalent inference boundaries; that is a separate
acceptance gate.

Sources: [query graph](../libraries/mlf-crates/Bootstrap/QueryGraph.hs),
[group execution](../libraries/mlf-crates/Bootstrap/CrateGraph.hs),
[session/publication](../libraries/mlf-crates/Bootstrap/CrateSession.hs).

## Checked root finalization and native imports

This change performs a preliminary consolidation below the group runner.
`CompilerCore.finishSolvedCompilation` and `ImportedRoot.finishUsingSolver`
now delegate to `CompilerCore.finishCheckedRoot` to resolve evidence, elaborate
a solved graph, independently check the target, compare inferred and checked
types, and compare source and target erasures. It uses `resolveWithinIn` and
`elaborateWithinIn` with an empty outer type environment, matching the previous
`Elaborate` helpers.

The shared stage takes the existing type context, datatype environment, solved
constraints, source declarations, authenticated parameters, checker, and exact
verification messages. It returns both the checked wrapper and the user type.
The generic solver and file solver policies remain outside it. The ordinary
caller still derives the datatype environment from the supplied type context;
the imported caller still supplies its additional kind environment and
authenticates parameters before evidence resolution. Ordinary source rendering
still uses the checked type, while imported source rendering uses the separate
user type.

The imported case carries additional obligations that a closed result does not:

1. `ImportParameters` identifies the exact selected declaration inventory.
   `ImportedRoot.verifyImportedParameter` checks every parameter against its
   authenticated contract after solving, including unused parameters.
2. Imported kinds can extend the datatype environment used for evidence and
   elaboration. Dropping them changes checking behavior.
3. The checked wrapper has import arrows; the user result type does not. Keep
   both values instead of deriving the reported user type from the wrapper.
4. Expected type and expected erasure must include the same ordered wrapper
   parameters. Independent target checking remains mandatory.
5. File group checking may use the existing checked open environment. Preserve
   its admission checks and diagnostic replay rather than substituting a
   less constrained checker.

After group inference, use separate, narrow result adapters:

| Result adapter | Required operation |
| --- | --- |
| Closed source program | Close selected checked dependencies and return a checked term with the user-facing source type. |
| Package artifact | Preserve declared exports, identities, interfaces, dependency metadata, and atomic publication. |
| Installed native root | Retain checked external parameters and their exact declaration-to-export mapping; materialize the required builtins according to the existing policy. |

For native roots, retain `PreparedLibraries.NativeRoot`, `nativeLayoutIds`,
`nativeSelectedIds`, and the fixed export layout prepared in
`PreparedCompiler.nativeLayoutFor` until the replacement has equivalent
invariants. Preserve installation identity, nominal datatype ownership,
constructor layout, selected signatures, parameter order, and builtin handling.
Passing the wrapper through a closed crate artifact is not an equivalent
substitute: it can erase the distinction between imported native values and
locally compiled definitions.

Sources: [closed finalization](../libraries/mlf-inference/Bootstrap/CompilerCore.hs),
[elaboration helpers](../libraries/mlf-inference/Bootstrap/Elaborate.hs),
[imported root](../libraries/mlf-crates/Bootstrap/ImportedRoot.hs),
[group inference](../libraries/mlf-crates/Bootstrap/InferenceUnit.hs),
[native root admission](../libraries/mlf-crates/Bootstrap/PreparedLibraries.hs),
[native layout/emission](../bootstrap/MLF/PreparedCompiler.hs).

## Staged migration and acceptance gates

Each phase should be a separately reviewable change. A phase is complete only
when its stated behavior is exercised, not merely when the new API exists.

### 1. Establish the behavioral comparison

Capture the existing entry behavior for ordinary files, modules, expressions,
stdin, package targets, and installed roots. Include both Prelude modes,
explicit search paths, and source shadowing of installed modules.

Require fixed expected types, values, diagnostics, or independently checked
xMLF for representative cases. Differential checks against the old engine are
useful in addition, but comparing two adapters that now call the same function
is not an independent oracle.

Acceptance: tests detect a changed CLI exit status, diagnostic phase, public
source name, printed type, or program result before production routing changes.

### 2. Share finalization without changing inference policy

Implemented in this change by `CompilerCore.finishCheckedRoot`. The common
evidence/elaboration/checking stages preserve the existing solver selection,
type-context strategy, import checks, source-name restoration, and error
ordering at each caller. Verify these properties through the controls below.

Acceptance: closed and imported positive/negative controls preserve type and
erasure agreement; unused malformed imports still fail; existing generic AST
demand and diagnostic tests remain valid. This phase may be described as shared
finalization, not unified incremental compilation.

### 3. Extract storage from group execution

Make `CrateGraph` accept an explicit query session/storage provider. Exercise the
same prepared groups through fresh memory, cold disk, warm disk, and retained
invocation sessions.

Acceptance: equivalent checked results and failures; no filesystem access from
the memory provider; same-session payload reads work; corrupted disk entries
are rejected or recomputed under the existing policy; interrupted publication
does not publish a successful result. Existing package cache behavior remains
unchanged.

### 4. Adapt ordinary owned roots

Build the common root plan from `loadSourceRoot` and resolved source identities.
Run declaration groups through the shared engine and close their checked
dependencies into the root. Begin with invocation-local storage; persistent
source-cache policy can follow after equivalence is established.

Acceptance: the matrix below passes on the ordinary CLI, and the resulting
checked target passes the independent checker. Retain the generic AST API and
its existing graph/demand behavior. Preserve `CompilerCore.presolution` for
generic callers; a collection of group graphs is not a drop-in replacement for
the existing whole-program graph.

### 5. Adapt installed native roots

Use the same root planner and group engine with authenticated imported
contracts, then invoke the native result adapter. Keep any compatibility
fallback explicit and observable in existing diagnostic/reporting fields.

Acceptance: source shadowing, selected export IDs, hidden dictionary imports,
unused import validation, datatype layout extension, native execution, and
installation relocation controls pass. A fallback that silently recompiles
everything through the ordinary engine does not demonstrate this migration.

### 6. Enable measured reuse and remove duplicate orchestration

Only after ordinary and native roots pass their semantic gates, choose defaults
for persistent source caches and cross-target retained sessions. Remove the
superseded production orchestration while retaining public compatibility
adapters where needed.

Acceptance: ordinary source, crate, and native source requests all execute the
same source-group planning, contract extension, and checking implementation;
storage and result adapters account for the remaining differences. Re-running
an unchanged request demonstrates real reuse, and edits invalidate the correct
dependent groups.

## Required behavioral matrix

| Contract | Representative controls and expected property |
| --- | --- |
| Principal inference | Polymorphic identity at different instantiations; higher-rank arguments; no accidental monomorphization or new inferred annotation boundary |
| Generalization | Captured variables, unsigned self recursion, mutual SCCs, and independent argument polymorphism; solve the whole SCC before generalization |
| Class evidence | Qualified recursion, local class scopes, re-exports, hidden dictionaries, and instance visibility; preserve the defining module's authorization |
| Datatypes | Local/ imported nominal types, higher kinds, and constructor layouts; reject forged or mismatched metadata |
| Laziness and diagnostics | Unused malformed source annotations/import parameters, demand-order controls, and failing optimized group attempts; preserve required validation and fallback diagnostics |
| Input acquisition | File, stdin, expression, missing file, missing/ambiguous import, search-path precedence, and both Prelude modes |
| CLI output | Existing type and xMLF presentation, diagnostic phase and exit status, runtime output/effects, and LLVM commands' expected output behavior |
| Imported native boundary | Correct selected IDs, wrapper parameter order, hidden evidence dependencies, builtin materialization, and reported user type |
| Cache behavior | Fresh memory, cold/warm disk, source and dependency edits, changed compiler/installation, corrupt payload, and failed publication |

Extend the independent cases already present in
[SharedFrontend](../tests/shared/MLF/Tests/SharedFrontend.hs),
[indexed graph controls](../tests/indexvec/Graphs.hs), and
[qualified recursion controls](../tests/recursive-inference/QualifiedCrateHost.hs).
Run the affected ordinary CLI, package, and native contracts through their real
entry points as described in the [test guide](../tests/README.md). Keep stable
test IDs and register any new private test modules in the importing targets.

## Performance evidence

Unification should remove duplicated work and enable reuse, but neither follows
from a smaller number of entry functions. Measure them separately.

Use the same commit, source closure, host machine, host compiler optimization,
and requested output. Record cold compilation, repeated compilation, and a
small dependency edit separately. For the backend-driver investigation, compare
the same driver with O0 and O2 hosts in serial runs; the routine and optimizer
CI job totals are different workloads and cannot establish that comparison.

Record loading/resolution, source planning and class work, group inference,
evidence resolution, elaboration/checking, cache read/write, LLVM preparation,
LLVM emission, and native object/link costs. Include peak memory and group/query
counts so a cache or planner change cannot conceal a new growth problem.

Use the existing
[compiler-shapes harness](../tools/performance/compiler-shapes/README.md)
for a reduced independent-oracle reproducer when profiling identifies an
algorithmic bottleneck. Preserve bounded query payloads and avoid repeatedly
serializing a growing dependency closure once per declaration. A memory session
may still perform canonical hashing and validation; it is not automatically
faster for a single small expression.

Report speedups only after these matched measurements. The architecture's
completion criterion is shared inference behavior with preserved contracts;
its performance result must be reported from the actual cold, warm, and edited
workloads.
