#!/usr/bin/env bash
# Fail before a native build if a benchmark pin or source adaptation is broken.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
if [ "${1:-}" = --framework-list ]; then
  exec python3 -B tools/release/benchmark_provenance_cases.py --framework-list
fi
manifest=benchmarks/manifest.json
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
framework=false
work=
if [ "${MLF_TEST_SUITE:-}" = benchmark-provenance ]; then
  framework=true
  . tools/testing/native-events.sh
  python3 -B tools/release/benchmark_provenance_cases.py
fi
selected() {
  if "$framework"; then mlf_case_selected "benchmark-provenance/$1"; else return 0; fi
}
start() {
  if "$framework"; then mlf_case_start "benchmark-provenance/$1"; fi
}
pass() {
  if "$framework"; then mlf_case_result pass 0; fi
}
finish() {
  local status=$?
  trap - EXIT
  if "$framework"; then mlf_case_cleanup "$status"; fi
  if [ -n "$work" ]; then rm -rf -- "$work"; fi
  exit "$status"
}
check() {
  local name=$1
  shift
  if selected "$name"; then
    start "$name"
    "$@"
    pass
  fi
}
trap finish EXIT

if selected manifest; then
  start manifest
  jq -e '
  .pinned_sha256 as $pins |
  ($pins | type == "object" and length > 0) and
  all($pins | to_entries[]; (.key | type == "string") and (.value | test("^[0-9a-f]{64}$"))) and
  all(.workloads[].provenance[];
    (.original_source | type == "string" and length > 0) and
    (.build_source | type == "string" and length > 0) and
    ($pins[.original_source] != null) and ($pins[.build_source] != null) and
    (.original_source == .build_source or
      ($pins[(.build_source | split("/") | .[:-1] | join("/")) + "/adaptation.patch"] != null)))
  ' "$manifest" >/dev/null
  pass
fi

mkdir -p .mlf-build
temporary=$(mktemp -d "$PWD/.mlf-build/benchmark-provenance.XXXXXX")
case "$temporary" in "$PWD"/.mlf-build/benchmark-provenance.*) work=$temporary ;; *) exit 1 ;; esac
if selected pinned-inputs; then
  start pinned-inputs
  jq -r '.pinned_sha256 | to_entries[] | "\(.value)  \(.key)"' "$manifest" > "$work/SHA256SUMS"
  sha256 -c "$work/SHA256SUMS" >/dev/null
  pass
fi
check transition python3 -B tools/release/check_benchmark_transition.py
check transition-controls python3 -B tools/testing/run.py benchmark-transition-controls
# Authenticate current reconciliation bytes separately from unchanged historical
# suites. Sequential physical replays preserve each original source contract.
check reconciliation/ordinary python3 -B tools/testing/run.py benchmark-reconciliation
check reconciliation/optimized python3 -B tools/testing/run.py benchmark-reconciliation --python-optimization
check predecessor/declid python3 -B tools/testing/run.py benchmark-predecessor-declid
check predecessor/declid-optimized python3 -B tools/testing/run.py benchmark-predecessor-declid --python-optimization
check predecessor/main python3 -B tools/testing/run.py benchmark-predecessor-main
check predecessor/main-optimized python3 -B tools/testing/run.py benchmark-predecessor-main --python-optimization
jq -r '.workloads[].provenance[] | select(.original_source != .build_source) | [.original_source,.build_source] | @tsv' "$manifest" > "$work/adaptations.tsv"

count=0
while IFS=$'\t' read -r original built; do
  count=$((count + 1))
  name=adaptation/$built
  if ! selected "$name"; then continue; fi
  start "$name"
  target="$work/source-$count"
  adaptation="${built%/*}/adaptation.patch"
  cp "$original" "$target"
  # GNU patch (Linux) and BSD patch (macOS) both use the actual patch command
  # exercised by the native harness, followed by a byte-for-byte comparison.
  if ! patch --batch "$target" "$adaptation" > "$work/patch.log" 2>&1; then
    cat "$work/patch.log" >&2
    printf 'Benchmark adaptation failed: %s\n' "$adaptation" >&2
    exit 1
  fi
  if ! cmp "$target" "$built"; then
    printf 'Benchmark adaptation does not reconstruct %s\n' "$built" >&2
    exit 1
  fi
  pass
done < "$work/adaptations.tsv"
check adaptation-inventory test "$count" -gt 0
if [ "$framework" = false ] || [ -z "${MLF_TEST_EXACT:-}" ]; then
  printf 'Benchmark provenance passed: all pinned hashes and %s exact patch reconstructions.\n' "$count"
fi

