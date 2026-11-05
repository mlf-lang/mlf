#!/usr/bin/env python3
"""Run the unchanged P1/P2 metadata refusal suites on their frozen dependencies.

This checks historical authentication, not current compiler semantics. The
current Int64 producer is qualified separately by run_integrated.py.
"""
from pathlib import Path
import importlib.util
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
REF = '3b56689320f29b45835d26915fb99a4218eec09e'
BASE = 'tools/performance/crate-optimizations/'


def frozen(path):
    return subprocess.check_output(['git', 'show', REF+':'+path], cwd=ROOT)


def main():
    p1 = json.loads(frozen(BASE+'p1/oracle-manifest.json'))
    p2 = json.loads(frozen(BASE+'p2/native-compatibility-manifest.json'))
    p2oracle = json.loads(frozen(BASE+'p2/oracle-manifest.json'))
    p3 = json.loads(frozen(BASE+'p3/candidate.json'))
    paths = (set(p1['shared_dependency_pins']) |
             set(p1['collection_dependency_reaudit']['candidate_dependency_pins']) |
             set(p2['sources']) | set(p2['inputs']) |
             set(p2oracle['shared_dependency_pins']) | set(p3['source_sha256']))
    with tempfile.TemporaryDirectory() as directory:
        snapshot = Path(directory).resolve()
        for path in sorted(paths):
            if Path(path).is_absolute() or '..' in Path(path).parts:
                raise ValueError('unsafe frozen dependency path')
            target = snapshot/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(frozen(path))
        suite = unittest.TestSuite()
        for label, path in [('p1', BASE+'p1/test_oracle_authentication.py'),
                            ('p2', BASE+'p2/test_native_compatibility.py')]:
            original = ROOT/path
            if original.read_bytes() != frozen(path):
                raise ValueError('historical refusal suite changed: '+path)
            spec = importlib.util.spec_from_file_location('frozen_metadata_'+label, original)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.ROOT = snapshot
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        if suite.countTestCases() != 20:
            raise ValueError('complete eleven P1 and nine P2 historical refusal tests required')
        if not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful():
            raise SystemExit(1)


if __name__ == '__main__':
    main()
