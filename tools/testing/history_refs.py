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
    '2ea93adf6d8c76857e0d202a033e9bfee191e444': ('bbed4764fdf6f0280b60299ebee67301e813a669', '0c25f12db03157b838ff867174b7f30183f3056a', '83f313ea7634b567e2f4b694a4e7bb1d8dfd8428', 'commit'),
    '65e9e66680ee65f5e24745240dfe7ec8706e3e3b': ('65d8130ba35827dfc6e5260d1e937cef94359304', '247c18d05e8e612ac7c1a96efa9a14163879d8ce', 'af3761c6d59321352f29556cbc6c22bee5dcb127', 'commit'),
    'bea6c93980e47946afc22ee99be0d571ed544489': ('266237520ee235c47c26fdbb4d94f643fd981171', '181ae274ebafc3a1d68d2e1998fed52490ca14da', '05a89e7b45579bf36882c6f00d3e7dca581ccf50', 'commit'),
    'cb4c56c3744653c76648e609c06a71afad1ae2d4': ('bcceb30f1c89096b0ad6d01a84de1511b06b6f1f', '80ec39c253b00551e79a393437a45038a54dc490', '13b82bf5d02805b6b17a68cae2467677c8dd6898', 'commit'),
    'e7da00f201bfb66bf6e26d59e56184dd37a83abd': ('bf38dc538598a0389a3310fe26c16f6609c912fc', '72fcf81daed158ff29c2df83eba3ab156227697b', '622e0001c4ad124d2f0096e0eca990c9896e978f', 'commit'),
    '177b951a4a870e0350c5a3eef5196f79be0624db': ('53217d3c66d7e6396f3c5c4aa41f8a38eacfd703', '177b951a4a870e0350c5a3eef5196f79be0624db', '53217d3c66d7e6396f3c5c4aa41f8a38eacfd703', 'tree'),
    '7efa13e6a64c0445ebcf891c4e15694321a43780': ('5c6bce7864b016d2d0a37f337ed6138e3bf2627a', '7efa13e6a64c0445ebcf891c4e15694321a43780', '5c6bce7864b016d2d0a37f337ed6138e3bf2627a', 'tree'),
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
SOURCE_ANCHOR = 'ef8dcc77b732084da9b00055dd54b8696edc499f'
SOURCE_PARENTS = ('33804e720af071350941cd87d9f010ef5e09ef28',
                  'afbe7219806881301831d79f43596811eca3279d')
MAIN_BASE = 'afbe7219806881301831d79f43596811eca3279d'
SEAL_PATH = 'tools/testing/history_refs.py'
TRANSPORTED = frozenset((
    '116de67c01461ad1a16f20256b8d92f88a145c32',
    '266237520ee235c47c26fdbb4d94f643fd981171',
    '38bceccab021f0850167735b70d36b2db8ec0d14',
    '821a3c6e5b1e59f5ee3ea2a6884306979d46683b',
    '65d8130ba35827dfc6e5260d1e937cef94359304',
))


from typing import NamedTuple


class SquashTransport(NamedTuple):
    source: str
    integration: str
    parent: str
    tree: str


# Original PR25 identities remain immutable. The target is explicit so its
# integration may be authenticated inside a later sealed precursor.
SQUASH_TRANSPORTS = {
    'bbed4764fdf6f0280b60299ebee67301e813a669': SquashTransport(
        '90319e3b8c3a7758cd68b3b6474ba0dff6a61923',
        'd52fb5a7c931fbd8d5262bbaf77f5babe0089baa',
        '0b738335a62b6f23a5b945da793c939b2b116b88',
        '44c4aadf0e6799c9ef16bc2899fe14557f6cd802'),
}


class CompletedSeal(NamedTuple):
    anchor: str
    anchor_parents: tuple
    source: str
    integration: str
    parent: str
    tree: str
    histories: tuple


COMPLETED_SEALS = {
    '19': CompletedSeal(
        'a7d53dfe1bcb30532ac3a1a49288ad2303f26e66',
        ('5f77c669586e44f31d13b861d4f92130e1f55a47',),
        '33abccb3055efca34608810bc3b5d4010e98ef46',
        'afbe7219806881301831d79f43596811eca3279d',
        '5d4310381a119c4136a1b9664e2c532ad76323f7',
        '46bc6787b3833cde8ef81ddb078a1848ef7f47cd',
        ('116de67c01461ad1a16f20256b8d92f88a145c32',
         '266237520ee235c47c26fdbb4d94f643fd981171',
         '38bceccab021f0850167735b70d36b2db8ec0d14')),
}


