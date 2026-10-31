# Prepared library source tooling

This directory prepares and qualifies a compiler-owned registry of fixed library
checked ASTs. It does not cache user roots, infer user SCCs separately, or reuse
native object code. The adapter and tools have passed the finite fixture
qualification described below. The production registry remains empty until a
separately frozen production library is generated and independently qualified.

`RawLibrary` SHA-shaped strings are not authentication by themselves. The normal
entry may consume only the generated compiler registry. Build qualification must
independently regenerate its source and compare it exactly with the canonical
module, including source and object SHA256 commitments. Existing artifact
admission and the independent final target checker remain mandatory.

## Preparation

Run `prepare.py --library-manifest libraries/mlf-foundation/mlf-package.json
--module Bootstrap.Regex --output NEW_DIRECTORY` after the canonical core,
literal renderer, and `MLF.PreparedLibraryData` module are registered in
`shared-sources.json`. Requested module names are generic library roots, never
program or benchmark selectors. Multiple `--module` arguments form one union
closure. No extra module is included in the resulting registry merely because
it appears in the library manifest.

Preparation snapshots every registered compiler source, host glue, tool source,
and library input; it does not execute a compiler. Its input identity includes
exact source hashes, requested roots, ordinary source package `main`, Prelude
mode, frontend semantics, primitive ABI, and exact production lexical source
paths. Snapshot storage paths do not enter that identity. The previous generated
registry is excluded from its own regeneration key.
`--lexical-root` selects the exact ordinary loader prefix without filesystem
canonicalization; its default is the absolute library-manifest directory.
The frozen bytes can be stored elsewhere, but the parser filename is never
silently replaced by the snapshot path or a resolved symlink target.

`build.py --job NEW_DIRECTORY --ghc ABSOLUTE_GHC --cc ABSOLUTE_CC` is an explicit
later execution step. It uses one immutable source tree and the manifest's
ordinary source roots. There are no include overlays. Its generator:

1. Reads frozen buffers while passing the original lexical paths to
   `Parser.parseModule`, which supplies package `main`.
2. Selects and validates the actual requested dependency closure using
   `Module.loadGraphBy`, carrying the exact parser read in `LoadedModule`.
3. Generates the fresh builtin object, then calls `Crate.compileSources` on
   manually ordinary-parsed and hygienically cleaned library sources, with a
   declaration-only crate entry and the fresh builtin dependency.
4. Reopens `.mlfci`/`.mlfco`, computes their SHA256 using native `fileDigest`, and
   calls `PreparedLibraries.prepareFresh`. This is registry admission; it does
   not infer a user program or create unchecked `CheckedTerm` evidence.
5. Renders the raw registry through `PreparedLibraryLiteral.rawLibrary` and
   writes both artifacts and a generation receipt.

The generated data is copied only to its registered canonical path inside the
owned snapshot before building the probe. Publishing it to the production tree
belongs to the parent and its normal source-registration/build qualification.
The generator never imports the generated registry, so fresh generation cannot
silently reuse its previous output. Relative-path or relocated source profiles
need their own exact registry; string-literal path rebasing is not performed.

## Independent fixture corpus and regeneration

The checked-in `fixtures/mlf-package.json` contains six small library modules.
`fixtures/controls.json` gives 33 independent acceptance, route, output, and
layout-order oracles. The library exercises exported and private classes,
private instance helpers, higher-rank and bounded contracts, quantified data
fields, and managed call-stack boundaries. It is independent of any benchmark
program and can be qualified before a production library freeze.
An unsigned constrained module binding is a positive dictionary-abstraction
control: its caller may supply a visible instance. A separate signed binding
with an unqualified `String` contract must resolve its wanted evidence in the
defining module and reject when that module lacks the instance.

Prepare this corpus with `prepare.py --library-manifest
tools/experimental/prepared-libraries/fixtures/mlf-package.json --module
Fixed.API --output NEW_JOB`, then run the explicit `build.py` step. Next run
`materialize.py --job NEW_JOB --output NEW_CONTROL_INPUTS`. Materialization
copies mutations into its own new directory and writes `manifest.json`; it
does not invoke a compiler. Expected results are checked-in literals. Only
exact source paths and actual generated protected names are substituted.
The latter deliberately trigger value-name and dictionary-name collisions.
All dependency bytes consumed by each request remain pinned.

`regenerate.py --job NEW_JOB` independently rebuilds the producer with fresh
host objects and fresh GHC object directories, and invokes it with an empty
new query-cache directory. Before invocation it saves immutable copies of the
first generated module and both builtin/library `.mlfci` and `.mlfco` pairs.
The second invocation uses the **same exact lexical source and artifact output
paths**, then compares all five outputs byte for byte. Absolute builtin
dependency paths in metadata are preserved; neither paths nor string literals
are normalized. The claim is same-path-profile reproducibility, not cross-job
byte reproducibility. On failure the first outputs remain in the saved backup.

