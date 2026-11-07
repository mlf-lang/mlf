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
preparation="$producer/port-preparation/build-report.json"
candidate=$(sha256 .mlf-build/shared-candidate/manifest.json | awk '{print $1}')

# Bind each split version to its fixture. Only exact cold attempt
# files are admitted beyond the ordinary cache products and build receipts.
proof_record= proof_files_key= proof_mode= proof_attempt= proof_command=
case "$shard" in
  StateTypes)
    proof_record=state_types_split
    proof_files_key=state_types_split_files
    proof_mode=state-types-split-v1
    proof_attempt=state-types-split-
    proof_command=--prepare-statetypes-split
    ;;
  InferenceConformance)
    proof_record=inference_discovered
    proof_files_key=inference_discovered_files
    proof_mode=inference-discovered-split-v1
    proof_attempt=inference-discovered-
    proof_command=--prepare-inferenceconformance-discovered
    ;;
esac

discovered_files() {
  jq -ce --arg root "$PWD/" --arg prep "$PWD/$producer/port-preparation" \
    --arg record "$proof_record" --arg mode "$proof_mode" --arg attempt "$proof_attempt" \
    --arg command "$proof_command" \
    --arg binary "$PWD/$producer/suite-build/bin/port" '
    def digest: type == "string" and test("^[0-9a-f]{64}$");
    .[$record] as $splits |
    $splits[0] as $split |
    [$split.attempt + "/coordinator.stdout", $split.attempt + "/config.json",
     $split.attempt + "/source-inputs.json",
     ($split.attempt + "/scratch/" + ("producer.stdout","producer.stderr","consumer.stdout","consumer.stderr")),
     ($split.attempt + "/scratch/producer/" + ("unit.mlfci","unit.mlfco","unit.queries","ordered-proof.json"))] as $outputs |
    [.commands[] | select(.argv[1] == $command)] as $commands |
    $commands[0] as $command |
    if .complete == true and .implementation == "MLF" and
       ($splits | type == "array" and length == 1) and
       ($split | keys == ["attempt","build_report_sha256","files","mode","preparation_sha256"]) and
       $split.mode == $mode and
       ($split.build_report_sha256 | digest) and ($split.preparation_sha256 | digest) and
       ($split.attempt | startswith($prep + "/" + $attempt) and
         (ltrimstr($prep + "/" + $attempt) | test("^[A-Za-z0-9]{8}$"))) and
       ($commands | length == 1) and ($command.argv | length == 4) and
       ($record == "state_types_split" or $command.argv[0] == $binary) and
       $command.cwd == ($root | rtrimstr("/")) and $command.exit_code == 0 and
       $command.argv[2] == ($split.attempt + "/config.json") and
       $command.argv[3] == $split.files[$command.argv[2]] and
       $command.stdout == ($split.attempt + "/coordinator.stdout") and
       ($command.stderr | startswith($prep + "/commands/") and
         (ltrimstr($prep + "/commands/") | test("^(0|[1-9][0-9]*)[.]stderr$"))) and
       ($split.files | type == "object" and keys == (($outputs + [$command.stderr]) | sort)) and
       all($split.files[]; digest)
    then $split.files | with_entries(.key |= ltrimstr($root))
    else error("invalid cold discovered Port evidence inventory") end
  ' "$1"
}

verify_discovered_manifest() {
  jq -e --arg key "$proof_files_key" --argjson split "$1" '
    .files as $files | .[$key] == $split and
    all($split | to_entries[]; $files[.key] == .value)
  ' "$archive/manifest.json" >/dev/null
}

