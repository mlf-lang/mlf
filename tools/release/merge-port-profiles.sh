#!/usr/bin/env bash
# Assemble a logical port qualification from two unchanged native MLF reports.
set -euo pipefail
test "$#" -eq 3 || { printf '%s\n' 'usage: merge-port-profiles.sh BUILD_DIRECTORY COMPILER_SHA256 MANAGER_SHA256' >&2; exit 2; }
build=$(cd "$1" && pwd)
compiler_hash=$2
manager_hash=$3
[[ "$compiler_hash" =~ ^[a-f0-9]{64}$ && "$manager_hash" =~ ^[a-f0-9]{64}$ ]] || exit 2
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
test "$(sha256 "$build/bin/emlf" | awk '{print $1}')" = "$compiler_hash"
test "$(sha256 "$build/bin/mlfpkg" | awk '{print $1}')" = "$manager_hash"
base="$build/compiler-tests/unit/verification.json"
destination="$build/compiler-tests/port"
test ! -e "$destination" || { printf '%s\n' 'Refusing to replace an assembled port qualification.' >&2; exit 1; }
jq -e --arg compiler "$compiler_hash" --arg manager "$manager_hash" '
  .complete == true and .implementation == "MLF" and .group == "unit" and
  .compiler_sha256 == $compiler and .manager_sha256 == $manager and
  (.sources | type == "object" and length > 0)
' "$base" >/dev/null
for profile in standard compact-gc; do
  directory="$build/compiler-tests/port-$profile"
  report="$directory/verification.json"
  test -f "$report" && test ! -L "$report"
  jq -e --arg profile "$profile" --arg compiler "$compiler_hash" --arg manager "$manager_hash" '
    .complete == true and .implementation == "MLF" and .group == "port" and
    .compiler_sha256 == $compiler and .manager_sha256 == $manager and
    .requested_profiles == [$profile] and (.matrices | keys) == [$profile] and
    .matrices[$profile].backends == 2 and .matrices[$profile].rows == 25 and
    (.matrices[$profile].gc_free_space_divisor as $d | [1,2,4] | index($d) != null) and
    .matrices[$profile].gc_initial_heap_bytes == (if $profile == "standard" then 536870912 else 8388608 end) and
    (.matrices[$profile].log_sha256 | type == "string" and test("^[a-f0-9]{64}$"))
  ' "$report" >/dev/null
  cmp <(jq -S .sources "$base") <(jq -S .sources "$report")
  log="$directory/$profile.log"
  test -f "$log" && test ! -L "$log"
  test "$(sha256 "$log" | awk '{print $1}')" = "$(jq -er --arg profile "$profile" '.matrices[$profile].log_sha256' "$report")"
done
standard="$build/compiler-tests/port-standard/verification.json"
compact="$build/compiler-tests/port-compact-gc/verification.json"
standard_hash=$(sha256 "$standard" | awk '{print $1}')
compact_hash=$(sha256 "$compact" | awk '{print $1}')
mkdir "$destination"
cp "$build/compiler-tests/port-standard/standard.log" "$destination/standard.log"
cp "$build/compiler-tests/port-compact-gc/compact-gc.log" "$destination/compact-gc.log"
jq -s --arg standard "$standard_hash" --arg compact "$compact_hash" '
  .[0] as $s | .[1] as $c | $s |
  .requested_profiles = ["standard", "compact-gc"] |
  .matrices = ($s.matrices + $c.matrices) |
  .drivers_by_profile = {standard: $s.drivers, "compact-gc": $c.drivers} |
  del(.drivers) |
  .qualification_assembly = {
    implementation: "jq", kind: "verified-native-port-profiles",
    original_reports: {
      standard: {path: "../port-standard/verification.json", sha256: $standard},
      "compact-gc": {path: "../port-compact-gc/verification.json", sha256: $compact}
    }
  }
' "$standard" "$compact" > "$destination/verification.json.tmp"
mv "$destination/verification.json.tmp" "$destination/verification.json"
