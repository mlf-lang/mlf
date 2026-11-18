import hashlib, json, os, pathlib, subprocess, types
ROOT=pathlib.Path.cwd(); OUT=ROOT/'evidence'; OUT.mkdir(exist_ok=True)
def load(path):
    m=types.ModuleType(path.stem);m.__file__=str(path);exec(compile(path.read_bytes(),str(path),'exec'),m.__dict__);return m
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
pins={'old':'d8325d909c249fd82d4ad6173d44d8818cc6f8bf','new':'ee495d5783fca3c26a3c0e659ebeac1bab76a37d'}
roots={k:(ROOT/k).resolve() for k in pins}
H=load(roots['new']/'tools/performance/a1-private-index/helper.py')
limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,host_available_floor_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,max_work_bytes=2*1024**3,wall_seconds=600)
record={'complete':False,'scope':'type-only bounded same-runner diagnosis; not semantic or speed qualification','pins':pins,'limits':limits,'legs':[],'host':H.host()}
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

# No compiler or fixture changes. Both control legs must reproduce before observation.
import inspect,time,resource
ref_bins={'old':'d90ecca441c0c1a00c224639b335124ec4802d97f99e7d44eea9ccce3a715c8d','new':'8845fbb4729e555157c2cd3ca45d2981741bf8308bbdbef6ece74c85a5d90245'}
assert record['fixture_sha256']=='e7bc0d6bdd6ec6ac1a7d9b2cd6f71cb398c430f3029c870057d096efff2aaa82'
assert all(record[k]['binary_sha256']==v for k,v in ref_bins.items())
helper=roots['new']/'tools/performance/a1-private-index/helper.py'
assert subprocess.check_output(['git','hash-object',str(helper)],text=True).strip()=='1feffe5d9f360a8fbb9f27868985d4a1a97ab010'
base_group=H.process_group
original=inspect.getsource(base_group)
needle="            if int(fields[2]) == group or int(fields[3]) == group:"
assert original.count(needle)==1
modified=original.replace(needle,"            if entry.name == str(group): capture(group,fields)\n"+needle)
record['scope']='unmodified type binaries; CPU/VM/fault snapshots already available in the existing guard poll. Not allocation attribution, timing or heap profiling.'
record['schedule']=['control-old','control-new','observe-old','observe-new']
record['observer_rows']=['elapsed_since_first_poll_s','ru_minflt','ru_majflt','utime_ticks','stime_ticks','vsize_bytes','rss_bytes']
record['clock_ticks_per_second']=os.sysconf('SC_CLK_TCK')
page_size=os.sysconf('SC_PAGE_SIZE')
for i,(label,enabled) in enumerate([('old',False),('new',False),('old',True),('new',True)]):
    rows=[]; start=None; next_sample=0.0
    def capture(group,fields):
        global start,next_sample
        now=time.monotonic()
        if now < next_sample or len(rows)>=602:return
        if start is None:start=now
        next_sample=now+1.0
        # Linux /proc/PID/stat split after final comm delimiter, same indices and bytes already read by guard.
        rows.append([round(now-start,4),int(fields[7]),int(fields[9]),int(fields[11]),int(fields[12]),int(fields[20]),int(fields[21])*page_size])
    if enabled:
        namespace=dict(base_group.__globals__);namespace['capture']=capture
        exec(compile(modified,'<exact-guard-stat-observer>','exec'),namespace)
        H.process_group=namespace['process_group']
    root=roots[label];dest=OUT/('leg-'+str(i)+'-'+label)
    argv=[root/'.mlf-build/shared-ghc/bin/emlf','-i',root/'libraries/mlf-foundation','--type',entry]
    expected=0 if label=='old' else 251
    try:
        H.Runner(OUT,limits).run(argv,root,dest,expected_exit=expected)
    except RuntimeError as e:
        record['last_error']=repr(e)
    finally:
        H.process_group=base_group
        if enabled:(OUT/('stat-'+str(i)+'-'+label+'.json')).write_text(json.dumps(rows)+'\n')
    if not (dest/'command.json').exists():
        record['stop_reason']='missing leg receipt';save();break
    receipt=json.loads((dest/'command.json').read_text())
    valid=receipt.get('complete') and receipt.get('exit_code')==expected and not receipt.get('reason') and not receipt.get('terminal_live_descendants') and (dest/'stdout').read_bytes()==(b'IO ()\n' if label=='old' else b'') and (dest/'stderr').read_bytes()==(b'' if label=='old' else b'emlf: out of memory\n') and (not enabled or (len(rows)>=2 and rows[-1][0] >= 0.8*receipt['wall_seconds']))
    record['legs'].append({'label':label,'observed':enabled,'outcome_reproduced':bool(valid),'samples':len(rows),'max_child_rss_bytes':receipt.get('max_individual_child_rss_bytes'),'exit_code':receipt.get('exit_code')});save()
    if not valid:record['stop_reason']='control, reproduction, guard or observation failed';save();break
record['complete']=len(record['legs'])==4 and all(k['outcome_reproduced'] for k in record['legs'])
save()
if record['complete']:
    rss={l['label']+'-'+str(l['observed']):l['max_child_rss_bytes'] for l in record['legs']}
    record['observer_rss_ratios']={k:rss[k+'-True']/rss[k+'-False'] for k in ['old','new']}
    record['rss_comparable']=all(0.95 <= r <= 1.05 for r in record['observer_rss_ratios'].values())
    if not record['rss_comparable']:record['interpretation']='Observer/control max RSS differs by >5%; no trusted differential trajectory.'
    save()
