#!/usr/bin/env python3
"""Build the source controls with an already qualified producer's exact flags."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import identity, select

PREFIX = 'source-query-api/'
BASE_LABELS = (
    'graph read order, red/green propagation, compiler/builtin namespace, and cycle handling',
    'source query raw reuse, evidence, protection, independent old contracts/bodies, and runtime oracle',
    *(f'source change {label} {version}' for label, count in (
        ('body', 2), ('type', 2), ('protection', 2), ('datatype', 2),
        ('scc', 3), ('scope', 3), ('scope-order', 2)) for version in range(count)),
    'actual copied-definition fallback, legacy parity, runtime result, and warm graph reuse',
    'actual Session same-process failure/retry, lock release, whole-crate publication and retained generation',
)
FORMAL_LABEL = 'cross-executable formal loading and legacy prepared-native literal compatibility'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('receipt', type=Path, nargs='?')
    parser.add_argument('output', type=Path, nargs='?')
    parser.add_argument('--framework-list', action='store_true')
    parser.add_argument('--interface', type=Path, help='CLI-produced object to load in this different executable')
    parser.add_argument('--resume-build', action='store_true',
                        help='reuse failed control-build objects; archive logs and start fresh test caches')
    args = parser.parse_args()
    available = [*BASE_LABELS, *([FORMAL_LABEL] if args.interface else [])]
    focused = select(PREFIX, available)
    selected = [focused] if focused is not None else available
    if args.framework_list:
        print(json.dumps([identity(PREFIX, label) for label in selected]))
        return
    if args.receipt is None or args.output is None:
        parser.error('receipt and output are required')
    producer = json.loads(args.receipt.read_text())
    if not producer['complete'] or producer['optimization'] != '2':
        parser.error('a complete -O2 producer is required')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=args.resume_build)
    receipt = out / 'receipt.json'
    if args.resume_build:
        if receipt.exists() and json.loads(receipt.read_text())['complete']:
            parser.error('do not overwrite completed controls')
        attempts = out / ('failed-attempt-' + str(len(list(out.glob('failed-attempt-*')))))
        attempts.mkdir()
        for name in ('build.log', 'checks.log', 'cache', 'receipt.json'):
            if (out / name).exists():
                (out / name).rename(attempts / name)
    for entry in producer['shared_inputs'].values():
        if sha(entry['path']) != entry['sha256']:
            raise ValueError('producer input changed: ' + entry['path'])
    command = next(c['argv'] for c in producer['commands'] if '-o' in c['argv'] and
                   c['argv'][c['argv'].index('-o') + 1].endswith('/bin/emlf')).copy()
    fixture = ROOT / 'tools/performance/crate-query-graph/SourceChecks.hs'
    command = [str(fixture) if value.endswith('/host/ghc/app/emlf/Main.hs') else value for value in command]
    command[command.index('-o') + 1] = str(out / 'source-checks')
    objects = out / 'objects'
    objects.mkdir(exist_ok=args.resume_build)
    old_objects = command[command.index('-odir') + 1]
    if not args.resume_build:
        # Reuse only the exact module objects authenticated by the ordinary build.
        for source in Path(old_objects).rglob('*'):
            if not source.is_file():
                continue
            relative = source.relative_to(old_objects)
            if str(relative) in ('Main.o', 'Main.hi'):
                continue
            if sha(source) != producer['object_inputs']['objects/' + str(relative)]:
                raise ValueError('producer object changed: ' + str(source))
            destination = objects / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    command[command.index('-odir') + 1] = str(objects)
    command[command.index('-hidir') + 1] = str(objects)
    command.insert(command.index('-odir'), '-i' + old_objects)
    record = dict(complete=False, selected_cases=selected, command=command,
                  producer_receipt_sha256=sha(args.receipt), fixture_sha256=sha(fixture),
                  selector_sha256=sha(ROOT / 'tools/testing/receipt_selection.py'))
    log_path = out / 'checks.log'
    try:
        with (out / 'build.log').open('w') as log:
            subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
        record['binary_sha256'] = sha(out / 'source-checks')
        with log_path.open('w') as log:
            subprocess.run([out / 'source-checks', out / 'cache', *([args.interface.resolve()] if args.interface else [])],
                           env=dict(os.environ, MLF_SOURCE_QUERY_LABEL=focused or ''), cwd=ROOT,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        actual = [line.removeprefix('PASS ') for line in log_path.read_text().splitlines() if line.startswith('PASS ')]
        if actual != selected:
            raise ValueError('completed source checks differ from selected inventory')
        record['complete'] = True
    finally:
        if log_path.is_file():
            record['checks_log_sha256'] = sha(log_path)
        temporary = receipt.with_suffix('.json.new')
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(receipt)
    print(log_path.read_text(), end='')


if __name__ == '__main__':
    main()
