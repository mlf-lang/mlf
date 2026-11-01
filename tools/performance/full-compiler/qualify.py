#!/usr/bin/env python3
"""Frozen complete emlf closure, exact-child guard and explicit endpoint audit."""
from pathlib import Path
import argparse,inspect,json,re,sys,time,types
ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent


def pack(xs):return ''.join(str(len(x))+':'+x for x in xs)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workload',type=Path,required=True);p.add_argument('--setup',type=Path,required=True)
    p.add_argument('--producer',type=Path,required=True);p.add_argument('--producer-source',type=Path,required=True)
    p.add_argument('--lane',choices=['mlf-checked','mlf-llvm','mlf-native','ghc-check','ghc-objects','ghc-native'],required=True)
    p.add_argument('--checked-prefix',type=Path);p.add_argument('--reference-prefix',type=Path)
    p.add_argument('--audit-guard',action='store_true',help='Log existing guard kill attempts; resource limits and kill behavior are unchanged.')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();w=json.loads(a.workload.read_text());setup=json.loads(a.setup.read_text());out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('guard');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,'host_available_floor_bytes':3*1024**3,'max_work_bytes':4*1024**3,'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
    record={'complete':False,'lane':a.lane,'performance_samples':0,'workload_sha256':H.sha(a.workload),'commands':[]};save=lambda:H.save(out/'receipt.json',record);save()
    if a.audit_guard:
        real_killpg=H.os.killpg;attempts=[]
        def logged_killpg(group,sig):
            scope=inspect.currentframe().f_back.f_locals
            row={'group':group,'signal':int(sig),'time':time.time(),'reason':scope.get('reason'),'sampled_peak':scope.get('peak'),'waited':bool(scope.get('waited'))}
            row['processes']=H.process_group(group);attempts.append(row);H.save(out/'guard-kill-audit.json',attempts)
            try:return real_killpg(group,sig)
            except BaseException as e:
                row['syscall_error']=repr(e);H.save(out/'guard-kill-audit.json',attempts);raise
        H.os.killpg=logged_killpg
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth=H.authenticate(a.producer,a.producer_source);H.require(set(w['input_files'])=={x['source'] for x in w['modules']} and len(w['modules'])==w['module_count']==81,'exact complete target inventory');H.check_pins(w['input_files'])
            source=Path(w['modules'][0]['source']).parents[3]
            # Source root comes from the frozen entry path, not caller search paths.
            entry=next(x for x in w['modules'] if x['module']==w['entry']);source=Path(entry['source']).parents[3]
            H.require((source/'shared-sources.json').is_file(),'frozen checkout source root')
            manifest=H.load(source/'shared-sources.json');known={x['module']:x for x in manifest['modules']};seen=set();outside=set()
            def visit(name):
                if name in seen:return
                if name not in known:outside.add(name);return
                seen.add(name)
                for n in re.findall(r'(?m)^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)',(source/known[name]['path']).read_text()):visit(n)
            visit(w['entry']);H.require(seen=={x['module'] for x in w['modules']} and outside=={'MLF.Primitive'},'independent current complete import closure')
            roots=[str(source/x) for x in manifest['source_roots'] if x!='host/ghc'];wrapper=source/'host/ghc/app/emlf/Main.hs'
            inputs={**w['input_files'],**{str(x):H.sha(x) for x in [a.workload.resolve(),a.setup.resolve(),Path(__file__),HERE/'worker.py',hp,wrapper]}}
            job={'lane':a.lane,'output':str(out),'setup':setup,'producer':str(a.producer.resolve()),'source_roots':roots,'wrapper':str(wrapper)}
            if a.lane in ['mlf-checked','mlf-native']:
                queries=out/'queries';queries.mkdir()
                fields=['MLF-CRATE-1','full-compiler/current',w['entry'],'false',pack([pack([x['module'],x['source']]) for x in sorted(w['modules'],key=lambda x:x['module'])]),pack([setup['builtin']+'.mlfci']),str(queries),setup['builtin']]
                (out/'crate.spec').write_text(pack(fields));inputs[str(out/'crate.spec')]=H.sha(out/'crate.spec')
            elif a.lane=='mlf-llvm':
                H.require(a.checked_prefix is not None,'checked input for LLVM-only qualification');job['checked_prefix']=str(a.checked_prefix.resolve())
                for suffix in ['.mlfci','.mlfco']:inputs[str(a.checked_prefix.resolve())+suffix]=H.sha(str(a.checked_prefix)+suffix)
            else:(out/'objects').mkdir()
            H.save(out/'job.json',job);inputs[str(out/'job.json')]=H.sha(out/'job.json');record.update(inputs=inputs,producer_receipt_sha256=H.sha(a.producer/'receipt.json'));save()
            cmd=[sys.executable,'-B',ROOT/'tools/performance/process-spawn/with_scope.py',sys.executable,'-B',HERE/'worker.py','--job',out/'job.json']
            result=H.Runner(out,limits).run(cmd,source,out/'command',timed=True);record['commands'].append(result);save()
            stages=H.load(out/'stages.json');H.require(stages['complete'] and all(x['exit_code']==0 for x in stages['stages']),'complete endpoint stages');record['stages']=stages['stages']
            if a.lane in ['mlf-checked','mlf-native']:
                q=H.load(out/'unit.queries');H.require(q['reused_groups']==0 and q['inferred_groups']==len(q['groups'])>0 and all(x['cached'] is False for x in q['groups']),'complete fresh inference');H.require(len({x['id'] for x in q['groups']})==len(q['groups']),'unique group identities');record.update(fresh=q['inferred_groups'],reused=0,groups=[{k:g[k] for k in ['id','members']} for g in q['groups']],checked_artifacts={str(out/('unit'+s)):H.sha(out/('unit'+s)) for s in ['.mlfci','.mlfco']})
                if a.reference_prefix:
                    H.require(all((out/('unit'+s)).read_bytes()==Path(str(a.reference_prefix)+s).read_bytes() for s in ['.mlfci','.mlfco']),'independent full raw-byte comparison');oldq=H.load(str(a.reference_prefix)+'.queries');H.require(record['groups']==[{k:g[k] for k in ['id','members']} for g in oldq['groups']],'same full fresh group inventory');record['raw_bytes_equal']=True
            elif a.lane.startswith('ghc-'):
                log='\n'.join((out/('source-to-'+a.lane+suffix)).read_text() for suffix in ['.stdout','.stderr']);actual=[]
                for name,path in re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),',log):
                    resolved=Path(path.strip());resolved=resolved if resolved.is_absolute() else out/resolved;actual.append((name,str(resolved.resolve())))
                expected={x['module']:x['source'] for x in w['modules']};expected['Main']=str(wrapper)
                H.require(len(actual)==len(expected) and dict(actual)==expected,'exactly 81 fresh shared modules plus the 5-line host entry wrapper');record.update(fresh_shared_modules=81,fresh_host_wrapper=1,reused_shared_target_modules=0,compiled=actual)
            if a.lane.endswith('native'):
                for name,args in [('version',['--version']),('identity',['--implementation-identity'])]:
                    check=H.Runner(out,limits).run([out/'program',*args],source,out/name);record['commands'].append(check)
                    identity=b'MLF/shared-haskell-v1 '+(b'GHC' if a.lane.startswith('ghc-') else b'native-MLF')+b'\n'
                    H.require((out/name/'stdout').read_bytes()==(b'emlf 0.3.0\n' if name=='version' else identity),'independent authored CLI result '+name)
                record['native_cli_checks']=True
            H.check_pins(inputs);H.require(H.authenticate(a.producer,a.producer_source)==auth,'ordinary producer unchanged');record.update(complete=True,endpoint_wall_seconds=result['wall_seconds']);save();print('PASS',a.lane,record.get('fresh',record.get('fresh_shared_modules')),result['wall_seconds'],flush=True)
    except BaseException as e:record['error']=repr(e);save();raise


if __name__=='__main__':main()
