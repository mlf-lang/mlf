#!/bin/sh
# Native-only transition: released seed -> frozen legacy bridge -> exact shared
# sources. GHC, source translators and mutable historical checkouts are not used.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
build=${MLF_SHARED_BOOTSTRAP_DIR:-${MLF_ASYNC_BOOTSTRAP_DIR:-"$root/.mlf-build/shared-bootstrap"}}
mkdir -p "$build"
build=$(CDPATH= cd -- "$build" && pwd)
# Never let a failed/retried invocation advertise a preceding successful result.
printf '{"complete":false,"phase":"initializing"}\n' > "$build/bootstrap.json"
rm -f "$build/compiler.path" "$build/manager.path" "$build/capability.txt" \
  "$build/completion-capability.txt" "$build/implementation-identity.txt" \
  "$build/manager-implementation-identity.txt"
phase=initializing
temporary=
finish() {
  status=$?
  trap - EXIT
  if [ -n "$temporary" ]; then rm -rf "$temporary"; fi
  if [ "$status" -ne 0 ]; then
    printf '{"complete":false,"phase":"%s","exit_code":%s}\n' "$phase" "$status" > "$build/bootstrap.json"
    printf 'Shared native bootstrap failed during %s; evidence: %s\n' "$phase" "$build" >&2
  fi
  exit "$status"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
verify_seed_only=false
case "$#:${1:-}" in
  0:) ;;
  1:--verify-seed-only) verify_seed_only=true ;;
  *) printf '%s\n' 'Usage: bootstrap-shared.sh [--verify-seed-only]; use MLF_SHARED_BOOTSTRAP_DIR.' >&2; exit 2 ;;
esac
control_only=false
case "${MLF_SHARED_BOOTSTRAP_CONTROL_ONLY:-0}" in
  0) ;;
  1) control_only=true ;;
  *) printf '%s\n' 'MLF_SHARED_BOOTSTRAP_CONTROL_ONLY must be 0 or 1.' >&2; exit 2 ;;
