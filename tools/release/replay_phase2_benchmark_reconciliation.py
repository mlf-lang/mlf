#!/usr/bin/env python3
"""Run unchanged reconciliation controls in the authenticated pre-Phase-2 source."""
from pathlib import Path
import os
import runpy
import subprocess
import sys
import tarfile
import unittest

from check_benchmark_phase2_successor import ROOT, successor

ORIGINAL = 'tools/performance/artifact-binary/test_pr43_reconciliation.py'
ORIGINAL_SHA = '922f101f7c4f6cb3d0434eed10c2a61cd6672fadd5ea460eae4ad920042e67a9'


def run_frozen(root):
    path = root / ORIGINAL
    raw = successor.read(root, ORIGINAL, 65536)
    successor.require(successor.sha(raw) == ORIGINAL_SHA, 'exact unchanged reconciliation fixture')
    parent = str(path.parent)
    sys.path.insert(0, parent)
    try:
        runpy.run_path(str(path), run_name='__main__')
    finally:
        sys.path.remove(parent)


def objects_directory(root):
    git = ['git', '--no-replace-objects', '-C', str(root)]
    common = subprocess.check_output([*git, 'rev-parse', '--path-format=absolute', '--git-common-dir'],
                                      stderr=subprocess.PIPE, text=True).strip()
    result = Path(common).resolve(strict=True) / 'objects'
    successor.require(result.is_dir() and '\n' not in str(result), 'actual checkout Git object database')
    return result


def materialize_stock_metadata(opened):
    # This is the newly created checked pre-Phase-2 source projection, not the
    # caller's worktree. No owned source path starts within tools/performance.
    prior = opened.contract.archived
    source = [*opened.git.command, 'archive', opened.tip, 'tools/performance']
    with subprocess.Popen(source, stdout=subprocess.PIPE) as child:
        with tarfile.open(fileobj=child.stdout, mode='r|') as stream:
            stream.extractall(prior, filter='data')
        successor.require(child.wait() == 0, 'exact stock metadata source archive')
    subprocess.run(['git', 'init', '-q', str(prior)], check=True)
    (prior / '.git/objects/info/alternates').write_text(str(objects_directory(ROOT)) + '\n',
                                                       encoding='utf-8')
    return prior


def main():
    if os.environ.get('MLF_TEST_LIST') == '1':
        # Official unittest_adapter discovery only. Its runner exits after IDs;
        # no historical or production outcome can be reported by discovery.
        successor.require(unittest.TextTestRunner.__name__ == 'EvidenceRunner',
                          'stock discovery adapter')
        run_frozen(ROOT)
        return
    with successor.qualified(ROOT) as opened:
        run_frozen(materialize_stock_metadata(opened))


if __name__ == '__main__':
    main()
