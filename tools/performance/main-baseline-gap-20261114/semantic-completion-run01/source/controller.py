#!/usr/bin/python3
"""Disabled explicit completion of the failed main12 qualification. No performance sampling is implemented.
The accepted SETUP scope remains the bounded root; this append-only child scope
uses its own fresh epoch/admission and original immutable guard. READY-only copy
is permitted only after complete independent source review.
"""
from pathlib import Path
import argparse, datetime, fcntl, hashlib, json, os, re, shutil, stat, subprocess, sys, time, types
R = Path('<EXPERIMENT_ROOT>')
PB = R/'main-gap-semantic-completion-v2-source'
E = R/'main-gap-setup-run04'
WORK = E/'semantic-completion-01'
FAILED = E/'semantic-qualification-01'
READY = False
CONFIG_SHA = '671ea34137976bb255aad7ca4ea88b3a84aac20bd5b538520dd9bfbcdda3ed5b'
BUDGETS = {'COMPLETION':180}
MAX_NS = 180 * 10**9
POST_SETUP_MAX_NS = 1800 * 10**9
HEADROOM_NS = 5 * 10**9
PACKAGES = ['base','array','bytestring','text','containers','directory']
ALLOWED_ENV = {'HOME','PATH','LD_LIBRARY_PATH','LC_ALL','LANG','TZ','GHC_ENVIRONMENT','GHCRTS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MAKEFLAGS','PYTHONDONTWRITEBYTECODE','TMPDIR','CC','TC','LIBRARY_PATH','PKG_CONFIG_PATH'}
FORBIDDEN_ENV = {'MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT','LD_PRELOAD','LD_AUDIT','LD_DEBUG','LD_DEBUG_OUTPUT','LD_PROFILE','LD_ASSUME_KERNEL','GLIBC_TUNABLES','GHC_PACKAGE_PATH','GHC_CHARENC','HPCTIXFILE'}
WORKER_OUTPUT_DIRS = ('commands','stats','ghc')


def require(value, message):
    if not value:
        raise RuntimeError(message)



def safe(value, *, existing=False):
    p = Path(value)
    require(p.is_absolute() and '..' not in p.parts, 'absolute non-traversing path required')
    for q in [p, *p.parents]:
        require(not q.is_symlink(), 'symlink path forbidden: ' + str(q))
    if existing:
        require(p.exists(), 'missing path: ' + str(p))
    return p



def sha(path):
    p = safe(path, existing=True)
    require(p.is_file(), 'regular file required')
    with p.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()



def pin(path):
    p = safe(path, existing=True)
    return {'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size}



def verify_pin(item):
    p = safe(item['path'], existing=True)
    require(sha(p) == item['sha256'], 'pin mismatch: ' + str(p))
    if 'bytes' in item:
        require(type(item['bytes']) is int and p.stat().st_size == item['bytes'], 'pin length mismatch')
    return p



def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(safe(path, existing=True).read_text(), object_pairs_hook=unique)



def save(path, value):
    p = safe(path)
    temporary = p.with_name(p.name + '.tmp')
    require(not os.path.lexists(temporary), 'temporary output already exists')
    with temporary.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(p)



def module(path, name):
    result = types.ModuleType(name)
    result.__file__ = str(path)
    exec(compile(Path(path).read_bytes(), str(path), 'exec'), result.__dict__)
    return result



def source_check(c):
    source = c['source']
    git = c['git']['path']
    def query(*args):
        return subprocess.check_output([git,'-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false',
                                        '-C',source,*args], text=True, env=load(c['environment']['path']))
    require(query('rev-parse','HEAD').strip() == c['source_commit'] and
            query('rev-parse','HEAD^{tree}').strip() == c['source_tree'], 'main commit/tree differs')
    require(query('status','--porcelain=v1','--untracked-files=no') == '', 'tracked source dirty')
    require(set(query('ls-files','-z').rstrip('\0').split('\0')) ==
            {r['relative'] for r in load(c['source_inventory']['path'])}, 'tracked inventory differs')
    require(query('ls-files','--others','--exclude-standard','-z') == '', 'unexpected untracked source input')
    # The only new source-local control file is the ignored real reproduction lock.
    ignored = query('ls-files','--others','--ignored','--exclude-standard','-z').rstrip('\0')
    require(not ignored or ignored.split('\0') == ['.mlf-build/.reproduction.lock'], 'unexpected ignored source artifacts')



def row_sha(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,separators=(',',':')).encode()).hexdigest()



def resource_snapshot(c, guard):
    # Observe real active processes, not absence of old quarantined metadata.
    rows = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) == os.getpid():
            continue
        try:
            parts = (p/'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
            words = [os.fsdecode(x) for x in parts if x]
            base = Path(words[0]).name if words else ''
            heavy = bool(re.fullmatch(r'(?:ghc(?:-.*)?|ghc-iserv.*|cc1(?:plus)?|clang(?:-.*)?|emlf|stats-emlf|mlfpkg|builtin-prelude|source-smoke)',base))
            heavy = heavy or any(Path(w).name in {'guard.py','resource_watchdog.py'} for w in words[1:] if w.startswith('/'))
            if heavy:
                rows.append({'pid':int(p.name),'argv':words})
        except (FileNotFoundError,ProcessLookupError):
            pass
    available = guard.available_memory(); disk = shutil.disk_usage(WORK).free
    require(not rows, 'unknown/live heavy incumbent: '+repr(rows))
    require(available >= guard.LIMITS['host_available'] and disk >= guard.LIMITS['free_disk'], 'current resource floor failed')
    return {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'monotonic_ns':time.monotonic_ns(),'host_available_bytes':available,'disk_free_bytes':disk,'heavy_incumbents':rows}



def completed_epoch_identity(ep, work, phase):
    """Identity only, after exact historical epoch pin and final cleanup binding.
    Not an admission and never a substitute for the live current-boot gate.
    """
    require(type(ep['boot_id']) is str and ep['boot_id'] and ep['schema']=='astra-lock-epoch-v1'
            and ep['created_for']==str(work) and ep['workspace']==str(R) and ep['phase']==phase,
            'historical completed epoch identity differs')



def interface(text, identity, modules, dependencies):
    lines=text.splitlines();require(lines and lines[0]=='crate '+identity,'interface crate')
    owners=[x[7:] for x in lines if x.startswith('module ')]
    require(len(owners)==len(modules) and set(owners)==set(modules),'all module owners required')
    deps=[x[11:].split(' ',1) for x in lines if x.startswith('dependency ')]
    require(all(len(x)==2 and ' ' in x[1] for x in deps),'dependency grammar')
    found=[(n,tail.rsplit(' ',1)[0]) for n,tail in deps]
    require(len(found)==len(dependencies) and dict(found)==dependencies,'dependency identities/paths')



def tree_pins(folder, strict_new=True):
    result=[]
    seen=set();root=safe(folder,existing=True);require(root.is_dir(),'artifact tree root')
    for p in sorted(folder.rglob('*')):
        st=p.lstat();require(not stat.S_ISLNK(st.st_mode),'output symlink forbidden')
        require(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode),'nonregular output forbidden')
        if stat.S_ISREG(st.st_mode):
            require(not strict_new or (st.st_nlink==1 and (st.st_dev,st.st_ino) not in seen),'new output hardlink/alias forbidden')
            seen.add((st.st_dev,st.st_ino));result.append(pin(p))
    return result


