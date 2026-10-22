#!/usr/bin/env bash
# Produce a reviewable, pinned upload set. This command never contacts GitHub.
set -euo pipefail
test "$#" -eq 4 || { echo 'Usage: prepare-package-release.sh BUNDLE REPOSITORY TAG OUTPUT' >&2; exit 2; }
bundle=$1 repository=$2 tag=$3 output=$4
manager=${MLF_PACKAGE_MANAGER:?select the updated native mlfpkg}
[[ "$repository" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || exit 2
[[ "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._/+\-]*$ && "$tag" != latest ]] || exit 2
test ! -e "$output" || { echo 'Use a new output directory.' >&2; exit 1; }
bundle=$(cd -- "$bundle" && pwd)
name=$(jq -er '.name' "$bundle/release.json")
version=$(jq -er '.version' "$bundle/release.json")
compiler=$(jq -er '.compiler_sha256' "$bundle/release.json")
[[ "$name" =~ ^[a-z][a-z0-9-]*$ && "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$compiler" =~ ^[a-f0-9]{64}$ ]] || exit 2
mkdir -p -- "$(dirname -- "$output")"
# mkdir without -p also refuses an existing symlink or concurrent publisher.
mkdir -- "$output"
output=$(cd -- "$output" && pwd)
asset="$name-$version-$compiler.mlfr"
packed=$("$manager" pack "$bundle" "$output/$asset")
sha256() { if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1"; else shasum -a 256 "$1"; fi; }
manifest_hash=$(sha256 "$bundle/release.json" | awk '{print $1}')
asset_hash=$(sha256 "$output/$asset" | awk '{print $1}')
test "$(jq -er '.sha256' <<< "$packed")" = "$manifest_hash"
test "$(jq -er '.asset_sha256' <<< "$packed")" = "$asset_hash"
jq -n --arg name "$name" --arg repository "$repository" --arg tag "$tag" --arg asset "$asset" \
  --arg manifest "$manifest_hash" --arg digest "$asset_hash" \
  '{dependencies:{($name):{github:{repository:$repository,tag:$tag,asset:$asset},sha256:$manifest,asset_sha256:$digest}}}' > "$output/dependency.json"
printf '%s  %s\n' "$asset_hash" "$asset" > "$output/SHA256SUMS"
{
  printf '# %s %s\n\nChecked library release.\n\nCompiler SHA-256: `%s`\n\n' "$name" "$version" "$compiler"
  printf 'Add this dependency to `mlf-package.json`, then run `mlfpkg lock`:\n\n```json\n'
  cat "$output/dependency.json"
  printf '```\n\nThe asset and manifest digests are both pinned. Requires an mlfpkg with GitHub distribution support.\n'
} > "$output/NOTES.md"
printf 'Prepared checked package release: %s\n' "$output"
