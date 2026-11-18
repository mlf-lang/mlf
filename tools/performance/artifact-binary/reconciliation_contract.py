"""Authenticate PR43 reconciliation before reversible historical source projection."""
from functools import lru_cache
import hashlib
import json
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
MANIFEST_SHA256 = '2fb0e643dbae16d9188127dfae795aa82e37dbb223c26d55c142cbecf71e01d2'
INFERRED_CHAIN_MANIFEST_SHA256 = 'f611478915e5da8a47ee1d065f17ab26152029efb847418e0d6e0580b23cca74'
COMPILER_SOURCE_EDGES = [
    '119554684dde21433b8068a044ca7155a9a9fe7b42c6f484025730deaefbaf23',
    '8ea021f075aebc58394ac3e317e11a504f46efe5fbea432ccc30fb72dd2b5874',
    '5e7780d90e30581a5d5ee75413ff88f5157b0289347a6cd408ea52cb4fb5986a',
    '5153b754ad34b79a92f50c5c6b4fffccecb40159aae9bd80cbdc687dfb18892e',
    '6a0dfd2b44d1317e92940779e1cd9034ecb7e4c7b87c56b7cdca0d735a5e8446',
    '110168e3fa536e65cb01d471f4f3c3f47ec45c708e5d88e4ba94ff4c7e638dca',
    '91ede30a8620dddabf6c64221574b828ffa55e386e14c15986500ae372e1be3d',
    'b7ddd603409f79dff84f3624b66f676dffcd3ff63b4479ace0136f96441f8613',
]
ADAPTER_MANIFEST_SHA256 = '6bbc1da597cb7eaaeab16aff52e8b44e2d4dc11ff10997679a45b3405bf0be98'
CHAIN_EDGE_SHA256 = '5acc941d400b8b194ca97ca6a3c3ad6322e199279191bbf7b2d5816dab59841c'
PREDECESSOR_IMPLEMENTATION = '7cacadad979f3db29da9067b5fe0ca8e1634d960dbf978ad6d5cae39ba338794'
LIVE_PREDECESSOR = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
LIVE_PREDECESSOR_TREE = '3148203097e7622ced1b272e606bfa892fad746b'
LIVE_PREDECESSOR_MANIFEST = '63598306f049a050def3fd21ddf21878a7f4f882b59a48a86c53a3398624e9c5'
LIVE_TRANSITION_PATH = 'tools/shared/build.py'
LIVE_PREDECESSOR_SOURCE = 'eff291112f318206ce0f7ab85cb8a2e474be41489441204696630a395f4ca3df'
PERFORMANCE_BASE = 'fc300bc9fdc389b585cbef0630fc8915d53e89c5'
PERFORMANCE_TREE = '386f0b41ab5f9b39fca273f3040f51d73df924a1'
PERFORMANCE_BASE_MANIFEST = 'ebe5671476447cd4b256784e7d898ed6095c7c54cc9286c6869ca4909b2b708b'
PERFORMANCE_MAINTENANCE_PATH = 'patricia/test_adapters.py'
ADAPTER_BASE = '08a08aa98c01f4f07b6efb01a250a0d86f387811'
ADAPTER_TREE = 'eec52972c0028a7f1d20da0ac15f867664c2c918'
ADAPTER_BASE_MANIFEST = '82b9b045993ff9ac2d14a5b67dbfd35288004a79ae08303a1047f81de438d009'
ADAPTER_PATH = 'patricia/adapt_oracles.py'
ADAPTER_OLD_SHA = '45ce4b0fac779be59272e1a9ae377115c1c91a7e03f6acf77588c41aea40af0e'
ADAPTER_OLD_DECLARATION = b"LIVE_SESSION_HEADER = 'module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller) where {'"
ADAPTER_NEW_DECLARATION = b"LIVE_SESSION_HEADER = 'module Bootstrap.CrateSession (compileSpecFile, compileSpecFileWithPrelude, compileSpecFileWithVerification, compileSpecFileUsingInstaller,\\n    CompiledCrate, compiledObject, compiledInterfaces, compileSpecFileRetainedUsingInstaller) where {'"
PERFORMANCE_PATHS = {
    'bootstrap/MLF/BuiltinPreludeData.hs',
    'bootstrap/MLF/Entry/Emlf.hs',
    'bootstrap/MLF/PreparedCompiler.hs',
    'host/ghc/MLF/Host/Base.hs',
    'host/ghc/MLF/Host/IO.hs',
    'host/ghc/MLF/Primitive.hs',
    'host/ghc/cbits/host.c',
    'libraries/mlf-crates/Bootstrap/ArtifactStructure.hs',
    'libraries/mlf-crates/Bootstrap/Bitstream.hs',
    'libraries/mlf-crates/Bootstrap/BuiltinPreludeContext.hs',
    'libraries/mlf-crates/Bootstrap/BuiltinPreludeLiteral.hs',
    'libraries/mlf-crates/Bootstrap/Crate.hs',
    'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
    'libraries/mlf-crates/Bootstrap/CrateGraph.hs',
    'libraries/mlf-crates/Bootstrap/CrateQuery.hs',
    'libraries/mlf-crates/Bootstrap/CrateSession.hs',
    'libraries/mlf-crates/Bootstrap/InferenceUnit.hs',
    'libraries/mlf-crates/Bootstrap/OpenFragment.hs',
    'libraries/mlf-crates/Bootstrap/QueryGraph.hs',
    'libraries/mlf-crates/Bootstrap/Separate.hs',
    'libraries/mlf-crates/Bootstrap/SourceEquality.hs',
    'libraries/mlf-crates/Bootstrap/SourceInference.hs',
    'libraries/mlf-foundation/Bootstrap/Fresh.hs',
    'libraries/mlf-foundation/Bootstrap/Host.hs',
    'libraries/mlf-foundation/Bootstrap/Map.hs',
    'libraries/mlf-foundation/Bootstrap/Types.hs',
    'libraries/mlf-frontend/Bootstrap/Layout.hs',
    'libraries/mlf-frontend/Bootstrap/Lexer.hs',
    'libraries/mlf-frontend/Bootstrap/Module.hs',
    'libraries/mlf-frontend/Bootstrap/Parsec.hs',
    'libraries/mlf-frontend/Bootstrap/Parser.hs',
    'libraries/mlf-inference/Bootstrap/Classes.hs',
    'libraries/mlf-interpreter/Bootstrap/Runtime.hs',
    'libraries/mlf-language-core/Bootstrap/Primitive.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM/Codegen.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM/Library.hs',
    'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs',
    'libraries/mlf-package-core/Package/Build.hs',
    'libraries/mlf-package-core/Package/Scheduler.hs',
    'mlf-shared.cabal',
    'mlf.lock',
    'runtime/mlf_build_runner_hash.h',
    'runtime/mlf_runtime.c',
    'runtime/mlf_runtime.h',
    'shared-sources.json',
    'tests/shared/MLF/Tests/SharedFrontend.hs',
    'tools/shared/build.py',
    'tools/shared/test_direct.py',
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


def validate_performance_transition(spec, repository, core):
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
    # This one live boundary test follows the performance source transition.
    # Authenticate its physical intermediate endpoint, not just a mutable row.
    maintenance = spec.get('performance_transition', {}).get('maintenance', {})
    name = PERFORMANCE_MAINTENANCE_PATH
    require(type(maintenance) is dict and set(maintenance) == {name},
            'exact performance maintenance paths')
    old = subprocess.check_output([*git, 'show', PERFORMANCE_BASE + ':tools/performance/' + name])
    row = maintenance[name]
    previous = prior['maintenance'][name]
    require(len(old) <= core.MAX_SOURCE_BYTES and sha(old) == previous[1],
            'performance predecessor maintenance source')
    require(type(row) is list and len(row) == 2 and row[0] == sha(old) and
            type(row[1]) is str and len(row[1]) == 64 and
            all(c in '0123456789abcdef' for c in row[1]) and row[0] != row[1],
            'performance maintenance transition')
    expected['maintenance'] = {**prior['maintenance'], name: [previous[0], row[1]]}
    expected['performance_transition'] = {
        'predecessor': PERFORMANCE_BASE, 'predecessor_tree': PERFORMANCE_TREE,
        'predecessor_manifest_sha256': PERFORMANCE_BASE_MANIFEST, 'changes': changes,
        'maintenance': maintenance,
    }
    require(spec == expected, 'only the declared performance endpoints may change')


def validate_adapter_successor(spec, prior_raw, old_source, current_source, tree, core):
    """One reversible test-header edit, after an immutable complete predecessor."""
    require(tree == ADAPTER_TREE, 'fixed adapter predecessor tree')
    require(sha(prior_raw) == ADAPTER_BASE_MANIFEST, 'fixed adapter predecessor manifest')
    require(sha(old_source) == ADAPTER_OLD_SHA, 'fixed adapter predecessor source')
    require(old_source.count(ADAPTER_OLD_DECLARATION) == 1 and
            ADAPTER_NEW_DECLARATION not in old_source, 'unique previous adapter declaration')
    expected_source = old_source.replace(ADAPTER_OLD_DECLARATION, ADAPTER_NEW_DECLARATION)
    require(current_source == expected_source and current_source.count(ADAPTER_NEW_DECLARATION) == 1 and
            current_source.replace(ADAPTER_NEW_DECLARATION, ADAPTER_OLD_DECLARATION) == old_source,
            'exact reversible adapter header change')
    prior = core.strict_json(prior_raw)
    require(ADAPTER_PATH not in prior['maintenance'], 'unchanged adapter at predecessor')
    row = [ADAPTER_OLD_SHA, sha(current_source)]
    expected = {**prior, 'maintenance': {**prior['maintenance'], ADAPTER_PATH: row},
        'adapter_successor': {'predecessor': ADAPTER_BASE, 'predecessor_tree': ADAPTER_TREE,
            'predecessor_manifest_sha256': ADAPTER_BASE_MANIFEST, 'maintenance': {ADAPTER_PATH: row}}}
    require(spec == expected, 'only declared adapter successor may change')
    return prior


def validate_adapter_transition(spec, repository, core, history_root=None):
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    tree = subprocess.check_output([*git, 'rev-parse', ADAPTER_BASE + '^{tree}'], text=True).strip()
    prior_raw = subprocess.check_output([*git, 'show', ADAPTER_BASE + ':tools/performance/artifact-binary/' + MANIFEST])
    old_source = subprocess.check_output([*git, 'show', ADAPTER_BASE + ':tools/performance/' + ADAPTER_PATH])
    require(len(prior_raw) <= core.MAX_METADATA_BYTES and len(old_source) <= core.MAX_SOURCE_BYTES,
            'adapter predecessor byte bounds')
    current = core.read_file(Path(history_root) if history_root is not None else Path(repository) / 'tools/performance', ADAPTER_PATH)
    prior = validate_adapter_successor(spec, prior_raw, old_source, current, tree, core)
    validate_performance_transition(prior, repository, core)


def canonical_manifest(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


def rewind_sources(current, delta):
    changes = dict(current)
    for path, (old, new) in delta.items():
        # A return to the original bytes disappears from the cumulative table.
        first, last = changes.get(path, [new, new])
        require(old != new and last == new, 'compiler source endpoint: ' + path)
        if first == old:
            changes.pop(path, None)
        else:
            changes[path] = [first, old]
    return changes


def compiler_history(spec):
    """Reconstruct complete manifests back to the published inferred-chain merge."""
    edges = spec.get('compiler_source_transitions')
    require(type(edges) is list and [sha(canonical_manifest(edge)) for edge in edges] == COMPILER_SOURCE_EDGES,
            'fixed compiler source transitions')
    history = [spec]
    for index in reversed(range(len(edges))):
        edge = edges[index]
        current = history[-1]
        prior = {**current, 'changes': rewind_sources(current['changes'], edge['changes'])}
        if 'maintenance' in edge:
            prior['maintenance'] = rewind_sources(current['maintenance'], edge['maintenance'])
        if index:
            prior['compiler_source_transitions'] = edges[:index]
        else:
            del prior['compiler_source_transitions']
        require(sha(canonical_manifest(prior)) == edge['predecessor_manifest_sha256'],
                'complete compiler source predecessor')
        history.append(prior)
    require(sha(canonical_manifest(history[-1])) == INFERRED_CHAIN_MANIFEST_SHA256, 'published inferred-chain manifest')
    return history


def chain_predecessor(spec):
    prior = dict(spec)
    edge = prior.pop('inferred_chain_transition', None)
    require(sha(canonical_manifest(edge)) == CHAIN_EDGE_SHA256, 'fixed inferred-chain transition')
    prior['changes'] = rewind_sources(prior['changes'], edge['changes'])
    require(sha(canonical_manifest(prior)) == ADAPTER_MANIFEST_SHA256, 'entire adapter endpoint')
    return prior


def adapter_endpoint(spec):
    """Recover the exact adapter manifest without requiring a checkout."""
    return chain_predecessor(compiler_history(spec)[-1])


def validate_live_transition(spec, repository, core, history_root=None):
    git = ['git', '--no-replace-objects', '-C', str(repository)]
    manifest_path = 'tools/performance/artifact-binary/' + MANIFEST

    def at(commit, path, limit):
        data = subprocess.check_output([*git, 'show', commit + ':' + path])
        require(len(data) <= limit, 'compiler source byte bound: ' + path)
        return data

    history = compiler_history(spec)
    for current, previous in zip(history, history[1:]):
        delta = current['compiler_source_transitions'][-1]
        commit = delta['predecessor']
        tree = subprocess.check_output([*git, 'rev-parse', commit + '^{tree}'], text=True).strip()
        require(tree == delta['predecessor_tree'], 'compiler source predecessor tree')
        require(at(commit, manifest_path, core.MAX_METADATA_BYTES) == canonical_manifest(previous),
                'archived compiler source manifest')
        for path, (old, _) in delta['changes'].items():
            require(sha(at(commit, path, core.MAX_SOURCE_BYTES)) == old, 'archived compiler source: ' + path)
        for name, (old, _) in delta.get('maintenance', {}).items():
            require(name == PERFORMANCE_MAINTENANCE_PATH and
                    sha(at(commit, 'tools/performance/' + name, core.MAX_SOURCE_BYTES)) == old,
                    'archived compiler maintenance source: ' + name)

    spec = history[-1]
    prior = chain_predecessor(spec)
    validate_adapter_transition(prior, repository, core, history_root)
    edge = spec['inferred_chain_transition']
    base, measured = edge['predecessor'], edge['measured']
    for role, commit in [('predecessor', base), ('measured', measured)]:
        tree = subprocess.check_output([*git, 'rev-parse', commit + '^{tree}'], text=True).strip()
        require(tree == edge[role + '_tree'], 'inferred-chain ' + role + ' tree')
    base_raw = at(base, manifest_path, core.MAX_METADATA_BYTES)
    measured_raw = at(measured, manifest_path, core.MAX_METADATA_BYTES)
    require(sha(base_raw) == edge['predecessor_manifest_sha256'] == ADAPTER_MANIFEST_SHA256 and
            core.strict_json(base_raw) == prior, 'complete inferred-chain predecessor')
    require(sha(measured_raw) == edge['measured_manifest_sha256'], 'measured source manifest')
    before = prior['changes']
    after = core.strict_json(measured_raw)['changes']
    require(before.keys() <= after.keys(), 'inferred-chain source removed')
    changed = {path for path in after if before.get(path) != after[path]}
    require(changed == set(edge['changes']), 'exact inferred-chain source paths')
    for path in changed:
        old = sha(at(base, path, core.MAX_SOURCE_BYTES))
        new = sha(at(measured, path, core.MAX_SOURCE_BYTES))
        first, last = before.get(path, [old, old])
        require(last == old and old != new and edge['changes'][path] == [old, new] and
                after[path] == [first, new], 'inferred-chain source transition: ' + path)
    require(after == spec['changes'], 'exact measured compiler source endpoints')


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
        require(set(spec) == {'format', 'predecessor', 'changes', 'additions', 'maintenance', 'live_transition', 'performance_transition', 'adapter_successor', 'inferred_chain_transition', 'compiler_source_transitions'} and
                spec['format'] == 'pr43-reconciliation-source-migration-v1' and spec['predecessor'] == PREDECESSOR,
                'successor manifest schema')
        validate_live_transition(spec, location, self.core, history_root)
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
