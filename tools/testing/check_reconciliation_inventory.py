#!/usr/bin/env python3
"""Validate the supplemental main-reconciliation census, not runtime coverage."""
import hashlib
import json
from history_refs import historical_bytes, checked_current
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

def main():
    value = json.loads(RECORD.read_text())
    assert value['schema_version'] == 1 and value['kind'] == 'supplemental-source-inventory'
    assert value['first_parent'] == PARENT and value['incoming_main'] == INCOMING
    assert value['frozen_inventory_unchanged'] is True
    assert value['runtime_migration_complete'] is False
    rows = value['entries']
    assert len(rows) == len(EXPECTED) and {r['path'] for r in rows} == set(EXPECTED)
    for row in rows:
        path = row['path']
        assert (row['change'], row['role'], row['owner']) == EXPECTED[path]
        assert row['execution_verified'] is False and row['framework_integrated'] is False
        assert row['remaining_phase'] == 'P6'
        assert checked_current(path, (ROOT / path).read_bytes(), row['sha256'])
        assert (ROOT / row['owner']).is_file()
        if path != 'tools/testing/check_reconciliation_inventory.py':
            frozen = historical_bytes(INCOMING, path)
            assert checked_current(path, (ROOT / path).read_bytes(), row['incoming_sha256']), path
            assert sha(frozen) == row['incoming_sha256']
    for path, expected in value['preserved_inputs'].items():
        actual = (ROOT / path).read_bytes()
        prior = historical_bytes(PARENT, path)
        assert actual == prior and sha(actual) == expected, path
    assert value['selection_is_not_execution'] is True
    print(json.dumps({'status':'supplemental-source-inventory-valid','tracked_entries':len(rows),
                      'new_upstream_paths':2,'new_local_audits':1,'changed_upstream_owners':3,
                      'runtime_migration_complete':False}, sort_keys=True))

if __name__ == '__main__':
    main()
