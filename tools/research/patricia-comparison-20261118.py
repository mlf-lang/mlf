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
HINT=0x4200000000
MIB=1<<20
HIST={'old':3984908288,'new':4300558336}
def map_shape(body,cap):
    spans=[]; started=False; total=0
    for line in body.splitlines():
        cols=line.split(None,5);lo,hi=[int(v,16) for v in cols[0].split('-')]
        valid=(len(cols)==5 and cols[1] in ('rw-p','---p') and cols[2].strip('0')=='' and cols[3]=='00:00' and cols[4]=='0')
        if not started:
            if lo!=HINT:continue
            started=True
        if lo!=HINT+total or not valid:break
        spans.append([cols[1],hi-lo]);total+=hi-lo
    want=(int(cap*0.666)//MIB)*MIB
    return {'hint_exact':started,'predicted_bytes':want,'observed_bytes':total,'extent_count':len(spans),'normalized_spans':spans,'rw_bytes':sum(b for a,b in spans if a=='rw-p'),'none_bytes':sum(b for a,b in spans if a=='---p'),'match':bool(spans and total in (want,want+MIB))}
def map_once(pid,fields,exe,cap):
    box=pathlib.Path('/proc')/str(pid)
    def stamp():
        return ((box/'stat').read_text().rsplit(') ',1)[1].split()[19],os.readlink(box/'exe'))
    expect=(fields[19],str(exe.resolve()))
    if stamp()!=expect:return {'match':False,'error':'leader identity before read'}
    body=(box/'maps').read_text();line=next(x for x in (box/'limits').read_text().splitlines() if x.startswith('Max address space'))
    if stamp()!=expect:return {'match':False,'error':'leader identity after read'}
    o=map_shape(body,cap);ns=line.split()[3:5]
    o.update(same_leader=True,soft_hard_as=ns)
    o['match']=o['match'] and ns==[str(cap),str(cap)]
    return o
record['scope']='RLIMIT_AS-only ordinary binary comparison; exact-hint anonymous mapping and early cap verification; nonarena headroom also changes, no function or allocation attribution.'
record['schedule']=['old-6','new-6','new-5.5','old-5.5']
record['observer_rows']=['elapsed_since_first_poll_s','minflt','majflt','utime_ticks','stime_ticks','vsize_bytes','rss_bytes']
page_size=os.sysconf('SC_PAGE_SIZE')
record['page_size_bytes']=page_size;record['clock_ticks_per_second']=os.sysconf('SC_CLK_TCK')
for i,(label,cap) in enumerate([('old',6<<30),('new',6<<30),('new',11<<29),('old',11<<29)]):
    rows=[];start=None;next_sample=0.0;maps=None;root=roots[label];exe=root/'.mlf-build/shared-ghc/bin/emlf';dest=OUT/('leg-'+str(i)+'-'+label)
    def capture(group,fields):
        global start,next_sample,maps
        now=time.monotonic()
        if now<next_sample or len(rows)>=602:return
        if start is None:start=now
        next_sample=now+1.0
        rows.append([round(now-start,4),int(fields[7]),int(fields[9]),int(fields[11]),int(fields[12]),int(fields[20]),int(fields[21])*page_size])
        if maps is None and now-start>=2.0 and fields[0]!='Z':
            maps={'match':False,'error':'read failed'}
            try: maps=map_once(group,fields,exe,cap)
            except (OSError,ValueError,IndexError,StopIteration) as e:maps={'match':False,'error':type(e).__name__}
    ns=dict(base_group.__globals__);ns['capture']=capture
    exec(compile(modified,'<exact-guard-stat-observer>','exec'),ns);H.process_group=ns['process_group']
    expected=0 if label=='old' else 251
    try:H.Runner(OUT,dict(limits,address_space_per_process_bytes=cap)).run([exe,'-i',root/'libraries/mlf-foundation','--type',entry],root,dest,expected_exit=expected)
    except RuntimeError as e:record['last_runner_exception']=repr(e)
    finally:
        H.process_group=base_group
        (OUT/('stat-'+str(i)+'-'+label+'.json')).write_text(json.dumps(rows)+'\n')
        (OUT/('map-'+str(i)+'-'+label+'.json')).write_text(json.dumps(maps)+'\n')
    if not (dest/'command.json').exists():record['stop_reason']='missing receipt';save();break
    j=json.loads((dest/'command.json').read_text());ec=j.get('exit_code')
    stdout=(dest/'stdout').read_bytes();stderr=(dest/'stderr').read_bytes()
    verdict=(ec==0 and stdout==b'IO ()\n' and stderr==b'') or (ec==251 and not stdout and stderr==b'emlf: out of memory\n')
    accepted=bool(verdict and j.get('reason') is None and j.get('terminal_live_descendants')==[] and j.get('limits',{}).get('address_space_per_process_bytes')==cap and j.get('logs') and all(sha(pathlib.Path(k))==v for k,v in j['logs'].items()) and maps and maps['match'] and len(rows)>2 and rows[-1][0]>=.8*j['wall_seconds'])
    if i<2:accepted=accepted and bool(j['complete']) and ec==expected and .95<=j['max_individual_child_rss_bytes']/HIST[label]<=1.05
    record['legs'].append({'label':label,'cap':cap,'exit_code':ec,'observations':len(rows),'map':maps,'max_child_rss_bytes':j['max_individual_child_rss_bytes'],'accepted':accepted});save()
    if not accepted:record['stop_reason']='control, map, exact outcome, identity, safety or observation gate failed';save();break
record['complete']=len(record['legs'])==4 and all(k['accepted'] for k in record['legs'])
save()
