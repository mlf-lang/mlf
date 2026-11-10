#!/usr/bin/env python3
"""One combined 120s localization run, not ordinary timing or qualification.

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
        if line.startswith('F1_SNAPSHOT '):
            row=json.loads(line[len('F1_SNAPSHOT '):])
            for key in ['elapsed_ns','completed_roots','active_roots','roots','recursive_visits',
                        'unique_variable_roots','max_visits_per_root','roots_with_repeats']:
                if type(row.get(key)) is not int or row[key]<0:raise ValueError('invalid snapshot '+key)
            if row['roots'] != row['completed_roots']+row['active_roots']:raise ValueError('root count mismatch')
            if row['recursive_visits']<row['unique_variable_roots']:raise ValueError('visit count mismatch')
            if not isinstance(row['events'],dict) or any(type(v) is not int or v<1 for v in row['events'].values()):
                raise ValueError('invalid event counts')
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
    I=module(HERE/'instrument.py','type_instrument');P=module(HERE/'progress.py','progress_instrument')
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
                         HERE/'instrument.py',HERE/'progress.py',HERE/'Counters.hs',
                         HERE/'DiagnosticControls.hs',Path(__file__).resolve(),
                         source/'tools/performance/process-spawn/with_scope.py']:
                pins[str(path)]=H.sha(path)
            for extension in ['.mlfci','.mlfco']:
                path=setup['builtin']+extension
                H.require(H.sha(path)==setup['builtin_record'][path],'fixed builtin changed')
                pins[path]=H.sha(path)
            H.check_pins(pins)
            private=out/'source';(private/'Bootstrap/X').mkdir(parents=True)
            transformations=[]
            changed,edits=I.instrument((source/OWNER).read_bytes())
            (private/'Bootstrap/X/Type.hs').write_text(changed)
            transformations.append(dict(owner=OWNER,before=OWNER_SHA,after=H.sha(private/'Bootstrap/X/Type.hs'),
                                        reversible=True,edits=edits))
            for name,expected in P.OWNERS.items():
                relative='libraries/mlf-crates/Bootstrap/'+name+'.hs';raw=(source/relative).read_bytes()
                H.require(H.sha(source/relative)==expected,'progress owner changed')
                transformed,count=P.instrument(name,raw)
                target=private/'Bootstrap'/(name+'.hs');target.write_bytes(transformed)
                (out/(name+'.patch')).write_text(''.join(difflib.unified_diff(raw.decode().splitlines(True),
                    transformed.decode().splitlines(True),fromfile=relative,tofile=str(target))))
                transformations.append(dict(owner=relative,before=expected,after=H.sha(target),
                                            reversible=True,changes=count))
            for name in ['Counters.hs','DiagnosticControls.hs']:
                shutil.copy2(HERE/name,private/('KindCounters.hs' if name=='Counters.hs' else name))
            (private/'Main.hs').write_text('''module Main where
import Control.Exception(bracket)
import MLF.Host.IO(runEntry)
import qualified MLF.Entry.Emlf as Entry
import qualified KindCounters
main = bracket KindCounters.startReporting KindCounters.stopReporting $ \\_ -> do
  KindCounters.boundary "entry.main.enter"
  runEntry Entry.main
''')
            copied={}
            for relative,digest in auth['object_inputs'].items():
                if relative.startswith('objects/') and relative.endswith(('.o','.hi')):
                    original=producer/relative;H.require(H.sha(original)==digest,'producer object changed')
                    target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,target)
                    H.require(H.sha(target)==digest,'object copy mismatch');copied[relative]=digest
            for name in ['Main','Bootstrap/X/Type','Bootstrap/CrateSession','Bootstrap/CrateGraph']:
                for extension in ['.o','.hi']:(out/'objects'/(name+extension)).unlink(missing_ok=True)
            flags=[];skip=False
            for flag in auth['flags']:
                if skip:skip=False;continue
                if flag in ['-odir','-hidir']:skip=True
                else:
                    flags.append(flag)
                    if flag=='-i':flags.append('-i'+str(private))
            flags+=['-odir',str(out/'objects'),'-hidir',str(out/'objects')]
            base=[auth['ghc']['path'],'--make','-j1',*flags,'-I'+str(source/'runtime'),'-rtsopts=ignoreAll']
            transports=[str(source/'host/ghc/cbits/host.c'),str(source/'runtime/mlf_process_supervisor.c')]
            record.update(transformations=transformations,copied_objects=copied,inputs=pins)
            save()
            def run(label,argv,limits=LIMITS):
                try:return H.Runner(out,limits).run(argv,source,out/label)
                finally:
                    path=out/label/'command.json'
                    if path.exists():record['commands'].append(H.load(path));save()
            controls=out/'controls-probe'
            run('build-controls',[*base,'-main-is','DiagnosticControls.main',str(private/'DiagnosticControls.hs'),
                                  *transports,'-o',str(controls)])
            run('controls',[str(controls)])
            H.require((out/'controls/stdout').read_text()=='PASS diagnostic value and demand controls\n',
                      'control output changed')
            H.require((out/'controls/stderr').read_text()=='KIND_DIAGNOSTIC {"roots":4,"recursive_visits":12,"unique_variable_roots":7,"max_visits_per_root":9,"roots_with_repeats":2}\n',
                      'control counts changed')
            run('reporter-controls',[str(controls),'--reporter-control'])
            rows,other=snapshots(out/'reporter-controls/stderr')
            H.require(not other and rows[0]['reason']=='start' and rows[0]['roots']==0 and
                      any(r['reason']=='periodic' and r['recursive_visits']==12 and
                          r['last_boundary']=='controls.complete' for r in rows) and rows[-1]['reason']=='stop',
                      'live reporter controls failed')
            record['preflight_snapshots']=rows;save()
            binary=out/'diagnostic-emlf'
            run('build-compiler',[*base,str(private/'Main.hs'),*transports,'-o',str(binary)])
            run('entry-preflight',[str(binary),'--version'])
            rows,other=snapshots(out/'entry-preflight/stderr')
            H.require(not other and rows[0]['reason']=='start' and rows[0]['roots']==0 and
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
            H.require(rows and rows[0]['reason']=='start' and rows[0]['roots']==0,'missing immediate zero snapshot')
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
            H.check_pins(pins);H.require(H.authenticate(producer,source)==auth,'ordinary producer changed')
            save();print(json.dumps({k:record[k] for k in ['compiler_complete','last_snapshot','snapshot_count','full_output_exists']},indent=2))
    except BaseException as error:
        record['error']=repr(error);save();raise

if __name__=='__main__':main()
