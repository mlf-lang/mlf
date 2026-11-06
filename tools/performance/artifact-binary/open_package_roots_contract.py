"""Exact root-bounded open-package source successor of unchanged open-release proof.

This five-file edge binds actual generation output and an independent terminal
recovery check. The original generation wrapper failure remains evidence.
Source projection is not runtime equivalence or toolchain qualification.
"""
from pathlib import Path
import copy
import hashlib
import os
import re
import stat
import types

OPEN_CONTRACT_SHA256 = "7089b03465e76728c4a7d33411687a10014acbd8cdd0b6350685c93cc4904d17"
OPEN_MANIFEST_SHA256 = "e08b52ca94682a5e4343d47a9f5e1e4c158f337f129013ec14dfa24412abe48d"
OPEN_VALUE_SHA256 = "b3f26b6524440e19d0184080ecc2af066a9d9e2a98ea39f7b5846c8f966cadae"
BASE_HEAD = "9ef905033caa654ca07507d8b5ac2363f3207269"
BASE_TREE = "5688ecefcfce0eaa9f79a4ddf39d122f35d8195a"
PARENT_INVENTORY_SHA256 = "939a65293025b6e055c74970eb720b943875036a75c0db5c0c4dde94327b0284"
PARENT_REGISTRY_SHA256 = "bd3aa59b8a3369c3b03a5319c50c1056e791f4e4569bdd7618c6c402275ebced"
CURRENT_INVENTORY_SHA256 = "0e19351adb45a3a71841f946a174505656299a8774a0f497333feebf23b730b7"
CURRENT_REGISTRY_SHA256 = "0bc8a2934cc7b41d2d71e4ede119c4273dbe33bda79175253196939004790b93"
PROVENANCE_VALUE_SHA256 = "a434a47728c7d0f46e8300f87d58a8bb05ddca4146acd907e05d95de053dce54"
IDENTITIES = {"bootstrap/MLF/BuiltinPreludeData.hs": ("3ef159011d588632e27cc03f76461af04615b621b4c51d8f8687e122b5ae5c85", "cec037c459cd0ef0eb057c1593268adf115492feb14d69f4dddcf0be3d860a36",), "libraries/mlf-crates/Bootstrap/ArtifactStructure.hs": ("b2dd0dcb4c99f5e8f1f1932cd0fc4a427a588467c172d2967e1c053ae1fbd0a3", "cfaa0baf223769438241ebc1cd08ea7d91e9fae0eaef6135d513f62564a965d8",), "libraries/mlf-crates/Bootstrap/Bitstream.hs": ("4e140e47bc89281c5956534854e337b9de3edf475f03469ecfafba30a8cabed1", "124dc2e6abcf69f8ae12ae77fca348882c711f3cb930a24b571b01aa1262430f",), "libraries/mlf-crates/Bootstrap/OpenFragment.hs": ("ae14c4563d74eb132a17b911e4fcb5f72d74bd2017be0f4acbd6efd0809e9606", "b3d43f1a3a46b62107b0301e6278225c97dac4477c7c8bb21e981fc887933f4b",), "mlf.lock": ("67a194f6ed737128b55eee971ee6c2092dc6a4181ff075b1b69a900b05b799cf", "3a845410aa2cd8cad95ab421e25d8d0dd0d045627a75ea675b3effd82e49f040",)}
NEW_IDENTITY = "990dd1e310cc42b2a8a5f2aedb64725b6df9c2c00f904e47368a8b03c130faaf"
LITERAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
CHANGED_PATHS = set(IDENTITIES)
CHANGED_MODULES = {"Bootstrap.ArtifactStructure": "libraries/mlf-crates/Bootstrap/ArtifactStructure.hs", "Bootstrap.Bitstream": "libraries/mlf-crates/Bootstrap/Bitstream.hs", "Bootstrap.OpenFragment": "libraries/mlf-crates/Bootstrap/OpenFragment.hs", "MLF.BuiltinPreludeData": "bootstrap/MLF/BuiltinPreludeData.hs"}
MANIFEST_NAME = 'open-package-roots-migration.json'
PROVENANCE_NAME = 'open-package-roots-provenance.json'
FORMAT = 'open-package-roots-source-migration-v1'
VIEW_FORMAT = 'query-graph-with-writer-builtin-open-release-and-package-roots-source-v1'
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


