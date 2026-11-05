#!/usr/bin/env python3
"""Serial entry point for the portable, finite W1 qualification inventory."""
import json
import subprocess
import sys
import support as common


def main():
    args = common.arguments()
    if args.output.exists():
        raise ValueError('fresh output directory required; never replace failed evidence')
    common.check_pair(args)
    args.output.mkdir(parents=True)
    receipt = args.output / 'receipt.json'
    record = {'complete': False, 'performance_measured': False, 'native_bootstrap_executed': False,
              'full_async_CI_executed': False, 'inventory_sha256': common.sha(common.HERE / 'CONTROL-INVENTORY.json'),
              'inputs': common.input_pins(), 'steps': []}
    def save():
        receipt.write_text(json.dumps(record, indent=2) + '\n')
    save()
    try:
        for script, directory in [('build_controls.py', 'build'), ('real_controls.py', 'transport'),
                                  ('fault_controls.py', 'faults')]:
            common.check_pair(args)
            argv = [sys.executable, '-B', str(common.HERE / script), '--producer', str(args.producer),
                    '--baseline-root', str(args.baseline_root), '--baseline-producer', str(args.baseline_producer),
                    '--output', str(args.output)]
            step = {'script': script, 'argv': argv, 'complete': False}
            record['steps'].append(step)
            save()
            with (args.output / (directory + '.stdout')).open('wb') as stdout, \
                 (args.output / (directory + '.stderr')).open('wb') as stderr:
                result = subprocess.run(argv, env=common.env(), cwd=common.ROOT, stdout=stdout, stderr=stderr)
            step['exit_code'] = result.returncode
            save()
            if result.returncode:
                raise RuntimeError(script + ' failed; retain this output, do not replace it')
            path = args.output / directory / 'receipt.json'
            child = json.loads(path.read_text())
            if child.get('complete') is not True:
                raise ValueError('incomplete stage receipt: ' + directory)
            step.update(complete=True, receipt=str(path), receipt_sha256=common.sha(path))
            save()
        common.check_pair(args)
        transport = json.loads((args.output / 'transport/receipt.json').read_text())
        faults = json.loads((args.output / 'faults/receipt.json').read_text())
        build = json.loads((args.output / 'build/receipt.json').read_text())
        if not (transport['case_count'] == 20 and transport['execution_count'] == 40 and
                faults['fault_cases'] == 20 and faults['real_descendant_cleanup_cases'] == 4 and
                faults['missing_header_constant_fallback_passed'] and faults['no_new_glibc_pidfd_symbol'] and
                build['actual_GHC_eligible_fastpath_verified'] and build['only_Main_recompiled'] and
                build['all_Haskell_dependency_objects_unchanged']):
            raise ValueError('finite inventory incomplete')
        record.update(complete=True, transport_cases=20, transport_executions=40, fault_cases=20,
                      real_descendant_cleanup_cases=4, actual_GHC_fastpath_verified=True,
                      ordinary_benchmark_separate=True)
    except BaseException as error:
        record['error'] = repr(error)
        raise
    finally:
        save()
    print('PASS finite W1 controls; this is not an ordinary performance sample')


if __name__ == '__main__':
    main()
