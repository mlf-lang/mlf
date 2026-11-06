#!/usr/bin/env python3
"""Verify the live benchmark input transition without rebasing old measurements."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[2]
HISTORY = 'benchmarks/history/artifact-binary-parent-manifest.json'
OLD_TYPES = 'benchmarks/history/artifact-binary-parent-Types.hs.txt'
TYPES = 'libraries/mlf-foundation/Bootstrap/Types.hs'
HISTORY_SHA = 'c5da11d57bbe021ec0e4f5b906929128df04542402c9bd01d77386658adff70f'
OLD_TYPES_SHA = '9eb67b3a3e7f3591f051a8627bb466209a3be39436d58f48db8efc89f936fbac'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('benchmark source transition: ' + message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def load_contract(root):
    path = root / 'tools/performance/artifact-binary/source_migration_adapter.py'
    spec = importlib.util.spec_from_file_location('benchmark_binary_source_adapter', path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    # This existing contract authenticates all 192 current source files, its
    # fixed metadata and historical chain. No benchmark hash grants that trust.
    return adapter.live_contract(root / 'tools/performance')


def validate_bridge(current_raw, historical_raw, current_types, historical_types, contract):
    require(sha(historical_raw) == HISTORY_SHA, 'exact historical manifest SHA')
    historical = strict_json(historical_raw)
    require(historical['pinned_sha256'][TYPES] == OLD_TYPES_SHA, 'historical Types pin')
    require(sha(historical_types) == OLD_TYPES_SHA, 'historical Types fixture SHA')
    projected = contract.restore_path(current_types, TYPES)
    require(projected == historical_types, 'exact historical Types reconstruction')
    # Only this declared source transition and its two evidence pins change.
    # Workloads, flags, other pins, and upstream provenance remain unchanged.
    expected = copy.deepcopy(historical)
    expected['pinned_sha256'][TYPES] = contract.value['current_files'][TYPES]
    expected['pinned_sha256'][HISTORY] = HISTORY_SHA
    expected['pinned_sha256'][OLD_TYPES] = OLD_TYPES_SHA
    canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(canonical(strict_json(current_raw)) == canonical(expected),
            'undeclared live manifest change')
    require(sha(current_types) == expected['pinned_sha256'][TYPES], 'current Types pin')


def validate(root=ROOT):
    contract = load_contract(root)
    validate_bridge((root / 'benchmarks/manifest.json').read_bytes(),
                    (root / HISTORY).read_bytes(), (root / TYPES).read_bytes(),
                    (root / OLD_TYPES).read_bytes(), contract)


if __name__ == '__main__':
    validate()
    print('Benchmark source transition passed: current inputs and exact historical evidence.')
