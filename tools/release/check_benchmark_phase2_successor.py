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


def validate():
    with successor.qualified(ROOT) as opened:
        successor.validate_new_benchmark(ROOT, opened)


if __name__ == '__main__':
    validate()
    print('Benchmark source transition passed: original history and exact Phase 2 IntSet input.')
