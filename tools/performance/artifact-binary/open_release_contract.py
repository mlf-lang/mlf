"""Exact open-release successor of the unchanged builtin/writer/graph bridge.

The four-file edge binds actual generation-only evidence. Historical values and
receipts keep their original meanings. Source projection is not runtime
equivalence, a generation rerun, or toolchain qualification.
"""
from pathlib import Path
import copy
import hashlib
import os
import re
import stat
import types

BUILTIN_CONTRACT_SHA256 = '80ab586aed593698fc60f1644e8f0b4b24fc5d33140e7da60675ee5cf6677c19'
BUILTIN_MANIFEST_SHA256 = 'fb8335e198e463d3a25b336f124d56dac141c6ad2063df531c09ade8e7411559'
BUILTIN_VALUE_SHA256 = '804ffd40e4b87d835d388291d11fa982bf58845b19c3e7a5c914d30ed36b30a2'
BASE_HEAD = 'eea644f405f90a81a6a81982570bb82fdf425c34'
BASE_TREE = '21fd8a08c26a350560f63bdb76c7c72ac47bbda0'
PARENT_INVENTORY_SHA256 = '46b45c12e78a56b3fd134270b927fee336b7755e4ac47ad2dcbe440a4a3dd422'
PARENT_REGISTRY_SHA256 = '0a4872f55933ae158cf76735bfe05c00ac7368c0ed38887638a43d244ab715d1'
CURRENT_INVENTORY_SHA256 = '939a65293025b6e055c74970eb720b943875036a75c0db5c0c4dde94327b0284'
CURRENT_REGISTRY_SHA256 = 'bd3aa59b8a3369c3b03a5319c50c1056e791f4e4569bdd7618c6c402275ebced'
PROVENANCE_VALUE_SHA256 = 'c2bf8122103f6f0b9cf0a232537c6133fcf4083cf0e6e2537b4e775a9b758156'
IDENTITIES = {'bootstrap/MLF/BuiltinPreludeData.hs': ('f5ec5f115ed013bc40993039f02249eb809c5aa1ecf22d0c39bc4564a8c73e78', '3ef159011d588632e27cc03f76461af04615b621b4c51d8f8687e122b5ae5c85'), 'libraries/mlf-crates/Bootstrap/CrateArtifact.hs': ('d13d59ed310bb8ef447596437516cfadbbbb025da632b18930e2b4263ac97826', 'c9d33e20985b3a9b6ec34733f024e5378388799d5cf5f68bbbce13242e886453'), 'libraries/mlf-package-core/Package/Release.hs': ('36339e780160c328cf6b4a5cc2d2391c6b166f8bc6c53319cace55ea312801d3', '0b23919bb1f3047a222fd8efec0da951d5b1f6e2a3d1bb69d093a9db0ccb9a4e'), 'mlf.lock': ('531c9b120eb85e1a66f90d4bc8a10cc9c537e7ac052063a0ab76f0a5336aeaae', '67a194f6ed737128b55eee971ee6c2092dc6a4181ff075b1b69a900b05b799cf')}
NEW_IDENTITY = 'e32f8eaa793ae00d5d6a9342be6278604a487cea3dd9f2a19adb387e2ec202af'
LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
CHANGED_PATHS = set(IDENTITIES)
CHANGED_MODULES = {'Bootstrap.CrateArtifact': 'libraries/mlf-crates/Bootstrap/CrateArtifact.hs', 'MLF.BuiltinPreludeData': 'bootstrap/MLF/BuiltinPreludeData.hs', 'Package.Release': 'libraries/mlf-package-core/Package/Release.hs'}
MANIFEST_NAME = 'open-release-migration.json'
PROVENANCE_NAME = 'open-release-provenance.json'
FORMAT = 'open-release-source-migration-v1'
VIEW_FORMAT = 'query-graph-with-writer-builtin-and-open-release-source-v1'
SCOPE = 'Source identity and reversible projection only; no new runtime or generation qualification.'


