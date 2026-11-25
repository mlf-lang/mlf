"""Authenticate the Foundation merge on top of the unchanged PR55 source proof."""
from contextlib import ExitStack, contextmanager
from functools import lru_cache
import hashlib
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory
from types import ModuleType

HERE = Path(__file__).resolve().parent
DRAFT = '8afe7d1978ca67b29c438329b1014176b045dd64'
FOUNDATION = '9345d58b2b1675fbe0fcf899b5dc3d2f229e1acf'
MERGE = 'd72950ed771d4fd48145cd4f467ff9ce43ef13d4'
WRITER_PREDECESSOR = 'ccaded50dbf189b89d164cea0add9742965ff6be'
WRITER_SIGNATURES = '0eea12495edd0b1572d5c330379005fb59a1052e'
PARITY_INPUT_PARENT = '86cd25e18258bd2adafd8d3786e16d02448167f6'
PARITY_INPUTS = '93872016affaa8b731fd35c263899b8ebb50dc40'
RECURSIVE_PARITY_PARENT = 'f49b13e154ea6a166fdce5aa86d94a29e77509b3'
RECURSIVE_PARITY_INPUT = 'd16fe59419ab7baa0398e9698960a1948d3ebc1a'
LLVM_NONRETURN_PARENT = '92ced54fa5166afa99528479e62c25c64b838e4f'
LLVM_NONRETURN = 'fc073d50687efb196ecdf27662a79471afbe8f6d'
F1_HYGIENE_PARENT = 'e836cbc4b9e5f0405e73988fba8d6bbafd008e44'
F1_HYGIENE = 'd103b9271cd5520113e17bb2a27309df077e3fc4'
OPTIMIZER_RAW_PARENT = '1ebe7605aafb98d085993481114aee5a5f180f05'
OPTIMIZER_RAW = 'f70057609fd59adb4e8aafb0ad556b3de2566338'
QUERY_WIRE_PARENT = '5fa22510b94e6a9772da0b5c34cfeb7f552a0f3a'
QUERY_WIRE = '1a3d593884b5dbb5fe2aa6d9878bb9262bbd9ea7'
LIFECYCLE_STRING_PARENT = '8ac74b0ab7cf11db1f9a11cf9c483a4304b90695'
LIFECYCLE_STRING = 'ec13adb93e5e71770f20b19db448c5181de62030'
ARTIFACT_STACK_PARENT = 'f000c8bcd9108b90814be518995c4edeb25e2c3c'
ARTIFACT_STACK = 'f21cba5d133da862a4eca6e6174290cc6b5882e0'
OPEN_PACKAGE_LIMIT_PARENT = 'd92bb349935f25c58d89626b18053ff094880814'
OPEN_PACKAGE_LIMIT = 'b02e208b617fd34d36e08047875c3b642a906332'
BACKEND_PATHS_PARENT = '148cbb3f8cb47863987fb146745b389ddd0e6e17'
BACKEND_PATHS = 'a57e46fd89740410607685473bed6dcc70649dd8'
CORE_LEAF_SELECTION_PARENT = '222afddb378bdf55a9bf3ad343d9a77fc5d1d52d'
CORE_LEAF_SELECTION = 'ef3d0106036758b9fd7847ecce7750955097d817'
CORE_LEAF_PROOF = '6167fe44a0e6a47fe9bf72a96d5de114d3c6ae31'
REVIEW_FIXES = 'c50d8b256b52670e6c0cb4213b367f15f01a9e2d'
REVIEW_MERGE = 'd8b0c0313f6d3b3c9b93e1ec6367599d3d22db14'
ORIGINAL = 'tools/performance/artifact-binary/phase2_source_successor.py'
ORIGINAL_SHA = '72041ef0f3ea9c84d5f7ff100f721c326ecbbc86c1b705bf2c45f11cb19f9f16'
EXTRA_MERGE_ROLES = {
    'testing/tools/mlf.lock', 'tests/indexvec/Graphs.hs', 'tests/mlf.lock',
    'tests/shared/mlf.lock', 'tools/performance/compiler-shapes/generate.py',
    'tools/performance/compiler-shapes/matrix.json',
}
WRITER_SIGNATURE_ROLES = {
    'bootstrap/MLF/BuiltinPreludeData.hs',
    'libraries/mlf-crates/Bootstrap/Bitstream.hs',
    'mlf.lock',
    'testing/tools/mlf.lock',
    'tests/mlf.lock',
    'tests/shared/mlf.lock',
    'tools/shared/test_packed_writer.py',
}
PARITY_INPUT_ROLES = {
    'tests/Tests/Corpus.emlf', 'tests/mlf.lock', 'tools/shared/prepare_parity.py',
}
LLVM_NONRETURN_ROLES = {
    'libraries/mlf-llvm/Bootstrap/LLVM/Build.hs', 'mlf.lock', 'testing/tools/mlf.lock',
    'tests/mlf.lock', 'tests/shared/mlf.lock', 'tools/shared/test_ordinary_tail.py',
}
F1_HYGIENE_ROLES = {
    'bootstrap/MLF/BuiltinPreludeData.hs',
    'libraries/mlf-crates/Bootstrap/Separate.hs', 'mlf.lock', 'testing/tools/mlf.lock',
    'tests/mlf.lock', 'tests/shared/mlf.lock',
}
OPTIMIZER_RAW_ROLES = {
    'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs', 'mlf.lock',
    'testing/tools/mlf.lock', 'tests/mlf.lock', 'tests/shared/mlf.lock',
}
QUERY_WIRE_ROLES = {
    'libraries/mlf-crates/Bootstrap/QueryGraph.hs', 'bootstrap/MLF/BuiltinPreludeData.hs', 'mlf.lock',
    'testing/tools/mlf.lock', 'tests/mlf.lock', 'tests/shared/mlf.lock',
}
LIFECYCLE_STRING_ROLES = {
    'testing/tools/LifecycleMain.emlf', 'testing/tools/mlf.lock', 'tests/mlf.lock',
}
ARTIFACT_STACK_ROLES = {
    'libraries/mlf-crates/Bootstrap/Bitstream.hs', 'libraries/mlf-crates/Bootstrap/QueryGraph.hs',
    'bootstrap/MLF/BuiltinPreludeData.hs', 'mlf.lock',
    'testing/tools/mlf.lock', 'tests/mlf.lock', 'tests/shared/mlf.lock',
}
OPEN_PACKAGE_LIMIT_ROLES = {
    'libraries/mlf-crates/Bootstrap/OpenFragment.hs',
    'bootstrap/MLF/BuiltinPreludeData.hs', 'mlf.lock',
    'testing/tools/mlf.lock', 'tests/mlf.lock', 'tests/shared/mlf.lock',
}
BACKEND_PATHS_ROLES = {'tests/Tests/Separate.emlf', 'tests/Tests/Readability.emlf', 'tests/mlf.lock'}
CORE_LEAF_SELECTION_ROLES = {'tests/Tests/CoreRunner.emlf', 'tests/mlf.lock'}

