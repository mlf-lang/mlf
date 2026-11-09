#!/usr/bin/env python3
"""Run independent direct-import controls against a completed frozen producer."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import CommandRunner


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fixture', type=Path,
                        default=Path(__file__).resolve().with_name('DirectImportControls.hs'))
    args = parser.parse_args()
    build = args.build.resolve(strict=True)
    producer = json.loads((build / 'receipt.json').read_text())
    if not producer['complete'] or not producer['immutable_inputs_verified_after']:
        raise RuntimeError('producer snapshot is incomplete')
    pins = dict(producer['compiled_snapshot_pins'])
    pins[str(Path(__file__).resolve())] = sha(__file__)
    pins[str(build / 'receipt.json')] = sha(build / 'receipt.json')
    compiler = Path(producer['executable'])
    pins[str(compiler)] = producer['executable_sha256']
    command = list(producer['commands'][-1]['argv'])
    fixture_source = args.fixture.resolve(strict=True)
    pins[str(fixture_source)] = sha(fixture_source)
    pins[command[0]] = producer['source_pins'][command[0]]
    for path, expected in pins.items():
        if sha(path) != expected:
            raise RuntimeError('producer input changed: ' + path)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    fixture = out / 'DirectImportControls.hs'
    fixture.write_bytes(fixture_source.read_bytes())
    pins[str(fixture)] = pins[str(fixture_source)]
    if sha(fixture) != pins[str(fixture)]:
        raise RuntimeError('fixture changed during snapshot')
    command[command.index(str(build / 'source/tools/experimental/prepared-prelude/source/Harness.hs'))] = str(fixture)
    command[command.index('-o') + 1] = str(out / 'direct-controls')
    receipt = {'complete': False, 'scope': 'independent raw boundary and ordinary-principal controls',
               'performance_assertions': False, 'inputs': pins, 'commands': [], 'cases': []}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def run(label, argv):
        with (out / (label + '.stdout')).open('wb') as stdout, (out / (label + '.stderr')).open('wb') as stderr:
            process = subprocess.Popen(argv, cwd=build / 'source', stdout=stdout, stderr=stderr,
                env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'},
                start_new_session=True)
            try:
                process.communicate(timeout=180)
            except BaseException:
                _, _, receipt['cleanup'] = CommandRunner.stop_group(process)
                raise
        receipt['commands'].append({'argv': argv, 'exit': process.returncode})
        save()
        if process.returncode or (out / (label + '.stderr')).stat().st_size:
            raise RuntimeError(label + ' failed')

    save()
    try:
        # Reuse only the completed producer's matching GHC object cache. This
        # recompiles its host-only Main; the producer executable stays pinned.
        run('build', command)
        pins[str(out / 'direct-controls')] = sha(out / 'direct-controls')
        run('controls', [str(out / 'direct-controls')])
        lines = (out / 'controls.stdout').read_text().splitlines()
        if not lines or lines[-1] != 'PASS all independent direct import controls':
            raise RuntimeError('independent raw controls did not complete')
        lines = lines[:-1]
        if len(lines) != 46 or len(set(lines)) != 46 or not all(line.startswith('PASS ') for line in lines):
            raise RuntimeError('independent raw control inventory changed')
        receipt['cases'] = lines
        receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = repr(error)
        raise
    finally:
        changed = [path for path, expected in pins.items() if sha(path) != expected]
        receipt['immutable_inputs_verified_after'] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
        if changed:
            raise RuntimeError('raw control inputs changed during execution')
    print(out / 'receipt.json')


if __name__ == '__main__':
    main()