def directory_paths(root):
    result=[]
    for p in sorted(safe(root,existing=True).rglob('*')):
        st=p.lstat();require(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode),'artifact tree special type')
        if stat.S_ISDIR(st.st_mode):result.append(str(p.relative_to(root)))
    return result



def runtime_module(c):
    # Existing read-only runtime helper uses only these two oracles names.
    original=sys.modules.get('oracles')
    shim=types.ModuleType('oracles');shim.require=require;shim.PACKAGES=PACKAGES
    try:
        sys.modules['oracles']=shim
        return module(verify_pin(c['runtime_helper']),'exact_runtime_helper')
    finally:
        if original is None: sys.modules.pop('oracles',None)
        else: sys.modules['oracles']=original


def configuration():
    require(sha(PB/'BINDINGS.json')==CONFIG_SHA,'final frozen bindings changed/unbound')
    c=load(PB/'BINDINGS.json')
    require(c['schema']=='main-gap-completion-disabled-bindings-v1' and c['READY'] is False and c['configuration_complete'] is True
            and c['stage']=='COMPLETION' and c['setup_work']==str(E) and c['work']==str(WORK)
            and c['outer_cap_seconds']==180 and c['cleanup_inclusive_max_ns']==MAX_NS
            and c['post_setup_total_ns']==POST_SETUP_MAX_NS and type(c['post_setup_prior_ns']) is int
            and c['post_setup_prior_ns']==596647140326 and c['command_count']==12 and c['statistics_count']==2
            and c['performance_sample_count']==0 and c['sampling_runner_included'] is False,
            'exact separate completion scope required')
    require(c['failure_review'] is not None and c['setup_review'] is not None,'genuine independent prior evidence unbound')
    return c


def source_gate(review_pin):
    r=load(verify_pin(review_pin))
    require(r['schema']=='main-gap-completion-source-review-v1' and r['complete'] is True
            and r['source_gate_passed'] is True and r['blockers']==[],'complete independent source review required')
    require(verify_pin(r['source_package_manifest'])==PB/'MANIFEST.json','single source package identity')
    rows=load(PB/'MANIFEST.json')['files']
    require(len(rows)==len({x['path'] for x in rows}) and str(PB/'controller.py') in {x['path'] for x in rows},'source inventory')
    for item in rows:require(verify_pin(item).is_relative_to(PB),'source manifest escaped package')
    original=(PB/'controller.py').read_text()
    require(original.count('\nREADY = False\n')==1 and Path(__file__)==WORK/'controller.py'
            and Path(__file__).read_text()==original.replace('\nREADY = False\n','\nREADY = True\n',1),
            'exact READY-only activation required')
    require((WORK/'controller.disabled.py').read_bytes()==(PB/'controller.py').read_bytes(),'disabled snapshot required')
    return r


def inventory(item):
    rows=load(verify_pin(item))
    require(type(rows) is list and rows and all(type(x) is dict and set(x)=={'path','sha256','bytes'} for x in rows),'full pin inventory array')
    require(len(rows)==len({x['path'] for x in rows}),'duplicate inventory path')
    for row in rows:
        require(type(row['bytes']) is int and row['bytes']>=0 and re.fullmatch('[0-9a-f]{64}',row['sha256']), 'invalid full pin')
        verify_pin(row)
    return rows


def accepted_setup(c):
    r=load(verify_pin(c['setup_review']))
    require(r['schema']=='main-gap-setup-actual-review-v1' and r['complete'] is True
            and r['actual_SETUP_passed'] is True and r['setup_qualified'] is True and r['blockers']==[]
            and r['cleanup_lease_locks'] is True and r['source_commit']==c['source_commit'], 'genuine accepted SETUP required')
    require(r['configuration']==c['setup_configuration'] and r['immutable_inventory_format']=='json-array-of-full-pins-v1', 'SETUP configuration/inventory contract')
    p=r['actual_pins'];require(set(p)=={'controller','outer','worker','admission','claim','config'},'exact actual SETUP pin roles')
    paths={'controller':E/'setup/controller.json','outer':E/'setup/outer/guard.json','worker':E/'setup/setup-receipt.json',
        'admission':E/'coordination/SETUP-admission.json','claim':E/'claims/SETUP.json','config':E/'setup/outer/guard-config.json'}
    for k in paths:require(verify_pin(p[k])==paths[k],'actual SETUP path role '+k)
    controller,outer,worker,a,claim,cfg=[load(p[k]['path']) for k in ['controller','outer','worker','admission','claim','config']]
    require(controller['complete'] is True and controller['phase']=='SETUP' and controller['setup_receipt']==p['worker']
            and controller['outer']==p['outer'] and controller['admission']==p['admission']
            and controller['configuration']==r['configuration'] and worker['configuration']==r['configuration']
            and worker['complete'] is True and worker['admission']==p['admission'] and worker['source_commit']==c['source_commit'], 'same actual SETUP receipts')
    require(claim=={'phase':'SETUP','admission':p['admission'],'retry_allowed':False},'original SETUP claim')
    ep=load(verify_pin(a['epoch']));completed_epoch_identity(ep,E,'SETUP')
    require(controller['epoch']==a['epoch']==outer['epoch'] and controller['locks']==a['locks']==outer['locks']
            and outer['complete'] is True and outer['exit_code']==0 and outer['reason'] is None
            and all(outer[x] is True for x in ['cleanup','lock_reacquired','lease_cleared','standalone_admission'])
            and outer['test_only'] is False and outer['bounded_root']==str(E) and outer['seconds']==600
            and outer['config_sha256']==p['config']['sha256'] and outer['command']==controller['command']==cfg['command']
            and cfg['epoch']==a['epoch'] and cfg['locks']==a['locks'] and cfg['bounded_root']==str(E), 'historical completed SETUP cleanup/guard linkage')
    e=controller['guard_envelope'];require(e['schema']=='main-gap-setup-guard-envelope-v1' and e['clock']=='monotonic_ns'
            and e['guard_call_returned'] is True and all(type(e[k]) is int for k in ['start_ns','return_ns','elapsed_ns'])
            and 0<=e['start_ns']<=e['return_ns'] and e['elapsed_ns']==e['return_ns']-e['start_ns']
            and e['elapsed_ns']==r['elapsed_ns']==r['cumulative_ns'] and e['elapsed_ns']<=600*10**9
            and e['outer']==p['outer'] and e['admission']==p['admission'] and e['returned_guard_sha256']==row_sha(outer), 'actual completed SETUP cleanup-inclusive ns')
    wd=load(verify_pin(controller['original_watchdog']))
    require(wd['complete'] is True and wd['exit_code']==0 and wd['reason'] is None and wd['samples'][-1]['group_rss']==0, 'completed SETUP watchdog')
    ins=inventory(r['immutable_inputs']);outs=inventory(r['immutable_outputs'])
    require(len(ins)==r['immutable_input_count'] and len(outs)==r['immutable_output_count']
            and outs==sorted(worker['outputs'],key=lambda x:x['path']), 'complete exact SETUP inventories')
    require(r['original_binary']==c['original_binary'] and r['stats_binary']==c['stats_binary']
            and verify_pin(r['stats_binary'])==E/'setup/stats-emlf', 'actual executing binaries required')
    verify_pin(r['original_binary']);require(worker['stats_relink']['binary']==r['stats_binary'], 'own stats relink binary')
    return {'review':r,'actual_pins':p,'worker':worker,'immutable_inputs':ins,'immutable_outputs':outs,
            'original_binary':r['original_binary'],'stats_binary':r['stats_binary']}


