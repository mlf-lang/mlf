# 00. Fixed declaration migration baseline

The compiler and package manager come from a fresh public GHC `-O2` installation of commit `726cd256aa90d3e8cf596842fbb29515c1bc5249`. The capture program reads the independent v1 reader from that checkout. The Foundation input consists of the 14 `Bootstrap/*.hs` blobs at `c5928b5be73cd78d194405e734aa012415570e1a`.

From the migration worktree, choose new absolute paths for `BASE_TREE`, `INSTALL` and `OUT`. Create the installation and capture the three Foundation states as follows.

```sh
CAPTURE="$PWD/tools/performance/declid-migration/capture-baseline.py"
git worktree add --detach "$BASE_TREE" 726cd256aa90d3e8cf596842fbb29515c1bc5249
mkdir -p "$OUT"
(cd "$BASE_TREE" && python3 -B tools/shared/build.py --build-dir "$INSTALL")
python3 -B "$CAPTURE" "$BASE_TREE" "$INSTALL" "$OUT/foundation"
```

`foundation/summary.json` records the actual programs, installation receipt hash, locked package plan, corpus hashes, products, graph accounting and receipt reconstruction. Each state retains `unit.mlfci`, `unit.mlfco`, `unit.queries`, `generation.mlfqg` and `rows.json`. The rows include every full stable key, result digest, ordered read key and version, and optional payload location. The Foundation spec and stored crate interfaces contain absolute paths. For byte comparisons between compilers, use the same spec paths. Executable hashes also identify a particular installed prefix.

Run the compiler-crate build from a fresh cache in the fixed source checkout. Use the native toolchain selected for both arms of the comparison.

```sh
cd "$BASE_TREE"
source tools/release/native-environment.sh
bash tools/release/ensure-build-runner.sh "$OUT/runner" "$(command -v clang)"
export MLF_BUILD_RUNNER="$OUT/runner/mlf-build-runner"
"$INSTALL/bin/mlfpkg" --offline --manifest libraries/mlf-crates/mlf-package.json \
  --build-dir "$OUT/mlf-crates-build" --cache-dir "$OUT/mlf-crates-cache" \
  --compiler "$INSTALL/bin/emlf" --runtime "$PWD/runtime/mlf_runtime.c" \
  --jobs 1 --timeout 21600 build > "$OUT/mlf-crates.log" 2>&1
```

## Fixed-run products

On macOS 26.6.2 arm64, `emlf --implementation-identity` reported `MLF/shared-haskell-v1 GHC`. The receipt identifies GHC 9.14.1. `mlfpkg --offline --locked plan` succeeded. `foundation.json` binds the receipt, binaries, products and independently decoded row sets to their SHA-256 values. `products.tar.xz` contains the original installation receipt, spec, locked plan and all three states' products, wire indexes and decoded rows. The archive SHA-256 is `94887387cbfb077a6103800a1085a7d85256592d6d4958bc064caaa366278a9d`.

| State | Inferred | Reused | Logical rows | Ordered reads | Cold generation retained |
| --- | ---: | ---: | ---: | ---: | --- |
| Cold | 504 | 0 | 3,403 | 19,277 | Initial publication |
| Warm | 0 | 504 | 3,403 | 19,277 | Yes |
| Version edit | 1 | 503 | 3,403 | 19,277 | New generation |

The independent reader validated content addresses, edge versions and acyclicity. For each state it reconstructed 504 final receipts from the emitted object and checked predecessor versions. Of those, 496 retained the raw address and eight had a distinct final content digest. These capture runs overlapped other compiler work. The wall-clock and resource samples in `foundation.json` describe the evidence capture only.

## Compiler-crate self-build

The single-job package manager built all six dependencies from the empty cache. The `mlf-crates` job inferred **1,715** groups, emitted its interface, object and query report, and exited 1 with `binary expanded-work limit exceeded` before publishing the target's `CURRENT`. `self-build.json` records the actual compile command, toolchain and runner, dependency keys, emitted file hashes, diagnostic, and build-report and log hashes. This reproduces the v1 publication boundary that step 17 must overcome with the existing work limit.
