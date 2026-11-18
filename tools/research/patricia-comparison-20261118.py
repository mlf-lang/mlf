import hashlib, json, os, pathlib, subprocess, types
ROOT=pathlib.Path.cwd(); OUT=ROOT/'evidence'; OUT.mkdir(exist_ok=True)
def load(path):
    m=types.ModuleType(path.stem);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
pins={'old':'d8325d909c249fd82d4ad6173d44d8818cc6f8bf','new':'ee495d5783fca3c26a3c0e659ebeac1bab76a37d'}
roots={k:(ROOT/k).resolve() for k in pins}
H=load(roots['new']/'tools/performance/a1-private-index/helper.py')
limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
record={'complete':False,'scope':'emit-only bounded same-runner diagnosis; not semantic or speed qualification','pins':pins,'limits':limits,'legs':[],'host':H.host()}
def save(): (OUT/'comparison.json').write_text(json.dumps(record,indent=2)+'\n')
save()
fixture=None
for label,root in roots.items():
    assert subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()==pins[label]
    producer=root/'.mlf-build/shared-ghc'
    H.authenticate(producer,root)
    text,wanted,_,_=load(root/'tools/performance/patricia/run_native.py').fixture('rank-views')
    if fixture is None: fixture=text
    assert fixture==text
    record[label]={'binary_sha256':sha(producer/'bin/emlf'),'receipt_sha256':sha(producer/'receipt.json')}
entry=OUT/'Main.hs';entry.write_text(fixture);record['fixture_sha256']=sha(entry);save()
failures={k:0 for k in pins}
for index,label in enumerate(['old','new','new','old']):
    root=roots[label];dest=OUT/('leg-'+str(index)+'-'+label)
    argv=[root/'.mlf-build/shared-ghc/bin/emlf','-i',root/'libraries/mlf-foundation','--emit-llvm',entry]
    try: H.Runner(OUT,limits).run(argv,root,dest,expected_exit=0)
    except RuntimeError as error:
        record['last_error']=repr(error);save()
        if not (dest/'command.json').exists():
            record['stop_reason']='prelaunch guard without receipt';break
    receipt=json.loads((dest/'command.json').read_text())
    record['legs'].append({'label':label,'receipt':str(dest/'command.json'),'complete':receipt['complete']})
    if not receipt['complete']: failures[label]+=1
    save()
    if receipt.get('terminal_live_descendants') or receipt.get('reason'):
        record['stop_reason']='guard or descendant safety stop';break
    if failures[label]>=2: record['stop_reason']='repeated failure';break
record['completed_schedule']=len(record['legs'])==4
record['all_legs_success']=all(x['complete'] for x in record['legs']) and record['completed_schedule']
record['complete']=record['all_legs_success'];save()
