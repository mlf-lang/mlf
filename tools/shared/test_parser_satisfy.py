#!/usr/bin/env python3
"""Check parser token results and demand against frozen pre-worker semantics."""
from pathlib import Path
import argparse
import json

from test_direct import CommandRunner, authenticate_build, sha

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    build, output = receipt.parent, args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or output.is_relative_to(build):
        parser.error('independent output directory required')
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'commands': [], 'inputs': {},
              'scope': 'Actual qualified host Parsec objects, complete results and demand; not native compiler qualification.'}

    def save():
        (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    runner = CommandRunner(ROOT, output, record, save)
    try:
        producer = authenticate_build(receipt, build / 'bin')
        fixture = ROOT / 'tools/shared/fixtures/ParserSatisfyControls.hs'
        inputs = [receipt, fixture, Path(__file__).resolve(), ROOT / 'tools/shared/test_direct.py',
                  ROOT / 'libraries/mlf-frontend/Bootstrap/Parsec.hs',
                  ROOT / 'libraries/mlf-frontend/Bootstrap/Lexer.hs', build / 'host.o', build / 'supervisor.o']
        record['inputs'] = {str(path): sha(path) for path in inputs}
        flags = ['-O2', '-fpedantic-bottoms', '-fno-state-hack', '-dcore-lint', '-Wno-x-partial',
                 '-package-env', '-', '-clear-package-db', '-global-package-db', '-no-user-package-db', '-hide-all-packages']
        for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
            flags += ['-package', package]
        runner.run('compile', [producer['ghc']['path'], '-c', *flags, '-i', '-i' + str(output),
                   '-i' + str(build / 'objects'), fixture, '-o', output / 'Main.o', '-ohi', output / 'Main.hi'], timeout=120)
        objects = [build / path for path in sorted(producer['object_inputs']) if path.endswith('.o') and path != 'objects/Main.o']
        runner.run('link', [producer['ghc']['path'], *flags, '-rtsopts=ignoreAll', output / 'Main.o',
                   *objects, build / 'host.o', build / 'supervisor.o', '-o', output / 'controls'], timeout=120)
        runner.run('controls', [output / 'controls'],
                   expected=b'Parser satisfy controls: 7560 complete result cases; 11 demand checks\n', timeout=120)
        for path, digest in record['inputs'].items():
            if sha(path) != digest:
                raise ValueError('test input changed: ' + path)
        authenticate_build(receipt, build / 'bin')
        record.update(complete=True, control_binary_sha256=sha(output / 'controls'))
        print('PASS parser satisfy: 7560 complete result cases; 11 demand checks')
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
