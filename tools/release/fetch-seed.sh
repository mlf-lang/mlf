#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
# Version and both executable hashes are reviewed in source control.
# shellcheck source=.github/seed.env
source "$root/.github/seed.env"
destination=${1:?seed destination required}
mkdir -p "$destination"
destination=$(cd "$destination" && pwd)
archive="mlf-$MLF_SEED_VERSION-macos-arm64.tar.gz"
gh release download "v$MLF_SEED_VERSION" --repo mlf-lang/mlf --pattern "$archive" --pattern SHA256SUMS --dir "$destination"
(cd "$destination" && shasum -a 256 -c SHA256SUMS)
tar -xzf "$destination/$archive" -C "$destination"
package="$destination/mlf-$MLF_SEED_VERSION-macos-arm64"
test "$(shasum -a 256 "$package/libexec/emlf" | awk '{print $1}')" = "$MLF_SEED_COMPILER_SHA256"
test "$(shasum -a 256 "$package/libexec/mlfpkg" | awk '{print $1}')" = "$MLF_SEED_MANAGER_SHA256"
if [ -n "${GITHUB_ENV:-}" ]; then
  printf 'MLF_COMPILER=%s\nMLF_PACKAGE_MANAGER=%s\n' "$package/libexec/emlf" "$package/libexec/mlfpkg" >> "$GITHUB_ENV"
fi
printf '%s\n' "$package"
