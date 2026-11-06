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
    'bea6c93980e47946afc22ee99be0d571ed544489': ('266237520ee235c47c26fdbb4d94f643fd981171', '181ae274ebafc3a1d68d2e1998fed52490ca14da', '05a89e7b45579bf36882c6f00d3e7dca581ccf50', 'commit'),
    'cb4c56c3744653c76648e609c06a71afad1ae2d4': ('bcceb30f1c89096b0ad6d01a84de1511b06b6f1f', '80ec39c253b00551e79a393437a45038a54dc490', '13b82bf5d02805b6b17a68cae2467677c8dd6898', 'commit'),
    '4d732f31982ebe18124511f2ca4cb412770d6bd6': ('38bceccab021f0850167735b70d36b2db8ec0d14', 'feb1d0125f52a90eac3a2bb4379b8c3982393307', '557f438290273ca109241684f564ff89ef5f0a98', 'commit'),
    'e7da00f201bfb66bf6e26d59e56184dd37a83abd': ('bf38dc538598a0389a3310fe26c16f6609c912fc', '72fcf81daed158ff29c2df83eba3ab156227697b', '622e0001c4ad124d2f0096e0eca990c9896e978f', 'commit'),
}


def _object_tree(root, identity, kind):
    result = subprocess.run(['git', '--no-replace-objects', 'cat-file', '-e', identity], cwd=root,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if result.returncode:
        return None
    actual_kind = subprocess.check_output(['git', '--no-replace-objects', 'cat-file', '-t', identity], cwd=root, text=True).strip()
    if actual_kind != kind:
        raise ValueError('historical object has unexpected type: ' + identity)
    return subprocess.check_output(['git', '--no-replace-objects', 'rev-parse', '--verify', identity + '^{tree}'],
                                   cwd=root, text=True).strip()

# Two-phase seal: commit all reviewed bytes with this literal zeroed, then
# make a single child changing only this literal to that precursor's SHA.
SOURCE_ANCHOR = '0000000000000000000000000000000000000000'
SOURCE_PARENTS = ('5f77c669586e44f31d13b861d4f92130e1f55a47',)
MAIN_BASE = '5d4310381a119c4136a1b9664e2c532ad76323f7'
SEAL_PATH = 'tools/testing/history_refs.py'
TRANSPORTED = frozenset((
    '116de67c01461ad1a16f20256b8d92f88a145c32',
    '266237520ee235c47c26fdbb4d94f643fd981171',
    '38bceccab021f0850167735b70d36b2db8ec0d14',
))


def _git(*args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=ROOT)


def _require_complete_history():
    import os
    if _git('rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValueError('shallow history is not publication evidence')
    graft_path = Path(os.fsdecode(_git('rev-parse', '--git-path', 'info/grafts').strip()))
    if not graft_path.is_absolute():
        graft_path = ROOT / graft_path
    if graft_path.exists() or os.environ.get('GIT_GRAFT_FILE'):
        raise ValueError('grafted history is not publication evidence')


def _parents(identity):
    if _object_tree(ROOT, identity, 'commit') is None:
        raise ValueError('transport commit is unavailable: ' + identity)
    headers = _git('cat-file', 'commit', identity).split(b'\n\n', 1)[0].splitlines()
    return [line[7:].decode('ascii') for line in headers if line.startswith(b'parent ')]


def _is_ancestor(ancestor, descendant):
    _require_complete_history()
    result = subprocess.run(['git', '--no-replace-objects', 'merge-base', '--is-ancestor',
                             ancestor, descendant], cwd=ROOT, stderr=subprocess.PIPE)
    if result.returncode not in (0, 1):
        raise ValueError('historical ancestry check failed')
    return result.returncode == 0


def verify_anchor():
    import re
    _require_complete_history()
    if not re.fullmatch('[0-9a-f]{40}', SOURCE_ANCHOR) or SOURCE_ANCHOR == '0' * 40:
        raise ValueError('unsealed publication source anchor')
    if _parents(SOURCE_ANCHOR) != list(SOURCE_PARENTS):
        raise ValueError('source precursor parents differ')
    if not _is_ancestor(MAIN_BASE, SOURCE_ANCHOR):
        raise ValueError('source precursor main ancestry differs')
    for original, (rewritten, _oldtree, newtree, kind) in REVISIONS.items():
        if _object_tree(ROOT, rewritten, kind) != newtree:
            raise ValueError('published historical object is unavailable or differs: ' + original)
        if kind == 'commit' and not _is_ancestor(rewritten, SOURCE_ANCHOR):
            raise ValueError('source precursor historical ancestry differs')


def _entries(identity):
    entries = {}
    for entry in _git('ls-tree', '-rzt', '--full-tree', identity).split(b'\0'):
        if entry:
            metadata, path = entry.split(b'\t', 1)
            # Retain empty subtrees too. Only the seal's ancestor tree IDs
            # necessarily change; their modes/types remain authenticated.
            if SEAL_PATH.encode('utf-8').startswith(path + b'/'):
                metadata = b' '.join(metadata.split()[:2])
            entries[path] = metadata
    return entries


def verify_sealed_tree(candidate):
    """Authenticate the whole tree as precisely one deterministic substitution."""
    before = _entries(SOURCE_ANCHOR)
    after = _entries(candidate)
    path = SEAL_PATH.encode('utf-8')
    old_meta = before.pop(path, None)
    new_meta = after.pop(path, None)
    if (before != after or old_meta is None or new_meta is None
            or old_meta.split()[:2] != [b'100644', b'blob']
            or new_meta.split()[:2] != [b'100644', b'blob']):
        raise ValueError('sealed source tree or mode differs')
    original = _git('cat-file', 'blob', old_meta.split()[2].decode('ascii'))
    current = _git('cat-file', 'blob', new_meta.split()[2].decode('ascii'))
    marker = b"SOURCE_ANCHOR = '" + b'0' * 40 + b"'\n"
    replacement = b"SOURCE_ANCHOR = '" + SOURCE_ANCHOR.encode('ascii') + b"'\n"
    if original.count(marker) != 1 or current != original.replace(marker, replacement, 1):
        raise ValueError('sealed source literal differs')


def verify_source(candidate):
    verify_anchor()
    if _parents(candidate) != [SOURCE_ANCHOR]:
        raise ValueError('sealed source parents differ')
    verify_sealed_tree(candidate)


VERIFIED_SOURCE_REF = 'refs/history/pr19-verified-source'


def verified_source_in_checkout():
    """Find authenticated Q in HEAD history or a previously verified local ref.

    Merely possessing P is insufficient: even a rejected fetch can install P.
    The retained ref is only a locator and is reauthenticated on every use.
    """
    if _is_ancestor(SOURCE_ANCHOR, 'HEAD'):
        candidates = _git('rev-list', '--ancestry-path', SOURCE_ANCHOR + '..HEAD').splitlines()
        for raw in candidates:
            candidate = raw.decode('ascii')
            if _parents(candidate) == [SOURCE_ANCHOR]:
                try:
                    verify_source(candidate)
                except ValueError:
                    continue
                return candidate
    result = subprocess.run(['git', '--no-replace-objects', 'rev-parse', '--verify', '--quiet',
                             VERIFIED_SOURCE_REF], cwd=ROOT, stdout=subprocess.PIPE)
    if result.returncode == 1:
        return None
    if result.returncode:
        raise ValueError('verified source locator lookup failed')
    candidate = result.stdout.decode('ascii').strip()
    verify_source(candidate)
    return candidate


def verify_publication():
    """Authenticate Q, then distinguish integrated history from premerge CI."""
    verify_anchor()
    source = verified_source_in_checkout()
    if source is None:
        raise ValueError('verified sealed source is unavailable; run preparation')
    source_tree = _object_tree(ROOT, source, 'commit')
    # Only an exact reviewed squash permits subsequent main-tree changes.
    # P may reappear through later merges without masking this valid boundary.
    for raw in _git('rev-list', '--first-parent', 'HEAD').splitlines():
        candidate = raw.decode('ascii')
        if (_parents(candidate) == [MAIN_BASE]
                and _object_tree(ROOT, candidate, 'commit') == source_tree):
            verify_sealed_tree(candidate)
            return
    # Before integration, both a source checkout and GitHub's synthetic merge
    # must preserve Q's complete sealed tree. Extra changes require resealing.
    head = _git('rev-parse', '--verify', 'HEAD').decode('ascii').strip()
    if (head == source or _parents(head) == [MAIN_BASE, source]):
        if _object_tree(ROOT, head, 'commit') == source_tree:
            return
    raise ValueError('publication has no exact sealed HEAD or reviewed squash integration')


def verify_published_revision(original):
    if original not in REVISIONS:
        raise ValueError('unreviewed historical identity: ' + original)
    rewritten, _oldtree, newtree, kind = REVISIONS[original]
    if _object_tree(ROOT, rewritten, kind) != newtree:
        raise ValueError('published historical object is unavailable or differs: ' + original)
    verify_publication()
    if kind == 'commit' and not _is_ancestor(rewritten, 'HEAD') and rewritten not in TRANSPORTED:
        raise ValueError('historical commit has no reviewed squash transport')


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
    return subprocess.check_output(['git', '--no-replace-objects', 'show', resolve_revision(revision) + ':' + normalized], cwd=ROOT)


# A second, separately reviewed reconciliation preserves the frozen 2026-10-23
# census. These are immutable incoming-main bytes, not candidate-derived goldens.
RECONCILED_MAIN = '5d4310381a119c4136a1b9664e2c532ad76323f7'
RECONCILED_MAIN_PATHS = {
    '.github/workflows/ci.yml': '98b2f748bdb7cc8db5b76459ebf7a874075a22df098ea2371f795f8f7ebec9a0',
    'tools/release/check.sh': '262f3fd1ee305c41a7562f293dfbaa4e49676736f514574f86c7cf703ffbbb1b',
    'tools/release/async-change-scope.py': 'a3cfc33040260bdd3e37623bb2ff50cee0518f0d602cfedae56c65ea80fdc634',
    'tools/release/test-async-change-scope.py': 'cd043259b9f227c29ddaa4042cafc6c6bc9c7faddbb9265b28593b5b9a3617b9',
    'tools/release/test-ci-policy.mjs': 'bf71f5c7c17f83add84a6d11ccdf84a2917c03e253dd4f07300d6dc73f57e81e',
}


def checked_current(path, current, expected_sha256):
    """Verify frozen inputs plus only the reviewed incoming-main/preparation delta."""
    import hashlib
    snapshot = '4d732f31982ebe18124511f2ca4cb412770d6bd6'
    original = historical_bytes(snapshot, path)
    if hashlib.sha256(original).hexdigest() != expected_sha256:
        raise ValueError('frozen reconciliation input changed: ' + path)
    if path == 'mlf.lock':
        from framework_recovery import repaired_root_lock
        return current == repaired_root_lock(ROOT, original)
    value = original.decode('utf-8')
    if path in RECONCILED_MAIN_PATHS:
        incoming = _git('show', RECONCILED_MAIN + ':' + path)
        if hashlib.sha256(incoming).hexdigest() != RECONCILED_MAIN_PATHS[path]:
            raise ValueError('reviewed incoming main differs: ' + path)
        value = incoming.decode('utf-8')
    if path == '.github/workflows/ci.yml':
        changes = [('permissions:\n  contents: read\n',
                    'permissions:\n  contents: read\n  actions: read\n'), (
            '      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6\n      - run: tools/release/check.sh\n',
            '      - uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6\n        with:\n          fetch-depth: 0\n      - name: Prepare reviewed historical source objects\n        run: python3 -B tools/testing/prepare_history_refs.py\n      - run: tools/release/check.sh\n',
        )]
    elif path == 'tools/release/check.sh':
        changes = [("tools/release/test-fetch-seed.sh\n",
                    "tools/release/test-fetch-seed.sh\npython3 tools/release/test-fetch-seed-artifact.py\n"),
                   ("python3 tools/release/test-async-change-scope.py\n",
                    "python3 tools/release/test-async-change-scope.py\npython3 tools/testing/test_history_refs.py\npython3 tools/testing/test_history_workflows.py\npython3 tools/testing/test_framework_recovery.py\n")]
    elif path == 'tools/testing/check_reconciliation_inventory.py':
        changes = [
            ('import subprocess\n', 'from history_refs import historical_bytes, checked_current\n'),
            ("        assert sha((ROOT / path).read_bytes()) == row['sha256']\n",
             "        assert checked_current(path, (ROOT / path).read_bytes(), row['sha256'])\n"),
            ("            frozen = subprocess.check_output(['git','show',INCOMING+':'+path], cwd=ROOT)\n",
             "            frozen = historical_bytes(INCOMING, path)\n"),
            ("        prior = subprocess.check_output(['git','show',PARENT+':'+path], cwd=ROOT)\n",
             "        prior = historical_bytes(PARENT, path)\n"),
            ("            assert frozen == (ROOT / path).read_bytes(), path\n",
             "            assert checked_current(path, (ROOT / path).read_bytes(), row['incoming_sha256']), path\n"),
            ("        assert actual == prior and sha(actual) == expected, path\n",
             "        assert sha(prior) == expected, path\n        if path == 'mlf.lock':\n            assert checked_current(path, actual, expected), path\n        else:\n            assert actual == prior, path\n"),
        ]
    else:
        changes = []
    for before, after in changes:
        if value.count(before) != 1:
            raise ValueError('frozen transport transformation is ambiguous: ' + path)
        value = value.replace(before, after, 1)
    return current == value.encode('utf-8')
