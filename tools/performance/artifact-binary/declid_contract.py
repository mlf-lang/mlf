"""Authenticate the DeclId checkout, then project its verified bytes onto the #29 contract."""
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess
import tarfile
import tempfile
import types

PREDECESSOR = '8c4556416023ac727e3fb2294070358a3dae8d9e'
PREDECESSOR_TREE = 'c20bd3d8e0cdd7e319dfca77ea0b86cfbf77554d'
PREDECESSOR_MANIFEST = 'fb8335e198e463d3a25b336f124d56dac141c6ad2063df531c09ade8e7411559'
MANIFEST = 'declid-source-migration.json'
MANIFEST_SHA256 = '5b032865732345915068eef1aec6658721256efd490de85965d4011a260027e8'
PREDECESSOR_IMPLEMENTATION = '80ab586aed593698fc60f1644e8f0b4b24fc5d33140e7da60675ee5cf6677c19'


def require(condition, message):
    if not condition:
        raise ValueError('DeclId source migration: ' + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=1)
def archived_checkout(repository):
    """This process owns one immutable, SHA-addressed physical predecessor for the old reader."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', PREDECESSOR + '^{tree}'], text=True).strip()
    require(tree == PREDECESSOR_TREE, 'pinned predecessor tree')
    directory = tempfile.TemporaryDirectory(prefix='mlf-declid-previous-')
    with subprocess.Popen([*git, 'archive', PREDECESSOR], stdout=subprocess.PIPE) as archive:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(directory.name, filter='data')
        require(archive.wait() == 0, 'cannot read pinned predecessor')
    return directory


def module_at(path):
    require(path.is_file() and not path.is_symlink(), 'predecessor implementation file')
    with path.open('rb') as stream:
        raw = stream.read(65537)
    require(len(raw) <= 65536 and sha(raw) == PREDECESSOR_IMPLEMENTATION, 'predecessor implementation SHA')
    result = types.ModuleType(path.stem)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


class Contract:
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        self.directory = Path(directory).resolve(strict=True)
        self.source_root = Path(source_root or Path(history_root).parents[1]).resolve(strict=True)
        require(manifest_sha256 == MANIFEST_SHA256, 'expected independently pinned successor manifest')
        # A relocated source/metadata bundle can still use the current caller's
        # Git object database. In both cases the same commit and tree are required.
        for location in (history_root, Path.cwd()):
            repo = subprocess.run(['git', '-C', str(location), 'rev-parse', '--show-toplevel'],
                                  capture_output=True, text=True)
            if repo.returncode == 0:
                location = repo.stdout.strip()
                tree = subprocess.run(['git', '--no-replace-objects', '-C', location, 'rev-parse', PREDECESSOR + '^{tree}'],
                                      capture_output=True, text=True)
                if tree.returncode == 0 and tree.stdout.strip() == PREDECESSOR_TREE:
                    break
        else:
            raise ValueError('DeclId source migration: full Git history required for pinned predecessor')
        self.archived = Path(archived_checkout(location).name)
        # Only the immutable tree supplies executable predecessor code. The caller's
        # bundle supplies its metadata, which the old constructor authenticates.
        old_dir = self.archived / 'tools/performance/artifact-binary'
        previous_type = module_at(old_dir / 'builtin_regeneration_contract.py').Contract
        self.previous = previous_type(self.directory, PREDECESSOR_MANIFEST,
                                      self.archived / 'tools/performance', self.archived)
        self.core = self.previous._core
        self.manifest_sha256 = manifest_sha256
        raw = self.core.read_file(self.directory, MANIFEST, self.core.MAX_METADATA_BYTES)
        require(sha(raw) == manifest_sha256, 'successor manifest SHA')
        spec = self.core.strict_json(raw)
        require(set(spec) == {'format', 'predecessor', 'changes', 'additions', 'maintenance'} and
                spec['format'] == 'declid-source-migration-v1' and spec['predecessor'] == PREDECESSOR,
                'successor manifest schema')
        self.changes = spec['changes']
        self.maintenance = spec['maintenance']
        files = dict(self.previous.value['current_files'])
        for name, row in self.changes.items():
            require(len(row) == 2 and files[name] == row[0] and row[0] != row[1], 'source transition ' + name)
            files[name] = row[1]
        for name, digest in spec['additions'].items():
            require(name not in files, 'added path already owned: ' + name)
            files[name] = digest
        self.core.hash_map(files, 'DeclId files')
        self.value = {'current_files': files}
        self.live_source_inventory(self.source_root)
        registry = self.core.strict_json(self.core.read_file(self.source_root, 'shared-sources.json'))
        paths = {row['module']: row['path'] for row in registry['modules']}
        require(len(paths) == len(registry['modules']), 'duplicate module')
        old_paths = self.previous.value['module_paths']
        require(all(paths.get(n) == p for n, p in old_paths.items()), 'changed or removed module owner')
        added = {n: p for n, p in paths.items() if n not in old_paths}
        require(set(added.values()) == set(spec['additions']), 'added module and source inventories differ')
        self.value.update(module_paths=paths, current_registry={n: files[p] for n, p in paths.items()})
        self.added_modules = {**self.previous.added_modules, **added}
        self.parent = self.previous.parent
        self.maintenance_parent = self.previous.maintenance_parent
        self.evidence_source_root = self.previous.evidence_source_root
        self.metadata_paths = (*self.previous.metadata_paths, MANIFEST, 'declid_contract.py')
        self.added_paths = sorted(set(self.previous.added_paths) | set(spec['additions']))
        for path in self.previous.metadata_paths:
            if path != 'source_migration_adapter.py':
                require(self.core.read_file(self.directory, path) == self.core.read_file(old_dir, path),
                        'predecessor metadata changed: ' + path)
        # The successor must preserve every frozen tool/oracle identity the old
        # constructor read, including when the caller supplies a relocated tree.
        history_names = set(self.parent['frozen_history']) | set(self.maintenance_parent['files'])
        require(set(self.maintenance) <= history_names, 'unexpected maintenance owner')
        for name in history_names:
            raw = self.core.read_file(history_root, name)
            old = self.core.read_file(self.archived / 'tools/performance', name)
            if name in self.maintenance:
                require(self.maintenance[name] == [sha(old), sha(raw)] and raw != old,
                        'maintenance transition ' + name)
            else:
                require(raw == old, 'undeclared historical change ' + name)

    def live_source_inventory(self, root):
        actual = {p: sha(self.core.read_file(root, p)) for p in self.value['current_files']}
        require(actual == self.value['current_files'], 'whole live source inventory differs')
        return actual

    def live_registry(self, root):
        require(sha(self.core.read_file(root, 'shared-sources.json')) == self.value['current_files']['shared-sources.json'],
                'module registry bytes')
        registry = {n: sha(self.core.read_file(root, p)) for n, p in self.value['module_paths'].items()}
        self.require_registry(registry, 'current')
        return registry

    def require_registry(self, value, side):
        if side == 'parent':
            return self.previous.require_registry(value, side)
        require(side == 'current' and value == self.value['current_registry'], 'exact complete current registry')

    def _older_bytes(self, raw, path):
        require(type(raw) is bytes and sha(raw) == self.value['current_files'].get(path), 'source SHA ' + path)
        if path not in self.previous.value['current_files']:
            return None
        if path in self.changes:
            old = self.core.read_file(self.archived, path)
            require(sha(old) == self.changes[path][0], 'predecessor SHA ' + path)
            return old
        return raw

    def restore_path(self, raw, path):
        previous = self._older_bytes(raw, path)
        return None if previous is None else self.previous.restore_path(previous, path)

    def project_owner(self, raw, module):
        require(module in self.value['module_paths'], 'unknown source owner')
        return self.restore_path(raw, self.value['module_paths'][module])

    def advance_registry(self, parent):
        self.previous.advance_registry(parent)
        return dict(self.value['current_registry'])

    def added_source_bytes(self, root):
        result = {n: self.core.read_file(root, p) for n, p in self.added_modules.items()}
        self.registry_to_parent(self.value['current_registry'], result)
        return result

    def registry_to_parent(self, current, additions):
        self.require_registry(current, 'current')
        require(type(additions) is dict and set(additions) == set(self.added_modules), 'full added source inventory')
        old = {n: self._older_bytes(additions[n], p) for n, p in self.added_modules.items()}
        return self.previous.registry_to_parent(self.previous.value['current_registry'],
                                                {n: old[n] for n in self.previous.added_modules})

    def live_host_inventory(self, root):
        actual = {p: sha(self.core.read_file(root, p)) for p in self.parent['host_inventory']}
        require(actual == {p: self.value['current_files'][p] for p in self.parent['host_inventory']},
                'complete live host inventory')
        return actual

    def legacy_host_subset_to_parent(self, current):
        require(type(current) is dict and set(current) <= set(self.parent['legacy_host_bridge']) and
                current == {p: self.value['current_files'][p] for p in current}, 'exact live host subset')
        return self.previous.legacy_host_subset_to_parent({p: self.previous.value['current_files'][p] for p in current})

    def advance_legacy_host_subset(self, parent):
        previous = self.previous.advance_legacy_host_subset(parent)
        return {p: self.value['current_files'][p] for p in previous}

    def restore_maintenance(self, raw, name):
        if name in self.maintenance:
            old = self.core.read_file(self.archived / 'tools/performance', name)
            require([sha(old), sha(raw)] == self.maintenance[name], 'maintenance source identity')
            raw = old
        return self.previous.restore_maintenance(raw, name)

    def _newer_bytes(self, raw, path):
        require(sha(raw) == self.previous.value['current_files'].get(path), 'predecessor path SHA')
        if path not in self.changes:
            return raw
        new = self.core.read_file(self.source_root, path)
        require(sha(new) == self.changes[path][1], 'successor path SHA')
        return new

    def advance_path(self, raw, path):
        return self._newer_bytes(self.previous.advance_path(raw, path), path)

    def restore_previous_lock(self, raw):
        return self.previous.restore_previous_lock(self._older_bytes(raw, 'mlf.lock'))

    def advance_lock(self, raw):
        return self._newer_bytes(self.previous.advance_lock(raw), 'mlf.lock')

    def project_tree_bytes(self, current):
        self.previous._require_raw_map(current, self.value['current_files'], 'DeclId current')
        previous = {p: self._older_bytes(raw, p) for p, raw in current.items()}
        return self.previous.project_tree_bytes({p: previous[p] for p in self.previous.value['current_files']})

    def advance_tree_bytes(self, parent, additions):
        self.previous._require_raw_map(additions, {p: self.value['current_files'][p] for p in self.added_paths},
                                       'DeclId additions')
        old = {p: self._older_bytes(additions[p], p) for p in self.previous.added_paths}
        previous = self.previous.advance_tree_bytes(parent, old)
        result = {p: self._newer_bytes(raw, p) for p, raw in previous.items()}
        result.update({p: raw for p, raw in additions.items() if p not in previous})
        require(self.project_tree_bytes(result) == parent, 'full historical round trip')
        return result

    def host_inventory_to_parent(self, current):
        paths = self.parent['host_inventory']
        require(current == {p: self.value['current_files'][p] for p in paths}, 'complete host inventory')
        return self.previous.host_inventory_to_parent({p: self.previous.value['current_files'][p] for p in paths})

    def advance_host_inventory(self, parent):
        previous = self.previous.advance_host_inventory(parent)
        return {p: self.value['current_files'][p] for p in previous}

    def runtime_inventory_to_parent(self, current, header):
        names = [p for p in self.value['current_files'] if p.startswith('runtime/')]
        require(current == {p: self.value['current_files'][p] for p in names}, 'complete runtime inventory')
        return self.previous.runtime_inventory_to_parent({p: self.previous.value['current_files'][p] for p in names},
                                                         self._older_bytes(header, 'runtime/mlf_byte_file.h'))

    def advance_runtime_inventory(self, parent):
        previous = self.previous.advance_runtime_inventory(parent)
        return {p: self.value['current_files'][p] for p in previous}
