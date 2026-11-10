#!/usr/bin/env python3
"""One markers-only 120s localization run, not ordinary timing or qualification.

Run under the coordinator-owned outer flock. Failed/guarded compiler receipts
remain incomplete; readable partial snapshots do not turn them into success.
"""
from pathlib import Path
import argparse
import difflib
import json
import os
import shutil
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OWNER = 'libraries/mlf-xmlf/Bootstrap/X/Type.hs'
OWNER_SHA = '5ae7191adc5df556b83901682ee17e3de889a99e9fe35e97d7370ec2443d0d3d'
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
              disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
              max_work_bytes=4*1024**3, process_tree_rss_bytes=5*1024**3, wall_seconds=600)

def module(path,name):
    result=types.ModuleType(name);result.__file__=str(path)
    exec(compile(path.read_bytes(),str(path),'exec'),result.__dict__)
    return result

def pack(fields):return ''.join(str(len(field))+':'+field for field in fields)

def snapshots(path):
    result=[];other=[]
    for line in path.read_text().splitlines():
        if line.startswith('GRAPH_SNAPSHOT '):
            row=json.loads(line[len('GRAPH_SNAPSHOT '):])
            for key in ['elapsed_ns','scc_started','scc_finished_fresh','scc_finished_reused']:
                if type(row.get(key)) is not int or row[key]<0:raise ValueError('invalid snapshot '+key)
            if row['scc_started'] < row['scc_finished_fresh']+row['scc_finished_reused']:raise ValueError('SCC count mismatch')
            if len(row['slowest_completed'])>5:raise ValueError('unbounded top records')
            identities=[row['current_identity']]+[x['identity'] for x in row['slowest_completed']]
            if row['last_completed'] is not None:identities.append(row['last_completed']['identity'])
            for identity in identities:
                if identity is not None:
                    if identity['member_count']<0 or len(identity['members'])>4 or any(len(x['stable_prefix'])>96 for x in identity['members']):
                        raise ValueError('unbounded identity')
            for value in row['closed_windows'].values():
                if value['closed_ns']<0 or value['closed_count']<0:raise ValueError('invalid window total')
            result.append(row)
        else:other.append(line)
    return result,other

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['producer','producer-source','workload','setup','output']:
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();source=a.producer_source.resolve();producer=a.producer.resolve();out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    hp=source/'tools/performance/a1-private-index/helper.py';H=module(hp,'guard')
    P=module(HERE/'transform.py','progress_instrument')
    record=dict(complete=False,harness_complete=False,diagnostic_only=True,performance_samples=0,
                semantic_qualification=False,commands=[],run_seconds=120)
    save=lambda:H.save(out/'receipt.json',record);save()
    try:
        with H.SerialLock(source/'.mlf-build'):
            auth=H.authenticate(producer,source)
            H.require(H.sha(source/OWNER)==OWNER_SHA,'frozen Type owner changed')
            w=H.load(a.workload);setup=H.load(a.setup)
            H.require(set(w['input_files'])=={x['source'] for x in w['modules']} and len(w['modules'])==90,
                      'exact frozen 90-module inventory')
            freeze_path=source/'tools/performance/full-compiler/prepare_workload.py'
            fresh=module(freeze_path,'freeze').freeze(source,w['baseline_ref'])
            H.require(fresh['input_files']==w['input_files'] and fresh['entry']==w['entry'],
                      'independent recursive source closure changed')
            pins={**w['input_files']}
            for path in [a.workload.resolve(),a.setup.resolve(),hp,freeze_path,producer/'receipt.json',
                         HERE/'transform.py',HERE/'Progress.hs',HERE/'Controls.hs',
                         HERE.parent/'type-kind-memo/progress.py',Path(__file__).resolve(),
                         source/'tools/performance/process-spawn/with_scope.py']:
                pins[str(path)]=H.sha(path)
            for extension in ['.mlfci','.mlfco']:
                path=setup['builtin']+extension
                H.require(H.sha(path)==setup['builtin_record'][path],'fixed builtin changed')
                pins[path]=H.sha(path)
            H.check_pins(pins)
            private=out/'source';(private/'Bootstrap/X').mkdir(parents=True)
            transformations=[]
            for name,expected in P.OWNERS.items():
                relative='libraries/mlf-crates/Bootstrap/'+name+'.hs';raw=(source/relative).read_bytes()
                H.require(H.sha(source/relative)==expected,'progress owner changed')
                transformed,count=P.instrument(name,raw)
                target=private/'Bootstrap'/(name+'.hs');target.write_bytes(transformed)
                (out/(name+'.patch')).write_text(''.join(difflib.unified_diff(raw.decode().splitlines(True),
                    transformed.decode().splitlines(True),fromfile=relative,tofile=str(target))))
                transformations.append(dict(owner=relative,before=expected,after=H.sha(target),
                                            reversible=True,changes=count))
            shutil.copy2(HERE/'Progress.hs',private/'GraphProgress.hs')
            (private/'Main.hs').write_text('''module Main where
import Control.Exception(bracket)
import MLF.Host.IO(runEntry)
import qualified MLF.Entry.Emlf as Entry
import qualified GraphProgress
main = bracket GraphProgress.startReporting GraphProgress.stopReporting $ \\_ -> do
  GraphProgress.boundary "entry.main.enter"
  runEntry Entry.main
''')
            copied={}
            for relative,digest in auth['object_inputs'].items():
                if relative.startswith('objects/') and relative.endswith(('.o','.hi')):
                    original=producer/relative;H.require(H.sha(original)==digest,'producer object changed')
                    target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
                    H.require(H.sha(target)==digest,'object copy mismatch');copied[relative]=digest
            for name in ['Main','Bootstrap/CrateSession','Bootstrap/CrateGraph']:
                for extension in ['.o','.hi']:(out/'objects'/(name+extension)).unlink(missing_ok=True)
            flags=[];skip=False
            for flag in auth['flags']:
                if skip:skip=False;continue
                if flag in ['-odir','-hidir']:skip=True
                else:
                    flags.append(flag)
                    if flag=='-i':flags.append('-i'+str(private))
            flags+=['-odir',str(out/'objects'),'-hidir',str(out/'objects')]
            base=[auth['ghc']['path'],'--make','-j1',*flags,'-rtsopts=ignoreAll']
            transports=[];c_objects={};c_commands=[]
            H.require(H.sha(auth['cc']['path'])==auth['cc']['sha256'],'ordinary CC changed')
            for name in ['host.o','supervisor.o']:
                candidates=[c for c in auth['commands'] if '-o' in c['argv'] and
                            c['argv'][c['argv'].index('-o')+1]==str(producer/name)]
                H.require(len(candidates)==1,'missing unique ordinary C command')
                command=candidates[0]
                H.require(command['argv'][0]==auth['cc']['path'] and command['cwd']==str(source),'C command provenance changed')
                expected=H.sha(producer/name);pins[str(producer/name)]=expected
                shutil.copy2(producer/name,out/name)
                H.require(H.sha(out/name)==expected,'ordinary C copy changed')
                argv=list(command['argv']);argv[argv.index('-o')+1]=str(out/('verified-'+name))
                c_commands.append((name,argv));transports.append(str(out/name));c_objects[name]=expected
            record.update(ordinary_flags=auth['flags'],diagnostic_flags=flags,
                          ordinary_c_objects=c_objects,type_owner_unchanged=OWNER_SHA,
                          c_authentication='pending exact-command rebuild and byte equality')

            record.update(transformations=transformations,copied_objects=copied,inputs=pins)
            save()
            def run(label,argv,limits=LIMITS):
                try:return H.Runner(out,limits).run(argv,source,out/label)
                finally:
                    path=out/label/'command.json'
                    if path.exists():record['commands'].append(H.load(path));save()
            for name,argv in c_commands:
                run('verify-'+name,argv)
                H.require(H.sha(out/('verified-'+name))==c_objects[name], 'ordinary C rebuild differs')
            record['c_authentication']='exact authenticated compiler/source/command rebuild matched both copied ordinary objects'
            save()
            controls=out/'controls-probe'
            control_flags=list(flags)
            for flag in ['-odir','-hidir']:
                control_flags[control_flags.index(flag)+1]=str(out/'control-objects')
            run('build-controls',[auth['ghc']['path'],'--make','-j1',*control_flags,
                                  '-rtsopts=ignoreAll',str(HERE/'Controls.hs'),'-o',str(controls)])
            run('controls',[str(controls)])
            H.require((out/'controls/stdout').read_text()=='PASS graph marker controls\n','control output changed')
            rows,other=snapshots(out/'controls/stderr')
            H.require(not other and rows[0]['reason']=='start' and rows[0]['scc_started']==0 and
                      any(r['reason']=='periodic' and r['open_window']['name']=='prepared_record' and
                          r['open_window']['age_ns']>0 for r in rows) and
                      any(r['reason']=='identity-cleared' and r['current_identity'] is None and
                          r['last_completed']['identity']['member_count']==8 for r in rows) and
                      rows[-1]['reason']=='stop','live marker controls failed')
            record['control_snapshots']=rows;save()
            binary=out/'diagnostic-emlf'
            run('build-compiler',[*base,str(private/'Main.hs'),*transports,'-o',str(binary)])
            run('entry-preflight',[str(binary),'--version'])
            rows,other=snapshots(out/'entry-preflight/stderr')
            H.require(not other and rows[0]['reason']=='start' and rows[0]['scc_started']==0 and
                      (out/'entry-preflight/stdout').read_text()=='emlf 0.3.0\n', 'entry preflight failed')
            for path in private.rglob('*'):
                if path.is_file():pins[str(path)]=H.sha(path)
            pins[str(binary)]=H.sha(binary)
            queries=out/'queries';queries.mkdir()
            fields=['MLF-CRATE-1','full-compiler/current',w['entry'],'false',
                    pack([pack([x['module'],x['source']]) for x in sorted(w['modules'],key=lambda x:x['module'])]),
                    pack([setup['builtin']+'.mlfci']),str(queries),setup['builtin']]
            spec=out/'crate.spec';spec.write_text(pack(fields));pins[str(spec)]=H.sha(spec);save()
            for name in ['MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT']:os.environ.pop(name,None)
            command=[sys.executable,'-B',source/'tools/performance/process-spawn/with_scope.py',
                     binary,'--compile-crate',spec,'-o',out/'unit']
            try:run('locate',command,{**LIMITS,'wall_seconds':120})
            except RuntimeError as error:
                outcome=H.load(out/'locate/command.json')
                if outcome.get('reason')!='wall limit':raise
                record['bounded_stop']=str(error)
            rows,other=snapshots(out/'locate/stderr')
            H.require(rows and rows[0]['reason']=='start' and rows[0]['scc_started']==0,'missing immediate zero snapshot')
            H.require(any(row['reason']=='periodic' for row in rows),'no live snapshots')
            outcome=H.load(out/'locate/command.json')
            H.require(not outcome.get('terminal_live_descendants'),'diagnostic child still alive')
            record.update(complete=outcome['complete'],harness_complete=True,
                          compiler_complete=outcome['complete'],last_snapshot=rows[-1],
                          snapshot_count=len(rows),other_stderr=other,
                          directory_inventory=[dict(path=str(path.relative_to(out)),kind='directory' if path.is_dir() else 'file',
                                                    bytes=path.stat().st_size if path.is_file() else None)
                                               for path in sorted(queries.rglob('*'))],
                          full_output_exists={suffix:(out/('unit'+suffix)).is_file() for suffix in ['.mlfci','.mlfco','.queries']})
            H.require(H.sha(source/OWNER)==OWNER_SHA,'Type owner changed after run')
            H.check_pins(pins);H.require(H.authenticate(producer,source)==auth,'ordinary producer changed')
            save();print(json.dumps({k:record[k] for k in ['compiler_complete','last_snapshot','snapshot_count','full_output_exists']},indent=2))
    except BaseException as error:
        record['error']=repr(error);save();raise

if __name__=='__main__':main()
