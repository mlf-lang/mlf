"""Exact writer-preflight successor of the unchanged graph135 source bridge.

The small successor manifest authenticates two changed files, not new runtime
measurements or builtin generation. ``value`` is a materialized current view:
its ``transition`` and ``maintenance`` retain the historical graph edge, while
``successor`` records the additional two-file edge. The old source_head is
explicitly named graph_source_head; source_base_head/tree identify the reviewed
Git base, not a commit claimed to contain the repaired bytes.

This module is loaded only by the explicitly called, author-pinned live loader.
The historical graph implementation is independently pinned before execution.
"""
from pathlib import Path
import copy
import hashlib
import os
import stat
import types

GRAPH_CONTRACT_SHA256 = 'e41fb3ac880e2f53872de56571918b0c26409998fe771f2547f37da8271cf682'
GRAPH_MANIFEST_SHA256 = '71532df8a848c84d9803c3aa4b9adba65fcb53c90a56e7551a5c6555b2dc00be'
GRAPH_VALUE_SHA256 = '16570e0f76a66c521d6d70ae306cc7eb777afc204bde261e1c022d5e7c795be8'
GRAPH_SOURCE_HEAD = 'bdc5db805975c3d77fb3eb93c6199b7452820658'
BASE_HEAD = '6d829369efd58c482ac28ac6e0a8cdd96b17adb4'
BASE_TREE = '2c9b7f9e083213e613ac86fd09e5f90f293cd1aa'
WRITER = 'libraries/mlf-crates/Bootstrap/CrateArtifact.hs'
WRITER_MODULE = 'Bootstrap.CrateArtifact'
CHANGED_PATHS = {WRITER, 'mlf.lock'}
FORMAT = 'writer-preflight-source-migration-v1'
VIEW_FORMAT = 'query-graph-with-writer-preflight-source-v1'
MANIFEST_NAME = 'writer-preflight-migration.json'
SCOPE = 'Source identity and reversible projection only; no new runtime or generation qualification.'


def read_implementation(path):
    """Use the same bounded, regular, no-file-link gate as the live loader."""
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


_graph_path = Path(__file__).resolve().parent / 'query_graph_contract.py'
_graph_raw = read_implementation(_graph_path)
if hashlib.sha256(_graph_raw).hexdigest() != GRAPH_CONTRACT_SHA256:
    raise ValueError('fixed predecessor graph contract implementation SHA')
_GRAPH = types.ModuleType('fixed_preflight_predecessor_graph_contract')
_GRAPH.__file__ = str(_graph_path)
exec(compile(_graph_raw, str(_graph_path), 'exec'), _GRAPH.__dict__)


def _materialize(graph, successor):
    """Construct, never silently repin, a current API view of the two edges."""
    value = copy.deepcopy(graph)
    value['format'] = VIEW_FORMAT
    value['graph_source_head'] = value.pop('source_head')
    value['source_base_head'] = successor['base_head']
    value['source_base_tree'] = successor['base_tree']
    value['successor'] = copy.deepcopy(successor)
    for path, row in successor['transition']['deltas'].items():
        value['current_files'][path] = row['new']
    value['current_registry'][WRITER_MODULE] = successor['transition']['deltas'][WRITER]['new']
    value['current_inventory_sha256'] = successor['current_inventory_sha256']
    value['current_registry_sha256'] = successor['current_registry_sha256']
    return value


