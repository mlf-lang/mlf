#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."

# Preserve this entry point for release rehearsals and older callers.
if [ "${1:-}" = --metadata-only ]; then
  . tools/release/test-events.sh release-metadata
  release_begin release/metadata/version
  version=$(cat VERSION)
  [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
  grep -Eq "^[[:space:]]*version = \"$version\";?[[:space:]]*$" libraries/mlf-foundation/Bootstrap/Version.hs
  release_pass
  release_begin release/metadata/manifest-versions
  for manifest in mlf-package.json libraries/*/mlf-package.json tests/mlf-package.json; do
    test "$(jq -r .version "$manifest")" = "$version"
  done
  release_pass
  release_begin release/metadata/changelog
  grep -q "^## $version " CHANGELOG.md
  release_pass
  release_begin release/metadata/shell-syntax
  for script in tools/release/*.sh; do bash -n "$script"; done
  release_pass
  release_begin release/metadata/license
  test -s LICENSE
  release_pass
  release_begin release/metadata/diff
  python3 -B tools/release/check_diff.py
  release_pass
  exit
fi
if [ "$#" -ne 0 ]; then
  printf 'Usage: %s\n' "$0" >&2
  exit 2
fi

run() { python3 -B tools/testing/run.py "$@"; }
run release-metadata
run release-metadata-diff
run benchmark-provenance
run release-setup-macos
run release-package-publishing
run release-smoke-receipts
run release-fetch-seed
run release-seed-artifact
run release-pr-gate
run release-qualification-gate
run benchmark-gate-controls
run release-ci-policy
run release-native-ci-partition
run release-macos-toolchain-workflow
run release-shared-provenance
run python-shared-darwin-toolchain
run python-shared-darwin-toolchain --python-optimization
run release-generated-string-pool
run release-prepared-verification
run release-performance-a1-platform
run release-performance-local-transaction
run python-patricia-fingerprint-core
run release-performance-inference-controls
run release-io-action-controls
run release-framework-controls
run release-framework-policy
run release-source-field-controls
run release-parameter-field-controls
run release-watchdog-tests
run release-watchdog-output
run release-guest-framework-controls
run release-guest-state-controls
run release-tag-controls
run release-shared-candidate
run release-unit-evidence
run release-tuple-list-qualification
run release-qualification-jobs
run release-source-smoke-diagnostics
run release-pr-smoke-cli-watchdog
run release-async-bootstrap
run release-shared-bootstrap-dispatch
run release-shared-bootstrap-orchestration
run release-direct-source-smoke
run release-timed-async-bootstrap
run release-async-change-scope
run python-testing-manifest-snapshot
run release-manifest-snapshot
run release-core-registry-controls
printf 'Release metadata and shell syntax passed for %s.\n' "$(cat VERSION)"
