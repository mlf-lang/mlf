"""Prepare directly compilable graph controls and current private-module views."""
import hashlib
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'patricia_runtime_sources', Path(__file__).with_name('runtime_sources.py'))
_sources = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sources)
private_module_view = _sources.private_module_view

OWNER = 'libraries/mlf-crates/Bootstrap/CrateSession.hs'
GRAPH_SOURCES = {'AdmissionTests.hs': 'tools/performance/patricia/controls/graph/AdmissionTests.hs',
 'C4Fixtures.hs': 'tools/performance/patricia/controls/graph/C4Fixtures.hs',
 'C4ProjectionOracle.hs': 'tools/performance/patricia/controls/graph/C4ProjectionOracle.hs',
 'C4TransactionControls.hs': 'tools/performance/patricia/controls/graph/C4TransactionControls.hs',
 'C4TransactionOracle.hs': 'tools/performance/patricia/controls/graph/C4TransactionOracle.hs',
 'FrozenConstraint.hs': 'tools/performance/patricia/oracles/graph/FrozenConstraint.hs',
 'FrozenGraph.hs': 'tools/performance/patricia/oracles/graph/FrozenGraph.hs',
 'FrozenIntMap.hs': 'tools/performance/patricia/oracles/graph/FrozenIntMap.hs',
 'FrozenIntSet.hs': 'tools/performance/patricia/oracles/graph/FrozenIntSet.hs',
 'FrozenMap.hs': 'tools/performance/patricia/oracles/graph/FrozenMap.hs',
 'FrozenSolver.hs': 'tools/performance/patricia/oracles/graph/FrozenSolver.hs',
 'HeteroinputControls.hs': 'tools/performance/patricia/controls/graph/HeteroinputControls.hs',
 'OracleTypes.hs': 'tools/performance/patricia/OracleTypes.hs',
 'PatriciaOracleControls.hs': 'tools/performance/patricia/PatriciaOracleControls.hs',
 'PublicControls.hs': 'tools/performance/patricia/controls/graph/PublicControls.hs',
 'SessionFieldFixtures.hs': 'tools/performance/patricia/controls/graph/SessionFieldFixtures.hs',
 'SessionGraftFixtures.hs': 'tools/performance/patricia/controls/graph/SessionGraftFixtures.hs',
 'SessionOracle.hs': 'tools/performance/patricia/controls/graph/SessionOracle.hs',
 'SessionTests.hs': 'tools/performance/patricia/controls/graph/SessionTests.hs',
 'TransactionOracle.hs': 'tools/performance/patricia/controls/graph/TransactionOracle.hs'}
VALIDATION_SOURCES = {'BoundaryControls.hs': 'tools/performance/patricia/controls/validation/BoundaryControls.hs',
 'V1FrozenSession.hs': 'tools/performance/patricia/oracles/V1FrozenSession.hs'}


def current_session(root, out, name):
    owner = Path(root) / OWNER
    current = owner.read_bytes()
    (Path(out) / (name + '.hs')).write_bytes(private_module_view(current, name))
    return {str(owner): hashlib.sha256(current).hexdigest()}


def prepare(root, out, *, source_root=None):
    """Use ordinary maintained tests plus separately fixed reference algorithms."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    inputs = _sources.copy_sources(root, out, GRAPH_SOURCES)
    inputs.update(current_session(source_root or root, out, 'SessionUnderTest'))
    return inputs


def prepare_validation(root, out, *, source_root=None):
    """Pair the independent pre-optimization oracle with this checkout's session."""
    inputs = _sources.copy_sources(root, out, VALIDATION_SOURCES)
    inputs.update(current_session(source_root or root, out, 'V1SessionUnderTest'))
    return inputs
