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
locked_inputs={"old":{"object_inputs":"3d4e55562e15482eb19265820d648d8f7fe261e4700c585bdd4fe02228d7b779","resolved_modules":"dc980d404188953009eba29c04a7fa856be709708e04923fcfd6416e73da7ae8","resolved_host_modules":"f6bb370236c702e1282baca2ada46b5944df522bb1eca16a28ca5f4980d35d7f","configuration_inputs":"ec04b1382d64c5b43ffa6ffd2b663e1d94e216006526695fef1d28869cb36501","shared_inputs":"1c1b747c167c5936b8856e89d0280789622d4538173a93306464a2ae04b8d2f0","host_inputs":"a8a09986e2e01b941741151e12e7a2cbf8665996bb6d53f78561b556cfa28e04","flags":"50e344ad68ebb24127b0b8e73be203817bc964f033bcf3fbcf1d43afe166258f","ghc":"8057b580fb047c5302ab1291596cf79a30e906f21c4cd223ea2d5e7c71ada348","cc":"f0eaee113e92135d35342b0994c6a039894e5da8991860c3f7c11c6202c4afa3","installed_dependencies":"6588b2ecaea0410f237fd3a23d4a78073940ca89304ea83e1596ff16ee6b9572","toolchain":"08c0814ca993e4904b1087c717838ef95273f955fdc71432df2b46b8d0d66301"},"new":{"object_inputs":"26215720f9596e5462c611c0254498fd8c1a4ede4b6b9281666c28d40c41243a","resolved_modules":"2a65c9034307623cc7d411925648209d56021b9657e01341b9768259b6f46a6a","resolved_host_modules":"7d6328f49a88fc532323ac3be760d3ff3fa37bcee9fb50bd395650d664de8b1e","configuration_inputs":"d14ae947e683961893ca57020002c71042fa797a69dd1a63eb890994aa5179cd","shared_inputs":"36c769215036a3f72d32d82b54193304a291930b2e967dff63cbc10509927bdb","host_inputs":"ea210294596583ac33ff4dbedb5d5e82a0c4c30d7a48cf9d31a962f2bd9c3694","flags":"0f373f3be1a95bf7d1a0a00fcd9e8dc6be3435188249f2f67ad23208db703e8c","ghc":"8057b580fb047c5302ab1291596cf79a30e906f21c4cd223ea2d5e7c71ada348","cc":"f0eaee113e92135d35342b0994c6a039894e5da8991860c3f7c11c6202c4afa3","installed_dependencies":"6588b2ecaea0410f237fd3a23d4a78073940ca89304ea83e1596ff16ee6b9572","toolchain":"08c0814ca993e4904b1087c717838ef95273f955fdc71432df2b46b8d0d66301"}}