esac
compiler=${MLF_COMPILER:?verified released compiler required}
manager=${MLF_PACKAGE_MANAGER:?matching released package manager required}
compiler=$(command -v "$compiler")
manager=$(command -v "$manager")
test -x "$compiler" && test -x "$manager"
phase=verify-seed
command -v shasum >/dev/null
command -v jq >/dev/null
sha256() { shasum -a 256 "$1" | awk '{print $1}'; }
seed_error() { printf 'Unverified seed input: %s\n' "$*" >&2; exit 2; }
record_seed_file() {
  test -f "$1" && test ! -L "$1" || seed_error "expected a regular, non-symlink file: $1"
  shasum -a 256 "$1" >> "$build/seed-inputs.before.sha256"
}
native_executable() {
  test -f "$1" && test -x "$1" && test ! -L "$1" || return 1
  magic=$(od -An -tx1 -N4 "$1" | tr -d ' \n')
  case "$magic" in
    7f454c46|feedface|cefaedfe|feedfacf|cffaedfe|cafebabe|bebafeca|cafebabf|bfbafeca) return 0 ;;
    *) return 1 ;;
  esac
}
control_fixture() {
  test "$control_only" = true &&
    test "$(head -n 1 "$1")" = '#!/bin/sh' &&
    test "$(sed -n '2p' "$1")" = '# MLF bootstrap control fixture (not a native tool).'
}
seed_tool() (
  role=$1
  command_path=$(CDPATH= cd -P -- "$(dirname -- "$2")" && pwd)/$(basename -- "$2")
  record_seed_file "$command_path"
  command_hash=$(sha256 "$command_path")
  actual=$command_path
  kind=native-executable
  bundle=
  # Exact audited tools/release/launcher.sh bytes from the official 0.3 bundle.
  # Do not infer exec targets from arbitrary shell text or execute unknown scripts.
  if [ "$command_hash" = f3097897e94de4693a730752156ebf04e1d551621bb2efa95bf2afe33b844abd ]; then
    test "$(basename -- "$command_path")" = "$role" &&
      test "$(basename -- "$(dirname -- "$command_path")")" = bin ||
      seed_error 'official launcher must be at bundle/bin/'"$role"
    bundle=$(dirname -- "$(dirname -- "$command_path")")
    actual="$bundle/libexec/$role"
    kind=official-bundle-launcher
    record_seed_file "$actual"
  elif ! native_executable "$actual"; then
    control_fixture "$actual" || seed_error "unsupported wrapper; supply the actual native $role executable: $command_path"
    kind=mock-control-fixture
  fi
  if ! native_executable "$actual"; then
    control_fixture "$actual" || seed_error "launcher target is not a native executable: $actual"
    kind=mock-control-fixture
  fi
  # Direct libexec paths are used by CI seed installation. Bind their bundle too.
  if [ -z "$bundle" ] && [ "$(basename -- "$actual")" = "$role" ] &&
      [ "$(basename -- "$(dirname -- "$actual")")" = libexec ]; then
    bundle=$(dirname -- "$(dirname -- "$actual")")
  fi
  # Native magic proves file format, not compiler origin. The frozen bridge
  # accepts a released pair only through a complete release-bundle receipt.
  if [ -z "$bundle" ] && [ "$kind" != mock-control-fixture ]; then
    seed_error "standalone $role has no release-bundle provenance; use bundle/bin/$role or bundle/libexec/$role"
  fi
  bundle_json=null
  if [ -n "$bundle" ]; then
    for file in CHECKSUMS VERSION COMMIT release.json bin/emlf bin/mlfpkg libexec/emlf libexec/mlfpkg; do
      record_seed_file "$bundle/$file"
    done
    # Validate paths before giving the manifest to shasum. A copied bundle may
    # contain only its declared files, with no symlink-based hidden inputs.
    awk 'NF != 2 || length($1) != 64 || $1 ~ /[^0-9a-f]/ || $2 !~ /^\.\// ||
      $2 ~ /(^|\/)\.\.(\/|$)/ || $2 ~ /\\/ {exit 1}
      {if (seen[$2]++) exit 1; count++} END {if (!count) exit 1}' "$bundle/CHECKSUMS" ||
      seed_error "invalid release checksum manifest: $bundle/CHECKSUMS"
    test -z "$(find "$bundle" -type l -print)" || seed_error "release bundle contains symlinks: $bundle"
    (cd "$bundle"; find . -type f ! -path ./CHECKSUMS | LC_ALL=C sort) > "$build/seed-$role.bundle-files"
    awk '{print $2}' "$bundle/CHECKSUMS" | LC_ALL=C sort > "$build/seed-$role.declared-files"
    cmp "$build/seed-$role.bundle-files" "$build/seed-$role.declared-files" >/dev/null ||
      seed_error "release bundle file inventory differs from CHECKSUMS: $bundle"
    (cd "$bundle"; shasum -a 256 -c CHECKSUMS >/dev/null) || seed_error "release bundle checksum mismatch: $bundle"
    while IFS= read -r file; do record_seed_file "$bundle/${file#./}"; done < "$build/seed-$role.declared-files"
    jq -e --arg version "$(cat "$bundle/VERSION")" --arg commit "$(cat "$bundle/COMMIT")" \
      --arg compiler "$(sha256 "$bundle/libexec/emlf")" --arg manager "$(sha256 "$bundle/libexec/mlfpkg")" \
      '.schema_version == 1 and .version == $version and .commit == $commit and
       .compiler_sha256 == $compiler and .manager_sha256 == $manager and .test_implementation == "MLF"' \
      "$bundle/release.json" >/dev/null || seed_error "release metadata disagrees with native tool bytes: $bundle"
    bundle_json=$(jq -n --arg path "$bundle" --arg checksums "$(sha256 "$bundle/CHECKSUMS")" \
      --arg metadata "$(sha256 "$bundle/release.json")" '{path:$path,checksums_sha256:$checksums,release_json_sha256:$metadata}')
  fi
  jq -n --arg kind "$kind" --arg path "$command_path" --arg hash "$command_hash" \
    --arg actual "$actual" --arg actual_hash "$(sha256 "$actual")" --argjson bundle "$bundle_json" \
    '{kind:$kind,command:{path:$path,sha256:$hash},actual_executable:{path:$actual,sha256:$actual_hash},bundle:$bundle}'
)
: > "$build/seed-inputs.before.sha256"
seed_tool emlf "$compiler" > "$build/seed-compiler.json"
seed_tool mlfpkg "$manager" > "$build/seed-manager.json"
if [ "$control_only" = false ]; then
  jq -e -s '.[0].bundle != null and .[1].bundle != null and
    .[0].bundle == .[1].bundle' "$build/seed-compiler.json" "$build/seed-manager.json" >/dev/null ||
    seed_error 'compiler and manager must belong to the same verified release bundle'
