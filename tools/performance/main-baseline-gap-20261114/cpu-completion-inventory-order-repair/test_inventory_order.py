"""Narrow source-order regression. No archived module entry point is run.

Only preserved_shape is AST-extracted; its historical dependency calls are
replaced with explicit data-only fixtures. All filesystem tests use a fresh
temporary tree. No compiler, loader, locks, admission or activation is used.
"""
from pathlib import Path
import ast
import hashlib
import json
import os
import stat
import tempfile
import types

HERE = Path(__file__).resolve().parent
OLD = HERE / 'original_shape.py'
NEW = HERE / 'repaired_shape.py'
results = []

def check(value, label):
    if not value:
        raise AssertionError(label)
    results.append({'name': label, 'pass': True})

def rejects(fn, label):
    try:
        fn()
    except RuntimeError:
        check(True, label)
    else:
        raise AssertionError('accepted: ' + label)

def require(value, message):
    if not value:
        raise RuntimeError(message)

old = OLD.read_bytes()
new = NEW.read_bytes()
before = b'sorted(names)=='
after = b'sorted(names,key=Path)=='
check(old.count(before) == 1 and new == old.replace(before, after, 1),
      'exact one-expression delta, all other fixture bytes unchanged')
def fixture(source, root, expected, directories, calls):
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name == 'preserved_shape']
    check(len(nodes) == 1, 'one preserved_shape definition')
    bindings = {
        'Path': Path, 'R': root, 'os': os, 'stat': stat, 'require': require,
        'failure': lambda c: {'run_scope_files': 'files', 'run_scope_directories': 'dirs'},
        'verify_pin': lambda value: value,
        'load': lambda name: expected if name == 'files' else directories,
        'base': lambda c: (types.SimpleNamespace(verify_old_scope=lambda bc: calls.append(bc)), 'old-base'),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<extracted-only>', 'exec'), bindings)
    return bindings['preserved_shape']

with tempfile.TemporaryDirectory(prefix='mlf-inventory-order-') as tmp:
    root = Path(tmp)
    scope = root / 'main-cpu-attribution-run02'
    (scope / 'objects/Bootstrap/Graph').mkdir(parents=True)
    for rel in ['objects/Bootstrap/Graph.p_hi', 'objects/Bootstrap/Graph/IndexStore.p_hi',
                'objects/Bootstrap/Graph0.p_hi', 'plain']:
        (scope / rel).write_text(rel)
    files = sorted(p for p in scope.rglob('*') if p.is_file())
    expected = [{'path': str(p), 'bytes': p.stat().st_size,
                 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    directories = sorted(str(p.relative_to(scope)) for p in scope.rglob('*') if p.is_dir())
    calls = []
    old_fn = fixture(old, root, expected, directories, calls)
    new_fn = fixture(new, root, expected, directories, calls)
    rejects(lambda: old_fn({}), 'full v1 preserved_shape reproduces ordering failure')
    check(new_fn({}) is expected, 'full repaired function retains original rows and metadata')
    check(calls == ['old-base'], 'old-scope check still called, no bypass')
    extra = scope / 'extra'
    extra.write_text('x')
    rejects(lambda: new_fn({}), 'unexpected filesystem file rejected')
    extra.unlink()
    victim = files[-1]
    original = victim.read_bytes()
    victim.unlink()
    rejects(lambda: new_fn({}), 'missing filesystem file rejected')
    victim.write_bytes(original)
    expected.append(dict(expected[-1]))
    rejects(lambda: new_fn({}), 'duplicate frozen record rejected')
    expected.pop()
    extra.mkdir()
    rejects(lambda: new_fn({}), 'extra directory rejected')
    extra.rmdir()
    extra.symlink_to(files[0])
    rejects(lambda: new_fn({}), 'symlink alias rejected')
    extra.unlink()
    os.link(files[0], extra)
    rejects(lambda: new_fn({}), 'hardlink alias rejected')
    extra.unlink()
    check(new_fn({}) is expected, 'restored synthetic tree accepted without old-row mutation')

report = {'schema': 'mlf-completion-inventory-order-public-fixture-v1',
          'complete': True, 'narrow_source_checks_passed': True,
          'full_source_gate_passed': False, 'execution_admitted': False,
          'compiler_loader_benchmark_runs': 0, 'original_DIAG_passed': False,
          'checks': results, 'count': len(results),
          'old_fixture_sha256': hashlib.sha256(old).hexdigest(),
          'candidate_fixture_sha256': hashlib.sha256(new).hexdigest()}
print(json.dumps(report, indent=2))
