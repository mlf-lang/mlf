"""Audited additive layer over the frozen P2/P3 provenance (never repins it).

The source edit transcript is NOT an expected-output oracle. Reversing its exact
line hunks must reproduce the historical dependency hash before either runner
may use current producer interfaces. No fuzzy patches or git checkout required.
"""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'native-compatibility-manifest.json'
SOURCE_PATHS = {
    'libraries/mlf-foundation/Bootstrap/Map.hs',
    'libraries/mlf-language-core/Bootstrap/Data.hs',
    'libraries/mlf-frontend/Bootstrap/Module.hs',
    'libraries/mlf-xmlf/Bootstrap/X/Pretty.hs',
    'libraries/mlf-xmlf/Bootstrap/X/Checked.hs',
    'libraries/mlf-crates/Bootstrap/Separate.hs',
    'libraries/mlf-crates/Bootstrap/CrateArtifact.hs',
}
INPUT_PATHS = {'tools/performance/crate-optimizations/' + name for name in [
    'p2/native_compatibility.py', 'p2/NativeCompatibilityControls.hs',
    'p2/run_fingerprint_differential.py', 'p2/test_native_compatibility.py',
    'p2/oracle-manifest.json', 'p3/run_controls.py',
    'p3/historical-run-controls.py.txt', 'p3/controls-manifest.json',
    'p3/candidate.json', 'p3/oracle-manifest.json',
]}

def digest(value):
    return hashlib.sha256(value).hexdigest()


def validate_manifest(manifest):
    if manifest['format'] != 'reviewed-native-compatibility-v1' or set(manifest['sources']) != SOURCE_PATHS:
        raise ValueError('native compatibility source inventory changed')
    if set(manifest['inputs']) != INPUT_PATHS:
        raise ValueError('native compatibility input inventory changed')
    controls = manifest['additional_controls']
    if controls['checks'] != 1243 or sum(controls['derivation'].values()) != 1243:
        raise ValueError('native compatibility control count changed')


def project_historical(current, entry):
    """Reverse exact, ordered whole-line edits; reject changed or ambiguous data."""
    if digest(current) != entry['current_sha256']:
        raise ValueError('unreviewed native-integration source')
    lines = current.decode('utf-8').splitlines(keepends=True)
    restored = []
    cursor = 0
    for hunk in entry['hunks']:
        start = hunk['current_start']
        before = hunk['before'].splitlines(keepends=True)
        after = hunk['after'].splitlines(keepends=True)
        if start < cursor or start > len(lines) or lines[start:start + len(after)] != after:
            raise ValueError('native compatibility hunk does not match exactly')
        restored.extend(lines[cursor:start])
        restored.extend(before)
        cursor = start + len(after)
    restored.extend(lines[cursor:])
    historical = ''.join(restored).encode('utf-8')
    if digest(historical) != entry['historical_sha256']:
        raise ValueError('native compatibility projection changed historical source')
    return historical


def authenticate(source):
    source = Path(source)
    manifest = json.loads(MANIFEST.read_text())
    validate_manifest(manifest)
    projected = {}
    for name, entry in manifest['sources'].items():
        projected[name] = project_historical((source / name).read_bytes(), entry)
    for name, expected in manifest['inputs'].items():
        if digest((source / name).read_bytes()) != expected:
            raise ValueError('native compatibility control input changed: ' + name)
    # Reconnect to historical manifests, rather than trusting an independently
    # editable replacement for their dependency/bridge pins.
    p2 = json.loads((HERE / 'oracle-manifest.json').read_text())
    for name, expected in p2['shared_dependency_pins'].items():
        actual = projected.get(name, (source / name).read_bytes())
        if digest(actual) != expected:
            raise ValueError('historical P2 shared-dependency pin changed: ' + name)
    separate = 'libraries/mlf-crates/Bootstrap/Separate.hs'
    if digest(projected[separate]) != p2['integrated_p3_sha256']:
        raise ValueError('historical P2-to-P3 bridge changed')
    p3 = json.loads((HERE.parent / 'p3/candidate.json').read_text())
    for name, expected in p3['source_sha256'].items():
        actual = projected.get(name, (source / name).read_bytes())
        if digest(actual) != expected:
            raise ValueError('historical P3 candidate pin changed: ' + name)
    return manifest, projected
