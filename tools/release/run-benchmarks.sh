#!/usr/bin/env bash
# Complete measured C / baseline / candidate comparison. Never reuse test
# verdicts or benchmark outputs, and never convert a failed limit into success.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
test "$(uname -s):$(uname -m)" = Darwin:arm64
. tools/release/native-environment.sh
tools/release/shared-candidate.sh verify
tools/release/check-benchmark-provenance.sh
output=$PWD/.mlf-build/benchmark-game
test ! -e "$output"
mkdir -p "$output/timing/commands"
printf '{"complete":false,"status":"preparing"}\n' > "$output/gate.json"
finish() {
  status=$?
  trap - EXIT
  if [ "$status" -ne 0 ]; then
    jq -n --argjson code "$status" '{complete:false,status:"failed",exit_code:$code}' > "$output/gate.json"
  fi
  exit "$status"
}
trap finish EXIT
candidate=$PWD/.mlf-build/bin/emlf
manager=$PWD/.mlf-build/bin/mlfpkg
# Fetching a comparison baseline must not overwrite the selected candidate in
# GITHUB_ENV. The published archive, source and both tools have source pins.
GITHUB_ENV= tools/release/fetch-seed.sh "$output/baseline" .github/benchmark-baseline-macos.env
source .github/benchmark-baseline-macos.env
baseline=$output/baseline/mlf-$MLF_SEED_VERSION-macos-arm64/libexec/emlf
llvm=$(brew --prefix llvm)
lld=$(brew --prefix lld)
clang=$llvm/bin/clang
test "$(pkg-config --modversion libpcre2-8)" = "$(jq -er '.workloads[] | select(.name == "regex-redux") | .pkg_config_versions["libpcre2-8"]' benchmarks/manifest.json)"
# Exercise compact-GC support before spending time on the benchmark driver.
"$baseline" --emit-llvm-gc examples/io-hello.emlf > "$output/baseline-smoke.ll"
test -s "$output/baseline-smoke.ll"
cp .mlf-build/shared-candidate/manifest.json "$output/candidate-manifest.json"
cp .github/benchmark-baseline-macos.env "$output/baseline.env"
cp .github/macos-dependencies.env "$output/toolchain.env"
cp benchmarks/manifest.json "$output/workloads.json"
sw_vers > "$output/os.txt"
uname -a >> "$output/os.txt"
sysctl -n hw.model hw.ncpu hw.memsize > "$output/hardware.txt"
"$clang" --version > "$output/clang.txt"
# Each helper is built by the final native manager and final native compiler.
# Both compiler variants use the same generic optimized LLVM/link transport;
# C always invokes real Clang with the unchanged manifest flags.
tools/release/time-command.sh "$output/timing" prepare \
  "$manager" --manifest tools/bench/mlf-package.json --compiler "$candidate" \
  --runtime "$PWD/runtime/mlf_runtime.c" --build-dir "$output/driver" \
  --timeout 21600 build --target bench --target build-backend --target build-linker
"$output/driver/bin/build-backend" "$clang" "$llvm" "$PWD/tools/bench/llvm-backend.c" "$output/llvm-backend"
"$output/driver/bin/build-linker" "$clang" "$llvm" "$lld" "$PWD/tools/bench/link-backend.cpp" "$output/linker-helper"
node tools/bench/configure-backend.cjs "$clang" "$llvm/bin/opt" "$lld/bin/ld64.lld" "$output/backend" \
  --single-process "$output/llvm-backend/mlf-llvm" --prestart-link "$output/linker-helper/mlf-link"
# No workload arguments: the native runner executes every pinned workload, all
# independent correctness sizes and the unchanged measured default inputs.
# Save failure status only to permit verification/evidence collection, then fail.
status=0
MLF_BENCH_MLF_CLANG="$output/backend/clang-mlf" MLF_BENCH_STREAM_LLVM=1 MLF_BENCH_STREAM_LINK=1 \
  tools/release/time-command.sh "$output/timing" measurements \
  "$output/driver/bin/bench" "$candidate" "$baseline" "$output/results" 7 "$clang" 3 2 \
  > "$output/benchmark.log" 2>&1 || status=$?
cat "$output/benchmark.log"
# Even a failed benchmark must not mutate any selected tool or source input.
tools/release/shared-candidate.sh verify
node tools/release/verify-benchmarks.mjs "$output/results/results.json" benchmarks/manifest.json \
  "$candidate" "$baseline" "$clang" "$output/backend" "$output/llvm-backend" "$output/linker-helper"
test "$status" -eq 0
jq -n --arg source "$(git rev-parse HEAD)" --arg run "${GITHUB_RUN_ID:-}" \
  '{complete:true,status:"passed",source:$source,run:$run,workloads:10,runs:7,limits:{compilation:3,runtime:2}}' > "$output/gate.json"
