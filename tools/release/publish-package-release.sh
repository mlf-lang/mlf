#!/usr/bin/env bash
# Publish only a complete prepared upload set; never replace an existing release.
set -euo pipefail
test "$#" -eq 4 || { echo 'Usage: publish-package-release.sh OUTPUT REPOSITORY TAG SOURCE_COMMIT' >&2; exit 2; }
output=$1 repository=$2 tag=$3 source=$4
[[ "$repository" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
[[ "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._/+\-]*$ && "$tag" != latest ]] || exit 2
[[ "$source" =~ ^[a-f0-9]{40}$ ]] || exit 2
cd -- "$output"
jq -e --arg repo "$repository" --arg tag "$tag" '
  (.dependencies | length) == 1 and
  (.dependencies[] | .github.repository == $repo and .github.tag == $tag and
    (.github.asset | test("^[a-z][a-z0-9.-]*-[a-f0-9]{64}\\.mlfr$")) and
    (.sha256 | test("^[a-f0-9]{64}$")) and (.asset_sha256 | test("^[a-f0-9]{64}$")))' dependency.json >/dev/null
asset=$(jq -er '.dependencies[].github.asset' dependency.json)
expected=$(jq -er '.dependencies[].asset_sha256' dependency.json)
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }
test "$(sha256 "$asset" | awk '{print $1}')" = "$expected"
test "$(jq -j '.manifest' "$asset" | sha256 - | awk '{print $1}')" = "$(jq -er '.dependencies[].sha256' dependency.json)"
test "$(cat SHA256SUMS)" = "$expected  $asset"
test -s NOTES.md
encoded=$(jq -rn --arg ref "refs/tags/$tag" '$ref | @uri')
test "$(gh api "repos/$repository/commits/$encoded" --hostname github.com --jq .sha)" = "$source"
if gh release view "$tag" --repo "github.com/$repository" >/dev/null 2>&1; then
  echo 'Refusing to replace an existing release or its assets.' >&2
  exit 1
fi
# --verify-tag refuses accidental creation of a tag at the default branch.
# Assets are uploaded while draft, before immutable release publication.
gh release create "$tag" --repo "github.com/$repository" --verify-tag --draft --latest=false \
  --title "$tag" --notes-file NOTES.md "$asset" dependency.json SHA256SUMS
# Uploads can take time; a moved tag leaves the draft unpublished for inspection.
test "$(gh api "repos/$repository/commits/$encoded" --hostname github.com --jq .sha)" = "$source"
gh release edit "$tag" --repo "github.com/$repository" --draft=false --latest=false
