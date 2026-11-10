#!/usr/bin/env python3
"""Sequential public crate commands inside ONE outer process group and deadline.

No nested Runner, start_new_session, timeout reset, target cache or resume path.
All validation here is charged to the endpoint. Stage clocks are descriptive.
"""
from pathlib import Path
import argparse
import os
import resource
import subprocess
import time
from common import H, pack, fresh, interface, HERE

BUILTIN_ID = 'mlf:builtin-shared-haskell-v1:13'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',type=Path,required=True)
    args = parser.parse_args()
    job = H.load(args.job)
    out, plan, setup = Path(job['output']), job['plan'], job['setup']
    emlf = Path(job['producer'])/'bin/emlf'
    H.require(os.environ.get('MLF_BUILD_SCOPE') == str(os.getpgrp()), 'must inherit guarded process scope')
    record = dict(complete=False, stages=[], fresh={}, artifact_pins={})
    save = lambda: H.save(out/'stages.json',record)
    save()
    artifacts = record['artifact_pins']

    def run(name,argv,stdout=None,reject=False):
        log = out/'logs'/name
        log.mkdir(parents=True,exist_ok=False)
        output, error = stdout or log/'stdout', log/'stderr'
        stage = dict(name=name,argv=[str(x) for x in argv],complete=False,
                     stdout=str(output),stderr=str(error),expected_exit_code=1 if reject else 0)
        record['stages'].append(stage)
        save()  # Keep the currently running stage if the outer guard kills us.
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        start = time.perf_counter_ns()
        with output.open('wb') as stdout_file,error.open('wb') as stderr_file:
            result = subprocess.run(stage['argv'],cwd=out,stdin=subprocess.DEVNULL,
                                    stdout=stdout_file,stderr=stderr_file)
        finished_ns = time.perf_counter_ns()
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        stage.update(exit_code=result.returncode,finished_monotonic_ns=finished_ns,
                     wall_seconds=(finished_ns-start)/1e9,
                     user_seconds=after.ru_utime-before.ru_utime,
                     system_seconds=after.ru_stime-before.ru_stime,
                     stdout_sha256=H.sha(output),stderr_sha256=H.sha(error))
        # Crashes/signals are not a valid negative control.
        valid = result.returncode == 1 if reject else result.returncode == 0
        stage['complete'] = valid
        save()
        H.require(valid, 'stage failed '+name)
        return output

    def spec_file(directory,identity,entry,modules,dependencies):
        directory.mkdir(parents=True,exist_ok=False)
        queries = directory/'queries'
        queries.mkdir()
        spec = directory/'crate.spec'
        spec.write_text(pack(['MLF-CRATE-1',identity,entry,'false',
            pack([pack([r['module'],r['source']]) for r in modules]),
            pack(list(dependencies.values())),str(queries),setup['builtin']]))
        H.require(not any(queries.iterdir()), 'target cache is not empty')
        return spec

    def link_and_build(prefix,label):
        H.check_pins(artifacts)
        llvm = out/(label+'.ll')
        run(label+'-llvm',[emlf,'--crate-to-llvm-gc',str(prefix)+'.mlfci'],llvm)
        artifacts[str(llvm)] = H.sha(llvm)
        program = out/(label+'-program')
        run(label+'-clang',[setup['clang'],'-O2','-Wno-override-module',llvm,setup['runtime'],
                            *setup['libs'],'-lm','-lpthread','-ldl','-o',program])
        record['runnable_monotonic_ns'] = record['stages'][-1]['finished_monotonic_ns']
        save()
        artifacts[str(program)] = H.sha(program)
        return program

    try:
        H.check_pins(job['pins'])
        built = {}
        for part in plan['slices']:
            H.check_pins(artifacts)
            name = part['name']
            identity = 'fresh-split/'+plan['kind']+'/'+name
            dependencies = {BUILTIN_ID: setup['builtin']+'.mlfci'}
            for dep in part['dependencies']:
                H.require(dep in built, 'dependency was not freshly built in this endpoint')
                dependencies[built[dep]['identity']] = str(built[dep]['prefix'])+'.mlfci'
            directory = out/'targets'/name
            spec = spec_file(directory,identity,part['entry'],part['modules'],dependencies)
            prefix = directory/'unit'
            run(name+'-compile',[emlf,'--compile-crate',spec,'-o',prefix])
            report = H.load(str(prefix)+'.queries')
            record['fresh'][name] = fresh(report,identity)
            for suffix in ['.mlfci','.mlfco','.queries']:
                path = Path(str(prefix)+suffix)
                H.regular(path)
                artifacts[str(path)] = H.sha(path)
            shown = run(name+'-interface',[emlf,'--show-crate',str(prefix)+'.mlfci'])
            interface(shown.read_text(),identity,[r['module'] for r in part['modules']],dependencies)
            built[name] = dict(identity=identity,prefix=prefix)
            save()
        program = link_and_build(built[plan['slices'][-1]['name']]['prefix'],'target')
        if plan['kind'] == 'compiler90':
            for name,flag,expected in [('version','--version',b'emlf 0.3.0\n'),
                    ('identity','--implementation-identity',b'MLF/shared-haskell-v1 native-MLF\n')]:
                output = run(name,[program,flag])
                H.require(output.read_bytes() == expected,'authored compiler CLI differs '+name)
            record['cli_monotonic_ns'] = time.perf_counter_ns()
            save()
            record['semantic_start_monotonic_ns'] = time.perf_counter_ns()
            # One fixed independent program, not compiler generation or differential A/B.
            output = run('native-small-program',[program,'--run','--expr',
                         'main = do { printInt 42; putStrLn "split λ" }'])
            H.require(output.read_bytes() == '42\nsplit λ\n'.encode(),
                      'native compiler independent interpreter result differs')
            H.require(not (out/'logs/native-small-program/stderr').read_bytes(),
                      'unexpected small-program diagnostic')
            run('native-small-type-error',[program,'--type','--expr','stringLength 1'],reject=True)
            diagnostic = (out/'logs/native-small-type-error/stderr').read_text()
            H.require('type constructor mismatch' in diagnostic, 'missing native type-error diagnostic')
            record['semantic_end_monotonic_ns'] = time.perf_counter_ns()
            save()
        else:
            output = run('fixture-native',[program])
            H.require(output.read_bytes() == 'split λ\n42\n42\n'.encode(),'fixture native behavior differs')
            # Independent fixture only: rejected roots use fresh dirs but the already
            # qualified fixture libraries. Never counted as fresh compiler samples.
            base = (HERE/'fixture/Main.hs').read_text()
            changes = [('private-export',base.replace('printInt answer','printInt hidden'),None,'hidden'),
                       ('type-error',base.replace('printInt answer','printInt (stringLength 1)'),None,'type constructor mismatch'),
                       ('missing-direct-dependency',base,['facade'],'Model')]
            for name,text,deps,marker in changes:
                source = out/(name+'.hs')
                source.write_text(text)
                identity = 'fresh-split/negative/'+name
                dependencies = {BUILTIN_ID:setup['builtin']+'.mlfci'}
                for dep in deps if deps is not None else ['model','facade']:
                    dependencies[built[dep]['identity']] = str(built[dep]['prefix'])+'.mlfci'
                spec = spec_file(out/'negative'/name,identity,'Main',
                                 [dict(module='Main',source=str(source))],dependencies)
                run(name,[emlf,'--compile-crate',spec,'-o',spec.parent/'unit'],reject=True)
                diagnostic = (out/'logs'/name/'stderr').read_text()
                H.require(diagnostic.strip() and (marker is None or marker in diagnostic),
                          'negative failed without expected diagnostic '+name)
                H.require(not (spec.parent/'unit.mlfci').exists(),'rejected crate emitted interface')
            # Tamper an independent copy only; preserve every valid target artifact.
            corrupt = out/'corrupt'
            corrupt.mkdir()
            prefix = built['entry']['prefix']
            (corrupt/'unit.mlfci').write_bytes(Path(str(prefix)+'.mlfci').read_bytes())
            raw = bytearray(Path(str(prefix)+'.mlfco').read_bytes())
            (corrupt/'unit.mlfco').write_bytes(raw)
            intact = run('relocated-intact-object',[emlf,'--crate-to-llvm-gc',corrupt/'unit.mlfci'])
            H.require(intact.read_bytes() == (out/'target.ll').read_bytes(),
                      'intact copied artifact failed ordinary output equivalence')
            raw[-1] ^= 1
            (corrupt/'unit.mlfco').write_bytes(raw)
            run('corrupt-object',[emlf,'--crate-to-llvm-gc',corrupt/'unit.mlfci'],reject=True)
            diagnostic = (out/'logs/corrupt-object/stderr').read_text()
            H.require('checksum mismatch' in diagnostic or 'SHA mismatch' in diagnostic,
                      'expected corruption-specific diagnostic')
        H.check_pins(artifacts)
        H.check_pins(job['pins'])
        record['complete'] = True
        save()
    except BaseException as error:
        record['error'] = repr(error)
        save()
        raise

if __name__ == '__main__':
    main()