class Contract(_GRAPH.Contract):
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64 or any(
                ch not in '0123456789abcdef' for ch in manifest_sha256):
            raise ValueError('explicit writer-preflight manifest SHA required')
        self._successor_sha256 = manifest_sha256
        self._initializing_successor = True
        # The unchanged constructor authenticates the old graph manifest and
        # frozen binary contract. Its validation hook installs the current view
        # before its source-admission hook reads any live production bytes.
        super().__init__(directory, GRAPH_MANIFEST_SHA256, history_root, source_root=source_root)
        self._initializing_successor = False
        self.manifest_sha256 = manifest_sha256
        names = set(self.metadata_paths) | {'writer_preflight_contract.py', MANIFEST_NAME}
        names.update(row['file'] for row in self.value['successor']['transition']['deltas'].values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_successor(self, successor):
        c = self._core
        c.require(type(successor) is dict and set(successor) == {
            'format', 'graph_contract_sha256', 'graph_manifest_sha256', 'graph_source_head',
            'base_head', 'base_tree', 'module_count', 'primitive_count', 'file_count',
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256', 'transition', 'qualification_scope'
        }, 'writer-preflight manifest fields')
        c.require(successor['format'] == FORMAT and
                  successor['graph_contract_sha256'] == GRAPH_CONTRACT_SHA256 and
                  successor['graph_manifest_sha256'] == GRAPH_MANIFEST_SHA256 and
                  successor['graph_source_head'] == GRAPH_SOURCE_HEAD and
                  successor['base_head'] == BASE_HEAD and successor['base_tree'] == BASE_TREE and
                  type(successor['module_count']) is int and successor['module_count'] == 135 and
                  type(successor['primitive_count']) is int and successor['primitive_count'] == 132 and
                  type(successor['file_count']) is int and successor['file_count'] == 196 and
                  successor['qualification_scope'] == SCOPE,
                  'writer-preflight identity / unchanged counts / scope')
        c.require(all(c.is_sha(successor[name]) for name in (
            'parent_registry_sha256', 'parent_inventory_sha256', 'current_registry_sha256',
            'current_inventory_sha256')), 'writer-preflight inventory hashes')
        edge = successor['transition']
        c.require(type(edge) is dict and set(edge) == {'changed_paths', 'added_paths', 'deltas'} and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and edge['added_paths'] == [] and
                  type(edge['deltas']) is dict and set(edge['deltas']) == CHANGED_PATHS,
                  'exact two-file writer-preflight transition')
        for row in edge['deltas'].values():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      all(c.is_sha(row[name]) for name in ('sha256', 'old', 'new')) and
                      row['old'] != row['new'], 'writer-preflight delta fields')

    def _validate_manifest(self):
        c = self._core
        if getattr(self, '_initializing_successor', False):
            # Authenticate the genuine historical graph schema before deriving
            # any current view. Its source_head continues to mean bdc5db80.
            super()._validate_manifest()
            raw = c.read_file(self.directory, MANIFEST_NAME, c.MAX_METADATA_BYTES)
            c.require(c.sha(raw) == self._successor_sha256, 'fixed writer-preflight manifest SHA')
            successor = c.strict_json(raw)
            self._validate_successor(successor)
            self.value = _materialize(self.value, successor)
        v = self.value
        c.require(type(v) is dict and set(v) == {
            'format', 'frozen_manifest_sha256', 'graph_source_head', 'source_base_head',
            'source_base_tree', 'module_paths', 'module_count', 'primitive_count',
            'current_registry', 'current_registry_sha256', 'current_files',
            'current_inventory_sha256', 'transition', 'maintenance', 'qualification_scope', 'successor'
        } and v['format'] == VIEW_FORMAT, 'writer-preflight current view fields')
        successor = v['successor']
        self._validate_successor(successor)
        c.hash_map(v['current_files'], 'writer-preflight current files')
        c.hash_map(v['current_registry'], 'writer-preflight current registry')
        c.require(WRITER in v['current_files'] and 'mlf.lock' in v['current_files'] and
                  WRITER_MODULE in v['current_registry'], 'writer-preflight current owner inventory')
        # Reconstruct the old *value*, not an invented checkout. Both its full
        # canonical identity and its unchanged original validator are required.
        graph = copy.deepcopy(v)
        del graph['successor']
        del graph['source_base_head']
        del graph['source_base_tree']
        graph['source_head'] = graph.pop('graph_source_head')
        graph['format'] = 'query-graph-source-migration-v1'
        for path, row in successor['transition']['deltas'].items():
            graph['current_files'][path] = row['old']
        graph['current_registry'][WRITER_MODULE] = successor['transition']['deltas'][WRITER]['old']
        graph['current_inventory_sha256'] = successor['parent_inventory_sha256']
        graph['current_registry_sha256'] = successor['parent_registry_sha256']
        c.require(c.canonical_sha(graph) == GRAPH_VALUE_SHA256, 'complete unchanged predecessor graph value')
        trial = object.__new__(_GRAPH.Contract)
        trial._core, trial.frozen_value, trial.value = c, self.frozen_value, graph
        _GRAPH.Contract._validate_manifest(trial)
        c.require(v == _materialize(graph, successor) and
                  c.canonical_sha(v['current_files']) == successor['current_inventory_sha256'] and
                  c.canonical_sha(v['current_registry']) == successor['current_registry_sha256'] and
                  all(v['current_files'][path] == v['current_registry'][name]
                      for name, path in v['module_paths'].items()),
                  'exact complete writer-preflight current source identity')
        self._validate_rows(successor['transition']['deltas'], CHANGED_PATHS,
                            graph['current_files'], v['current_files'], 'writer-preflight-deltas/')
        # This method also works for object.__new__ callers supplying only
        # _core, frozen_value and value, as the existing strict tests require.
        self.graph_value = graph

    def _to_frozen(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full repaired current path SHA: ' + path)
        successor = self.value['successor']['transition']['deltas']
        if path in successor:
            raw = self._apply(raw, path, successor, True)
        if path in _GRAPH.ADDED_MODULES.values():
            return None
        rows = self.value['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _from_frozen(self, raw, path):
        result = super()._from_frozen(raw, path)
        rows = self.value['successor']['transition']['deltas']
        return self._apply(result, path, rows, False) if path in rows else result

    def _validate_successor_lock(self, graph_raw, current_raw):
        """Structural guard independent of the current lock's outer hash."""
        c = self._core
        rows = self.value['successor']['transition']['deltas']
        c.require(type(graph_raw) is bytes and c.sha(graph_raw) == rows['mlf.lock']['old'],
                  'exact predecessor graph lock')
        expected = c.strict_json(graph_raw)
        packages = [row for row in expected['packages'] if row['path'] == 'libraries/mlf-crates']
        c.require(len(packages) == 1 and
                  packages[0]['sources'].get('Bootstrap/CrateArtifact.hs') == rows[WRITER]['old'],
                  'unique predecessor writer lock entry')
        packages[0]['sources']['Bootstrap/CrateArtifact.hs'] = rows[WRITER]['new']
        c.require(c.strict_json(current_raw) == expected,
                  'lock changed beyond exactly one writer source hash')

    def _validate_metadata_transition(self, frozen, current):
        # The existing structural guard still checks every graph package,
        # registry addition, package ordering, version and primitive ABI.
        super()._validate_metadata_transition(frozen, current)
        graph_lock = self._apply(current['mlf.lock'], 'mlf.lock',
                                 self.value['successor']['transition']['deltas'], True)
        self._validate_successor_lock(graph_lock, current['mlf.lock'])
