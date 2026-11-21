#!/usr/bin/env python3
"""Replay unchanged source-contract tests in fixed physical predecessor sources.

No compiler, generator, benchmark or native qualification is run. These are
historical regressions only; test_pr43_reconciliation checks current sources.
Run after the current-source suite exits to avoid overlapping archive copies.
"""
from pathlib import Path
import argparse
import ast
import json
import os
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
FRAMEWORK = ROOT / 'tools/testing'
sys.path.insert(0, str(FRAMEWORK))
import events

SOURCES = {
    'declid': ('4fd6730d35b6ecaf8e169ad228ac3c7a3ed56160',
               '1c60d3daca5162bd24658d295169f601593345ef',
               ('tools/performance/artifact-binary/test_declid_migration.py',)),
    'main': ('b4b472f7abfe837399e1051aa73e1af3c852d968',
             '04b563af3b8a9acb2938747d5d1f36c883f4d351',
             ('tools/performance/artifact-binary/test_query_graph_migration.py',
              'tools/performance/artifact-binary/test_ci_integration_migration.py',
              'tools/performance/crate-prelude/test_contract.py')),
}
# Select code and contract inputs, not unrelated papers/benchmark result files.
# The predecessor contracts still authenticate their entire owned inventories.
PATHS = ('libraries', 'bootstrap', 'host', 'runtime', 'tools', '.github',
         'shared-sources.json', 'mlf.lock', 'mlf-package.json', 'mlf-shared.cabal',
         'cabal.project', 'tests', 'testing', 'package')


def inventory(git, commit, script, prefix):
    """Read the plain TestCase declarations from the authenticated frozen source."""
    code = ast.parse(subprocess.check_output([*git, 'show', f'{commit}:{script}']))
    classes = [node for node in code.body if isinstance(node, ast.ClassDef)
               and any(isinstance(base, ast.Attribute) and base.attr == 'TestCase'
                       for base in node.bases)]
    ids = sorted(f'{prefix}{case.name}.{test.name}' for case in classes for test in case.body
                 if isinstance(test, ast.FunctionDef) and test.name.startswith('test'))
    if not ids:
        raise ValueError(f'missing frozen test inventory: {script}')
    return ids


def collect(path, expected):
    """Forward only observations from the exact child plan, retaining partial results."""
    with path.open(encoding='utf-8') as stream:
        first = stream.readline()
        if not first:
            return
        if json.loads(first) != {'plan': expected}:
            raise ValueError('frozen unittest plan differs from reviewed source')
        for line in stream:
            if not line.endswith('\n'):
                raise ValueError('truncated frozen unittest report')
            row = json.loads(line)
            if 'start' in row:
                events.start(row.pop('start'), **row)
            else:
                events.result(row.pop('id'), row.pop('status'), **row)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', choices=tuple(SOURCES))
    parser.add_argument('--framework-list', action='store_true')
    args = parser.parse_args()
    commit, expected_tree, scripts = SOURCES[args.source]
    git = ['git', '--no-replace-objects', '-C', str(ROOT)]
    tree = subprocess.check_output([*git, 'rev-parse', commit + '^{tree}'], text=True).strip()
    if tree != expected_tree:
        raise ValueError('fixed predecessor tree mismatch')
    registered = os.environ.get('MLF_TEST_SUITE') == f'benchmark-predecessor-{args.source}'
    scripts_to_run = {}
    mode = 'optimized' if sys.flags.optimize else 'ordinary'
    exact = os.environ.get('MLF_TEST_EXACT') if registered else None
    if args.framework_list or registered:
        for script in scripts:
            prefix = f'benchmark-predecessor/{args.source}/{mode}/{Path(script).stem}/'
            ids = inventory(git, commit, script, prefix)
            if not exact or exact in ids:
                scripts_to_run[script] = (prefix, [exact] if exact else ids)
        planned = [identity for _, ids in scripts_to_run.values() for identity in ids]
        if not planned:
            raise ValueError(f'case outside this frozen source and Python mode: {exact}')
        if args.framework_list:
            print(json.dumps(planned))
            return
        events.plan(planned)
    else:
        scripts_to_run = dict.fromkeys(scripts)

    with tempfile.TemporaryDirectory(prefix='mlf-pr43-replay-') as temporary:
        checkout = Path(temporary) / 'source'
        checkout.mkdir()
        with subprocess.Popen([*git, 'archive', commit, *PATHS], stdout=subprocess.PIPE) as archive:
            with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
                stream.extractall(checkout, filter='data')
            if archive.wait() != 0:
                raise ValueError('cannot materialize fixed predecessor')
        for script, plan in scripts_to_run.items():
            print('HISTORICAL SOURCE CONTRACT:', commit, script, flush=True)
            # cwd retains the authentic repository object database for DeclId's
            # original predecessor lookup. Script __file__ retains old ROOT.
            flags = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
            command = [sys.executable, *flags, '-B']
            if plan is None:
                subprocess.run([*command, checkout / script], cwd=ROOT, check=True)
                continue
            prefix, ids = plan
            event_log = Path(temporary) / (Path(script).stem + '.events.jsonl')
            event_log.touch(exist_ok=False)
            env = {**os.environ, 'MLF_TEST_ID_PREFIX': prefix, 'MLF_TEST_EVENTS': str(event_log)}
            result = subprocess.run([*command, FRAMEWORK / 'unittest_adapter.py', checkout / script],
                                    cwd=ROOT, env=env)
            collect(event_log, ids)
            if result.returncode:
                raise SystemExit(result.returncode if result.returncode > 0 else 128 - result.returncode)


if __name__ == '__main__':
    main()
