# Prepared library source tooling

This directory prepares and qualifies a compiler-owned registry of fixed library
checked ASTs. It does not cache user roots, infer user SCCs separately, or reuse
native object code. The current files are a source-only implementation draft;
they must be typechecked and exercised after the parent grants a build lane and
freezes the library inputs. No completed generation or qualification is claimed.

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
the probe. The witness control preserves schema and primitive count while
changing a canonical builtin source witness, and must fall back. These options
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

Before qualification is complete, its manifest must cover all of:

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
- Corrupt source/object commitments and stale schema/ABI rejection through the
  separate registry admission controls; coherent generated-literal edits are
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
