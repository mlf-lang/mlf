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
RECURSIVE_WORKERS_MANIFEST = 'foundation-recursive-workers-source-migration.json'
RECURSIVE_WORKERS = 'a69bb9d7b528092ecd54fbb3057f24c6e713c2b1'
RECURSIVE_WORKERS_TREE = 'e7e17222e2d2d413f21d075319575f697c0274b7'
RECURSIVE_WORKERS_BRANCH_PARENT = '4723a9fe71e53d4556e76e23db1951b81fab7dde'
RECURSIVE_WORKERS_FRAMEWORK_PARENT = '456c2cda46012554f92f174b8dda57e8eebffa65'
RECURSIVE_WORKERS_FRAMEWORK_PARENT_TREE = 'e9ba0b557dbecac05ac535db5cb17cdc80925fde'
COLD_CRATES_MANIFEST = 'foundation-cold-crates-source-migration.json'
COLD_CRATES = '05fccdef6b8c41e00b8753b657ddf2568028e67b'
COLD_CRATES_TREE = '41612f7d403c536f8c08041e818a199d8f71e7e9'
COLD_CRATES_BRANCH_PARENT = '3397a9a8655bee8904f7d077b00f8a5431262e55'
COLD_CRATES_FRAMEWORK_PARENT = 'e82358f421ac929b53e8c0bd7f58f8869ae1a7cd'
COLD_CRATES_FRAMEWORK_PARENT_TREE = '4f45ba118694f4cddfd5a6e45e55d10df95e669a'
# These three merged sources differ from both parents: the combined generator
# identity, C4 survivor demand plus retaining expansion, and the source lock.
# The generator identity is not an executable regeneration receipt.
COLD_CRATES_MERGED = {
    'bootstrap/MLF/BuiltinPreludeData.hs':
        '912284252eee6ba26d26a4af528eb9f71db81775e3675ac88c5d0e1cd29cb1f9',
    'libraries/mlf-inference/Bootstrap/Graph/Solver.hs':
        '3f596788575624c35803217f85b79c7a807a157a40773865b71476c1137c6e8a',
    'mlf.lock':
        '5735f8a1de3f6c8cc7c9014d611f8df44510700c4aa88384a52213a8de5ff087',
}
# Local worker-attribute follow-up. Retain the cold branch lowerer and lock as
# authenticated endpoints; this is a source transition, not a performance receipt.
LOCAL_WORKER_POLICY = {
    'libraries/mlf-llvm/Bootstrap/LLVM/Build.hs': (
        'df11e203f7ab7b12a6b099218d35215ddfd12a93d2c75fbd02f7d2e6979b51c1',
        '1702e6110830367a5dfeabcc7c4cb3a0172fbfabae26a40c8069fbec9792ec16',
    ),
    'mlf.lock': (
        '5735f8a1de3f6c8cc7c9014d611f8df44510700c4aa88384a52213a8de5ff087',
        '3ec3bf20b6d1ddcd55d182430ab681d3d63171e0fade2690a9a1d126929377e7',
    ),
}
CHECKED_GRAPH_MANIFEST = 'foundation-checked-graph-source-migration.json'
CHECKED_GRAPH = '3278a3e09e69031c847b3200810095e8097fe1f7'
CHECKED_GRAPH_TREE = 'c44d1ab36554b9d27dc8e83f28522d644646979e'
CHECKED_GRAPH_FRAMEWORK_PARENT = '265560ef383526c66126a9e79580e39bb4850973'
CHECKED_GRAPH_FRAMEWORK_PARENT_TREE = '1ae66b30d25c084ae306ef8b7409396135be75b0'
CHECKED_GRAPH_PARENTS = (
    '1891f0232b7ad1feacd5dc65f62ad15ccbbc1b1f', '83dbeab115c665e83991fd74369312809d831858',
    '83cd0fe62fc4d0162a821cb4e27c9c6068c6e7ff', '18ef7d72a21203ece47f53129abbaa21a05652ff', COLD_CRATES,
)
# Both lineages change the builtin identity and source lock. These are
# source endpoints, not evidence of a fresh canonical generator run.
CHECKED_GRAPH_MERGED = {
    'bootstrap/MLF/BuiltinPreludeData.hs':
        'f7ac348252aff20e7b60d7fe752b67b828df40ed6a6333a281924d07bd2fae50',
    'mlf.lock':
        '253109c4f37cb9b24c25f6359ca7a2a8782f0b9140ff8e8dae74ad16d5bb4ace',
}

