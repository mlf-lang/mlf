#!/usr/bin/env python3
"""O0/O2 owner controls, using unchanged authenticated ordinary dependencies.

This is a narrow semantic gate. It does not build or qualify a complete candidate
compiler and it never changes the producer. Optional timing is synthetic encoding
only; it is not compiler wall-time evidence. Run serially on an idle machine.
"""
from pathlib import Path
import argparse
import json
import math
import shutil
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OWNERS = ['Bootstrap.CrateQuery', 'Bootstrap.CrateSession']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--producer-source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--measure', action='store_true')
    parser.add_argument('--integration', action='store_true', help='Run the unchanged source-context campaign using the qualified O2 owners.')
    args = parser.parse_args()
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('source_context_write_guard')
    H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    producer = args.producer.resolve(strict=True)
    source = args.producer_source.resolve(strict=True)
    output = args.output.resolve()
    H.require(not output.exists(), 'fresh output required')
    H.require(not producer.is_relative_to(output) and not output.is_relative_to(producer)
              and not ROOT.is_relative_to(output), 'output must be separate from producer/source ancestor')
    auth = H.authenticate(producer, source)
    # Admit exactly the two local owners. Every other shared source and host
    # input must be byte-identical to the authenticated producer.
    manifest = H.load(ROOT / 'shared-sources.json')
    paths = {row['module']: row['path'] for row in manifest['modules']}
    for name, relative in paths.items():
        if name not in OWNERS:
            H.require(H.sha(ROOT / relative) == H.sha(source / relative), 'unexpected changed dependency: ' + name)
    for relative in auth['host_inputs']:
        H.require(H.sha(ROOT / relative) == H.sha(source / relative), 'changed host dependency: ' + relative)
    output.mkdir(parents=True)
    pins = {str(producer / relative): digest for relative, digest in auth['object_inputs'].items()}
    H.require(pins and set(H.file_pins(producer / 'objects')) == set(pins),
              'producer object inventory differs from authenticated receipt')
    H.check_pins(pins)
    inputs = {str(path): H.sha(path) for path in [helper, Path(__file__), HERE / 'Main.hs',
              ROOT / 'shared-sources.json', *[ROOT / relative for relative in paths.values()],
              *[ROOT / relative for relative in auth['host_inputs']],
              ROOT / 'tools/shared/fixtures/item4/SourceContextCache.hs',
              ROOT / 'tools/shared/fixtures/item4/SourceKeyWitness.hs',
              ROOT / 'tools/shared/run_context_controls.py',
              ROOT / 'tools/shared/test_source_context_cache.py',
              *[ROOT / ('tools/shared/' + name) for name in ['artifact_binary_reference.py',
                 'artifact_binary_typed.py', 'artifact_structure_contract.json']]]}
    limits = {'address_space_per_process_bytes': 6*1024**3, 'disk_free_floor_bytes': 2*1024**3,
              'host_available_floor_bytes': 2*1024**3, 'max_work_bytes': 1024**3,
              'process_tree_rss_bytes': 5*1024**3, 'wall_seconds': 600}
    record = {'complete': False, 'scope': 'two-owner-controls-not-full-producer',
              'producer_receipt_sha256': H.sha(producer / 'receipt.json'), 'inputs': inputs,
              'measure': args.measure, 'integration': args.integration, 'commands': [], 'synthetic_samples': []}
    flags, index = [], 0
    while index < len(auth['flags']):
        flag = auth['flags'][index]
        if flag in ['-odir', '-hidir']:
            index += 2
            continue
        if not flag.startswith(('-i', '-O')):
            flags.append(flag)
        index += 1
    def run(name, argv, timed=False):
        result = H.Runner(output, limits).run(argv, ROOT, output / name, timed=timed)
        record['commands'].append(result)
        H.save(output / 'receipt.json', record)
        return result
    try:
        transport = []
        for name, relative in [('host', 'host/ghc/cbits/host.c'),
                               ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            obj = output / (name + '.o')
            run('compile-' + name, [auth['cc']['path'], '-O2', '-std=c11',
                '-I' + str(ROOT / 'runtime'), '-c', ROOT / relative, '-o', obj])
            transport.append(obj)
        for optimization in ['0', '2']:
            work = output / ('O' + optimization)
            objects = work / 'objects'
            shutil.copytree(producer / 'objects', objects)
            for suffix in ['.hi', '.o']:
                (objects / ('Main' + suffix)).unlink(missing_ok=True)
            local_pins = H.file_pins(objects)
            owner_files = {str(objects / (name.replace('.', '/') + suffix))
                           for name in OWNERS for suffix in ['.hi', '.o']}
            preserved = {path: digest for path, digest in local_pins.items() if path not in owner_files}
            local_flags = [*flags, '-O' + optimization, '-i', '-i' + str(objects),
                           '-odir', str(objects), '-hidir', str(objects),
                           '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns']
            for owner in OWNERS:
                run('O' + optimization + '-compile-' + owner,
                    [auth['ghc']['path'], *local_flags, '-c', ROOT / paths[owner]])
            run('O' + optimization + '-compile-fixture',
                [auth['ghc']['path'], *local_flags, '-c', HERE / 'Main.hs'])
            binary = work / 'controls'
            run('O' + optimization + '-link', [auth['ghc']['path'], *local_flags, '-rtsopts=ignoreAll',
                *sorted(objects.rglob('*.o')), *transport, '-o', binary])
            control_name = 'O' + optimization + '-controls'
            run(control_name, [binary, 'controls', work / 'cache'])
            H.require((output / control_name / 'stdout').read_text() ==
                      'PASS 81 byte/digest transitions; retention identity/cap; publication repair/failure and complete writer controls\n'
                      and not (output / control_name / 'stderr').read_bytes(), 'exact control completion required')
            H.check_pins(preserved)
            if args.integration and optimization == '2':
                witness = ROOT / 'tools/shared/fixtures/item4/SourceKeyWitness.hs'
                fixture = ROOT / 'tools/shared/fixtures/item4/SourceContextCache.hs'
                run('compile-source-context-witness', [auth['ghc']['path'], *local_flags, '-c', witness])
                run('compile-source-context-fixture', [auth['ghc']['path'], *local_flags, '-c', fixture,
                    '-o', objects / 'Main.o', '-ohi', objects / 'Main.hi'])
                integration_binary = work / 'source-context-controls'
                run('link-source-context-fixture', [auth['ghc']['path'], *local_flags, '-rtsopts=ignoreAll',
                    *sorted(objects.rglob('*.o')), *transport, '-o', integration_binary])
                import sys
                python = Path(sys.executable).resolve(strict=True)
                controls = ROOT / 'tools/shared/run_context_controls.py'
                integration_output = work / 'source-context-campaign'
                run('source-context-campaign', [python, '-I', '-B', controls,
                    '--fixture', integration_binary, '--output', integration_output])
                gate = H.module(ROOT / 'tools/shared/test_source_context_cache.py', 'unchanged_source_context_gate')
                inspector_hashes = {str(controls.with_name(name)): H.sha(controls.with_name(name))
                                    for name in gate.BINARY_HELPER_NAMES}
                gate.verify_control_receipt(integration_output / 'receipt.json', integration_binary,
                    python, controls, inspector_hashes)
                record['integration_commands'] = gate.EXPECTED_COMMANDS
                H.check_pins(preserved)
            if args.measure and optimization == '2':
                # Frozen eight-leg ABBA BAAB sequence. No warmup/sample replacement.
                sequence = ['fresh', 'memo', 'memo', 'fresh', 'memo', 'fresh', 'fresh', 'memo']
                outputs = []
                for i, mode in enumerate(sequence):
                    name = 'sample-' + str(i) + '-' + mode
                    result = run(name, [binary, mode, '1000', '64'], timed=True)
                    outputs.append((output / name / 'stdout').read_bytes())
                    record['synthetic_samples'].append({'mode': mode, 'wall_seconds': result['wall_seconds'],
                        'child_user_seconds': result['child_user_seconds'],
                        'child_system_seconds': result['child_system_seconds']})
                H.require(len(set(outputs)) == 1, 'synthetic final encoding hashes differ')
                med = {mode: math.exp(sum(math.log(r['wall_seconds']) for r in record['synthetic_samples']
                    if r['mode'] == mode)/4) for mode in ['fresh', 'memo']}
                record['synthetic_geomean_wall_seconds'] = med
                record['synthetic_ratio'] = med['fresh'] / med['memo']
        H.check_pins(inputs)
        H.check_pins(pins)
        H.require(H.authenticate(producer, source) == auth, 'producer changed')
        record['complete'] = True
    finally:
        H.save(output / 'receipt.json', record)
    print(json.dumps({'complete': True, 'scope': record['scope'], 'synthetic_samples': len(record['synthetic_samples'])}))


if __name__ == '__main__':
    main()
