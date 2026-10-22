#!/usr/bin/env bash
# Build only the checkout tools, then exercise their public CLI directly.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
build="$PWD/.mlf-build/pr-smoke"
mkdir -p "$build"
printf '{"complete":false}\n' > "$build/result.json"
test "$#" -eq 0
seed_compiler=${MLF_COMPILER:?verified native seed compiler required}
seed_manager=${MLF_PACKAGE_MANAGER:?verified native seed manager required}
started=$SECONDS
"$seed_manager" --compiler "$seed_compiler" --runtime "$PWD/runtime/mlf_runtime.c" \
  --timeout 1800 --locked --build-dir "$build/candidate" \
  build --target emlf --target mlfpkg 2>&1 | tee "$build/build.log"
jq -e '
  .complete == true and .implementation == "MLF" and
  ([.builds[] | select(.kind | startswith("executable mlf-compiler:")) | .kind] | sort) ==
    ["executable mlf-compiler:emlf","executable mlf-compiler:mlfpkg"]
' "$build/candidate/build-report.json" >/dev/null
build_seconds=$((SECONDS - started))
compiler="$build/candidate/bin/emlf"
manager="$build/candidate/bin/mlfpkg"
test -x "$compiler" && test -x "$manager"
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
compiler_sha256=$(sha256 "$compiler")
manager_sha256=$(sha256 "$manager")
# No extra compiler generation, test executable, or backend drivers are built.
tools/release/pr-smoke-cli.sh "$compiler" "$build/cli" 2>&1 | tee "$build/cli.log"
tools/release/pr-smoke-packages.sh "$compiler" "$manager" "$build/packages" 2>&1 | tee "$build/packages.log"
jq -e --arg compiler "$compiler_sha256" '
  .complete == true and .compiler_sha256 == $compiler and .cases == 8 and
  .accepted == 2 and .rejected == 2 and .runtime == 3 and .invalid_target == 1 and
  .backends == ["interpreter","llvm"]
' "$build/cli/result.json" >/dev/null
jq -e --arg compiler "$compiler_sha256" --arg manager "$manager_sha256" '
  .complete == true and .compiler_sha256 == $compiler and .manager_sha256 == $manager and
  .cases == 3 and .backends == ["interpreter","llvm"]
' "$build/packages/result.json" >/dev/null
test "$(sha256 "$compiler")" = "$compiler_sha256"
test "$(sha256 "$manager")" = "$manager_sha256"
jq -n --arg commit "$(git rev-parse HEAD)" --argjson build_seconds "$build_seconds" \
  --argjson total_seconds "$((SECONDS - started))" \
  --arg compiler_sha256 "$compiler_sha256" --arg manager_sha256 "$manager_sha256" \
  --arg build_report_sha256 "$(sha256 "$build/candidate/build-report.json")" \
  --arg cli_sha256 "$(sha256 "$build/cli/result.json")" \
  --arg packages_sha256 "$(sha256 "$build/packages/result.json")" \
  '{complete:true,commit:$commit,build_seconds:$build_seconds,total_seconds:$total_seconds,
    compiler_sha256:$compiler_sha256,manager_sha256:$manager_sha256,
    build_report_sha256:$build_report_sha256,cli_sha256:$cli_sha256,packages_sha256:$packages_sha256}' > "$build/result.json"
cat "$build/result.json"
