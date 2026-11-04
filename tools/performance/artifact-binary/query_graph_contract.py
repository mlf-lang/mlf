"""Exact live graph135 -> frozen binary132 -> historical128 source bridge.

This proves source identity and byte-exact projection, not equivalence of compiler
behavior or a new builtin generation. The existing binary manifest, generation
receipt, deltas and historical measurements remain unchanged.
"""
from pathlib import Path
import os
import stat
import types

FROZEN_CONTRACT_SHA256 = 'f6c81c97a1284442c5825d38fc806639af9b49e8634b516d649dfa8c7583910d'
FROZEN_MANIFEST_SHA256 = 'bd96069b029ff0e7b0b6756dd0f57126c8b016ddf89d4359a8ae83243438e29e'
ADDED_MODULES = {
    'Bootstrap.CrateGraph': 'libraries/mlf-crates/Bootstrap/CrateGraph.hs',
    'Bootstrap.OpenFragment': 'libraries/mlf-crates/Bootstrap/OpenFragment.hs',
    'Bootstrap.QueryGraph': 'libraries/mlf-crates/Bootstrap/QueryGraph.hs',
}
CHANGED_PATHS = [
    'bootstrap/MLF/BuiltinPreludeData.hs',
    'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
    'libraries/mlf-crates/Bootstrap/CrateSession.hs',
    'libraries/mlf-crates/Bootstrap/InferenceUnit.hs',
    'libraries/mlf-crates/Bootstrap/PreparedLibraries.hs',
    'libraries/mlf-crates/Bootstrap/PreparedLibraryLiteral.hs',
    'libraries/mlf-crates/Bootstrap/SourceInference.hs',
    'libraries/mlf-crates/mlf-package.json',
    'libraries/mlf-inference/Bootstrap/EvidenceBoundary.hs',
    'libraries/mlf-package-core/Package/Release.hs',
    'mlf-shared.cabal', 'mlf.lock', 'shared-sources.json',
]
MAINTENANCE_PATHS = {'patricia/run_integrated.py', 'patricia/test_adapters.py'}
SCOPE = 'Source identity and reversible projection only; no new runtime or generation qualification.'


def read_implementation(path):
    """Read only a bounded regular implementation, never follow a file link."""
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