import re
# This is an independent new-host experiment, not the historic executable cohort.
def canon(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
def file_sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def runtime_manifest(exe):
    # Use the trusted, just-built program and clean loader environment. Identify ELF interpreter and ELF runtime closure.
    if any(os.environ.get(k) for k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH')):raise RuntimeError('nonempty loader override')
    env=dict(os.environ,LC_ALL='C'); listing=subprocess.check_output(['/usr/bin/ldd',str(exe)],text=True,env=env,timeout=15)
    if 'not found' in listing:raise RuntimeError('unresolved dependency')
    files={}
    for line in listing.splitlines():
        line=line.strip()
        if not line or line.startswith('linux-vdso.'):continue
        v=line.split('=>',1)[-1].strip().split(' (0x',1)[0]
        if not v.startswith('/'):raise RuntimeError('unexpected ldd row')
        p=pathlib.Path(v).resolve(strict=True)
        files[str(p)]={'sha256':file_sha(p),'bytes':p.stat().st_size}
    ph=subprocess.check_output(['/usr/bin/readelf','-lW',str(exe)],text=True,env=env,timeout=15)
    ld=re.search(r'Requesting program interpreter: ([^]]+)\]',ph)
    if not ld or str(pathlib.Path(ld.group(1)).resolve(strict=True)) not in files:raise RuntimeError('missing interpreter')
    return {'binary_sha256':file_sha(exe),'interpreter':str(pathlib.Path(ld.group(1)).resolve()),'loaded_elf_dependencies':files}
cohort={'epoch':'new-runner independent; never substitute for historical hashes','image':os.environ.get('ImageVersion'),'run_id':os.environ.get('GITHUB_RUN_ID'),'members':{}}
if not cohort['image'] or not cohort['run_id']:raise RuntimeError('missing environment identity')
for l,r in roots.items():
    receipt=json.loads((r/'.mlf-build/shared-ghc/receipt.json').read_text())
    if any(canon(receipt[k])!=v for k,v in locked_inputs[l].items()):raise RuntimeError('pinned intermediate identity mismatch: '+l)
    ex=r/'.mlf-build/shared-ghc/bin/emlf'
    m=runtime_manifest(ex)
    if m['binary_sha256']!=record[l]['binary_sha256'] or m['binary_sha256']!=receipt['outputs']['emlf']['sha256']:raise RuntimeError('unverified executable')
    cohort['members'][l]={'runtime':m,'package_database_sha256':receipt['package_database_sha256'],'receipt_sha256':record[l]['receipt_sha256'],'intermediate_sha256':locked_inputs[l]}
a,b=cohort['members']['old'],cohort['members']['new']
if a['runtime']['loaded_elf_dependencies']!=b['runtime']['loaded_elf_dependencies'] or a['package_database_sha256']!=b['package_database_sha256'] or a['runtime']['binary_sha256']==b['runtime']['binary_sha256']:raise RuntimeError('mismatched shared runtime or non-distinct producers')
manifest=OUT/'new-epoch-cohort.json';manifest.write_text(json.dumps(cohort,indent=2)+'\n');frozen=sha(manifest)
def verify_frozen(l):
    if sha(manifest)!=frozen:raise RuntimeError('mutated manifest')
    ex=roots[l]/'.mlf-build/shared-ghc/bin/emlf'
    if runtime_manifest(ex)!=cohort['members'][l]['runtime'] or sha(roots[l]/'.mlf-build/shared-ghc/receipt.json')!=cohort['members'][l]['receipt_sha256']:raise RuntimeError('changed executable, dependency or receipt')
record['epoch_manifest_sha256']=frozen;save()

helper=roots['new']/'tools/performance/a1-private-index/helper.py'
assert subprocess.check_output(['git','hash-object',str(helper)],text=True).strip()=='1feffe5d9f360a8fbb9f27868985d4a1a97ab010'
base_group=H.process_group
original=inspect.getsource(base_group)
needle="            if int(fields[2]) == group or int(fields[3]) == group:"
assert original.count(needle)==1
modified=original.replace(needle,"            if entry.name == str(group): capture(group,fields)\n"+needle)
HINT=0x4200000000
MIB=1<<20
HIST={}
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
record['scope']='NEW COHORT ONLY: same-job independently frozen binaries and runtime, untreated then observed 6 GiB controls followed by reduced 5.5 GiB; no equivalence to historical ELF identities, timing or allocation attribution.'
record['schedule']=['plain-old-6','plain-new-6','observed-old-6','observed-new-6','observed-new-5.5','observed-old-5.5']
record['observer_rows']=['elapsed_since_first_poll_s','minflt','majflt','utime_ticks','stime_ticks','vsize_bytes','rss_bytes']
page_size=os.sysconf('SC_PAGE_SIZE')
record['page_size_bytes']=page_size;record['clock_ticks_per_second']=os.sysconf('SC_CLK_TCK')
for i,(label,cap) in enumerate([('old',6<<30),('new',6<<30),('old',6<<30),('new',6<<30),('new',11<<29),('old',11<<29)]):
    verify_frozen(label)
    observed=i>=2
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
    exec(compile(modified,'<exact-guard-stat-observer>','exec'),ns);H.process_group=ns['process_group'] if observed else base_group
    expected=0 if label=='old' else 251
    try:H.Runner(OUT,dict(limits,address_space_per_process_bytes=cap)).run([exe,'-i',root/'libraries/mlf-foundation','--type',entry],root,dest,expected_exit=expected)
    except RuntimeError as e:record['last_runner_exception']=repr(e)
    finally:
        H.process_group=base_group
        (OUT/('stat-'+str(i)+'-'+label+'.json')).write_text(json.dumps(rows)+'\n')
        (OUT/('map-'+str(i)+'-'+label+'.json')).write_text(json.dumps(maps)+'\n')
    verify_frozen(label)
    if not (dest/'command.json').exists():record['stop_reason']='missing receipt';save();break
    j=json.loads((dest/'command.json').read_text());ec=j.get('exit_code')
    stdout=(dest/'stdout').read_bytes();stderr=(dest/'stderr').read_bytes()
    verdict=(ec==0 and stdout==b'IO ()\n' and stderr==b'') or (ec==251 and not stdout and stderr==b'emlf: out of memory\n')
    accepted=bool(verdict and j.get('reason') is None and j.get('terminal_live_descendants')==[] and j.get('limits',{}).get('address_space_per_process_bytes')==cap and j.get('logs') and all(sha(pathlib.Path(k))==v for k,v in j['logs'].items()) and (not observed or (maps and maps['match'] and len(rows)>2 and rows[-1][0]>=.8*j['wall_seconds'])))
    if i<4:accepted=accepted and bool(j['complete']) and ec==expected
    if i<2 and accepted:HIST[label]=j['max_individual_child_rss_bytes']
    if i in (2,3):accepted=accepted and .95<=j['max_individual_child_rss_bytes']/HIST[label]<=1.05
    record['legs'].append({'label':label,'observed':observed,'cap':cap,'exit_code':ec,'observations':len(rows),'map':maps,'max_child_rss_bytes':j['max_individual_child_rss_bytes'],'accepted':accepted});save()
    if not accepted:record['stop_reason']='control, map, exact outcome, identity, safety or observation gate failed';save();break
record['complete']=len(record['legs'])==6 and all(k['accepted'] for k in record['legs'])
save()
