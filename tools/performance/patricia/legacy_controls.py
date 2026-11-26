"""Directly compilable retained P1/P2/P3 controls for the current ABI."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    'patricia_runtime_sources', Path(__file__).with_name('runtime_sources.py'))
_sources = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sources)

SOURCES = {'p123': {'BinaryP2WriterControls.hs': 'tools/performance/artifact-binary/BinaryP2WriterControls.hs',
          'FrozenFingerprint.hs': 'tools/performance/patricia/oracles/p123/FrozenFingerprint.hs',
          'FrozenInferenceUnit.hs': 'tools/performance/crate-optimizations/p3/FrozenInferenceUnit.hs',
          'FrozenPrefix.hs': 'tools/performance/crate-optimizations/p3/FrozenPrefix.hs',
          'FrozenSelectorMap.hs': 'tools/performance/crate-optimizations/p1/FrozenSelectorMap.hs',
          'FrozenSelectorSet.hs': 'tools/performance/crate-optimizations/p1/FrozenSelectorSet.hs',
          'FrozenSelectors.hs': 'tools/performance/patricia/oracles/p123/FrozenSelectors.hs',
          'LegacyArtifactWriter.hs': 'tools/performance/patricia/oracles/LegacyArtifactWriter.hs',
          'NativeCompatibilityControls.hs': 'tools/performance/crate-optimizations/p2/NativeCompatibilityControls.hs',
          'P1Controls.hs': 'tools/performance/patricia/controls/p123/P1Controls.hs',
          'P2Controls.hs': 'tools/performance/patricia/controls/p123/P2Controls.hs',
          'P3Controls.hs': 'tools/performance/patricia/controls/p123/P3Controls.hs',
          'QueryV6Bridge.hs': 'tools/performance/patricia/controls/p123/QueryV6Bridge.hs',
          'RetainedP2Controls.hs': 'tools/performance/patricia/controls/p123/RetainedP2Controls.hs'}}
MODULES = {
    'p123': ['P1Controls', 'P2Controls', 'NativeCompatibilityControls', 'P3Controls'],
}


def prepare(root, out, suite):
    if suite not in SOURCES:
        raise ValueError('unknown retained control family: ' + suite)
    out = Path(out)
    out.mkdir(exist_ok=False, parents=True)
    return MODULES[suite], _sources.copy_sources(root, out, SOURCES[suite])