fi
LC_ALL=C sort -u "$build/seed-inputs.before.sha256" > "$build/seed-inputs.sorted.sha256"
mv "$build/seed-inputs.sorted.sha256" "$build/seed-inputs.before.sha256"
jq -n --argjson control "$control_only" --slurpfile compiler "$build/seed-compiler.json" \
  --slurpfile manager "$build/seed-manager.json" --arg inputs "$(sha256 "$build/seed-inputs.before.sha256")" \
  '{format:1,control_only:$control,compiler:$compiler[0],manager:$manager[0],inputs_sha256:$inputs}' > "$build/seed-tools.json"
seed_identity=$("$compiler" --implementation-identity 2>/dev/null) || seed_identity=
if [ "$seed_identity" = 'MLF/shared-haskell-v1 GHC' ]; then
  printf '%s\n' 'The frozen native bootstrap requires native MLF seed tools; a GHC-produced compiler belongs to direct-host qualification.' >&2
  exit 2
fi
if [ "$verify_seed_only" = true ]; then
  jq -n --argjson control "$control_only" --arg inputs "$(sha256 "$build/seed-inputs.before.sha256")" \
    '{complete:false,phase:"seed-verified-only",control_only:$control,seed_inputs_sha256:$inputs}' > "$build/bootstrap.json"
  printf 'Seed input provenance verified; no bootstrap was run: %s\n' "$build/seed-tools.json"
  exit 0
fi
mkdir -p "$build/forbidden-tools"
for tool in ghc ghc-pkg runghc runhaskell cabal python python3; do
  cat > "$build/forbidden-tools/$tool" <<'FORBIDDEN'
#!/bin/sh
printf 'Forbidden native bootstrap dependency: %s\n' "$0" >&2
exit 97
FORBIDDEN
  chmod 755 "$build/forbidden-tools/$tool"
done
PATH="$build/forbidden-tools:$PATH"
export PATH
case "$(uname -s)" in Linux) ulimit -s unlimited ;; esac
GC_FREE_SPACE_DIVISOR=${GC_FREE_SPACE_DIVISOR:-8}
export GC_FREE_SPACE_DIVISOR
# Record actual paths and raw bytes. This is a receipt, never a rewritten input.
record_sources() {
  {
    jq -er '.modules[].path' "$root/shared-sources.json"
    find libraries -name mlf-package.json -type f
    find runtime -type f \( -name '*.c' -o -name '*.h' \)
    printf '%s\n' VERSION shared-sources.json mlf-package.json scripts/bootstrap-shared.sh
  } | LC_ALL=C sort -u | while IFS= read -r file; do
    test -f "$root/$file"
    shasum -a 256 "$root/$file"
  done
}
phase=verify-inputs
record_sources > "$build/shared-inputs.before.sha256"
jq '{source_syntax,frontend_semantics,builtin_interface,primitive_abi}' shared-sources.json > "$build/source-contract.json"
seed_compiler_hash=$(sha256 "$compiler")
seed_manager_hash=$(sha256 "$manager")
frozen="$root/bootstrap/shared-haskell-v1-bridge"
(cd "$frozen"; shasum -a 256 -c source.tar.gz.sha256)
identity=$(awk '{print $1}' "$frozen/source.tar.gz.sha256")
source="$build/bridge-source-$identity"
if [ ! -d "$source" ]; then
  temporary=$(mktemp -d "$build/bridge-source.XXXXXX")
  tar -xzf "$frozen/source.tar.gz" -C "$temporary"
  (cd "$temporary"; shasum -a 256 -c bridge-inputs.sha256 >/dev/null)
  mv "$temporary" "$source"
  temporary=
