#!/usr/bin/env python3
"""Snapshot the current Map source closure and directly compilable controls.

Input digests identify this run. They are not an allowlist of approved source
revisions: a source edit is accepted by a fresh preparation and rejected if it
happens after that preparation. Reference algorithms live in ordinary fixtures;
preparing or running the controls never needs old Git objects.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from check_manifest_snapshot import source_imports

MAP = 'libraries/mlf-foundation/Bootstrap/Map.hs'
C_SOURCES = ('host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c')
FIXTURES = ('RetainedBalanceControls.hs', 'HistoricalBalanceControls.hs',
            'HistoricalMap.hs', 'FrozenMap.hs', 'BaselineMap.hs')
CONTROLS = ('CurrentMapPolicyControls.hs', 'Main.hs')
MAX_BYTES = 1024 * 1024


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(root, relative):
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(),
            'relative source path required')
    path = Path(root)
    for part in Path(relative).parts:
        require(part not in ('..', '.', '/') and part, 'relative source path')
        path = path / part
        require(not path.is_symlink(), 'symlink source forbidden: ' + relative)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_size <= MAX_BYTES,
            'bounded regular source: ' + relative)
    raw = path.read_bytes()
    require(len(raw) <= MAX_BYTES, 'source changed size: ' + relative)
    return raw


def project_includes(raw):
    result = []
    for name in re.findall(rb'^\s*#\s*include\s*"([^"]+)"', raw, re.M):
        require(b'/' not in name and b'\\' not in name, 'bare project include required')
        result.append('runtime/' + name.decode('ascii'))
    return result


def project_include_graph(inputs):
    pending = list(C_SOURCES)
    graph = {}
    while pending:
        path = pending.pop()
        if path in graph:
            continue
        require(path in inputs, 'unbound transitive project include: ' + path)
        graph[path] = project_includes(inputs[path])
        pending.extend(graph[path])
    require(set(graph) == {p for p in inputs if p.endswith(('.c', '.h'))},
            'exact conservative project C/header closure')
    return graph


def read_inputs(source):
    """Follow local imports and quoted C includes, including CPP alternatives."""
    source = Path(source)
    pending = [MAP, *C_SOURCES]
    inputs = {}
    while pending:
        path = pending.pop()
        if path in inputs:
            continue
        raw = read_regular(source, path)
        inputs[path] = raw
        if path.endswith(('.c', '.h')):
            pending.extend(project_includes(raw))
        else:
            for module in source_imports(raw.decode('utf-8')):
                if not module.startswith(('Bootstrap.', 'MLF.')):
                    continue  # GHC packages are authenticated by the producer.
                rel = module.replace('.', '/') + '.hs'
                matches = [source / 'host/ghc' / rel] if module.startswith('MLF.') else list(
                    source.glob('libraries/*/' + rel))
                matches = [match for match in matches if match.is_file()]
                require(len(matches) == 1, 'missing/ambiguous local module: ' + module)
                pending.append(matches[0].relative_to(source).as_posix())
    project_include_graph(inputs)
    return inputs


def read_fixtures():
    return {**{name: read_regular(HERE / 'fixtures', name) for name in FIXTURES},
            **{name: read_regular(HERE, name) for name in CONTROLS}}


def input_identity(inputs):
    require(type(inputs) is dict and inputs, 'nonempty source inventory required')
    for name, raw in inputs.items():
        require(type(name) is str and type(raw) is bytes and len(raw) <= MAX_BYTES,
                'bounded source bytes required')
        require(name and not Path(name).is_absolute() and '..' not in Path(name).parts,
                'relative source path required')
    return {name: {'sha256': sha(raw), 'bytes': len(raw)} for name, raw in sorted(inputs.items())}


def verify_identity(inputs, expected):
    require(input_identity(inputs) == expected, 'input inventory or bytes changed during run')


def source_module_paths(inputs):
    """Home-module object paths and owning include roots for this snapshot."""
    modules = {}
    for path in inputs:
        if not path.endswith('.hs'):
            continue
        parts = Path(path).parts
        if parts[:2] == ('host', 'ghc'):
            include = 'host/ghc'
        else:
            require(len(parts) > 2 and parts[0] == 'libraries', 'local Haskell source owner')
            include = '/'.join(parts[:2])
        name = Path(path).relative_to(include).as_posix()[:-3]
        require(name not in modules, 'duplicate home module: ' + name)
        modules[name] = include
    return modules


def prepare(output, inputs, fixtures):
    """Copy inputs once, retaining their actual run identity for later checks."""
    require(set(fixtures) == set(FIXTURES + CONTROLS), 'complete Map control inventory')
    require(MAP in inputs, 'current Map source required')
    output = Path(output)
    manifest = {
        'prepared': True, 'qualification_complete': False,
        'scope': 'current Map source closure and independent algorithm/control fixtures',
        'current_inputs': input_identity(inputs),
        'fixture_inputs': input_identity(fixtures),
        'project_include_graph': project_include_graph(inputs),
        'source_modules': source_module_paths(inputs),
        'shared_base': 'Reference Map algorithms use current Types/Std/IndexVec and GHC host modules.',
    }
    output.mkdir(parents=True, exist_ok=False)
    for relative, raw in {**{'source/' + name: raw for name, raw in inputs.items()}, **fixtures}.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
    verify_snapshot(output, manifest)
    (output / 'preparation.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def verify_snapshot(output, manifest):
    output = Path(output)
    source = output / 'source'
    actual_sources = {path.relative_to(source).as_posix() for path in source.rglob('*') if path.is_file()}
    require(actual_sources == set(manifest['current_inputs']), 'prepared source inventory changed')
    verify_identity({name: read_regular(source, name) for name in actual_sources}, manifest['current_inputs'])
    actual_fixtures = {path.name for path in output.iterdir() if path.name != 'source' and path.name != 'preparation.json'}
    require(actual_fixtures == set(manifest['fixture_inputs']), 'prepared control inventory changed')
    verify_identity({name: read_regular(output, name) for name in actual_fixtures}, manifest['fixture_inputs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    require(not output.exists() and not source.is_relative_to(output) and
            (not output.is_relative_to(source) or output.is_relative_to(source / '.mlf-build')),
            'fresh output outside source inputs, or dedicated .mlf-build area')
    inputs, fixtures = read_inputs(source), read_fixtures()
    manifest = prepare(output, inputs, fixtures)
    verify_identity(read_inputs(source), manifest['current_inputs'])
    verify_identity(read_fixtures(), manifest['fixture_inputs'])


if __name__ == '__main__':
    main()
