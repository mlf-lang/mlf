#!/usr/bin/env bash
# Bridge a released manager to the current manifest schema through library crates.
# Compilation, dependency traversal and cache validation remain in the seed manager.
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
test "$#" -eq 1 || { echo 'Usage: bootstrap-manager.sh FRESH_BUILD_DIRECTORY' >&2; exit 2; }
build=$1
compiler=${MLF_COMPILER:?verified native seed compiler required}
manager=${MLF_PACKAGE_MANAGER:?verified native seed manager required}
clang=${CC:-${MLF_CLANG:-clang}}
test ! -e "$build" || { printf 'Use a fresh manager bootstrap directory: %s\n' "$build" >&2; exit 2; }
if [ -f "$root/shared-sources.json" ]; then
  # A released compiler cannot parse the current .hs inputs. Bootstrap both
  # tools through the frozen bridge, and publish the compiler with the manager.
  mkdir -p "$build/bin"
  build=$(cd -- "$build" && pwd)
  identity=$("$compiler" --implementation-identity 2>/dev/null) || identity=
  if [ "$identity" = 'MLF/shared-haskell-v1 native-MLF' ]; then
    # Portable LLVM candidates are already shared-aware. Reuse this verified
    # native toolchain rather than feeding it through the released-seed bridge.
    manager_identity=$("$manager" --implementation-identity 2>/dev/null) || manager_identity=
    if [ "$manager_identity" != 'MLF/shared-haskell-v1 native-MLF' ]; then
      printf '%s\n' 'Shared-aware native bootstrap requires a native-MLF manager as well as compiler. Rebuild the manager with scripts/bootstrap-package.sh using the qualified native compiler.' >&2
      exit 2
    fi
    "$manager" --manifest "$root/mlf-package.json" --compiler "$compiler" \
      --clang "$clang" --runtime "$root/runtime/mlf_runtime.c" --timeout 21600 \
      --build-dir "$build" build --target mlfpkg
    jq -e '.complete == true and .implementation == "MLF"' "$build/build-report.json" >/dev/null
    output_manager_identity=$("$build/bin/mlfpkg" --implementation-identity 2>/dev/null) || output_manager_identity=
    if [ "$output_manager_identity" != 'MLF/shared-haskell-v1 native-MLF' ]; then
      printf '%s\n' 'Produced manager does not identify as native-MLF.' >&2
      exit 2
    fi
    tools/release/ensure-build-runner.sh "$build/bin" "$clang"
    printf '%s\n' "$compiler" > "$build/compiler.path"
    jq -n --arg compiler "$compiler" \
      --arg report "$(shasum -a 256 "$build/build-report.json" | awk '{print $1}')" \
      '{complete:true,route:"shared-aware-native",compiler:$compiler,build_report_sha256:$report}' > "$build/bootstrap.json"
  else
    if [ "$identity" = 'MLF/shared-haskell-v1 GHC' ]; then
      printf '%s\n' 'Native release bootstrap requires a native MLF seed; use tools/shared/build.py for the separate GHC path.' >&2
      exit 2
    fi
    MLF_SHARED_BOOTSTRAP_DIR="$build/shared-bootstrap" CC="$clang" \
      "$root/scripts/bootstrap-shared.sh"
    cp "$build/shared-bootstrap/stage2" "$build/bin/emlf"
    native_manager=$(cat "$build/shared-bootstrap/manager.path")
    cp "$native_manager" "$build/bin/mlfpkg"
    cp "$(dirname -- "$native_manager")/mlf-build-runner" "$build/bin/mlf-build-runner"
    cp "$build/shared-bootstrap/native/build-report.json" "$build/build-report.json"
    cp "$build/shared-bootstrap/bootstrap.json" "$build/bootstrap.json"
    printf '%s\n' "$build/bin/emlf" > "$build/compiler.path"
  fi
  printf '%s\n' "$build/bin/mlfpkg" > "$build/manager.path"
  printf '%s\n' "$build/bin/mlfpkg"
  exit 0
fi
mkdir -p "$build/source"
build=$(cd -- "$build" && pwd)
cp mlf-package.json "$build/root-manifest.json"
# The released schema supports package dependencies, but not a target-specific
# dependencies field. Materialize precisely that target's direct source libraries.
jq -e --arg root "$root" '
  .executables.mlfpkg as $target |
  ($target.dependencies // (.dependencies | keys)) as $names |
  {format:1,name:"mlf-bootstrap-manager",version:.version,
   dependencies:(.dependencies | with_entries(select(.key as $name | $names | index($name))) |
     with_entries(.value |= if (keys == ["path"] and (.path | type == "string"))
       then {path:($root + "/" + .path)} else error("bootstrap requires local source dependencies") end)),
   executables:{mlfpkg:($target | del(.dependencies))}}
' "$build/root-manifest.json" > "$build/source/mlf-package.json"
while IFS= read -r source; do
  mkdir -p -- "$build/source/$(dirname -- "$source")"
  cp -- "$root/$source" "$build/source/$source"
done < <(jq -r '.executables.mlfpkg | .main, ((.modules // {})[])' "$build/root-manifest.json")
printf '%s\n' 'Building the current manager from library crates with the verified seed manager.'
"$manager" --manifest "$build/source/mlf-package.json" --compiler "$compiler" \
  --clang "$clang" --runtime "$root/runtime/mlf_runtime.c" \
  --timeout "${MLF_BOOTSTRAP_ACTION_TIMEOUT:-1800}" --build-dir "$build" build --target mlfpkg
jq -e '.complete == true and .implementation == "MLF"' "$build/build-report.json" >/dev/null
cmp mlf-package.json "$build/root-manifest.json"
while IFS= read -r source; do cmp "$root/$source" "$build/source/$source"; done \
  < <(jq -r '.executables.mlfpkg | .main, ((.modules // {})[])' "$build/root-manifest.json")
tools/release/ensure-build-runner.sh "$build/bin" "$clang"
test -x "$build/bin/mlfpkg"
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi | awk '{print $1}'; }
jq -n --arg seed_manager "$(sha256 "$manager")" --arg compiler "$(sha256 "$compiler")" \
  --arg manager "$(sha256 "$build/bin/mlfpkg")" --arg helper "$(sha256 "$build/bin/mlf-build-runner")" \
  --arg report "$(sha256 "$build/build-report.json")" \
  '{complete:true,seed_manager_sha256:$seed_manager,compiler_sha256:$compiler,
    manager_sha256:$manager,build_runner_sha256:$helper,build_runner_protocol:1,
    build_report_sha256:$report}' > "$build/bootstrap.json"
printf '%s\n' "$build/bin/mlfpkg"
printf '%s\n' "$compiler" > "$build/compiler.path"
