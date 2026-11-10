#!/usr/bin/env python3
"""One guarded endpoint, not ten reset budgets. No resume and no generation test."""
from pathlib import Path
import argparse
import os
import sys
from common import HERE, ROOT, HELPER, H, LIMITS, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ['plan','setup','producer','producer-source','output']:
        parser.add_argument('--'+flag, type=Path, required=True)
    args = parser.parse_args()
    out, producer, source = args.output.resolve(), args.producer.resolve(), args.producer_source.resolve()
    out.mkdir(parents=True,exist_ok=False)  # A failed directory can never be resumed.
    record = dict(complete=False, strategy='fresh-split-v1', performance_samples=0,
                  original_single_crate_baseline_unchanged=True,
                  native_generational_test=False, commands=[])
    save = lambda: H.save(out/'receipt.json',record)
    save()
    try:
        forbidden = ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']
        record['forbidden_environment_present'] = {name: name in os.environ for name in forbidden}
        save()
        H.require(not any(record['forbidden_environment_present'].values()),
                  'query diagnostic/audit/failpoint environment must be absent')
        with H.SerialLock(producer.parent):
            auth = H.authenticate(producer,source)
            setup, plan = H.load(args.setup), H.load(args.plan)
            H.require(setup['complete'] is True and Path(setup['producer']).resolve() == producer
                      and Path(setup['source']).resolve() == source, 'same authenticated fixed setup')
            H.require(setup['identity']['producer_emlf_sha256'] == H.sha(producer/'bin/emlf')
                      and setup['identity']['producer_receipt_sha256'] == H.sha(producer/'receipt.json'),
                      'fixed setup producer identity differs')
            if plan['kind'] == 'compiler90':
                H.require(Path(plan['source']) == source, 'same original source checkout required')
            pins = validate(plan)
            pins.update(plan['static_pins'])
            for suffix in ['.mlfci','.mlfco']:
                path = setup['builtin']+suffix
                H.require(H.sha(path) == setup['builtin_record'][path], 'original fixed builtin differs')
                pins[path] = H.sha(path)
            paths = [args.plan.resolve(), args.setup.resolve(), producer/'receipt.json', producer/'bin/emlf',
                     Path(setup['runtime']), Path(setup['clang']).resolve(), Path(sys.executable).resolve(),
                     HERE/'run.py', HERE/'worker.py', HERE/'common.py', HELPER,
                     ROOT/'tools/performance/process-spawn/with_scope.py']
            if plan['kind'] == 'fixture':
                paths += list((HERE/'fixture').glob('*.hs'))
            pins.update({str(path): H.sha(path) for path in paths})
            H.check_pins(pins)
            job = dict(plan=plan, setup=setup, producer=str(producer), output=str(out), pins=pins)
            H.save(out/'job.json',job)
            pins[str(out/'job.json')] = H.sha(out/'job.json')
            record.update(kind=plan['kind'], inputs=pins, limits=LIMITS,
                          environment={key: os.environ.get(key) for key in
                                       ['PATH','LD_LIBRARY_PATH','LIBRARY_PATH','PKG_CONFIG_PATH']},
                          boundary='One Popen-through-wait4 endpoint: all fresh source slices, '
                                   'dependency/pin validation, whole-program LLVM, Clang, CLI. '
                                   'Only static freeze, producer authentication and fixed setup excluded.')
            save()
            argv = [sys.executable,'-B',ROOT/'tools/performance/process-spawn/with_scope.py',
                    sys.executable,'-B',HERE/'worker.py','--job',out/'job.json']
            try:
                command = H.Runner(out,LIMITS).run(argv,source,out/'command',timed=plan['kind']=='compiler90')
            finally:
                if (out/'command/command.json').exists():
                    record['commands'] = [H.load(out/'command/command.json')]
                    save()
            stages = H.load(out/'stages.json')
            H.require(stages['complete'], 'incomplete split endpoint')
            H.check_pins(pins)
            H.require(H.authenticate(producer,source) == auth, 'producer changed')
            if plan['kind'] == 'compiler90':
                begin = command['started_monotonic_ns']
                end = command['completed_monotonic_ns']
                H.require(begin <= stages['runnable_monotonic_ns'] <= stages['cli_monotonic_ns']
                          <= stages['semantic_start_monotonic_ns'] <= stages['semantic_end_monotonic_ns']
                          <= end, 'endpoint timestamps out of order')
                record.update(source_to_runnable_seconds=(stages['runnable_monotonic_ns']-begin)/1e9,
                              source_to_cli_seconds=(stages['cli_monotonic_ns']-begin)/1e9,
                              semantic_validation_seconds=(stages['semantic_end_monotonic_ns']-
                                                           stages['semantic_start_monotonic_ns'])/1e9,
                              whole_qualification_scope_seconds=command['wall_seconds'])
            record.update(complete=True,endpoint_wall_seconds=command['wall_seconds'],
                          stages_sha256=H.sha(out/'stages.json'),
                          artifact_pins=stages['artifact_pins'], fresh=stages['fresh'],
                          scope='small independent semantic controls' if plan['kind']=='fixture'
                                else 'compiler build, CLI and one small interpreted program/type rejection only; not complete compiler semantics')
            save()
    except BaseException as error:
        record['error'] = repr(error)
        save()
        raise
    print('PASS',plan['kind'],record['endpoint_wall_seconds'])

if __name__ == '__main__':
    main()