require_port_parents() {
  local path=$1
  while [[ "$path" = */* ]]; do
    path=${path%/*}
    test ! -L "$path"
    if test -e "$path"; then test -d "$path"; fi
  done
}

verify_discovered_seal() {
  local target suite_digest seal_digest discovered_digest
  target="$PWD/.mlf-build/cache/$(jq -er '.cache_keys[0]' "$archive/manifest.json")/unit.xmlf"
  suite_digest=$(sha256 "$producer/suite-build/build-report.json" | awk '{print $1}')
  seal_digest=$(sha256 "$target.preparation.json" | awk '{print $1}')
  discovered_digest=$(sha256 "$target.discovered.json" | awk '{print $1}')
  jq -es --arg target "$target" --arg suite "$suite_digest" --arg seal_digest "$seal_digest" \
    --arg discovered "$discovered_digest" --arg checker "$checker" \
    --arg record "$proof_record" --arg fixture "$shard" '
    .[0][$record][0] as $split | .[1].targets[0] as $row | .[2] as $seal |
    $split.files as $files | $split.attempt as $attempt |
    .[3].prepared_port.preparation_route == $split.mode and
    $split.build_report_sha256 == $suite and $split.preparation_sha256 == $seal_digest and
    $row.fixture == $fixture and $row.target == $target and $row.preparation_mode == $split.mode and
    $row.preparation_sha256 == $seal_digest and $row.discovered_sha256 == $discovered and
    $seal.format == 1 and $seal.fixture == $fixture and $seal.preparation_mode == $split.mode and
    $seal.checker_sha256 == $checker and $seal.target_sha256 == $row.target_sha256 and
    $seal.checks_sha256 == $row.checks_sha256 and $seal.discovered_sha256 == $discovered and
    $seal.source_inputs_sha256 == $files[$attempt + "/source-inputs.json"] and
    $seal.interface_sha256 == $files[$attempt + "/scratch/producer/unit.mlfci"] and
    $seal.object_sha256 == $files[$attempt + "/scratch/producer/unit.mlfco"] and
    $seal.queries_sha256 == $files[$attempt + "/scratch/producer/unit.queries"] and
    $seal.ordered_proof_sha256 == $files[$attempt + "/scratch/producer/ordered-proof.json"]
  ' "$preparation" "$producer/prepared-port.json" "$target.preparation.json" "$producer/verification.json" >/dev/null
}

verify_files() {
  if [[ -n "$proof_record" ]]; then
    local split_files
    split_files=$(discovered_files "$preparation")
    verify_discovered_manifest "$split_files"
  fi
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
  ' "$preparation" >/dev/null
  jq -es '
    .[0].compiler_sha256 == .[1].compiler_sha256 and .[0].manager_sha256 == .[1].manager_sha256 and
    (.[0].cache_keys | sort) == ([.[2].builds[].key] | sort)
  ' "$archive/manifest.json" "$producer/verification.json" "$preparation" >/dev/null
  key=$(jq -er '[.builds[] | select(.kind == "executable mlf-tests:port") | .key] | if length == 1 then .[0] else error("missing port producer") end' .mlf-build/prerequisites/tests/build-report.json)
  checker=$(sha256 ".mlf-build/cache/$key/program" | awk '{print $1}')
  jq -es --arg checker "$checker" --argjson count "$count" '
    .[0].sources == .[1].sources and .[0].checker_sha256 == $checker and
    (.[0].targets | length) == $count and
    ([.[0].targets[].fixture] | sort) == .[2].fixtures
  ' "$producer/prepared-port.json" "$producer/verification.json" "$archive/manifest.json" >/dev/null
  if [[ -n "$proof_record" ]]; then verify_discovered_seal; fi
  while IFS=$'\t' read -r fixture target hash checks_hash; do
    test "$(sha256 "$target" | awk '{print $1}')" = "$hash"
    test "$(sha256 "$target.checks.json" | awk '{print $1}')" = "$checks_hash"
    jq -e --arg fixture "$fixture" --arg hash "$hash" '
      .format == 1 and .fixture == $fixture and .target_sha256 == $hash and .entry_type == "IO ()" and
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
    split_files=null
    if [[ -n "$proof_record" ]]; then split_files=$(discovered_files "$preparation"); fi
    jq -n --arg source "$(git rev-parse HEAD)" --arg root "$PWD" --arg platform "$platform" \
      --arg shard "$shard" --arg candidate "$candidate" \
      --arg proof_key "$proof_files_key" --argjson split "$split_files" --slurpfile report "$producer/verification.json" --slurpfile build "$preparation" '
      {format:1,source:$source,root:$root,platform:$platform,shard:$shard,candidate_manifest_sha256:$candidate,
       compiler_sha256:$report[0].compiler_sha256,manager_sha256:$report[0].manager_sha256,
       fixtures:($report[0].prepared_port.target_hashes | keys),cache_keys:[$build[0].builds[].key]} +
       (if $split == null then {} else {($proof_key):$split} end)
    ' > "$archive/manifest.json"
    printf '%s\n' "$producer/verification.json" "$producer/prepared-port.json" \
      "$preparation" "$producer/suite-build/build-report.json" > "$archive/inputs.txt"
    jq -r '.cache_keys[]' "$archive/manifest.json" | while IFS= read -r key; do
      [[ "$key" =~ ^[0-9a-f]{64}$ ]]
      printf '.mlf-build/cache/%s\n' "$key"
    done >> "$archive/inputs.txt"
    if [[ -n "$proof_record" ]]; then
      jq -r --arg key "$proof_files_key" '.[$key] | keys[]' "$archive/manifest.json" | while IFS= read -r path; do
        require_port_parents "$path"
        test -f "$path"
        test ! -L "$path"
        printf '%s\n' "$path"
      done >> "$archive/inputs.txt"
    fi
    while IFS= read -r path; do
      find "$path" -type f
    done < "$archive/inputs.txt" | LC_ALL=C sort -u > "$archive/files.txt"
    while IFS= read -r path; do
      if [[ -n "$proof_record" ]]; then require_port_parents "$path"; fi
      test ! -L "$path"
      printf '%s\t%s\n' "$path" "$(sha256 "$path" | awk '{print $1}')"
    done < "$archive/files.txt" | jq -Rn '[inputs | split("\t") | {key:.[0],value:.[1]}] | from_entries' > "$archive/files.json"
    jq -s '.[0] + {files:.[1]}' "$archive/manifest.json" "$archive/files.json" > "$archive/manifest.tmp"
    mv "$archive/manifest.tmp" "$archive/manifest.json"
    verify_files
    tar_inputs="$archive/inputs.txt"
    if [[ -n "$proof_record" ]]; then tar_inputs="$archive/files.txt"; fi
    COPYFILE_DISABLE=1 tar -czf "$archive/outputs.tar.gz" -T "$tar_inputs"
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
    if [[ -n "$proof_record" ]]; then
      split_files=$(tar -xOzf "$archive/outputs.tar.gz" "$preparation" | discovered_files /dev/stdin)
      verify_discovered_manifest "$split_files"
      expected_entries=$(jq -er '.files | keys[]' "$archive/manifest.json" | LC_ALL=C sort)
      test "$(LC_ALL=C sort "$archive/entries.txt")" = "$expected_entries"
      # A discovered Port archive lists regular files explicitly, including its
      # cache files. Reject links or other member types before extraction.
      LC_ALL=C tar -tvzf "$archive/outputs.tar.gz" | awk '
        substr($0,1,1) != "-" || / link to | -> / {invalid=1}
        END {exit (invalid || NR == 0)}'
    fi
    while IFS= read -r entry; do
      case "/$entry/" in *'/../'*|*'/./'*|//*|*'\'*) exit 1 ;; esac
      if [[ "$entry" = .mlf-build/cache/* ]]; then
        key=${entry#.mlf-build/cache/}; key=${key%%/*}
        jq -e --arg key "$key" '.cache_keys | index($key) != null' "$archive/manifest.json" >/dev/null
      else
        case "$entry" in
          "$producer/verification.json"|"$producer/prepared-port.json"|"$preparation"|"$producer/suite-build/build-report.json") ;;
          *) [[ -n "$proof_record" ]]
             jq -e --arg key "$proof_files_key" --arg path "$entry" '.[$key] | has($path)' "$archive/manifest.json" >/dev/null ;;
        esac
      fi
      if [[ -n "$proof_record" ]]; then
        require_port_parents "$entry"
        test ! -e "$entry"
        test ! -L "$entry"
      fi
    done < "$archive/entries.txt"
    tar -xzf "$archive/outputs.tar.gz"
    verify_files
    tools/release/shared-candidate.sh verify
    ;;
  *) exit 2 ;;
esac
