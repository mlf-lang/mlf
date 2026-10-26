# Compiler optimization checkpoint (2026-10-26)

## Scope and default behavior

This series preserves the ordinary frontend's whole-Prelude normalization
(`Standalone.normalize = normalizeWithScope True`). The separately tested
`normalizeWithScope False` intervention is **not** selected here.

The production changes are:

- LLVM argument, result, and lazy-producer analyses and lowering, including
  their integration in Build/Codegen/Optimize. These are generic compiler
  transformations, not benchmark source or regex algorithm substitutions.
- Updated codegen cache identity
  `MLF-CODEGEN-CRATE-INPUT-COMPACT-4-RESULT-SUM-1-LAZY-PRODUCER-1`, with the
  corresponding `Tests.CrateCodegen` expectation and module/lock inventories.
- GHC-host ASCII string indexing and slicing. Equal UTF-8 byte and Unicode
  scalar counts identify ASCII. Bounds are checked before byte indexing;
  non-ASCII input retains the character-array path. ASCII slices are copied,
  so a small slice does not retain a large parent buffer.

The host implementation uses Text internals and was exercised with Text 2.1.3
and GHC 9.14.1. The existing Cabal bounds specify Text >= 2.1.3 and < 2.2;
these observations are not evidence that every future version in that range
has been tested. Native-runtime string representation is not changed by this
host-only patch.

## Optional installed Prelude experiment

The isolated tool under `tools/experimental/installed-prelude` is an explicit
opt-in experiment, not a replacement default CLI or package dependency.
Follow its README for its supported build, installation and invocation route.
Do not call its pure restoration API as a substitute for authenticating the
external descriptor and the exact metadata/object bytes.

Its intended contract preserves full installed class/instance inventories,
whole-user-root inference, fresh checked linking, and final independent target
checking. Actual imported-root compilation and the final grafted checked term
are distinct values: no synthetic presolution or general source-principal
certificate is produced. Named multi-module programs are not qualified by the
standalone experiment.

## Validation evidence and limits

The development checkpoint had fresh authenticated producer builds, the
31-module cold prerequisite gate and six locked-plan checks. Native A-to-B
bootstrap did **not** complete: the native stage-B worker failed. These source
optimizations must not be described as a completed native fixed point.

The installed whole-root experiment separately passed:

- 12 fixed semantic cases, including five exact negative diagnostic pairings;
- seven runtime fixtures at O0 and O2 on both baseline and opt-in paths;
- UTF-8/non-BMP output and n-body N=1000 output controls;
- four prelaunch descriptor/compiler/ABI/object admission negatives;
- one exact protected-binding collision with explicit `OriginalFallback` and
  the reason `canonical installed identifier collision`.

The private datatype `MLFCallStack` test instead follows the existing
`StandaloneType0` rename and uses the installed-root route. An earlier test
incorrectly expected fallback; its failed result was retained and a separately
reviewed full cohort used the corrected, stricter route expectation.

These finite controls are not a proof of principal-type equivalence for all
source programs. Admission failure, explicit fallback and successful installed
reuse must remain separate outcomes. New packaging/source identities require
new qualification; historical scratch-path receipts cannot authenticate a new
checkout. Performance observations must retain host, workload, install-cost,
cache and output-artifact boundaries; they do not establish the full historical
main-versus-branch gap or the requested final runtime target.

## Reproduction entry points

Use a fresh output directory and the repository's supported GHC/C toolchain:

```sh
python3 tools/shared/build.py --ghc "$GHC" --cc "$CC" \
  --optimization 2 --build-dir "$OUT/producer"
python3 tools/shared/test_direct.py --bin-dir "$OUT/producer/bin" \
  --build-receipt "$OUT/producer/receipt.json" --cc "$CC" --output "$OUT/direct"
```

The development-only argument/result/lazy-producer analysis units and deep
native diagnostics are not all packaged by these commands; their historical
scratch receipts are not portable replay gates.

These existing commands are reproduction entry points, not a claim that the
new publication tree has already run them. Existing focused lazy-IO semantic
controls live in `tools/shared/test_io_action_sharing.py`; native coverage
requires its documented GC/toolchain arguments. Exact installed-experiment
controls and their own receipts belong to that tool's separate workflow.

Keep generated binaries, checked snapshots, query caches, local toolchain
copies and absolute-path development receipts out of the source package.
