# Experimental installed Prelude, whole-root inference

This is an **opt-in GHC-host experiment**, not a replacement for the standard
compiler or its Prelude policy. The normal CLI and `normalize=True` remain
unchanged. The overlay adds a factored standalone rewrite, authenticated
installed full-builtin metadata/checked code, and one whole-user-root inference
and checked graft. It does not use per-SCC query persistence, prune instances,
skip checking, change the source algorithm, or cache the user's program.

The implementation is intentionally outside the normal package manifests.
`InstalledPreludeWholeRoot` depends on the crate/compiler layers and cannot be
added to the frontend package without a dependency cycle. The experimental build
uses overlay-first source paths and fresh objects. `StandaloneReference` is a
test-only old normalizer; the builder verifies that only its module header differs
from the ordinary source.

## Build and explicitly install

Linux, Python 3.11+, and the repository's supported GHC 9.14.1 toolchain are
required. Use your own paths below. No toolchain download or global install is
performed. First build the **ordinary compiler from this exact checkout** using
its existing `tools/shared/build.py --optimization 2 --ghc ... --cc ...
--build-dir ...` procedure. The experiment reuses that receipt's authenticated
toolchain identities, not its object files.

```sh
ROOT=/path/to/checkout
EXP="$ROOT/tools/experimental/installed-prelude"
PRODUCER=/path/to/fresh-official-producer
BUILD=/path/to/fresh-experimental-build
PRODUCER_SHA=$(sha256sum "$PRODUCER/receipt.json" | cut -d' ' -f1)
python3 "$EXP/build.py" --root "$ROOT" --producer "$PRODUCER" \
  --producer-receipt-sha256 "$PRODUCER_SHA" --output "$BUILD"
BUILD_SHA=$(sha256sum "$BUILD/receipt.json" | cut -d' ' -f1)
python3 "$EXP/snapshot.py" install --build-receipt "$BUILD/receipt.json" \
  --build-receipt-sha256 "$BUILD_SHA" --output /path/to/fresh-install
```

Keep the printed descriptor SHA **outside the artifact bundle**. The expected
SHA is a local trust anchor supplied by the operator, not a claim made by the
artifact. An untrusted artifact plus its own matching hash is not authentication.
Installation setup is separate from application compilation. Each consume reads
and checks the descriptor and both artifact byte streams, then passes precisely
those same verified bytes to the strict UTF-8/scalar-framing decoder.

```sh
python3 "$EXP/snapshot.py" consume-check \
  --build-receipt "$BUILD/receipt.json" --build-receipt-sha256 "$BUILD_SHA" \
  --manifest /path/to/fresh-install/result/descriptor.json \
  --manifest-sha256 EXTERNALLY_RETAINED_SHA \
  --source program.emlf --output /path/to/fresh-check
```

Inputs must be original unnamed standalone source, not a fabricated module.
`--mode no-prelude` is explicit. `consume-check` preserves `InstalledRoot` versus
`OriginalFallback` in `result/route.txt`; a successful fallback is **not** evidence
of installed reuse. `consume-llvm` additionally writes checked proof files and
LLVM. `emit-installed-llvm` writes only LLVM to `program.ll` and rejects fallback
as an **experimental installed-only admission rule**, not a change to the core's
fallback semantics. It does not skip inference/checking. The inherited watchdog
merges child stdout/stderr into `process/build.log`; a successful LLVM result is
that child log, not the watchdog's own JSON stdout.

All standard handles and output files in the host harness explicitly use UTF-8;
no locale-dependent interpretation of source or artifact strings is intended.
Build and operation receipts record actual commands, environment, source/tool
identities and failure status. Each command uses the existing watchdog with
6 GiB address-space / 3 GiB process-tree RSS limits, 2 GiB disk floor and bounded
wall time (C 60 s, GHC/install 300 s, consume 180 s). Its 256 MiB output-growth
limit covers the monitored process-log directory, **not all object/result files**.
Tool authentication/source inventory happens outside those command caps. A
`CLEANUP_UNCERTAIN` marker requires manual descendant verification before reuse.

## Reproducible tests / final-tree gate

```sh
python3 -m unittest discover -s "$EXP/tests" -p 'test_*.py'
python3 "$EXP/tests/qualify.py" --build-receipt "$BUILD/receipt.json" \
  --build-receipt-sha256 "$BUILD_SHA" --output /path/to/fresh-smoke
```

The pure tests use deliberately synthetic metadata to test framing/authentication,
not source acceptance. The small smoke performs a fresh install, factor/reference
checks (both normalization modes), ordinary versus installed checks for Hello and
Unicode, and an explicit collision fallback. It checks routes and target types;
this is **not principal-scheme or full behavioral equivalence**.

Before treating a newly packaged tree as qualified, also execute the fixed native
gate on that exact tree/toolchain: Hello and Unicode at O0/O2 must output `x\n`
and UTF-8 `é😀\n` respectively, with status zero and empty stderr. Compile the
unchanged existing n-body adapter at O2 and check N=1000 with its existing independent
oracle and raw LLVM comparison. Use the same pinned runtime/clang inputs for both
routes, fresh directories and ordinary baseline CLI. Record new final-tree
receipts; earlier scratch build/install receipts are not proof of this build.
The broader research corpus is supporting history, not automatically a final-tree
pass. Do not run benchmarks while another fixed timing cohort owns the CPU.

## Limits and publication claims

No default switch, automatic installation, globally trusted artifact registry,
general module consumer, principal-type equality proof, or compile/runtime target
claim is made here. Root display types are not a nominal-identity equivalence
proof. Constructor numbering may differ when installed declarations precede user
data; no generic IR/tag normalization is implemented in this package. Performance
must include required artifact authentication/load/check/inference/LLVM costs,
with installation and host-producer setup reported separately. Keep generated
receipts, snapshots, binaries and toolchains outside the source tree and out of
version control.
