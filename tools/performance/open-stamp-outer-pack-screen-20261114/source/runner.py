#!/usr/bin/python3
"""DRAFT ONLY. Direct ordinary OpenFragment outer stamp A/B screen, never a compiler handoff."""
from pathlib import Path
import argparse, ast, hashlib, json, os, re, shutil, sys, time, types

HERE = Path(__file__).resolve().parent
R = HERE.parent
BASELINE = R/'rebind-r25-formal'
SOURCE = BASELINE/'source'
PRODUCER = BASELINE/'ordinary/build/producer'
TARGET = 'Bootstrap.OpenFragment'
VALIDATOR = BASELINE/'validation/controller.py'
VALIDATOR_SHA = 'fbfdad2f9a93cd62c176e013ea7fc6e563ffb5fd635fd1b28d87d3ddfcec346e'
RUNTIME = R/'dense-direct-capture-r24-source/implementation/runtime_pins.py'
RUNTIME_SHA = 'cf1346302f2467d74a883e51042d28442d0c0af5f659702e6fcf09ed43c1662b'
R13 = R/'recovery/tools/performance/full-compiler/continuation-20261111/sparse-attribution-r13'
READY = False  # SOURCE ONLY. Coordinator must review, enable, re-pin, and separately admit.
TOTAL_SECONDS = 180
GUARD_SHA = '53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e'
ORACLE_SHA = '9a9bc72aef6bfe7cf3853620b8b4dc055b12d5ab50df1f53dd95247775d8777f'
BASE = 'bda8f9807c8b13b5ce14753d0320fa54772e4bc4'
SCOPE = 'direct-ordinary-open-stamp-screen-no-compiler-or-performance-qualification'

def need(ok, why):
    if not ok: raise ValueError(why)


def safe(p):
    p=Path(p)
    need(p.is_absolute() and '..' not in p.parts,'absolute nontraversing path required')
    need(all(not q.is_symlink() for q in [p,*p.parents]),'symlink forbidden')
    return p


