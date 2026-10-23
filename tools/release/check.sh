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
tools/release/test-setup-macos.sh
tools/release/test-package-publishing.sh
tools/release/test-smoke-receipts.sh
tools/release/test-fetch-seed.sh
tools/release/test-pr-gate.sh
tools/release/test-qualification-gate.sh
node tools/release/test-benchmark-gate.mjs
node tools/release/test-ci-policy.mjs
node tools/release/test-release-tag.mjs
tools/release/test-shared-candidate.sh
tools/release/test-unit-evidence.sh
tools/release/test-qualification-jobs.sh
tools/release/test-source-smoke-diagnostics.sh
tools/release/test-pr-smoke-cli-watchdog.sh
tools/release/test-async-bootstrap.sh
bash tools/release/test-timed-async-bootstrap.sh
python3 tools/release/test-async-change-scope.py
printf 'Release metadata and shell syntax passed for %s.\n' "$version"
