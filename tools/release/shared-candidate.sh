#!/usr/bin/env bash
# Transport genuine native outputs within one source/platform/toolchain only.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
mode=${1:?export, import or verify required}
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$@"; else shasum -a 256 "$@"; fi; }
digest() { sha256 "$1" | awk '{print $1}'; }
case "$(uname -s):$(uname -m)" in
  Darwin:arm64) platform=macos-arm64 ;;
  Linux:x86_64) platform=linux-x64 ;;
  *) exit 2 ;;
esac
shared=.mlf-build/shared-candidate
runner_report=.mlf-build/prerequisites/compiler-tests/build-report.json
reports=(.mlf-build/build-report.json .mlf-build/prerequisites/tests/build-report.json "$runner_report")
# Paths remain at the producer root. Never rewrite reports or relocate cache
# identities to manufacture a matching receipt.
relative_path() {
  case "$1" in ''|/*|*\\*) return 1 ;; esac
  case "/$1/" in *'/../'*|*'/./'*|*'//'*) return 1 ;; esac
}
dependency_inputs() {
  while IFS= read -r key; do
    receipt=".mlf-build/cache/$key/dependency-files.json"
    test -f "$receipt" || continue
    jq -e 'type == "object"' "$receipt" >/dev/null
    jq -r 'to_entries[] | [.key,.value] | @tsv' "$receipt"
  done < <(jq -r '.artifact_keys[]' "$shared/manifest.json") | LC_ALL=C sort -u
}
verify_dependencies() {
  while IFS=$'\t' read -r path expected; do
    case "/$path/" in *'/../'*|*'/./'*|*'\\'*) exit 1 ;; esac
    case "$path" in "$PWD/.mlf-build/cache/"*) ;; *) echo 'Dependency escaped the shared native store.' >&2; exit 1 ;; esac
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]]
    test "$(digest "$path")" = "$expected" || { printf 'Missing or changed crate dependency: %s\n' "$path" >&2; exit 1; }
  done < "$1"
}
verify_artifacts() {
  jq -se --slurpfile manifest "$shared/manifest.json" '
    ([.[] | .builds[].key] | unique) == $manifest[0].artifact_keys
  ' "${reports[@]}" >/dev/null
  while IFS= read -r key; do
    artifact=".mlf-build/cache/$key"
    jq -e --arg key "$key" '
      .key == $key and (.files | type == "object" and length > 0) and
      all(.files[]; type == "string" and test("^[0-9a-f]{64}$"))
    ' "$artifact/artifact.json" >/dev/null
    if jq -se --arg key "$key" 'any(.[] | .builds[]; .key == $key and (.kind | startswith("crate ") or startswith("executable ")))' "${reports[@]}" >/dev/null; then
      jq -e '.files | has("dependency-files.json") and has("unit.mlfci") and has("unit.mlfco")' "$artifact/artifact.json" >/dev/null
    fi
    while IFS=$'\t' read -r file expected; do
      relative_path "$file"
      test -f "$artifact/$file" && test ! -L "$artifact/$file"
      test "$(digest "$artifact/$file")" = "$expected"
    done < <(jq -r '.files | to_entries[] | [.key,.value] | @tsv' "$artifact/artifact.json")
  done < <(jq -r '.artifact_keys[]' "$shared/manifest.json")
}
verify_publication() {
  local report=$1 name=$2 binary=$3 key artifact
  key=$(jq -er --arg kind "executable mlf-compiler:$name" '[.builds[] | select(.kind == $kind) | .key] | if length == 1 then .[0] else error("missing unique native publication") end' "$report")
  [[ "$key" =~ ^[0-9a-f]{64}$ ]]
  artifact="$PWD/.mlf-build/cache/$key"
  jq -se --arg name "$name" --arg key "$key" --arg artifact "$artifact" --arg hash "$(digest "$binary")" '
    .[0] as $report | .[1] as $stamp |
    [$report."pending-publications"[] | select(.name == $name)] as $published |
    ($published | length) == 1 and $published[0].key == $key and
    $published[0].artifact == $artifact and $published[0].binary == ($artifact + "/program") and
    $published[0].files == $stamp.files and $stamp.key == $key and
    $published[0].files.program == $hash
  ' "$report" "$artifact/artifact.json" >/dev/null
  cmp "$binary" "$artifact/program"
}
verify_runner() {
  compiler_hash=$(digest .mlf-build/bin/emlf)
  manager_hash=$(digest .mlf-build/bin/mlfpkg)
  helper_hash=$(digest .mlf-build/bin/mlf-build-runner)
  runner_hash=$(digest .mlf-build/bin/compiler-tests)
  report_hash=$(digest "$runner_report")
  jq -es --arg root "$PWD" --arg compiler "$compiler_hash" --arg manager "$manager_hash" \
    --arg helper "$helper_hash" --arg runner "$runner_hash" --arg report "$report_hash" '
    def digest: type == "string" and test("^[0-9a-f]{64}$");
    .[0] as $b | .[1].campaign_runner as $r |
    $b.format == 1 and $b.complete == true and $b.implementation == "MLF" and
    $b.cache_directory == ($root + "/.mlf-build/cache") and
    ($b.packages.packages | length > 0) and
    ([$b.packages.packages[] | select(.path == "." and .name == "mlf-compiler")] | length) == 1 and
    $b.toolchain.compiler == {path:($root + "/.mlf-build/bin/emlf"),sha256:$compiler} and
    $b.toolchain.manager == {path:($root + "/.mlf-build/bin/mlfpkg"),sha256:$manager} and
    ($b.scheduler | length) == 1 and ($b.scheduler_results | length) == 1 and
    $b.scheduler[0].helper == {path:($root + "/.mlf-build/bin/mlf-build-runner"),sha256:$helper} and
    $b.scheduler_results[0].complete == true and
    $b.scheduler_results[0].exit_code == 0 and
    ($b.scheduler_results[0].jobs == 1 or $b.scheduler_results[0].jobs == 2) and
    ($b.scheduler_results[0].maximum_parallel_jobs >= 0 and
     $b.scheduler_results[0].maximum_parallel_jobs <= $b.scheduler_results[0].jobs) and
    $b.scheduler[0].invocation_id == $b.scheduler_results[0].invocation_id and
    $r.report == ".mlf-build/prerequisites/compiler-tests/build-report.json" and
    $r.report_sha256 == $report and $r.sha256 == $runner and
    $r.compiler_sha256 == $compiler and $r.manager_sha256 == $manager and $r.build_runner_sha256 == $helper and
    ($r.executable_key | digest) and
    [$b.builds[] | select(.kind == "executable mlf-compiler:compiler-tests") | .key] == [$r.executable_key] and
    $r.dependency_keys == ([$b.builds[].key] | unique)
  ' "$runner_report" "$shared/manifest.json" >/dev/null
  verify_publication "$runner_report" compiler-tests .mlf-build/bin/compiler-tests
  # A source commit alone is insufficient if a stale producer report was packed.
  # Check the actual root package and every source dependency of the runner.
  while IFS=$'\t' read -r package source expected; do
    test "$package" = . || relative_path "$package"
    relative_path "$source"
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]]
    test "$(digest "$package/$source")" = "$expected"
  done < <(jq -r '.packages.packages[] | .path as $p |
    ([$p,"mlf-package.json",.manifest]), (.sources | to_entries[] | [$p,.key,.value]) | @tsv' "$runner_report")
  # Reject a changed selected tool or ambient native environment even if an old
  # version is still installed at the original producer path.
  for tool in clang pkg-config; do
    test "$(digest "$(command -v "$tool")")" = "$(jq -er --arg tool "$tool" '.toolchain[$tool].sha256' "$runner_report")"
  done
  while IFS=$'\t' read -r name expected; do
    test "${!name:-}" = "$expected"
  done < <(jq -r '.toolchain.native_environment | to_entries[] | [.key,.value] | @tsv' "$runner_report")
}
verify() {
  jq -e --arg source "$(git rev-parse HEAD)" --arg platform "$platform" --arg root "$PWD" '
    .format == 2 and .source == $source and .platform == $platform and .root == $root and
    (.artifact_keys | length > 0) and .artifact_keys == (.artifact_keys | unique) and
    all(.artifact_keys[]; test("^[0-9a-f]{64}$")) and (.files | length > 0)
  ' "$shared/manifest.json" >/dev/null
  while IFS=$'\t' read -r path expected; do
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]]
    test "$(digest "$path")" = "$expected" || { printf 'Changed shared candidate input: %s\n' "$path" >&2; exit 1; }
  done < <(jq -r '.inputs | to_entries[] | [.key,.value] | @tsv' "$shared/manifest.json")
  while IFS=$'\t' read -r path expected; do
    relative_path "$path"
    case "$path" in .mlf-build/*) ;; *) exit 1 ;; esac
    test -f "$path" && test ! -L "$path"
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]]
    test "$(digest "$path")" = "$expected" || { printf 'Changed shared candidate output: %s\n' "$path" >&2; exit 1; }
  done < <(jq -r '.files | to_entries[] | [.key,.value] | @tsv' "$shared/manifest.json")
  for report in "${reports[@]}"; do
    jq -e '.complete == true and .implementation == "MLF" and
      all(.scheduler_results[]; .complete == true and .exit_code == 0)' "$report" >/dev/null
  done
  verify_artifacts
  for tool in emlf mlfpkg; do
    verify_publication .mlf-build/build-report.json "$tool" ".mlf-build/bin/$tool"
  done
  test "$(.mlf-build/bin/mlf-build-runner --protocol-version)" = 1
  helper_hash=$(digest .mlf-build/bin/mlf-build-runner)
  jq -se --arg hash "$helper_hash" 'all(.[]; all(.scheduler[]?; .helper.sha256 == $hash))' "${reports[@]}" >/dev/null
  verify_runner
  dependency_inputs > "$shared/dependency-inputs.tsv"
  verify_dependencies "$shared/dependency-inputs.tsv"
}
case "$mode" in
  export)
    test -z "$(git status --porcelain)" || { echo 'Commit candidate infrastructure before exporting.' >&2; exit 1; }
    test ! -e "$shared"
    mkdir -p "$shared"
    jq -s --arg source "$(git rev-parse HEAD)" --arg platform "$platform" --arg root "$PWD" '
      def hashes: to_entries | map({key:.key,value:.value});
      {format:2,source:$source,platform:$platform,root:$root,
       artifact_keys:([.[] | .builds[].key] | unique),inputs:(
        [ .[] | .toolchain as $t |
          {key:$t.clang.path,value:$t.clang.sha256},
          {key:$t["pkg-config"].path,value:$t["pkg-config"].sha256},
          ($t.runtime | hashes[]), ($t.gmp.libraries | hashes[]), ($t.gmp.headers | hashes[]),
          (.native_inputs[]? | (.libraries | hashes[]), (.headers | hashes[])) ] | from_entries)}
    ' "${reports[@]}" > "$shared/manifest.json"
    for item in bin/emlf bin/mlfpkg bin/compiler-tests bin/mlf-build-runner build-report.json prerequisites/tests/build-report.json prerequisites/compiler-tests/build-report.json; do
      path="$PWD/.mlf-build/$item"
      jq --arg path "$path" --arg hash "$(digest "$path")" '.inputs[$path] = $hash' "$shared/manifest.json" > "$shared/manifest.tmp"
      mv "$shared/manifest.tmp" "$shared/manifest.json"
    done
    jq --arg report "$runner_report" --arg report_hash "$(digest "$runner_report")" \
      --arg binary "$(digest .mlf-build/bin/compiler-tests)" --slurpfile runner "$runner_report" '
      .campaign_runner = {report:$report,report_sha256:$report_hash,sha256:$binary,
        compiler_sha256:$runner[0].toolchain.compiler.sha256,manager_sha256:$runner[0].toolchain.manager.sha256,
        build_runner_sha256:$runner[0].scheduler[0].helper.sha256,
        executable_key:([$runner[0].builds[] | select(.kind == "executable mlf-compiler:compiler-tests") | .key] |
          if length == 1 then .[0] else error("missing unique final-compiler runner") end),
        dependency_keys:([$runner[0].builds[].key] | unique)}
    ' "$shared/manifest.json" > "$shared/manifest.tmp"
    mv "$shared/manifest.tmp" "$shared/manifest.json"
    printf '%s\n' .mlf-build/bin "${reports[@]}" > "$shared/archive-inputs.txt"
    jq -r '.artifact_keys[]' "$shared/manifest.json" | while IFS= read -r key; do
      [[ "$key" =~ ^[0-9a-f]{64}$ ]]
      printf '.mlf-build/cache/%s\n' "$key"
    done >> "$shared/archive-inputs.txt"
    dependency_inputs > "$shared/dependency-inputs.tsv"
    verify_dependencies "$shared/dependency-inputs.tsv"
    while IFS=$'\t' read -r path expected; do printf '%s\n' "${path#"$PWD/"}"; done \
      < "$shared/dependency-inputs.tsv" >> "$shared/archive-inputs.txt"
    # Bind every transported artifact file, including original dependency and
    # artifact receipts, rather than trusting only the top-level executable.
    while IFS= read -r path; do find "$path" -type f; done < "$shared/archive-inputs.txt" | LC_ALL=C sort -u > "$shared/files.txt"
    while IFS= read -r path; do
      relative_path "$path"
      test ! -L "$path"
      printf '%s\t%s\n' "$path" "$(digest "$path")"
    done < "$shared/files.txt" | jq -Rn '[inputs | split("\t") | {key:.[0],value:.[1]}] | from_entries' > "$shared/files.json"
    jq -s '.[0] + {files:.[1]}' "$shared/manifest.json" "$shared/files.json" > "$shared/manifest.tmp"
    mv "$shared/manifest.tmp" "$shared/manifest.json"
    verify
    # Only regular authenticated files are packed, never symlinks or execution
    # verdicts. Tar is transport; the unmodified producer reports are the proof.
    COPYFILE_DISABLE=1 tar -czf "$shared/outputs.tar.gz" -T "$shared/files.txt"
    (cd "$shared" && sha256 outputs.tar.gz manifest.json > SHA256SUMS)
    ;;
  import)
    test -z "$(git status --porcelain)"
    test ! -e .mlf-build/bin && test ! -e .mlf-build/cache
    (cd "$shared" && sha256 -c SHA256SUMS)
    jq -e --arg source "$(git rev-parse HEAD)" --arg platform "$platform" --arg root "$PWD" \
      '.format == 2 and .source == $source and .platform == $platform and .root == $root' "$shared/manifest.json" >/dev/null
    tar -tzf "$shared/outputs.tar.gz" > "$shared/entries.txt"
    while IFS= read -r entry; do
      relative_path "$entry"
      case "$entry" in .mlf-build/bin/*|.mlf-build/cache/*|.mlf-build/build-report.json|.mlf-build/prerequisites/tests/build-report.json|"$runner_report") ;; *) exit 1 ;; esac
      jq -e --arg path "$entry" '.files | has($path)' "$shared/manifest.json" >/dev/null
    done < "$shared/entries.txt"
    cmp <(LC_ALL=C sort "$shared/entries.txt") <(jq -r '.files | keys[]' "$shared/manifest.json" | LC_ALL=C sort)
    # Require regular files before extraction (no links, devices or traversal).
    tar -tvzf "$shared/outputs.tar.gz" | while IFS= read -r entry; do case "$entry" in -*) ;; *) exit 1 ;; esac; done
    tar -xzf "$shared/outputs.tar.gz"
    verify
    printf 'MLF_COMPILER=%s/.mlf-build/bin/emlf\nMLF_PACKAGE_MANAGER=%s/.mlf-build/bin/mlfpkg\nMLF_BUILD_RUNNER=%s/.mlf-build/bin/mlf-build-runner\nMLF_CI_SHARED_CANDIDATE=1\n' "$PWD" "$PWD" "$PWD" >> "${GITHUB_ENV:?}"
    ;;
  verify) verify ;;
  *) exit 2 ;;
esac