def verify_setup_static(c, accepted):
    r=accepted['review']
    verify_pin(c['setup_review']);verify_pin(r['configuration']);verify_pin(r['immutable_inputs']);verify_pin(r['immutable_outputs'])
    for item in [*accepted['actual_pins'].values(),*accepted['immutable_inputs'],*accepted['immutable_outputs']]:verify_pin(item)
    # Historical static artifact roots, never the append-only parent scope as a whole.
    expected=sorted(accepted['immutable_outputs'],key=lambda x:x['path']);actual=[]
    for name in ['dependencies','builtin-work','ordinary-reference','stats-main','ghc-control','commands']:actual+=tree_pins(E/'setup'/name,strict_new=False)
    actual+=[pin(E/'setup'/name) for name in ['stats-emlf','builtin.mlfci','builtin.mlfco','builtin.lock']]
    require(sorted(actual,key=lambda x:x['path'])==expected,'SETUP static output file-set changed')
    verify_setup_scope(c,hash_files=True)


def verify_setup_scope(c,hash_files=False):
    require(safe(E,existing=True).is_dir(),'real historical SETUP root required')
    base=load(verify_pin(c['setup_scope_inventory']));r=load(verify_pin(c['failure_review']))
    old=load(verify_pin(r['scope_inventory']));subdirs=load(verify_pin(r['scope_directories']))
    require(base['root']==str(E) and base['allowed_new_root']==str(FAILED) and base['baseline_active_entries']==[], 'original completed SETUP boundary')
    require(type(old) is list and type(subdirs) is list and subdirs==sorted(set(subdirs)),'old failure complete inventory format')
    for p in old:require(set(p)=={'path','bytes','sha256'} and safe(p['path']).is_relative_to(FAILED),'old Q inventory escaped')
    for p in subdirs:require(type(p) is str and p not in ('','.') and not Path(p).is_absolute() and '..' not in Path(p).parts,'old Q directory spelling')
    allpins=[{k:p[k] for k in ['path','bytes','sha256']} for p in base['files']]+old
    names=sorted(str(Path(p['path']).relative_to(E)) for p in allpins)
    dirs=sorted(base['directories']+['active/cells',str(FAILED.relative_to(E))]+[str(FAILED.relative_to(E)/p) for p in subdirs])
    require(len(names)==len(set(names)) and len(dirs)==len(set(dirs)),'old E inventory duplicates')
    actual=[];actualdirs=[]
    for root,children,files in os.walk(E,followlinks=False):
        parent=Path(root)
        for name in list(children):
            p=parent/name;require(stat.S_ISDIR(p.lstat().st_mode),'old E directory type')
            if p==WORK:children.remove(name);continue
            actualdirs.append(str(p.relative_to(E)))
            if p==E/'active/cells':children.remove(name)
        for name in files:
            p=parent/name;require(stat.S_ISREG(p.lstat().st_mode),'old E file type');actual.append(str(p.relative_to(E)))
    require(sorted(actual)==names and sorted(actualdirs)==dirs,'preserved E file/directory additions or deletions')
    if hash_files:
        for p in allpins:verify_pin(p)
    return allpins