Materialization requires successful immutable producer and probe build steps;
regeneration requires successful immutable producer steps. If an unrelated
later loader-control build failed, its original failure receipt is retained
and the derived receipt explicitly records `producer_full_build_complete` or
`first_full_build_complete` as false. This permits diagnosis of completed
producer artifacts without treating the full build as successful. Full
qualification still requires the separately completed loader controls.

## Differential probe and qualification

`Probe.hs` is shared Haskell syntax. It accepts
`inspect|emit|run ordinary|prepared REQUEST.json`. A request contains:

```json
{
  "source_path": "/exact/lexical/Root.emlf",
  "buffer_path": "/owned/frozen/Root.emlf",
  "include_paths": ["/exact/lexical/library-root"],
  "no_prelude": false,
  "arguments": []
}
```

Ordinary file loading is the default. For source-mutation controls only, an
optional complete `source_map` supplies `{module, source_path, buffer_path}` rows.
The map uses the actual parser and graph validator and preserves lexical
provenance while reading owned frozen mutation buffers; it never overwrites a
live library. It is explicitly a source-map API test, not a file-search test.
Qualification-only `registry_variant` values `stale-builtin-witness`,
`stale-schema`, and `invalid-source-hash` corrupt the linked compiler data inside
the probe. The witness control changes only the canonical `implementationHost`
binding's string body, preserving its path, name, declaration header, schema
and primitive count, and must fall back. Its original-body precondition prevents
a facade change from silently making the mutation ineffective. These options
are absent from the production entry and are not a raw registry loading API.

The inspection report contains the raw structural principal target type,
ordered datatype and constructor layouts, and exact source Entity mapping.
Dictionary correspondences come from actual class lowering on the ordinary
route and the documented stable dictionary identities on the prepared route.
`compare.py` independently checks alpha equivalence of bound variables and that
explicit nominal correspondence. It performs no generated-name regex stripping,
layout sorting, source-path normalization, or diagnostic digit stripping.
Every consumed source buffer is returned as evidence and matched to pinned
bytes by the qualification driver.

`qualify.py --probe PROBE --manifest CASES.json --output NEW_DIRECTORY` consumes
an explicit finite control manifest:

```json
{
  "format": "MLF-PREPARED-LIBRARY-CONTROLS-1",
  "inputs": ["/absolute/Root.emlf", "/absolute/request.json"],
  "cases": [{
    "name": "independent-polymorphic-use",
    "request": "/absolute/request.json",
    "accepted": true,
    "reused": true,
    "execute": ["interpreter", "native"],
    "interpreter": {"exit_code": 0, "stdout_hex": "370a", "stderr_hex": ""},
    "native": {"exit_code": 0, "stdout_hex": "370a", "stderr_hex": ""}
  }]
}
```

The example illustrates the schema only; it is not a completed test. Native
cases additionally require explicit `--clang`, `--runtime-object`, `--gc-prefix`,
and `--gmp-prefix` and run at both `-O0` and `-O2`. Acceptance and reuse/fallback
must match independent booleans. Executed cases must match literal exit status,
stdout, and stderr oracles. Call-stack oracles retain package, module, lexical
filename, line/column positions, and order exactly. Negative cases can also pin
an exact `error` object containing `phase` and `diagnostic`.

To split CPU lanes, pass `--engines inspect interpreter` for all acceptance,
reuse, structural type/layout and interpreter controls; later pass `--engines
inspect native` into a fresh result directory for the native phase. All cases
are inspected in both phases. Receipts list selected and skipped execution
engines, and `all_declared_executions_completed` remains false when an execution
engine was omitted. A phase-complete receipt therefore makes no claim about
the skipped phase. With no `--engines` filter, both engines run.

For a frozen qualification, invoke the materializer and qualifier copied under
`NEW_JOB/sources/tools/experimental/prepared-libraries/`, and pass that copy's
`fixtures/controls.json`. This keeps the control literals and readers immutable
when subsequent source work changes their checked-in versions.

Performance qualification must measure a fresh complete process, including
registry materialization, source admission, artifact/context checking and final
target checking. Report those fixed-library costs separately from the avoided
library inference work, and retain the full source-to-LLVM, fresh native object
and link boundary for the ordinary CLI comparison. The probe's extra structural
reports and diagnostic command durations are not CLI performance evidence.

## Recorded finite qualification

