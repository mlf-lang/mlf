#!/usr/bin/env bash
# Transport genuine native outputs within one source/platform/toolchain only.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
mode=${1:?export, import or verify required}
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
case "$(uname -s):$(uname -m)" in
  Darwin:arm64) platform=macos-arm64 ;;
  Linux:x86_64) platform=linux-x64 ;;
  *) exit 2 ;;
esac
shared=.mlf-build/shared-candidate
dependency_inputs() {
  for receipt in .mlf-build/cache/*/dependency-files.json; do
    test -f "$receipt" || continue
    jq -e 'type == "object"' "$receipt" >/dev/null
    jq -r 'to_entries[] | [.key,.value] | @tsv' "$receipt"
  done | LC_ALL=C sort -u
}
verify_dependencies() {
  while IFS=$'\t' read -r path expected; do
    case "/$path/" in *'/../'*|*'/./'*|*'\'*) exit 1 ;; esac
    case "$path" in "$PWD/.mlf-build/cache/"*) ;; *) echo 'Dependency escaped the shared native store.' >&2; exit 1 ;; esac
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]]
    test "$(sha256 "$path" | awk '{print $1}')" = "$expected" || { printf 'Missing or changed crate dependency: %s\n' "$path" >&2; exit 1; }
  done < "$1"
}
verify() {
  jq -e --arg source "$(git rev-parse HEAD)" --arg platform "$platform" --arg root "$PWD" \
    '.format == 1 and .source == $source and .platform == $platform and .root == $root' "$shared/manifest.json" >/dev/null
  while IFS=$'\t' read -r path expected; do
    test "$(sha256 "$path" | awk '{print $1}')" = "$expected" || { printf 'Changed shared candidate input: %s\n' "$path" >&2; exit 1; }
  done < <(jq -r '.inputs | to_entries[] | [.key,.value] | @tsv' "$shared/manifest.json")
  for report in .mlf-build/build-report.json .mlf-build/prerequisites/tests/build-report.json; do
    jq -e '.complete == true and .implementation == "MLF"' "$report" >/dev/null
  done
  for tool in emlf mlfpkg; do
    key=$(jq -er --arg kind "executable mlf-compiler:$tool" '[.builds[] | select(.kind == $kind) | .key] | if length == 1 then .[0] else error("missing unique native candidate") end' .mlf-build/build-report.json)
    [[ "$key" =~ ^[0-9a-f]{64}$ ]]
    cmp ".mlf-build/bin/$tool" ".mlf-build/cache/$key/program"
  done
  # The native runner travels with the exact compiler/manager pair. It has no
  # MLF artifact key, so bind its published bytes directly to the manifest.
  jq -e --arg path "$PWD/.mlf-build/bin/mlf-build-runner" '.inputs[$path] | test("^[0-9a-f]{64}$")' "$shared/manifest.json" >/dev/null
  test "$(.mlf-build/bin/mlf-build-runner --protocol-version)" = 1
  runner_hash=$(sha256 .mlf-build/bin/mlf-build-runner | awk '{print $1}')
  jq -se --arg hash "$runner_hash" 'all(.[]; all(.scheduler[]?; .helper.sha256 == $hash))' \
    .mlf-build/build-report.json .mlf-build/prerequisites/tests/build-report.json >/dev/null
  dependency_inputs > "$shared/dependency-inputs.tsv"
  verify_dependencies "$shared/dependency-inputs.tsv"
}
case "$mode" in
  export)
    test -z "$(git status --porcelain)" || { echo 'Commit candidate infrastructure before exporting.' >&2; exit 1; }
    test ! -e "$shared"
    mkdir -p "$shared"
    # Include the actual candidate outputs and native dependency identities from
    # both producers. Seed identities stay in the unmodified build reports.
    jq -s --arg source "$(git rev-parse HEAD)" --arg platform "$platform" --arg root "$PWD" '
      def hashes: to_entries | map({key:.key,value:.value});
      {format:1,source:$source,platform:$platform,root:$root,inputs:(
        [ .[] | .toolchain as $t |
          {key:$t.clang.path,value:$t.clang.sha256},
          {key:$t["pkg-config"].path,value:$t["pkg-config"].sha256},
          ($t.runtime | hashes[]), ($t.gmp.libraries | hashes[]), ($t.gmp.headers | hashes[]),
          (.native_inputs[]? | (.libraries | hashes[]), (.headers | hashes[])) ] | from_entries)}
    ' .mlf-build/build-report.json .mlf-build/prerequisites/tests/build-report.json > "$shared/manifest.json"
    for item in bin/emlf bin/mlfpkg bin/mlf-build-runner build-report.json prerequisites/tests/build-report.json; do
      path="$PWD/.mlf-build/$item"
      hash=$(sha256 "$path" | awk '{print $1}')
      jq --arg path "$path" --arg hash "$hash" '.inputs[$path] = $hash' "$shared/manifest.json" > "$shared/manifest.tmp"
      mv "$shared/manifest.tmp" "$shared/manifest.json"
    done
    verify
    # Keep the candidate's own fixed-point artifacts and the prerequisite build
    # closure. Builtin-prelude files are genuine outputs named by the ordinary
    # dependency receipts, even though they live under .queries. Keep their
    # original paths and hashes, without rewriting receipts or inference data.
    printf '%s\n' .mlf-build/bin .mlf-build/build-report.json \
      .mlf-build/prerequisites/tests/build-report.json > "$shared/archive-inputs.txt"
    jq -sr '[ (.[0].builds[] | select(.kind | startswith("executable mlf-compiler:"))), .[1].builds[] ] | map(.key) | unique[]' \
      .mlf-build/build-report.json .mlf-build/prerequisites/tests/build-report.json | while IFS= read -r key; do
        [[ "$key" =~ ^[0-9a-f]{64}$ ]]
        printf '.mlf-build/cache/%s\n' "$key"
      done >> "$shared/archive-inputs.txt"
    while IFS=$'\t' read -r path expected; do
      printf '%s\n' "${path#"$PWD/"}"
    done < "$shared/dependency-inputs.tsv" >> "$shared/archive-inputs.txt"
    LC_ALL=C sort -u "$shared/archive-inputs.txt" > "$shared/archive-inputs.sorted"
    COPYFILE_DISABLE=1 tar -czf "$shared/outputs.tar.gz" -T "$shared/archive-inputs.sorted"
    (cd "$shared" && sha256 outputs.tar.gz manifest.json > SHA256SUMS)
    ;;
  import)
    test -z "$(git status --porcelain)"
    test ! -e .mlf-build/bin && test ! -e .mlf-build/cache
    (cd "$shared" && sha256 -c SHA256SUMS)
    jq -e --arg source "$(git rev-parse HEAD)" --arg platform "$platform" --arg root "$PWD" \
      '.format == 1 and .source == $source and .platform == $platform and .root == $root' "$shared/manifest.json" >/dev/null
    tar -tzf "$shared/outputs.tar.gz" > "$shared/entries.txt"
    while IFS= read -r entry; do
      case "/$entry/" in *'/../'*|*'/./'*|//*|*'\'*) exit 1 ;; esac
      case "$entry" in .mlf-build/bin|.mlf-build/bin/*|.mlf-build/cache|.mlf-build/cache/*|.mlf-build/build-report.json|.mlf-build/prerequisites/tests/build-report.json) ;; *) exit 1 ;; esac
    done < "$shared/entries.txt"
    tar -xzf "$shared/outputs.tar.gz"
    verify
    printf 'MLF_COMPILER=%s/.mlf-build/bin/emlf\nMLF_PACKAGE_MANAGER=%s/.mlf-build/bin/mlfpkg\nMLF_BUILD_RUNNER=%s/.mlf-build/bin/mlf-build-runner\nMLF_CI_SHARED_CANDIDATE=1\n' "$PWD" "$PWD" "$PWD" >> "${GITHUB_ENV:?}"
    ;;
  verify) verify ;;
  *) exit 2 ;;
esac
