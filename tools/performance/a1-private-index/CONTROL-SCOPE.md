# A1 finite independent controls (experimental, not accepted)

`run_controls.py` preserves the independently frozen session, admission, parsed-file
and sealed-entry controls. A pass is finite correctness evidence only: it is not a
semantic proof, a performance result, or acceptance of A1. P3 remains the accepted
optimization. The runner is A1-only; it cannot qualify a P3 producer lacking the
registered private owner and index store.

## Run locally

Use the same Python interpreter that created the official build receipt. Python
3.10+ and a complete ordinary **GHC 9.14.1 / O2** maintained producer for this exact
123-module A1 source are required. The directory containing `receipt.json`, `bin/`
and `objects/` is the producer. The builtin prefix must already have its `.mlfci`
and `.mlfco` files; normal dependency preparation creates these through the public
crate path. There is no `--export-builtin-prelude` CLI.

```sh
python3 -B tools/performance/a1-private-index/run_controls.py \
  --source-root "$PWD" \
  --producer /absolute/path/to/complete-a1-producer \
  --builtin-prefix /absolute/path/to/shared/dependencies/builtin \
  --output /absolute/path/to/new-controls-output
```

Choose a fresh output directory for every attempt. Keep unsuccessful receipts and
logs rather than overwriting or relabeling them. Run serially, outside timing
windows, with the orchestration/resource boundary appropriate to the local host.
The runner contains no Linux `/proc`, fixed compiler path, or Linux object-hash
assumption. It uses actual authenticated producer argv, flags and local objects.
This is not a claim that the maintained official producer's own toolchain/dependency
collector is qualified on macOS: that prerequisite must authenticate unchanged,
or the runner fails closed. Do not bypass it; use the supported local Linux
VM/container workflow if the official collector does not support the host.

## Preserved inventory and assertions

* **6 session groups / 28 finite traces:** literal `SessionTests`, `SessionOracle`,
  `SessionGraftFixtures`, `SessionFieldFixtures` and six `Frozen*` modules retain
  their bytes and handwritten assertions. Full graph/state comparisons, bucket
  topology and balance, error/fallback epochs, old-parent rewrites, detached final
  solver witnesses and the unchanged public route remain covered.
* **22 admission cases:** 8 positive topology/alias/scope/paging/identity cases,
  8 exact rejections and first-error ordering cases, 3 finite counter-demand probes,
  and 3 test-only local ordering probes. The actual private
  `prepareGraph -> openPreparedSession -> freezeSession` route is compared against
  literal frozen preparation and independent hand expectations. Sparse and huge
  IDs, duplicate edges, nested scopes, aliases and children-before-binder are
  retained. Partial local probes are not a claim of arbitrary-bottom equivalence
  or reachability through the sealed production entry.
* **9 parsed-file cases:** literal `file-cases.json`, `materialize_file_cases.py`
  and `FileMain.hs`. Each side begins with its own empty query cache; successful
  cases require positive fresh inference and zero reuse. Old/public and
  new/sealed entries use the **same local sources and builtin prefix**. Complete
  diagnostics and `.mlfci`, `.mlfco`, `.queries` bytes must agree exactly, with no
  path, diagnostic, identifier or artifact normalization. Successful artifacts
  are independently disk-loaded/linked, checked against handwritten types,
  checked again, parsed after pretty-printing, rechecked and compared after erasure.
  Rejections keep literal fragments/exact errors and must not leave checked artifacts.
* **4 interface negatives:** `OpenSession`, `SolvePrepared`, `SessionConstructor`,
  `RawSolverRebind`. Each must fail with exit 1, its intended fragment(s), exactly
  one error and the right source filename. Missing imports, parse failures,
  panics and unrelated internal errors never count as privacy evidence.

Exact stdout is checked for each driver. Final stdout is:

```text
PASS A1 controls: 6 groups, 28 traces, 22 admission, 9 files, 4 seal negatives; no speed claim
```

## Provenance and isolation

The runner pins the literal control files and all 123 shared source hashes. It
calls the maintained `tools/shared/test_direct.py:authenticate_build` before and
after execution, requiring the complete official O2 producer, inferred-interface
inventory, source/configuration/toolchain/dependency/output identities and builtin
verification evidence. It also compares every producer Haskell object against the
receipt's exact object inventory, copies the objects byte-for-byte, and rejects
unexpected recompilation: GHC's fresh module-resolution rows must be exactly the
prescribed test modules and local wrapper. Production object bytes remain immutable.

The sole production export remains `compileSpecFile`. A fresh output-only
`SessionUnderTest.hs` changes only the module/export header. An exact byte inverse
against the registered owner is required and recorded; production files are never
edited. Host test drivers/oracles keep their existing `OPTIONS_GHC -O0`; production
modules, frozen literal algorithm modules and the header-only owner copy retain
the original O2 link flags. No general export or raw production entry is introduced.

The two C objects come from the producer's exact successful C compile/link commands
and authenticated source/toolchain paths, not platform-specific hash constants.
Their actual local hashes and byte-identical copies are pinned before/after. The
maintained producer schema does **not** store historical C-output digests; this
runner records a current snapshot tied to those commands, not an invented digest
at build time. Haskell object digests do come from the original producer receipt.

The supplied builtin pair must match the frozen, path-independent checked artifact
hashes (`e7e79d5a...703f099b` interface; `3d0e2142...f1f5c2d799` object), and those exact
files remain pinned throughout. This is an explicit historical-byte identity
contract, not a claim that this runner rebuilt or independently requalified all
six dependency providers. The outer preparation workflow owns that separate
seven-object validation and invalid-object rejection. All comparisons within
these controls use the caller's one common local builtin prefix.

`controls/oracle-provenance.json` is source-only public provenance: original private
execution paths are omitted, while the original record digest and literal source
hashes remain. No semantic oracle is regenerated from candidate output. Full raw
execution receipts remain private and are not installation prerequisites.
The control constants were not inferred from candidate output. The runner writes
fresh command logs, hashes, copy evidence and an initially incomplete `receipt.json`;
only after every assertion and post-authentication does it set `complete` and
`all_controls_passed`. It records `qualified=false`, `goal_evidence=false` and
`experimental_not_accepted=true` deliberately. No benchmark, native bootstrap,
macOS remote action, full campaign or algorithm change is performed here.
