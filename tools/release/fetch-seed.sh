#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
# Version and both executable hashes are reviewed in source control. PR CI can
# select its newer crate-capable seed without changing historical release builds.
test "$#" -le 2 || { printf '%s\n' 'Expected destination and optional seed pins.' >&2; exit 2; }
MLF_SEED_ARCHIVE_SHA256=
# shellcheck source=.github/seed.env
source "${2:-$root/.github/seed.env}"
destination=${1:?seed destination required}
mkdir -p "$destination"
destination=$(cd "$destination" && pwd)
archive="mlf-$MLF_SEED_VERSION-macos-arm64.tar.gz"
gh release download "v$MLF_SEED_VERSION" --repo mlf-lang/mlf --pattern "$archive" --pattern SHA256SUMS --dir "$destination"
# A release can also publish supplementary validation archives. Verify the
# archive downloaded here; both native executable hashes are checked below.
awk -v archive="$archive" '$2 == archive { print; found++ } END { if (found != 1) exit 1 }' \
  "$destination/SHA256SUMS" > "$destination/archive.sha256"
(cd "$destination" && shasum -a 256 -c archive.sha256)
if [ -n "$MLF_SEED_ARCHIVE_SHA256" ]; then
  test "$(shasum -a 256 "$destination/$archive" | awk '{print $1}')" = "$MLF_SEED_ARCHIVE_SHA256"
fi
tar -xzf "$destination/$archive" -C "$destination"
package="$destination/mlf-$MLF_SEED_VERSION-macos-arm64"
test "$(shasum -a 256 "$package/libexec/emlf" | awk '{print $1}')" = "$MLF_SEED_COMPILER_SHA256"
test "$(shasum -a 256 "$package/libexec/mlfpkg" | awk '{print $1}')" = "$MLF_SEED_MANAGER_SHA256"
if [ -n "${GITHUB_ENV:-}" ]; then
  printf 'MLF_COMPILER=%s\nMLF_PACKAGE_MANAGER=%s\n' "$package/libexec/emlf" "$package/libexec/mlfpkg" >> "$GITHUB_ENV"
fi
printf '%s\n' "$package"
