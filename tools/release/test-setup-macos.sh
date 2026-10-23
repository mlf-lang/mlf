#!/usr/bin/env bash
# Exercise the real setup script without touching Homebrew or using the network.
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
root=$PWD
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/template/tools/release" "$scratch/template/.github" "$scratch/bin"
cp tools/release/setup-macos.sh "$scratch/template/tools/release/"
cp .github/macos-dependencies.env "$scratch/template/.github/"
cat > "$scratch/bin/uname" <<'SH'
#!/usr/bin/env bash
case "$1" in -s) echo "${MOCK_OS:-Darwin}" ;; -m) echo "${MOCK_ARCH:-arm64}" ;; *) exit 89 ;; esac
SH
cat > "$scratch/bin/sw_vers" <<'SH'
#!/usr/bin/env bash
echo "${MOCK_VERSION:-26.6.2}"
SH
cat > "$scratch/bin/git" <<'SH'
#!/usr/bin/env bash
printf 'git %s\n' "$*" >> "$MOCK_ROOT/commands"
if [ "$1" = init ]; then mkdir -p "$3/.git"; exit; fi
[ "$1" = -C ]; shift 2
case "$1 $2" in
 'remote add') exit 0 ;;
 'remote get-url') echo "${MOCK_REMOTE:-https://github.com/Homebrew/homebrew-core.git}" ;;
 'status --porcelain') if [ "${MOCK_DIRTY:-0}" = 1 ]; then echo ' M Formula/x.rb'; fi ;;
 'fetch --depth=1') test "${MOCK_FETCH_FAIL:-0}" != 1 ;;
 'checkout --detach') test "${MOCK_CHECKOUT_FAIL:-0}" != 1 ;;
 'rev-parse HEAD') echo "${MOCK_COMMIT:-842dec212e8602f00b8601f5791dbad263e22dd8}" ;;
 *) exit 89 ;;
esac
SH
cat > "$scratch/bin/brew" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'brew %s\n' "$*" >> "$MOCK_ROOT/commands"
version() { case "$1" in llvm) echo 23.1.4 ;; zstd) echo 1.5.7_1 ;; *) echo 1.0 ;; esac; }
case "$1" in
 --prefix)
   if [ "$#" = 1 ]; then echo "${MOCK_PREFIX:-/opt/homebrew}"; else
     v=$(version "$2"); if [ "${MOCK_WRONG_KEG:-}" = "$2" ]; then v=99.0; fi
     p="$MOCK_ROOT/opt/homebrew/Cellar/$2/$v"; mkdir -p "$p"; echo "$p"
   fi ;;
 --repository) echo "$MOCK_ROOT/brew" ;;
 deps)
   test "$*" = 'deps --formula --union --topological llvm gmp pkgconf bdw-gc'
   printf '%s\n' zstd z3 "${MOCK_EXTRA_DEP:-zstd}" ;;
 info)
   test "${HOMEBREW_NO_AUTO_UPDATE:-}" = 1
   test "${HOMEBREW_NO_INSTALL_FROM_API:-}" = 1
   test "${HOMEBREW_NO_INSTALL_CLEANUP:-}" = 1
   test "${HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK:-}" = 1
   name=${4}; v=$(version "$name"); revision=0
   if [[ "$v" = *_* ]]; then revision=${v#*_}; v=${v%_*}; fi
   checksum=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
   if [ "${MOCK_MISSING_BOTTLE:-}" = "$name" ]; then checksum=; fi
   jq -n --arg name "$name" --arg version "$v" --arg sha "$checksum" --argjson revision "$revision" \
     '{formulae:[{name:$name,versions:{stable:$version},revision:$revision,bottle:{stable:{files:{arm64_tahoe:{sha256:$sha}}}}}]}' ;;
 list) [ "${MOCK_INSTALLED:-0}" = 1 ] ;;
 install|reinstall)
   test "$2" = --force-bottle
   test "${MOCK_INSTALL_FAIL:-}" != "$3"
   mkdir -p "$MOCK_ROOT/installed"
   printf 'pinned bottle\n' > "$MOCK_ROOT/installed/$3" ;;
 *) exit 89 ;;
