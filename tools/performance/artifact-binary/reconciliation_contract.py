"""Authenticate PR43 reconciliation before reversible historical source projection."""
from functools import lru_cache
import hashlib
import os
import stat
from pathlib import Path
import subprocess
import tarfile
import tempfile
import types

PREDECESSOR = '4fd6730d35b6ecaf8e169ad228ac3c7a3ed56160'
PREDECESSOR_TREE = '1c60d3daca5162bd24658d295169f601593345ef'
PREDECESSOR_MANIFEST = '69bc6cc39ec70a0209a6011f4ce7fef0aaf5039d903fa1b8477ee4a2bc46dcd8'
MANIFEST = 'pr43-reconciliation-migration.json'
MANIFEST_SHA256 = 'fd94a0a3c984044f07f4dc129eb27090a71fde0ac530cfe76a067a5db2613369'
PREDECESSOR_IMPLEMENTATION = '7cacadad979f3db29da9067b5fe0ca8e1634d960dbf978ad6d5cae39ba338794'
LIVE_PREDECESSOR = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
LIVE_PREDECESSOR_TREE = '3148203097e7622ced1b272e606bfa892fad746b'
LIVE_PREDECESSOR_MANIFEST = '63598306f049a050def3fd21ddf21878a7f4f882b59a48a86c53a3398624e9c5'
LIVE_TRANSITION_PATH = 'tools/shared/build.py'
LIVE_PREDECESSOR_SOURCE = 'eff291112f318206ce0f7ab85cb8a2e474be41489441204696630a395f4ca3df'
PERFORMANCE_BASE = 'fc300bc9fdc389b585cbef0630fc8915d53e89c5'
PERFORMANCE_TREE = '386f0b41ab5f9b39fca273f3040f51d73df924a1'
PERFORMANCE_BASE_MANIFEST = 'ebe5671476447cd4b256784e7d898ed6095c7c54cc9286c6869ca4909b2b708b'
PERFORMANCE_PATHS = {
    'bootstrap/MLF/BuiltinPreludeData.hs', 'bootstrap/MLF/Entry/Emlf.hs',
    'bootstrap/MLF/PreparedCompiler.hs',
    'libraries/mlf-crates/Bootstrap/BuiltinPreludeContext.hs',
    'libraries/mlf-crates/Bootstrap/Crate.hs', 'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
    'libraries/mlf-crates/Bootstrap/CrateGraph.hs', 'libraries/mlf-crates/Bootstrap/CrateSession.hs',
    'libraries/mlf-crates/Bootstrap/InferenceUnit.hs', 'libraries/mlf-crates/Bootstrap/QueryGraph.hs',
    'libraries/mlf-crates/Bootstrap/Separate.hs', 'libraries/mlf-crates/Bootstrap/SourceInference.hs',
    'mlf.lock', 'tests/shared/MLF/Tests/SharedFrontend.hs',
}


def require(condition, message):
    if not condition:
        raise ValueError('PR43 reconciliation source migration: ' + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=1)