fi
(cd "$source"; shasum -a 256 -c bridge-inputs.sha256 >/dev/null)
phase=frozen-legacy-bridge
# The bundled script and all its inputs remain legacy syntax. Its stage-1
# ProcessHost shim is isolated from both the native bridge and final sources.
MLF_COMPILER="$compiler" MLF_PACKAGE_MANAGER="$manager" \
  MLF_ASYNC_BOOTSTRAP_DIR="$build/bridge" "$source/scripts/bootstrap-async.sh"
bridge="$build/bridge/stage2"
bridge_manager=$(cat "$build/bridge/manager.path")
"$bridge" --implementation-identity > "$build/bridge-identity.txt"
test "$(cat "$build/bridge-identity.txt")" = 'MLF/shared-haskell-v1 native-MLF'
phase=current-shared-source
# One invocation preserves the genuine aggregate report and both tool rows.
# Bootstrap deliberately precedes lock qualification; callers subsequently
# validate the regenerated committed lock with the new compiler and manager.
set -- --manifest "$root/mlf-package.json" --compiler "$bridge" \
  --runtime "$root/runtime/mlf_runtime.c" --timeout 21600 --jobs 1 \
  --build-dir "$build/native" --cache-dir "$build/native-cache"
if [ -n "${MLF_GC_PREFIX:-}" ]; then set -- "$@" --gc-prefix "$MLF_GC_PREFIX"; fi
if [ -n "${CC:-}" ]; then set -- "$@" --clang "$CC"; fi
"$bridge_manager" "$@" build --target emlf --target mlfpkg
jq -e '.complete == true and .implementation == "MLF" and
  ([.builds[] | select(.kind | startswith("executable mlf-compiler:")) | .kind] | sort) ==
  ["executable mlf-compiler:emlf","executable mlf-compiler:mlfpkg"]' "$build/native/build-report.json" >/dev/null
