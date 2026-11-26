#!/usr/bin/env python3
"""Apply the original benchmark transition and the single exact IntSet successor."""
from pathlib import Path
import hashlib
import os
import stat
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SUCCESSOR_PATH = 'tools/performance/artifact-binary/phase2_source_successor.py'
SUCCESSOR_SHA = '72041ef0f3ea9c84d5f7ff100f721c326ecbbc86c1b705bf2c45f11cb19f9f16'


def _load():
    path = ROOT / SUCCESSOR_PATH
    bound = 65536
    opened = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(opened, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= bound:
            raise ValueError('bounded Phase 2 source successor implementation')
        raw = stream.read(bound + 1)
    if len(raw) != info.st_size or hashlib.sha256(raw).hexdigest() != SUCCESSOR_SHA:
        raise ValueError('exact Phase 2 source successor implementation')
    module = ModuleType('_mlf_phase2_source_successor')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


successor = _load()
foundation = successor.pinned_module(
    ROOT, 'tools/performance/artifact-binary/foundation_phase2_source.py',
    'cb0ee3ae6abcff650f1d9042549e26e87f1a0f4e1594e37f90da0c697dcb0ff1',
)
successor.qualified = foundation.qualified


def stock_transition(root, opened):
    stock, (before, history, live_types, old_types, std, source_map) = successor.benchmark_inputs(root, opened)
    contract = opened.contract
    reviewed_pr55 = '08d7d608c13e89cabad0c81bc494072dafc7c86a'
    prior_types = opened.git.run('cat-file', 'blob', reviewed_pr55 + ':' + stock.TYPES)
    prior_pin = successor.strict_json(before)['pinned_sha256'][stock.TYPES]
    live_pin = contract.value['current_files'][stock.TYPES]
    successor.require(successor.sha(prior_types) == prior_pin and successor.sha(live_types) == live_pin,
                      'exact Types inputs before and after byte equality')

    class ReviewedTypesContract:
        value = {**contract.value, 'current_files': {**contract.value['current_files'], stock.TYPES: prior_pin}}

        def restore_path(self, raw, path):
            if path == stock.TYPES:
                successor.require(raw == prior_types, 'exact pre-optimization Types bytes')
                raw = live_types
            return contract.restore_path(raw, path)

    return stock, (before, history, prior_types, old_types, std, source_map), ReviewedTypesContract(), live_pin


def validate_new_benchmark(root, opened, *, new_manifest=None, live_intset=None):
    stock, inputs, reviewed, live_pin = stock_transition(root, opened)
    stock.validate_bridge(*inputs, reviewed)
    intset = successor.read(root, successor.INTSET) if live_intset is None else live_intset
    old_intset = successor.parse_intset(opened.git, intset)
    successor.require(opened.contract.restore_path(intset, successor.INTSET) == old_intset,
                      'actual stock historical IntSet source bytes')
    raw = successor.read(root, successor.BENCHMARK) if new_manifest is None else new_manifest
    current = successor.strict_json(raw)
    pins = current.get('pinned_sha256') if isinstance(current, dict) else None
    successor.require(isinstance(pins, dict) and pins.get(stock.TYPES) == live_pin,
                      'exact byte-equality Types benchmark pin')
    pins[stock.TYPES] = reviewed.value['current_files'][stock.TYPES]
    successor.validate_intset_manifest(successor.json_bytes(current), inputs[0], inputs[1], intset, opened.git)


def validate():
    with successor.qualified(ROOT) as opened:
        validate_new_benchmark(ROOT, opened)


if __name__ == '__main__':
    validate()
    print('Benchmark source transition passed: original history and exact Phase 2 IntSet input.')
