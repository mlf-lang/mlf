#!/usr/bin/env python3
"""Run finite P1-P3 controls on the current authenticated O2 producer, not a benchmark."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    producer = args.producer.resolve(strict=True)
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(producer) or producer.is_relative_to(out) or ROOT.is_relative_to(out):
        parser.error('output must be fresh and separate from the producer/source')
    out.mkdir(parents=True)
    record = {'format': 'integrated-crate-controls-v1', 'complete': False,
              'performance_measured': False, 'commands': [],
              'producer_receipt_sha256': sha(producer / 'receipt.json')}

    def save():
        (out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    save()
    try:
        for name, script in [('p1', 'run_selector_differential.py'),
                             ('p2', 'run_fingerprint_differential.py'),
                             ('p3', 'run_controls.py')]:
            runner = HERE / name / script
            command = [sys.executable, '-B', str(runner), '--source-root', str(ROOT),
                       '--build-receipt', str(producer / 'receipt.json'), '--output', str(out / name)]
            if name == 'p3':
                command.append('--serial-slot-granted')
            item = {'name': name, 'argv': command, 'runner_sha256': sha(runner)}
            record['commands'].append(item)
            save()
            with (out / (name + '.stdout')).open('wb') as stdout, (out / (name + '.stderr')).open('wb') as stderr:
                process = subprocess.Popen(command, cwd=ROOT, stdout=stdout, stderr=stderr,
                                           stdin=subprocess.DEVNULL, start_new_session=True)
                try:
                    code = process.wait(timeout=1200)
                except BaseException:
                    for sig in [signal.SIGTERM, signal.SIGKILL]:
                        try:
                            os.killpg(process.pid, sig)
                        except ProcessLookupError:
                            pass
                        try:
                            process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            pass
                    raise
            item['exit_code'] = code
            save()
            if code != 0:
                raise RuntimeError(name + ' controls failed; retain and inspect logs')
            receipt = out / name / 'receipt.json'
            result = json.loads(receipt.read_text())
            if result.get('complete') is not True:
                raise ValueError(name + ' incomplete control receipt')
            item['receipt_sha256'] = sha(receipt)
        record['complete'] = True
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        save()
    print('PASS P1/P2/P3 finite controls: 154072 / 2503 / 922; no speed claim')


if __name__ == '__main__':
    main()