def live_scope_structure(current_cell=None,final=False):
    """Positive new-scope names; contents are separately pinned after their owner finishes.
    Watchdog's one atomic temporary receipt is live, never a worker byte oracle.
    """
    require(current_cell in (None,'foundation14'),'only the named Foundation scratch may be mutable')
    require(safe(WORK,existing=True).is_dir(),'real child scope root required')
    roots={'controller.py':'f','controller.disabled.py':'f','activation.json':'f','coordination':'d','claims':'d','tmp':'d',
        'launch-binding.json':'f','controller.json':'f','controller.json.tmp':'f','bounded-receipt.json':'f',
        'bounded-receipt.json.tmp':'f','build.log':'f','outer':'d','completion-receipt.json':'f','completion-receipt.json.tmp':'f',
        **{name:'d' for name in WORKER_OUTPUT_DIRS}}
    for p in WORK.iterdir():
        try:st=p.lstat()
        except FileNotFoundError:
            require(p.name=='bounded-receipt.json.tmp','unexpected disappearing scope entry');continue
        require(p.name in roots,'unknown new-scope root '+p.name)
        require((stat.S_ISDIR(st.st_mode) if roots[p.name]=='d' else stat.S_ISREG(st.st_mode) and st.st_nlink==1),'new-scope root type/alias')
    for dirname,names in [('coordination',{'COMPLETION-prepare-attempt.json','COMPLETION-epoch.json','COMPLETION-admission.json'}),('claims',{'COMPLETION.json'})]:
        folder=WORK/dirname
        if folder.exists():
            for p in folder.iterdir():
                st=p.lstat();require(p.name in names and stat.S_ISREG(st.st_mode) and st.st_nlink==1,'unexpected coordinator file')
    outer=WORK/'outer'
    if outer.exists():
        allowed={'stdout','stderr','guard-config.json','guard.json','reports'}
        require({p.name for p in outer.iterdir()}<=allowed,'unknown outer lifecycle file')
        if final:require({p.name for p in outer.iterdir()}==allowed,'complete final outer inventory')
        for p in outer.iterdir():
            st=p.lstat()
            if p.name=='reports':require(stat.S_ISDIR(st.st_mode) and not list(p.iterdir()),'outer has no requested reports')
            else:require(stat.S_ISREG(st.st_mode) and st.st_nlink==1,'outer lifecycle file type/alias')
    if final:
        require(all(not (WORK/name).exists() for name in ['controller.json.tmp','bounded-receipt.json.tmp','completion-receipt.json.tmp']), 'final lifecycle temporary file')
    require((WORK/'tmp').is_dir() and not list((WORK/'tmp').iterdir()),'completed child temporary directory must be empty')
    active=safe(E/'active',existing=True);allowed={'cells'} if (active/'cells').exists() else set()
    require({p.name for p in active.iterdir()}==allowed,'unexpected active root or unarchived stats sink')
    if (active/'cells').exists():
        require((active/'cells').is_dir() and not (active/'cells').is_symlink(),'active cells type')
        children=list((active/'cells').iterdir())
        require({p.name for p in children}==({current_cell} if current_cell else set()),'only the single current cell may be live')
        for p in children:require(p.is_dir() and not p.is_symlink(),'active cell directory type')
    else:require(current_cell is None,'missing current cell root')


def verify_setup_file_set(accepted):
    """Names/ownership only; caller rehashes the unique union of all full pins.
    Do not redundantly hash the 6393-entry inventory twice per child command.
    """
    paths=[]
    for name in ['dependencies','builtin-work','ordinary-reference','stats-main','ghc-control','commands']:
        root=safe(E/'setup'/name,existing=True);require(root.is_dir(),'static setup output root')
        for p in root.rglob('*'):
            require(not p.is_symlink(),'setup output symlink')
            if p.is_file():paths.append(str(p))
            else:require(p.is_dir(),'unexpected setup output type')
    paths += [str(safe(E/'setup'/name,existing=True)) for name in ['stats-emlf','builtin.mlfci','builtin.mlfco','builtin.lock']]
    require(sorted(paths)==sorted(p['path'] for p in accepted['immutable_outputs']),'SETUP output names changed')


def static_inputs(c):
    source=safe(c['source'],existing=True);env=load(verify_pin(c['environment']))
    require(set(env)<=ALLOWED_ENV and all(type(k) is str and type(v) is str for k,v in env.items())
            and not (FORBIDDEN_ENV & set(os.environ)), 'explicit unprofiled environment')
    expected={'GHC_ENVIRONMENT':'-','GHCRTS':'','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(WORK/'tmp'),
        'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MAKEFLAGS':'-j1','CC':c['cc']['path']}
    require(all(env.get(k)==v for k,v in expected.items()) and all(k in env for k in ['HOME','PATH']), 'semantic environment differs')
    require(Path(sys.executable).resolve()==Path(c['python']['path'])==Path('/usr/bin/python3').resolve(),'Python interpreter differs')
    require(c['guard']['sha256']=='53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e','immutable guard required')
    for item in c['source_inputs']:verify_pin(item)
    for key in ['guard','python','git','ghc','cc','environment','history','runtime_paths','global_packages','runtime_helper','stats_parser','worker','publication_oracle','semantic_parsers','identity_helper','plan_commands','plan_manifest','workload_manifest']:verify_pin(c[key])
    rows=load(verify_pin(c['source_inventory']));require(len(rows)==3876 and len({r['relative'] for r in rows})==3876,'complete fresh main source inventory')
    for r in rows:
        p=safe(source/r['relative'],existing=True);require(p.is_relative_to(source) and p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
            and ('100755' if p.stat().st_mode & 0o111 else '100644')==r['mode'],'source file changed')
    runtime=load(c['runtime_paths']['path'])
    for row in runtime['bindings']:
        p=Path(row['path']);require(str(p.resolve(strict=True))==row['resolved'],'runtime resolution changed')
        links=[{'path':str(q),'target':os.readlink(q)} for q in [*reversed(p.parents),p] if q.is_symlink()]
        require(links==row['links'] and verify_pin(row['file'])==p.resolve(),'runtime binding changed')
    for path,files in runtime['directories'].items():require(sorted(str(p) for p in Path(path).iterdir())==files,'loader directory changed')
    require(all(not os.path.lexists(p) for p in runtime['required_absent']),'unexpected loader preload')
    gp=load(c['global_packages']['path']);require(sorted(str(p) for p in Path(gp['directory']).iterdir())==gp['entries'],'global package inventory changed')
    for row in gp['files']:verify_pin(row)
    history=load(c['history']['path']);require(len(history['files'])==8 and history['old_cleanup_claimed'] is False,'historical boundary')
    for row in history['files']:verify_pin(row)
    for route in c['cell_route_contracts'].values():
        require(route['route_format_source_evidence'] is not None and route['config'][-1] is None and route['checked_schema']==8,'pre-reviewed route-observation contract unbound')
        verify_pin(route['route_format_source_evidence'])
    return source,env


def envelope_ns(e):
    require(e['schema']=='main-gap-completion-guard-envelope-v1' and e['clock']=='monotonic_ns' and e['guard_call_returned'] is True,'returned monotonic envelope required')
    require(all(type(e[k]) is int for k in ['start_ns','return_ns','elapsed_ns']) and 0<=e['start_ns']<=e['return_ns']
            and e['elapsed_ns']==e['return_ns']-e['start_ns'],'integer complete envelope arithmetic')
    return e['elapsed_ns']


def entry_ns(used,phase):
    require(type(used) is int and used==596647140326 and phase=='COMPLETION' and used+MAX_NS<=POST_SETUP_MAX_NS,
            'real failed-stage duration plus complete next cap must fit unchanged total')
    return used


def deadline_fields(d,a,path,argv,now):
    require(d['schema']=='main-gap-completion-launch-binding-v1' and d['clock']=='monotonic_ns'
            and d['admission']==pin(path) and d['epoch']==a['epoch'] and d['locks']==a['locks']
            and d['command_without_binding']==argv and d['claim']==pin(WORK/'claims/COMPLETION.json')
            and d['scope']==str(WORK) and d['bounded_root']==str(E),'same-scope immutable launch binding')
    require(all(type(d[k]) is int for k in ['start_ns','deadline_ns']) and type(now) is int
            and 0<=d['start_ns']<=now<d['deadline_ns'] and d['deadline_ns']-d['start_ns']==MAX_NS-HEADROOM_NS,
            'expired/reversed/extended whole-stage deadline')
    return d


