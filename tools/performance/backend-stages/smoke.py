#!/usr/bin/env python3
"""Qualify the diagnostic on a fresh small main crate, never a compiler generation."""
from pathlib import Path
import argparse
import os
import sys
import run as backend


def pack(fields):
    return ''.join(str(len(value))+':'+value for value in fields)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['producer', 'producer-source', 'setup', 'output']:
        parser.add_argument('--'+option, type=Path, required=True)
    args = parser.parse_args()
    producer, source = args.producer.resolve(), args.producer_source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    H = backend.module(backend.ROOT/'tools/performance/a1-private-index/helper.py')
    record = dict(complete=False, diagnostic_qualification=True,
                  performance_samples=0, native_compiler_fixed_point=False, commands=[])
    save = lambda: H.save(output/'receipt.json', record)
    save()
    try:
        auth = H.authenticate(producer, source)
        setup = H.load(args.setup)
        H.require(setup['complete'] is True and Path(setup['producer']) == producer,
                  'fixed-dependency setup does not belong to the authenticated producer')
        fixture = backend.HERE/'Smoke.hs'
        query = output/'queries'
        query.mkdir()
        spec = output/'crate.spec'
        spec.write_text(pack(['MLF-CRATE-1', 'backend-stages/smoke', 'Main', 'false',
            pack([pack(['Main', str(fixture)])]), pack([setup['builtin']+'.mlfci']),
            str(query), setup['builtin']]))
        files = [Path(__file__).resolve(), backend.HERE/'run.py', fixture, spec,
                 args.setup.resolve(), producer/'receipt.json', Path(setup['runtime']),
                 Path(setup['clang']), *[Path(setup['builtin']+suffix)
                                       for suffix in ['.mlfci', '.mlfco']]]
        pins = {str(path): H.sha(path) for path in files}
        record.update(inputs=pins, environment={name: os.environ.get(name)
            for name in ['PATH', 'LD_LIBRARY_PATH', 'LIBRARY_PATH', 'PKG_CONFIG_PATH']})
        save()

        def run(label, argv):
            H.check_pins(pins)
            row = H.Runner(output, backend.LIMITS).run(argv, source, output/label)
            record['commands'].append(row)
            save()

        with H.SerialLock(producer.parent):
            run('source-to-checked', [producer/'bin/emlf', '--compile-crate', spec,
                                      '-o', output/'unit'])
        report = H.load(output/'unit.queries')
        H.require(report['inferred_groups'] > 0 and report['reused_groups'] == 0
                  and all(group['cached'] is False for group in report['groups']),
                  'smoke crate did not infer every target group freshly')
        for suffix in ['.mlfci', '.mlfco', '.queries']:
            path = output/('unit'+suffix)
            pins[str(path)] = H.sha(path)
        # run.py owns the same producer lock. Do not nest flock acquisition.
        run('diagnostic-runner', [sys.executable, '-B', backend.HERE/'run.py',
            '--producer', producer, '--producer-source', source,
            '--checked-interface', output/'unit.mlfci', '--output', output/'diagnostic'])
        result = H.load(output/'diagnostic/receipt.json')
        H.require(result['complete'] and result['ordinary_output_equal'],
                  'full diagnostic runner did not qualify')
        with H.SerialLock(producer.parent):
            run('native-build', [setup['clang'], '-O2', '-Wno-override-module', '-x', 'ir',
                output/'diagnostic/ordinary/stdout', '-x', 'none', setup['runtime'],
                *setup['libs'], '-lm', '-lpthread', '-ldl', '-o', output/'program'])
            run('native-check', [output/'program'])
        H.require((output/'native-check/stdout').read_bytes() == 'backend λ\n42\n'.encode(),
                  'independent small native output differs')
        H.check_pins(pins)
        H.require(H.authenticate(producer, source) == auth, 'ordinary producer changed')
        record.update(complete=True, inputs=pins, fresh_groups=report['inferred_groups'],
                      ordinary_output_equal=True, independent_native_output=True,
                      diagnostic_receipt_sha256=H.sha(output/'diagnostic/receipt.json'))
        save()
    except BaseException as error:
        record.update(complete=False, error=repr(error))
        save()
        raise
    print('PASS small-crate diagnostic and independent native output')


if __name__ == '__main__':
    main()
