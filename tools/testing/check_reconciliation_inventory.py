#!/usr/bin/env python3
"""Validate the supplemental main-reconciliation census, not runtime coverage."""
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / 'docs/main-reconciliation-inventory-20261023.json'
PARENT = 'bea6c93980e47946afc22ee99be0d571ed544489'
INCOMING = 'cb4c56c3744653c76648e609c06a71afad1ae2d4'
EXPECTED = {
    'tools/release/async-change-scope.py': ('added', 'selection-helper', '.github/workflows/ci.yml'),
    'tools/release/test-async-change-scope.py': ('added', 'policy-fault-controls', 'tools/release/check.sh'),
    '.github/workflows/ci.yml': ('changed', 'workflow-dispatch', 'tools/release/test-ci-policy.mjs'),
    'tools/release/check.sh': ('changed', 'metadata-dispatch', '.github/workflows/ci.yml'),
    'tools/release/test-ci-policy.mjs': ('changed', 'policy-fault-controls', 'tools/release/check.sh'),
    'tools/testing/check_reconciliation_inventory.py': ('added', 'static-provenance-audit', 'docs/main-reconciliation-20261023.md'),
}

def sha(data):
    return hashlib.sha256(data).hexdigest()

# The dated census describes this historical tree, not all future descendants.
SNAPSHOT = '4d732f31982ebe18124511f2ca4cb412770d6bd6'
RECORD_SHA256 = '5cfacbd32eb87eaf057d6c6ea65b5a1bc21ba727990e0dccdd210741f6c2fa19'
FOLLOW_ON = {
    # Explicit PR async opt-in policy supersedes the frozen diff-scope selector.
    'tools/release/async-change-scope.py': 'python3 tools/release/test-async-change-scope.py',
    'tools/release/test-async-change-scope.py': 'python3 tools/release/test-async-change-scope.py',
    '.github/workflows/ci.yml': 'node tools/release/test-ci-policy.mjs',
    'tools/release/check.sh': 'bash -n tools/release/check.sh; run its maintained controls',
    'tools/release/test-ci-policy.mjs': 'node tools/release/test-ci-policy.mjs',
    'tools/testing/check_reconciliation_inventory.py': 'python3 tools/testing/test_reconciliation_inventory.py',
    'tests/testing-migration-ledger.json': 'python3 tools/testing/migration_inventory.py',
    'mlf.lock': 'qualified mlfpkg --locked plan; python3 tools/testing/check_manifest_snapshot.py',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_bytes(revision, path):
    return subprocess.check_output(['git', 'show', revision + ':' + path], cwd=ROOT)


def validate(root=ROOT, record=None):
    raw = (root / RECORD.relative_to(ROOT)).read_bytes() if record is None else record
    require(sha(raw) == RECORD_SHA256, 'dated census changed')
    value = json.loads(raw)
    require(value['schema_version'] == 1 and value['kind'] == 'supplemental-source-inventory', 'census schema')
    require(value['first_parent'] == PARENT and value['incoming_main'] == INCOMING, 'historical commits changed')
    require(value['frozen_inventory_unchanged'] is True and
            value['runtime_migration_complete'] is False and
            value['selection_is_not_execution'] is True, 'historical claims changed')
    rows = value['entries']
    require(len(rows) == len(EXPECTED) and {r['path'] for r in rows} == set(EXPECTED), 'census membership')
    current = []

    def compare_current(path, historical):
        actual = (root / path).read_bytes()
        changed = actual != historical
        require(not changed or path in FOLLOW_ON, 'unreviewed current source change: ' + path)
        current.append({'path': path, 'historical_sha256': sha(historical),
                        'current_sha256': sha(actual), 'differs_from_historical': changed,
                        'current_validation_verified': False,
                        'required_follow_on_validation': FOLLOW_ON.get(path)})

    for row in rows:
        path = row['path']
        require((row['change'], row['role'], row['owner']) == EXPECTED[path], 'historical role changed')
        require(row['execution_verified'] is False and row['framework_integrated'] is False and
                row['remaining_phase'] == 'P6', 'historical status changed')
        historical = git_bytes(SNAPSHOT, path)
        require(sha(historical) == row['sha256'], 'historical source digest: ' + path)
        git_bytes(SNAPSHOT, row['owner'])  # owner must exist in historical snapshot
        if path != 'tools/testing/check_reconciliation_inventory.py':
            incoming = git_bytes(INCOMING, path)
            require(historical == incoming and sha(incoming) == row['incoming_sha256'], 'incoming source digest: ' + path)
        compare_current(path, historical)
    for path, expected in value['preserved_inputs'].items():
        prior = git_bytes(PARENT, path)
        historical = git_bytes(SNAPSHOT, path)
        require(historical == prior and sha(prior) == expected, 'historical preserved input: ' + path)
        compare_current(path, historical)
    return {'status': 'historical-supplemental-source-inventory-valid',
            'historical_snapshot': SNAPSHOT, 'tracked_entries': len(rows),
            'new_upstream_paths': 2, 'new_local_audits': 1, 'changed_upstream_owners': 3,
            'current_sources': current, 'current_validation_verified': False,
            'runtime_migration_complete': False}


def main():
    print(json.dumps(validate(), sort_keys=True))


if __name__ == '__main__':
    main()