class Contract:
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        import hashlib
        self.directory = Path(directory).resolve(strict=True)
        path = self.directory / 'source_contract.py'
        raw = read_implementation(path)
        if hashlib.sha256(raw).hexdigest() != FROZEN_CONTRACT_SHA256:
            raise ValueError('fixed frozen binary contract implementation SHA')
        core = types.ModuleType('frozen_binary_source_contract')
        core.__file__ = str(path)
        exec(compile(raw, str(path), 'exec'), core.__dict__)
        self._core = core
        core.require(core.is_sha(manifest_sha256), 'explicit graph manifest SHA required')
        self.manifest_sha256 = manifest_sha256
        raw = core.read_file(self.directory, 'source-migration.json', core.MAX_METADATA_BYTES)
        core.require(core.sha(raw) == FROZEN_MANIFEST_SHA256, 'frozen binary manifest SHA')
        self.frozen_value = core.strict_json(raw)
        raw = core.read_file(self.directory, 'query-graph-migration.json', core.MAX_METADATA_BYTES)
        core.require(core.sha(raw) == manifest_sha256, 'fixed graph manifest SHA')
        self.value = core.strict_json(raw)
        self._validate_manifest()
        owner = self

        class FrozenContract(core.Contract):
            # The original implementation continues to see only its frozen132
            # manifest and receipt. Its admission authenticates the live135 input
            # first, then checks exact inverse bytes, never an invented checkout.
            def live_source_inventory(self, current_root):
                owner._project_live_to_frozen(current_root)
                return dict(owner.frozen_value['current_files'])

            def restore_maintenance(self, raw, name):
                return super().restore_maintenance(owner._maintenance_to_frozen(raw, name), name)

        self._frozen = FrozenContract(self.directory, FROZEN_MANIFEST_SHA256,
                                      history_root, source_root=source_root)
        self.parent = self._frozen.parent
        self.maintenance_parent = self._frozen.maintenance_parent
        self.source_root = self._frozen.source_root
        self.evidence_source_root = self._frozen.evidence_source_root
        self.added_modules = {**core.ADDED_MODULES, **ADDED_MODULES}
        self.added_paths = sorted(set(self.frozen_value['added_paths']) | set(ADDED_MODULES.values()))
        names = {'source_contract.py', 'source_migration_adapter.py', 'source-migration.json',
                 'parent-inventory.json', 'maintenance-parents.json', 'builtin-verification-receipt.json',
                 'query_graph_contract.py', 'query-graph-migration.json'}
        for group in (self.frozen_value['deltas'], self.frozen_value['maintenance'],
                      self.value['transition']['deltas'], self.value['maintenance']):
            names.update(row['file'] for row in group.values())
        self.metadata_paths = tuple(sorted(names))

    def _validate_manifest(self):
        c, v, old = self._core, self.value, self.frozen_value
        c.require(type(v) is dict and set(v) == {
            'format', 'frozen_manifest_sha256', 'source_head', 'module_paths', 'module_count',
            'primitive_count', 'current_registry', 'current_registry_sha256', 'current_files',
            'current_inventory_sha256', 'transition', 'maintenance', 'qualification_scope'
        }, 'graph manifest fields')
        c.require(v['format'] == 'query-graph-source-migration-v1' and
                  v['frozen_manifest_sha256'] == FROZEN_MANIFEST_SHA256 and
                  v['source_head'] == 'bdc5db805975c3d77fb3eb93c6199b7452820658' and
                  v['module_count'] == 135 and v['primitive_count'] == 132 and
                  v['qualification_scope'] == SCOPE, 'graph manifest identity / scope')
        c.require(v['module_paths'] == {**old['module_paths'], **ADDED_MODULES},
                  'exact three added graph modules')
        c.hash_map(v['current_files'], 'graph current files')
        c.hash_map(v['current_registry'], 'graph current registry')
        files = v['current_files']
        c.require(set(files) == set(old['current_files']) | set(ADDED_MODULES.values()) and
                  c.canonical_sha(files) == v['current_inventory_sha256'],
                  'complete graph current file inventory')
        c.require(set(v['current_registry']) == set(v['module_paths']) and
                  c.canonical_sha(v['current_registry']) == v['current_registry_sha256'] and
                  all(files[path] == v['current_registry'][name]
                      for name, path in v['module_paths'].items()),
                  'complete graph registry / source identity')
        edge = v['transition']
        c.require(type(edge) is dict and set(edge) == {'added_paths', 'changed_paths', 'deltas'} and
                  edge['added_paths'] == sorted(ADDED_MODULES.values()) and
                  edge['changed_paths'] == sorted(CHANGED_PATHS) and
                  sorted(p for p, h in old['current_files'].items() if files[p] != h) == sorted(CHANGED_PATHS),
                  'exact graph transition inventory')
        self._validate_rows(edge['deltas'], set(CHANGED_PATHS), old['current_files'],
                            files, 'query-graph-deltas/')
        c.require(type(v['maintenance']) is dict and set(v['maintenance']) == MAINTENANCE_PATHS,
                  'exact graph maintenance entrypoints')
        self._validate_rows(v['maintenance'], MAINTENANCE_PATHS,
                            {p: old['maintenance'][p]['new'] for p in MAINTENANCE_PATHS},
                            {p: row.get('new') for p, row in v['maintenance'].items()
                             if type(row) is dict}, 'query-graph-maintenance/')

    def _validate_rows(self, rows, paths, before, after, prefix):
        c = self._core
        c.require(type(rows) is dict and set(rows) == paths, 'exact graph delta inventory')
        seen = set()
        for path, row in rows.items():
            c.require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                      row['old'] == before[path] and row['new'] == after.get(path) and
                      c.is_sha(row['new']) and row['old'] != row['new'] and c.is_sha(row['sha256']),
                      'graph delta identity: ' + path)
            c.relative_path(row['file'])
            c.require(row['file'].startswith(prefix) and row['file'] not in seen,
                      'graph delta path / duplicate')
            seen.add(row['file'])

    def _apply(self, raw, path, rows, reverse):
        c = self._core
        row = rows[path]
        data = c.read_file(self.directory, row['file'], c.MAX_METADATA_BYTES)
        c.require(c.sha(data) == row['sha256'], 'fixed graph delta SHA: ' + path)
        delta = c.strict_json(data)
        c.require(delta.get('path') == path and delta.get('old_sha256') == row['old'] and
                  delta.get('new_sha256') == row['new'], 'graph delta owner binding')
        result = c.apply_splices(raw, delta, reverse=reverse)
        c.require(c.apply_splices(result, delta, reverse=not reverse) == raw,
                  'exact graph inverse / forward equality')
        return result

    def _to_frozen(self, raw, path):
        c = self._core
        c.require(path in self.value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.value['current_files'][path], 'full graph current path SHA: ' + path)
        if path in ADDED_MODULES.values():
            return None
        rows = self.value['transition']['deltas']
        return self._apply(raw, path, rows, True) if path in rows else raw

    def _from_frozen(self, raw, path):
        c = self._core
        c.require(path in self.frozen_value['current_files'] and type(raw) is bytes and
                  c.sha(raw) == self.frozen_value['current_files'][path], 'full frozen current path SHA: ' + path)
        rows = self.value['transition']['deltas']
        return self._apply(raw, path, rows, False) if path in rows else raw

    def _maintenance_to_frozen(self, raw, name):
        rows = self.value['maintenance']
        return self._apply(raw, name, rows, True) if name in rows else raw

    def _validate_metadata_transition(self, frozen, current):
        c = self._core
        old = c.strict_json(frozen['shared-sources.json'])
        new = c.strict_json(current['shared-sources.json'])
        expected = dict(old)
        expected['modules'] = sorted(old['modules'] + [
            {'module': n, 'path': p, 'role': 'implementation'}
            for n, p in ADDED_MODULES.items()], key=lambda row: row['module'])
        c.require(new == expected and len(c.module_paths(new)) == 135,
                  'shared manifest changed beyond exact graph transition')
        # The primitive ABI remains132; only three library modules were added.
        old_lock = c.strict_json(frozen['mlf.lock'])
        new_lock = c.strict_json(current['mlf.lock'])
        before, after = self.frozen_value['current_files'], self.value['current_files']
        seen_changed, inserted = set(), set()
        changed = {p for p in CHANGED_PATHS if p.endswith('.hs') and not p.startswith('host/')}
        for row in old_lock['packages']:
            manifest = c.lock_path(row['path'], 'mlf-package.json')
            c.require(row['manifest'] == before[manifest], 'frozen graph package manifest')
            row['manifest'] = after[manifest]
            for name in list(row['sources']):
                path = c.lock_path(row['path'], name)
                if path in changed:
                    c.require(row['sources'][name] == before[path], 'frozen graph lock source: ' + path)
                    row['sources'][name] = after[path]
                    seen_changed.add(path)
            if row['path'] == 'libraries/mlf-crates':
                for path in ADDED_MODULES.values():
                    name = path[len(row['path']) + 1:]
                    c.require(name not in row['sources'], 'graph module already in frozen lock')
                    row['sources'][name] = after[path]
                    inserted.add(path)
        c.require(seen_changed == changed and inserted == set(ADDED_MODULES.values()) and
                  new_lock == old_lock, 'lock changed outside exact graph source bridge')

    def _project_live_to_frozen(self, root):
        c = self._core
        current = {p: c.read_file(root, p) for p in self.value['current_files']}
        c.require({p: c.sha(raw) for p, raw in current.items()} == self.value['current_files'],
                  'exact whole live graph source inventory required')
        frozen = {p: self._to_frozen(current[p], p) for p in self.frozen_value['current_files']}
        c.require({p: c.sha(raw) for p, raw in frozen.items()} == self.frozen_value['current_files'],
                  'exact complete projected binary132 inventory')
        self._validate_metadata_transition(frozen, current)
        return frozen

    def require_registry(self, value, side):
        c = self._core
        c.require(side in ('parent', 'current'), 'registry side')
        expected = self.parent['registry'] if side == 'parent' else self.value['current_registry']
        c.hash_map(value, side + ' registry')
        c.require(value == expected, 'exact complete ' + side + ' registry required')

    def advance_registry(self, parent):
        self.require_registry(parent, 'parent')
        self._frozen.advance_registry(parent)
        return dict(self.value['current_registry'])

    def registry_to_parent(self, current, added_source_bytes):
        c = self._core
        self.require_registry(current, 'current')
        c.require(type(added_source_bytes) is dict and set(added_source_bytes) == set(self.added_modules),
                  'actual seven added module bytes required for inverse projection')
        for name, raw in added_source_bytes.items():
            c.require(type(raw) is bytes and len(raw) <= c.MAX_SOURCE_BYTES and c.sha(raw) == current[name],
                      'added module raw SHA: ' + name)
        old_added = {n: self._to_frozen(added_source_bytes[n], p) for n, p in c.ADDED_MODULES.items()}
        return self._frozen.registry_to_parent(self.frozen_value['current_registry'], old_added)

    def restore_path(self, raw, path):
        frozen = self._to_frozen(raw, path)
        return None if frozen is None else self._frozen.restore_path(frozen, path)

    def advance_path(self, raw, path):
        return self._from_frozen(self._frozen.advance_path(raw, path), path)

    def project_owner(self, raw, module):
        self._core.require(module in self.value['module_paths'], 'unknown source owner')
        return self.restore_path(raw, self.value['module_paths'][module])

    def restore_maintenance(self, raw, name):
        return self._frozen.restore_maintenance(raw, name)

    def restore_previous_lock(self, raw):
        # Constructor checks the complete current lock transition; this call
        # additionally requires exact bytes and the original binary lock bridge.
        return self._frozen.restore_previous_lock(self._to_frozen(raw, 'mlf.lock'))

    def advance_lock(self, raw):
        return self._from_frozen(self._frozen.advance_lock(raw), 'mlf.lock')

    def _require_raw_map(self, value, expected, label):
        self._frozen._require_raw_map(value, expected, label)

    def project_tree_bytes(self, current):
        self._require_raw_map(current, self.value['current_files'], 'current')
        frozen = {p: self._to_frozen(current[p], p) for p in self.frozen_value['current_files']}
        self._validate_metadata_transition(frozen, current)
        return self._frozen.project_tree_bytes(frozen)

    def advance_tree_bytes(self, parent, additions):
        self._require_raw_map(parent, self.parent['files'], 'parent')
        self._require_raw_map(additions, {p: self.value['current_files'][p] for p in self.added_paths}, 'added')
        frozen_added = {p: self._to_frozen(additions[p], p) for p in self.frozen_value['added_paths']}
        frozen = self._frozen.advance_tree_bytes(parent, frozen_added)
        result = {p: self._from_frozen(raw, p) for p, raw in frozen.items()}
        result.update({p: additions[p] for p in ADDED_MODULES.values()})
        self._require_raw_map(result, self.value['current_files'], 'current')
        self._core.require(self.project_tree_bytes(result) == parent, 'whole graph source roundtrip')
        return result

    def live_registry(self, current_root):
        c = self._core
        result = {n: c.sha(c.read_file(current_root, p)) for n, p in self.value['module_paths'].items()}
        self.require_registry(result, 'current')
        return result

    def live_source_inventory(self, current_root):
        self._project_live_to_frozen(current_root)
        return dict(self.value['current_files'])

    def added_source_bytes(self, current_root):
        c = self._core
        result = {n: c.read_file(current_root, p) for n, p in self.added_modules.items()}
        self.registry_to_parent(self.value['current_registry'], result)
        return result

    # None of this edge's source changes is a host/runtime input. Require that
    # invariant before delegating the unchanged strict inventory APIs.
    def _unchanged_bridge(self, method, *args):
        c = self._core
        names = set(self._frozen.parent['host_inventory']) | {
            p for p in self.value['current_files'] if p.startswith('runtime/')}
        c.require(all(self.value['current_files'][p] == self.frozen_value['current_files'][p]
                      for p in names), 'graph transition altered host/runtime bridge')
        return getattr(self._frozen, method)(*args)

    def advance_host_inventory(self, parent):
        return self._unchanged_bridge('advance_host_inventory', parent)

    def host_inventory_to_parent(self, current):
        return self._unchanged_bridge('host_inventory_to_parent', current)

    def advance_legacy_host_subset(self, parent):
        return self._unchanged_bridge('advance_legacy_host_subset', parent)

    def legacy_host_subset_to_parent(self, current):
        return self._unchanged_bridge('legacy_host_subset_to_parent', current)

    def live_host_inventory(self, current_root):
        return self._unchanged_bridge('live_host_inventory', current_root)

    def runtime_inventory_to_parent(self, current, added_header_bytes):
        return self._unchanged_bridge('runtime_inventory_to_parent', current, added_header_bytes)

    def advance_runtime_inventory(self, parent):
        return self._unchanged_bridge('advance_runtime_inventory', parent)