The frozen `prepared-library-fixture-3` job completed generator, probe and loader
builds. Its loader controls cover order, cycles, diamonds, exact lookup errors,
suffix ambiguity and retained source evidence. The
`prepared-library-fixture-results-3/receipt.json` receipt under `.mlf-build`
records all 33 cases and 366 commands passing, including 50 interpreter and
100 native O0/O2 executions. All declared execution engines completed and
input hashes still matched afterward. The five rejected programs and the
accepted reuse/fallback routes retain explicit independent oracles.

This finite result includes exact managed call-stack provenance, changed
builtin implementation under unchanged schema, hidden helpers/classes,
defining-module instance visibility, contracts, ordered datatype layouts and
source/dependency/path admission boundaries. The same job's
`regeneration/receipt.json` records a fresh producer and empty query cache,
four successful commands and exact equality for all five generated
registry/artifact outputs. Its immutable first-output backup and input pins
also verified. This establishes same-path-profile reproducibility only.

These results do not qualify a populated production foundation registry, a
native-host compiler, a different installation path or performance targets.
The earlier two failed fixture receipts
remain preserved; their mistakes were independent oracle errors, not relaxed
acceptance or error-order comparisons.

## Next step: portable build preparation (design only)

There is currently no public install/preparation wrapper. The experimental job
freezes the producer's required inputs, not the complete canonical project
needed by every ordinary GHC/native build gate. The normal committed compiler
continues to use the empty registry and correct ordinary fallback.

A future integration should freeze the complete canonical checkout inventory,
including dirty source bytes, untracked source files, every package manifest,
lock, wrapper, runtime input and build tool. Record executable modes and reject
unsupported symlinks, source escapes or an output tree recursively included in
its own inventory. Before any compiler executes, verify exact tree membership
and bytes. Generate from an explicit dependency-closed library manifest, module
roots and exact target lexical library root. The latter must not be normalized
or substituted into arbitrary target string literals.

Inside that owned tree, the sole already-registered
`bootstrap/MLF/PreparedLibraryData.hs` may receive the independently regenerated
literal. Every other implementation/configuration file must remain unchanged.
The producer must not import this generated module. Only then should the
ordinary `tools/shared/build.py` and native package manager consume that same
canonical tree, with their normal module-resolution and provenance audits.
There must be no extra include directory that shadows a module and no mutation
of the user's live checkout. A different installation path regenerates its
ordinary provenance profile; a populated literal made for this checkout alone
does not establish portable performance.

Native `mlfpkg lock` is a separate phase: `Package.Command` writes the actual
package's `mlf.lock`, so copied locks become stale after generated Data changes.
Record these declared manager-generated metadata updates, then run the real
`--offline --locked plan`; do not hand-edit a lock or claim the earlier complete
tree remained byte-identical through this phase. All implementation and package
manifest bytes must still match the prepared tree. No package cache migration
or runtime raw-registry loader is needed for this design.

The future receipt verifier must require the complete generation/regeneration
evidence inventory, compare original and prepared file maps independently with
only the canonical Data exception, and cross-check all product hashes. Any
final authentication failure must invalidate completion. A caller-pinned receipt
alone does not make an incomplete evidence map valid. Independent review found
these obligations in an unfinished wrapper; that unqualified wrapper was removed
before this checkpoint. Implementation, two-path portability controls and actual
foundation performance qualification remain work for the next round.

The finite matrix covers the following requirements; each must actually pass
before qualification is complete:

- Actual dependency-closed reuse and independent polymorphic uses; positive
  cases require `reused: true`.
- Source-byte, lexical-path, Prelude-mode, and dependency-implementation changes
  in owned frozen fixtures; these require the prescribed ordinary fallback.
- Private export/name rejection before admission; unused invalid user bindings
  and instances; genuine module and class support-name collision fallback.
- Imported higher-rank/bounded-forall contracts, dictionary-only dependencies,
  private helpers used by instances, defining-module instance visibility, and
  classes whose ordinary and prepared dictionary names differ.
- Ordered source/user datatypes and constructors, including nested and
  quantified field types; exact native library/user call stacks.
- Invalid source-digest shape, stale schema and same-version stale builtin
  witness rejection through separate registry admission controls; exact object
  digests are rechecked by the generation/materialization tools, while coherent generated-literal edits are
  detected by regenerate-and-compare, not by SHA-format checking.

`LoaderControls.hs` supplies independent expected traversal order and exact
errors for multiple dependencies, root-last ordering, diamonds, cycles, missing
first dependency, wrong module identity, forbidden imported expressions, path
precedence, mixed `.hs`/`.emlf` ambiguity, and parser-buffer evidence. Run it only
with a fresh owned directory containing empty `first` and `second`
subdirectories. It intentionally does not compare two wrappers over the same
implementation and call that an independent oracle.

The scripts record immutable input checks and command evidence. Command elapsed
times are diagnostic only. These finite controls are not a full-language proof,
a native-host compiler qualification, or a benchmark performance result.