def verify_squash_source(rewritten, transport):
    if _object_tree(ROOT, transport.source, 'commit') != transport.tree:
        raise ValueError('squash source tree differs or is unavailable')
    if not (_is_ancestor(rewritten, transport.source)
            and _is_ancestor(transport.parent, transport.source)):
        raise ValueError('squash source ancestry differs')


def verify_squash_transport(rewritten, transport, target):
    verify_squash_source(rewritten, transport)
    if _object_tree(ROOT, transport.integration, 'commit') != transport.tree:
        raise ValueError('squash integration tree differs or is unavailable')
    if _parents(transport.integration) != [transport.parent]:
        raise ValueError('squash integration parent differs')
    if not _is_ancestor(transport.integration, target):
        raise ValueError('squash integration ancestry differs')


def verify_completed_source(event):
    if _parents(event.anchor) != list(event.anchor_parents):
        raise ValueError('completed seal precursor parents differ')
    if _parents(event.source) != [event.anchor]:
        raise ValueError('completed seal source parents differ')
    if _object_tree(ROOT, event.source, 'commit') != event.tree:
        raise ValueError('completed seal source tree differs')
    verify_sealed_tree(event.source, event.anchor)
    for ancestor in (event.parent, *event.histories):
        if not _is_ancestor(ancestor, event.anchor):
            raise ValueError('completed seal source ancestry differs')


def verify_completed_seal(event, target):
    verify_completed_source(event)
    if _object_tree(ROOT, event.integration, 'commit') != event.tree:
        raise ValueError('completed seal integration tree differs')
    if _parents(event.integration) != [event.parent]:
        raise ValueError('completed seal integration parent differs')
    if not _is_ancestor(event.integration, target):
        raise ValueError('completed seal integration ancestry differs')


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
    for event in COMPLETED_SEALS.values():
        verify_completed_seal(event, SOURCE_ANCHOR)
    for original, (rewritten, _oldtree, newtree, kind) in REVISIONS.items():
        if _object_tree(ROOT, rewritten, kind) != newtree:
            raise ValueError('published historical object is unavailable or differs: ' + original)
        if kind == 'commit' and not _is_ancestor(rewritten, SOURCE_ANCHOR):
            transport = SQUASH_TRANSPORTS.get(rewritten)
            if transport is None:
                raise ValueError('source precursor historical ancestry differs')
            verify_squash_transport(rewritten, transport, SOURCE_ANCHOR)


@lru_cache(maxsize=128)
def _parsed_tree_entries(root, tree, seal_path):
    """Cache only immutable raw-tree parsing, never live object availability.

    The cache key includes repository and tree identity. Every use separately
    rechecks all referenced object types and availability in one Git batch.
    """
    entries = {}
    object_types = {}
    modes = {b'40000': (b'040000', b'tree'), b'100644': (b'100644', b'blob'),
             b'100755': (b'100755', b'blob'), b'120000': (b'120000', b'blob'),
             b'160000': (b'160000', b'commit')}

    def walk(oid, prefix):
        raw = subprocess.check_output(['git', '--no-replace-objects', 'cat-file', 'tree', oid], cwd=root)
        offset = 0
        names = set()
        previous = None
        while offset < len(raw):
            space = raw.find(b' ', offset)
            nul = raw.find(b'\0', space + 1)
            if space < offset or nul < space or nul + 21 > len(raw):
                raise ValueError('malformed sealed raw tree record')
            mode, name = raw[offset:space], raw[space + 1:nul]
            child = raw[nul + 1:nul + 21].hex()
            offset = nul + 21
            if mode not in modes or not name or name in (b'.', b'..') or b'/' in name:
                raise ValueError('noncanonical sealed raw tree mode or name')
            path = prefix + name
            if name in names or path in entries:
                raise ValueError('duplicate sealed tree path')
            names.add(name)
            canonical_mode, kind = modes[mode]
            sort_key = name + (b'/' if kind == b'tree' else b'\0')
            if previous is not None and sort_key <= previous:
                raise ValueError('noncanonical sealed raw tree order')
            previous = sort_key
            metadata = canonical_mode + b' ' + kind + b' ' + child.encode('ascii')
            if seal_path.startswith(path + b'/'):
                metadata = canonical_mode + b' ' + kind
            entries[path] = metadata
            # Gitlinks refer to other repositories and need not be locally
            # available. Their exact mode and object ID still remain pinned.
            if kind != b'commit':
                prior = object_types.setdefault(child, kind)
                if prior != kind:
                    raise ValueError('sealed tree object has conflicting types')
            if kind == b'tree':
                walk(child, path + b'/')

    walk(tree, b'')
    return tuple(entries.items()), tuple(object_types.items())


