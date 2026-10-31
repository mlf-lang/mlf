#!/usr/bin/env python3
"""Check the current registered A1 producer; never select a historical benchmark ref."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    producer, out = args.producer.resolve(strict=True), args.output.resolve()
    require(not out.exists() and not out.is_relative_to(producer) and
            not producer.is_relative_to(out) and not ROOT.is_relative_to(out),
            'fresh output separate from producer/source required')
    auth_path = ROOT / 'tools/shared/test_direct.py'
    auth = types.ModuleType('integrated_a1_authentication')
    auth.__file__ = str(auth_path)
    exec(compile(auth_path.read_bytes(), str(auth_path), 'exec'), auth.__dict__)
    before = auth.authenticate_build(producer / 'receipt.json', producer / 'bin', root=ROOT)
    require(before['optimization'] == '2', 'current complete O2 producer required')
    out.mkdir(parents=True)
    record = {'format': 'integrated-a1-controls-v2', 'complete': False,
              'historical_ref_selected': False, 'performance_measured': False,
              'optimization_accepted': False, 'native_bootstrap_executed': False,
              'producer_receipt_sha256': sha(producer / 'receipt.json'),
              'runner_sha256': sha(__file__), 'commands': []}

    def save():
        (out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    def run(label, command):
        item = {'label': label, 'argv': list(map(str, command))}
        record['commands'].append(item)
        save()
        with (out / (label + '.stdout')).open('wb') as stdout, (out / (label + '.stderr')).open('wb') as stderr:
            child = subprocess.Popen(item['argv'], cwd=ROOT, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                code = child.wait(timeout=1200)
            except BaseException:
                for sig in [signal.SIGTERM, signal.SIGKILL]:
                    try:
                        os.killpg(child.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                raise
        item.update(exit_code=code, stdout_sha256=sha(out / (label + '.stdout')),
                    stderr_sha256=sha(out / (label + '.stderr')))
        save()
        require(code == 0, label + ' failed; retain and inspect logs')

    save()
    try:
        # The ordinary crate entry creates/checks a fresh canonical builtin.
        # No private export or preexisting target/query cache is substituted.
        fixture = out / 'Fixture.emlf'
        fixture.write_text('module Fixture where\nvalue = 42\n')
        spec, builtin, target = out / 'fixture.spec', out / 'builtin', out / 'fixture'
        queries = out / 'queries'
        spec.write_text(pack(['MLF-CRATE-1', 'a1-integrated-controls/fixture', '', 'false',
                              pack([pack(['Fixture', str(fixture)])]), '', str(queries), str(builtin)]))
        pins = {str(p): sha(p) for p in [Path(__file__), auth_path, fixture, spec,
                                        HERE / 'run_current_controls.py', producer / 'receipt.json']}
        run('prepare-builtin', [producer / 'bin/emlf', '--compile-crate', spec, '-o', target])
        # Hash only for immutability. The current control runner must admit the
        # actual decoded pair against the committed canonical RawPrelude literal;
        # historical byte hashes remain exclusive to run_controls.py.
        for suffix in ['.mlfci', '.mlfco']:
            path = Path(str(builtin) + suffix)
            pins[str(path)] = sha(path)
        report = json.loads(Path(str(target) + '.queries').read_text())
        require(report['inferred_groups'] == 1 and report['reused_groups'] == 0 and
                len(report['groups']) == 1 and report['groups'][0]['cached'] is False,
                'one genuinely fresh fixture source group required')
        run('controls', [sys.executable, '-B', HERE / 'run_current_controls.py', '--source-root', ROOT,
                         '--producer', producer, '--builtin-prefix', builtin, '--output', out / 'controls'])
        result = json.loads((out / 'controls/receipt.json').read_text())
        require(result.get('complete') is True and result.get('all_controls_passed') is True and
                result.get('format') == 'current-a1-controls-v1' and
                result.get('builtin_controls_passed') is True and
                result.get('builtin_malformed_rejections') == 7 and
                result.get('historical_builtin_identity_claimed') is False and
                result.get('session_groups_passed') == 6 and result.get('finite_trace_cases') == 28 and
                result.get('admission_controls_passed') is True and len(result.get('file_cases', [])) == 9 and
                result.get('negative_cases_passed') == 4, 'complete exact finite A1 gate required')
        after = auth.authenticate_build(producer / 'receipt.json', producer / 'bin', root=ROOT)
        require(before == after, 'producer identity changed during integrated controls')
        require(all(sha(path) == digest for path, digest in pins.items()), 'gate input changed')
        record.update(complete=True, immutable_inputs_verified_after=True,
                      controls_receipt_sha256=sha(out / 'controls/receipt.json'),
                      shared_sources={name: row['sha256'] for name, row in before['shared_inputs'].items()})
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        save()
    print('PASS integrated A1 controls: current authenticated producer; no historical timing claim')


if __name__ == '__main__':
    main()