def inner_command(phase,path,digest,c,binding_sha=None):
    require(phase=='COMPLETION','single semantic phase')
    argv=[c['python']['path'],'-B',str(WORK/'controller.py'),'_completion','--admission',str(path),'--sha256',digest]
    if binding_sha is not None:
        require(re.fullmatch('[0-9a-f]{64}',binding_sha),'actual launch binding SHA')
        argv+=['--launch-binding-sha256',binding_sha]
    return argv


def command(phase,path,digest,c,binding_sha=None):
    return [c['python']['path'],'-B',str(Path(c['source'])/'tools/shared/resource_watchdog.py'),
        '--seconds','180','--address-space-mib','6144','--rss-mib','5120','--max-output-mib','2048',
        '--disk-free-mib','5120',str(WORK),*inner_command(phase,path,digest,c,binding_sha)]


def launch_binding(a,c,path,digest):
    """One immutable binding under both original locks and the unique claim.
    The original guard acquires those same locks independently after this short
    source-coordination critical section. Failure leaves the one-use claim.
    """
    handles=[]
    try:
        for item in a['locks']:
            p=safe(item['path'],existing=True);h=p.open('r+');handles.append(h)
            st=os.fstat(h.fileno());require((st.st_dev,st.st_ino)==(item['device'],item['inode']),'binding lock inode')
            fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)
        (WORK/'claims').mkdir(mode=0o700,exist_ok=True)
        with (WORK/'claims/COMPLETION.json').open('x') as f:
            json.dump({'phase':'COMPLETION','admission':pin(path),'retry_allowed':False},f);f.flush();os.fsync(f.fileno())
        start=time.monotonic_ns()
        d={'schema':'main-gap-completion-launch-binding-v1','clock':'monotonic_ns','start_ns':start,
            'deadline_ns':start+MAX_NS-HEADROOM_NS,'admission':pin(path),'epoch':a['epoch'],'locks':a['locks'],
            'claim':pin(WORK/'claims/COMPLETION.json'),'scope':str(WORK),'bounded_root':str(E),
            'command_without_binding':command('COMPLETION',path,digest,c)}
        with (WORK/'launch-binding.json').open('x') as f:
            json.dump(d,f,indent=2,sort_keys=True);f.write('\n');f.flush();os.fsync(f.fileno())
        return pin(WORK/'launch-binding.json')
    finally:
        for h in reversed(handles):h.close()


def launch(phase,path,digest):
    a,c,env,guard=validate(path,digest,phase)
    accepted=accepted_setup(c);accepted_prefix(c);verify_setup_static(c,accepted);live_scope_structure();resource_snapshot(c,guard)
    require(guard.footprint(E)<=guard.LIMITS['output'],'existing SETUP footprint already consumes outer budget')
    require(not os.path.lexists(guard.epoch_active_path(a['locks'],a['epoch'])) and
            not os.path.lexists(guard.epoch_quarantine_path(a['locks'],a['epoch'])),'new epoch blocked')
    require(not (WORK/'outer').exists() and not (WORK/'controller.json').exists(),'scope already attempted')
    binding=launch_binding(a,c,path,digest);d=load(verify_pin(binding))
    argv=command(phase,path,digest,c,binding['sha256'])
    deadline_fields(d,a,path,command(phase,path,digest,c),time.monotonic_ns())
    record={'schema':'main-gap-completion-controller-v1','phase':phase,'complete':False,
        'configuration':pin(PB/'BINDINGS.json'),'adapter':pin(__file__),'admission':pin(path),'epoch':a['epoch'],'locks':a['locks'],
        'setup_review':c['setup_review'],'setup_actual_pins':accepted['actual_pins'],'launch_binding':binding,
        'source':c['source'],'source_commit':c['source_commit'],'environment':c['environment'],'command':argv,
        'budget_seconds':180,'independent_actual_review_required':True,'continue_allowed':False,'stop_required':True,
        'performance_samples':0,'sampling_authorized':False,'native_generation_AB_fixedpoint':False,
        'failed_prefix_review':c['failure_review'],'original_stage_remains_failed':True,'combined_review_required':True}
    output=WORK/'controller.json';save(output,record);row=None
    try:
        os.environ.clear();os.environ.update(env)
        guard_start_ns=time.monotonic_ns()
        require(d['start_ns']<=guard_start_ns<d['deadline_ns'],'launch binding not before guard call')
        row=guard.run_guard(argv,cwd=Path(c['source']),output=WORK/'outer',locks=a['locks'],epoch=a['epoch'],seconds=180,bounded_root=E)
        guard_return_ns=time.monotonic_ns()
        record['guard_envelope']={'schema':'main-gap-completion-guard-envelope-v1','clock':'monotonic_ns',
            'start_ns':guard_start_ns,'return_ns':guard_return_ns,'elapsed_ns':guard_return_ns-guard_start_ns,
            'guard_call_returned':True,'scope':'entire original guard call through return, including cleanup',
            'command':argv,'admission':pin(path),'launch_binding':binding,
            'outer':pin(WORK/'outer/guard.json') if (WORK/'outer/guard.json').is_file() else None,
            'returned_guard_sha256':row_sha(row)}
        if (WORK/'outer/guard.json').is_file():record['outer']=pin(WORK/'outer/guard.json')
        save(output,record)
        n=envelope_ns(record['guard_envelope']);require(n<=MAX_NS and a['used_ns']+n<=POST_SETUP_MAX_NS,'actual cleanup-inclusive semantic budget')
        verify_pin(binding)
        require(record['outer']==record['guard_envelope']['outer'] and row_sha(load(WORK/'outer/guard.json'))==row_sha(row),'returned outer differs')
        check_outer(row,phase,argv,a,c)
        wd=load(WORK/'bounded-receipt.json')
        require(wd['complete'] is True and wd['exit_code']==0 and wd['reason'] is None and wd['samples']
                and wd['samples'][-1]['group_rss']==0 and wd['command']==inner_command(phase,path,digest,c,binding['sha256']),'original watchdog failed')
        record['original_watchdog']=pin(WORK/'bounded-receipt.json')
        validate(path,digest,phase);verify_setup_static(c,accepted);live_scope_structure(final=True)
        result=load(WORK/'completion-receipt.json')
        require(result['complete'] is True and len(result['commands'])==12 and len(result['statistics'])==2 and len(result['cells'])==1
                and result['original_suffix_ordinals']==list(range(85,92)) and result['extra_freshness_commands']==5
                and result['failed_prefix_review']==c['failure_review']
                and result['launch_binding']==binding and result['admission']==pin(path) and result['performance_samples']==0,
                'complete exact separate completion ledger required')
        require(sorted(result['outputs'],key=lambda x:x['path'])==worker_output_pins(),'positive complete worker output ownership')
        for item in result['outputs']:verify_pin(item)
        record['completion_receipt']=pin(WORK/'completion-receipt.json')
        require(not guard.epoch_active_path(a['locks'],a['epoch']).exists() and not guard.epoch_quarantine_path(a['locks'],a['epoch']).exists(),'new epoch not cleaned')
        record['complete']=True
    except BaseException as error:
        record.update(complete=False,error=repr(error));raise
    finally:
        valid=False;n=None;total=None
        try:n=envelope_ns(record['guard_envelope']);total=a['used_ns']+n;valid=True
        except (KeyError,TypeError,ValueError,RuntimeError):pass
        record['budget']={'elapsed_valid':valid,'elapsed_ns':n,'prior_ns':a['used_ns'],'cumulative_ns':total,
            'stage_maximum_ns':MAX_NS,'post_setup_maximum_ns':POST_SETUP_MAX_NS,
            'budget_passed':valid and n<=MAX_NS and total<=POST_SETUP_MAX_NS,'includes_outer_cleanup_time':True,
            'original_guard_elapsed_seconds_excludes_cleanup':row.get('elapsed_seconds') if row else None}
        record['stop_required']=True;save(output,record)
    return record


