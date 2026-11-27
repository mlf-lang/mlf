#!/usr/bin/env python3
"""Compare unchanged probes linked to two real MLF source checkouts.

These are GHC-hosted algorithm CPU timings, not native compiler build ratios.
Use ../compiler-shapes/bench.py for the end-to-end comparison with GHC.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import time

HERE = Path(__file__).resolve().parent
GROUPS = {
    'crates': ('Crates.hs', {
        'metadata-bytes': [1048576, 8388608],
        'source-arrow': [256, 1024, 4096],
        'source-forall': [128, 512, 2048],
        'source-qualified': [128, 512, 2048],
        'evidence-import': [16, 64, 128],
    }),
    'llvm': ('LLVM.hs', {
        'demand-balanced': [1024, 4096],
        'demand-left': [1024, 4096],
        'demand-right': [1024, 4096],
        'demand-alias': [64, 256],
        'capture-chain': [128, 512],
        'worker-demand-chain': [64, 256, 1024],
        'worker-demand-independent': [64, 256, 1024],
        'let-summary': [1024, 4096],
    }),
    'inference': ('Inference.hs', {
        'bounds': [256, 1024], 'bounds-dense': [256, 1024],
        'local-path': [256, 1024, 4096],
    }),
    'frontend': ('Frontend.hs', {'parse': [128, 1024, 4096], 'rows-after': [512, 4096]}),
}
FLAGS = ['-O2', '-fstatic-argument-transformation', '-fpedantic-bottoms', '-fno-state-hack']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(root):
    manifest = json.loads((root / 'shared-sources.json').read_text())
    paths = [row['path'] for row in manifest['modules']] + manifest['host_only']
    paths += ['shared-sources.json', *[str(p.relative_to(root)) for p in (root / 'runtime').glob('*.h')]]
    return {path: sha(root / path) for path in sorted(set(paths))}


def pack(fields):
    return ''.join(str(len(value)) + ':' + value for value in fields)


def independent_result(family, size):
    if family == 'metadata-bytes':
        return {'count': size, 'checksum': 1}
    if family.startswith('source-'):
        text = pack(['variable', 'λ😀\0'])
        star = pack(['star'])
        bound = pack(['bottom-kind', pack(['kind-arrow', star, star])])
        for i in range(size, 0, -1):
            if family == 'source-arrow':
                text = pack(['arrow', pack(['variable', 'a']), text])
            elif family == 'source-forall':
                text = pack(['forall', 'rigid', 'v' + str(i), bound, text])
            elif family == 'source-qualified':
                argument = pack(['variable', 'a'])
                predicate = pack(['predicate', 'Cλ', pack([argument])])
                text = pack(['qualified', pack([predicate]), text])
            else:
                raise ValueError(family)
        return {'count': len(text),
                'checksum': sum(i * ord(c) for i, c in enumerate(text, 1)) % 1000000007}
    if family in ('demand-left', 'demand-right', 'demand-balanced'):
        return {'count': size, 'checksum': size * (size + 1) * (2 * size + 1) // 6,
                'complete': True}
    if family in ('worker-demand-chain', 'worker-demand-independent'):
        return {'count': size, 'checksum': -(size * (size + 1) * (2 * size + 1) // 6),
                'complete': True}
    if family == 'demand-alias':
        return {'count': 2, 'checksum': 5, 'complete': True}
    return None


def decode(group, raw):
    if group == 'frontend':
        family, size, cpu, allocated, checksum = raw.strip().split(',')
        return {'family': family, 'size': int(size), 'cpu_seconds': float(cpu),
                'allocated_bytes': int(allocated), 'checksum': int(checksum)}
    return json.loads(raw)


def observable(row):
    return {key: value for key, value in row.items()
            if key not in ('cpu_seconds', 'allocated_bytes', 'wall_seconds')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, default=HERE.parents[2])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--group', action='append', choices=GROUPS, required=True)
    parser.add_argument('--family', action='append')
    parser.add_argument('--size', type=int, action='append')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--ghc', default='ghc')
    args = parser.parse_args()
    if args.repeats < 3 or (args.size and any(n <= 0 for n in args.size)):
        parser.error('use at least three repeats and positive sizes')
    ghc = Path(shutil.which(args.ghc) or args.ghc).resolve(strict=True)
    version = subprocess.check_output([ghc, '--numeric-version'], text=True).strip()
    if version != '9.14.1':
        raise ValueError('GHC 9.14.1 required')
    roots = {'baseline': args.baseline.resolve(strict=True), 'candidate': args.candidate.resolve(strict=True)}
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    record = {'format': 1, 'complete': False, 'scope': 'production helper CPU time on GHC; not end-to-end speed',
              'ghc': {'path': str(ghc), 'version': version, 'sha256': sha(ghc)},
              'flags': FLAGS, 'repeats': args.repeats, 'inputs': {}, 'commands': [], 'results': []}

    def save():
        temporary = out / 'results.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(out / 'results.json')

    for label, root in roots.items():
        record['inputs'][label] = {'root': str(root), 'source_pins': snapshot(root),
            'commit': subprocess.check_output(['git', '-C', root, 'rev-parse', 'HEAD'], text=True).strip()}
    save()
    for group in args.group:
        filename, families = GROUPS[group]
        probe = HERE / filename
        probe_pin = sha(probe)
        executables = {}
        for label, root in roots.items():
            build = out / (group + '-' + label)
            build.mkdir()
            manifest = json.loads((root / 'shared-sources.json').read_text())
            executable = build / 'probe'
            command = [str(ghc), '--make', '-v0', '-w', *FLAGS,
                '-rtsopts', '-with-rtsopts=-T', '-i',
                *['-i' + str(root / path) for path in manifest['source_roots']],
                '-odir', str(build), '-hidir', str(build), str(probe),
                str(root / 'host/ghc/cbits/host.c'), str(root / 'runtime/mlf_process_supervisor.c'),
                '-I' + str(root / 'runtime'), '-o', str(executable)]
            with (build / 'build.log').open('w') as log:
                subprocess.run(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            record['commands'].append({'argv': command, 'cwd': str(root),
                'log_sha256': sha(build / 'build.log'), 'executable_sha256': sha(executable),
                'probe_sha256': probe_pin})
            executables[label] = executable
            save()
        for family, defaults in families.items():
            if args.family and family not in args.family:
                continue
            for size in args.size or defaults:
                samples = {label: [] for label in roots}
                expected = independent_result(family, size)
                for repetition in range(args.repeats):
                    order = list(roots) if repetition % 2 == 0 else list(reversed(roots))
                    for label in order:
                        start = time.monotonic()
                        raw = subprocess.check_output([executables[label], family, str(size)], text=True, timeout=300)
                        row = decode(group, raw)
                        row['wall_seconds'] = time.monotonic() - start
                        if row['family'] != family or row['size'] != size:
                            raise ValueError('probe returned a different workload')
                        if expected is not None and any(row.get(k) != v for k, v in expected.items()):
                            raise ValueError(('independent oracle mismatch', family, size, row, expected))
                        samples[label].append(row)
                    if observable(samples['baseline'][-1]) != observable(samples['candidate'][-1]):
                        raise ValueError(('baseline/candidate output mismatch', family, size, samples))
                medians = {label: statistics.median(row['cpu_seconds'] for row in rows)
                           for label, rows in samples.items()}
                record['results'].append({'group': group, 'family': family, 'size': size,
                    'samples': samples, 'median_cpu_seconds': medians,
                    'baseline_over_candidate': medians['baseline'] / medians['candidate'],
                    'independent_oracle': expected,
                    'validation': 'exact output equality across all repetitions; independent oracle when recorded'})
                print(f'{family} {size}: {medians["baseline"]:.6f}s -> {medians["candidate"]:.6f}s', flush=True)
                save()
        if sha(probe) != probe_pin:
            raise ValueError('probe changed during measurement')
    for label, root in roots.items():
        if snapshot(root) != record['inputs'][label]['source_pins']:
            raise ValueError('production source changed during measurement: ' + label)
    record['complete'] = True
    save()


if __name__ == '__main__':
    main()
