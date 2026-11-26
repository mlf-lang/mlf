#!/usr/bin/env python3
"""Measure production module parsing and the historical row accumulator."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=5)
    parser.add_argument('--ghc', default='ghc')
    args = parser.parse_args()
    baseline = args.baseline.resolve(strict=True)
    output = args.output.resolve()
    if output == ROOT or ROOT.is_relative_to(output) or args.samples < 1:
        parser.error('a separate output directory and at least one sample are required')
    output.mkdir(parents=True, exist_ok=False)
    version = subprocess.check_output([args.ghc, '--numeric-version'], text=True).strip()
    if version != '9.14.1':
        parser.error('GHC 9.14.1 is required')
    optimization = ['-O2', '-fstatic-argument-transformation', '-fpedantic-bottoms', '-fno-state-hack']
    for label, repository in [('before', baseline), ('after', ROOT)]:
        objects = output / label
        objects.mkdir()
        command = [args.ghc, '--make', '-v0', '-w', *optimization, '-rtsopts',
                   '-i' + str(repository / 'host/ghc'),
                   *['-i' + str(path) for path in sorted((repository / 'libraries').iterdir())],
                   '-odir', str(objects), '-hidir', str(objects), '-I' + str(repository / 'runtime'),
                   str(Path(__file__).with_name('Frontend.hs')),
                   str(repository / 'host/ghc/cbits/host.c'), str(repository / 'runtime/mlf_process_supervisor.c'),
                   '-o', str(objects / 'probe')]
        subprocess.run(command, cwd=ROOT, check=True)
    rows = []
    for family, widths in [('parse', [128,512,2048,4096]), ('rows', [256,1024,4096,8192])]:
        for width in widths:
            checksums = []
            for label in ['before', 'after']:
                mode = 'parse' if family == 'parse' else 'rows-' + label
                samples = []
                for _ in range(args.samples):
                    line = subprocess.check_output([output / label / 'probe', mode, str(width),
                                                    '+RTS', '-T', '-RTS'], text=True).strip()
                    _, _, elapsed, allocation, checksum = line.split(',')
                    samples.append({'cpu_seconds': float(elapsed), 'allocated_bytes': int(allocation),
                                    'checksum': int(checksum)})
                    checksums.append(int(checksum))
                row = {'family': family, 'width': width, 'version': label,
                       'median_cpu_seconds': statistics.median(sample['cpu_seconds'] for sample in samples),
                       'median_allocated_bytes': statistics.median(sample['allocated_bytes'] for sample in samples),
                       'samples': samples}
                rows.append(row)
                print(json.dumps({key: value for key, value in row.items() if key != 'samples'}), flush=True)
            if len(set(checksums)) != 1:
                raise ValueError(f'baseline and current semantic checksums differ: {family}/{width}')
    result = {'baseline': subprocess.check_output(['git', '-C', baseline, 'rev-parse', 'HEAD'], text=True).strip(),
              'ghc': version, 'optimization': ' '.join(optimization),
              'scope': 'Isolated production parseModule timing and historical normalizeRow append accumulator; '
                       'CPU time and GHC allocations, not end-to-end compiler speed. '
                       'Row before uses the pre-9815b98 accumulator reference.', 'results': rows}
    (output / 'frontend-results.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