_open_path = Path(__file__).resolve().parent / 'open_release_contract.py'
_open_raw = read_implementation(_open_path)
if hashlib.sha256(_open_raw).hexdigest() != OPEN_CONTRACT_SHA256:
    raise ValueError('fixed predecessor open-release contract implementation SHA')
_OPEN = types.ModuleType('fixed_package_roots_predecessor_open_release_contract')
_OPEN.__file__ = str(_open_path)
exec(compile(_open_raw, str(_open_path), 'exec'), _OPEN.__dict__)
CURRENT_FIELDS = _OPEN.CURRENT_FIELDS | {'open_package_roots_successor'}


def _materialize(predecessor, successor):
    value = copy.deepcopy(predecessor)
    value['format'] = VIEW_FORMAT
    value['source_base_head'], value['source_base_tree'] = successor['base_head'], successor['base_tree']
    value['open_package_roots_successor'] = copy.deepcopy(successor)
    for path, row in successor['transition']['deltas'].items():
        value['current_files'][path] = row['new']
    for name, path in CHANGED_MODULES.items():
        value['current_registry'][name] = successor['transition']['deltas'][path]['new']
    value['current_inventory_sha256'] = successor['current_inventory_sha256']
    value['current_registry_sha256'] = successor['current_registry_sha256']
    return value


