"""Bridge the current test-framework sources to the fixed pre-migration tree."""

from functools import lru_cache
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile


BASELINE = '720dd649627fbf8b19c7447493a4fdf6fd05eb39'
BASELINE_TREE = '65a02f636c716d4f58a9997d87ec89677e41a609'
MANIFEST = 'test-framework-source-migration.json'
FOUNDATION_MANIFEST = 'foundation-source-migration.json'
FOUNDATION = 'd607907bda1ce5ac053dae10497dc1888b08f0fc'
FOUNDATION_TREE = '937e4b687ce8af86ffd4aa6fa239dfbe860ec1ef'
FOUNDATION_MERGE_PATHS = {'mlf.lock', 'tests/shared/MLF/Tests/SharedFrontend.hs'}
HOSTED_PARITY_CHANGES = {
    'mlf.lock': (
        '7f98e4a7552ef58cafd5b200f3dd722d127c23227e7d6bd5f53280fc84128d97',
        '88b174d70a31399b189fa0ab864ebe753bcf492ad30d400cdf9bff962b347663',
    ),
    'tests/Tests/CompilerTests.hs': (
        'ff14edf8bf979c34979117b2c1aff5c31b7c508d8f321474a3b40a548836d961',
        '57c8284be73681306fbcaa08a24bf54421628f4340fba403ff801c93b918e56b',
    ),
}
ARCHIVE_PATHS = (
    'bootstrap', 'host', 'libraries', 'package', 'runtime', 'testing', 'tests',
    'tools/performance', 'tools/shared', 'shared-sources.json', 'mlf.lock',
    'mlf-package.json', 'mlf-shared.cabal', 'cabal.project',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('test-framework source migration: ' + message)


def source_repository(history_root):
    for path in (history_root, Path.cwd()):
        result = subprocess.run(
            ['git', '-C', str(path), 'rev-parse', '--show-toplevel'],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    raise ValueError('test-framework source migration: full Git history required')


@lru_cache(maxsize=1)
def archived_baseline(repository):
    git = ['git', '--no-replace-objects', '-C', repository]
    tree = subprocess.check_output([*git, 'rev-parse', BASELINE + '^{tree}'], text=True).strip()
    require(tree == BASELINE_TREE, 'pinned pre-migration tree')
    directory = tempfile.TemporaryDirectory(prefix='mlf-test-migration-previous-')
    with subprocess.Popen([*git, 'archive', BASELINE, *ARCHIVE_PATHS], stdout=subprocess.PIPE) as archive:
        with tarfile.open(fileobj=archive.stdout, mode='r|') as stream:
            stream.extractall(directory.name, filter='data')
        require(archive.wait() == 0, 'cannot read pinned pre-migration tree')
    return directory


def baseline_root(history_root):
    return Path(archived_baseline(source_repository(history_root)).name)


def foundation_changes(spec, repository, files, framework_changes, framework_pin):
    require(set(spec) == {'commit', 'tree', 'framework_manifest_sha256', 'changes'} and
            spec['commit'] == FOUNDATION and spec['tree'] == FOUNDATION_TREE and
            spec['framework_manifest_sha256'] == framework_pin, 'exact Foundation transition identity')
    git = ['git', '--no-replace-objects', '-C', repository]
    tree = subprocess.check_output([*git, 'rev-parse', FOUNDATION + '^{tree}'], text=True).strip()
    require(tree == FOUNDATION_TREE, 'pinned Foundation tree')
    changed = subprocess.check_output([*git, 'diff-tree', '--no-commit-id', '--name-only',
                                       '--no-renames', '-r', FOUNDATION], text=True).splitlines()
    changes = spec['changes']
    require(changes.keys() == files.keys() & set(changed), 'complete Foundation source transition')
    require(changes.keys() & framework_changes.keys() == FOUNDATION_MERGE_PATHS,
            'exact Foundation overlap with the test-framework transition')
    for path, row in changes.items():
        prior = subprocess.check_output([*git, 'show', FOUNDATION + '^:' + path])
        branch = subprocess.check_output([*git, 'show', FOUNDATION + ':' + path])
        baseline_digest = framework_changes[path][0] if path in framework_changes else files[path]
        require(set(row) == {'framework', 'branch', 'merged'} and row['framework'] == files[path] and
                sha(prior) == baseline_digest and
                row['branch'] == sha(branch) and row['framework'] != row['merged'] and
                (path in FOUNDATION_MERGE_PATHS or row['merged'] == row['branch']),
                'Foundation source endpoint: ' + path)
    return {path: row['merged'] for path, row in changes.items()}


def successor_type(predecessor_type, predecessor_manifest, framework_pin, manifest_pin, read_implementation):
    """Reuse exact projection operations, adding a locally reviewed inventory edge."""

    class Contract(predecessor_type):
        def __init__(self, directory, manifest_sha256, history_root, source_root=None):
            self.directory = Path(directory).resolve(strict=True)
            raw = read_implementation(self.directory / MANIFEST)
            require(sha(raw) == framework_pin, 'pinned framework manifest SHA')
            foundation_raw = read_implementation(self.directory / FOUNDATION_MANIFEST)
            require(sha(foundation_raw) == manifest_pin == manifest_sha256, 'pinned Foundation manifest SHA')
            self.manifest_sha256 = manifest_sha256
            self.source_root = Path(source_root or Path(history_root).parents[1]).resolve(strict=True)
            repository = source_repository(history_root)
            self.archived = Path(archived_baseline(repository).name)
            archived_history = self.archived / 'tools/performance'
            self.previous = predecessor_type(self.directory, predecessor_manifest,
                                            archived_history, self.archived)
            self.core = self.previous.core
            spec = self.core.strict_json(raw)
            require(set(spec) == {'baseline', 'baseline_tree', 'predecessor_manifest_sha256',
                                  'changes', 'removed_modules', 'maintenance'} and
                    spec['baseline'] == BASELINE and spec['baseline_tree'] == BASELINE_TREE and
                    spec['predecessor_manifest_sha256'] == predecessor_manifest,
                    'exact predecessor identity and transition schema')
            self.changes = dict(spec['changes'])
            self.maintenance = spec['maintenance']
            old_files = self.previous.value['current_files']
            old_paths = self.previous.value['module_paths']
            retired = spec['removed_modules']
            require(retired == {'Tests.TupleListLegacy': old_paths['Tests.TupleListLegacy']},
                    'exact retired assertion module')
            self.removed_paths = frozenset(retired.values())
            files = {p: digest for p, digest in old_files.items() if p not in self.removed_paths}
            require(set(self.changes) <= files.keys(), 'transition outside predecessor inventory')
            for path, (old, new) in self.changes.items():
                require(old == old_files[path] and old != new, 'source transition: ' + path)
                files[path] = new
            foundation = foundation_changes(self.core.strict_json(foundation_raw), repository,
                                            files, self.changes, framework_pin)
            self.changes.update({path: [old_files[path], new] for path, new in foundation.items()})
            files.update(foundation)
            for path, (previous, current) in HOSTED_PARITY_CHANGES.items():
                require(files[path] == previous, 'hosted parity source transition: ' + path)
                self.changes[path] = [old_files[path], current]
                files[path] = current
            self.core.hash_map(files, 'current framework sources')
            paths = {n: p for n, p in old_paths.items() if n not in retired}
            self.value = {'current_files': files, 'module_paths': paths,
                          'current_registry': {n: files[p] for n, p in paths.items()}}
            self.live_source_inventory(self.source_root)
            registry = self.core.strict_json(self.core.read_file(self.source_root, 'shared-sources.json'))
            actual = {row['module']: row['path'] for row in registry['modules']}
            require(len(actual) == len(registry['modules']) and actual == paths,
                    'exact registered source ownership')

            self.parent = self.previous.parent
            self.maintenance_parent = self.previous.maintenance_parent
            self.evidence_source_root = self.previous.evidence_source_root
            self.added_modules = self.previous.added_modules
            self.added_paths = self.previous.added_paths
            require(not self.removed_paths.intersection(self.added_paths),
                    'retirement leaves historical addition evidence intact')
            self.metadata_paths = (*self.previous.metadata_paths, MANIFEST, FOUNDATION_MANIFEST, Path(__file__).name)
            history_names = set(self.parent['frozen_history']) | set(self.maintenance_parent['files'])
            require(self.maintenance.keys() <= history_names, 'unknown maintenance owner')
            for name in history_names:
                previous = self.core.read_file(archived_history, name)
                current = self.core.read_file(history_root, name)
                if name in self.maintenance:
                    require(self.maintenance[name] == [sha(previous), sha(current)] and
                            previous != current, 'maintenance transition: ' + name)
                else:
                    require(previous == current, 'undeclared historical change: ' + name)

        def live_source_inventory(self, root):
            for path in self.removed_paths:
                require(not os.path.lexists(Path(root) / path), 'retired source present: ' + path)
            return super().live_source_inventory(root)

        def project_tree_bytes(self, current):
            self._require_raw_map(current, self.value['current_files'], 'framework current')
            previous = {path: self._older_bytes(raw, path) for path, raw in current.items()}
            previous.update({p: self.core.read_file(self.archived, p) for p in self.removed_paths})
            return self.previous.project_tree_bytes(previous)

        def advance_tree_bytes(self, parent, additions):
            self._require_raw_map(additions, {p: self.value['current_files'][p] for p in self.added_paths},
                                  'framework historical additions')
            old = {p: self._older_bytes(raw, p) for p, raw in additions.items()}
            previous = self.previous.advance_tree_bytes(parent, old)
            current = {p: self._newer_bytes(raw, p) for p, raw in previous.items()
                       if p not in self.removed_paths}
            require(self.project_tree_bytes(current) == parent, 'whole framework source round trip')
            return current

    return Contract