# Follow the published dictionary-spine fast-forward from the prior tree.
DICTIONARY_SPINE = 'b29ceb3f118b606b437dbd23ac9215bb4dd7244e'
DICTIONARY_SPINE_TREE = 'a845f7dee50ebd2243b9474d8a55ec4870d493ed'
DICTIONARY_SPINE_PARENT = '12888ebff944e948fd0ac0ce53c3bfa0fb9744b5'
DICTIONARY_SPINE_PARENT_TREE = '36dd97ac864c5443d56ee57cb4392543dde312aa'
DICTIONARY_SPINE_CHANGES = {
    'bootstrap/MLF/BuiltinPreludeData.hs': (
        'fe13defe8bf31903646c68251d95fa63c4d2d8227c6a62d97cb3bf99f2a25d1d',
        '8765ad88f32a4250fb5f90516d2206db6d3124bda3f8b0815eb9734d40664ae4',
        'f7ac348252aff20e7b60d7fe752b67b828df40ed6a6333a281924d07bd2fae50',
        'ae182e9ab7be9fe364fa952e129560b8b198e2fe8b8bd2c12264a8dbaa1588e4',
    ),
    'libraries/mlf-crates/Bootstrap/SourceInference.hs': (
        'c78e7fe48c1936bd9f60bbd5b2aa0b9f432dd811da2b6b44a0c3e9618411ed5a',
        '7377c30b72bf5dfcfe55883d967a23fdbfe0ab1bfe9217f9dcec1b5968aa50dc',
        'c78e7fe48c1936bd9f60bbd5b2aa0b9f432dd811da2b6b44a0c3e9618411ed5a',
        '7377c30b72bf5dfcfe55883d967a23fdbfe0ab1bfe9217f9dcec1b5968aa50dc',
    ),
    'mlf.lock': (
        '502f83f784cf97bd68d45729fdb0d3c3a67cf1f9253b870b4b38438a99cc5931',
        '65e308f6ee4a48f7a1aa1010f9d9d70dfdfcec14512969773a1be903c58b2e9d',
        '253109c4f37cb9b24c25f6359ca7a2a8782f0b9140ff8e8dae74ad16d5bb4ace',
        '0fed9ed0448957d03f4a2827ef662c8140ce27a312b3bd654e5d1d8bf03b0dcd',
    ),
}

