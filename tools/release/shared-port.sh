#!/usr/bin/env bash
# Transfer genuine checked-target build artifacts. Qualification execution and
# independent runtime references remain in the final port group.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
mode=${1:?export or import required}
shard=${2:?port preparation shard required}
case "$shard" in StateTypes|SolverReuse|InferenceConformance) count=1 ;; other) count=22 ;; *) exit 2 ;; esac
case "$(uname -s):$(uname -m)" in Darwin:arm64) platform=macos-arm64 ;; Linux:x86_64) platform=linux-x64 ;; *) exit 2 ;; esac
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
archive=".mlf-build/shared-port/$shard"
producer=".mlf-build/compiler-tests/port-prepare-$shard"
candidate=$(sha256 .mlf-build/shared-candidate/manifest.json | awk '{print $1}')
verify_files() {
  while IFS=$'\t' read -r path expected; do
    test -f "$path" && test ! -L "$path"
    test "$(sha256 "$path" | awk '{print $1}')" = "$expected"
  done < <(jq -r '.files | to_entries[] | [.key,.value] | @tsv' "$archive/manifest.json")
  jq -es --arg compiler "$PWD/.mlf-build/bin/emlf" --arg manager "$PWD/.mlf-build/bin/mlfpkg" '
    .[0].compiler_sha256 == .[1].inputs[$compiler] and .[0].manager_sha256 == .[1].inputs[$manager]
  ' "$producer/verification.json" .mlf-build/shared-candidate/manifest.json >/dev/null
  jq -e --arg group "port-prepare-$shard" --argjson count "$count" '
    .complete == true and .implementation == "MLF" and .group == $group and
    .requested_profiles == [] and .prepared_port.targets == $count and
    (.prepared_port.target_hashes | length) == $count and (has("matrices") | not)
  ' "$producer/verification.json" >/dev/null
  jq -e --argjson count "$count" '
    .complete == true and .implementation == "MLF" and (.builds | length) == $count and
    all(.builds[]; .kind | startswith("checked port target "))
  ' "$producer/port-preparation/build-report.json" >/dev/null
  jq -es '
    .[0].compiler_sha256 == .[1].compiler_sha256 and .[0].manager_sha256 == .[1].manager_sha256 and
    (.[0].cache_keys | sort) == ([.[2].builds[].key] | sort)
  ' "$archive/manifest.json" "$producer/verification.json" "$producer/port-preparation/build-report.json" >/dev/null
  key=$(jq -er '[.builds[] | select(.kind == "executable mlf-tests:port") | .key] | if length == 1 then .[0] else error("missing port producer") end' .mlf-build/prerequisites/tests/build-report.json)
  checker=$(sha256 ".mlf-build/cache/$key/program" | awk '{print $1}')
  jq -es --arg checker "$checker" --argjson count "$count" '
    .[0].sources == .[1].sources and .[0].checker_sha256 == $checker and
    (.[0].targets | length) == $count and
    ([.[0].targets[].fixture] | sort) == .[2].fixtures
  ' "$producer/prepared-port.json" "$producer/verification.json" "$archive/manifest.json" >/dev/null
  while IFS=$'\t' read -r fixture target hash checks_hash; do
    test "$(sha256 "$target" | awk '{print $1}')" = "$hash"
    test "$(sha256 "$target.checks.json" | awk '{print $1}')" = "$checks_hash"
    jq -e --arg fixture "$fixture" --arg hash "$hash" '
      .format == 1 and .fixture == $fixture and .target_sha256 == $hash and .entry_type == "IO Unit" and
      .checks == ["independent-type","inferred-type","serialization-erasure","transported-type"]
    ' "$target.checks.json" >/dev/null
  done < <(jq -r '.targets[] | [.fixture,.target,.target_sha256,.checks_sha256] | @tsv' "$producer/prepared-port.json")
}
tools/release/shared-candidate.sh verify
case "$mode" in
  export)
    test -z "$(git status --porcelain)"
    test ! -e "$archive"
    mkdir -p "$archive"
    jq -n --arg source "$(git rev-parse HEAD)" --arg root "$PWD" --arg platform "$platform" \
      --arg shard "$shard" --arg candidate "$candidate" \
      --slurpfile report "$producer/verification.json" --slurpfile build "$producer/port-preparation/build-report.json" '
      {format:1,source:$source,root:$root,platform:$platform,shard:$shard,candidate_manifest_sha256:$candidate,
       compiler_sha256:$report[0].compiler_sha256,manager_sha256:$report[0].manager_sha256,
       fixtures:($report[0].prepared_port.target_hashes | keys),cache_keys:[$build[0].builds[].key]}
    ' > "$archive/manifest.json"
    printf '%s\n' "$producer/verification.json" "$producer/prepared-port.json" \
      "$producer/port-preparation/build-report.json" "$producer/suite-build/build-report.json" > "$archive/inputs.txt"
    jq -r '.cache_keys[]' "$archive/manifest.json" | while IFS= read -r key; do
      [[ "$key" =~ ^[0-9a-f]{64}$ ]]
      printf '.mlf-build/cache/%s\n' "$key"
    done >> "$archive/inputs.txt"
    while IFS= read -r path; do
      find "$path" -type f
    done < "$archive/inputs.txt" | LC_ALL=C sort -u > "$archive/files.txt"
    while IFS= read -r path; do
      test ! -L "$path"
      printf '%s\t%s\n' "$path" "$(sha256 "$path" | awk '{print $1}')"
    done < "$archive/files.txt" | jq -Rn '[inputs | split("\t") | {key:.[0],value:.[1]}] | from_entries' > "$archive/files.json"
    jq -s '.[0] + {files:.[1]}' "$archive/manifest.json" "$archive/files.json" > "$archive/manifest.tmp"
    mv "$archive/manifest.tmp" "$archive/manifest.json"
    verify_files
    COPYFILE_DISABLE=1 tar -czf "$archive/outputs.tar.gz" -T "$archive/inputs.txt"
    (cd "$archive" && sha256 outputs.tar.gz manifest.json > SHA256SUMS)
    rm "$archive/inputs.txt" "$archive/files.txt" "$archive/files.json"
    if test -n "${GITHUB_OUTPUT:-}"; then printf 'archive=%s\n' "$archive" >> "$GITHUB_OUTPUT"; fi
    ;;
  import)
    (cd "$archive" && sha256 -c SHA256SUMS)
    jq -e --arg source "$(git rev-parse HEAD)" --arg root "$PWD" --arg platform "$platform" --arg shard "$shard" \
      --arg candidate "$candidate" --argjson count "$count" '
      .format == 1 and .source == $source and .root == $root and .platform == $platform and .shard == $shard and
      .candidate_manifest_sha256 == $candidate and (.cache_keys | length) == $count and
      (.cache_keys | unique | length) == $count and (.fixtures | length) == $count and (.fixtures | unique | length) == $count and
      (if $shard == "other" then all(.fixtures[]; . != "StateTypes" and . != "SolverReuse" and . != "InferenceConformance") else .fixtures == [$shard] end)
    ' "$archive/manifest.json" >/dev/null
    while IFS= read -r key; do
      [[ "$key" =~ ^[0-9a-f]{64}$ ]]
      test ! -e ".mlf-build/cache/$key"
    done < <(jq -r '.cache_keys[]' "$archive/manifest.json")
    tar -tzf "$archive/outputs.tar.gz" > "$archive/entries.txt"
    while IFS= read -r entry; do
      case "/$entry/" in *'/../'*|*'/./'*|//*|*'\'*) exit 1 ;; esac
      if [[ "$entry" = .mlf-build/cache/* ]]; then
        key=${entry#.mlf-build/cache/}; key=${key%%/*}
        jq -e --arg key "$key" '.cache_keys | index($key) != null' "$archive/manifest.json" >/dev/null
      else
        case "$entry" in "$producer/verification.json"|"$producer/prepared-port.json"|"$producer/port-preparation/build-report.json"|"$producer/suite-build/build-report.json") ;; *) exit 1 ;; esac
      fi
    done < "$archive/entries.txt"
    tar -xzf "$archive/outputs.tar.gz"
    verify_files
    tools/release/shared-candidate.sh verify
    ;;
  *) exit 2 ;;
esac
