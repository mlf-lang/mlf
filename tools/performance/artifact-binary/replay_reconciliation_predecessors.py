#!/usr/bin/env python3
"""Replay unchanged source-contract tests in fixed physical predecessor sources.

No compiler, generator, benchmark or native qualification is run. These are
historical regressions only; test_pr43_reconciliation checks current sources.
Run after the current-source suite exits to avoid overlapping archive copies.
"""
from pathlib import Path
import argparse
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[3]
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', choices=tuple(SOURCES))
    args = parser.parse_args()
    commit, expected_tree, scripts = SOURCES[args.source]
    git = ['git', '--no-replace-objects', '-C', str(ROOT)]
    tree = subprocess.check_output([*git, 'rev-parse', commit + '^{tree}'], text=True).strip()
    if tree != expected_tree:
        raise ValueError('fixed predecessor tree mismatch')
    with tempfile.TemporaryDirectory(prefix='mlf-pr43-replay-') as temporary:
        checkout = Path(temporary)
        with subprocess.Popen([*git, 'archive', commit, *PATHS], stdout=subprocess.PIPE) as archive:
            with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
                stream.extractall(checkout, filter='data')
            if archive.wait() != 0:
                raise ValueError('cannot materialize fixed predecessor')
        for script in scripts:
            print('HISTORICAL SOURCE CONTRACT:', commit, script, flush=True)
            # cwd retains the authentic repository object database for DeclId's
            # original predecessor lookup. Script __file__ retains old ROOT.
            flags = ['-' + 'O' * sys.flags.optimize] if sys.flags.optimize else []
            subprocess.run([sys.executable, *flags, '-B', checkout / script],
                           cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
