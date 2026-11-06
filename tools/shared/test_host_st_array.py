#!/usr/bin/env python3
"""Exercise host ST arrays at O0/O2, including lazy values and error priority."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ghc = Path(shutil.which(args.ghc) or args.ghc).resolve(strict=True)
    cc = Path(shutil.which(args.cc) or args.cc).resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    fixture = ROOT/'tools/shared/fixtures/HostSTArray.hs'
    inputs = [Path(__file__).resolve(), fixture, ROOT/'host/ghc/MLF/Host/Base.hs',
              ROOT/'host/ghc/cbits/host.c', ROOT/'runtime/mlf_process_supervisor.c',
              *sorted((ROOT/'runtime').glob('*.h'))]
    hashes = {str(path): digest(path) for path in inputs}
    record = {'complete': False, 'scope': 'GHC host ST array controls only',
              'inputs': hashes, 'commands': [], 'ghc': str(ghc), 'cc': str(cc)}

    def save():
        (output/'receipt.json').write_text(json.dumps(record, indent=2)+'\n')

    def run(label, command):
        result = subprocess.run(list(map(str, command)), cwd=ROOT,
                                capture_output=True, timeout=60)
        (output/(label+'.stdout')).write_bytes(result.stdout)
        (output/(label+'.stderr')).write_bytes(result.stderr)
        record['commands'].append({'label': label, 'argv': list(map(str, command)),
                                   'exit_code': result.returncode})
        save()
        if result.returncode:
            raise RuntimeError(label+' failed; see '+str(output))
        return result

    version = run('ghc-version', [ghc, '--numeric-version']).stdout.strip()
    if version != b'9.14.1':
        raise RuntimeError('requires GHC 9.14.1')
    objects = []
    for label, source in [('host', ROOT/'host/ghc/cbits/host.c'),
                          ('supervisor', ROOT/'runtime/mlf_process_supervisor.c')]:
        obj = output/(label+'.o')
        run(label, [cc, '-O2', '-std=c11', '-I'+str(ROOT/'runtime'),
                    '-c', source, '-o', obj])
        objects.append(obj)
    for optimization in ['0', '2']:
        directory = output/('O'+optimization)
        directory.mkdir()
        binary = directory/'host-st-array'
        run('build-O'+optimization,
            [ghc, '--make', '-j1', '-O'+optimization, '-fpedantic-bottoms',
             '-fno-state-hack', '-package-env', '-', '-i'+str(ROOT/'host/ghc'),
             '-odir', directory, '-hidir', directory, fixture, *objects, '-o', binary])
        result = run('run-O'+optimization, [binary])
        lines = result.stdout.splitlines()
        if result.stderr or len(lines) != 34 or lines[-1] != b'PASS 33 host ST array controls' or any(
                not line.startswith(b'PASS ') for line in lines):
            raise RuntimeError('unexpected host control output at O'+optimization)
    if hashes != {str(path): digest(path) for path in inputs}:
        raise RuntimeError('host test inputs changed during controls')
    record['complete'] = True
    save()
    print('PASS 33 host ST array controls at O0 and O2')


if __name__ == '__main__':
    main()
