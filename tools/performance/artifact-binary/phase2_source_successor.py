"""Bounded exact PR55/b6b7a99 source projection composed with the original live contract.

This module never trusts a caller-supplied archive, substitutes a history receipt,
or executes a compiler. The authenticated checkout and checked-in edge determine
the old source bytes, then the original independent history contract runs.
"""


from contextlib import contextmanager
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zlib
import subprocess
from tempfile import TemporaryDirectory
from types import MappingProxyType, ModuleType
from typing import NamedTuple


HERE = Path(__file__).resolve().parent
POLICY_NAME = 'phase2-c1-source-successor.json'
POLICY_SHA = '2198a903fec70c7c10e2eeb36d20f731624d5963e36677e2a589b33b0e5571af'
OLD_ADAPTER_SHA = 'e532a614ba8baef5637347be2ae052a90c36d117b153ac5bfe8b117d41313163'
STOCK_BENCHMARK_SHA = 'd6f7248b1a8def2bc0c4ca55d714fe2daed7547c483814442700997850197836'
CAP = 8 * 1024 * 1024
PR = '265560ef383526c66126a9e79580e39bb4850973'
FOUNDATION = 'b6b7a998362932a38bfb4432b73ed5402bde55de'
FOUNDATION_TREE = 'b37a4a89ba0288beb2a3a96dcde02e2219550b20'
FOUNDATION_PARENT = '652cb345dc8ab12aebfef218ac15fe9c3225dd27'
MERGED = 'c65afd09031547eac6cf09dd2b209a2b3a94a7eb'
MERGED_TREE = 'd82b24a161d348f86a6a2eea0c8b6b0196aed86e'
ADMITTED = '613aa405dc89a0d3381b2e3fee79fa2ab3c979a5'
ADMITTED_TREE = '21fea1d9ce3fa16722b4e2575d96c8bb97a8d3a3'
CALLBACK = '24249743cd9c4b627a362cb9307cd5966d252065'
CALLBACK_TREE = '85b59ea6574c688a9cf4cb9b587d50747b9c8366'
CURRENT = '4fcc21b4d495aff78c2ee5647e7cf45e92d1a73a'
CURRENT_TREE = '60023f17582feb7ed447b38745f0f378f3f2b40a'
OLD_FRAMEWORK_PIN = '400c7b78ddc60bb5d024869b50a4b99915735843d82d85a9f0b8c80639b84020'
REGISTRY = 'shared-sources.json'
RETIRED = 'tests/Tests/TupleListLegacy.hs'
INTSET = 'libraries/mlf-foundation/Bootstrap/IntSet.hs'
ORIGIN = 'f21bf054b87ff4cf22a86ba8e2e0d1416efaa47f'
ORIGIN_TREE = '20a2dbfc1dc4dc036de087d4e1275e4a848940eb'
ORIGIN_PARENT = 'bba253e8418612f4c97d5cf4826457b2d9f5c1a1'
OLD_INTSET_OID = '41b09cdd43193899ec46e15df57906012b3f3098'
NEW_INTSET_OID = 'e40f03ea1b505bcefb1c53df44c9ee37cf8925f9'
OLD_INTSET_SHA = 'c04ea56944feaa4bbeedcd5ded176b3cc10c3cd99aef2aac483df9928b2a35fe'
NEW_INTSET_SHA = '35c5338f7373cd2f58252e688936d822f408d17a30d298576666fbd2473c5b30'
BENCHMARK = 'benchmarks/manifest.json'
BENCHMARK_BEFORE_SHA = 'b39bc8956d8e53f35804b193de0119e0a9fb3388f1e3af18f9a32215915e82e2'
BENCHMARK_HISTORY_SHA = 'c5da11d57bbe021ec0e4f5b906929128df04542402c9bd01d77386658adff70f'
SPLICES_NAME = 'phase2-source-splices.zlib.b64'
SPLICES_SHA = 'ed9ec00891e90839e5aecfb78dbd241986e1ecfc596ed884117e82dcd15f6ba1'
SPLICES_JSON_SHA = 'a84337239f2024b5a1403d7ff4c20f8c0ac02377446fbc78579c965f2e17a4a2'
STOCK_CODEC_SHA = 'f6c81c97a1284442c5825d38fc806639af9b49e8634b516d649dfa8c7583910d'
MAIN = 'eab4487475adc33639a723406e7ae0f3ad5cced9'
WIRING = {
    'benchmarks/manifest.json': 'M',
    'tools/performance/phase1-test-suites.json': 'M',
    'tools/release/check-benchmark-provenance.sh': 'M',
    'tools/performance/artifact-binary/phase2-c1-source-successor.json': 'A',
    'tools/performance/artifact-binary/phase2-source-splices.zlib.b64': 'A',
    'tools/performance/artifact-binary/phase2_source_successor.py': 'A',
    'tools/release/check_benchmark_phase2_successor.py': 'A',
    'tools/release/test_benchmark_phase2_successor.py': 'A',
    'tools/release/replay_phase2_benchmark_reconciliation.py': 'A',
}
OLD_CLAUSE = b"""  fromDistinctAscList :: [] Int -> IntSet;
  fromDistinctAscList values = wrap (case L.foldlStrict ascInsert NoState values of {
    NoState -> IntSetNil;
    State key bits stack -> ascLinkStack stack key (tip key bits)
  });
"""
NEW_CLAUSE = b"""  finishAsc :: AscState -> IntSet;
  finishAsc state = wrap (case state of {
    NoState -> IntSetNil;
    State key bits stack -> ascLinkStack stack key (tip key bits)
  });
  fromDistinctAscList :: [] Int -> IntSet;
  fromDistinctAscList values = finishAsc (L.foldlStrict ascInsert NoState values);
"""


