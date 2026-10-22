#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
version=$(cat VERSION)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
grep -Fxq "version = \"$version\"" libraries/mlf-foundation/Bootstrap/Version.emlf
for manifest in mlf-package.json libraries/*/mlf-package.json tests/mlf-package.json; do
  test "$(jq -r .version "$manifest")" = "$version"
done
grep -q "^## $version " CHANGELOG.md
for script in tools/release/*.sh; do bash -n "$script"; done
test -s LICENSE
git diff --check
tools/release/check-benchmark-provenance.sh
printf 'Release metadata and shell syntax passed for %s.\n' "$version"
