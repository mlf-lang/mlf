#!/usr/bin/env python3
"""One fresh compiler build; outer exact-child runner owns all resource guards."""
from pathlib import Path
import argparse,json,resource,subprocess,time


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job',type=Path,required=True)
    a=p.parse_args();job=json.loads(a.job.read_text());out=Path(job['output']);setup=job['setup'];lane=job['lane'];stages=[]
    def save(complete=False):
        (out/'stages.json').write_text(json.dumps({'complete':complete,'lane':lane,'stages':stages},indent=2)+'\n')
    def run(name,argv,stdout=None):
        stdout=stdout or out/(name+'.stdout');stderr=out/(name+'.stderr');before=resource.getrusage(resource.RUSAGE_CHILDREN);start=time.perf_counter_ns()
        with stdout.open('wb') as output,stderr.open('wb') as error:
            result=subprocess.run([str(x) for x in argv],cwd=out,stdout=output,stderr=error)
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        stages.append({'name':name,'argv':[str(x) for x in argv],'exit_code':result.returncode,'wall_seconds':(time.perf_counter_ns()-start)/1e9,'user_seconds':after.ru_utime-before.ru_utime,'system_seconds':after.ru_stime-before.ru_stime,'stdout':str(stdout),'stderr':str(stderr)});save()
        if result.returncode:raise SystemExit(result.returncode)
    if lane.startswith('ghc-'):
        flags=['--make','-j1','-O2','-fforce-recomp','-fpedantic-bottoms','-fno-state-hack','-v',
            '-package-env','-','-clear-package-db','-global-package-db','-package-db',setup['package_db'],
            '-no-user-package-db','-hide-all-packages','-package','base','-package','mlf-shape-primitives','-i']
        flags+=['-i'+x for x in job['source_roots']]+['-odir',str(out/'objects'),'-hidir',str(out/'objects')]
        if lane=='ghc-check':flags+=['-fno-code','-fwrite-interface','-no-link']
        elif lane=='ghc-objects':flags+=['-no-link']
        elif lane=='ghc-native':flags+=['-rtsopts=ignoreAll','-o',str(out/'program')]
        else:raise ValueError('unknown GHC lane')
        run('source-to-'+lane,[setup['ghc'],*flags,job['wrapper']])
    else:
        emlf=Path(job['producer'])/'bin/emlf'
        if lane in ['mlf-checked','mlf-native']:
            run('source-to-checked',[emlf,'--compile-crate',out/'crate.spec','-o',out/'unit'])
            prefix=out/'unit'
        else:prefix=Path(job['checked_prefix'])
        if lane in ['mlf-llvm','mlf-native']:
            run('checked-to-llvm',[emlf,'--crate-to-llvm-gc',str(prefix)+'.mlfci'],out/'unit.ll')
        if lane=='mlf-native':
            run('llvm-to-executable',[setup['clang'],'-O2','-Wno-override-module',out/'unit.ll',setup['runtime'],*setup['libs'],'-lm','-lpthread','-ldl','-o',out/'program'])
        elif lane not in ['mlf-checked','mlf-llvm']:raise ValueError('unknown MLF lane')
    save(True)


if __name__=='__main__':main()