# The closed-spine follow-up has a separate authenticated published parent.
CLOSED_DICTIONARY_SPINE = '9b605fc5c90afa2be83950d0c9b3dfef4eafd05f'
CLOSED_DICTIONARY_SPINE_TREE = 'a7fc2e38c4306a9d8a5fafa602a1eb0467aad28a'
CLOSED_DICTIONARY_SPINE_PARENT = 'b29ceb3f118b606b437dbd23ac9215bb4dd7244e'
CLOSED_DICTIONARY_SPINE_PARENT_TREE = 'a845f7dee50ebd2243b9474d8a55ec4870d493ed'
CLOSED_DICTIONARY_SPINE_CHANGES = {
    'bootstrap/MLF/BuiltinPreludeData.hs': (
        '8765ad88f32a4250fb5f90516d2206db6d3124bda3f8b0815eb9734d40664ae4',
        'a59bed925a57dc4424643c1734d8d15427a647830d0564f46ca57bb010b00e17',
        'ae182e9ab7be9fe364fa952e129560b8b198e2fe8b8bd2c12264a8dbaa1588e4',
        '6219f9732b967647e41edb7b59ae4ca4721dcdd80ab0db9e74368ea62e85dd91',
    ),
    'libraries/mlf-crates/Bootstrap/SourceInference.hs': (
        '7377c30b72bf5dfcfe55883d967a23fdbfe0ab1bfe9217f9dcec1b5968aa50dc',
        'a8d6f2623bbdfc01333dfb0a01ec9fe8d26eee36cdcfa6cadf590c6ee6b199e8',
        '7377c30b72bf5dfcfe55883d967a23fdbfe0ab1bfe9217f9dcec1b5968aa50dc',
        'a8d6f2623bbdfc01333dfb0a01ec9fe8d26eee36cdcfa6cadf590c6ee6b199e8',
    ),
    'mlf.lock': (
        '65e308f6ee4a48f7a1aa1010f9d9d70dfdfcec14512969773a1be903c58b2e9d',
        '705465fb3691a98be91c3aa259ad2440ea921f395209044b8ac6364c97e111b2',
        '0fed9ed0448957d03f4a2827ef662c8140ce27a312b3bd654e5d1d8bf03b0dcd',
        'a92e9f9d2f88323b743d72a7cdffe711eab83862947f7a2cc0552177b187465b',
    ),
}
# Extend the Foundation endpoints with the two separately reviewed admission splits.
INFERENCE_ADMISSION_CHANGES = {
    'libraries/mlf-crates/Bootstrap/InferenceUnit.hs': (
        'b0340adef4cc594e89639026ea51ad254477598207066407dff6bf8cbd107880',
        'ab2c78c4699ae9d28446e063d32f04c1db9c1277ebf4fb27f6f980ca89eb06a6',
    ),
    'tests/shared/MLF/Tests/SharedFrontend.hs': (
        '0cd275af5b468182e5f8bd48a6f8f706b67bf8369f023f17b23629b1105fc2c8',
        'ebb4120d9ec3abb5fb8ff4f829dba01e9f5d3717106bdf44cb5d2a1ec3a46474',
    ),
    'bootstrap/MLF/BuiltinPreludeData.hs': (
        '6219f9732b967647e41edb7b59ae4ca4721dcdd80ab0db9e74368ea62e85dd91',
        'c06e31af69b3b5b584b46521a589f7bf380be9b80bc73aec1a2f26d6fd3a55ea',
    ),
    'mlf.lock': (
        'a92e9f9d2f88323b743d72a7cdffe711eab83862947f7a2cc0552177b187465b',
        'c2a42407201430c3e0aaa178293347787f154a8d6df5735a9a9598d12eaf4972',
    ),
}
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
# Local prepared-solver repair: only survivor demand and its lock digest change.
C4_SURVIVOR_DEMAND_CHANGES = {
    'libraries/mlf-inference/Bootstrap/Graph/Solver.hs': (
        'df197571d58c89faef47b23a645cba89585093e5d6387fc9cc18bc6123ae022f',
        'c5e9145114e6d7714d89010d4d78f61dac879a25dd3d6f37fdec047a30a31499',
    ),
    'mlf.lock': (
        '85971352d3b7a012b388322969ff9d858e532e828482d5f04f63164d18ebf3ea',
        'e714b87ec9a2aa4f92eec720e5436c9810015764bda13835c44426007041fcf9',
    ),
}
# The repaired Solver is in the builtin generator's source closure. GHC O0
# and O2 independently generated the same literal with only its identity changed.
C4_BUILTIN_REGENERATION_CHANGES = {
    'bootstrap/MLF/BuiltinPreludeData.hs': (
        '0a2c09d3698b26c8ac48e9388b0fecefd1e4469fe088192662a7849010cd51de',
        'b6dfd0eba758cba48b893d0d25d83e8254d0f25d95274559cb4c4e05467ccb5f',
    ),
    'mlf.lock': (
        'e714b87ec9a2aa4f92eec720e5436c9810015764bda13835c44426007041fcf9',
        '58be558b0894ec523f3dde29a02c83025ade1858a514417e18f017fc4e63f263',
    ),
}
COMPACT_SCOPE_MAINTENANCE = {
    'patricia/run_integrated.py': (
        '4fd2ad1497834d43189800dc720457fbe62c02511911d8c89317534336115744',
        '73885e37b41a19fbfb1307386ba073e44ea43dd313a8ec49216656164ae36db1',
    ),
}
SESSION_SCOPE_INPUT_MAINTENANCE = {
    'patricia/run_integrated.py': (
        '73885e37b41a19fbfb1307386ba073e44ea43dd313a8ec49216656164ae36db1',
        '2318263bec07392b32a3652d8bb0dafc0f5f9edd39828c7e20b0ce082ac89354',
    ),
}
ADMISSION_SCOPE_PREFIX_MAINTENANCE = {
    'patricia/run_integrated.py': (
        '2318263bec07392b32a3652d8bb0dafc0f5f9edd39828c7e20b0ce082ac89354',
        '5c4edb54e2ae1429e37795ca3bc9adf5e89cc69b8a32d852aed136e31688c920',
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
                   framework, framework_tree, parents, merged_endpoints=None):
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
                ((path == 'mlf.lock' or row['merged'] == row['branch']) if merged_endpoints is None
                 else row['merged'] == merged_endpoints.get(path, row['branch'])),
                'Phase 2 source endpoint: ' + path)
    return {path: row['merged'] for path, row in changes.items()}