def semantic(path,digest,binding_sha):
    require(re.fullmatch('[0-9a-f]{64}',binding_sha),'actual launch binding required')
    binding=pin(WORK/'launch-binding.json');require(binding['sha256']==binding_sha,'launch binding differs from actual outer argv')
    a,c,env,guard=validate(path,digest,'COMPLETION');require(dict(os.environ)==env,'exact semantic environment')
    require(load(WORK/'claims/COMPLETION.json')=={'phase':'COMPLETION','admission':pin(path),'retry_allowed':False},'single claim')
    verify_qualifier_scope(a,c,guard,path,digest,binding_sha)
    d=deadline_fields(load(verify_pin(binding)),a,path,command('COMPLETION',path,digest,c),time.monotonic_ns())
    accepted=accepted_setup(c)
    impl=module(verify_pin(c['worker']),'pinned_semantic_worker')
    worker=impl.Completion(sys.modules[__name__],c,a,env,guard,path,digest,accepted,accepted_prefix(c),d,
        module(verify_pin(c['publication_oracle']),'pinned_semantic_publication'),
        module(verify_pin(c['semantic_parsers']),'pinned_semantic_parsers'),
        module(verify_pin(c['stats_parser']),'exact_external_stats_parser'),runtime_module(c),module(verify_pin(c['identity_helper']),'completion_identity'))
    worker.record['launch_binding']=binding
    try:
        worker.run();validate(path,digest,'COMPLETION');verify_qualifier_scope(a,c,guard,path,digest,binding_sha)
        verify_pin(binding);require(time.monotonic_ns()<d['deadline_ns'],'worker complete within shared deadline')
    except BaseException as error:
        worker.record.update(complete=False,error=repr(error));worker.save();raise


def main():
    require(READY,'READY=False: disabled semantic source; no admission/execution permitted')
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('phase',choices=list(BUDGETS))
    p.add_argument('--source-review',type=Path,required=True);p.add_argument('--source-review-sha256',required=True)
    r=sub.add_parser('run');r.add_argument('phase',choices=list(BUDGETS));w=sub.add_parser('_completion')
    for p in [r,w]:p.add_argument('--admission',type=Path,required=True);p.add_argument('--sha256',required=True)
    w.add_argument('--launch-binding-sha256',required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        review=pin(args.source_review);require(review['sha256']==args.source_review_sha256,'source review SHA')
        prepare(args.phase,review,configuration()['failure_review'])
    elif args.command=='_completion':semantic(args.admission,args.sha256,args.launch_binding_sha256)
    else:print(json.dumps(launch(args.phase,args.admission,args.sha256),indent=2,sort_keys=True))




def worker_output_pins():
    result=[]
    for name in WORKER_OUTPUT_DIRS:
        rows=tree_pins(WORK/name);require(rows,'missing worker output root');result+=rows
    require(len(result)==len({r['path'] for r in result}),'duplicate worker output')
    return sorted(result,key=lambda r:r['path'])



def prepare(phase, source_review, prior_review):
    c = configuration(); source_gate(source_review); source,env = static_inputs(c); source_check(c)
    require(phase == 'COMPLETION' and prior_review is not None, 'actual SETUP review required')
    require(prior_review==c['failure_review'],'exact independent failed-prefix review'); accepted_setup(c);accepted_prefix(c);verify_setup_scope(c,hash_files=True)
    used = entry_ns(c['post_setup_prior_ns'], phase)
    require(not (WORK/'claims'/f'{phase}.json').exists() and not (WORK/'outer').exists() and not (WORK/'commands').exists(), 'stage already attempted')
    q = WORK/'coordination'; q.mkdir(mode=0o700,exist_ok=True)
    with (q/f'{phase}-prepare-attempt.json').open('x') as f:
        json.dump({'phase':phase,'one_attempt':True,'adapter':pin(__file__),'source_review':source_review},f)
        f.flush();os.fsync(f.fileno())
    guard = module(verify_pin(c['guard']),'main_baseline_original_guard')
    observation = resource_snapshot(c,guard)
    shared = safe(c['shared_lock']['path'],existing=True)
    require((shared.stat().st_dev,shared.stat().st_ino) == (c['shared_lock']['device'],c['shared_lock']['inode']), 'shared lock file changed')
    repro = safe(c['reproduction_lock']); repro.parent.mkdir(exist_ok=True)
    if not repro.exists():
        with repro.open('x'): pass
    code = 'import sys,fcntl\nf=open(sys.argv[1],"r+")\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)\nexcept BlockingIOError: sys.exit(73)\n'
    locks=[];probes=[]
    for path in [shared,repro]:
        st=path.stat();locks.append(dict(path=str(path),device=st.st_dev,inode=st.st_ino))
        argv=[c['python']['path'],'-B','-c',code,str(path)]
        with path.open('r+') as h:
            fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)
            try: held=subprocess.run(argv,timeout=10,capture_output=True)
            finally: fcntl.flock(h,fcntl.LOCK_UN)
        free=subprocess.run(argv,timeout=10,capture_output=True)
        require(held.returncode == 73 and free.returncode == 0 and held.stdout == held.stderr == free.stdout == free.stderr == b'', 'same-file lock peer probe failed')
        require((path.stat().st_dev,path.stat().st_ino) == (st.st_dev,st.st_ino), 'lock inode changed')
        probes.append(dict(path=str(path),held_child_exit=73,free_child_exit=0))
    guard.reacquire_locks(locks)
    ep={'schema':'astra-lock-epoch-v1','new_epoch':True,'historical_continuity_claimed':False,
        'boot_id':observation['boot_id'],'workspace':str(R),'created_for':str(WORK),'phase':phase,
        'shared':locks[0],'reproduction':locks[1],'shared_peer_contention_passed':True,
        'reproduction_reacquired':True,'probes':probes,'resources':observation,
        'environment_clock':datetime.datetime.now(datetime.timezone.utc).isoformat(),'native_AB_paused':True}
    ep_path=q/f'{phase}-epoch.json';require(not ep_path.exists(),'epoch already exists');save(ep_path,ep)
    (WORK/'tmp').mkdir(mode=0o700,exist_ok=True)
    require(not list((WORK/'tmp').iterdir()), 'temporary directory not empty')
    static_inputs(c);source_check(c);resource_snapshot(c,guard)
    require(prior_review==c['failure_review'],'exact independent failed-prefix review'); accepted_setup(c);accepted_prefix(c)
    require(used == c['post_setup_prior_ns'], 'old failed semantic elapsed must not reset')
    admission={'schema':'main-gap-completion-admission-v1','approved':True,'phase':phase,
               'configuration':pin(PB/'BINDINGS.json'),'adapter':pin(WORK/'controller.py'),
               'source_review':source_review,'prior_review':prior_review,'budget_seconds':BUDGETS[phase],
               'used_ns':used,'maximum_ns':MAX_NS,'epoch':pin(ep_path),'locks':locks,
               'environment':c['environment'],'source':c['source'],'guard':c['guard']}
    ap=q/f'{phase}-admission.json';require(not ap.exists(),'admission already exists');save(ap,admission)
    validate(ap,sha(ap),phase)
    print(json.dumps({'admission':pin(ap),'epoch':pin(ep_path),'used_ns':used,'launched':False},sort_keys=True))