def read_implementation(path):
    """Bounded regular-file reader; never follow a file link or block on a FIFO."""
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


_builtin_path = Path(__file__).resolve().parent / 'builtin_regeneration_contract.py'
_builtin_raw = read_implementation(_builtin_path)
if hashlib.sha256(_builtin_raw).hexdigest() != BUILTIN_CONTRACT_SHA256:
    raise ValueError('fixed predecessor builtin contract implementation SHA')
_BUILTIN = types.ModuleType('fixed_open_release_predecessor_builtin_contract')
_BUILTIN.__file__ = str(_builtin_path)
exec(compile(_builtin_raw, str(_builtin_path), 'exec'), _BUILTIN.__dict__)
CURRENT_FIELDS = _BUILTIN.CURRENT_FIELDS | {'open_release_successor'}


def _materialize(builtin, successor):
    value = copy.deepcopy(builtin)
    value['format'] = VIEW_FORMAT
    value['source_base_head'], value['source_base_tree'] = successor['base_head'], successor['base_tree']
    value['open_release_successor'] = copy.deepcopy(successor)
    for path, row in successor['transition']['deltas'].items():
        value['current_files'][path] = row['new']
    for name, path in CHANGED_MODULES.items():
        value['current_registry'][name] = successor['transition']['deltas'][path]['new']
    value['current_inventory_sha256'] = successor['current_inventory_sha256']
    value['current_registry_sha256'] = successor['current_registry_sha256']
    return value