def dictionary_spine_changes(repository, files):
    return dictionary_spine_transition(repository, files, DICTIONARY_SPINE, DICTIONARY_SPINE_TREE,
                                       DICTIONARY_SPINE_PARENT, DICTIONARY_SPINE_PARENT_TREE,
                                       DICTIONARY_SPINE_CHANGES)


def closed_dictionary_spine_changes(repository, files):
    return dictionary_spine_transition(repository, files,
                                       CLOSED_DICTIONARY_SPINE, CLOSED_DICTIONARY_SPINE_TREE,
                                       CLOSED_DICTIONARY_SPINE_PARENT, CLOSED_DICTIONARY_SPINE_PARENT_TREE,
                                       CLOSED_DICTIONARY_SPINE_CHANGES)


def dictionary_spine_transition(repository, files, branch_commit, branch_tree,
                                parent_commit, parent_tree, changes):
    git = ['git', '--no-replace-objects', '-C', repository]
    def revision(expression):
        return subprocess.check_output([*git, 'rev-parse', '--verify', expression], text=True).strip()
    require(revision(branch_commit + '^{tree}') == branch_tree and
            revision(branch_commit + '^') == parent_commit and
            revision(parent_commit + '^{tree}') == parent_tree,
            'pinned dictionary-spine trees and ancestry')
    paths = subprocess.check_output([*git, 'diff-tree', '--no-commit-id', '--name-only',
                                     '--no-renames', '-r', parent_commit,
                                     branch_commit], text=True).splitlines()
    require(changes.keys() == files.keys() & set(paths),
            'complete dictionary-spine source transition')
    for path, (parent, branch, prior, _) in changes.items():
        def at(commit):
            return sha(subprocess.check_output([*git, 'show', commit + ':' + path]))
        require(at(parent_commit) == parent and at(branch_commit) == branch and
                files[path] == prior, 'dictionary-spine endpoint: ' + path)
    return {path: row[3] for path, row in changes.items()}