def require(condition, label):
    if not condition:
        raise ValueError('PR55 Phase 2 source successor: ' + label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def oid(raw, kind='blob'):
    return hashlib.sha1(f'{kind} {len(raw)}\0'.encode() + raw).hexdigest()


def json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('non-finite JSON constant: ' + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def path_parts(path):
    require(type(path) is str, 'path type')
    parts = path.split('/')
    require(all(re.fullmatch(r'[a-zA-Z0-9_.+-]+', node) and node not in ('.', '..') for node in parts),
            'unsafe source path: ' + path)
    return parts


def read(root, path, bound=CAP):
    """Bounded regular-file read underneath a pinned directory, no symlink nodes."""
    parts = path_parts(path)
    dir_open = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_open = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    directory = os.open(root, dir_open)
    try:
        for part in parts[:-1]:
            child = os.open(part, dir_open, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], file_open, dir_fd=directory)
        with os.fdopen(fd, 'rb') as stream:
            st = os.fstat(stream.fileno())
            require(stat.S_ISREG(st.st_mode) and st.st_size <= bound, 'regular bounded file: ' + path)
            raw = stream.read(bound + 1)
            require(len(raw) <= bound and len(raw) == st.st_size, 'stable bounded file: ' + path)
            return raw
    finally:
        os.close(directory)


def pinned_module(directory, path, expected_sha):
    raw = read(directory, path, 65536)
    require(sha(raw) == expected_sha, 'exact stock implementation: ' + path)
    module = ModuleType('_mlf_c1_stock_' + expected_sha)
    module.__file__ = str(directory / path)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


def matches(value, length):
    return type(value) is str and bool(re.fullmatch('[a-f0-9]{%d}' % length, value))


def load_policy():
    raw = read(HERE, POLICY_NAME, 65536)
    require(sha(raw) == POLICY_SHA, 'exact source-only endpoint policy')
    policy = strict_json(raw)
    require(set(policy) == {'format', 'old', 'changed', 'registry_sha', 'registry_count'} and
            policy['format'] == 'pr55-c1-source-successor-v1' and
            type(policy['old']) is dict and len(policy['old']) == 197 and
            type(policy['changed']) is dict and len(policy['changed']) == 16 and 'mlf.lock' in policy['changed'] and
            set(policy['changed']) <= set(policy['old']) and
            RETIRED not in policy['old'] and
            policy['registry_count'] == 136 and policy['registry_sha'] == policy['old'][REGISTRY],
            'exact role/owner inventory')
    for path, digest in policy['old'].items():
        path_parts(path)
        require(matches(digest, 64), 'old role digest: ' + path)
    for path, row in policy['changed'].items():
        require(type(row) is list and len(row) == 2 and matches(row[0], 64) and
                matches(row[1], 40) and policy['old'][path] != row[0],
                'distinct exactly bound endpoint: ' + path)
    require(policy['old'][INTSET] == OLD_INTSET_SHA and
            policy['changed'][INTSET] == [NEW_INTSET_SHA, NEW_INTSET_OID],
            'IntSet endpoint source composition')
    return policy


class Git:
    """Explicit no-replacement reader, only full pinned commit and role names."""
    def __init__(self, git_dir):
        self.command = ['git', '--no-replace-objects', '--git-dir=' + str(Path(git_dir).resolve(strict=True))]

    def run(self, *args):
        return subprocess.check_output([*self.command, *args], stderr=subprocess.PIPE)

    def commit(self, commit, tree=None, parents=None):
        raw = self.run('cat-file', 'commit', commit)
        require(oid(raw, 'commit') == commit, 'commit identity: ' + commit)
        headers = raw.split(b'\n\n', 1)[0].splitlines()
        require(tree is None or headers[0] == b'tree ' + tree.encode(), 'commit tree: ' + commit)
        if tree is not None:
            require(oid(self.run('cat-file', 'tree', tree), 'tree') == tree,
                    'exact raw Git tree bytes: ' + tree)
        actual = [row[7:].decode() for row in headers if row.startswith(b'parent ')]
        require(parents is None or actual == parents, 'ordered commit parents: ' + commit)
        return actual

    def inventory(self, commit, paths):
        entries = self.run('ls-tree', '-rz', commit, '--', *sorted(paths)).split(b'\0')
        output = {}
        require(entries[-1] == b'', 'NUL-terminated tree listing')
        for entry in entries[:-1]:
            metadata, path = entry.decode().split('\t', 1)
            mode, kind, digest = metadata.split()
            require(path in paths and path not in output and mode in ('100644', '100755') and
                    kind == 'blob' and matches(digest, 40), 'ordinary exact Git source role: ' + path)
            output[path] = digest
        require(output.keys() == set(paths), 'complete tracked Git role inventory')
        return output


def raw_map(value, digests, label):
    require(isinstance(value, (dict, MappingProxyType)) and value.keys() == set(digests),
            'complete ' + label + ' paths')
    for path, raw in value.items():
        require(type(raw) is bytes and len(raw) <= CAP and sha(raw) == digests[path],
                label + ' size or digest: ' + path)


class Projection:
    """Pure byte-level edge; instantiation does not certify predecessor history."""
    def __init__(self, before, after, old_changed, new_changed):
        require(before.keys() == after.keys() and all(matches(x, 64) for x in before.values()) and
                all(matches(x, 64) for x in after.values()), 'stable whole role inventory')
        changed = {p for p in before if before[p] != after[p]}
        raw_map(old_changed, {p: before[p] for p in changed}, 'old transition')
        raw_map(new_changed, {p: after[p] for p in changed}, 'new transition')
        self.before, self.after, self.old, self.new = (
            MappingProxyType(dict(value)) for value in (before, after, old_changed, new_changed))

    def reverse(self, current):
        raw_map(current, self.after, 'current source')
        previous = {**current, **self.old}
        raw_map(previous, self.before, 'prior source')
        return previous

    def advance(self, previous):
        raw_map(previous, self.before, 'prior source')
        current = {**previous, **self.new}
        raw_map(current, self.after, 'current source')
        return current


def authenticate_source_spine(git, candidate_commit):
    # Authorship metadata of local integration commits need not survive the
    # write transport. Full ordered Git parents and immutable trees must.
    require(matches(candidate_commit, 40), 'explicit source-tip Git identity')
    git.commit(PR)
    git.commit(FOUNDATION, FOUNDATION_TREE, [FOUNDATION_PARENT])
    current = candidate_commit
    for tree in (CURRENT_TREE, CALLBACK_TREE, ADMITTED_TREE):
        parents = git.commit(current, tree)
        require(len(parents) == 1, 'exact single-parent overlay')
        current = parents[0]
    git.commit(current, MERGED_TREE, [PR, FOUNDATION])


def checkout_source_tip(source_root):
    root = Path(source_root).resolve(strict=True)
    command = ['git', '--no-replace-objects', '-C', str(root), 'rev-parse']
    def revision(*args):
        return subprocess.check_output([*command, *args], stderr=subprocess.PIPE,
                                       text=True).strip()
    require(Path(revision('--show-toplevel')) == root, 'actual normal checkout root')
    git = Git(revision('--path-format=absolute', '--git-dir'))
    head = revision('--verify', 'HEAD')
    recorded = git.commit(head)
    require(len(recorded) in (1, 2), 'review metadata or exact CI merge shape')
    if len(recorded) == 2:
        require(recorded[0] == MAIN and git.run('rev-parse', head+'^{tree}') ==
                git.run('rev-parse', recorded[1]+'^{tree}'),
                'exact unchanged synthetic CI merge tree and reviewed main')
        metadata = recorded[1]
    else:
        metadata = head
    parents = git.commit(metadata)
    require(len(parents) == 1, 'single source-only parent for review metadata')
    tip = parents[0]
    authenticate_source_spine(git, tip)
    parts = git.run('diff', '--no-renames', '--name-status', '-z', tip, metadata).split(b'\0')
    require(parts[-1] == b'' and len(parts) == len(WIRING)*2+1, 'exact review metadata patch size')
    actual = {p.decode(): status.decode() for status, p in zip(parts[::2], parts[1::2])}
    require(actual == WIRING, 'only the independently reviewed metadata paths may follow the source tip')
    return git, tip


def bounded_splices(raw, expected_packed=SPLICES_SHA, expected_json=SPLICES_JSON_SHA):
    require(type(raw) is bytes and raw.endswith(b'\n') and len(raw) <= 65536 and
            sha(raw) == expected_packed, 'exact bounded reversible edge')
    decoded = base64.b64decode(raw[:-1], validate=True)
    require(base64.b64encode(decoded) == raw[:-1], 'canonical splice encoding')
    z = zlib.decompressobj()
    unpacked = z.decompress(decoded, 262145)
    require(len(unpacked) <= 262144 and z.eof and not z.unconsumed_tail and not z.unused_data and
            sha(unpacked) == expected_json, 'exact bounded splice expansion')
    value = strict_json(unpacked)
    require(type(value) is dict and set(value) == {'format', 'deltas'} and
            value['format'] == 'pr55-phase2-old-role-splices-v1' and
            type(value['deltas']) is dict, 'exact reversible manifest schema')
    return value['deltas']


def reconstruct_precursor(current, policy):
    # Independently fixed SHA anchors authenticate the exact stock byte codec
    # and reviewed bounded data. Nothing comes from an environment/receipt.
    codec = pinned_module(HERE, 'source_contract.py', STOCK_CODEC_SHA)
    rows = bounded_splices(read(HERE, SPLICES_NAME, 65536))
    require(rows.keys() == policy['changed'].keys(), 'exact reversible path inventory')
    old = {}
    for path, delta in rows.items():
        require(type(delta) is dict and delta.get('path') == path and
                delta.get('old_sha256') == policy['old'][path] and
                delta.get('new_sha256') == policy['changed'][path][0], 'independent role endpoint: ' + path)
        raw = codec.apply_splices(current[path], delta, reverse=True)
        require(codec.apply_splices(raw, delta) == current[path], 'exact raw role round trip: ' + path)
        old[path] = raw
    return old


def authenticate_c1(git, source_root, policy, candidate_commit=CURRENT):
    authenticate_source_spine(git, candidate_commit)
    require(not os.path.lexists(source_root / RETIRED), 'retired source present')
    paths = set(policy['old'])
    git_ids = git.inventory(candidate_commit, paths)
    current = {p: read(source_root, p) for p in paths}
    latest = {**policy['old'], **{p: row[0] for p, row in policy['changed'].items()}}
    raw_map(current, latest, 'against the exact current source policy')
    for p, raw in current.items():
        require(oid(raw) == git_ids[p], 'physical source vs independently pinned Git role: ' + p)
    require(all(git_ids[p] == row[1] for p, row in policy['changed'].items()), 'changed Git blob pin')
    registry = strict_json(current[REGISTRY])['modules']
    names = {row['module']: row['path'] for row in registry}
    require(len(registry) == len(names) == policy['registry_count'] and len(set(names.values())) == len(names)
            and set(names.values()) <= paths, 'exact current module ownership')
    return current, latest, names


def composed_type(previous_type):
    class Contract(previous_type):
        def __init__(self, predecessor, edge, source_root, prior_root):
            self.previous = predecessor
            self.edge = edge
            self.directory = HERE
            self.archived = prior_root
            self.source_root = source_root
            self.core = predecessor.core
            self.removed_paths = predecessor.removed_paths
            self.changes = {p: [edge.before[p], edge.after[p]] for p in edge.old}
            self.parent = predecessor.parent
            self.maintenance_parent = predecessor.maintenance_parent
            self.evidence_source_root = predecessor.evidence_source_root
            self.added_modules = predecessor.added_modules
            self.added_paths = predecessor.added_paths
            self.manifest_sha256 = POLICY_SHA
            self.metadata_paths = (*predecessor.metadata_paths, POLICY_NAME, Path(__file__).name)
            paths = dict(predecessor.value['module_paths'])
            self.value = {'current_files': dict(edge.after), 'module_paths': paths,
                          'current_registry': {name: edge.after[p] for name, p in paths.items()}}

        def restore_maintenance(self, raw, name):
            return self.previous.restore_maintenance(raw, name)

        def project_tree_bytes(self, current):
            return self.previous.project_tree_bytes(self.edge.reverse(current))

        def advance_tree_bytes(self, parent, additions):
            self._require_raw_map(additions, {p: self.edge.after[p] for p in self.added_paths},
                                  'c1 source additions')
            older = {p: self._older_bytes(raw, p) for p, raw in additions.items()}
            current = self.edge.advance(self.previous.advance_tree_bytes(parent, older))
            require(self.project_tree_bytes(current) == parent, 'full stock historical round trip')
            return current

    return Contract


class Qualified(NamedTuple):
    contract: object
    git: Git
    tip: str


@contextmanager
def qualified(root):
    source_root = Path(root).resolve(strict=True)
    g, candidate_commit = checkout_source_tip(source_root)
    policy = load_policy()
    current, latest, ownership = authenticate_c1(g, source_root, policy, candidate_commit)
    old_changed = reconstruct_precursor(current, policy)
    new_changed = {p: current[p] for p in policy['changed']}
    edge = Projection(policy['old'], latest, old_changed, new_changed)
    previous = edge.reverse(current)
    require(edge.advance(previous) == current and parse_intset(g, current[INTSET]) == previous[INTSET],
            'whole source byte round trip including original IntSet edge')

    with TemporaryDirectory(prefix='mlf-pr55-projected-stock-') as tmp:
        prior_root = Path(tmp)
        for p, raw in previous.items():
            target = prior_root / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        old_adapter = pinned_module(HERE, 'source_migration_adapter.py', OLD_ADAPTER_SHA)
        predecessor = old_adapter.live_contract(source_root / 'tools/performance', source_root=prior_root)
        require(predecessor.manifest_sha256 == OLD_FRAMEWORK_PIN and
                predecessor.value['current_files'] == dict(edge.before) and
                predecessor.value['module_paths'] == ownership,
                'stock constructor independently authenticated exactly this predecessor')
        contract = composed_type(type(predecessor))(predecessor, edge, source_root, prior_root)
        contract.live_source_inventory(source_root)
        contract.live_registry(source_root)
        historic = contract.project_tree_bytes(current)
        additions = {p: current[p] for p in contract.added_paths}
        require(contract.advance_tree_bytes(historic, additions) == current,
                'forward/inverse through real stock historical projection')
        yield Qualified(contract, g, candidate_commit)


def intset_edit(raw, old, new, before, after):
    require(type(raw) is bytes and sha(raw) == before, 'IntSet exact input')
    require(raw.count(old) == 1 and new not in raw, 'IntSet unique reviewed edit')
    output = raw.replace(old, new)
    require(sha(output) == after and output.count(new) == 1 and output.replace(new, old) == raw,
            'IntSet exact inverse')
    return output


def parse_intset(git, raw):
    git.commit(ORIGIN, ORIGIN_TREE, [ORIGIN_PARENT])
    git.commit(ORIGIN_PARENT)
    require(git.inventory(ORIGIN_PARENT, {INTSET}) == {INTSET: OLD_INTSET_OID} and
            git.inventory(ORIGIN, {INTSET}) == {INTSET: NEW_INTSET_OID},
            'IntSet authenticated public source edge')
    previous = intset_edit(raw, NEW_CLAUSE, OLD_CLAUSE, NEW_INTSET_SHA, OLD_INTSET_SHA)
    require(oid(raw) == NEW_INTSET_OID and oid(previous) == OLD_INTSET_OID and
            intset_edit(previous, OLD_CLAUSE, NEW_CLAUSE, OLD_INTSET_SHA, NEW_INTSET_SHA) == raw,
            'IntSet exact old/current bytes')
    return previous


def validate_intset_manifest(current_raw, before_raw, old_history_raw, live_intset, git):
    require(sha(before_raw) == BENCHMARK_BEFORE_SHA, 'pinned pre-IntSet manifest')
    require(sha(old_history_raw) == BENCHMARK_HISTORY_SHA, "exact archived benchmark manifest")
    prior = strict_json(before_raw)
    history = strict_json(old_history_raw)
    expected = strict_json(before_raw)
    old = parse_intset(git, live_intset)
    require(prior['pinned_sha256'][INTSET] == history['pinned_sha256'][INTSET] == sha(old),
            'same IntSet on both exact historical source roles')
    expected['pinned_sha256'][INTSET] = sha(live_intset)
    require(json_bytes(strict_json(current_raw)) == json_bytes(expected),
            'only the live IntSet benchmark pin may change')


def benchmark_inputs(root, opened):
    source_root = Path(root).resolve(strict=True)
    stock = pinned_module(source_root, 'tools/release/check_benchmark_transition.py', STOCK_BENCHMARK_SHA)
    before = opened.git.run('cat-file', 'blob', opened.tip + ':' + BENCHMARK)
    require(sha(before) == BENCHMARK_BEFORE_SHA, 'independent pre-IntSet benchmark anchor')
    inputs = (before, *(read(source_root, p) for p in
              (stock.HISTORY, stock.TYPES, stock.OLD_TYPES, stock.STD, stock.MAP)))
    return stock, inputs


def validate_new_benchmark(root, opened, *, new_manifest=None, live_intset=None):
    source_root = Path(root).resolve(strict=True)
    stock, inputs = benchmark_inputs(source_root, opened)
    stock.validate_bridge(*inputs, opened.contract)
    if live_intset is None:
        live_intset = read(source_root, INTSET)
    require(opened.contract.restore_path(live_intset, INTSET) == parse_intset(opened.git, live_intset),
            'actual stock historical IntSet source bytes')
    if new_manifest is None:
        new_manifest = read(source_root, BENCHMARK)
    validate_intset_manifest(new_manifest, inputs[0], inputs[1], live_intset, opened.git)
