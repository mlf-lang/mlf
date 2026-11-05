"""Exact actual-O0 builtin successor of the unchanged writer/graph/frozen bridge.

This source contract authenticates a separately reviewed, portable summary of
real CI generator output. It does not rerun generation, qualify the incomplete
producer, or rewrite any historical generation receipt. Only the live literal
and its one lock hash advance. ``writer_value`` retains the original writer
view, including its original source-base semantics.
"""
from pathlib import Path
import copy
import hashlib
import os
import re
import stat
import types

WRITER_CONTRACT_SHA256 = 'd0bd6478e7ffe525a72e1f6d0053e86a8773a133913297df335d0cf67407510c'
WRITER_MANIFEST_SHA256 = '0919d3dbe4e5acde7efd63737803fec6e58d092639faa43367930c559c931cf6'
WRITER_VALUE_SHA256 = '55d2e6cb8277b60763131372f9c4c7dcfdbf57eb61eb47c264f2d8fdc60d1778'
BASE_HEAD = 'aa661e80f159d4851f05b71bbf77fa868da23b7e'
BASE_TREE = '8fd27c3bd6b715b8be00b731cf974a6bd35e269a'
PARENT_INVENTORY_SHA256 = '0f8ea1134f6604f57529733329ed9df774fd06f92930e893e0381a6879b9b6b8'
PARENT_REGISTRY_SHA256 = 'fef91be4eb4359680920dcb395ece28526c3fe6e2d2b51b0c77d1c3ae507ec95'
CURRENT_INVENTORY_SHA256 = '46b45c12e78a56b3fd134270b927fee336b7755e4ac47ad2dcbe440a4a3dd422'
CURRENT_REGISTRY_SHA256 = '0a4872f55933ae158cf76735bfe05c00ac7368c0ed38887638a43d244ab715d1'
OLD_LITERAL_SHA256 = '02481fb9c2460ab5e2ca6577416ffc36b66085dc95bd04df491d9c14ce610f56'
ACTUAL_LITERAL_SHA256 = 'f5ec5f115ed013bc40993039f02249eb809c5aa1ecf22d0c39bc4564a8c73e78'
OLD_LOCK_SHA256 = '48df44dfebb7b382dd0427e77395a3fce2fb2dae870aa1b8476a96bc9a1901d1'
CURRENT_LOCK_SHA256 = '531c9b120eb85e1a66f90d4bc8a10cc9c537e7ac052063a0ab76f0a5336aeaae'
OLD_IDENTITY = '6252afcb6e2ee3fd333ed6ebce6c672996bf282caca3a1d2187903dd2828a21e'
NEW_IDENTITY = '8a985e28c3b29d21bdd5d50a488d85fec7f0608a01d8905ae4f45dde3599f74e'
PROVENANCE_VALUE_SHA256 = 'bc7642ea0d5fc9a4765b588fca88ebef3556f160c2821615024d8d8b8e0c87eb'
LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
LITERAL_MODULE = 'MLF.BuiltinPreludeData'
CHANGED_PATHS = {LITERAL, 'mlf.lock'}
MANIFEST_NAME = 'builtin-regeneration-migration.json'
PROVENANCE_NAME = 'builtin-regeneration-provenance.json'
FORMAT = 'builtin-regeneration-source-migration-v1'
VIEW_FORMAT = 'query-graph-with-writer-and-builtin-regeneration-source-v1'
SCOPE = 'Source identity and reversible projection only; no new runtime or generation qualification.'
CURRENT_FIELDS = {
    'format', 'frozen_manifest_sha256', 'graph_source_head', 'source_base_head',
    'source_base_tree', 'module_paths', 'module_count', 'primitive_count',
    'current_registry', 'current_registry_sha256', 'current_files',
    'current_inventory_sha256', 'transition', 'maintenance', 'qualification_scope',
    'successor', 'builtin_successor'
}