def _entries(identity):
    """Reject duplicate names, noncanonical order/modes and malformed objects."""
    tree = _object_tree(ROOT, identity, 'commit')
    if tree is None:
        raise ValueError('sealed tree commit is unavailable')
    parsed, types = _parsed_tree_entries(ROOT, tree, SEAL_PATH.encode('utf-8'))
    object_types = dict(types)
    object_types[tree] = b'tree'
    if object_types:
        identities = list(object_types)
        output = subprocess.check_output(
            ['git', '--no-replace-objects', 'cat-file', '--batch-check=%(objectname) %(objecttype)'],
            cwd=ROOT, input=('\n'.join(identities) + '\n').encode('ascii')).splitlines()
        expected = [oid.encode('ascii') + b' ' + object_types[oid] for oid in identities]
        if output != expected:
            raise ValueError('sealed tree object type differs or is unavailable')
    return dict(parsed)


def verify_sealed_tree(candidate, anchor=None):
    """Authenticate the whole tree as precisely one deterministic substitution."""
    anchor = SOURCE_ANCHOR if anchor is None else anchor
    before = _entries(anchor)
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
    replacement = b"SOURCE_ANCHOR = '" + anchor.encode('ascii') + b"'\n"
    if original.count(marker) != 1 or current != original.replace(marker, replacement, 1):
        raise ValueError('sealed source literal differs')

    # Independently reconstruct the precise expected root OID from raw anchor
    # bytes. Only the seal blob and its ancestor OIDs may change; no parsed-row
    # equivalence, mode normalization or traversal ordering can substitute for
    # full Git tree identity.
    import hashlib

    def object_id(kind, raw):
        return hashlib.sha1(kind + b' ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()

    def replace_child(oid, parts, replacement_oid):
        raw = _git('cat-file', 'tree', oid)
        offset = 0
        found = []
        while offset < len(raw):
            space = raw.index(b' ', offset)
            nul = raw.index(b'\0', space + 1)
            end = nul + 21
            if raw[space + 1:nul] == parts[0]:
                child = raw[nul + 1:end].hex()
                updated = (replace_child(child, parts[1:], replacement_oid)
                           if len(parts) > 1 else replacement_oid)
                found.append((nul + 1, end, bytes.fromhex(updated)))
            offset = end
        if len(found) != 1:
            raise ValueError('ambiguous sealed raw tree path')
        start, end, updated = found[0]
        return object_id(b'tree', raw[:start] + updated + raw[end:])

    expected_tree = replace_child(_object_tree(ROOT, anchor, 'commit'),
                                  SEAL_PATH.encode('utf-8').split(b'/'),
                                  object_id(b'blob', original.replace(marker, replacement, 1)))
    if _object_tree(ROOT, candidate, 'commit') != expected_tree:
        raise ValueError('sealed source exact raw tree identity differs')


def verify_source(candidate):
    verify_anchor()
    if _parents(candidate) != [SOURCE_ANCHOR]:
        raise ValueError('sealed source parents differ')
    verify_sealed_tree(candidate)


VERIFIED_SOURCE_REF = 'refs/history/pr22-verified-source'


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
    if kind == 'commit' and not _is_ancestor(rewritten, 'HEAD'):
        if rewritten in SQUASH_TRANSPORTS:
            # The original integration is carried by P22, not falsely claimed
            # to remain a direct ancestor after the second squash.
            verify_squash_transport(rewritten, SQUASH_TRANSPORTS[rewritten], SOURCE_ANCHOR)
        elif rewritten not in TRANSPORTED:
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