def sha(p):
    with safe(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()


def pin(p):
    p=safe(p); return {'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}


def verify(x):
    p=safe(x['path']); need(p.is_file() and sha(p)==x['sha256'] and p.stat().st_size==x['bytes'],'pin drift: '+str(p))
    if 'mode' in x: need(p.stat().st_mode==x['mode'],'output mode drift: '+str(p))
    return p


def unique(pairs):
    out={}
    for k,v in pairs:
        need(k not in out,'duplicate JSON key'); out[k]=v
    return out


def load(p): return json.loads(safe(p).read_text(),object_pairs_hook=unique)


def save(p,value):
    p=safe(p); tmp=p.with_suffix(p.suffix+'.tmp')
    with tmp.open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
    tmp.replace(p)


def module(p,expected,name):
    need(sha(p)==expected,'tool source changed')
    m=types.ModuleType(name); m.__file__=str(p)
    exec(compile(safe(p).read_bytes(),str(p),'exec'),m.__dict__)
    return m


def guard(): return module(R13/'guard.py',GUARD_SHA,'r27_original_guard')


def input_pins(plan):
    for item in plan['input_pins']: verify(item)


def validate(digest):
    need(READY,'READY=False: no execution approved; coordinator review/enable/re-pin required')
    need(Path(sys.executable).resolve()==Path('/usr/bin/python3').resolve(),'canonical Python')
    need(sha(HERE/'admission.json')==digest,'admission digest drift')
    a=load(HERE/'admission.json')
    need(a['schema']=='open-stamp-outer-pack-admission-v1' and a['approved'] is True,
         'fresh explicit single-shot approval required')
    need(a['scope']==SCOPE and a['budget_seconds']==TOTAL_SECONDS and a['retry_allowed'] is False,'scope/budget/retry')
    plan=load(verify(a['plan'])); input_pins(plan)
    need(plan['work']==str(HERE) and plan['scope']==SCOPE and plan['inputs_frozen'] is True
         and plan['baseline_commit']==BASE and plan['native_generation_AB_paused'] is True,'wrong/unfrozen plan')
    need(verify(a['runner'])==HERE/'runner.py','wrong runner')
    review=load(verify(a['review']))
    need(review['complete'] is True and review['runner']==a['runner'] and review['plan']==a['plan'],
         'review does not bind current code/plan')
    need(review['closure_reuse_safe'] is True and review['fixture_semantic_review_complete'] is True and review['file_flow_review_complete'] is True,
         'closure and fixture source review required')
    source_review=load(verify(plan['source_semantic_review']))
    need(source_review['schema']=='open-stamp-source-review-v1' and source_review['complete'] is True and source_review['blockers']==[]
         and source_review['source_files_manifest_sha256']==plan['source_files_manifest']['sha256']
         and source_review['candidate_target_sha256']==plan['candidate_target']['sha256'],'independent source/fixture review binding')
    ep=load(verify(a['epoch']))
    need(Path(a['epoch']['path'])==HERE/'coordination/lock-epoch.json','fresh job-specific epoch required')
    need(ep['schema']=='astra-lock-epoch-v1' and ep['new_epoch'] is True
         and ep['historical_continuity_claimed'] is False and ep['workspace']==str(R)
         and ep['created_for']==str(HERE)
         and ep['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'fresh current-boot epoch')
    need(ep['shared_peer_contention_passed'] is True and ep['reproduction_reacquired'] is True,'coordinator lock protocol evidence')
    need(a['locks']==[ep['shared'],ep['reproduction']],'exact fresh epoch bindings')
    need(a['locks'][0]['path']==str(R/'.astra-resource-locks/heavy.lock')
         and a['locks'][1]['path']==str(SOURCE/'.mlf-build/.reproduction.lock'),'actual shared/reproduction locks only')
    original=load(verify(plan['ordinary_environment']))
    need(a['environment']==dict(original,TMPDIR=str(HERE/'tmp')),'only bounded TMPDIR relocation allowed')
    need(a['environment']['GHC_ENVIRONMENT']=='-' and a['environment']['GHCRTS']==''
         and a['environment']['PYTHONDONTWRITEBYTECODE']=='1','environment policy')
    return a,plan


def worker_argv(digest): return [str(Path(sys.executable).resolve()),'-B',str(HERE/'runner.py'),'_worker',digest]

def claim(a): return {'schema':'open-stamp-outer-pack-single-use-claim-v1','admission':pin(HERE/'admission.json'),'retry_allowed':False}


def worker_scope(a,digest):
    return guard().verify_worker_scope(worker_argv(digest),cwd=HERE,output=HERE/'guard',
      locks=a['locks'],epoch=a['epoch'],seconds=TOTAL_SECONDS,bounded_root=HERE,
      claim_path=HERE/'claim.json',claim_expected=claim(a))


def clean_outer(row):
    need(row['complete'] is True and row['exit_code']==0 and row['reason'] is None
         and row['cleanup'] is True and row['lock_reacquired'] is True and row.get('lease_cleared') is True
         and row['test_only'] is False and row['standalone_admission'] is True
         and row['limits']==guard().LIMITS,'outer did not finish and clean up')


def production_delta(auth,plan):
    """Exact frozen outer stamp lexical changes. Does not waive baseline auth."""
    old=verify(plan['baseline_target']).read_text(); new=verify(plan['candidate_target']).read_text()
    original=auth['resolved_modules'][TARGET]
    need(sha(original['path'])==original['sha256']==plan['baseline_target']['sha256'],
         'reference OpenFragment is not exact qualified F25 source')
    delta=load(verify(plan['candidate_delta']))
    need(delta['base_commit']==BASE and delta['schema']=='open-stamp-outer-pack-edits-v2'
         and delta['guard_threshold']==1048576 and delta['max_UTF8_bytes_per_scalar']==4
         and delta['per_field_framing_upper_bound']==20
         and delta['base_sha256']==plan['baseline_target']['sha256']
         and delta['candidate_sha256']==plan['candidate_target']['sha256'],'wrong outer stamp OpenFragment delta')
    need(isinstance(delta['edits'],list) and len(delta['edits'])==1,'exactly one outer stamp edit required')
    replay=old
    for edit in delta['edits']:
        need(edit['before'] and replay.count(edit['before'])==1,'ambiguous lexical edit')
        replay=replay.replace(edit['before'],edit['after'],1)
    need(replay==new,'changes outside exact frozen stamp edit')
    need('{-# SCC' not in new and 'MLF_QUERY_PROFILE' not in new,'profiling-way instrumentation forbidden')
    return delta



def discover_closures(auth,plan):
    """Recompute every fixture mode, both OpenFragment sides, from pinned reviewed imports."""
    ordinary={**auth['resolved_modules'],**auth['resolved_host_modules']}
    package_modules=set(); units=set(auth['installed_dependencies']['packages'])
    for raw in auth['installed_dependencies']['files']:
        path=Path(raw)
        if path.suffix!='.hi':continue
        parents=[i for i,part in enumerate(path.parts) if part in units]
        if len(parents)==1:
            package_modules.add('.'.join(Path(*path.parts[parents[0]+1:]).with_suffix('').parts))
    need(package_modules,'authenticated installed-package module inventory missing')
    modes=plan['fixture_modes']
    need([m['name'] for m in modes]==['stamp'] and modes[0]['sides']==['A','B'],
         'one identical fixed driver per side required')
    production_delta(auth,plan)
    all_borrowed=set(); results={}
    for mode in modes:
        fresh_names={r['module'] for r in mode['modules']}
        need(len(fresh_names)==len(mode['modules']) and 'Main' in fresh_names and TARGET not in fresh_names,
             'duplicate/missing fixture module')
        need(not (fresh_names&set(ordinary)),'fixture shadows ordinary home module')
        for side in mode['sides']:
            fresh={r['module']:(r['source_by_side'][side] if 'source_by_side' in r else r['source']) for r in mode['modules']}
            sources=dict(ordinary,**fresh)
            sources[TARGET]=plan['baseline_target' if side=='A' else 'candidate_target']
            seen=set(); external=set(); edges={}
            def visit(name):
                if name in seen:return
                seen.add(name); row=sources[name]; text=safe(row['path']).read_text()
                need(sha(row['path'])==row['sha256'],'closure source drift')
                declaration=re.search(r'^module\s+([A-Z][A-Za-z0-9_.]*)\b',text,re.M)
                need(declaration and declaration.group(1)==name,'module identity drift')
                directives=re.findall(r'^\s*(#[^\n]*)',text,re.M)
                need('{-# SOURCE' not in text and 'TemplateHaskell' not in text and 'QuasiQuotes' not in text,
                     'unsupported source import mechanism')
                if directives:
                    cp=plan['reviewed_cpp_exception']
                    need(name=='MLF.Host.IO' and row['sha256']==cp['source_sha256']
                         and directives==cp['exact_directives'],'unreviewed CPP source')
                    need(cp['conditional_imports']==['Data.IntMap.Lazy','Data.Map.Lazy'],'CPP import alternatives changed')
                    for header in cp['header_pins']:
                        ht=verify(header).read_text(); ht=re.sub(r'/\*.*?\*/','',ht,flags=re.S)
                        need(not re.search(r'^\s*import\s+',ht,re.M),'header introduces Haskell import')
                        macros=set(re.findall(r'^\s*#\s*define\s+(\w+)',ht,re.M))
                        need(not (macros & {'import','qualified','MLF','Host','Base','Data','IntMap','Map','Lazy','M'}),
                             'header can rewrite source import identifiers')
                imports=re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][A-Za-z0-9_.]*)',text,re.M)
                need(len(imports)==len(re.findall(r'^\s*import\s+',text,re.M)),'unparsed import declaration')
                edges[name]=sorted(set(imports))
                for dep in imports:
                    if dep in sources:visit(dep)
                    else:
                        need(not dep.startswith(('Bootstrap.','MLF.')) and dep in package_modules,'unresolved home/package module')
                        external.add(dep)
            for name in [TARGET,*fresh]:visit(name)
            borrowed=sorted(seen-{TARGET,*fresh})
            need(all(not ({TARGET,*fresh}&set(edges[n])) for n in borrowed),
                 'borrowed dependency imports replaced OpenFragment/fresh fixture')
            compiled={TARGET}
            for row in mode['modules']:
                need((set(edges[row['module']])&set(fresh))<=compiled,'fixture compile order invalid')
                compiled.add(row['module'])
            result={'home_modules':sorted(seen),'borrowed_modules':borrowed,
                    'source_edges':edges,'external_import_modules':sorted(external)}
            results[side+'-'+mode['name']]=result; all_borrowed.update(borrowed)
    # All consumers of OpenFragment are fresh even if they happen to be in the producer.
    reverse=set([TARGET]); changed=True
    while changed:
        changed=False
        for name,row in ordinary.items():
            text=safe(row['path']).read_text()
            imports=set(re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][A-Za-z0-9_.]*)',text,re.M))
            if name not in reverse and imports&reverse:reverse.add(name);changed=True
    need(not (all_borrowed&reverse),'old OpenFragment or transitive consumer borrowed')
    return results


def derive_closure(auth,plan):
    results=discover_closures(auth,plan)
    need(results==plan['closures'],'reviewed exact mode closure changed')
    borrowed=sorted({name for row in results.values() for name in row['borrowed_modules']})
    need(borrowed==[r['module'] for r in plan['dependency_closure']],
         'borrowed union differs from recomputed downward closure')
    return results


def authenticate_baseline(plan):
    """Use the successful formal-r25 verifier, with its unchanged oracle/builtin gate."""
    V=module(VALIDATOR,VALIDATOR_SHA,'r27_r25_validator')
    V.initialise()  # hash-pinned original oracle/guard; only inside bounded auth child
    need(V.COMMITS['B']==BASE and V.ROOTS['B']==BASELINE,'wrong ordinary baseline')
    side=V.verify_side('B',plan['ordinary_handoff'])
    auth=side['auth']
    need(auth==load(verify(plan['producer_receipt'])),'authenticated ordinary receipt differs')
    need(side['source']==SOURCE and side['producer']==PRODUCER,'wrong ordinary source/producer')
    need(side['handoff']['environment']==plan['ordinary_environment'],'ordinary environment provenance')
    need(side['relink']['c_objects']==plan['c_objects'],'runtime C closure differs')
    derive_closure(auth,plan)
    return auth


def authenticate_child(digest,label):
    """Executed only as a bounded original-guard child of the admitted worker."""
    a,plan=validate(digest); need(label in ['before','after'],'auth phase')
    need(dict(os.environ)==a['environment'],'auth environment drift')
    # Child-specific actual guard binding; no reliance on an environment flag.
    parent=os.getppid(); argv=(Path('/proc')/str(parent)/'cmdline').read_bytes().split(b'\0')[:-1]
    need(len(argv)==4 and argv[1]==b'-B' and argv[2]==str(R13/'guard.py').encode(),'auth not a guard child')
    need(Path(os.fsdecode(argv[0])).resolve()==Path(sys.executable).resolve(),'auth guard interpreter')
    cfg=load(os.fsdecode(argv[3])); expected=[str(Path(sys.executable).resolve()),'-B',str(HERE/'runner.py'),'_authenticate',digest,label]
    need(cfg['command']==expected and cfg['nested'] is True and cfg['test_mode'] is False
         and cfg['cwd']==str(HERE) and cfg['bounded_root']==str(HERE)
         and cfg['locks']==[] and cfg['epoch'] is None and 0<cfg['seconds']<=25
         and cfg['accepted_exit_codes']==[0] and cfg['reports']==[str(HERE/('authentication-'+label+'.json'))],
         'bounded auth guard config')
    # Parent child-guard process must itself be launched by this job's worker.
    table=guard().process_table(); worker=table[parent]['ppid']
    wargv=(Path('/proc')/str(worker)/'cmdline').read_bytes().split(b'\0')[:-1]
    need(wargv==[x.encode() for x in worker_argv(digest)],'auth parent is not the admitted worker')
    result=authenticate_baseline(plan); input_pins(plan)
    save(HERE/('authentication-'+label+'.json'),result)


def strip_routing(flags):
    result=[]; i=0
    while i<len(flags):
        f=flags[i]
        if f in ['-odir','-hidir']: i+=2
        elif f=='-i' or f.startswith('-i'): i+=1
        else: result.append(f); i+=1
    need(all(result.count(f)==1 for f in ['-O2','-fpedantic-bottoms','-fno-state-hack']),'demand/optimization flags lost')
    return result


def observe_stdout(raw,mode,contract):
    need(raw and raw.endswith(b'\n') and b'\r' not in raw and len(raw)<4*1024*1024,'noncanonical/truncated output')
    lines=raw.decode('utf-8').splitlines()
    if mode=='controls':
        need(lines[-1]=='SUMMARY\t'+str(contract['controls_count']) and all(lines),'control summary/framing')
        return {'mode':mode,'controls_count':contract['controls_count']}
    need(mode=='measure' and len(lines)==36,'fixed measure rows')
    expected=[(label,size,rep) for size in [8,32,128,512] for rep in [1,2,3] for label in ['empty-before','stamp','empty-after']];rows=[]
    for line,(expected_label,size,rep) in zip(lines,expected):
        fields=line.split('\t');need(len(fields)==6,'measurement columns')
        label,sz,r,digest,allocated,elapsed=fields
        need(label==expected_label and sz==str(size) and r==str(rep),'fixed measure order')
        if label=='stamp':
            need(re.fullmatch(r'(0|[1-9][0-9]*)-(0|[1-9][0-9]*)',digest) is not None,'digest syntax')
            first,second=map(int,digest.split('-'));need(first<2147483647 and second<2147483629,'digest modulus bounds')
        else:need(digest=='-','empty observer digest')
        need(re.fullmatch(r'0|[1-9][0-9]*',allocated) and re.fullmatch(r'0|[1-9][0-9]*',elapsed),'invalid observer fields')
        rows.append({'label':label,'size':size,'repetition':rep,'digest':digest,'allocated_bytes':int(allocated),'elapsed_ns':int(elapsed)})
    return {'mode':mode,'rows':rows,'semantic_observations':[[x[k] for k in ['label','size','repetition','digest']] for x in rows],
            'empty_observers_subtracted':False,'performance_qualified':False,'emitted_review_required':True}


def compile_argv(ghc,flags,source,mod,root,*,target_dump=False):
    """One-shot only, explicit interface search, exact fresh object/interface outputs."""
    objdir=root/'objects'; interfaces=root/'interfaces'; rel=Path(mod.replace('.','/'))
    obj=objdir/rel.with_suffix('.o'); hi=interfaces/rel.with_suffix('.hi')
    argv=[ghc,*flags,'-fforce-recomp','-i','-i'+str(interfaces),'-odir',str(objdir),'-hidir',str(interfaces),
          '-ohi',str(hi),'-c',str(source),'-o',str(obj)]
    reports=[obj,hi]
    if target_dump:
        need(mod in [TARGET,'Main'],'only production target and Main capture allowed')
        prefix=root/('OpenFragment' if mod==TARGET else 'Main')
        argv+=['-ddump-simpl','-ddump-stg-final','-ddump-to-file','-ddump-file-prefix='+str(prefix)]
        reports += [Path(str(prefix)+'.dump-simpl'),Path(str(prefix)+'.dump-stg-final')]
    return argv,reports


def emitted_binding(source,mod,argv,output,outputs):
    """Whole one-shot target/Main dumps, never extra compiles or inferred costs."""
    need(mod in [TARGET,'Main'],'unapproved capture module')
    obj,hi,core,stg=outputs
    for item,label in [(core,'Tidy Core'),(stg,'Final STG:')]:
        raw=verify(item).read_bytes()
        heading=('==================== '+label+' ====================').encode()
        need(raw.count(heading)==1 and mod.encode() in raw,'missing/ambiguous complete module dump')
        need(b'{-# SCC' not in raw and b'r26.' not in raw,'instrumented dump rejected')
    return {'source':source,'module':mod,'command':list(map(str,argv)),'guard':pin(output/'guard.json'),
            'config':pin(output/'guard-config.json'),'stdout':pin(output/'stdout'),'stderr':pin(output/'stderr'),
            'object':obj,'interface':hi,'core':core,'stg_final':stg,
            'actual_one_shot_compile':True,'sharing_review_complete':False}


def runtime_module():
    # Reuse the original runtime helper unchanged, satisfying its ordinary import.
    O=module(R13/'oracles.py',ORACLE_SHA,'r27_runtime_oracle')
    previous=sys.modules.get('oracles'); sys.modules['oracles']=O
    try:return module(RUNTIME,RUNTIME_SHA,'r27_runtime_pins')
    finally:
        if previous is None:sys.modules.pop('oracles',None)
        else:sys.modules['oracles']=previous


def runtime_identity(snapshot):
    return {role:{k:v for k,v in row.items() if k!='command_auth'} for role,row in snapshot.items()}


def archived_reports(output,row,reports):
    """Original guard MOVES reports. Never read them at producer paths after return."""
    output=safe(output); requested=[safe(p) for p in reports]
    need(row.get('complete') is True and row.get('reason') is None,'no successful archive on failed command')
    need(len(set(requested))==len(requested),'duplicate requested reports')
    need(set(row['archived'])==set(map(str,requested)),'exact moved-report inventory')
    result={}
    for index,original in enumerate(requested):
        expected=output/'reports'/(str(index)+'-'+original.name)
        item=row['archived'][str(original)]
        need(verify(item)==expected,'wrong archive target/index/name')
        need(not original.exists(),'guard report was not moved')
        need(expected.stat().st_nlink==1,'archive hard link forbidden')
        result[str(original)]=dict(item,mode=expected.stat().st_mode)
    return result


def restore_report(original,archived,*,executable=False):
    """Create a pinned working COPY for later -c/interface/link/exec consumers.

    The immutable archive remains evidence. Exclusive creation preserves mode;
    a copyfile-only executable would lose +x. No fallback to an unverified old path.
    """
    original=safe(original); source=verify(archived)
    need(HERE in original.parents and original.parent.is_dir() and not original.exists(),
         'restore destination must be new within job')
    need(source!=original and source.stat().st_nlink==1,'restore source not isolated archive')
    mode=source.stat().st_mode
    if executable: need(bool(mode & 0o111),'archived binary lacks executable permission')
    with source.open('rb') as incoming, original.open('xb') as outgoing:
        shutil.copyfileobj(incoming,outgoing)
        outgoing.flush(); os.fsync(outgoing.fileno()); os.fchmod(outgoing.fileno(),mode & 0o7777)
    need(sha(original)==archived['sha256'] and original.stat().st_size==archived['bytes']
         and original.stat().st_mode==source.stat().st_mode and original.stat().st_nlink==1,
         'restored report bytes/mode differ')
    if executable: need(bool(original.stat().st_mode & 0o111),'restored binary lacks executable permission')
    return dict(pin(original),mode=original.stat().st_mode)


def work(digest):
    a,plan=validate(digest); G=guard(); scope=worker_scope(a,digest)
    need(dict(os.environ)==a['environment'],'worker environment drift')
    started=time.monotonic()
    rec={'schema':'open-stamp-outer-pack-worker-v1','complete':False,'scope':SCOPE,
      'admission':pin(HERE/'admission.json'),'worker_scope':scope,'commands':[],
      'candidate_compiler_qualified':False,'builtin_freshness_qualification':False,
      'performance_result':False,'retry_allowed':False,'restored_reports':[],'archive_pins':[],'command_artifacts':[]}
    save(HERE/'receipt.json',rec)
    RP=runtime_module()
    for name in ['commands','work','work/common','work/common/objects','work/common/c','work/A','work/B']:
        (HERE/name).mkdir(exist_ok=False)
    for side in ['A','B']:
        for sub in ['objects','interfaces']:(HERE/'work'/side/sub).mkdir()
    def recheck_working():
        for item in rec.get('copied_dependencies',[])+rec['restored_reports']+rec['archive_pins']+rec['command_artifacts']:verify(item)
        for row in rec.get('runtime_bindings',[]):need(RP.binding(row['path'])==row,'runtime binding drift')
    def command(label,argv,maximum,reports=(),*,deadline=None):
        input_pins(plan); worker_scope(a,digest); recheck_working()
        now=time.monotonic(); left=TOTAL_SECONDS-(now-started)-2; need(left>0,'total budget exhausted')
        seconds=min(maximum,left)
        if deadline is not None:
            seconds=min(seconds,deadline-now); need(seconds>0,'side fixture budget exhausted')
        output=HERE/'commands'/label
        for p in reports: need(not safe(p).exists(),'report already exists before child')
        row=G.run_child(list(map(str,argv)),cwd=HERE,output=output,seconds=seconds,
          reports=reports,bounded_root=HERE,accepted_exit_codes=(0,))
        rec['commands'].append({'label':label,'guard':row,'guard_pin':pin(output/'guard.json') if (output/'guard.json').is_file() else None})
        save(HERE/'receipt.json',rec)
        need(row.get('complete') is True and row.get('cleanup') is True and row.get('exit_code')==0
             and row.get('reason') is None and row.get('test_only') is False
             and row.get('standalone_admission') is False and row.get('locks')==[] and row.get('epoch') is None
             and row.get('lock_reacquired') is False and row.get('limits')==G.LIMITS and row.get('seconds')==seconds
             and row.get('command')==list(map(str,argv)) and row.get('cwd')==str(HERE)
             and row.get('output')==str(output) and row.get('bounded_root')==str(HERE),'bounded command failed: '+label)
        need(row['config_sha256']==sha(output/'guard-config.json'),'child config drift')
        moved=archived_reports(output,row,reports)
        rec['command_artifacts'].extend(pin(output/name) for name in ['guard.json','guard-config.json','stdout','stderr'])
        rec['archive_pins'].extend(moved.values()); save(HERE/'receipt.json',rec)
        input_pins(plan); recheck_working()
        return output,moved
    def restore(original,moved,executable=False):
        recheck_working()
        item=restore_report(original,moved[str(original)],executable=executable)
        rec['restored_reports'].append(item); recheck_working(); save(HERE/'receipt.json',rec); return original
    def runtime_snapshot(label,executables):
        # Exact r26c pattern: actual loader --list is an original-guard child.
        def remember(value):
            if isinstance(value,dict):
                if 'resolved' in value and 'sha256' in value:
                    need(RP.binding(value['path'])==value,'runtime alias/content drift')
                    if value not in rec.setdefault('runtime_bindings',[]):rec['runtime_bindings'].append(value)
                for child in value.values():remember(child)
            elif isinstance(value,list):
                for child in value:remember(child)
        result={}
        for role,executable in executables.items():
            def run(argv):
                output,_=command('runtime-'+label+'-'+role,argv,10)
                return {'stdout':(output/'stdout').read_text(),'stderr':(output/'stderr').read_text(),
                        'returncode':0,'auth':pin(output/'guard.json')}
            result[role]=RP.pin_runtime(executable,run);remember(result[role])
        save(HERE/'receipt.json',rec);return result
    def copy_interface(original,root,mod):
        dst=root/'interfaces'/Path(mod.replace('.','/')).with_suffix('.hi')
        need(not dst.exists(),'interface must be a fresh isolated copy')
        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(original,dst)
        need(sha(dst)==sha(original) and dst.stat().st_nlink==1,'interface copy differs')
        rec['copied_dependencies'].append(pin(dst))
    def compile_one(side,label,source,mod,root,maximum,*,target_dump=False):
        argv,reports=compile_argv(ghc,flags,verify(source),mod,root,target_dump=target_dump)
        input_interfaces=[pin(x) for x in sorted((root/'interfaces').rglob('*.hi'))]
        for path in reports:path.parent.mkdir(parents=True,exist_ok=True)
        output,moved=command(side+'-compile-'+label,argv,maximum,reports)
        # Reports MOVE to immutable evidence. Restore actual .o/.hi only;
        # complete raw dump archives remain canonical evidence, never recompiled.
        for path in reports[:2]:restore(path,moved)
        rec.setdefault('compile_inputs',{})[side+'-'+label]={'source':source,'interfaces':input_interfaces,
            'command':list(map(str,argv)),'guard':pin(output/'guard.json')}
        if target_dump:
            need(mod in [TARGET,'Main'],'capture module not allowed')
            key='target_builds' if mod==TARGET else 'fixture_builds'
            need(side not in rec.get(key,{}),'capture binding would be overwritten')
            rec.setdefault(key,{})[side]=dict(emitted_binding(source,mod,argv,output,[moved[str(x)] for x in reports]),
                input_interfaces=input_interfaces)
            save(HERE/'receipt.json',rec)
        return reports[:2]
    failed=None
    try:
        pre=HERE/'authentication-before.json'
        _,moved=command('01-authenticate',[sys.executable,'-B',str(HERE/'runner.py'),'_authenticate',digest,'before'],25,[pre])
        before=load(verify(moved[str(pre)]))
        need(before==load(verify(plan['producer_receipt'])),'ordinary auth data differs')
        borrowed={}; copied=[]
        for row in plan['dependency_closure']:
            need(row['module']!=TARGET,'old OpenFragment in reuse closure')
            for kind,suffix in [('object','.o'),('interface','.hi')]:
                original=verify(row[kind]); rel=Path(row['module'].replace('.','/')+suffix)
                need(original==PRODUCER/'objects'/rel and before['object_inputs']['objects/'+str(rel)]==row[kind]['sha256'],
                     'borrowed object/interface authentication')
                targets=[HERE/'work/common/objects'/rel] if kind=='object' else [HERE/'work'/side/'interfaces'/rel for side in ['A','B']]
                for dst in targets:
                    need(not dst.exists(),'borrowed destination already exists')
                    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,dst)
                    need(sha(dst)==row[kind]['sha256'] and dst.stat().st_nlink==1,'borrowed copy differs')
                    copied.append(pin(dst))
                    if kind=='object':borrowed[row['module']]=dst
        need(len(borrowed)==len(plan['dependency_closure']) and len(copied)==3*len(borrowed),'exact borrowed union size')
        c_objects=[]
        for row in plan['c_objects']:
            original=verify(row['object']);verify(row['source'])
            need(row['original_command'] in before['commands'],'C command not authenticated')
            dst=HERE/'work/common/c'/(row['label']+'.o');shutil.copyfile(original,dst)
            need(sha(dst)==row['object']['sha256'],'C copy drift');copied.append(pin(dst));c_objects.append(dst)
        need([x.name for x in c_objects]==['host.o','supervisor.o'],'exact C closure')
        rec['copied_dependencies']=copied;save(HERE/'receipt.json',rec)
        flags=strip_routing(before['flags']);need(flags==plan['retained_flags'],'producer flags drift')
        ghc=before['ghc']['path']
        runtime_exes={'python':str(Path(sys.executable).resolve()),
          'ghc':before['toolchain']['actual_ghc']['path'],'cc':before['cc']['path'],
          'ordinary-r25':before['outputs']['emlf']['path']}
        rec['runtime_before']=runtime_snapshot('before',runtime_exes)
        side_results={};target_files={}
        for side in ['A','B']:
            root=HERE/'work'/side
            target_files[side]=compile_one(side,'target',plan['baseline_target' if side=='A' else 'candidate_target'],TARGET,root,90,target_dump=True)
            mode=plan['fixture_modes'][0];label=side+'-stamp';mode_root=root/'stamp'
            mode_root.mkdir();(mode_root/'objects').mkdir();(mode_root/'interfaces').mkdir()
            closure=plan['closures'][label]
            for row in plan['dependency_closure']:
                if row['module'] in closure['borrowed_modules']:
                    copy_interface(root/'interfaces'/Path(row['module'].replace('.','/')).with_suffix('.hi'),mode_root,row['module'])
            copy_interface(target_files[side][1],mode_root,TARGET)
            fresh_objects=[target_files[side][0]]
            for item in mode['modules']:
                obj,hi=compile_one(side,'fixture-'+item['module'],item['source_by_side'][side] if 'source_by_side' in item else item['source'],item['module'],mode_root,20,target_dump=(item['module']=='Main'))
                fresh_objects.append(obj)
            dependencies=[borrowed[name] for name in closure['borrowed_modules']]
            link_objects=[*fresh_objects,*dependencies,*c_objects]
            expected={target_files[side][0],*[mode_root/'objects'/Path(x['module'].replace('.','/')).with_suffix('.o') for x in mode['modules']],*dependencies,*c_objects}
            need(len(dependencies)==46 and len(mode['modules'])==4 and len(link_objects)==len(set(link_objects))==53
                 and set(link_objects)==expected,'exact stamp link closure')
            need(sum(p.name=='OpenFragment.o' for p in link_objects)==1,'exactly one side OpenFragment object required')
            need(not any(p.name=='Main.o' for p in dependencies),'old Main borrowed')
            need(not any(PRODUCER in p.parents or HERE/'work'/('B' if side=='A' else 'A') in p.parents for p in link_objects),
                 'producer or cross-side object leaked into link')
            for path in link_objects:need(path.is_file(),'link input missing after report move')
            exe=mode_root/'stamp-fixture'
            argv=[ghc,*flags,'-rtsopts=ignoreAll',*map(str,link_objects),'-o',str(exe)]
            _,moved=command(label+'-link',argv,20,[exe]);restore(exe,moved,executable=True)
            for module_name,linked_object,build_key in [(TARGET,target_files[side][0],'target_builds'),('Main',mode_root/'objects/Main.o','fixture_builds')]:
                binding=rec[build_key][side]
                need(binding['module']==module_name and linked_object in link_objects and pin(linked_object)['sha256']==binding['object']['sha256'],'linked object differs from same-shot capture')
                for field in ['object','interface','core','stg_final']:verify(binding[field])
            one={label:str(exe)};fixture_runtime_before=runtime_snapshot(label+'-before',one)
            runs={}; fixture_started=time.monotonic(); fixture_deadline=fixture_started+30
            for run_mode in ['controls','measure']:
                output,_=command(label+'-'+run_mode,[str(exe),run_mode],30,deadline=fixture_deadline)
                need((output/'stderr').read_bytes()==b'','fixture stderr not empty')
                result=observe_stdout((output/'stdout').read_bytes(),run_mode,mode['output_contract'])
                if run_mode=='controls':need((output/'stdout').read_bytes()==verify(mode['expected_controls']).read_bytes(),'fixed controls expected bytes differ')
                runs[run_mode]={'result':result,'stdout':pin(output/'stdout'),'stderr':pin(output/'stderr')}
            fixture_elapsed=time.monotonic()-fixture_started
            need(fixture_elapsed<=30,'side fixture budget exceeded')
            rec.setdefault('fixture_budgets',{})[side]={'seconds':30,'elapsed_seconds':fixture_elapsed,
                'shared_modes':['controls','measure'],'includes_intervening_checks_and_parsing':True}
            fixture_runtime_after=runtime_snapshot(label+'-after',one)
            need(runtime_identity(fixture_runtime_before)==runtime_identity(fixture_runtime_after),'fixture runtime drift')
            side_results[side]={'runs':runs,'executable':pin(exe),'link_objects':[pin(x) for x in link_objects],
                'target_build':rec['target_builds'][side],'fixture_build':rec['fixture_builds'][side],'runtime_before':fixture_runtime_before,'runtime_after':fixture_runtime_after}
            need(pin(target_files[side][0])['sha256']==rec['target_builds'][side]['object']['sha256'],'linked OpenFragment differs from bound object/capture')
            rec['sides']=side_results;save(HERE/'receipt.json',rec)
        need(verify(side_results['A']['runs']['controls']['stdout']).read_bytes()==verify(side_results['B']['runs']['controls']['stdout']).read_bytes(),'A/B controls differ')
        need(side_results['A']['runs']['measure']['result']['semantic_observations']==side_results['B']['runs']['measure']['result']['semantic_observations'],'A/B measurement semantic observations differ')
        post=HERE/'authentication-after.json'
        _,moved=command('99-authenticate',[sys.executable,'-B',str(HERE/'runner.py'),'_authenticate',digest,'after'],25,[post])
        need(load(verify(moved[str(post)]))==before,'full baseline producer changed')
        rec['runtime_after']=runtime_snapshot('after',runtime_exes)
        need(runtime_identity(rec['runtime_before'])==runtime_identity(rec['runtime_after']),'toolchain/runtime drift')
        recheck_working();input_pins(plan);worker_scope(a,digest)
        rec['complete']=True;rec['baseline_post_authentication']=True;rec['A_B_control_bytes_equal']=True;rec['A_B_measure_semantics_equal']=True;rec['performance_qualified']=False
        rec['direct_api_screen_only']=True;rec['emitted_diagnostic_review_complete']=False;rec['Foundation_representativeness_established']=False
    except BaseException as e:
        failed=e; rec['error']=repr(e)
    finally:
        try: input_pins(plan); rec['final_input_pins_unchanged']=True
        except BaseException as e:
            rec['final_input_pins_unchanged']=False; rec['final_pin_error']=repr(e); rec['complete']=False
            if failed is None: failed=e
        rec['elapsed_seconds']=time.monotonic()-started; save(HERE/'receipt.json',rec)
    if failed is not None: raise failed


