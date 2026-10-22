#!/usr/bin/env bash
# Build the checkout once, then exercise its compiler, manager and C runtime.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
test "$#" -eq 0
build="$PWD/.mlf-build/pr-smoke"
mkdir -p "$build"
# Clear the success receipt before any command can fail on a rerun.
printf '{"complete":false}\n' > "$build/result.json"
seed_compiler=${MLF_COMPILER:?verified native seed compiler required}
seed_manager=${MLF_PACKAGE_MANAGER:?verified native seed manager required}
started=$SECONDS
"$seed_manager" --compiler "$seed_compiler" --runtime "$PWD/runtime/mlf_runtime.c" \
  --timeout 1800 --locked --build-dir "$build/candidate" build 2>&1 | tee "$build/build.log"
jq -e '
  .complete == true and .implementation == "MLF" and
  ([.builds[] | select(.kind | startswith("executable mlf-compiler:")) | .kind] | sort) ==
    ["executable mlf-compiler:compiler-tests","executable mlf-compiler:emlf","executable mlf-compiler:mlfpkg"]
' "$build/candidate/build-report.json" >/dev/null
build_seconds=$((SECONDS - started))
export MLF_COMPILER="$build/candidate/bin/emlf"
export MLF_PACKAGE_MANAGER="$build/candidate/bin/mlfpkg"
runner="$build/candidate/bin/compiler-tests"
test -x "$MLF_COMPILER" && test -x "$MLF_PACKAGE_MANAGER" && test -x "$runner"
# Direct invocation avoids building another root generation just to run tests.
# The suite still compiles its tests and backend drivers with the new compiler.
"$runner" pr-smoke --manager "$MLF_PACKAGE_MANAGER" --compiler "$MLF_COMPILER" \
  --build-dir "$build/tests" --cache-dir "$build/candidate/cache" 2>&1 | tee "$build/tests.log"
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
compiler_sha256=$(sha256 "$MLF_COMPILER")
manager_sha256=$(sha256 "$MLF_PACKAGE_MANAGER")
runner_sha256=$(sha256 "$runner")
framework_sha256=$(sha256 "$build/tests/suite-build/bin/test-framework")
unions_sha256=$(sha256 "$build/tests/suite-build/bin/int-set-unions")
coverage_sha256=$(sha256 "$build/tests/test-framework.coverage.jsonl")
inventory_sha256=$(sha256 tests/golden/unit-inventory.json)
framework_log_sha256=$(sha256 "$build/tests/test-framework.log")
jq -e --arg compiler "$compiler_sha256" --arg manager "$manager_sha256" \
  --arg runner "$runner_sha256" --arg framework "$framework_sha256" \
  --arg unions "$unions_sha256" --arg coverage "$coverage_sha256" \
  --arg inventory "$inventory_sha256" --arg framework_log "$framework_log_sha256" '
  .complete == true and .implementation == "MLF" and .group == "pr-smoke" and
  .compiler_sha256 == $compiler and .manager_sha256 == $manager and
  .runner_sha256 == $runner and
  .sources["tests/golden/unit-inventory.json"] == $inventory and
  .focused_suite == {name:"int-set-unions",binary_sha256:$unions} and
  (.suites["test-framework"] | .binary_sha256 == $framework and
    .log_sha256 == $framework_log and .coverage_report_sha256 == $coverage and
    .coverage_inventory_sha256 == $inventory and
    .coverage_result == {schema_version:1,suite:"test-framework",executions:3,aliases:0,metrics:{}}) and
  (.matrices["compact-gc"] | .rows == 12 and .backend_names == ["interpreter","llvm"]) and
  (.package_smoke | .cases == 3 and .backends == ["interpreter","llvm"])