def successor_type(predecessor_type, predecessor_manifest, framework_pin, foundation_pin,
                   phase2_pin, heap_force_pin, dictionary_demand_pin, thunk_captures_pin,
                   checked_dispatch_pin, recursive_workers_pin, cold_crates_pin, checked_graph_pin,
                   read_implementation):
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
            require(sha(checked_dispatch_raw) == checked_dispatch_pin,
                    'pinned checked-dispatch manifest SHA')
            recursive_workers_raw = read_implementation(self.directory / RECURSIVE_WORKERS_MANIFEST)
            require(sha(recursive_workers_raw) == recursive_workers_pin,
                    'pinned recursive-workers manifest SHA')
            cold_crates_raw = read_implementation(self.directory / COLD_CRATES_MANIFEST)
            require(sha(cold_crates_raw) == cold_crates_pin,
                    'pinned cold-crates manifest SHA')
            checked_graph_raw = read_implementation(self.directory / CHECKED_GRAPH_MANIFEST)
            require(sha(checked_graph_raw) == checked_graph_pin == manifest_sha256,
                    'pinned checked-graph manifest SHA')
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
            # Only the exact public export header in the live private-owner adapter
            # changed for cold crate plans. The archived baseline still supplies
            # the previous adapter and the original recursive C4 oracle sources.
            owner_adapter = 'patricia/adapt_oracles.py'
            require(owner_adapter not in self.maintenance, 'duplicate private-owner adapter transition')
            self.maintenance[owner_adapter] = [
                '92871acb93f9c742910b6dfb224bda86e292d2214718be50fdb172b434f65820',
                'e5ad567b3baecc736190708899cd2579b142a2ec2cd576efcbf5e0f985b52781',
            ]
            for edge in (COMPACT_SCOPE_MAINTENANCE, SESSION_SCOPE_INPUT_MAINTENANCE,
                         ADMISSION_SCOPE_PREFIX_MAINTENANCE):
                for name, (previous, current) in edge.items():
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
            for label, edge in (('C4 survivor demand', C4_SURVIVOR_DEMAND_CHANGES),
                                ('C4 builtin regeneration', C4_BUILTIN_REGENERATION_CHANGES)):
                for path, (previous, current) in edge.items():
                    require(files[path] == previous, label + ' source transition: ' + path)
                    self.changes[path] = [old_files[path], current]
                    files[path] = current
            # The PR-side root lock already includes the C4 solver/builtin transition.
            edge = phase2_changes(self.core.strict_json(recursive_workers_raw), repository, files,
                                  checked_dispatch_pin, 'checked_dispatch_manifest_sha256',
                                  RECURSIVE_WORKERS, RECURSIVE_WORKERS_TREE,
                                  RECURSIVE_WORKERS_FRAMEWORK_PARENT, RECURSIVE_WORKERS_FRAMEWORK_PARENT_TREE,
                                  (RECURSIVE_WORKERS_BRANCH_PARENT,))
            self.changes.update({path: [old_files[path], new] for path, new in edge.items()})
            files.update(edge)
            edge = phase2_changes(self.core.strict_json(cold_crates_raw), repository, files,
                                  recursive_workers_pin, 'recursive_workers_manifest_sha256',
                                  COLD_CRATES, COLD_CRATES_TREE,
                                  COLD_CRATES_FRAMEWORK_PARENT, COLD_CRATES_FRAMEWORK_PARENT_TREE,
                                  (COLD_CRATES_BRANCH_PARENT,), merged_endpoints=COLD_CRATES_MERGED)
            self.changes.update({path: [old_files[path], new] for path, new in edge.items()})
            files.update(edge)
            for path, (previous, current) in LOCAL_WORKER_POLICY.items():
                require(files[path] == previous, 'local worker policy source transition: ' + path)
                self.changes[path] = [old_files[path], current]
                files[path] = current
            edge = phase2_changes(self.core.strict_json(checked_graph_raw), repository, files,
                                  cold_crates_pin, 'cold_crates_manifest_sha256',
                                  CHECKED_GRAPH, CHECKED_GRAPH_TREE,
                                  CHECKED_GRAPH_FRAMEWORK_PARENT, CHECKED_GRAPH_FRAMEWORK_PARENT_TREE,
                                  CHECKED_GRAPH_PARENTS, merged_endpoints=CHECKED_GRAPH_MERGED)
            self.changes.update({path: [old_files[path], new] for path, new in edge.items()})
            files.update(edge)
            edge = dictionary_spine_changes(repository, files)
            self.changes.update({path: [old_files[path], new] for path, new in edge.items()})
            files.update(edge)
            edge = closed_dictionary_spine_changes(repository, files)
            self.changes.update({path: [old_files[path], new] for path, new in edge.items()})
            files.update(edge)
            for path, (previous, current) in INFERENCE_ADMISSION_CHANGES.items():
                require(files[path] == previous, 'inference admission source transition: ' + path)
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
            self.metadata_paths = (*self.previous.metadata_paths, MANIFEST, FOUNDATION_MANIFEST,
                                   PHASE2_MANIFEST, HEAP_FORCE_MANIFEST, DICTIONARY_DEMAND_MANIFEST,
                                   THUNK_CAPTURES_MANIFEST, CHECKED_DISPATCH_MANIFEST,
                                   RECURSIVE_WORKERS_MANIFEST, COLD_CRATES_MANIFEST,
                                   CHECKED_GRAPH_MANIFEST, Path(__file__).name)
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