esac
SH
# Only translate the simulated keg's physical path in the test shell. The
# unmodified production script still demands /opt/homebrew on a hosted Mac.
cat > "$scratch/shell-env" <<'SH'
pwd() {
  local value
  value=$(builtin pwd "$@")
  case "$value" in "$MOCK_ROOT"/opt/homebrew/*) printf '%s\n' "${value#"$MOCK_ROOT"}" ;; *) printf '%s\n' "$value" ;; esac
}
SH
chmod +x "$scratch/bin/"*
count=0
run_case() {
  local label=$1 expected=$2; shift 2
  count=$((count + 1))
  local repetitions=1
  if [ "${1:-}" = repeat ]; then repetitions=2; shift; fi
  local work="$scratch/case-$count"
  cp -R "$scratch/template" "$work"
  : > "$work/environment"; : > "$work/path"
  mkdir -p "$work/brew/Library/Taps/homebrew/homebrew-core"
  printf "preserve image changes\n" > "$work/brew/Library/Taps/homebrew/homebrew-core/image-marker"
  local status=0
  for ((attempt=1; attempt<=repetitions; attempt++)); do
  env PATH="$scratch/bin:$PATH" BASH_ENV="$scratch/shell-env" MOCK_ROOT="$work" \
    GITHUB_ACTIONS=true RUNNER_ENVIRONMENT=github-hosted RUNNER_TEMP="$work" GITHUB_ENV="$work/environment" GITHUB_PATH="$work/path" \
    "$@" bash "$work/tools/release/setup-macos.sh" >> "$work/output" 2>&1 || status=$?
  done
  if { [ "$expected" = pass ] && [ "$status" != 0 ]; } || { [ "$expected" = fail ] && [ "$status" = 0 ]; }; then
    cat "$work/output" >&2; printf 'FAIL %s (status %s)\n' "$label" "$status" >&2; exit 1
  fi
  if [ "$expected" = pass ]; then
    test "$(grep -Ec '^brew (reinstall|install) --force-bottle' "$work/commands")" = "$((6 * repetitions))"
    test "$(cat "$work/.mlf-build/macos-dependencies/closure.txt")" = "$(printf '%s\n' zstd z3 llvm gmp pkgconf bdw-gc)"
    test "$(grep -c '=1$' "$work/environment")" = "$((5 * repetitions))"
    test "$(readlink "$work/brew/Library/Taps/homebrew/homebrew-core")" = "$work/.mlf-build/macos-dependencies/homebrew-core"
    test "$(find "$work" -path "*/mlf-homebrew-core.*/homebrew-core/image-marker" | wc -l | tr -d " ")" = 1
    test "$(cat "$work"/mlf-homebrew-core.*/homebrew-core/image-marker)" = "preserve image changes"
    grep -q 'homebrew-core.git 842dec212e8602f00b8601f5791dbad263e22dd8$' "$work/commands"
  fi
  printf 'PASS macOS dependencies: %s\n' "$label"
}
run_case 'fresh bottle closure, revision suffix and dirty image tap preservation' pass
run_case 'repeated setup reuses owned tap and preserves the original once' pass repeat
run_case 'reinstall matching or newer hosted packages and bottle rebuilds' pass MOCK_INSTALLED=1
run_case 'developer machine rejected' fail GITHUB_ACTIONS=false
run_case 'self-hosted runner rejected' fail RUNNER_ENVIRONMENT=self-hosted
run_case 'Linux rejected' fail MOCK_OS=Linux
run_case 'Intel rejected' fail MOCK_ARCH=x86_64
run_case 'different macOS bottle platform rejected' fail MOCK_VERSION=27.0
run_case 'nonstandard prefix rejected' fail MOCK_PREFIX=/usr/local
run_case 'dirty owned formula checkout rejected' fail MOCK_DIRTY=1
run_case 'unexpected formula remote rejected' fail MOCK_REMOTE=https://example.invalid/core.git
run_case 'fetch failure stops installation' fail MOCK_FETCH_FAIL=1
run_case 'checkout failure stops installation' fail MOCK_CHECKOUT_FAIL=1
run_case 'wrong checked-out revision rejected' fail MOCK_COMMIT=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
run_case 'missing fixed bottle rejected' fail MOCK_MISSING_BOTTLE=llvm
run_case 'unsafe dependency name rejected' fail MOCK_EXTRA_DEP=../escape
run_case 'failed install is not reported as complete' fail MOCK_INSTALL_FAIL=llvm
run_case 'wrong active keg rejected' fail MOCK_WRONG_KEG=llvm
printf '%s pinned macOS dependency checks passed\n' "$count"