class Contract(_BUILTIN.Contract):
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        if not isinstance(manifest_sha256, str) or re.fullmatch('[0-9a-f]{64}', manifest_sha256) is None:
            raise ValueError('explicit open-release manifest SHA required')
        self._open_manifest_sha256 = manifest_sha256
        self._initializing_open = True
        # The validation hook installs the complete current view before admission.
        super().__init__(directory, BUILTIN_MANIFEST_SHA256, history_root, source_root=source_root)
        self._initializing_open = False
        self.manifest_sha256 = manifest_sha256
        self.builtin_metadata_paths = self.metadata_paths
        names = set(self.metadata_paths) | {'open_release_contract.py', MANIFEST_NAME, PROVENANCE_NAME}
        names.update(row['file'] for row in self.value['open_release_successor']['transition']['deltas'].values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_open_successor(self, successor):
        c = self._core
        c.require(type(successor) is dict and set(successor) == {
            'format', 'builtin_contract_sha256', 'builtin_manifest_sha256', 'builtin_value_sha256',
            'base_head', 'base_tree', 'module_count', 'primitive_count', 'file_count',
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256', 'transition', 'evidence', 'qualification_scope'
        }, 'open-release manifest fields')
        expected = {
            'format': FORMAT, 'builtin_contract_sha256': BUILTIN_CONTRACT_SHA256,
            'builtin_manifest_sha256': BUILTIN_MANIFEST_SHA256, 'builtin_value_sha256': BUILTIN_VALUE_SHA256,
            'base_head': BASE_HEAD, 'base_tree': BASE_TREE,
            'parent_registry_sha256': PARENT_REGISTRY_SHA256,
            'parent_inventory_sha256': PARENT_INVENTORY_SHA256,
            'current_registry_sha256': CURRENT_REGISTRY_SHA256,
            'current_inventory_sha256': CURRENT_INVENTORY_SHA256, 'qualification_scope': SCOPE
        }
        c.require(all(successor[key] == value for key, value in expected.items()) and
                  all(type(successor[key]) is int and successor[key] == value
                      for key, value in [('module_count', 135), ('primitive_count', 132), ('file_count', 196)]),
                  'open-release identity / unchanged counts / scope')
        edge = successor['transition']
        c.require(type(edge) is dict and set(edge) == {'changed_paths', 'added_paths', 'deltas'} and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and edge['added_paths'] == [] and
                  type(edge['deltas']) is dict and set(edge['deltas']) == CHANGED_PATHS,
                  'exact four-file open-release transition')
        for path, row in edge['deltas'].items():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      c.is_sha(row['sha256']) and (row['old'], row['new']) == IDENTITIES[path],
                      'open-release delta identity')
        evidence = successor['evidence']
        c.require(type(evidence) is dict and set(evidence) == {'file', 'sha256'} and
                  evidence['file'] == PROVENANCE_NAME and c.is_sha(evidence['sha256']),
                  'open-release evidence reference')

    def _validate_manifest(self):
        c = self._core
        initializing = getattr(self, '_initializing_open', False)
        if initializing:
            _BUILTIN.Contract._validate_manifest(self)
            raw = c.read_file(self.directory, MANIFEST_NAME, c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == self._open_manifest_sha256, 'fixed open-release manifest SHA')
            successor = c.strict_json(raw)
            self._validate_open_successor(successor)
            self.value = _materialize(self.value, successor)
            self._initializing_open = False
        v = self.value
        c.require(type(v) is dict and set(v) == CURRENT_FIELDS and v['format'] == VIEW_FORMAT,
                  'open-release current view fields')
        successor = v['open_release_successor']
        self._validate_open_successor(successor)
        c.hash_map(v['current_files'], 'open-release current files')
        c.hash_map(v['current_registry'], 'open-release current registry')
        c.require(CHANGED_PATHS <= set(v['current_files']) and
                  set(CHANGED_MODULES) <= set(v['current_registry']), 'open-release owner inventory')
        builtin = copy.deepcopy(v)
        del builtin['open_release_successor']
        builtin['format'] = _BUILTIN.VIEW_FORMAT
        builtin['source_base_head'], builtin['source_base_tree'] = _BUILTIN.BASE_HEAD, _BUILTIN.BASE_TREE
        for path, row in successor['transition']['deltas'].items():
            builtin['current_files'][path] = row['old']
        for name, path in CHANGED_MODULES.items():
            builtin['current_registry'][name] = IDENTITIES[path][0]
        builtin['current_inventory_sha256'] = PARENT_INVENTORY_SHA256
        builtin['current_registry_sha256'] = PARENT_REGISTRY_SHA256
        c.require(c.canonical_sha(builtin) == BUILTIN_VALUE_SHA256, 'complete unchanged predecessor builtin value')
        trial = object.__new__(_BUILTIN.Contract)
        trial._core, trial.frozen_value, trial.value = c, self.frozen_value, builtin
        _BUILTIN.Contract._validate_manifest(trial)
        c.require(v == _materialize(builtin, successor) and
                  c.canonical_sha(v['current_files']) == CURRENT_INVENTORY_SHA256 and
                  c.canonical_sha(v['current_registry']) == CURRENT_REGISTRY_SHA256 and
                  all(v['current_files'][path] == v['current_registry'][name]
                      for name, path in v['module_paths'].items()),
                  'exact complete open-release current source identity')
        self._validate_rows(successor['transition']['deltas'], CHANGED_PATHS,
                            builtin['current_files'], v['current_files'], 'open-release-deltas/')
        self.builtin_value = builtin
        self.writer_value, self.graph_value = trial.writer_value, trial.graph_value
        if initializing:
            reference = successor['evidence']
            raw = c.read_file(self.directory, reference['file'], c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == reference['sha256'], 'fixed open-release evidence SHA')
            self.open_release_generation_evidence = c.strict_json(raw)
            self._validate_open_release_provenance_record(self.open_release_generation_evidence)

    def _validate_open_release_provenance_record(self, value):
        # Do not override _validate_provenance_record: builtin initialization
        # dispatches that validator for its genuine historical evidence.
        c = self._core
        c.require(type(value) is dict and c.canonical_sha(value) == PROVENANCE_VALUE_SHA256,
                  'complete reviewed actual open-release generation summary')
        source, comparison = value['source'], value['comparison']
        c.require(source['base_head'] == BASE_HEAD and source['base_tree'] == BASE_TREE and
                  source['identity'] == 'builtin-source-v1:' + NEW_IDENTITY and
                  c.canonical_sha(source['identity_inputs']) == NEW_IDENTITY and
                  comparison['old']['sha256'] == IDENTITIES[LITERAL][0] and
                  comparison['generated']['sha256'] == IDENTITIES[LITERAL][1],
                  'actual generation evidence / open-release source edge')
        c.require(all(self.value['current_files'][row['path']] == row['sha256']
                      for row in source['compiled_sources'].values()) and
                  all(self.value['current_files'][path] == row['sha256']
                      for path, row in source['overlay'].items()),
                  'actual compiled source and overlay binding')

    def _builtin_proxy(self):
        trial = object.__new__(_BUILTIN.Contract)
        trial._core, trial.directory = self._core, self.directory
        trial.frozen_value, trial.value = self.frozen_value, self.builtin_value
        trial.writer_value, trial.graph_value = self.writer_value, self.graph_value
        return trial

    def _to_builtin(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full open-release current path SHA: ' + path)
        rows = self.value['open_release_successor']['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _to_writer(self, raw, path):
        return self._builtin_proxy()._to_writer(self._to_builtin(raw, path), path)

    def _to_frozen(self, raw, path):
        return self._builtin_proxy()._to_frozen(self._to_builtin(raw, path), path)

    def _from_frozen(self, raw, path):
        result = self._builtin_proxy()._from_frozen(raw, path)
        rows = self.value['open_release_successor']['transition']['deltas']
        return self._apply(result, path, rows, False) if path in rows else result

    def _validate_open_literal(self, builtin_raw, current_raw):
        c = self._core
        c.require(type(builtin_raw) is bytes and c.sha(builtin_raw) == IDENTITIES[LITERAL][0] and
                  type(current_raw) is bytes, 'exact predecessor builtin literal')
        matches = list(re.finditer(rb'builtin-source-v1:([0-9a-f]{64})', builtin_raw))
        c.require(len(matches) == 1 and matches[0].span(1) == (776, 840) and
                  matches[0].group(1) == _BUILTIN.NEW_IDENTITY.encode('ascii') and
                  len(builtin_raw) == 2219103 and
                  current_raw == builtin_raw[:776] + NEW_IDENTITY.encode('ascii') + builtin_raw[840:],
                  'literal changed beyond actual generation identity-only delta')

    def _validate_open_lock(self, builtin_raw, current_raw):
        c = self._core
        c.require(type(builtin_raw) is bytes and c.sha(builtin_raw) == IDENTITIES['mlf.lock'][0],
                  'exact predecessor builtin lock')
        expected = c.strict_json(builtin_raw)
        seen = set()
        for package in expected['packages']:
            for name, digest in package['sources'].items():
                path = c.lock_path(package['path'], name)
                if path in CHANGED_PATHS - {'mlf.lock'}:
                    c.require(path not in seen and digest == IDENTITIES[path][0], 'unique predecessor lock owner')
                    package['sources'][name] = IDENTITIES[path][1]
                    seen.add(path)
        c.require(seen == CHANGED_PATHS - {'mlf.lock'} and c.strict_json(current_raw) == expected,
                  'lock changed beyond exactly three source hashes')

    def _validate_metadata_transition(self, frozen, current):
        c = self._core
        c.require(type(current) is dict and CHANGED_PATHS <= set(current), 'open-release metadata inputs')
        builtin = dict(current)
        for path in CHANGED_PATHS:
            builtin[path] = self._to_builtin(current[path], path)
        self._validate_open_literal(builtin[LITERAL], current[LITERAL])
        self._validate_open_lock(builtin['mlf.lock'], current['mlf.lock'])
        self._builtin_proxy()._validate_metadata_transition(frozen, builtin)