def archived_checkout(repository):
    """This process owns one immutable, SHA-addressed physical predecessor for the old reader."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', PREDECESSOR + '^{tree}'], text=True).strip()
    require(tree == PREDECESSOR_TREE, 'pinned predecessor tree')
    directory = tempfile.TemporaryDirectory(prefix='mlf-pr43-previous-')
    with subprocess.Popen([*git, 'archive', PREDECESSOR, 'libraries', 'bootstrap', 'host', 'runtime',
        'tools/performance', 'tools/shared', 'shared-sources.json', 'mlf.lock',
        'mlf-package.json', 'mlf-shared.cabal', 'cabal.project', 'tests', 'testing', 'package'], stdout=subprocess.PIPE) as archive:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(directory.name, filter='data')
        require(archive.wait() == 0, 'cannot read pinned predecessor')
    return directory


def module_at(path):
    require(path.is_file() and not path.is_symlink(), 'predecessor implementation file')
    with path.open('rb') as stream:
        raw = stream.read(65537)
    require(len(raw) <= 65536 and sha(raw) == PREDECESSOR_IMPLEMENTATION, 'predecessor implementation SHA')
    return module_bytes(path, raw)


@lru_cache(maxsize=1)
def module_bytes(path, raw):
    # module_at revalidates the immutable implementation on every call. Reuse
    # only identical pinned bytes so its original predecessor cache is shared.
    result = types.ModuleType(path.stem)
    result.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), result.__dict__)
    return result


def manifest_bytes(directory):
    path = directory / MANIFEST
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                         getattr(os, 'O_NONBLOCK', 0))
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_size <= 65536,
                'bounded regular successor manifest')
        raw = os.read(descriptor, 65537)
        require(len(raw) <= 65536, 'successor manifest byte bound')
        return raw
    finally:
        os.close(descriptor)


def validate_macos_transition(spec, repository, core):
    """Admit only the declared build-driver repair after the fixed main endpoint."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', LIVE_PREDECESSOR + '^{tree}'], text=True).strip()
    require(tree == LIVE_PREDECESSOR_TREE, 'pinned live predecessor tree')
    raw = subprocess.check_output([*git, 'show', LIVE_PREDECESSOR +
                                   ':tools/performance/artifact-binary/' + MANIFEST])
    require(len(raw) <= core.MAX_METADATA_BYTES and sha(raw) == LIVE_PREDECESSOR_MANIFEST,
            'pinned live predecessor manifest')
    prior = core.strict_json(raw)
    old = subprocess.check_output([*git, 'show', LIVE_PREDECESSOR + ':' + LIVE_TRANSITION_PATH])
    require(len(old) <= core.MAX_SOURCE_BYTES and sha(old) == LIVE_PREDECESSOR_SOURCE and
            prior['changes'][LIVE_TRANSITION_PATH][1] == LIVE_PREDECESSOR_SOURCE,
            'pinned live predecessor source')
    row = spec['changes'].get(LIVE_TRANSITION_PATH)
    require(type(row) is list and len(row) == 2 and row[1] != LIVE_PREDECESSOR_SOURCE,
            'changed live build endpoint')
    transition = {
        'predecessor': LIVE_PREDECESSOR,
        'predecessor_tree': LIVE_PREDECESSOR_TREE,
        'predecessor_manifest_sha256': LIVE_PREDECESSOR_MANIFEST,
        'changes': {LIVE_TRANSITION_PATH: [LIVE_PREDECESSOR_SOURCE, row[1]]},
    }
    # Preserve the original PR43 endpoints, every other current endpoint,
    # additions, registry ownership and historical maintenance records verbatim.
    expected = {**prior, 'changes': {**prior['changes'], LIVE_TRANSITION_PATH:
                                  [prior['changes'][LIVE_TRANSITION_PATH][0], row[1]]},
                'live_transition': transition}
    require(spec == expected, 'only the declared live build endpoint may change')


