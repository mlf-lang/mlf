#!/usr/bin/env python3
"""One fresh build. Parent retains process-group guards and exact-child timing."""
from pathlib import Path
import argparse
import json
import resource
import subprocess
import time


ORDINARY_CLANG_FLAGS = ('-O2', '-Wno-override-module')


CACHED_ENDPOINT = 'crate-bootstrap-cached-production-v1'
PRODUCTION_ENDPOINTS = ('crate-bootstrap-production-v1', CACHED_ENDPOINT)


def pack(values):
    return ''.join(str(len(x))+':'+x for x in values)


def mlf_commands(endpoint, emlf, spec, out):
    if endpoint == 'crate-bootstrap-v1' or endpoint in PRODUCTION_ENDPOINTS:
        emit = [emlf, '--crate-to-llvm-gc', out/'unit.mlfci']
        if endpoint == CACHED_ENDPOINT:
            emit += ['--cache', out/'codegen-cache', '--query-report', out/'codegen.json']
        return [('source-to-checked', [emlf, '--compile-crate', spec, '-o', out/'unit'], None),
                ('checked-to-llvm', emit, out/'unit.ll')]
    if endpoint == 'crate-fused-v1':
        return [('source-to-llvm', [emlf, '--compile-crate-to-llvm-gc', spec, '-o', out/'unit'], out/'unit.ll')]
    if endpoint == 'crate-plan-v1':
        return [('source-to-llvm', [emlf, '--compile-crate-plan', out/'build.plan', spec, '-o', out/'unit'],
                 out/'unit.ll')]
    raise ValueError('unsupported compile endpoint: ' + endpoint)


def mlf_stage_names(endpoint):
    return [stage for stage, _, _ in mlf_commands(endpoint, Path('/emlf'), Path('/spec'), Path('/out'))] + ['llvm-to-executable']


def dependencies(case):
    return case.get('dependencies', [case['dependency']] if 'dependency' in case else [])


def dependency_folder(build, libraries, index):
    return build/('dependency' if len(libraries)==1 else f'dependency-{index}')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--lane',choices=['ghc','mlf','reference','module'],required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); plan=json.loads(args.plan.read_text()); setup=plan['setup']
    case=next(c for c in plan['cases'] if c['id']==args.case)
    out=args.out.resolve(); out.mkdir(parents=True,exist_ok=False)
    stages=[]
    def save(complete=False):
        (out/'stages.json').write_text(json.dumps({'complete':complete,'stages':stages},indent=2)+'\n')
    def run(name,argv,stdout=None):
        stdout=stdout or out/(name+'.stdout'); stderr=out/(name+'.stderr')
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        start=time.perf_counter_ns()
        with stdout.open('wb') as output,stderr.open('wb') as error:
            result=subprocess.run([str(a) for a in argv],cwd=out,stdout=output,stderr=error)
        wall=(time.perf_counter_ns()-start)/1e9
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        stages.append({'name':name,'argv':[str(a) for a in argv], 'wall_seconds':wall,
                       'user_seconds':after.ru_utime-before.ru_utime,'system_seconds':after.ru_stime-before.ru_stime,
                       'exit_code':result.returncode,'stdout':str(stdout),'stderr':str(stderr)})
        save()
        if result.returncode:
            raise SystemExit(result.returncode)
    libraries = dependencies(case)
    if args.lane=='ghc':
        includes = ['-i'+path for path in sorted({str(Path(lib['source']).parent) for lib in libraries})]
        run('source-to-executable',[setup['ghc'],'--make','-j1','-O2','-fforce-recomp',
            '-package-env','-','-clear-package-db','-global-package-db','-package-db',setup['package_db'],
            '-no-user-package-db','-hide-all-packages','-package','base','-package','mlf-shape-primitives',
            '-i',*includes,'-odir',out,'-hidir',out,case['source'],'-o',out/'program'])
    else:
        producer = plan['compiler_reference']['producer'] if args.lane == 'reference' else setup['producer']
        emlf=Path(producer)/'bin/emlf'
        if args.lane in ('mlf', 'reference'):
            query=out/'queries'; query.mkdir()
            spec=out/'crate.spec'
            endpoint = plan.get('benchmark', {}).get('endpoint', {}).get('id', 'crate-bootstrap-v1')
            imports = [setup['builtin']+'.mlfci']
            entries = []
            if libraries and endpoint != 'crate-plan-v1':
                raise ValueError('cold dependency families require crate-plan-v1')
            compiled = []
            for index, lib in enumerate(libraries):
                dependency = dependency_folder(out, libraries, index)
                dependency.mkdir()
                dep_query = dependency/'queries'
                dep_query.mkdir()
                dep_spec = dependency/'crate.spec'
                dep_spec.write_text(pack(['MLF-CRATE-1','compiler-shapes/'+case['id']+'/'+dependency.name,'',
                    'false',pack([pack([lib['module'],lib['source']])]),pack(imports),
                    str(dep_query),setup['builtin']]))
                compiled.append(str(dependency/'unit.mlfci'))
                imports = compiled[-1:]
                entries.append(pack([str(dep_spec),str(dependency/'unit')]))
            if compiled:
                imports = compiled
            if endpoint == 'crate-plan-v1':
                (out/'build.plan').write_text(pack(['MLF-CRATE-PLAN-1',pack(entries)]))
            spec.write_text(pack(['MLF-CRATE-1','compiler-shapes/'+case['id'],'Main','false',
                pack([pack(['Main',case['source']])]),pack(imports),str(query),setup['builtin']]))
            for name, argv, target in mlf_commands(endpoint, emlf, spec, out):
                run(name, argv, target)
        else:
            run('module-source-to-llvm',[emlf,'--emit-llvm-gc',case['source']],out/'unit.ll')
        flags = ORDINARY_CLANG_FLAGS
        if args.lane in ('mlf', 'reference') and endpoint in PRODUCTION_ENDPOINTS:
            flags = [*flags, *plan['native_target_policy'][args.lane]['flags']]
        run('llvm-to-executable',[setup['clang'],*flags,out/'unit.ll',
            setup['runtime'],*setup['libs'],'-lm','-lpthread','-ldl','-o',out/'program'])
    save(True)


if __name__=='__main__':
    main()
