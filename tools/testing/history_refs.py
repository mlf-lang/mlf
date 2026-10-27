#!/usr/bin/env python3
"""Resolve frozen audit identities after the reviewed history cleanup.

The left side remains the original evidence identity. Each right side was
independently checked against the original whole tree with only
`tools/profile/results/` and `papers/*.pdf` removed. Blob contents and modes
outside those paths are unchanged. Mappings are closed, immutable review data;
no environment or user configuration can select another object.
"""
from functools import lru_cache
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
# original identity -> (rewritten identity, original tree, rewritten tree, kind)
REVISIONS = {
    '8a3e69b165765931c3ff762379a78db9659b2cd8': ('116de67c01461ad1a16f20256b8d92f88a145c32', 'ba0ae958b466ca08ffee79a83dadbd8b7d2156fa', 'cc3c6c9ce7cd46d403973627802e7d3b87166b98', 'commit'),
    '4d732f31982ebe18124511f2ca4cb412770d6bd6': ('38bceccab021f0850167735b70d36b2db8ec0d14', 'feb1d0125f52a90eac3a2bb4379b8c3982393307', '557f438290273ca109241684f564ff89ef5f0a98', 'commit'),
    'c0c5dddd11ed5775e2a3d5564cfeeef8383610a5': ('821a3c6e5b1e59f5ee3ea2a6884306979d46683b', '9f8aaaa86e5930fd89c88c542bb21647d7b15fca', '99732133c0914fd86a44cc04eae411650b229777', 'commit'),
    '65e9e66680ee65f5e24745240dfe7ec8706e3e3b': ('65d8130ba35827dfc6e5260d1e937cef94359304', '247c18d05e8e612ac7c1a96efa9a14163879d8ce', 'af3761c6d59321352f29556cbc6c22bee5dcb127', 'commit'),
    'bea6c93980e47946afc22ee99be0d571ed544489': ('266237520ee235c47c26fdbb4d94f643fd981171', '181ae274ebafc3a1d68d2e1998fed52490ca14da', '05a89e7b45579bf36882c6f00d3e7dca581ccf50', 'commit'),
    'cb4c56c3744653c76648e609c06a71afad1ae2d4': ('bcceb30f1c89096b0ad6d01a84de1511b06b6f1f', '80ec39c253b00551e79a393437a45038a54dc490', '13b82bf5d02805b6b17a68cae2467677c8dd6898', 'commit'),
    'e7da00f201bfb66bf6e26d59e56184dd37a83abd': ('bf38dc538598a0389a3310fe26c16f6609c912fc', '72fcf81daed158ff29c2df83eba3ab156227697b', '622e0001c4ad124d2f0096e0eca990c9896e978f', 'commit'),
    '177b951a4a870e0350c5a3eef5196f79be0624db': ('53217d3c66d7e6396f3c5c4aa41f8a38eacfd703', '177b951a4a870e0350c5a3eef5196f79be0624db', '53217d3c66d7e6396f3c5c4aa41f8a38eacfd703', 'tree'),
    '7efa13e6a64c0445ebcf891c4e15694321a43780': ('5c6bce7864b016d2d0a37f337ed6138e3bf2627a', '7efa13e6a64c0445ebcf891c4e15694321a43780', '5c6bce7864b016d2d0a37f337ed6138e3bf2627a', 'tree'),
}


def _object_tree(root, identity, kind):
    result = subprocess.run(['git', 'cat-file', '-e', identity], cwd=root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        return None
    actual_kind = subprocess.check_output(['git', 'cat-file', '-t', identity], cwd=root, text=True).strip()
    if actual_kind != kind:
        raise ValueError('historical object has unexpected type: ' + identity)
    return subprocess.check_output(['git', 'rev-parse', '--verify', identity + '^{tree}'],
                                   cwd=root, text=True).strip()


@lru_cache(maxsize=None)
def resolve_revision(revision):
    if revision not in REVISIONS:
        raise ValueError('unreviewed historical identity: ' + revision)
    rewritten, original_tree, rewritten_tree, kind = REVISIONS[revision]
    tree = _object_tree(ROOT, rewritten, kind)
    if tree is not None:
        if tree != rewritten_tree:
            raise ValueError('rewritten historical tree differs from reviewed mapping: ' + revision)
        return rewritten
    tree = _object_tree(ROOT, revision, kind)
    if tree is None:
        raise ValueError('reviewed historical identity is unavailable: ' + revision)
    if tree != original_tree:
        raise ValueError('original historical tree differs from reviewed mapping: ' + revision)
    return revision


def historical_bytes(revision, path):
    source = Path(path)
    normalized = source.as_posix()
    if (source.is_absolute() or not path or normalized == '.' or '..' in source.parts
            or ':' in path or '\x00' in path or '\\' in path
            or normalized == 'tools/profile/results' or normalized.startswith('tools/profile/results/')
            or (normalized.startswith('papers/') and normalized.endswith('.pdf'))):
        raise ValueError('unavailable or invalid historical source path: ' + path)
    return subprocess.check_output(['git', 'show', resolve_revision(revision) + ':' + normalized], cwd=ROOT)
