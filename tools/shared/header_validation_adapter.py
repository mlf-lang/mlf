"""Copy independently authored header controls and record this run's inputs.

The historical lane covers four reference naming functions using current shared
foundational modules. The current lane exercises production naming against its
independent oracle. Both are ordinary Haskell fixtures; no Git history or source
transformation is needed to prepare them.
"""
from pathlib import Path
import hashlib
import json
import stat

FIXTURE_DIRECTORY = Path('tools/shared/fixtures/native')
FIXTURE_FILES = {
    'HistoricalHeaderNames.hs': 'header-validation/HistoricalHeaderNames.hs',
    'HeaderNamingOracle.hs': 'HeaderNamingOracle.hs',
    'HeaderValidationHistorical.hs': 'header-validation/HeaderValidationHistorical.hs',
    'HeaderValidationCurrent.hs': 'header-validation/HeaderValidationCurrent.hs',
}
MAX_BYTES = 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def input_paths(root):
    root = Path(root).resolve()
    return {name: root / FIXTURE_DIRECTORY / relative for name, relative in FIXTURE_FILES.items()}


def read_regular(root, path):
    root, path = Path(root).resolve(), Path(path)
    relative = path.relative_to(root)
    current = root
    for part in relative.parts:
        require(part not in ('.', '..'), 'relative fixture path required')
        current = current / part
        require(not current.is_symlink(), 'fixture symlink forbidden: ' + str(path))
    info = current.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES,
            'bounded regular fixture required: ' + str(path))
    raw = current.read_bytes()
    require(len(raw) <= MAX_BYTES, 'fixture changed size: ' + str(path))
    return raw


def verify_prepared(root, destination, evidence, expected_inputs=None):
    """Reject source, snapshot or receipt drift, including stale caller inputs."""
    root, destination = Path(root).resolve(), Path(destination).resolve()
    paths = input_paths(root)
    require(type(evidence) is dict and set(evidence.get('generated', {})) == set(paths),
            'complete prepared header source inventory required')
    actual_inputs = {str(path): sha(read_regular(root, path)) for path in paths.values()}
    require(evidence.get('inputs') == actual_inputs, 'header fixture inputs changed during run')
    if expected_inputs is not None:
        require(all(expected_inputs.get(path) == digest for path, digest in actual_inputs.items()),
                'header preparation differs from bound build inputs')
    require({path.name for path in destination.glob('*.hs')} == set(paths),
            'prepared header source inventory changed')
    for name, path in paths.items():
        raw = read_regular(destination, destination / name)
        require(sha(raw) == evidence['generated'][name] == actual_inputs[str(path)],
                'prepared header source changed: ' + name)
    metadata = read_regular(destination, destination / 'preparation.json')
    require(json.loads(metadata) == evidence, 'header preparation receipt changed')


def prepare(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    paths = input_paths(root)
    files = {name: read_regular(root, path) for name, path in paths.items()}
    destination = output / 'header-validation'
    destination.mkdir(exist_ok=False)
    for name, raw in files.items():
        path = destination / name
        path.write_bytes(raw)
        require(path.read_bytes() == raw, 'written fixture readback: ' + name)
    evidence = {
        'format': 2,
        'inputs': {str(paths[name]): sha(raw) for name, raw in files.items()},
        'generated': {name: sha(raw) for name, raw in files.items()},
        'historical_scope': 'four reference formatter functions; current shared foundational modules',
        'historical_complete_compiler_qualified': False,
        'qualification_executed': False,
    }
    evidence_bytes = (json.dumps(evidence, indent=2) + '\n').encode()
    evidence_path = destination / 'preparation.json'
    evidence_path.write_bytes(evidence_bytes)
    require(evidence_path.read_bytes() == evidence_bytes, 'preparation receipt readback')
    verify_prepared(root, destination, evidence)
    return destination, evidence