def launch(digest):
    a,plan=validate(digest); G=guard()
    need(not (HERE/'claim.json').exists() and not (HERE/'receipt.json').exists(),'single-shot scope already consumed')
    need(not G.epoch_active_path(a['locks'],a['epoch']).exists()
         and not G.epoch_quarantine_path(a['locks'],a['epoch']).exists(),'epoch active or quarantined')
    (HERE/'tmp').mkdir(exist_ok=False)
    with (HERE/'claim.json').open('x') as f: json.dump(claim(a),f); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.environ.clear(); os.environ.update(a['environment'])
    result=G.run_guard(worker_argv(digest),cwd=HERE,output=HERE/'guard',locks=a['locks'],epoch=a['epoch'],
      seconds=TOTAL_SECONDS,test_mode=False,bounded_root=HERE)
    save(HERE/'outer-result.json',result); clean_outer(result)
    receipt=load(HERE/'receipt.json'); need(receipt['complete'] is True,'worker incomplete')
    need(result['command']==worker_argv(digest) and result['cwd']==str(HERE)
         and result['output']==str(HERE/'guard') and result['bounded_root']==str(HERE)
         and result['seconds']==TOTAL_SECONDS and result['epoch']==a['epoch'] and result['locks']==a['locks'],'final outer binding drift')
    input_pins(plan)
    for item in receipt.get('copied_dependencies',[])+receipt['restored_reports']+receipt['archive_pins']+receipt['command_artifacts']:
        verify(item)
    RP=runtime_module()
    for binding in receipt.get('runtime_bindings',[]):
        need(RP.binding(binding['path'])==binding,'post-outer read-only runtime binding drift')
    need(not G.epoch_active_path(a['locks'],a['epoch']).exists()
         and not G.epoch_quarantine_path(a['locks'],a['epoch']).exists(),'post-outer epoch not clear')
    save(HERE/'final.json',{'complete':True,'scope':SCOPE,'worker':pin(HERE/'receipt.json'),
      'outer':pin(HERE/'guard/guard.json'),'candidate_compiler_qualified':False,
      'builtin_freshness_qualification':False,'performance_result':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('mode',choices=['launch','_worker','_authenticate']); parser.add_argument('admission_sha256'); parser.add_argument('label',nargs='?')
    args=parser.parse_args()
    if args.mode=='_authenticate': authenticate_child(args.admission_sha256,args.label)
    else: (launch if args.mode=='launch' else work)(args.admission_sha256)
