#!/usr/bin/env python3
"""Compare fresh builds of the runnable emlf compiler, including native linking."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/testing'))
sys.path.insert(0, str(ROOT / 'tools/performance/full-compiler'))
import events
from qualify import DEFAULT_WALL_SECONDS

CASE_ID = 'full-compiler/native-comparison'
ORDER = ('mlf-native', 'ghc-native', 'ghc-native', 'mlf-native')


class EndpointFailure(Exception):
    def __init__(self, returncode, reason, receipt):
        super().__init__(f'{receipt.parent.name}: {reason or "endpoint failed"} ({receipt})')
        self.returncode = returncode
        self.status = 'timeout' if reason == 'wall limit' else 'fail'


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_pins(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, f'frozen input changed: {path}')


def compare(args):
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    qualifier = ROOT / 'tools/performance/full-compiler/qualify.py'
    worker = qualifier.with_name('worker.py')
    oracle = Path(__file__).with_name('check_native.py')
    workload = load(args.workload)
    setup = load(args.setup)
    source = args.producer_source.resolve()
    producer_receipt = args.producer / 'receipt.json'
    require(setup['complete'] and Path(setup['source']).resolve() == source
            and Path(setup['producer']).resolve() == args.producer.resolve()
            and setup['identity']['producer_receipt_sha256'] == sha(producer_receipt),
            'fixed setup must match the selected producer and source')
    inputs = [Path(__file__), qualifier, worker, oracle, args.workload, args.setup,
              producer_receipt, source / 'shared-sources.json',
              source / 'host/ghc/app/emlf/Main.hs', source / 'host/ghc/MLF/Host/Base.hs',
              Path(setup['runtime']), Path(setup['clang']),
              ROOT / 'tools/performance/a1-private-index/helper.py',
              ROOT / 'tools/performance/process-spawn/with_scope.py',
              *(Path(setup['builtin'] + suffix) for suffix in ('.mlfci', '.mlfco')),
              *(path for path in args.setup.parent.rglob('*') if path.is_file())]
    if args.reference_prefix:
        inputs.extend(Path(str(args.reference_prefix) + suffix)
                      for suffix in ('.mlfci', '.mlfco', '.queries'))
    pins = {**workload['input_files'], **{str(path.resolve()): sha(path) for path in inputs}}
    for path in (qualifier, worker, oracle, Path(__file__)):
        shutil.copy2(path, out / path.name)
    plan = {
        'order': ORDER,
        'purpose': 'descriptive native-endpoint comparison',
        'primary': 'geometric MLF/GHC wall ratio over two adjacent pairs',
        'qualification_metadata': 'Endpoint qualifications keep performance_samples=0. '
                                  'This plan designates four qualified endpoint runs as measurements.',
        'replacement_or_extension': False,
        'source_label': workload['baseline_ref'],
        'shared_modules': workload['module_count'],
        'reference_prefix': str(args.reference_prefix.resolve()) if args.reference_prefix else None,
        'ordinary_flags': 'GHC 9.14.1 -O2 -j1 and Clang -O2 serial',
        'wall_seconds_per_endpoint': args.wall_seconds,
        'inputs': pins,
    }
    save(out / 'plan.json', plan)
    receipt = out / 'receipt.json'
    record = {'complete': False, 'plan_sha256': sha(out / 'plan.json'), 'runs': [], 'oracles': []}
    save(receipt, record)
    first_mlf = None
    for position, lane in enumerate(ORDER):
        check_pins(pins)
        dest = out / f'{position}-{lane}'
        cmd = [sys.executable, '-B', qualifier, '--workload', args.workload.resolve(),
               '--setup', args.setup.resolve(), '--producer', args.producer.resolve(),
               '--producer-source', source, '--lane', lane, '--output', dest,
               '--wall-seconds', str(args.wall_seconds)]
        if lane == 'mlf-native' and args.reference_prefix:
            cmd.extend(('--reference-prefix', args.reference_prefix.resolve()))
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True)
        (out / f'{position}.stdout').write_bytes(result.stdout)
        (out / f'{position}.stderr').write_bytes(result.stderr)
        run_receipt = dest / 'receipt.json'
        row = {'position': position, 'lane': lane, 'exit_code': result.returncode}
        if run_receipt.is_file():
            row.update(receipt=str(run_receipt), receipt_sha256=sha(run_receipt))
        command_receipt = dest / 'command/command.json'
        reason = load(command_receipt).get('reason') if command_receipt.is_file() else None
        if reason:
            row['guard'] = reason
        record['runs'].append(row)
        save(receipt, record)
        if result.returncode:
            raise EndpointFailure(result.returncode, reason, run_receipt)
        qualified = load(run_receipt)
        require(qualified['complete'], f'incomplete endpoint: {dest}')
        row.update(wall_seconds=qualified['endpoint_wall_seconds'], stages=qualified['stages'],
                   peak_rss_bytes=qualified['commands'][0]['sampled_process_tree_peak_rss_bytes'])
        if lane == 'mlf-native':
            checked = tuple(qualified['checked_artifacts'][str(dest / ('unit' + suffix))]
                            for suffix in ('.mlfci', '.mlfco'))
            fingerprint = (checked, qualified['groups'])
            if first_mlf is None:
                first_mlf = fingerprint
            else:
                require(fingerprint == first_mlf, 'fresh MLF runs produced different checked artifacts or groups')
            row.update(fresh_groups=qualified['fresh'], reused_groups=qualified['reused'])
        else:
            row.update(fresh_shared_modules=qualified['fresh_shared_modules'],
                       fresh_host_wrappers=qualified['fresh_host_wrapper'])
        save(receipt, record)
        print(f'PASS {position} {lane} {row["wall_seconds"]:.3f}s', flush=True)

    # The authored behavioral oracle runs on both executable pairs outside the
    # timed window. An optional independent checked reference remains a raw gate.
    ratios = []
    for pair_number, pair in enumerate((record['runs'][:2], record['runs'][2:]), start=1):
        runs = {row['lane']: row for row in pair}
        programs = {lane: out / f'{row["position"]}-{lane}' / 'program' for lane, row in runs.items()}
        oracle_out = out / f'oracle-{pair_number}'
        result = subprocess.run([sys.executable, '-B', oracle, '--mlf', programs['mlf-native'],
                                 '--ghc', programs['ghc-native'], '--setup', args.setup.resolve(),
                                 '--output', oracle_out], cwd=ROOT)
        oracle_receipt = oracle_out / 'receipt.json'
        record['oracles'].append({'exit_code': result.returncode, 'receipt': str(oracle_receipt)})
        save(receipt, record)
        result.check_returncode()
        require(load(oracle_receipt)['complete'], f'incomplete behavioral oracle: {oracle_out}')
        ratios.append(runs['mlf-native']['wall_seconds'] / runs['ghc-native']['wall_seconds'])
    check_pins(pins)
    record.update(complete=True, pair_ratios=ratios, geometric_ratio=statistics.geometric_mean(ratios),
                  geometric_seconds={lane: statistics.geometric_mean(row['wall_seconds'] for row in record['runs']
                                                                    if row['lane'] == lane)
                                     for lane in ('mlf-native', 'ghc-native')})
    save(receipt, record)
    print(f'PASS closed native comparison {record["geometric_ratio"]:.3f}x', flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('producer', 'workload', 'setup', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--producer-source', type=Path, default=ROOT,
                        help='checkout used to build the ordinary GHC-hosted producer')
    parser.add_argument('--reference-prefix', type=Path,
                        help='independent checked artifacts and group inventory for the exact workload')
    parser.add_argument('--wall-seconds', type=int, default=DEFAULT_WALL_SECONDS,
                        help='Wall-time limit per endpoint (default: %(default)s seconds).')
    args = parser.parse_args()
    if args.wall_seconds < 1:
        parser.error('--wall-seconds must be positive')
    events.start(CASE_ID)
    try:
        result = compare(args)
    except (OSError, ValueError, KeyError, EndpointFailure, subprocess.CalledProcessError) as error:
        status = error.status if isinstance(error, EndpointFailure) else 'fail'
        events.result(CASE_ID, status, error=str(error), output=str(args.output.resolve()))
        print(f'full compiler comparison: {error}', file=sys.stderr)
        if isinstance(error, (EndpointFailure, subprocess.CalledProcessError)):
            return error.returncode if error.returncode > 0 else 128 - error.returncode
        return 1
    events.result(CASE_ID, 'pass', receipt=str(args.output.resolve() / 'receipt.json'),
                  geometric_ratio=result['geometric_ratio'], geometric_seconds=result['geometric_seconds'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