class Contract(_OPEN.Contract):
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        if not isinstance(manifest_sha256, str) or re.fullmatch('[0-9a-f]{64}', manifest_sha256) is None:
            raise ValueError('explicit open-package-roots manifest SHA required')
        self._roots_manifest_sha256 = manifest_sha256
        self._initializing_roots = True
        super().__init__(directory, OPEN_MANIFEST_SHA256, history_root, source_root=source_root)
        self._initializing_roots = False
        self.manifest_sha256 = manifest_sha256
        self.open_release_metadata_paths = self.metadata_paths
        names = set(self.metadata_paths) | {'open_package_roots_contract.py', MANIFEST_NAME, PROVENANCE_NAME}
        names.update(row['file'] for row in self.value['open_package_roots_successor']['transition']['deltas'].values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_roots_successor(self, successor):
        c = self._core
        c.require(type(successor) is dict and set(successor) == {
            'format', 'open_contract_sha256', 'open_manifest_sha256', 'open_value_sha256',
            'base_head', 'base_tree', 'module_count', 'primitive_count', 'file_count',
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256', 'transition', 'evidence', 'qualification_scope'
        }, 'open-package-roots manifest fields')
        expected = {
            'format': FORMAT, 'open_contract_sha256': OPEN_CONTRACT_SHA256,
            'open_manifest_sha256': OPEN_MANIFEST_SHA256, 'open_value_sha256': OPEN_VALUE_SHA256,
            'base_head': BASE_HEAD, 'base_tree': BASE_TREE,
            'parent_registry_sha256': PARENT_REGISTRY_SHA256,
            'parent_inventory_sha256': PARENT_INVENTORY_SHA256,
            'current_registry_sha256': CURRENT_REGISTRY_SHA256,
            'current_inventory_sha256': CURRENT_INVENTORY_SHA256, 'qualification_scope': SCOPE
        }
        c.require(all(successor[key] == value for key, value in expected.items()) and
                  all(type(successor[key]) is int and successor[key] == value
                      for key, value in [('module_count', 135), ('primitive_count', 132), ('file_count', 196)]),
                  'open-package-roots identity / unchanged counts / scope')
        edge = successor['transition']
        c.require(type(edge) is dict and set(edge) == {'changed_paths', 'added_paths', 'deltas'} and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and edge['added_paths'] == [] and
                  type(edge['deltas']) is dict and set(edge['deltas']) == CHANGED_PATHS,
                  'exact five-file open-package-roots transition')
        for path, row in edge['deltas'].items():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      c.is_sha(row['sha256']) and (row['old'], row['new']) == IDENTITIES[path],
                      'open-package-roots delta identity')
        evidence = successor['evidence']
        c.require(type(evidence) is dict and set(evidence) == {'file', 'sha256'} and
                  evidence['file'] == PROVENANCE_NAME and c.is_sha(evidence['sha256']),
                  'open-package-roots evidence reference')

    def _validate_manifest(self):
        c = self._core
        initializing = getattr(self, '_initializing_roots', False)
        if initializing:
            _OPEN.Contract._validate_manifest(self)
            raw = c.read_file(self.directory, MANIFEST_NAME, c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == self._roots_manifest_sha256, 'fixed open-package-roots manifest SHA')
            successor = c.strict_json(raw)
            self._validate_roots_successor(successor)
            self.value = _materialize(self.value, successor)
            self._initializing_roots = False
        v = self.value
        c.require(type(v) is dict and set(v) == CURRENT_FIELDS and v['format'] == VIEW_FORMAT,
                  'open-package-roots current view fields')
        successor = v['open_package_roots_successor']
        self._validate_roots_successor(successor)
        c.hash_map(v['current_files'], 'open-package-roots current files')
        c.hash_map(v['current_registry'], 'open-package-roots current registry')
        c.require(CHANGED_PATHS <= set(v['current_files']) and
                  set(CHANGED_MODULES) <= set(v['current_registry']), 'open-package-roots owner inventory')
        predecessor = copy.deepcopy(v)
        del predecessor['open_package_roots_successor']
        predecessor['format'] = _OPEN.VIEW_FORMAT
        predecessor['source_base_head'], predecessor['source_base_tree'] = _OPEN.BASE_HEAD, _OPEN.BASE_TREE
        for path, row in successor['transition']['deltas'].items():
            predecessor['current_files'][path] = row['old']
        for name, path in CHANGED_MODULES.items():
            predecessor['current_registry'][name] = IDENTITIES[path][0]
        predecessor['current_inventory_sha256'] = PARENT_INVENTORY_SHA256
        predecessor['current_registry_sha256'] = PARENT_REGISTRY_SHA256
        c.require(c.canonical_sha(predecessor) == OPEN_VALUE_SHA256, 'complete unchanged predecessor open-release value')
        trial = object.__new__(_OPEN.Contract)
        trial._core, trial.frozen_value, trial.value = c, self.frozen_value, predecessor
        _OPEN.Contract._validate_manifest(trial)
        c.require(v == _materialize(predecessor, successor) and
                  c.canonical_sha(v['current_files']) == CURRENT_INVENTORY_SHA256 and
                  c.canonical_sha(v['current_registry']) == CURRENT_REGISTRY_SHA256 and
                  all(v['current_files'][path] == v['current_registry'][name]
                      for name, path in v['module_paths'].items()),
                  'exact complete open-package-roots current source identity')
        self._validate_rows(successor['transition']['deltas'], CHANGED_PATHS,
                            predecessor['current_files'], v['current_files'], 'open-package-roots-deltas/')
        self.open_release_value = predecessor
        self.builtin_value, self.writer_value, self.graph_value = trial.builtin_value, trial.writer_value, trial.graph_value
        if initializing:
            reference = successor['evidence']
            raw = c.read_file(self.directory, reference['file'], c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == reference['sha256'], 'fixed open-package-roots evidence SHA')
            self.open_package_roots_generation_evidence = c.strict_json(raw)
            self._validate_roots_provenance_record(self.open_package_roots_generation_evidence)

    def _validate_roots_provenance_record(self, value):
        # Do not override either historical provenance hook during initialization.
        c = self._core
        c.require(type(value) is dict and c.canonical_sha(value) == PROVENANCE_VALUE_SHA256,
                  'complete reviewed actual open-package-roots generation and recovery summary')
        source, comparison = value['source'], value['comparison']
        c.require(source['base_head'] == BASE_HEAD and source['base_tree'] == BASE_TREE and
                  source['identity'] == 'builtin-source-v1:' + NEW_IDENTITY and
                  c.canonical_sha(source['identity_inputs']) == NEW_IDENTITY and
                  comparison['old']['sha256'] == IDENTITIES[LITERAL][0] and
                  comparison['generated']['sha256'] == IDENTITIES[LITERAL][1],
                  'actual generation evidence / open-package-roots source edge')
        c.require(all(self.value['current_files'][row['path']] == row['sha256']
                      for row in source['compiled_sources'].values()) and
                  all(self.value['current_files'][path] == row['sha256']
                      for path, row in source['overlay'].items()),
                  'actual compiled source and overlay binding')
        c.require(value['collector']['generation_body_complete'] is True and
                  value['collector']['wrapper_complete'] is False and
                  value['wrapper_failure']['exit_code'] == 1 and
                  value['recovery']['complete'] is True and
                  value['recovery']['original_wrapper_exit'] == 1 and
                  value['recovery']['actual_command_exits'] == [0, 0, 0] and
                  value['recovery']['complete_stdout_matches_literal'] is True and
                  value['recovery']['generation_receipt'] == {
                      key: value['receipt'][key] for key in ('bytes', 'sha256')},
                  'original failed wrapper and independent output recovery remain distinct')

    def _open_proxy(self):
        trial = object.__new__(_OPEN.Contract)
        trial._core, trial.directory = self._core, self.directory
        trial.frozen_value, trial.value = self.frozen_value, self.open_release_value
        trial.builtin_value = self.builtin_value
        trial.writer_value, trial.graph_value = self.writer_value, self.graph_value
        return trial

    def _to_open(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full open-package-roots current path SHA: ' + path)
        rows = self.value['open_package_roots_successor']['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _from_open(self, raw, path):
        c = self._core
        c.require(path in self.open_release_value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.open_release_value['current_files'][path], 'full predecessor open-release path SHA: ' + path)
        rows = self.value['open_package_roots_successor']['transition']['deltas']
        return self._apply(raw, path, rows, False) if path in rows else raw

    def _to_builtin(self, raw, path):
        return self._open_proxy()._to_builtin(self._to_open(raw, path), path)

    def _to_writer(self, raw, path):
        return self._open_proxy()._to_writer(self._to_open(raw, path), path)

    def _to_frozen(self, raw, path):
        return self._open_proxy()._to_frozen(self._to_open(raw, path), path)

    def _from_frozen(self, raw, path):
        return self._from_open(self._open_proxy()._from_frozen(raw, path), path)

    def _validate_roots_literal(self, predecessor_raw, current_raw):
        c = self._core
        c.require(type(predecessor_raw) is bytes and c.sha(predecessor_raw) == IDENTITIES[LITERAL][0] and
                  type(current_raw) is bytes, 'exact predecessor open-release literal')
        matches = list(re.finditer(rb'builtin-source-v1:([0-9a-f]{64})', predecessor_raw))
        c.require(len(matches) == 1 and matches[0].span(1) == (776, 840) and
                  matches[0].group(1) == _OPEN.NEW_IDENTITY.encode('ascii') and
                  len(predecessor_raw) == 2219103 and
                  current_raw == predecessor_raw[:776] + NEW_IDENTITY.encode('ascii') + predecessor_raw[840:],
                  'literal changed beyond actual generation identity-only delta')

    def _validate_roots_lock(self, predecessor_raw, current_raw):
        c = self._core
        c.require(type(predecessor_raw) is bytes and c.sha(predecessor_raw) == IDENTITIES['mlf.lock'][0],
                  'exact predecessor open-release lock')
        expected = c.strict_json(predecessor_raw)
        seen = set()
        for package in expected['packages']:
            for name, digest in package['sources'].items():
                path = c.lock_path(package['path'], name)
                if path in CHANGED_PATHS - {'mlf.lock'}:
                    c.require(path not in seen and digest == IDENTITIES[path][0], 'unique predecessor lock owner')
                    package['sources'][name] = IDENTITIES[path][1]
                    seen.add(path)
        c.require(seen == CHANGED_PATHS - {'mlf.lock'} and c.strict_json(current_raw) == expected,
                  'lock changed beyond exactly four source hashes')

    def _validate_metadata_transition(self, frozen, current):
        c = self._core
        c.require(type(current) is dict and CHANGED_PATHS <= set(current), 'open-package-roots metadata inputs')
        predecessor = dict(current)
        for path in CHANGED_PATHS:
            predecessor[path] = self._to_open(current[path], path)
        self._validate_roots_literal(predecessor[LITERAL], current[LITERAL])
        self._validate_roots_lock(predecessor['mlf.lock'], current['mlf.lock'])
        self._open_proxy()._validate_metadata_transition(frozen, predecessor)