def validate_live_transition(spec, repository, core):
    """Pin the performance follow-on while retaining the earlier exact transition."""
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', PERFORMANCE_BASE + '^{tree}'], text=True).strip()
    require(tree == PERFORMANCE_TREE, 'pinned performance predecessor tree')
    raw = subprocess.check_output([*git, 'show', PERFORMANCE_BASE +
                                   ':tools/performance/artifact-binary/' + MANIFEST])
    require(len(raw) <= core.MAX_METADATA_BYTES and sha(raw) == PERFORMANCE_BASE_MANIFEST,
            'pinned performance predecessor manifest')
    prior = core.strict_json(raw)
    validate_macos_transition(prior, repository, core)
    changes = spec.get('performance_transition', {}).get('changes', {})
    require(set(changes) == PERFORMANCE_PATHS, 'exact performance source paths')
    expected = {**prior, 'changes': dict(prior['changes'])}
    for path in sorted(PERFORMANCE_PATHS):
        old = subprocess.check_output([*git, 'show', PERFORMANCE_BASE + ':' + path])
        require(len(old) <= core.MAX_SOURCE_BYTES, 'performance predecessor source bound')
        row = changes[path]
        require(type(row) is list and len(row) == 2 and row[0] == sha(old) and row[0] != row[1],
                'performance transition ' + path)
        previous = prior['changes'].get(path, [row[0], row[0]])
        require(previous[1] == row[0], 'performance predecessor endpoint ' + path)
        expected['changes'][path] = [previous[0], row[1]]
    expected['performance_transition'] = {
        'predecessor': PERFORMANCE_BASE, 'predecessor_tree': PERFORMANCE_TREE,
        'predecessor_manifest_sha256': PERFORMANCE_BASE_MANIFEST, 'changes': changes,
    }
    require(spec == expected, 'only the declared performance endpoints may change')


class Contract:
    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        self.directory = Path(directory).resolve(strict=True)
        self.source_root = Path(source_root or Path(history_root).parents[1]).resolve(strict=True)
        require(manifest_sha256 == MANIFEST_SHA256, 'expected independently pinned successor manifest')
        require(sha(manifest_bytes(self.directory)) == MANIFEST_SHA256, 'successor manifest SHA')
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
            raise ValueError('PR43 reconciliation source migration: full Git history required for pinned predecessor')
        self.archived = Path(archived_checkout(location).name)
        # Only the immutable tree supplies executable predecessor code. The caller's
        # bundle supplies its metadata, which the old constructor authenticates.
        old_dir = self.archived / 'tools/performance/artifact-binary'
        previous_type = module_at(old_dir / 'declid_contract.py').Contract
        self.previous = previous_type(self.directory, PREDECESSOR_MANIFEST,
                                      self.archived / 'tools/performance', self.archived)
        self.core = self.previous.core
        self.manifest_sha256 = manifest_sha256
        raw = self.core.read_file(self.directory, MANIFEST, self.core.MAX_METADATA_BYTES)
        require(sha(raw) == manifest_sha256, 'successor manifest SHA')
        spec = self.core.strict_json(raw)
        require(set(spec) == {'format', 'predecessor', 'changes', 'additions', 'maintenance', 'live_transition', 'performance_transition'} and
                spec['format'] == 'pr43-reconciliation-source-migration-v1' and spec['predecessor'] == PREDECESSOR,
                'successor manifest schema')
        validate_live_transition(spec, location, self.core)
        self.changes = spec['changes']
        self.maintenance = spec['maintenance']
        files = dict(self.previous.value['current_files'])
        for name, row in self.changes.items():
            require(len(row) == 2 and files[name] == row[0] and row[0] != row[1], 'source transition ' + name)
            files[name] = row[1]
        for name, digest in spec['additions'].items():
            require(name not in files, 'added path already owned: ' + name)
            files[name] = digest
        self.core.hash_map(files, 'PR43 reconciled files')
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
        self.metadata_paths = (*self.previous.metadata_paths, MANIFEST, 'reconciliation_contract.py')
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

    def _require_raw_map(self, value, expected, label):
        require(type(value) is dict and set(value) == set(expected), 'complete raw ' + label + ' paths')
        for path, raw in value.items():
            require(type(raw) is bytes and len(raw) <= self.core.MAX_SOURCE_BYTES and
                    sha(raw) == expected[path], 'complete raw ' + label + ' SHA: ' + path)

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
        self._require_raw_map(current, self.value['current_files'], 'DeclId current')
        previous = {p: self._older_bytes(raw, p) for p, raw in current.items()}
        return self.previous.project_tree_bytes({p: previous[p] for p in self.previous.value['current_files']})

    def advance_tree_bytes(self, parent, additions):
        self._require_raw_map(additions, {p: self.value['current_files'][p] for p in self.added_paths},
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
