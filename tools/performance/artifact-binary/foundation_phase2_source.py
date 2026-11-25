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
    auxiliary_roles = (EXTRA_MERGE_ROLES | WRITER_SIGNATURE_ROLES | PARITY_INPUT_ROLES) - paths
    live_git.run('merge-base', '--is-ancestor', PARITY_INPUTS, RECURSIVE_PARITY_PARENT)
    live_git.commit(RECURSIVE_PARITY_INPUT, parents=[RECURSIVE_PARITY_PARENT])
    live_git.run('merge-base', '--is-ancestor', RECURSIVE_PARITY_INPUT, 'HEAD')
    recursive_parity_changes = set(live_git.run(
        'diff', '--name-only', RECURSIVE_PARITY_PARENT, RECURSIVE_PARITY_INPUT).decode().splitlines())
    proof.require(recursive_parity_changes == PARITY_INPUT_ROLES, 'exact recursive parity input projection roles')
    expected = live_git.inventory(RECURSIVE_PARITY_INPUT, paths | auxiliary_roles)
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
