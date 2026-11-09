#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")/../.."
version=$(cat VERSION)
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
grep -Eq "^[[:space:]]*version = \"$version\";?[[:space:]]*$" libraries/mlf-foundation/Bootstrap/Version.hs
for manifest in mlf-package.json libraries/*/mlf-package.json tests/mlf-package.json; do
  test "$(jq -r .version "$manifest")" = "$version"
done
grep -q "^## $version " CHANGELOG.md
for script in tools/release/*.sh; do bash -n "$script"; done
test -s LICENSE
git diff --check
# Materialize only the closed, SHA-pinned squash source if absent. The
# historical identity/reachability checks themselves remain offline.
python3 -B tools/testing/prepare_history_refs.py
tools/release/check-benchmark-provenance.sh
tools/release/test-setup-macos.sh
tools/release/test-package-publishing.sh
tools/release/test-smoke-receipts.sh
tools/release/test-fetch-seed.sh
python3 tools/release/test-fetch-seed-artifact.py
tools/release/test-pr-gate.sh
tools/release/test-qualification-gate.sh
node tools/release/test-benchmark-gate.mjs
node tools/release/test-ci-policy.mjs
python3 tools/shared/test_provenance.py
python3 -B tools/shared/test_generated_string_pool.py
python3 -B tools/shared/test_prepared_verification.py
python3 tools/performance/a1-private-index/test_platform.py
python3 -B tools/performance/a1-private-index/test_current.py
python3 -B tools/performance/c4-local-transaction/test_controls.py
python3 -B tools/performance/patricia/test_historical_metadata.py
python3 tools/performance/fingerprint-fusion/test_controls.py
python3 tools/shared/test_perf_inference.py
python3 tools/shared/test_io_action_sharing_controls.py
python3 tools/shared/test_framework_controls.py
python3 tools/shared/test_framework_policy.py
python3 tools/shared/test_source_field_layout_controls.py
python3 tools/shared/test_parameter_field_graph.py --self-test
python3 tools/shared/test_resource_watchdog.py
python3 tools/shared/test_resource_watchdog_output.py
python3 tools/shared/test_guest_framework_controls.py
python3 tools/shared/test_guest_state_laws_controls.py
node tools/release/test-release-tag.mjs
tools/release/test-shared-candidate.sh
tools/release/test-unit-evidence.sh
python3 tools/release/test-tuple-list-qualification.py
tools/release/test-qualification-jobs.sh
tools/release/test-source-smoke-diagnostics.sh
tools/release/test-pr-smoke-cli-watchdog.sh
tools/release/test-async-bootstrap.sh
tools/release/test-shared-bootstrap-dispatch.sh
tools/release/test-shared-bootstrap-orchestration.sh
tools/release/test-direct-source-smoke.sh
bash tools/release/test-timed-async-bootstrap.sh
python3 tools/release/test-async-change-scope.py
python3 tools/testing/test_manifest_snapshot.py
python3 tools/testing/check_manifest_snapshot.py
python3 tools/testing/test_history_refs.py
python3 tools/testing/test_composed_history_refs.py
python3 -B tools/testing/test_prepare_pr43_history.py
python3 tools/testing/check_tuple_list_migration.py
python3 tools/testing/test_tuple_list_migration.py
python3 tools/testing/test_migration_inventory.py
python3 tools/testing/check_core_leaf_migration.py
python3 tools/testing/check_reconciliation_inventory.py
python3 tools/testing/test_reconciliation_inventory.py
python3 tools/testing/test_history_workflows.py
python3 tools/testing/test_framework_recovery.py
printf 'Release metadata and shell syntax passed for %s.\n' "$version"
