#!/usr/bin/env python3
"""One fresh build. Parent retains process-group guards and exact-child timing."""
from pathlib import Path
import argparse
import json
import resource
import subprocess
import time


def pack(values):
    return ''.join(str(len(x))+':'+x for x in values)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--case',required=True)
    parser.add_argument('--lane',choices=['ghc','mlf','module'],required=True)
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
    if args.lane=='ghc':
        run('source-to-executable',[setup['ghc'],'--make','-j1','-O2','-fforce-recomp',
            '-package-env','-','-clear-package-db','-global-package-db','-package-db',setup['package_db'],
            '-no-user-package-db','-hide-all-packages','-package','base','-package','mlf-shape-primitives',
            '-i','-odir',out,'-hidir',out,case['source'],'-o',out/'program'])
    else:
        emlf=Path(setup['producer'])/'bin/emlf'
        if args.lane=='mlf':
            query=out/'queries'; query.mkdir()
            spec=out/'crate.spec'
            spec.write_text(pack(['MLF-CRATE-1','compiler-shapes/'+case['id'],'Main','false',
                pack([pack(['Main',case['source']])]),pack([setup['builtin']+'.mlfci']),str(query),setup['builtin']]))
            run('source-to-checked',[emlf,'--compile-crate',spec,'-o',out/'unit'])
            run('checked-to-llvm',[emlf,'--crate-to-llvm-gc',out/'unit.mlfci'],out/'unit.ll')
        else:
            run('module-source-to-llvm',[emlf,'--emit-llvm-gc',case['source']],out/'unit.ll')
        run('llvm-to-executable',[setup['clang'],'-O2','-Wno-override-module',out/'unit.ll',
            setup['runtime'],*setup['libs'],'-lm','-lpthread','-ldl','-o',out/'program'])
    save(True)


if __name__=='__main__':
    main()
