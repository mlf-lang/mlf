#!/usr/bin/env python3
"""Faithful Figure12 checks using authenticated GHC objects, not nested interpretation.

Builds only a test entry in a fresh output directory; qualified compiler objects
and implementation files are never rewritten. This is not native-unit coverage.
Run under the repository's externally selected process-tree resource envelope.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from figure12_data import decode
from test_direct import authenticate_build
from build import PACKAGES, DEMAND_FLAGS

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_inventory(fixture):
    cases = fixture['cases']
    names = [c['id'] for c in cases]
    rows = {n.split('.')[0] for n in names}
    wanted = {f'A{i}' for i in range(1, 14)} | {f'B{i}' for i in range(1, 8)} | {'C1a', 'C1b', 'C1c', 'C2'} | {f'E{i}{s}' for i in range(1, 6) for s in 'ab'}
    if len(names) != 43 or len(set(names)) != 43 or rows != wanted:
        raise ValueError('Figure12 paper row/expression inventory changed')
    if [c['id'] for c in cases if not c['paper_acceptance']] != ['A11', 'C1a', 'C1c', 'E1a']:
        raise ValueError('Figure12 paper expectations changed')
    if [c['id'] for c in cases if not c['expected_acceptance']] != ['A8', 'A11', 'C1a', 'C1c', 'E1a']:
        raise ValueError('Figure12 regression expectations changed')
    if [c['id'] for c in cases if c['paper_acceptance'] != c['expected_acceptance']] != ['A8']:
        raise ValueError('Figure12 paper discrepancy changed')
    if len(fixture['type_checks']) != 4 or len(fixture['repairs']) != 3:
        raise ValueError('Figure12 supplementary inventory changed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    receipt_path = args.build_receipt.resolve(strict=True)
    producer_dir = receipt_path.parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'mode': 'direct-GHC-Figure12-maintained-fixtures',
              'full_native_unit': False, 'commands': [], 'aliases': []}
    def save():
        (output/'receipt.json').write_text(json.dumps(record, indent=2)+'\n')
    def run(label, argv, expected=None):
        completed = subprocess.run([str(x) for x in argv], cwd=ROOT, capture_output=True, timeout=120)
        stdout, stderr = output/(label+'.stdout'), output/(label+'.stderr')
        stdout.write_bytes(completed.stdout)
        stderr.write_bytes(completed.stderr)
        record['commands'].append({'label': label, 'argv': [str(x) for x in argv],
            'exit_code': completed.returncode, 'stdout_sha256': digest(stdout), 'stderr_sha256': digest(stderr)})
        save()
        if completed.returncode or (expected is not None and (completed.stdout != expected or completed.stderr)):
            raise ValueError(f'{label} failed; see {stdout} and {stderr}')
        return completed.stdout
    save()
    try:
        producer = authenticate_build(receipt_path, producer_dir/'bin')
        objects = producer.get('object_inputs', {})
        if not objects:
            raise ValueError('Producer omitted authenticated object inventory')
        for name, sha in objects.items():
            path = (producer_dir/name).resolve(strict=True)
            if not path.is_relative_to(producer_dir) or digest(path) != sha:
                raise ValueError('Producer object changed: '+name)
        inputs = [Path(__file__).resolve(), ROOT/'tools/shared/test_direct.py', ROOT/'tools/shared/build.py',
                  ROOT/'tools/shared/figure12_data.py', ROOT/'tools/shared/Figure12Direct.hs',
                  ROOT/'tests/Tests/Figure12.emlf', ROOT/'tests/Tests/Figure12Suite.emlf',
                  ROOT/'tests/Tests/Map.emlf', ROOT/'tests/Tests/Set.emlf', ROOT/'tests/Tests/Helpers.emlf']
        input_hashes = {str(p.relative_to(ROOT)): digest(p) for p in inputs}
        record.update(producer_receipt=str(receipt_path), producer_receipt_sha256=digest(receipt_path),
            optimization=producer['optimization'], inputs=input_hashes, object_inputs=objects)
        fixture = decode(ROOT)
        validate_inventory(fixture)
        fixture_path = output/'fixture.json'
        fixture_path.write_text(json.dumps(fixture, ensure_ascii=False, indent=2)+'\n')
        record['fixture_sha256'] = digest(fixture_path)
        ghc = producer['ghc']['path']
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O'+producer['optimization'], *DEMAND_FLAGS]
        for package in PACKAGES:
            flags += ['-package', package]
        main_object = output/'Figure12Direct.o'
        run('compile-harness', [ghc, '-c', *flags, '-i', '-i'+str(producer_dir/'objects'),
            '-o', main_object, '-ohi', output/'Figure12Direct.hi', ROOT/'tools/shared/Figure12Direct.hs'])
        # All object bytes were authenticated above. Exclude the producer's last
        # wrapper Main; this test has its own Main and separate linker output.
        link_objects = [producer_dir/n for n in sorted(objects) if n.endswith('.o') and n != 'objects/Main.o']
        # The producer inventories Haskell objects, but not its two standalone
        # C objects. Rebuild these tiny transport objects from authenticated
        # source/toolchain rather than silently trusting unbound bytes.
        c_objects = []
        for label, source in [('host', ROOT/'host/ghc/cbits/host.c'), ('supervisor', ROOT/'runtime/mlf_process_supervisor.c')]:
            obj = output/(label+'.o')
            run('c-'+label, [producer['cc']['path'], '-O2', '-std=c11', '-I'+str(ROOT/'runtime'), '-c', source, '-o', obj])
            c_objects.append(obj)
        record['transport_objects'] = {str(p): digest(p) for p in c_objects}
        link_objects += c_objects
        executable = output/'figure12-direct'
        run('link-harness', [ghc, *flags, '-rtsopts=ignoreAll', main_object, *link_objects, '-o', executable])
        record['executable_sha256'] = digest(executable)
        inventory = json.loads(run('inventory', [executable, fixture_path, 'inventory', '0']))
        assumptions, programs, aliases = inventory['assumptions'], inventory['programs'], inventory['aliases']
        if len(assumptions) != 29 or len(programs) != 43 or aliases != [['A12.1','A10.1'],['E3a','A12.2']]:
            raise ValueError('Derived assumption/program/alias inventory changed')
        record['aliases'] = aliases
        record['inventory'] = inventory
        for i in range(29):
            run(f'assumption-{i:02}', [executable, fixture_path, 'assumption', str(i)], b'PASS assumption\n')
        for i in range(4):
            run(f'type-{i}', [executable, fixture_path, 'type', str(i)], b'PASS type\n')
        for i in range(3):
            run(f'repair-{i}', [executable, fixture_path, 'repair', str(i)], b'PASS repair\n')
        seen = {}
        for i, (case, program) in enumerate(zip(fixture['cases'], programs)):
            key = (case['expected_acceptance'], program)
            if key in seen:
                if [case['id'], seen[key]] not in aliases:
                    raise ValueError('Unreviewed execution alias')
            else:
                run('case-'+case['id'], [executable, fixture_path, 'case', str(i)], b'PASS case\n')
                seen[key] = case['id']
        if len(seen) != 41:
            raise ValueError('Distinct Figure12 executions changed')
        authenticate_build(receipt_path, producer_dir/'bin')
        for name, sha in objects.items():
            if digest(producer_dir/name) != sha:
                raise ValueError('Producer object changed during tests: '+name)
        if digest(receipt_path) != record['producer_receipt_sha256'] or any(digest(ROOT/p) != h for p,h in input_hashes.items()):
            raise ValueError('Fixture, harness or producer receipt changed during tests')
        if digest(fixture_path) != record['fixture_sha256'] or digest(executable) != record['executable_sha256']:
            raise ValueError('Decoded fixture or harness executable changed during tests')
        if any(digest(path) != sha for path, sha in record['transport_objects'].items()):
            raise ValueError('Rebuilt C transport object changed during tests')
        record.update(complete=True, paper_rows=34, labels=43, distinct_expressions=41,
                      assumption_controls=29, principal_type_controls=4, annotation_repairs=3,
                      current_target_roundtrip=True, current_target_type=True, current_target_erasure=True)
    except BaseException as error:
        record['error'] = type(error).__name__+': '+str(error)
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
