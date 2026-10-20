#!/usr/bin/env bash
# Fail before a native build if a benchmark pin or source adaptation is broken.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
manifest=benchmarks/manifest.json
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }

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

mkdir -p .mlf-build
work=$(mktemp -d "$PWD/.mlf-build/benchmark-provenance.XXXXXX")
case "$work" in "$PWD"/.mlf-build/benchmark-provenance.*) ;; *) exit 1 ;; esac
trap 'rm -rf -- "$work"' EXIT
jq -r '.pinned_sha256 | to_entries[] | "\(.value)  \(.key)"' "$manifest" > "$work/SHA256SUMS"
sha256 -c "$work/SHA256SUMS" >/dev/null
jq -r '.workloads[].provenance[] | select(.original_source != .build_source) | [.original_source,.build_source] | @tsv' "$manifest" > "$work/adaptations.tsv"

count=0
while IFS=$'\t' read -r original built; do
  count=$((count + 1))
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
done < "$work/adaptations.tsv"
test "$count" -gt 0
printf 'Benchmark provenance passed: all pinned hashes and %s exact patch reconstructions.\n' "$count"
