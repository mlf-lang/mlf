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
PHASE2_MANIFEST = 'foundation-phase2-source-migration.json'
PHASE2 = '2df930ce6fdd74af11c68d1cd3ecdec70d19119f'
PHASE2_TREE = '1079544662dce9f2596fa434fd00acba9e2b50ae'
PHASE2_INTERMEDIATE = '80b305b2580e3d941785072098493a3471a9dced'
PHASE2_BRANCH_PARENT = 'c253676070d4b094b6b1d4441cf4829f5ea4d8dd'
PHASE2_FRAMEWORK_PARENT = 'd09dfdd00141bc932b2d38b95f8343893abfed82'
PHASE2_FRAMEWORK_PARENT_TREE = 'b242d36eb97c4c76433851564f69e9d8c548f5c3'
HEAP_FORCE_MANIFEST = 'foundation-heap-force-source-migration.json'
HEAP_FORCE = '8558f0ff37425a3b432a87b0c9cb82ac7e77e1e8'
HEAP_FORCE_TREE = '67932b8d16df683bd53e6715923fe49b51d488ec'
HEAP_FORCE_FRAMEWORK_PARENT = 'e3ea95192453cb49965d6c9bedd0a45effe5bae9'
HEAP_FORCE_FRAMEWORK_PARENT_TREE = '577aef9b8bf17e127dc245614d70d56eb5c6a5fb'
DICTIONARY_DEMAND_MANIFEST = 'foundation-dictionary-demand-source-migration.json'
DICTIONARY_DEMAND = 'ca21a467577d31465607f1354b810e1374db93ce'
DICTIONARY_DEMAND_TREE = '0908efeb9e9b070d41f543c94d2d8d35dc9c63d8'
DICTIONARY_DEMAND_FRAMEWORK_PARENT = 'fa863042fe3fe16ca7e0a9d43b43a0d8abe728de'
DICTIONARY_DEMAND_FRAMEWORK_PARENT_TREE = '9d48c05097b968ce7d13d74b3403873750420c00'
THUNK_CAPTURES_MANIFEST = 'foundation-thunk-captures-source-migration.json'
THUNK_CAPTURES = '48d498a6696031323a2b3eac8bad10e4c3155d9b'
THUNK_CAPTURES_TREE = 'b1460a6a9277cda0747ce1a120dd01ec9f92890a'
THUNK_CAPTURES_FRAMEWORK_PARENT = '6805162d120b6fda66b82cc6a48e8f0490a446ef'
THUNK_CAPTURES_FRAMEWORK_PARENT_TREE = 'd4a2027dc925c9c8139fe90f28a965a4f3b5e712'
CHECKED_DISPATCH_MANIFEST = 'foundation-checked-dispatch-source-migration.json'
CHECKED_DISPATCH = '945689c219723e3bc8b1f3327ced109a13363bee'
CHECKED_DISPATCH_TREE = 'b8a4cab72284b9ad928ff73cb5462a62c2d9cada'
CHECKED_DISPATCH_FRAMEWORK_PARENT = '719fd4e4fc04a5c3f9c48621eee0d43b905454c2'
CHECKED_DISPATCH_FRAMEWORK_PARENT_TREE = '656eeb86fbbcc9fac5a78503624305646f75b2e0'
FOUNDATION_MERGE_PATHS = {'mlf.lock', 'tests/shared/MLF/Tests/SharedFrontend.hs'}
HOSTED_PARITY_CHANGES = {
    'mlf.lock': (
        '7f98e4a7552ef58cafd5b200f3dd722d127c23227e7d6bd5f53280fc84128d97',
        'e7caa82b98dcfa22d52c9cda775f6ae95b255b8941bb31c7677d4f4056a0d6c1',
    ),
    'tests/Tests/CompilerTests.hs': (
        'ff14edf8bf979c34979117b2c1aff5c31b7c508d8f321474a3b40a548836d961',
        '65ef8e082ef3fdd551514ec97912011d058792a29f00b2b1423c522377437068',
    ),
}
COMPACT_SCOPE_MAINTENANCE = {
    'patricia/run_integrated.py': (
        '4fd2ad1497834d43189800dc720457fbe62c02511911d8c89317534336115744',
        '73885e37b41a19fbfb1307386ba073e44ea43dd313a8ec49216656164ae36db1',
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


def phase2_changes(spec, repository, files, predecessor_pin, pin_key, branch, tree,
                   framework, framework_tree, parents):
    require(set(spec) == {'commit', 'tree', 'framework_parent', 'framework_parent_tree',
                          pin_key, 'changes'} and
            spec['commit'] == branch and spec['tree'] == tree and
            spec['framework_parent'] == framework and
            spec['framework_parent_tree'] == framework_tree and
            spec[pin_key] == predecessor_pin,
            'exact Phase 2 transition identity')
    git = ['git', '--no-replace-objects', '-C', repository]

    def revision(expr):
        return subprocess.check_output([*git, 'rev-parse', '--verify', expr], text=True).strip()

    require(revision(branch + '^{tree}') == tree and
            revision(framework + '^{tree}') == framework_tree and
            all(revision(child + '^') == parent
                for child, parent in zip((branch, *parents[:-1]), parents)),
            'pinned Phase 2 trees and ancestry')
    changed = subprocess.check_output([*git, 'diff-tree', '--no-commit-id', '--name-only',
                                      '--no-renames', '-r', parents[-1], branch],
                                     text=True).splitlines()
    changes = spec['changes']
    require(changes.keys() == files.keys() & set(changed), 'complete Phase 2 source transition')
    for path, row in changes.items():
        def at(commit):
            return sha(subprocess.check_output([*git, 'show', commit + ':' + path]))
        require(set(row) == {'branch_parent', 'framework', 'branch', 'merged'} and
                row['branch_parent'] == at(parents[-1]) and
                row['framework'] == files[path] == at(framework) and
                row['branch'] == at(branch) and row['framework'] != row['merged'] and
                (path == 'mlf.lock' or row['merged'] == row['branch']),
                'Phase 2 source endpoint: ' + path)
    return {path: row['merged'] for path, row in changes.items()}


def successor_type(predecessor_type, predecessor_manifest, framework_pin, foundation_pin,
                   phase2_pin, heap_force_pin, dictionary_demand_pin, thunk_captures_pin, checked_dispatch_pin, read_implementation):
    """Reuse exact projection operations, adding a locally reviewed inventory edge."""

    class Contract(predecessor_type):
        def __init__(self, directory, manifest_sha256, history_root, source_root=None):
            self.directory = Path(directory).resolve(strict=True)
            raw = read_implementation(self.directory / MANIFEST)
            require(sha(raw) == framework_pin, 'pinned framework manifest SHA')
            foundation_raw = read_implementation(self.directory / FOUNDATION_MANIFEST)
            require(sha(foundation_raw) == foundation_pin, 'pinned Foundation manifest SHA')
            phase2_raw = read_implementation(self.directory / PHASE2_MANIFEST)
            require(sha(phase2_raw) == phase2_pin, 'pinned Phase 2 manifest SHA')
            heap_force_raw = read_implementation(self.directory / HEAP_FORCE_MANIFEST)
            require(sha(heap_force_raw) == heap_force_pin, 'pinned heap-force manifest SHA')
            dictionary_demand_raw = read_implementation(self.directory / DICTIONARY_DEMAND_MANIFEST)
            require(sha(dictionary_demand_raw) == dictionary_demand_pin,
                    'pinned dictionary-demand manifest SHA')
            thunk_captures_raw = read_implementation(self.directory / THUNK_CAPTURES_MANIFEST)
            require(sha(thunk_captures_raw) == thunk_captures_pin,
                    'pinned thunk-captures manifest SHA')
            checked_dispatch_raw = read_implementation(self.directory / CHECKED_DISPATCH_MANIFEST)
            require(sha(checked_dispatch_raw) == checked_dispatch_pin == manifest_sha256,
                    'pinned checked-dispatch manifest SHA')
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
            self.maintenance = dict(spec['maintenance'])
            for name, (previous, current) in COMPACT_SCOPE_MAINTENANCE.items():
                original, migrated = self.maintenance[name]
                require(migrated == previous, 'compact scope maintenance transition: ' + name)
                self.maintenance[name] = [original, current]
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
            for data, pin, key, branch, tree, framework, framework_tree, parents in (
                    (phase2_raw, foundation_pin, 'foundation_manifest_sha256', PHASE2, PHASE2_TREE,
                     PHASE2_FRAMEWORK_PARENT, PHASE2_FRAMEWORK_PARENT_TREE,
                     (PHASE2_INTERMEDIATE, PHASE2_BRANCH_PARENT)),
                    (heap_force_raw, phase2_pin, 'phase2_manifest_sha256', HEAP_FORCE, HEAP_FORCE_TREE,
                     HEAP_FORCE_FRAMEWORK_PARENT, HEAP_FORCE_FRAMEWORK_PARENT_TREE, (PHASE2,)),
                    (dictionary_demand_raw, heap_force_pin, 'heap_force_manifest_sha256',
                     DICTIONARY_DEMAND, DICTIONARY_DEMAND_TREE, DICTIONARY_DEMAND_FRAMEWORK_PARENT,
                     DICTIONARY_DEMAND_FRAMEWORK_PARENT_TREE, (HEAP_FORCE,)),
                    (thunk_captures_raw, dictionary_demand_pin, 'dictionary_demand_manifest_sha256',
                     THUNK_CAPTURES, THUNK_CAPTURES_TREE, THUNK_CAPTURES_FRAMEWORK_PARENT,
                     THUNK_CAPTURES_FRAMEWORK_PARENT_TREE, (DICTIONARY_DEMAND,)),
                    (checked_dispatch_raw, thunk_captures_pin, 'thunk_captures_manifest_sha256',
                     CHECKED_DISPATCH, CHECKED_DISPATCH_TREE, CHECKED_DISPATCH_FRAMEWORK_PARENT,
                     CHECKED_DISPATCH_FRAMEWORK_PARENT_TREE, (THUNK_CAPTURES,))):
                edge = phase2_changes(self.core.strict_json(data), repository, files, pin, key,
                                      branch, tree, framework, framework_tree, parents)
                self.changes.update({path: [old_files[path], new] for path, new in edge.items()})
                files.update(edge)
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
            self.metadata_paths = (*self.previous.metadata_paths, MANIFEST, FOUNDATION_MANIFEST,
                                   PHASE2_MANIFEST, HEAP_FORCE_MANIFEST, DICTIONARY_DEMAND_MANIFEST,
                                   THUNK_CAPTURES_MANIFEST, CHECKED_DISPATCH_MANIFEST, Path(__file__).name)
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
