#!/usr/bin/env python3
"""Opt-in, source-authenticated O2 inference probes; not producer/CI qualification.

Authenticate a verified O2 producer's source baseline, build isolated baseline and
candidate dependency closures with GHC --make, then compare fresh-process fully
checked probes in ABBA order. This diagnostic is not producer/CI qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import statistics
import shutil
import sys
import time
from test_direct import CommandRunner

ROOT = Path(__file__).resolve().parents[2]
SOURCES = Path(__file__).with_suffix('')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(str(message))


def parse_probe_output(stdout, fixture):
    match = re.fullmatch(r'PASS ' + re.escape(str(fixture)) +
                         r' wall_ns=(\d+) cpu_ps=(\d+)\n', stdout)
    require(match is not None, 'probe output differs from the exact success oracle')
    return {'wall_s': int(match[1])/1e9, 'cpu_s': int(match[2])/1e12}


def verify_inputs(inputs):
    for path, digest in inputs.items():
        require(sha(path) == digest, 'input changed: ' + path)


def pin_inputs(inputs, paths):
    """Add fresh artifact pins without replacing any existing trust boundary."""
    for path in paths:
        key = str(path)
        digest = sha(path)
        if key in inputs:
            require(inputs[key] == digest, 'input changed: ' + key)
        else:
            inputs[key] = digest


def local_c_closure(sources, include_dirs):
    """Conservatively include quoted headers from every conditional branch."""
    pending = [Path(path).resolve() for path in sources]
    found = set()
    while pending:
        path = pending.pop()
        if path in found:
            continue
        require(path.is_file(), 'missing C source/header: ' + str(path))
        found.add(path)
        for name in re.findall(r'^\s*#\s*include\s*"([^"]+)"', path.read_text(), re.M):
            candidates = [path.parent/name, *(directory/name for directory in include_dirs)]
            matches = [candidate.resolve() for candidate in candidates if candidate.is_file()]
            require(matches, 'unresolved local C include: ' + name)
            pending.append(matches[0])
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', required=True, type=Path, help='verified O2 receipt.json')
    parser.add_argument('--baseline-ref', required=True, help='Git revision matching producer source bytes')
    parser.add_argument('--override', action='append', default=[], help='candidate source module to override; default Bootstrap.ClassDemand')
    parser.add_argument('--cycles', type=int, default=3)
    parser.add_argument('--controls', action='store_true')
    parser.add_argument('--reuse', type=Path, help='complete prior diagnostic receipt; clone and authenticate its build cache')
    parser.add_argument('--out', type=Path, help='new output directory, must not exist')
    args = parser.parse_args()
    if not 1 <= args.cycles <= 100:
        parser.error('--cycles must be between 1 and 100')
    overrides = args.override or ['Bootstrap.ClassDemand']
    out = (args.out or ROOT / '.mlf-build' / ('perf-inference-' + str(time.time_ns()))).resolve()
    out.mkdir(parents=True, exist_ok=False)
    producer = args.producer.resolve()
    receipt = json.loads(producer.read_text())
    source_root = Path(receipt['cabal_manifest']['path']).parent
    require(receipt['complete'] and receipt['optimization'] == '2' and not receipt['typecheck_only'], 'a complete O2 producer is required')
    require(receipt['ghc']['version'] == '9.14.1', 'GHC9.14.1 required')
    required = ['-O2', '-fpedantic-bottoms', '-fno-state-hack', '-clear-package-db', '-global-package-db', '-no-user-package-db', '-hide-all-packages']
    require(all(flag in receipt['flags'] for flag in required), 'producer lacks required semantic/closed-package flags')
    require(len(set(overrides)) == len(overrides), 'duplicate module override')
    for name in overrides:
        require(name in receipt['shared_inputs'], 'unknown module override: ' + name)
    record = {'diagnostic_only': True, 'build_mode': 'isolated-source-closures-ghc-make',
              'held_objects_linked': False,
              'baseline_ref': args.baseline_ref, 'producer': str(producer),
              'producer_sha256': sha(producer), 'overrides': overrides,
              'commands': [], 'observations': [], 'source_authentication': {},
              'forcing': 'full compiler, expected type, current and independent checker, roundtrip, erasure, exact runtime result, strict sourceType checksum',
              'started_unix': time.time(), 'driver_sha256': sha(__file__),
              'probe_sources': {str(p): sha(p) for p in SOURCES.glob('*') if p.is_file()}}
    def save():
        (out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    runner = CommandRunner(ROOT, out, record, save)
    def run(label, argv, timeout=120, expected=None):
        result = runner.run(label, argv, timeout=timeout, expected=expected,
                            overrides={'GHC_ENVIRONMENT': '-'})
        return result.stdout.decode('utf-8'), result.stderr.decode('utf-8')
    baseline_text, _ = run('resolve-baseline', ['git', 'rev-parse', '--verify',
        '--end-of-options', args.baseline_ref + '^{commit}'])
    require(re.fullmatch(r'[0-9a-f]{40}\n', baseline_text) is not None,
            'baseline did not resolve to one immutable commit')
    baseline_commit = baseline_text.strip()
    record['baseline_commit'] = baseline_commit
    inputs = {str(producer): sha(producer), str(Path(__file__).resolve()): sha(__file__),
              str(Path(__file__).with_name('test_direct.py')): sha(Path(__file__).with_name('test_direct.py'))}
    inputs.update(record['probe_sources'])
    preserved_sources = {}
    for path in [Path(__file__).resolve(),Path(__file__).with_name('test_direct.py'),
                 *[path for path in SOURCES.iterdir() if path.is_file()]]:
        relative = ('probes/' + path.name) if path.parent == SOURCES else path.name
        target = out/'preserved-tools'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(path.read_bytes())
        require(sha(target) == inputs[str(path)], 'tool source changed while preserving: ' + str(path))
        inputs[str(target)] = sha(target)
        preserved_sources[str(path)] = {'path':str(target),'sha256':sha(target)}
    record['preserved_tool_sources'] = preserved_sources
    record['python_version'] = sys.version
    python_binary = str(Path(sys.executable).resolve())
    inputs[python_binary] = sha(python_binary)
    if args.controls:
        test_source = ROOT/'tests/shared/MLF/Tests/ClassDemand.hs'
        inputs[str(test_source)] = sha(test_source)
    # Do not relabel an older receipt as current source. Authenticate its Git bytes.
    source_number = 0
    baseline_sources = {}
    for section in ['shared_inputs', 'host_inputs', 'configuration_inputs']:
        for name, item in receipt[section].items():
            rel = Path(item['path']).relative_to(source_root)
            blob = runner.run('authenticate-source-' + str(source_number),
                ['git', 'show', baseline_commit + ':' + str(rel)], timeout=30).stdout
            source_number += 1
            require(hashlib.sha256(blob).hexdigest() == item['sha256'], ('baseline source mismatch', rel))
            record['source_authentication'][str(rel)] = item['sha256']
            baseline_sources[str(rel)] = blob
            if section == 'host_inputs' or (item.get('role') == 'implementation' and name not in overrides):
                require(sha(ROOT / rel) == item['sha256'], ('unrequested implementation change', rel))
                inputs[str(ROOT / rel)] = item['sha256']
    for rel, digest in record['source_authentication'].items():
        if rel.endswith(('.c', '.h')) and (rel.startswith('runtime/') or rel.startswith('host/')):
            require(sha(ROOT/rel) == digest, 'transport source/header changed: ' + rel)
            inputs[str(ROOT/rel)] = digest
    for tool in ['ghc', 'cc']:
        require(sha(receipt[tool]['path']) == receipt[tool]['sha256'], 'compiler/CC binary changed')
        inputs[receipt[tool]['path']] = receipt[tool]['sha256']
    toolchain_files = {**receipt['toolchain']['files'], **receipt['installed_dependencies']['files']}
    verify_inputs(toolchain_files)
    inputs.update(toolchain_files)
    record['toolchain_files'] = toolchain_files
    # The producer authenticates source/toolchain identity. None of its Haskell
    # objects/interfaces are admitted into either diagnostic dependency closure.
    flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
             '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms', '-fno-state-hack']
    for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
        flags += ['-package', package]
    # These existing baseline warnings are compile-only accommodations, not the
    # producer's warning policy. Runtime/control stderr remains strictly empty.
    flags += ['-Wno-star-is-type', '-Wno-overlapping-patterns', '-Wno-deprecations',
              '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns']
    record['flags'] = flags
    record['toolchain'] = {name: receipt[name] for name in ['ghc', 'cc']}
    require('shared-sources.json' in baseline_sources, 'missing authenticated source-root manifest')
    manifest = json.loads(baseline_sources['shared-sources.json'])
    for source_root_name in manifest['source_roots']:
        relative = Path(source_root_name)
        require(not relative.is_absolute() and '..' not in relative.parts,
                'unsafe source root: ' + source_root_name)
    ghc, cc = receipt['ghc']['path'], receipt['cc']['path']
    changes = {}
    override_bytes = {}
    for name in overrides:
        item = receipt['shared_inputs'][name]
        require(item.get('role') == 'implementation', 'override is not an implementation module: ' + name)
        relative = Path(item['path']).relative_to(source_root)
        source = ROOT / relative
        digest = sha(source)
        inputs[str(source)] = digest
        override_bytes[str(relative)] = source.read_bytes()
        changes[name] = {'source': str(source), 'sha256': digest}
    record['candidate_sources'] = changes
    reuse = None
    if args.reuse:
        prior_path = args.reuse.resolve()
        prior = json.loads(prior_path.read_text())
        require(prior.get('complete') and prior.get('all_run_inputs_verified_after'),
                'reuse requires a complete verified diagnostic receipt')
        require(prior.get('build_mode') == 'isolated-source-closures-ghc-make'
                and prior.get('held_objects_linked') is False, 'cannot reuse an overlay build')
        require(prior.get('baseline_commit') == baseline_commit
                and prior.get('producer_sha256') == sha(producer)
                and prior.get('flags') == flags, 'reuse baseline/toolchain/flags differ')
        require(prior.get('overrides') == overrides, 'reuse override inventory differs')
        require(prior.get('toolchain') == record['toolchain']
                and prior.get('toolchain_files') == toolchain_files, 'reuse toolchain identity differs')
        previous_inputs = {}
        for variant in ['baseline', 'candidate']:
            variant_root = (prior_path.parent/variant).resolve()
            for path in prior['source_snapshots'][variant]:
                require(Path(path).resolve().is_relative_to(variant_root/'source'),
                        'reuse source outside its variant source tree')
            for path in prior['build_artifacts'][variant]:
                require(Path(path).resolve().is_relative_to(variant_root),
                        'reuse artifact outside its variant tree')
            previous_inputs.update(prior['source_snapshots'][variant])
            previous_inputs.update(prior['build_artifacts'][variant])
        previous_inputs.update(prior['toolchain_files'])
        for tool in ['ghc','cc']:
            previous_inputs[prior['toolchain'][tool]['path']] = prior['toolchain'][tool]['sha256']
        verify_inputs(previous_inputs)
        inputs.update(previous_inputs)
        inputs[str(prior_path)] = sha(prior_path)
        reuse = (prior_path.parent, prior)
        record['reuse'] = {'receipt': str(prior_path), 'sha256': sha(prior_path),
                           'mode': 'authenticated immutable prior tree, copied into this fresh run',
                           'removed_changed_module_artifacts': []}
    record['source_snapshots'] = {}
    record['build_artifacts'] = {}
    for variant in ['baseline', 'candidate']:
        directory = out / variant
        sources = directory / 'source'
        objects = directory / 'objects'
        objects.mkdir(parents=True)
        if reuse:
            previous_directory = reuse[0]/variant
            for path, digest in reuse[1]['build_artifacts'][variant].items():
                old = Path(path).resolve()
                require(old.is_relative_to(previous_directory.resolve()), 'reuse artifact outside its variant tree')
                relative = old.relative_to(previous_directory)
                # Only Haskell cache artifacts are reused. Transports/executables
                # are rebuilt, and no file in the previous run is modified.
                if relative.parts[0] == 'objects' and old.suffix in ['.o','.hi']:
                    target = directory/relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old,target)
        contents = dict(baseline_sources)
        if variant == 'candidate':
            contents.update(override_bytes)
        if args.controls:
            contents['tests/shared/MLF/Tests/ClassDemand.hs'] = test_source.read_bytes()
        contents['Main.hs'] = (SOURCES/'Main.hs').read_bytes()
        if args.controls:
            contents['PerfControls.hs'] = (SOURCES/'Controls.hs').read_text().replace(
                'module Main where', 'module PerfControls where').encode()
        modules_by_source = {str(Path(item['path']).relative_to(source_root)): name
            for name,item in receipt['shared_inputs'].items()}
        modules_by_source.update({'Main.hs':'Main', 'PerfControls.hs':'PerfControls',
            'tests/shared/MLF/Tests/ClassDemand.hs':'MLF.Tests.ClassDemand'})
        for relative, data in contents.items():
            target = sources/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            old = reuse[0]/variant/'source'/relative if reuse else None
            old_pin = reuse[1]['source_snapshots'][variant].get(str(old)) if reuse else None
            if old_pin is not None and old.read_bytes() == data:
                shutil.copy2(old,target)
            else:
                target.write_bytes(data)
                if reuse and relative in modules_by_source:
                    # A changed source never relies on clock/mtime ordering.
                    # GHC owns downstream invalidation from this missing .hi.
                    module = Path(*modules_by_source[relative].split('.'))
                    for suffix in ['.o','.hi']:
                        artifact = (objects/module).with_suffix(suffix)
                        artifact.unlink(missing_ok=True)
                        record['reuse']['removed_changed_module_artifacts'].append(str(artifact))
        snapshot_paths = [sources/relative for relative in contents]
        pin_inputs(inputs, snapshot_paths)
        record['source_snapshots'][variant] = {str(path): inputs[str(path)] for path in snapshot_paths}
        c_sources = [('host', sources/'host/ghc/cbits/host.c'),
                     ('supervisor', sources/'runtime/mlf_process_supervisor.c')]
        for path in local_c_closure([source for _, source in c_sources], [sources/'runtime']):
            require(str(path) in inputs, 'unauthenticated C source/header: ' + str(path))
        for name, source in c_sources:
            run('build-' + variant + '-' + name,
                [cc, '-O2', '-std=c11', '-I'+str(sources/'runtime'), '-c', source,
                 '-o', directory/(name+'.o')])
        transports = [directory/'host.o', directory/'supervisor.o']
        search = ['-i', '-i'+str(sources), *['-i'+str(sources/path) for path in manifest['source_roots']]]
        make = [ghc, '--make', '-j1', '-no-link', *flags, *search,
                '-odir', objects, '-hidir', objects]
        run('build-' + variant, [*make, sources/'Main.hs'], 180)
        require(list(objects.rglob('*.o')), 'GHC produced no closure objects')
        link_make = [ghc, '--make', '-j1', *flags, *search,
                     '-odir', objects, '-hidir', objects, '-rtsopts=ignoreAll']
        run('link-' + variant, [*link_make, sources/'Main.hs', *transports,
                               '-o', directory/'probe'], 60)
        pin_inputs(inputs, [directory/'probe'])
        if args.controls:
            run('build-controls-' + variant,
                [*make, '-main-is', 'PerfControls.main', sources/'PerfControls.hs'], 180)
            run('link-controls-' + variant,
                [*link_make, '-main-is', 'PerfControls.main', sources/'PerfControls.hs',
                 *transports, '-o', directory/'controls'], 60)
        # Pin all completed build artifacts before any measured/control run.
        # Control entrypoint compilation may legitimately refresh its own cache.
        pin_inputs(inputs, [path for path in directory.rglob('*') if path.is_file()
                           and (path.suffix in ['.o', '.hi'] or path.name in ['probe','controls'])])
        record['build_artifacts'][variant] = {str(path): inputs[str(path)]
            for path in directory.rglob('*') if str(path) in inputs
            and (path.suffix in ['.o', '.hi'] or path.name in ['probe', 'controls'])}
        save()
    run('fixtures', [sys.executable, SOURCES/'fixtures.py', out/'fixtures'])
    fixtures = json.loads((out/'fixtures/index.json').read_text())
    inputs.update({str(p): sha(p) for p in (out/'fixtures').iterdir() if p.is_file()})
    record['all_run_inputs'] = inputs
    record['transport_inputs'] = {path: digest for path, digest in inputs.items() if path.endswith(('.c', '.h'))}
    save()
    for cycle in range(args.cycles):
        for position, variant in enumerate(['baseline', 'candidate', 'candidate', 'baseline']):
            for fixture, kind in fixtures.items():
                stdout, stderr = run(f'run-{cycle}-{position}-{fixture}', [out/variant/'probe', out/'fixtures'/(fixture+'.emlf'), kind], 30)
                timing = parse_probe_output(stdout, out/'fixtures'/(fixture+'.emlf'))
                record['observations'].append({'cycle': cycle, 'variant': variant, 'fixture': fixture, **timing})
            save()
    if args.controls:
        # Verify the original pins before controls; never refresh a digest after
        # samples. Any input mutation invalidates the whole diagnostic run.
        verify_inputs(inputs)
        for variant in ['baseline', 'candidate']:
            run('controls-' + variant, [out/variant/'controls'], 180, expected=(
                b'shared frontend: qualified recursive inference checks passed\n'
                b'PASS targeted planner, recursive classes, provenance, capture/skolem, raw/canonical controls\n'))
    summary = {}
    for fixture in fixtures:
        summary[fixture] = {}
        for variant in ['baseline', 'candidate']:
            samples = [r['cpu_s'] for r in record['observations'] if r['fixture']==fixture and r['variant']==variant]
            summary[fixture][variant] = {'n': len(samples), 'median_cpu_s': statistics.median(samples)}
        a, b = (summary[fixture][v]['median_cpu_s'] for v in ['baseline', 'candidate'])
        summary[fixture]['median_cpu_change_percent'] = 100*(b/a-1)
        print(f'{fixture}: {a*1000:.3f} -> {b*1000:.3f} ms CPU ({100*(b/a-1):+.2f}%)')
    verify_inputs(inputs)
    record['all_run_inputs_verified_after'] = True
    record.update(summary=summary, ended_unix=time.time(), complete=True,
                  artifacts={str(p):sha(p) for p in out.rglob('*') if p.is_file() and (p.suffix in ['.o','.hi'] or p.name in ['probe','controls'])})
    save()
    print('Receipt:', out/'receipt.json')

if __name__ == '__main__':
    main()