REVIEW_FIX_ROLES = {
    'bootstrap/MLF/BuiltinPreludeData.hs', 'libraries/mlf-inference/Bootstrap/ClassDemand.hs',
    'libraries/mlf-inference/Bootstrap/EvidenceBoundary.hs', 'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs',
    'mlf.lock', 'testing/tools/mlf.lock', 'tests/Tests/BackendSuite.emlf', 'tests/indexvec/Graphs.hs',
    'tests/mlf.lock', 'tests/shared/mlf.lock', 'tools/developer/process.py', 'tools/developer/test_process.py',
    'tools/performance/compiler-shapes/generate.py', 'tools/performance/compiler-shapes/matrix.json',
    'tools/testing/receipt_adapter.py', 'tools/testing/run.py',
}


def repository(root, *args):
    return subprocess.check_output(
        ['git', '--no-replace-objects', '-C', str(root), *args], stderr=subprocess.PIPE,
    ).decode().strip()


def original_proof(root):
    path = root / ORIGINAL
    raw = path.read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != ORIGINAL_SHA:
        raise ValueError('unexpected reviewed PR55 source verifier')
    module = ModuleType('_mlf_original_phase2_draft')
    module.__file__ = str(path)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module


@lru_cache(maxsize=1)
def reviewed_draft(root):
    proof = original_proof(root)
    git = proof.Git(repository(root, 'rev-parse', '--path-format=absolute', '--git-dir'))
    git.commit(DRAFT)
    objects = Path(repository(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')) / 'objects'
    with ExitStack() as stack:
        draft = Path(stack.enter_context(TemporaryDirectory(prefix='mlf-pr55-draft-source-')))
        with subprocess.Popen([*git.command, 'archive', DRAFT], stdout=subprocess.PIPE) as child:
            with tarfile.open(fileobj=child.stdout, mode='r|') as stream:
                stream.extractall(draft, filter='data')
            proof.require(child.wait() == 0, 'archived reviewed PR55 draft')
        repository(draft, 'init', '-q')
        (draft / '.git/objects/info/alternates').write_text(str(objects) + '\n')
        repository(draft, 'update-ref', '--no-deref', 'HEAD', DRAFT)
        opened = stack.enter_context(original_proof(draft).qualified(draft))
        return stack.pop_all(), proof, opened

def qualified_contract(root, source_root=None):
    root = Path(root).resolve(strict=True)
    source_root = Path(source_root).resolve(strict=True) if source_root is not None else root
    _, proof, reviewed = reviewed_draft(root)
    live_git = proof.Git(repository(root, 'rev-parse', '--path-format=absolute', '--git-dir'))
    live_git.commit(MERGE, parents=[DRAFT, FOUNDATION])
    live_git.run('merge-base', '--is-ancestor', MERGE, 'HEAD')
    before = reviewed.contract.edge.before
    paths = set(before)
    known_changes = set(live_git.run('diff', '--name-only', DRAFT, MERGE).decode().splitlines())
    proof.require(known_changes <= paths | EXTRA_MERGE_ROLES, 'exact Foundation integration source roles')
    live_git.run('merge-base', '--is-ancestor', MERGE, WRITER_PREDECESSOR)
    live_git.commit(WRITER_SIGNATURES, parents=[WRITER_PREDECESSOR])
    live_git.run('merge-base', '--is-ancestor', WRITER_SIGNATURES, 'HEAD')
    writer_changes = set(live_git.run(
        'diff', '--name-only', WRITER_PREDECESSOR, WRITER_SIGNATURES).decode().splitlines())
    proof.require(writer_changes == WRITER_SIGNATURE_ROLES, 'exact packed writer signature source roles')
    live_git.run('merge-base', '--is-ancestor', WRITER_SIGNATURES, PARITY_INPUT_PARENT)
    live_git.commit(PARITY_INPUTS, parents=[PARITY_INPUT_PARENT])
    live_git.run('merge-base', '--is-ancestor', PARITY_INPUTS, 'HEAD')
    parity_changes = set(live_git.run(
        'diff', '--name-only', PARITY_INPUT_PARENT, PARITY_INPUTS).decode().splitlines())
    proof.require(parity_changes == PARITY_INPUT_ROLES, 'exact frozen parity input projection roles')
    live_git.run('merge-base', '--is-ancestor', PARITY_INPUTS, RECURSIVE_PARITY_PARENT)
    live_git.commit(RECURSIVE_PARITY_INPUT, parents=[RECURSIVE_PARITY_PARENT])
    live_git.run('merge-base', '--is-ancestor', RECURSIVE_PARITY_INPUT, 'HEAD')
    recursive_parity_changes = set(live_git.run(
        'diff', '--name-only', RECURSIVE_PARITY_PARENT, RECURSIVE_PARITY_INPUT).decode().splitlines())
    proof.require(recursive_parity_changes == PARITY_INPUT_ROLES, 'exact recursive parity input projection roles')
    live_git.run('merge-base', '--is-ancestor', RECURSIVE_PARITY_INPUT, LLVM_NONRETURN_PARENT)
    live_git.commit(LLVM_NONRETURN, parents=[LLVM_NONRETURN_PARENT])
    live_git.run('merge-base', '--is-ancestor', LLVM_NONRETURN, 'HEAD')
    llvm_changes = set(live_git.run(
        'diff', '--name-only', LLVM_NONRETURN_PARENT, LLVM_NONRETURN).decode().splitlines())
    proof.require(llvm_changes == LLVM_NONRETURN_ROLES, 'exact LLVM nonreturning worker source roles')
    live_git.run('merge-base', '--is-ancestor', LLVM_NONRETURN, F1_HYGIENE_PARENT)
    live_git.commit(F1_HYGIENE, parents=[F1_HYGIENE_PARENT])
    live_git.run('merge-base', '--is-ancestor', F1_HYGIENE, 'HEAD')
    f1_changes = set(live_git.run(
        'diff', '--name-only', F1_HYGIENE_PARENT, F1_HYGIENE).decode().splitlines())
    proof.require(f1_changes == F1_HYGIENE_ROLES, 'exact F1 hygiene source roles')
    live_git.run('merge-base', '--is-ancestor', F1_HYGIENE, OPTIMIZER_RAW_PARENT)
    live_git.commit(OPTIMIZER_RAW, parents=[OPTIMIZER_RAW_PARENT])
    live_git.run('merge-base', '--is-ancestor', OPTIMIZER_RAW, 'HEAD')
    optimizer_changes = set(live_git.run(
        'diff', '--name-only', OPTIMIZER_RAW_PARENT, OPTIMIZER_RAW).decode().splitlines())
    proof.require(optimizer_changes == OPTIMIZER_RAW_ROLES, 'exact raw LLVM optimizer source roles')
    live_git.run('merge-base', '--is-ancestor', OPTIMIZER_RAW, QUERY_WIRE_PARENT)
    live_git.commit(QUERY_WIRE, parents=[QUERY_WIRE_PARENT])
    live_git.run('merge-base', '--is-ancestor', QUERY_WIRE, 'HEAD')
    query_changes = set(live_git.run(
        'diff', '--name-only', QUERY_WIRE_PARENT, QUERY_WIRE).decode().splitlines())
    proof.require(query_changes == QUERY_WIRE_ROLES, 'exact legacy query wire source roles')
    live_git.run('merge-base', '--is-ancestor', QUERY_WIRE, LIFECYCLE_STRING_PARENT)
    live_git.commit(LIFECYCLE_STRING, parents=[LIFECYCLE_STRING_PARENT])
    live_git.run('merge-base', '--is-ancestor', LIFECYCLE_STRING, 'HEAD')
    lifecycle_changes = set(live_git.run(
        'diff', '--name-only', LIFECYCLE_STRING_PARENT, LIFECYCLE_STRING).decode().splitlines())
    proof.require(lifecycle_changes == LIFECYCLE_STRING_ROLES, 'exact lifecycle lease source roles')
    live_git.run('merge-base', '--is-ancestor', LIFECYCLE_STRING, ARTIFACT_STACK_PARENT)
    live_git.commit(ARTIFACT_STACK, parents=[ARTIFACT_STACK_PARENT])
    live_git.run('merge-base', '--is-ancestor', ARTIFACT_STACK, 'HEAD')
    stack_changes = set(live_git.run(
        'diff', '--name-only', ARTIFACT_STACK_PARENT, ARTIFACT_STACK).decode().splitlines())
    proof.require(stack_changes == ARTIFACT_STACK_ROLES, 'exact artifact stack source roles')
    live_git.run('merge-base', '--is-ancestor', ARTIFACT_STACK, OPEN_PACKAGE_LIMIT_PARENT)
    live_git.commit(OPEN_PACKAGE_LIMIT, parents=[OPEN_PACKAGE_LIMIT_PARENT])
    live_git.run('merge-base', '--is-ancestor', OPEN_PACKAGE_LIMIT, 'HEAD')
    stack_changes = set(live_git.run(
        'diff', '--name-only', OPEN_PACKAGE_LIMIT_PARENT, OPEN_PACKAGE_LIMIT).decode().splitlines())
    proof.require(stack_changes == OPEN_PACKAGE_LIMIT_ROLES, 'exact open package budget source roles')
    live_git.run('merge-base', '--is-ancestor', OPEN_PACKAGE_LIMIT, BACKEND_PATHS_PARENT)
    live_git.commit(BACKEND_PATHS, parents=[BACKEND_PATHS_PARENT])
    live_git.run('merge-base', '--is-ancestor', BACKEND_PATHS, 'HEAD')
    backend_changes = set(live_git.run(
        'diff', '--name-only', BACKEND_PATHS_PARENT, BACKEND_PATHS).decode().splitlines())
    proof.require(backend_changes == BACKEND_PATHS_ROLES, 'exact backend path test source roles')
    live_git.run('merge-base', '--is-ancestor', BACKEND_PATHS, CORE_LEAF_SELECTION_PARENT)
    live_git.commit(CORE_LEAF_SELECTION, parents=[CORE_LEAF_SELECTION_PARENT])
    live_git.run('merge-base', '--is-ancestor', CORE_LEAF_SELECTION, 'HEAD')
    selection_changes = set(live_git.run(
        'diff', '--name-only', CORE_LEAF_SELECTION_PARENT, CORE_LEAF_SELECTION).decode().splitlines())
    proof.require(selection_changes == CORE_LEAF_SELECTION_ROLES, 'exact Core leaf selection source roles')
    live_git.commit(CORE_LEAF_PROOF, parents=[CORE_LEAF_SELECTION])
    live_git.commit(REVIEW_FIXES, parents=[CORE_LEAF_SELECTION_PARENT])
    live_git.commit(REVIEW_MERGE, parents=[REVIEW_FIXES, CORE_LEAF_PROOF])
    live_git.run('merge-base', '--is-ancestor', REVIEW_MERGE, 'HEAD')
    for parent, result in [(CORE_LEAF_SELECTION_PARENT, REVIEW_FIXES), (CORE_LEAF_PROOF, REVIEW_MERGE)]:
        changes = live_git.run('diff', '--name-only', parent, result).decode().splitlines()
        proof.require(set(changes) == REVIEW_FIX_ROLES, 'exact compiler and dispatcher review changes')
    auxiliary_roles = (
        EXTRA_MERGE_ROLES | WRITER_SIGNATURE_ROLES | PARITY_INPUT_ROLES | LLVM_NONRETURN_ROLES | F1_HYGIENE_ROLES
        | OPTIMIZER_RAW_ROLES | QUERY_WIRE_ROLES | LIFECYCLE_STRING_ROLES | ARTIFACT_STACK_ROLES | OPEN_PACKAGE_LIMIT_ROLES | BACKEND_PATHS_ROLES
        | CORE_LEAF_SELECTION_ROLES | REVIEW_FIX_ROLES
    ) - paths
    expected = live_git.inventory(REVIEW_MERGE, paths | auxiliary_roles)
    if source_root == root:
        auxiliary = {p: proof.read(source_root, p) for p in auxiliary_roles}
        proof.require(all(proof.oid(raw) == expected[p] for p, raw in auxiliary.items()),
                      'exact Foundation, packed writer and frozen parity test, lock and shape inputs')
    current = {p: proof.read(source_root, p) for p in paths}
    proof.require(all(proof.oid(raw) == expected[p] for p, raw in current.items()),
                  'exact merged and signed source inventory')
    after = {p: proof.sha(raw) for p, raw in current.items()}
    changed = {p for p in paths if before[p] != after[p]}
    archive = reviewed.contract.archived
    old = {p: proof.read(archive, p) for p in changed}
    new = {p: current[p] for p in changed}
    edge = proof.Projection(before, after, old, new)
    proof.require(not os.path.lexists(source_root / proof.RETIRED), 'retired source present')
    predecessor = reviewed.contract.previous
    contract = proof.composed_type(type(predecessor))(predecessor, edge, source_root, archive)
    contract.directory = HERE
    contract.manifest_sha256 = proof.sha(proof.read(root, Path(__file__).relative_to(root).as_posix()))
    contract.metadata_paths = (*contract.metadata_paths, Path(__file__).name)
    contract.live_registry(source_root)
    return proof.Qualified(contract, live_git, reviewed.tip)


@contextmanager
def qualified(root):
    opened = qualified_contract(root)
    contract = opened.contract
    current = {p: contract.core.read_file(contract.source_root, p) for p in contract.value['current_files']}
    historic = contract.project_tree_bytes(current)
    additions = {p: current[p] for p in contract.added_paths}
    if contract.advance_tree_bytes(historic, additions) != current:
        raise ValueError('complete Foundation source round trip through the original contract')
    yield opened