def validate(path,digest,phase):
    require(READY, 'disabled source only')
    c=configuration();path=safe(path,existing=True)
    require(path == WORK/'coordination'/f'{phase}-admission.json' and sha(path)==digest,'admission identity')
    a=load(path)
    require(a['schema']=='main-gap-completion-admission-v1' and a['approved'] is True and a['phase']==phase
            and a['configuration']==pin(PB/'BINDINGS.json') and a['adapter']==pin(WORK/'controller.py')
            and a['budget_seconds']==BUDGETS[phase] and a['maximum_ns']==MAX_NS
            and a['environment']==c['environment'] and a['source']==c['source'] and a['guard']==c['guard'],'admission changed')
    source_gate(a['source_review']);source,env=static_inputs(c);source_check(c)
    require(phase=='COMPLETION' and type(a['used_ns']) is int and a['used_ns']==c['post_setup_prior_ns'], 'charged old failed stage prefix required')
    require(a['prior_review']==c['failure_review'],'exact failed-prefix review');accepted_setup(c);accepted_prefix(c)
    entry_ns(a['used_ns'],phase)
    ep=load(verify_pin(a['epoch']))
    require(a['epoch']['path']==str(WORK/'coordination'/f'{phase}-epoch.json') and ep['schema']=='astra-lock-epoch-v1'
            and ep['new_epoch'] is True and ep['historical_continuity_claimed'] is False
            and ep['created_for']==str(WORK) and ep['workspace']==str(R) and ep['phase']==phase
            and ep['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            and ep['shared_peer_contention_passed'] is True and ep['reproduction_reacquired'] is True,'fresh current-boot epoch required')
    require(a['locks']==[ep['shared'],ep['reproduction']] and [x['path'] for x in a['locks']]==[c['shared_lock']['path'],c['reproduction_lock']]
            and ep['probes']==[dict(path=x['path'],held_child_exit=73,free_child_exit=0) for x in a['locks']], 'actual two-lock proof mismatch')
    require(a['locks'][0]==c['shared_lock'], 'original real shared lock differs')
    for item in a['locks']:
        st=safe(item['path'],existing=True).stat()
        require((st.st_dev,st.st_ino)==(item['device'],item['inode']),'lock identity changed')
    require(safe(env['TMPDIR'],existing=True).is_dir(),'bounded tmp missing')
    return a,c,env,module(c['guard']['path'],'main_baseline_original_guard')



def check_outer(row,phase,argv,a,c):
    require(row['schema']=='sparse-scc-guard-v1' and row['complete'] is True and row['exit_code']==0 and row['reason'] is None
            and all(row[k] is True for k in ['cleanup','lock_reacquired','lease_cleared'])
            and row['standalone_admission'] is True and row['test_only'] is False,'outer not clean/successful')
    require(row['command']==argv and row['seconds']==BUDGETS[phase] and row['locks']==a['locks'] and row['epoch']==a['epoch']
            and row['cwd']==c['source'] and row['output']==str(WORK/'outer') and row['bounded_root']==str(E),'outer identity differs')
    cfgp=WORK/'outer/guard-config.json';cfg=load(cfgp)
    require(row['config_sha256']==sha(cfgp) and cfg=={'command':argv,'cwd':c['source'],'output':str(WORK/'outer'),
            'locks':a['locks'],'epoch':a['epoch'],'seconds':BUDGETS[phase],'reports':[],'test_mode':False,'nested':False,
            'bounded_root':str(E),'accepted_exit_codes':[0]},'outer actual configuration differs')



def verify_qualifier_scope(a, c, guard, path, digest, binding_sha):
    """Bind the two real ancestors: unchanged watchdog, then lock-owning guard."""
    folder = WORK
    cfg = folder / 'outer/guard-config.json'
    expected = {'command': command('COMPLETION', path, digest, c, binding_sha), 'cwd': a['source'],
        'output': str(folder / 'outer'), 'locks': a['locks'], 'epoch': a['epoch'],
        'seconds': 180, 'reports': [], 'test_mode': False, 'nested': False,
        'bounded_root': str(E), 'accepted_exit_codes': [0]}
    require(load(cfg) == expected, 'qualifier outer configuration mismatch')
    table = guard.process_table()
    watchdog = os.getppid()
    require(watchdog in table, 'missing watchdog parent')
    supervisor = table[watchdog]['ppid']
    require(supervisor in table, 'missing outer supervisor')
    starts = {pid: table[pid]['start'] for pid in [watchdog, supervisor]}
    def argv(pid):
        return (Path('/proc') / str(pid) / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    require(argv(watchdog) == [v.encode() for v in expected['command']], 'wrong watchdog ancestry')
    require(argv(supervisor) == [str(Path(sys.executable).resolve()).encode(), b'-B',
            c['guard']['path'].encode(), str(cfg).encode()], 'wrong guard ancestry')
    require(Path(os.readlink('/proc/self/cwd')) == Path(a['source']), 'qualifier cwd differs')
    lease = load(guard.epoch_active_path(a['locks'], a['epoch']))
    require(lease == {'schema': 'sparse-scc-epoch-lease-v1', 'epoch': a['epoch'], 'locks': a['locks'],
        'supervisor_pid': supervisor, 'supervisor_start': starts[supervisor],
        'guard_config_sha256': sha(cfg), 'output': str(folder / 'outer')}, 'wrong active lease')
    owners = guard.lock_owners(Path('/proc/locks').read_text())
    for item in a['locks']:
        require((supervisor, item['device'], item['inode']) in owners, 'supervisor does not own lock')
    after = guard.process_table()
    require(os.getppid() == watchdog and all(after.get(pid, {}).get('start') == start
            for pid, start in starts.items()), 'ancestor identity changed')




def accepted_prefix(c):
    r=load(verify_pin(c['failure_review']))
    require(r['schema']=='main-gap-semantic-failure-actual-review-v1' and r['complete'] is True
            and all(r[k] is True for k in ['failure_review_passed','deadline_failure_only','cleanup_lease_locks','failed_scope_preserved'])
            and r['actual_SEMANTIC_passed'] is False and r['blockers']==[] and r['source_commit']==c['source_commit']
            and r['original_binary']==c['original_binary'] and r['stats_binary']==c['stats_binary'], 'independently accepted deadline-only failure required')
    p=r['actual_pins'];require(set(p)=={'controller','worker','outer','config','watchdog','admission','claim','epoch','launch_binding','build_log','prepare_attempt'},'exact failed prefix role pins')
    paths={'controller':FAILED/'controller.json','worker':FAILED/'semantic-receipt.json','outer':FAILED/'outer/guard.json',
        'config':FAILED/'outer/guard-config.json','watchdog':FAILED/'bounded-receipt.json',
        'admission':FAILED/'coordination/SEMANTIC-admission.json','claim':FAILED/'claims/SEMANTIC.json',
        'epoch':FAILED/'coordination/SEMANTIC-epoch.json','launch_binding':FAILED/'launch-binding.json',
        'build_log':FAILED/'build.log','prepare_attempt':FAILED/'coordination/SEMANTIC-prepare-attempt.json'}
    for key,path in paths.items():require(verify_pin(p[key])==path,'failed prefix role '+key)
    previous,worker,outer,a,claim,epoch=[load(p[k]['path']) for k in ['controller','worker','outer','admission','claim','epoch']]
    require(previous['complete'] is False and worker['complete'] is False and worker['error']=="RuntimeError('whole-stage deadline including prechecks')"
            and len(worker['commands'])==84 and len(worker['statistics'])==22 and len(worker['cells'])==11 and worker['outputs']==[], 'exact original failed prefix')
    require(all(x['guard']['complete'] is True and x['guard']['exit_code']==0 and x['guard']['cleanup'] is True for x in worker['commands']), 'all preserved prefix child commands succeeded')
    require(previous['admission']==worker['admission']==p['admission'] and previous['outer']==p['outer']
            and previous['launch_binding']==worker['launch_binding']==p['launch_binding']
            and previous['epoch']==a['epoch']==outer['epoch']==p['epoch'] and previous['locks']==a['locks']==outer['locks'], 'same failed execution provenance')
    require(claim=={'phase':'SEMANTIC','admission':p['admission'],'retry_allowed':False},'old failed claim preserved')
    completed_epoch_identity(epoch,FAILED,'SEMANTIC')
    require(outer['exit_code']==1 and all(outer[k] is True for k in ['cleanup','lock_reacquired','lease_cleared'])
            and outer['bounded_root']==str(E) and outer['seconds']==600 and outer['config_sha256']==p['config']['sha256'], 'exact failed but cleaned outer')
    e=previous['guard_envelope']
    require(e['schema']=='main-gap-semantic-guard-envelope-v1' and e['guard_call_returned'] is True and e['clock']=='monotonic_ns'
            and all(type(e[k]) is int for k in ['start_ns','return_ns','elapsed_ns']) and 0<=e['start_ns']<=e['return_ns']
            and e['elapsed_ns']==e['return_ns']-e['start_ns']==r['elapsed_ns']==r['cumulative_ns']==c['post_setup_prior_ns']
            and e['outer']==p['outer'] and e['admission']==p['admission'] and e['returned_guard_sha256']==row_sha(outer), 'real charged old returned-call duration')
    for key in ['scope_inventory','scope_directories','partial_outputs_inventory','cell_evidence_inventory','foundation_reference_contract','remaining_original_commands']:verify_pin(r[key])
    allpins=inventory(r['scope_inventory'])
    require(len(allpins)==len({x['path'] for x in allpins}) and all(safe(x['path']).is_relative_to(FAILED) for x in allpins),'complete immutable failed scope')
    foundation=load(verify_pin(r['foundation_reference_contract']))
    require(Path(r['foundation_reference_contract']['path'])==FAILED/'reference-contracts/foundation14.json'
            and foundation['schema']=='main-gap-cell-original-reference-v3' and foundation['cell']=='foundation14'
            and foundation['original_binary']==c['original_binary'] and foundation['source_commit']==c['source_commit']
            and foundation['original_active_path']==str(E/'active/cells/foundation14') and foundation['candidate_invoked'] is False
            and foundation['performance_sample'] is False and foundation['retry_allowed'] is False
            and len(foundation['reference_commands'])==2 and foundation['formula_outputs']==[], 'exact frozen original Foundation reference')
    old_inputs=inventory(r['immutable_inputs'])
    require(len(old_inputs)==r['immutable_input_count']==6839,'complete actual old input inventory')
    return {'review':r,'worker':worker,'pins':allpins,'immutable_inputs':old_inputs,'foundation':foundation}

if __name__=='__main__':main()
