"""Load the unchanged C4 independent reader triple from its pinned Git tree."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile

PREDECESSOR = '8c4556416023ac727e3fb2294070358a3dae8d9e'
PREDECESSOR_TREE = 'c20bd3d8e0cdd7e319dfca77ea0b86cfbf77554d'
ROOT = Path(__file__).resolve().parents[3]
_directories = []


def verify(raw, digest, label):
    if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('fixed C4 oracle identity: ' + label)
    return raw


def load_oracles(pins):
    git = ['git', '--no-replace-objects', '-C', str(ROOT)]
    tree = subprocess.check_output([*git, 'rev-parse', PREDECESSOR + '^{tree}'],
                                   text=True).strip()
    if tree != PREDECESSOR_TREE:
        raise ValueError('fixed C4 oracle predecessor tree')
    directory = tempfile.TemporaryDirectory(prefix='mlf-c4-independent-oracles-')
    _directories.append(directory)
    path = Path(directory.name)
    for name, digest in pins.items():
        if Path(name).name != name:
            raise ValueError('fixed C4 oracle filename')
        raw = subprocess.check_output([*git, 'show', PREDECESSOR + ':tools/shared/' + name])
        (path / name).write_bytes(verify(raw, digest, name))
    modules = []
    saved = {name: sys.modules.get(name) for name in
             ('artifact_binary_reference', 'artifact_binary_typed')}
    try:
        for name in saved:
            spec = importlib.util.spec_from_file_location(name, path / (name + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            modules.append(module)
    finally:
        # The typed reader's absolute import sees only the authenticated sibling;
        # leave any independent live-reader caller's namespace unchanged.
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return path, *modules


def dependency_oracle(directory, reference, original_sha):
    """Only dependency-interface primitive declarations extend the frozen domain.

    The schema fields and all validation logic remain the authenticated reader's.
    Own fragments and linked terms continue using its unmodified 0..131 domain.
    """
    path = directory / 'artifact_binary_typed.py'
    raw = verify(path.read_bytes(), original_sha, path.name)
    old = b"if typ=='PrimitiveCode': require(0 <= node.data <= 131, 'closed primitive ABI')"
    new = old.replace(b'<= 131', b'<= 133')
    if raw.count(old) != 1:
        raise ValueError('one frozen dependency primitive-bound anchor')
    adapted = raw.replace(old, new)
    if adapted.replace(new, old) != raw:
        raise ValueError('exact dependency primitive-bound inverse')
    destination = directory / 'artifact_binary_typed_declid_dependencies.py'
    destination.write_bytes(adapted)
    name = '_c4_declid_dependency_oracle'
    spec = importlib.util.spec_from_file_location(name, destination)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get('artifact_binary_reference')
    try:
        sys.modules['artifact_binary_reference'] = reference
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop('artifact_binary_reference', None)
        else:
            sys.modules['artifact_binary_reference'] = previous
    return destination, module


def dependency_v12_bytes(original, legacy, original_sha):
    """Authenticate both historical layers before one explicit ABI-v12 edge."""
    original = verify(original, original_sha, 'artifact_binary_typed.py')
    old = b"if typ=='PrimitiveCode': require(0 <= node.data <= 131, 'closed primitive ABI')"
    middle = old.replace(b'<= 131', b'<= 133')
    current = old.replace(b'<= 131', b'<= 136')
    if original.count(old) != 1:
        raise ValueError('one frozen dependency primitive-bound anchor')
    if len(legacy) > 1024 * 1024 or legacy != original.replace(old, middle):
        raise ValueError('complete historical 133 dependency adapter identity')
    if legacy.count(middle) != 1 or legacy.replace(middle, old) != original:
        raise ValueError('complete 133-to-131 dependency inverse')
    adapted = legacy.replace(middle, current)
    if adapted.count(current) != 1 or adapted.replace(current, middle) != legacy:
        raise ValueError('complete 136-to-133 dependency inverse')
    if adapted.replace(current, middle).replace(middle, old) != original:
        raise ValueError('complete two-edge dependency inverse')
    return adapted


def dependency_v12_oracle(directory, reference, original_sha, legacy_path):
    """A separate dependency-only reader; never replace the retained 133 layer."""
    if legacy_path != directory / 'artifact_binary_typed_declid_dependencies.py':
        raise ValueError('historical dependency adapter path')
    original = (directory / 'artifact_binary_typed.py').read_bytes()
    adapted = dependency_v12_bytes(original, legacy_path.read_bytes(), original_sha)
    destination = directory / 'artifact_binary_typed_v12_dependencies.py'
    destination.write_bytes(adapted)
    name = '_c4_v12_dependency_oracle'
    spec = importlib.util.spec_from_file_location(name, destination)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get('artifact_binary_reference')
    try:
        sys.modules['artifact_binary_reference'] = reference
        spec.loader.exec_module(module)
    finally:
        if previous is None:
            sys.modules.pop('artifact_binary_reference', None)
        else:
            sys.modules['artifact_binary_reference'] = previous
    return destination, module