' "$build/tests/verification.json" >/dev/null
# Retain and validate the checked driver cache decisions for this campaign.
driver_report="$build/tests/driver-build/build-report.json"
driver_hash=$(sha256 "$driver_report")
# Builder.manager is the executing compiler-tests binary, not mlfpkg.
jq -se --arg group pr-smoke --arg driver_hash "$driver_hash" '
    def digest: type == "string" and test("^[0-9a-f]{64}$");
    .[0] as $v | .[1] as $b |
    $v.group == $group and $v.driver_build.sha256 == $driver_hash and
    ($v.driver_build.sha256 | digest) and
    ($v.compiler_sha256 | digest) and ($v.runner_sha256 | digest) and
    all([$v.compiler,$v.runner,$b.cache_directory][]; type == "string" and startswith("/")) and
    $b.format == 1 and $b.complete == true and $b.implementation == "MLF" and
    $b.toolchain.compiler.path == $v.compiler and
    $b.toolchain.compiler.sha256 == $v.compiler_sha256 and
    $b.toolchain.manager.path == $v.runner and
    $b.toolchain.manager.sha256 == $v.runner_sha256 and
    ($b.builds | type == "array" and length > 0) and
    ($v.drivers | keys) == (if $group == "port" then ["LLVMDriver"] else ["LLVMDriver","RuntimeDriver"] end) and
    all($v.drivers | to_entries[];
      .key as $name | .value as $driver |
      $driver.frontend == "source" and
      ($driver.sha256 | digest) and ($driver.llvm_sha256 | digest) and
      ($driver.artifacts | keys) ==
        (if $name == "RuntimeDriver" then ["linked","llvm","object","runtime","trace"] else ["linked","llvm","object","runtime"] end) and
      all($driver.artifacts | to_entries[];
        .key as $stage | .value as $receipt |
        ($receipt | keys) == ["artifact_sha256","cached","directory","files","key","kind"] and
        ($receipt.key | digest) and ($receipt.artifact_sha256 | digest) and
        ($receipt.cached | type == "boolean") and
        $receipt.directory == ($b.cache_directory + "/" + $receipt.key) and
        $receipt.kind ==
          (if $stage == "llvm" then "source " + $name + " LLVM" elif $stage == "object" then "LLVM object" elif $stage == "linked" then "test driver native link" else "test driver C object" end) and
        any($b.builds[]; . == ($receipt | {kind,key,cached})) and
        ($receipt.files | keys) ==
          [if $stage == "llvm" then "program.ll" elif $stage == "object" then "program.o" elif $stage == "linked" then "program" else "object.o" end] and
        all($receipt.files[]; digest)) and
      $driver.artifacts.llvm.files["program.ll"] == $driver.llvm_sha256 and
      $driver.artifacts.linked.files.program == $driver.sha256)
' "$build/tests/verification.json" "$driver_report" >/dev/null
# Changing expected stdout also changes the executable key. Require misses for
# the dependency and downstream crates, whose keys do not contain test stdout.
jq -e '
  [.builds[] | select(.kind == "crate message/0.1.0/library" or
    .kind == "crate greeting/0.1.0/library" or
    .kind == "crate local-packages-example/0.1.0/target-test-hello")] as $rows |
  ($rows | map(.kind) | sort) == ["crate greeting/0.1.0/library",
    "crate local-packages-example/0.1.0/target-test-hello", "crate message/0.1.0/library"]
  and all($rows[]; .cached == false)
' "$build/tests/package-smoke/build/build-report.json" >/dev/null
jq -n --arg commit "$(git rev-parse HEAD)" --argjson build_seconds "$build_seconds" \
  --argjson total_seconds "$((SECONDS - started))" \
  --arg compiler_sha256 "$compiler_sha256" --arg manager_sha256 "$manager_sha256" \
  --arg runner_sha256 "$runner_sha256" --arg framework_sha256 "$framework_sha256" \
  --arg coverage_sha256 "$coverage_sha256" --arg inventory_sha256 "$inventory_sha256" \
  --arg verification_sha256 "$(sha256 "$build/tests/verification.json")" \
  --arg driver_build_sha256 "$driver_hash" \
  '{complete:true,commit:$commit,build_seconds:$build_seconds,total_seconds:$total_seconds,
    compiler_sha256:$compiler_sha256,manager_sha256:$manager_sha256,runner_sha256:$runner_sha256,
    framework_sha256:$framework_sha256,coverage_sha256:$coverage_sha256,
    inventory_sha256:$inventory_sha256,verification_sha256:$verification_sha256,
    driver_build_sha256:$driver_build_sha256}' > "$build/result.json"
cat "$build/result.json"