def read_implementation(path):
    """Preserve the bounded regular-file/no-file-link implementation gate."""
    descriptor = None
    try:
        if path.is_symlink():
            raise ValueError('source implementation symlink')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                             getattr(os, 'O_NONBLOCK', 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise ValueError('source implementation regular-file / byte bound')
        raw = os.read(descriptor, 65537)
        if len(raw) > 65536:
            raise ValueError('source implementation grew past byte bound')
        return raw
    except OSError as error:
        raise ValueError('source implementation read failed') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


_writer_path = Path(__file__).resolve().parent / 'writer_preflight_contract.py'
_writer_raw = read_implementation(_writer_path)
if hashlib.sha256(_writer_raw).hexdigest() != WRITER_CONTRACT_SHA256:
    raise ValueError('fixed predecessor writer contract implementation SHA')
_WRITER = types.ModuleType('fixed_builtin_predecessor_writer_contract')
_WRITER.__file__ = str(_writer_path)
exec(compile(_writer_raw, str(_writer_path), 'exec'), _WRITER.__dict__)


def _materialize(writer, successor):
    value = copy.deepcopy(writer)
    value['format'] = VIEW_FORMAT
    value['source_base_head'] = successor['base_head']
    value['source_base_tree'] = successor['base_tree']
    value['builtin_successor'] = copy.deepcopy(successor)
    for path, row in successor['transition']['deltas'].items():
        value['current_files'][path] = row['new']
    value['current_registry'][LITERAL_MODULE] = successor['transition']['deltas'][LITERAL]['new']
    value['current_inventory_sha256'] = successor['current_inventory_sha256']
    value['current_registry_sha256'] = successor['current_registry_sha256']
    return value


class Contract(_WRITER.Contract):
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        if not isinstance(manifest_sha256, str) or re.fullmatch('[0-9a-f]{64}', manifest_sha256) is None:
            raise ValueError('explicit builtin-regeneration manifest SHA required')
        self._builtin_manifest_sha256 = manifest_sha256
        self._initializing_builtin = True
        super().__init__(directory, WRITER_MANIFEST_SHA256, history_root, source_root=source_root)
        self._initializing_builtin = False
        self.manifest_sha256 = manifest_sha256
        self.writer_metadata_paths = self.metadata_paths
        names = set(self.metadata_paths) | {'builtin_regeneration_contract.py', MANIFEST_NAME, PROVENANCE_NAME}
        names.update(row['file'] for row in self.value['builtin_successor']['transition']['deltas'].values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_builtin_successor(self, successor):
        c = self._core
        c.require(type(successor) is dict and set(successor) == {
            'format', 'writer_contract_sha256', 'writer_manifest_sha256', 'writer_value_sha256',
            'base_head', 'base_tree', 'module_count', 'primitive_count', 'file_count',
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256', 'transition', 'evidence', 'qualification_scope'
        }, 'builtin-regeneration manifest fields')
        expected = {
            'format': FORMAT, 'writer_contract_sha256': WRITER_CONTRACT_SHA256,
            'writer_manifest_sha256': WRITER_MANIFEST_SHA256, 'writer_value_sha256': WRITER_VALUE_SHA256,
            'base_head': BASE_HEAD, 'base_tree': BASE_TREE,
            'parent_registry_sha256': PARENT_REGISTRY_SHA256,
            'parent_inventory_sha256': PARENT_INVENTORY_SHA256,
            'current_registry_sha256': CURRENT_REGISTRY_SHA256,
            'current_inventory_sha256': CURRENT_INVENTORY_SHA256, 'qualification_scope': SCOPE
        }
        c.require(all(successor[key] == value for key, value in expected.items()) and
                  all(type(successor[key]) is int and successor[key] == value
                      for key, value in [('module_count', 135), ('primitive_count', 132), ('file_count', 196)]),
                  'builtin-regeneration identity / unchanged counts / scope')
        edge = successor['transition']
        c.require(type(edge) is dict and set(edge) == {'changed_paths', 'added_paths', 'deltas'} and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and edge['added_paths'] == [] and
                  type(edge['deltas']) is dict and set(edge['deltas']) == CHANGED_PATHS,
                  'exact two-file builtin-regeneration transition')
        identities = {LITERAL: (OLD_LITERAL_SHA256, ACTUAL_LITERAL_SHA256),
                      'mlf.lock': (OLD_LOCK_SHA256, CURRENT_LOCK_SHA256)}
        for path, row in edge['deltas'].items():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      c.is_sha(row['sha256']) and (row['old'], row['new']) == identities[path],
                      'builtin-regeneration delta identity')
        evidence = successor['evidence']
        c.require(type(evidence) is dict and set(evidence) == {'file', 'sha256'} and
                  evidence['file'] == PROVENANCE_NAME and c.is_sha(evidence['sha256']),
                  'builtin-regeneration evidence reference')

    def _validate_manifest(self):
        c = self._core
        initializing = getattr(self, '_initializing_builtin', False)
        if initializing:
            # This uses the unchanged writer hook, not a repinned historical view.
            _WRITER.Contract._validate_manifest(self)
            raw = c.read_file(self.directory, MANIFEST_NAME, c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == self._builtin_manifest_sha256, 'fixed builtin-regeneration manifest SHA')
            successor = c.strict_json(raw)
            self._validate_builtin_successor(successor)
            self.value = _materialize(self.value, successor)
            self._initializing_builtin = False
        v = self.value
        c.require(type(v) is dict and set(v) == CURRENT_FIELDS and v['format'] == VIEW_FORMAT,
                  'builtin-regeneration current view fields')
        successor = v['builtin_successor']
        self._validate_builtin_successor(successor)
        c.hash_map(v['current_files'], 'builtin current files')
        c.hash_map(v['current_registry'], 'builtin current registry')
        c.require(CHANGED_PATHS <= set(v['current_files']) and LITERAL_MODULE in v['current_registry'],
                  'builtin current owner inventory')
        writer = copy.deepcopy(v)
        del writer['builtin_successor']
        writer['format'] = _WRITER.VIEW_FORMAT
        writer['source_base_head'], writer['source_base_tree'] = _WRITER.BASE_HEAD, _WRITER.BASE_TREE
        for path, row in successor['transition']['deltas'].items():
            writer['current_files'][path] = row['old']
        writer['current_registry'][LITERAL_MODULE] = OLD_LITERAL_SHA256
        writer['current_inventory_sha256'] = successor['parent_inventory_sha256']
        writer['current_registry_sha256'] = successor['parent_registry_sha256']
        c.require(c.canonical_sha(writer) == WRITER_VALUE_SHA256, 'complete unchanged predecessor writer value')
        trial = object.__new__(_WRITER.Contract)
        trial._core, trial.frozen_value, trial.value = c, self.frozen_value, writer
        _WRITER.Contract._validate_manifest(trial)
        c.require(v == _materialize(writer, successor) and
                  c.canonical_sha(v['current_files']) == CURRENT_INVENTORY_SHA256 and
                  c.canonical_sha(v['current_registry']) == CURRENT_REGISTRY_SHA256,
                  'exact complete builtin-regeneration current source identity')
        self._validate_rows(successor['transition']['deltas'], CHANGED_PATHS,
                            writer['current_files'], v['current_files'], 'builtin-regeneration-deltas/')
        self.writer_value, self.graph_value = writer, trial.graph_value
        if initializing:
            reference = successor['evidence']
            raw = c.read_file(self.directory, reference['file'], c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == reference['sha256'], 'fixed builtin-regeneration evidence SHA')
            self.generation_evidence = c.strict_json(raw)
            self._validate_provenance_record(self.generation_evidence)

    def _validate_provenance_record(self, value):
        c = self._core
        # The small portable summary is pinned as a complete reviewed value.
        # Its raw archive/entry hashes refer to real CI evidence; this is not
        # a signature, a successful verifier receipt, or a generation rerun.
        c.require(type(value) is dict and c.canonical_sha(value) == PROVENANCE_VALUE_SHA256,
                  'complete reviewed actual-O0 provenance summary')
        rows = self.value['builtin_successor']['transition']['deltas']
        c.require(value['source']['head'] == BASE_HEAD and value['source']['tree'] == BASE_TREE and
                  value['comparison']['canonical_sha256'] == rows[LITERAL]['old'] and
                  value['comparison']['generated_sha256'] == rows[LITERAL]['new'],
                  'actual generation evidence / source-edge binding')

    def _writer_proxy(self):
        trial = object.__new__(_WRITER.Contract)
        trial._core, trial.directory = self._core, self.directory
        trial.frozen_value, trial.value = self.frozen_value, self.writer_value
        return trial

    def _to_writer(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full builtin current path SHA: ' + path)
        rows = self.value['builtin_successor']['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _to_frozen(self, raw, path):
        return self._writer_proxy()._to_frozen(self._to_writer(raw, path), path)

    def _from_frozen(self, raw, path):
        result = self._writer_proxy()._from_frozen(raw, path)
        rows = self.value['builtin_successor']['transition']['deltas']
        return self._apply(result, path, rows, False) if path in rows else result

    def _validate_builtin_literal(self, writer_raw, current_raw):
        c = self._core
        c.require(type(writer_raw) is bytes and c.sha(writer_raw) == OLD_LITERAL_SHA256 and
                  type(current_raw) is bytes, 'exact predecessor builtin literal')
        matches = list(re.finditer(rb'builtin-source-v1:([0-9a-f]{64})', writer_raw))
        c.require(len(matches) == 1 and matches[0].span(1) == (776, 840) and
                  matches[0].group(1) == OLD_IDENTITY.encode('ascii') and
                  len(writer_raw) == 2219103 and
                  current_raw == writer_raw[:776] + NEW_IDENTITY.encode('ascii') + writer_raw[840:],
                  'builtin changed beyond actual-generation identity-only delta')

    def _validate_builtin_lock(self, writer_raw, current_raw):
        c = self._core
        c.require(type(writer_raw) is bytes and c.sha(writer_raw) == OLD_LOCK_SHA256,
                  'exact predecessor writer lock')
        expected = c.strict_json(writer_raw)
        packages = [row for row in expected['packages'] if row['path'] == '.']
        c.require(len(packages) == 1 and packages[0]['sources'].get(LITERAL) == OLD_LITERAL_SHA256,
                  'unique predecessor builtin lock entry')
        packages[0]['sources'][LITERAL] = ACTUAL_LITERAL_SHA256
        c.require(c.strict_json(current_raw) == expected, 'lock changed beyond exactly one builtin source hash')

    def _validate_metadata_transition(self, frozen, current):
        c = self._core
        c.require(type(current) is dict and CHANGED_PATHS <= set(current), 'builtin metadata transition inputs')
        writer = dict(current)
        for path in CHANGED_PATHS:
            writer[path] = self._to_writer(current[path], path)
        self._validate_builtin_literal(writer[LITERAL], current[LITERAL])
        self._validate_builtin_lock(writer['mlf.lock'], current['mlf.lock'])
        self._writer_proxy()._validate_metadata_transition(frozen, writer)