cp "$bridge" "$build/stage1.new"
mv "$build/stage1.new" "$build/stage1"
cp "$build/native/bin/emlf" "$build/stage2.new"
mv "$build/stage2.new" "$build/stage2"
"${CC:-clang}" -O2 -std=c11 -Wall -Wextra -Werror "$root/runtime/mlf_build_runner.c" -o "$build/native/bin/mlf-build-runner.new"
test "$("$build/native/bin/mlf-build-runner.new" --protocol-version)" = 1
mv "$build/native/bin/mlf-build-runner.new" "$build/native/bin/mlf-build-runner"
phase=native-capabilities
"$build/native/bin/mlfpkg" --implementation-identity > "$build/manager-implementation-identity.txt"
test "$(cat "$build/manager-implementation-identity.txt")" = 'MLF/shared-haskell-v1 native-MLF'
"$build/stage2" --implementation-identity > "$build/implementation-identity.txt"
test "$(cat "$build/implementation-identity.txt")" = 'MLF/shared-haskell-v1 native-MLF'
"$build/stage2" --run --expr 'do { reply <- processSupervisor "MLF-PROCESS-1\0version\0"; printInt (if eqString reply ("0\0" ++ "1\0") then 1 else 0) }' > "$build/capability.txt"
test "$(cat "$build/capability.txt")" = 1
"$build/stage2" --run --expr 'do { scope <- asyncScopeNew 1 1; asyncNewCompletion scope (\cell -> do { code <- asyncResolveCompletion cell 41; asyncReadCompletion cell printInt (printInt 0) }) (printInt 0); asyncScopeClose scope }' > "$build/completion-capability.txt"
test "$(cat "$build/completion-capability.txt")" = 41
phase=verify-receipts
record_sources > "$build/shared-inputs.after.sha256"
cmp "$build/shared-inputs.before.sha256" "$build/shared-inputs.after.sha256"
(cd "$source"; shasum -a 256 -c bridge-inputs.sha256 >/dev/null)
(cd "$frozen"; shasum -a 256 -c source.tar.gz.sha256 >/dev/null)
test "$(sha256 "$frozen/source.tar.gz")" = "$identity"
test "$(sha256 "$compiler")" = "$seed_compiler_hash"
test "$(sha256 "$manager")" = "$seed_manager_hash"
(cd /; shasum -a 256 -c "$build/seed-inputs.before.sha256" >/dev/null)
source_identity=$(sha256 "$build/shared-inputs.before.sha256")
printf '%s\n' "$source_identity" > "$build/source-identity.txt"
printf '%s\n' "$identity" > "$build/bridge-source-identity.txt"
shasum -a 256 "$build/stage1" "$build/stage2" > "$build/compilers.sha256"
shasum -a 256 "$build/native/bin/mlfpkg" "$build/native/bin/mlf-build-runner" > "$build/manager.sha256"
jq -n --slurpfile contract "$build/source-contract.json" --slurpfile seeds "$build/seed-tools.json" \
  --argjson control "$control_only" --arg seed_inputs "$(sha256 "$build/seed-inputs.before.sha256")" \
  --arg sources "$source_identity" --arg archive "$identity" \
  --arg seed_compiler "$seed_compiler_hash" --arg seed_manager "$seed_manager_hash" \
  --arg seed_compiler_path "$compiler" --arg seed_manager_path "$manager" \
  --arg bridge_compiler "$(sha256 "$bridge")" --arg bridge_manager "$(sha256 "$bridge_manager")" \
  --arg compiler "$(sha256 "$build/stage2")" --arg manager "$(sha256 "$build/native/bin/mlfpkg")" \
  --arg runner "$(sha256 "$build/native/bin/mlf-build-runner")" \
  --arg report "$(sha256 "$build/native/build-report.json")" \
  '{complete:true,route:(if $control then "mock-control/frozen-legacy-bridge/shared-source-native" else "released-seed/frozen-legacy-bridge/shared-source-native" end),
    control_only:$control,seed_tools:$seeds[0],seed_inputs_sha256:$seed_inputs,
    fixed_point_qualified:false,contract:$contract[0],sources_sha256:$sources,
    bridge_archive_sha256:$archive,seed_compiler_sha256:$seed_compiler,seed_manager_sha256:$seed_manager,
    seed_compiler_path:$seed_compiler_path,seed_manager_path:$seed_manager_path,
    bridge_compiler_sha256:$bridge_compiler,bridge_manager_sha256:$bridge_manager,
    compiler_sha256:$compiler,manager_sha256:$manager,build_runner_sha256:$runner,
    build_runner_protocol:1,build_report_sha256:$report,process_capability:true,typed_completion_capability:true}' \
    > "$build/bootstrap.json.new"
mv "$build/bootstrap.json.new" "$build/bootstrap.json"
# Publish tool pointers only after all checks. The legacy stage2/manager.path
# locations remain compatible with existing async and release consumers.
printf '%s\n' "$build/stage2" > "$build/compiler.path"
printf '%s\n' "$build/native/bin/mlfpkg" > "$build/manager.path"
printf '%s\n' "$build/stage2"
