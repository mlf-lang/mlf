#!/usr/bin/env bash
# Install the same bottle closure in every hosted macOS qualification job.
set -euo pipefail
trap 'printf "Pinned macOS setup failed at line %s (status %s).\n" "$LINENO" "$?" >&2' ERR
cd -- "$(dirname -- "$0")/../.."
# This changes the runner's core tap and reinstalls its native dependencies.
# Keep it restricted to disposable GitHub-hosted runners, never developer Macs.
if [ "${GITHUB_ACTIONS:-}" != true ] || [ "${RUNNER_ENVIRONMENT:-}" != github-hosted ] ||
   [ "$(uname -s):$(uname -m)" != Darwin:arm64 ] || [[ "$(sw_vers -productVersion)" != 26.* ]]; then
  echo 'Pinned macOS setup requires a disposable GitHub-hosted macos-26 ARM64 runner.' >&2
  exit 1
fi
source .github/macos-dependencies.env
[[ "$MLF_HOMEBREW_CORE_COMMIT" =~ ^[0-9a-f]{40}$ ]]
export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_INSTALL_FROM_API=1
export HOMEBREW_NO_INSTALL_CLEANUP=1 HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK=1
export HOMEBREW_NO_ASK=1
# Persist the immutable resolution policy for later workflow steps as well.
for name in HOMEBREW_NO_AUTO_UPDATE HOMEBREW_NO_INSTALL_FROM_API HOMEBREW_NO_INSTALL_CLEANUP HOMEBREW_NO_INSTALLED_DEPENDENTS_CHECK HOMEBREW_NO_ASK; do
  printf '%s=1\n' "$name" >> "${GITHUB_ENV:?}"
done
prefix=$(brew --prefix)
test "$prefix" = /opt/homebrew || { printf 'Unexpected Homebrew prefix: %s\n' "$prefix" >&2; exit 1; }
core=$(brew --repository)/Library/Taps/homebrew/homebrew-core
output=$PWD/.mlf-build/macos-dependencies
checkout=$output/homebrew-core
mkdir -p "$output"
printf 'Preparing clean pinned Homebrew core at %s.\n' "$checkout"
if [ ! -e "$checkout/.git" ]; then
  mkdir -p "$checkout"
  test -z "$(find "$checkout" -mindepth 1 -maxdepth 1 -print -quit)"
  git init -q "$checkout"
  git -C "$checkout" remote add origin https://github.com/Homebrew/homebrew-core.git
fi
test -z "$(git -C "$checkout" status --porcelain)" || {
  echo 'Owned pinned Homebrew checkout has uncommitted changes.' >&2; exit 1;
}
case "$(git -C "$checkout" remote get-url origin)" in
  https://github.com/Homebrew/homebrew-core|https://github.com/Homebrew/homebrew-core.git) ;;
  *) echo 'Unexpected pinned Homebrew core remote.' >&2; exit 1 ;;
esac
git -C "$checkout" fetch --depth=1 https://github.com/Homebrew/homebrew-core.git "$MLF_HOMEBREW_CORE_COMMIT"
git -C "$checkout" checkout --detach "$MLF_HOMEBREW_CORE_COMMIT"
test "$(git -C "$checkout" rev-parse HEAD)" = "$MLF_HOMEBREW_CORE_COMMIT"
# Hosted images can contain a dirty core tap. Preserve it intact and select our
# clean checkout; never reset the image's changes or let them alter the pin.
mkdir -p "$(dirname "$core")"
if [ ! -L "$core" ] || [ "$(readlink "$core")" != "$checkout" ]; then
  if [ -e "$core" ] || [ -L "$core" ]; then
    backup=$(mktemp -d "${RUNNER_TEMP:?}/mlf-homebrew-core.XXXXXXXX")
    mv "$core" "$backup/homebrew-core"
    printf 'Preserved original Homebrew core at %s.\n' "$backup/homebrew-core"
  fi
  ln -s "$checkout" "$core"
fi
roots=(llvm gmp pkgconf bdw-gc)
# Explicit target flags force declared dependencies. Merely selecting formula,
# union and topological modes still permits installed receipt dependencies.
brew deps --os=tahoe --arch=arm64 --formula --union --topological "${roots[@]}" > "$output/dependencies.txt"
{ cat "$output/dependencies.txt"; printf '%s\n' "${roots[@]}"; } | awk 'NF && !seen[$0]++' > "$output/closure.txt"
closure=()
while IFS= read -r formula; do
  [[ "$formula" =~ ^[a-z0-9][a-z0-9@+_.-]*$ ]]
  closure+=("$formula")
  brew info --json=v2 --formula "$formula" > "$output/$formula.json"
  expected=$(jq -er '.formulae | if length == 1 then .[0] else error("ambiguous formula") end |
    select(.bottle.stable.files.arm64_tahoe.sha256 | test("^[0-9a-f]{64}$")) |
    .versions.stable + (if .revision > 0 then "_" + (.revision | tostring) else "" end)' "$output/$formula.json")
  # Reinstall even a matching version: bottle rebuilds can change bytes without
  # changing the version, and hosted images may contain an older bottle rebuild.
  if brew list --versions "$formula" >/dev/null 2>&1; then
    brew reinstall --force-bottle "$formula"
  else
    brew install --force-bottle "$formula"
  fi
  actual=$(cd -- "$(brew --prefix "$formula")" && pwd -P)
  test "$actual" = "$prefix/Cellar/$formula/$expected" || {
    printf 'Pinned dependency %s resolved to unexpected keg: %s\n' "$formula" "$actual" >&2
    exit 1
  }
done < "$output/closure.txt"
brew info --json=v2 --formula "${closure[@]}" > "$output/installed.json"
printf '%s\n' "$MLF_HOMEBREW_CORE_COMMIT" > "$output/homebrew-core-commit"
# The shared-candidate importer still checks every actual native input byte.
printf '%s/bin\n' "$(brew --prefix llvm)" >> "${GITHUB_PATH:?}"
printf 'MLF_GC_PREFIX=%s\n' "$(brew --prefix bdw-gc)" >> "$GITHUB_ENV"
printf 'Pinned macOS native dependencies installed from Homebrew core %s.\n' "$MLF_HOMEBREW_CORE_COMMIT"
