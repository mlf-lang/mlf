#!/usr/bin/python3
"""Disabled single frontend-only main setup; never a performance runner.
prepare only admits, run alone launches the immutable outer guard. No prior F25
qualification or elapsed is inherited. Copy with only READY changed after review.
"""
from pathlib import Path
import argparse, datetime, fcntl, hashlib, json, os, re, shlex, shutil, subprocess, sys, time, types
R = Path('<EXPERIMENT_ROOT>')
PB = R / 'main-gap-setup-v5-source'
WORK = R / 'main-gap-setup-run04'
READY = False
CONFIG_SHA = '8be176b18bb7d0d357f358ede76b5172c1b5f7efccb6add80abe5889767b32e8'
BUDGETS = {'SETUP': 600}
MAX_NS = 600 * 10**9
ALLOWED_ENV = {'HOME','PATH','LD_LIBRARY_PATH','LC_ALL','LANG','TZ','GHC_ENVIRONMENT','GHCRTS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MAKEFLAGS','PYTHONDONTWRITEBYTECODE','TMPDIR','CC','TC','LIBRARY_PATH','PKG_CONFIG_PATH'}
FORBIDDEN_ENV = {'MLF_QUERY_PROFILE','MLF_QUERY_SEMANTIC_AUDIT','MLF_QUERY_FAILPOINT','LD_PRELOAD','LD_AUDIT','LD_DEBUG','LD_DEBUG_OUTPUT','LD_PROFILE','LD_ASSUME_KERNEL','GLIBC_TUNABLES','GHC_PACKAGE_PATH','GHC_CHARENC','HPCTIXFILE'}
CASES = [
 ('version',['--version'],0,b'emlf 0.3.0\n',b''),
 ('identity',['--implementation-identity'],0,b'MLF/shared-haskell-v1 GHC\n',b''),
 ('semantic-42',['--run','--expr','printInt (40 + 2)'],0,b'42\n',b''),
 ('unicode-positive',['--run','--expr','putStrLn "λ雪🙂"'],0,'λ雪🙂\n'.encode(),b''),
 ('type-rejection',['--type','--expr','(True :: Int)'],1,b'',b'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n'),
]


PACKAGES = ['base','array','bytestring','text','containers','directory']
UNIT = 'mlf-shape-primitives-0.1'
BUILTIN = 'mlf:builtin-shared-haskell-v1:13'
FIXTURE = b'module Fixture where\nvalue = 42\n'
WORKER_OUTPUT_DIRS = ('dependencies','builtin-work','ordinary-reference','stats-main','ghc-control','commands')
WORKER_OUTPUT_FILES = ('stats-emlf','builtin.mlfci','builtin.mlfco','builtin.lock')


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


def configuration():
    require(sha(PB / 'CONFIG.json') == CONFIG_SHA, 'configuration changed')
    c = load(PB / 'CONFIG.json')
    require(c['schema'] == 'main-gap-setup-config-v1' and c['work'] == str(WORK)
            and c['workspace'] == str(R) and c['stage_caps'] == BUDGETS
            and type(c['total_guarded_elapsed_ns']) is int and c['total_guarded_elapsed_ns'] == MAX_NS
            and c['attempts_per_stage'] == 1, 'wrong baseline configuration')
    return c


def source_gate(review_pin):
    review = load(verify_pin(review_pin))
    require(review['schema'] == 'main-gap-setup-source-review-v1'
            and review['complete'] is True and review['source_gate_passed'] is True
            and review['blockers'] == [], 'independent complete source gate required')
    manifest = verify_pin(review['source_package_manifest'])
    require(manifest == PB / 'MANIFEST.json', 'wrong source package identity')
    rows = load(manifest)['files']
    require(len({r['path'] for r in rows}) == len(rows) and
            str(PB / 'controller.py') in {r['path'] for r in rows}, 'manifest inventory')
    for row in rows:
        require(verify_pin(row).is_relative_to(PB), 'source manifest escaped package')
    original = (PB / 'controller.py').read_text()
    require(original.count('\nREADY = False\n') == 1, 'disabled source READY declaration')
    require(Path(__file__).resolve() == WORK / 'controller.py' and
            Path(__file__).read_text() == original.replace('\nREADY = False\n','\nREADY = True\n',1),
            'only exact READY activation at fixed work path is permitted')
    require((WORK/'controller.disabled.py').read_bytes() == (PB/'controller.py').read_bytes(), 'original disabled snapshot required')
    return review


def static_inputs(c):
    source = safe(c['source'], existing=True)
    verify_pin(c['migration_manifest'])
    rows = load(verify_pin(c['source_inventory']))
    require(len(rows) == 3876 and len({r['relative'] for r in rows}) == 3876, 'complete main source inventory')
    for r in rows:
        p = safe(source / r['relative'], existing=True)
        require(p.is_relative_to(source) and p.is_file(), 'source path escape')
        require(p.stat().st_size == r['bytes'] and sha(p) == r['sha256'], 'source bytes changed')
        require(('100755' if p.stat().st_mode & 0o111 else '100644') == r['mode'], 'source mode changed')
    inventory = load(verify_pin(c['tool_inventory']))
    require(inventory['qualification_inherited'] is False and inventory['files'], 'fresh tool-file inventory required')
    for row in inventory['files']:
        verify_pin(row)
    for key in ['guard','python','git','ghc','cc','environment','history','baseline_controller','baseline_configuration','contract_manifest','closures','stats_parser','runtime_helper','ghc_pkg','ghc_pkg_elf','ar','shell','commands','global_packages','publication_oracle']:
        verify_pin(c[key])
    require(sha(c['guard']['path']) == '53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e', 'immutable guard differs')
    require(Path(sys.executable).resolve() == Path(c['python']['path']) == Path('/usr/bin/python3').resolve(), 'Python interpreter differs')
    runtime = load(verify_pin(c['runtime_paths']))
    require(runtime['qualification_inherited'] is False and runtime['loader_executed'] is False, 'runtime inventory is data only')
    for row in runtime['bindings']:
        p = Path(row['path'])
        require(str(p.resolve(strict=True)) == row['resolved'], 'runtime resolution changed')
        actual_links = [{'path':str(q),'target':os.readlink(q)} for q in [*reversed(p.parents),p] if q.is_symlink()]
        require(actual_links == row['links'] and verify_pin(row['file']) == p.resolve(), 'runtime binding changed')
    for folder, files in runtime['directories'].items():
        require(sorted(str(p) for p in Path(folder).iterdir()) == files, 'loader directory changed')
    require(all(not os.path.lexists(p) for p in runtime['required_absent']), 'unexpected system preload')
    global_packages=load(c['global_packages']['path'])
    require(sorted(str(p) for p in Path(global_packages['directory']).iterdir())==global_packages['entries'],'global package directory changed')
    for item in global_packages['files']:verify_pin(item)
    history = load(c['history']['path'])
    require(len(history['files']) == 8 and history['old_cleanup_claimed'] is False, 'historical evidence scope changed')
    for row in history['files']:
        verify_pin(row)
    env = load(c['environment']['path'])
    require(set(env) <= ALLOWED_ENV and all(type(k) is str and type(v) is str for k,v in env.items()), 'explicit environment required')
    require(not (FORBIDDEN_ENV & set(os.environ)), 'inherited profiling/loader override forbidden')
    expected = {'GHC_ENVIRONMENT':'-','GHCRTS':'','LC_ALL':'C.UTF-8','PYTHONDONTWRITEBYTECODE':'1',
                'TMPDIR':str(WORK/'tmp'),'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MAKEFLAGS':'-j1','CC':c['cc']['path']}
    require(all(env.get(k) == v for k,v in expected.items()) and all(k in env for k in ['HOME','PATH']), 'environment differs')
    return source, env


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


def envelope_ns(e):
    require(e['schema'] == 'main-gap-setup-guard-envelope-v1' and e['clock'] == 'monotonic_ns'
            and e['guard_call_returned'] is True, 'returned monotonic envelope required')
    require(all(type(e[k]) is int for k in ['start_ns','return_ns','elapsed_ns']), 'integer ns required; bool forbidden')
    require(0 <= e['start_ns'] <= e['return_ns'] and e['elapsed_ns'] == e['return_ns']-e['start_ns'], 'invalid elapsed arithmetic')
    return e['elapsed_ns']


def entry_ns(used, phase):
    require(type(used) is int and used >= 0 and phase in BUDGETS, 'invalid prefix or phase')
    require(used + BUDGETS[phase]*10**9 <= MAX_NS, 'entire next stage cap does not fit')
    return used


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
            heavy = bool(re.fullmatch(r'(?:ghc(?:-.*)?|ghc-iserv.*|cc1(?:plus)?|clang(?:-.*)?|emlf|mlfpkg|builtin-prelude|source-smoke)',base))
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


def prepare(phase, source_review, prior_review):
    c = configuration(); source_gate(source_review); source,env = static_inputs(c); source_check(c)
    require(phase == 'SETUP' and prior_review is not None, 'actual main producer reviews required')
    producer_gate(c, prior_review)
    used = entry_ns(0, phase)
    require(not (WORK/'claims'/f'{phase}.json').exists() and not (WORK/phase.lower()).exists(), 'stage already attempted')
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
    producer_gate(c, prior_review)
    require(used == 0, 'setup does not inherit baseline elapsed')
    admission={'schema':'main-gap-setup-admission-v1','approved':True,'phase':phase,
               'configuration':pin(PB/'CONFIG.json'),'adapter':pin(WORK/'controller.py'),
               'source_review':source_review,'prior_review':prior_review,'budget_seconds':BUDGETS[phase],
               'used_ns':used,'maximum_ns':MAX_NS,'epoch':pin(ep_path),'locks':locks,
               'environment':c['environment'],'source':c['source'],'guard':c['guard']}
    ap=q/f'{phase}-admission.json';require(not ap.exists(),'admission already exists');save(ap,admission)
    validate(ap,sha(ap),phase)
    print(json.dumps({'admission':pin(ap),'epoch':pin(ep_path),'used_ns':used,'launched':False},sort_keys=True))


def command(phase,path,digest,c):
    return [c['python']['path'],'-B',str(Path(c['source'])/'tools/shared/resource_watchdog.py'),
            '--seconds',str(BUDGETS[phase]),'--address-space-mib','6144','--rss-mib','5120',
            '--max-output-mib','2048','--disk-free-mib','5120',str(WORK/phase.lower()),*inner_command(phase,path,digest,c)]


def validate(path,digest,phase):
    require(READY, 'disabled source only')
    c=configuration();path=safe(path,existing=True)
    require(path == WORK/'coordination'/f'{phase}-admission.json' and sha(path)==digest,'admission identity')
    a=load(path)
    require(a['schema']=='main-gap-setup-admission-v1' and a['approved'] is True and a['phase']==phase
            and a['configuration']==pin(PB/'CONFIG.json') and a['adapter']==pin(WORK/'controller.py')
            and a['budget_seconds']==BUDGETS[phase] and a['maximum_ns']==MAX_NS
            and a['environment']==c['environment'] and a['source']==c['source'] and a['guard']==c['guard'],'admission changed')
    source_gate(a['source_review']);source,env=static_inputs(c);source_check(c)
    require(phase=='SETUP' and type(a['used_ns']) is int and a['used_ns']==0, 'single independent setup budget')
    producer_gate(c, a['prior_review'])
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
            and row['cwd']==c['source'] and row['output']==str(WORK/phase.lower()/'outer') and row['bounded_root']==str(WORK),'outer identity differs')
    cfgp=WORK/phase.lower()/'outer/guard-config.json';cfg=load(cfgp)
    require(row['config_sha256']==sha(cfgp) and cfg=={'command':argv,'cwd':c['source'],'output':str(WORK/phase.lower()/'outer'),
            'locks':a['locks'],'epoch':a['epoch'],'seconds':BUDGETS[phase],'reports':[],'test_mode':False,'nested':False,
            'bounded_root':str(WORK),'accepted_exit_codes':[0]},'outer actual configuration differs')


def verify_qualifier_scope(a, c, guard, path, digest):
    """Bind the two real ancestors: unchanged watchdog, then lock-owning guard."""
    folder = WORK / 'setup'
    cfg = folder / 'outer/guard-config.json'
    expected = {'command': command('SETUP', path, digest, c), 'cwd': a['source'],
        'output': str(folder / 'outer'), 'locks': a['locks'], 'epoch': a['epoch'],
        'seconds': 600, 'reports': [], 'test_mode': False, 'nested': False,
        'bounded_root': str(WORK), 'accepted_exit_codes': [0]}
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


def launch(phase,path,digest):
    a,c,env,guard=validate(path,digest,phase)
    producer_gate(c, a['prior_review'])
    resource_snapshot(c,guard)
    require(not os.path.lexists(guard.epoch_active_path(a['locks'],a['epoch'])) and
            not os.path.lexists(guard.epoch_quarantine_path(a['locks'],a['epoch'])),'new epoch blocked')
    (WORK/'claims').mkdir(mode=0o700,exist_ok=True)
    with (WORK/'claims'/f'{phase}.json').open('x') as f:
        json.dump({'phase':phase,'admission':pin(path),'retry_allowed':False},f);f.flush();os.fsync(f.fileno())
    folder=WORK/phase.lower();folder.mkdir(mode=0o700,exist_ok=False)
    argv=command(phase,path,digest,c)
    record={'schema':'main-gap-setup-controller-v1','complete':False,'phase':phase,
            'configuration':pin(PB/'CONFIG.json'),'adapter':pin(__file__),'admission':pin(path),
            'source':c['source'],'source_commit':c['source_commit'],'source_inventory':c['source_inventory'],
            'tool_inventory':c['tool_inventory'],'epoch':a['epoch'],'locks':a['locks'],'environment':c['environment'],
            'command':argv,'budget_seconds':BUDGETS[phase],'independent_actual_review_required':True,
            'continue_allowed':False,'stop_required':True,'native_generation_AB_fixedpoint':False}
    output=folder/'controller.json';save(output,record)
    row=None
    try:
        os.environ.clear();os.environ.update(env)
        guard_start_ns=time.monotonic_ns()
        row=guard.run_guard(argv,cwd=Path(c['source']),output=folder/'outer',locks=a['locks'],
                            epoch=a['epoch'],seconds=BUDGETS[phase],bounded_root=WORK)
        guard_return_ns=time.monotonic_ns()
        record['guard_envelope']={'schema':'main-gap-setup-guard-envelope-v1','clock':'monotonic_ns',
            'start_ns':guard_start_ns,'return_ns':guard_return_ns,'elapsed_ns':guard_return_ns-guard_start_ns,
            'guard_call_returned':True,'scope':'entire original run_guard call through return, including cleanup',
            'command':argv,'admission':pin(path),'outer':pin(folder/'outer/guard.json') if (folder/'outer/guard.json').is_file() else None,
            'returned_guard_sha256':row_sha(row)}
        if (folder/'outer/guard.json').is_file():record['outer']=pin(folder/'outer/guard.json')
        # Persist actual return even if subsequent success/cleanup checks reject it.
        save(output,record)
        n=envelope_ns(record['guard_envelope'])
        require(a['used_ns']+n<=MAX_NS,'actual cleanup-inclusive total budget exceeded')
        require(record['outer']==record['guard_envelope']['outer'] and row_sha(load(folder/'outer/guard.json'))==row_sha(row),'returned/persisted guard differs')
        check_outer(row,phase,argv,a,c)
        watchdog=load(folder/'bounded-receipt.json')
        require(watchdog['complete'] is True and watchdog['exit_code']==0 and watchdog['reason'] is None
                and watchdog['command']==inner_command(phase,path,digest,c) and watchdog['samples']
                and watchdog['samples'][-1]['group_rss']==0,'bounded watchdog failed')
        record['original_watchdog']=pin(folder/'bounded-receipt.json')
        validate(path,digest,phase)
        producer_gate(c, a['prior_review']); authenticate(c)
        result=load(folder/'setup-receipt.json')
        require(result['complete'] is True and len(result['commands'])==c['total_child_commands']
                and result['setup_payload_count']==13 and result['qualification_count']==11
                and result['runtime_count']==16, 'complete exact setup ledger required')
        require(result['outputs']==worker_output_pins(folder), 'complete worker-owned output inventory differs')
        for item in result['outputs']: verify_pin(item)
        record['setup_receipt']=pin(folder/'setup-receipt.json')
        require(not guard.epoch_active_path(a['locks'],a['epoch']).exists() and not guard.epoch_quarantine_path(a['locks'],a['epoch']).exists(),'new epoch not cleaned')
        record['complete']=True
    except BaseException as error:
        record.update(complete=False,error=repr(error))
        raise
    finally:
        valid=False;n=None;total=None
        try:
            n=envelope_ns(record['guard_envelope']);total=a['used_ns']+n;valid=True
        except (KeyError,TypeError,ValueError,RuntimeError):
            pass
        record['budget']={'elapsed_valid':valid,'elapsed_ns':n,'prior_ns':a['used_ns'],'cumulative_ns':total,
                          'maximum_ns':MAX_NS,'budget_passed':valid and total<=MAX_NS,
                          'includes_outer_cleanup_time':True,'original_guard_elapsed_seconds_excludes_cleanup':row.get('elapsed_seconds') if row else None}
        record['stop_required']=True  # Pause for independent actual result review even on observed success.
        # Even success is only observed evidence. Independent actual review is mandatory before another phase or a qualification claim.
        save(output,record)
    return record


def inner_command(phase,path,digest,c):
    require(phase == 'SETUP', 'single setup phase')
    return [c['python']['path'],'-B',str(WORK/'controller.py'),'_setup','--admission',str(path),'--sha256',digest]


def completed_epoch_identity(ep, work, phase):
    """Identity only, after exact historical epoch pin and final cleanup binding.
    Not an admission and never a substitute for the live current-boot gate.
    """
    require(type(ep['boot_id']) is str and ep['boot_id'] and ep['schema']=='astra-lock-epoch-v1'
            and ep['created_for']==str(work) and ep['workspace']==str(R) and ep['phase']==phase,
            'historical completed epoch identity differs')


def accepted_main_build(c, review_pin, b):
    """Historical completed BUILD reader: exact mature bindings, no current-boot demand."""
    r = load(verify_pin(review_pin))
    require(r['schema'] == 'main-baseline-ordinary-actual-review-v1' and r['phase'] == 'BUILD'
            and r['complete'] is True and r['actual_stage_review_passed'] is True and r['blockers'] == [],
            'actual independent main BUILD review required')
    expected = {'controller':b.WORK/'build/controller.json','outer':b.WORK/'build/outer/guard.json',
                'producer':b.WORK/'build/producer/receipt.json','admission':b.WORK/'coordination/BUILD-admission.json'}
    require(set(r['actual_pins']) == set(expected), 'actual BUILD review pin set differs')
    for key,p in expected.items():
        require(verify_pin(r['actual_pins'][key]) == p, 'wrong actual BUILD review path')
    old = load(expected['controller']); a = load(expected['admission']); g = load(expected['outer'])
    require(old['schema'] == 'main-baseline-ordinary-controller-v1' and old['phase'] == 'BUILD'
            and old['complete'] is True and old['configuration'] == pin(b.PB/'CONFIG.json')
            and old['adapter'] == pin(b.WORK/'controller.py') and old['admission'] == r['actual_pins']['admission']
            and old['producer_receipt'] == r['actual_pins']['producer'], 'actual main BUILD/controller binding')
    require(a['phase'] == 'BUILD' and a['prior_review'] is None and a['used_ns'] == 0, 'no inherited chain permitted')
    require(a['configuration']==old['configuration'] and a['adapter']==old['adapter']
            and a['source']==c['source'] and old['source_commit']==c['source_commit']
            and old['epoch']==a['epoch'] and old['locks']==a['locks']
            and old['command']==b.command('BUILD',expected['admission'],sha(expected['admission']),c), 'BUILD argv/admission/source mismatch')
    b.check_outer(g, 'BUILD', old['command'], a, c)
    e = old['guard_envelope']; n = b.envelope_ns(e)
    require(e['outer'] == r['actual_pins']['outer'] == old['outer'] and e['admission'] == old['admission']
            and e['command'] == g['command'] and e['returned_guard_sha256'] == row_sha(g), 'same-shot BUILD envelope')
    require(old['budget']['elapsed_valid'] is True and old['budget']['budget_passed'] is True
            and old['budget']['elapsed_ns'] == old['budget']['cumulative_ns'] == n
            and type(r['elapsed_ns']) is int and type(r['cumulative_ns']) is int
            and r['elapsed_ns'] == r['cumulative_ns'] == n, 'actual BUILD budget differs')
    ep = load(verify_pin(a['epoch']))
    completed_epoch_identity(ep,b.WORK,'BUILD')
    for marker in ['epoch-active-','epoch-quarantine-']:
        require(not (R/'.astra-resource-locks'/(marker+a['epoch']['sha256']+'.json')).exists(), 'main BUILD epoch not clean')
    return b.entry_ns(n, 'CONTROLS')


def producer_gate(c, reviews):
    """Consume real new-main BUILD+CONTROLS. No fallback to F25 or fabricated result."""
    require(type(reviews) is dict and set(reviews)=={'BUILD','CONTROLS'} and reviews==c['producer_reviews'], 'two exact actual producer reviews required')
    b=module(verify_pin(c['baseline_controller']),'pinned_main_baseline_consumer')
    bc=load(verify_pin(c['baseline_configuration']))
    require(b.PB/'CONFIG.json'==Path(c['baseline_configuration']['path']) and b.WORK==Path(c['baseline_work'])
            and bc['source']==c['source'] and bc['source_commit']==c['source_commit']
            and bc['source_tree']==c['source_tree'] and bc['source_inventory']==c['source_inventory'], 'baseline source binding differs')
    # Historical finished epochs retain exact pins/cleanup evidence, not a requirement to rerun after reboot.
    build_ns=accepted_main_build(bc,reviews['BUILD'],b)
    rr=load(verify_pin(reviews['CONTROLS']))
    require(rr['schema']=='main-baseline-ordinary-actual-review-v1' and rr['phase']=='CONTROLS'
            and rr['complete'] is True and rr['actual_stage_review_passed'] is True and rr['blockers']==[], 'actual focused CONTROLS review required')
    q=b.WORK
    expected={'controller':q/'controls/controller.json','outer':q/'controls/outer/guard.json',
              'producer':q/'build/producer/receipt.json','admission':q/'coordination/CONTROLS-admission.json',
              'controls':q/'controls/focused-control-receipt.json'}
    require(set(rr['actual_pins'])==set(expected), 'complete actual CONTROLS pin set')
    for key,p in expected.items(): require(verify_pin(rr['actual_pins'][key])==p, 'wrong CONTROLS actual path: '+key)
    row=load(expected['controller']);a=load(expected['admission']);g=load(expected['outer']);ctl=load(expected['controls'])
    require(row['schema']=='main-baseline-ordinary-controller-v1' and row['phase']=='CONTROLS' and row['complete'] is True
            and row['configuration']==c['baseline_configuration'] and row['adapter']==pin(q/'controller.py')
            and row['admission']==rr['actual_pins']['admission'] and row['controls']==rr['actual_pins']['controls']
            and row['source']==c['source'] and row['source_commit']==c['source_commit'], 'CONTROLS actual controller binding')
    require(a['schema']=='main-baseline-ordinary-admission-v1' and a['approved'] is True and a['phase']=='CONTROLS'
            and a['prior_review']==reviews['BUILD'] and a['used_ns']==build_ns and a['budget_seconds']==120
            and a['maximum_ns']==900*10**9 and a['configuration']==c['baseline_configuration']
            and a['adapter']==row['adapter'] and a['environment']==bc['environment']
            and a['source']==c['source'] and a['guard']==c['guard'] and row['epoch']==a['epoch'] and row['locks']==a['locks'], 'actual baseline admission differs')
    actual_source_review=load(verify_pin(a['source_review']))
    require(actual_source_review['schema']=='main-baseline-ordinary-source-review-v1'
            and actual_source_review['complete'] is True and actual_source_review['source_gate_passed'] is True
            and actual_source_review['blockers']==[] and verify_pin(actual_source_review['source_package_manifest'])==b.PB/'MANIFEST.json', 'baseline independent source review')
    require((q/'controller.py').read_bytes()==Path(c['baseline_controller']['path']).read_bytes().replace(b'\nREADY = False\n',b'\nREADY = True\n',1), 'baseline activation not READY-only')
    require(row['command']==b.command('CONTROLS',expected['admission'],sha(expected['admission']),bc), 'actual CONTROLS command differs')
    b.check_outer(g,'CONTROLS',row['command'],a,bc)
    e=row['guard_envelope'];n=b.envelope_ns(e)
    require(e['outer']==rr['actual_pins']['outer']==row['outer'] and e['admission']==row['admission']
            and e['command']==g['command'] and e['returned_guard_sha256']==row_sha(g), 'CONTROLS same-shot envelope')
    require(row['budget']['elapsed_valid'] is True and row['budget']['budget_passed'] is True
            and row['budget']['elapsed_ns']==n and row['budget']['prior_ns']==build_ns
            and row['budget']['cumulative_ns']==build_ns+n<=900*10**9
            and type(rr['elapsed_ns']) is int and type(rr['cumulative_ns']) is int
            and rr['elapsed_ns']==n and rr['cumulative_ns']==build_ns+n, 'baseline actual elapsed mismatch')
    require(ctl['schema']=='main-baseline-focused-controls-v1' and ctl['complete'] is True
            and ctl['adapter']==row['adapter'] and ctl['admission']==row['admission']
            and ctl['source_commit']==c['source_commit'] and ctl['producer_receipt']==rr['actual_pins']['producer'], 'focused producer identity differs')
    require(len(ctl['commands'])==len(CASES), 'exact five baseline controls')
    producer=load(expected['producer'])
    for got,(name,args,code,out,err) in zip(ctl['commands'],CASES):
        require(got['label']==name and got['passed'] is True and got['exit_code']==code
                and got['argv']==[producer['outputs']['emlf']['path'],*args] and got['cwd']==c['source']
                and verify_pin(got['stdout']).read_bytes()==out and verify_pin(got['stderr']).read_bytes()==err, 'baseline exact CLI oracle differs')
    ep=load(verify_pin(a['epoch']))
    completed_epoch_identity(ep,c['baseline_work'],'CONTROLS')
    for marker in ['epoch-active-','epoch-quarantine-']:
        require(not (R/'.astra-resource-locks'/(marker+a['epoch']['sha256']+'.json')).exists(), 'baseline CONTROLS epoch not clean')
    return {'reviews':reviews,'producer':rr['actual_pins']['producer'],'baseline_elapsed_not_carried':build_ns+n}


def authenticate(c):
    source=Path(c['source']);producer=Path(c['baseline_work'])/'build/producer'
    auth=module(source/'tools/shared/test_direct.py','main_gap_receipt_authenticator').authenticate_build(producer/'receipt.json',producer/'bin',source)
    require(auth['optimization']=='2' and auth['ghc']['path']==c['ghc']['path'] and auth['cc']['path']==c['cc']['path']
            and auth['orchestrator']['path']==c['python']['path'] and auth['complete'] is True
            and auth['prepared_verification']['kind']=='empty', 'actual bootstrap producer/tool identity differs')
    inventory={x['path']:x['sha256'] for x in load(c['tool_inventory']['path'])['files']}
    for mapping in [auth['toolchain']['files'],auth['installed_dependencies']['files']]:
        require(mapping and all(inventory.get(p)==h for p,h in mapping.items()), 'actual runtime/package source closure drift')
    actual={str(p.relative_to(producer)):sha(p) for p in (producer/'objects').rglob('*') if p.is_file()}
    require(auth['object_inputs']==actual and len(actual)==284, 'all 137 shared +4 host +one last wrapper object/interface pairs')
    builtin=load(verify_pin(auth['builtin_verification']))
    require(builtin['complete'] is True and builtin['candidate_verified'] is True
            and builtin['exact_regeneration'] is True and builtin['immutable_inputs_verified_after'] is True
            and builtin['source_files_rewritten'] is False, 'fresh canonical whole-file verification required')
    build=load(Path(c['baseline_work'])/'build/controller.json')
    require(len(build['c_objects'])==2, 'actual producer C objects absent')
    for label,item in zip(['host','supervisor'],build['c_objects']):
        require(verify_pin(item)==producer/(label+'.o'), 'same-build actual C object differs')
    closure=load(c['closures']['path'])
    rows=[*closure['emlf_non_main_shared'],*closure['private_primitive_modules']]
    require(len(rows)==94 and len({r['module'] for r in rows})==94 and len(closure['emlf_non_main_shared'])==90, 'exact Emlf non-Main closure')
    linked=[]
    for r in rows:
        verify_pin(r)
        owned=(auth['resolved_modules'] if r['module'] in auth['resolved_modules'] else auth['resolved_host_modules'])[r['module']]
        require(owned['path']==r['path'] and owned['sha256']==r['sha256'], 'module source ownership changed')
        p=producer/'objects'/r['module'].replace('.','/')
        item={'module':r['module'],'source':r,'object':pin(str(p)+'.o'),'interface':pin(str(p)+'.hi')}
        for f in ['object','interface']:
            rel=str(Path(item[f]['path']).relative_to(producer))
            require(auth['object_inputs'][rel]==item[f]['sha256'], 'same-build object/interface provenance')
        linked.append(item)
    require(not any(Path(x['object']['path']).name=='Main.o' for x in linked), 'never borrow last Main.o')
    return auth,linked,build['c_objects']


def import_flags(auth, producer, destination):
    """Exact mature transformation: only import/output routing changes."""
    result, i = [], 0
    flags = auth['flags']
    while i < len(flags):
        flag = flags[i]
        if flag in ('-odir', '-hidir'):
            i += 2
        elif flag == '-i' or flag.startswith('-i'):
            i += 1
        else:
            result.append(flag)
            i += 1
    return [*result, '-i', '-i' + str(producer / 'objects'),
            '-odir', str(destination), '-hidir', str(producer / 'objects')]


def pack(values): return ''.join(str(len(x))+':'+x for x in values)


def interface(text, identity, modules, dependencies):
    lines=text.splitlines();require(lines and lines[0]=='crate '+identity,'interface crate')
    owners=[x[7:] for x in lines if x.startswith('module ')]
    require(len(owners)==len(modules) and set(owners)==set(modules),'all module owners required')
    deps=[x[11:].split(' ',1) for x in lines if x.startswith('dependency ')]
    require(all(len(x)==2 and ' ' in x[1] for x in deps),'dependency grammar')
    found=[(n,tail.rsplit(' ',1)[0]) for n,tail in deps]
    require(len(found)==len(dependencies) and dict(found)==dependencies,'dependency identities/paths')


def fresh_fixture(report):
    require(type(report.get('format')) is int and report['format']==1 and report['crate']=='compiler-shapes/builtin', 'fixture query format/identity')
    require(type(report['inferred_groups']) is int and report['inferred_groups']==1
            and type(report['reused_groups']) is int and report['reused_groups']==0, 'one fresh group, zero reuse')
    groups=report['groups']
    require(type(groups) is list and len(groups)==1 and groups[0]['cached'] is False
            and type(groups[0]['id']) is str and groups[0]['id'], 'full ordered fixture group')


def unit_id(raw, name, auth):
    text=raw.decode('ascii')
    require(text.endswith('\n') and re.fullmatch(r'[A-Za-z0-9_.+-]+\n',text) is not None, 'exact one package id line')
    value=text[:-1]
    packages=auth['installed_dependencies']['packages']
    require(type(packages) is list and value in packages, 'actual package id absent from producer closure')
    dump=Path(auth['outputs']['emlf']['path']).parent.parent/'packages.txt'
    require(sha(dump)==auth['package_database_sha256'], 'authenticated producer package dump differs')
    rows=[dict(re.findall(r'^(name|id):[ \t]*(\S+)[ \t]*$',chunk,re.M)) for chunk in re.split(r'^---\s*$',dump.read_text(),flags=re.M)]
    matches=[r for r in rows if r.get('name')==name]
    require(matches==[{'name':name,'id':value}], 'actual global package name/id differs from producer dump')
    return value


def registered_unit_fields(actual, objects, deps, ids):
    """GHC may fold list fields; retain scalar identity and exact ordered tokens."""
    for key, expected in {'name':'mlf-shape-primitives','version':'0.1',
                          'id':UNIT,'key':UNIT,'exposed':'True'}.items():
        require(actual.get(key)==expected, 'registered package scalar differs: '+key)
    expected_lists={'exposed-modules':['MLF.Primitive'],
                    'hidden-modules':['MLF.Host.Base','MLF.Host.IO','MLF.Host.Async'],
                    'import-dirs':[str(objects)],'library-dirs':[str(deps)],
                    'hs-libraries':['HS'+UNIT],'depends':ids}
    known={'name','version','id','key','exposed',*expected_lists}
    require(set(actual) in (known,known|{'visibility'}), 'unexpected or missing registered package field')
    if 'visibility' in actual:
        require(actual['visibility']=='public', 'registered package visibility differs')
    for key, expected in expected_lists.items():
        require(type(actual.get(key)) is str, 'registered package list missing: '+key)
        require(shlex.split(actual[key])==expected, 'registered package list differs: '+key)


def tree_pins(folder):
    result=[]
    for p in sorted(folder.rglob('*')):
        require(not p.is_symlink(), 'output symlink forbidden')
        if p.is_file(): result.append(pin(p))
    return result


def worker_output_relative(relative):
    """Positive ownership only; no whole-stage walk or lifecycle-name blacklist."""
    p=Path(relative)
    require(not p.is_absolute() and p.parts and all(x not in ('.','..') for x in p.parts), 'worker relative path required')
    return (len(p.parts)==1 and p.name in WORKER_OUTPUT_FILES) or (len(p.parts)>1 and p.parts[0] in WORKER_OUTPUT_DIRS)


def worker_output_pins(folder):
    """Only completed worker artifacts and completed child archives are immutable.
    Outer controller/guard/watchdog files retain their independent post-return
    authentication, and are never hashed while those writers are still alive.
    """
    folder=safe(folder,existing=True);result=[]
    for name in WORKER_OUTPUT_DIRS:
        directory=safe(folder/name,existing=True)
        require(directory.is_dir(), 'worker output directory missing')
        rows=tree_pins(directory)
        require(rows, 'worker output directory unexpectedly empty')
        result.extend(rows)
    for name in WORKER_OUTPUT_FILES: result.append(pin(folder/name))
    require(len(result)==len({r['path'] for r in result}) and all(worker_output_relative(Path(r['path']).relative_to(folder)) for r in result), 'worker output ownership escaped')
    return sorted(result,key=lambda r:r['path'])


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


class Setup:
    def __init__(self,a,c,env,guard,path,digest):
        self.a,self.c,self.env,self.guard,self.path,self.digest=a,c,env,guard,path,digest
        self.folder=WORK/'setup';self.start=time.monotonic();self.number=0
        self.rp=runtime_module(c);self.stats=module(verify_pin(c['stats_parser']),'exact_external_stats_parser')
        self.publication=module(verify_pin(c['publication_oracle']),'pinned_pure_publication_oracle')
        self.auth,self.closure,self.c_objects=authenticate(c)
        self.producer=Path(c['baseline_work'])/'build/producer';self.source=Path(c['source'])
        self.inputs=[pin(self.producer/'receipt.json'),pin(PB/'SetupCheck.hs'),*self.c_objects,
            *[c[k] for k in ['ghc','ghc_pkg','ghc_pkg_elf','ar','cc','shell','python','stats_parser','runtime_helper','closures','environment','publication_oracle']]]
        for row in self.closure:self.inputs.extend([row['source'],row['object'],row['interface']])
        self.inputs.extend(load(c['global_packages']['path'])['files'])
        self.inputs.append(pin(self.producer/'packages.txt'))
        self.runtimes={};self.outputs=[]
        self.record={'schema':'main-gap-setup-worker-v1','complete':False,'commands':[],
            'configuration':pin(PB/'CONFIG.json'),'adapter':pin(__file__),'admission':pin(path),
            'producer_reviews':a['prior_review'],'producer_receipt':pin(self.producer/'receipt.json'),
            'fresh_canonical_verification':self.auth['builtin_verification'],
            'source_commit':c['source_commit'],'non_main_closure':self.closure,'c_objects':self.c_objects,
            'setup_payload_count':0,'qualification_count':0,'runtime_count':0,
            'runtime_before':{},'runtime_after':{},'outputs':[],
            'no_future_workload_or_measurement_executed':True}
        self.save()
    def save(self): save(self.folder/'setup-receipt.json',self.record)
    def recheck(self):
        for p in [*self.inputs,*self.outputs]:verify_pin(p)
        for runtime in self.runtimes.values():
            for value in [runtime['executable'],runtime['loader'],*runtime['config']['files'],*[x['binding'] for x in runtime['libraries']]]:
                require(self.rp.binding(value['path'])==value,'runtime binding drift')
            require(self.rp.config_snapshot(runtime['config_paths'],runtime['config_dirs'])==runtime['config'],'loader configuration drift')
        packages=load(self.c['global_packages']['path'])
        require(sorted(str(p) for p in Path(packages['directory']).iterdir())==packages['entries'],'global package directory changed')
        require(not os.path.lexists('/etc/ld.so.preload'),'unexpected loader preload')
    def remember(self,path):
        item=pin(path);self.outputs.append(item);return item
    def command(self,label,argv,*,kind,maximum=30,reports=(),status=0,out=None,err=None):
        self.recheck();self.number+=1
        require(self.number<=self.c['total_child_commands'], 'no extra commands or retries')
        expected=load(self.c['commands']['path'])['rows'][self.number-1]
        require(expected=={'ordinal':self.number,'label':label,'kind':kind,'maximum_seconds':maximum},'frozen exact command order/cap')
        left=600-(time.monotonic()-self.start)-2;require(left>0,'single setup deadline exhausted')
        seconds=min(maximum,left);argv=list(map(str,argv));output=self.folder/'commands'/('%03d-%s'%(self.number,label))
        for report in reports:require(not os.path.lexists(report),'RTS sink not empty')
        row=self.guard.run_child(argv,cwd=self.source,output=output,seconds=seconds,reports=reports,
                                 bounded_root=WORK,accepted_exit_codes=(status,))
        self.record['commands'].append({'label':label,'kind':kind,'guard':row,'receipt':pin(output/'guard.json') if (output/'guard.json').is_file() else None})
        self.record[kind+'_count']+=1;self.save()
        require(row['complete'] is True and row['cleanup'] is True and row['reason'] is None
                and row['test_only'] is False and row['standalone_admission'] is False and row['exit_code']==status
                and row['locks']==[] and row['epoch'] is None and row['lock_reacquired'] is False
                and row['command']==argv and row['cwd']==str(self.source) and row['output']==str(output)
                and row['bounded_root']==str(WORK) and row['limits']==self.guard.LIMITS and row['seconds']==seconds,'bounded child failed: '+label)
        require(set(row['archived'])==set(map(str,reports)), 'exact RTS archive set')
        for name in ['guard.json','guard-config.json','stdout','stderr']:self.remember(output/name)
        require(row['config_sha256']==sha(output/'guard-config.json'),'child configuration drift')
        stdout=(output/'stdout').read_bytes();stderr=(output/'stderr').read_bytes()
        require(out is None or stdout==out,'exact stdout failed: '+label)
        require(err is None or stderr==err,'exact stderr failed: '+label)
        for report in reports:
            item=row['archived'][str(report)];verify_pin(item);self.remember(item['path'])
            parsed=self.stats.parse_statistics(Path(item['path']).read_bytes())
            self.record.setdefault('statistics',[]).append({'command':label,'raw':item,'parsed':parsed,'qualification_only':True})
            require(not os.path.lexists(report),'RTS sink not archived')
        self.save();self.recheck();return stdout,stderr,row
    def runtime(self,label,executable):
        def callback(argv):
            out,err,row=self.command('runtime-'+label,argv,kind='runtime',maximum=10,err=b'')
            return {'stdout':out.decode(),'stderr':err.decode(),'returncode':0,'auth':pin(Path(row['output'])/'guard.json')}
        value=self.rp.pin_runtime(executable,callback)
        previous=self.runtimes.get(label.removesuffix('-after').removesuffix('-before'))
        if previous is not None:
            require({k:v for k,v in previous.items() if k!='command_auth'}=={k:v for k,v in value.items() if k!='command_auth'},'before/after runtime differs')
        self.runtimes[label.removesuffix('-after').removesuffix('-before')]=value
        return value
    def run(self):
        c=self.c;t=self.folder;source=self.source;producer=self.producer;ghc=c['ghc']['path'];pkg=c['ghc_pkg']['path']
        exe={'python':c['python']['path'],'ghc':self.auth['toolchain']['actual_ghc']['path'],
             'ghc-pkg':c['ghc_pkg_elf']['path'],'ar':c['ar']['path'],'cc':c['cc']['path'],'shell':c['shell']['path'],'producer':self.auth['outputs']['emlf']['path']}
        (t/'commands').mkdir(mode=0o700,exist_ok=False)
        for name,p in exe.items():self.record['runtime_before'][name]=self.runtime(name+'-before',p)
        deps=t/'dependencies';objects=deps/'objects';objects.mkdir(parents=True);db=deps/'package-db'
        flags=['-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages']
        for name in PACKAGES:flags+=['-package',name]
        self.command('fresh-private-four-module-unit',[ghc,'--make','-j1','-no-link','-O2','-XHaskell2010','-fpedantic-bottoms','-fno-state-hack',
            '-this-unit-id',UNIT,*flags,'-i','-i'+str(source/'host/ghc'),'-odir',objects,'-hidir',objects,source/'host/ghc/MLF/Primitive.hs'],kind='setup_payload',maximum=180)
        private=load(c['closures']['path'])['private_primitive_modules'];mods=sorted(r['module'].replace('.','/') for r in private)
        require({str(p.relative_to(objects)) for p in objects.rglob('*') if p.is_file()}=={m+s for m in mods for s in ['.o','.hi']}, 'exact private four-module output; no home unit borrowing')
        for item in tree_pins(objects):self.remember(item['path'])
        archive=deps/('libHS'+UNIT+'.a')
        self.command('archive-private-unit',[c['ar']['path'],'rcs',archive,*[objects/(m+'.o') for m in mods],*[x['path'] for x in self.c_objects]],kind='setup_payload',maximum=20)
        self.remember(archive)
        self.command('init-private-db',[pkg,'init',db],kind='setup_payload',maximum=10)
        ids=[]
        for name in PACKAGES:
            raw,_,_=self.command('global-unit-id-'+name,[pkg,'--global','field',name,'id','--simple-output'],kind='setup_payload',maximum=10,err=b'')
            ids.append(unit_id(raw,name,self.auth))
        conf=deps/'package.conf';conf.write_text('name: mlf-shape-primitives\nversion: 0.1\nid: '+UNIT+'\nkey: '+UNIT+'\n'
            'exposed: True\nexposed-modules: MLF.Primitive\nhidden-modules: MLF.Host.Base MLF.Host.IO MLF.Host.Async\n'
            +'import-dirs: '+str(objects)+'\nlibrary-dirs: '+str(deps)+'\nhs-libraries: HS'+UNIT+'\ndepends: '+' '.join(ids)+'\n')
        self.remember(conf)
        self.command('register-private-unit',[pkg,'--package-db',db,'register',conf],kind='setup_payload',maximum=20)
        registered=list(db.glob('*.conf'));require(len(registered)==1,'private database has exactly one unit')
        records=self.rp.package_records(registered[0].read_text());require(set(records)=={UNIT},'registered private unit identity')
        actual=records[UNIT]
        registered_unit_fields(actual,objects,deps,ids)
        for item in tree_pins(db):self.remember(item['path'])
        self.record['private_unit']={'unit':UNIT,'source_files':private,'objects':tree_pins(objects),
            'archive':pin(archive),'configuration':pin(conf),'registered':pin(registered[0]),'actual_dependency_ids':ids}
        # First public fixture is the ordinary producer reference, never a future workload warmup.
        self.prepare_fixture()
        self.command('new-main-fixed-builtin-pair',[exe['producer'],'--compile-crate',t/'builtin-work/fixture.spec','-o',t/'builtin-work/fixture'],kind='setup_payload',maximum=120,out=b'',err=b'')
        ordinary=self.fixture_snapshot()
        ordinary_shows={}
        for label,prefix,identity,owners,dependencies in self.show_specs():
            raw,_,_=self.command('ordinary-show-'+label,[exe['producer'],'--show-crate',str(prefix)+'.mlfci'],kind='qualification',maximum=20,err=b'')
            interface(raw.decode(),identity,owners,dependencies);ordinary_shows[label]=raw
        # Same exact source Main freshly compiled; all other 94 home objects belong to this producer.
        main=t/'stats-main';main.mkdir();f=import_flags(self.auth,producer,main)
        require(not any('-prof' in x or x.startswith('-fprof') for x in f),'ordinary no-profile flags only')
        main_source=load(c['closures']['path'])['fresh_emlf_main'];verify_pin(main_source)
        self.command('fresh-original-emlf-Main',[ghc,'-c','-fforce-recomp',*f,main_source['path'],'-o',main/'Main.o','-ohi',main/'Main.hi'],kind='setup_payload',maximum=60)
        mo=self.remember(main/'Main.o');mh=self.remember(main/'Main.hi')
        (WORK/'active').mkdir();sink=WORK/'active/mlf.stats';binary=t/'stats-emlf'
        self.command('ordinary-stats-own-relink',[ghc,*f,'-rtsopts=ignoreAll','-with-rtsopts=-s'+str(sink),main/'Main.o',
            *[x['object']['path'] for x in self.closure],*[x['path'] for x in self.c_objects],'-o',binary],kind='setup_payload',maximum=60)
        self.remember(binary);self.record['stats_relink']={'source':main_source,'main_object':mo,'main_interface':mh,
            'binary':pin(binary),'flags':f,'non_main_count':94,'c_object_count':2,'fixed_statistics_sink':str(sink)}
        exe['stats-emlf']=str(binary);self.record['runtime_before']['stats-emlf']=self.runtime('stats-emlf-before',binary)
        for label,args,status,out,err in CASES:
            self.command('stats-'+label,[binary,*args],kind='qualification',status=status,out=out,err=err,reports=(sink,),maximum=10)
        # Preserve every original output, then reconstruct the identical empty paths before the second compile.
        reference=t/'ordinary-reference';reference.mkdir()
        (t/'builtin-work').rename(reference/'builtin-work')
        for p in sorted(t.glob('builtin.*')):p.rename(reference/p.name)
        require(self.fixture_snapshot(reference,locks=False)==ordinary,'ordinary fixture archive changed bytes')
        for item in tree_pins(reference):self.remember(item['path'])
        self.record['ordinary_fixture_raw']={'root':str(reference),'files':ordinary,'same_paths_recreated':True}
        self.prepare_fixture()
        self.command('stats-fixed-fixture',[binary,'--compile-crate',t/'builtin-work/fixture.spec','-o',t/'builtin-work/fixture'],kind='qualification',maximum=120,out=b'',err=b'',reports=(sink,))
        actual=self.fixture_snapshot()
        ordinary_binary=verify_pin(self.auth['outputs']['emlf']);stats_binary=verify_pin(self.record['stats_relink']['binary'])
        ordinary_raw={rel:safe(reference/rel,existing=True).read_bytes() for rel in ordinary}
        stats_raw={rel:safe(t/rel,existing=True).read_bytes() for rel in actual}
        equivalence=self.publication.compare_fixture(ordinary_raw,stats_raw,sha(ordinary_binary),sha(stats_binary))
        for label,prefix,identity,owners,dependencies in self.show_specs():
            raw,_,_=self.command('stats-show-'+label,[binary,'--show-crate',str(prefix)+'.mlfci'],kind='qualification',maximum=20,err=b'',out=ordinary_shows[label],reports=(sink,))
            interface(raw.decode(),identity,owners,dependencies)
        self.record['fixture_equivalence']={'complete':True,'full_raw_files_equal':actual==ordinary,'cross_compiler_publication':equivalence,'fresh_groups_each':1,'reused_groups_each':0,
            'ordered_query_bytes_equal':True,'fixed_builtin_owners':['Prelude','MLF.Primitive'],'fixture_owners':['Fixture'],
            'no_path_or_identity_normalization':True,'ordinary_reference':str(reference),'stats_current':str(t),'ordinary_files':ordinary,'files':actual}
        # Small typed-only package/RTS compatibility control, not one of the future 12 cells.
        check=t/'ghc-control';check.mkdir();co=check/'objects';co.mkdir();cs=check/'SetupCheck.hs'
        cs.write_bytes((PB/'SetupCheck.hs').read_bytes());self.remember(cs);gs=WORK/'active/ghc.stats'
        gflags=['--make','-j1','-O2','-fforce-recomp','-fpedantic-bottoms','-fno-state-hack','-v','-package-env','-',
            '-clear-package-db','-global-package-db','-package-db',str(db),'-no-user-package-db','-hide-all-packages',
            '-package','base','-package','mlf-shape-primitives','-i','-odir',str(co),'-hidir',str(co),'-fno-code','-fwrite-interface','-no-link']
        self.command('ghc-typed-package-RTS-control',[ghc,*gflags,cs,'+RTS','-s'+str(gs),'-RTS'],kind='qualification',maximum=30,reports=(gs,))
        require({str(p.relative_to(co)) for p in co.rglob('*') if p.is_file()}=={'SetupCheck.hi'},'fresh typed interface only, no source dependencies recompiled')
        self.remember(co/'SetupCheck.hi')
        self.record['ghc_typed_control']={'source':pin(cs),'interface':pin(co/'SetupCheck.hi'),'flags':gflags,'no_object_or_link':True}
        require(len(self.record['statistics'])==9,'all 8 MLF +1 GHC strict complete RTS reports required')
        for name,p in exe.items():self.record['runtime_after'][name]=self.runtime(name+'-after',p)
        static_inputs(c);source_check(c);producer_gate(c,self.a['prior_review'])
        auth,closure,c_objects=authenticate(c)
        require(auth==self.auth and closure==self.closure and c_objects==self.c_objects,'producer/source/objects changed')
        self.recheck()
        require(self.number==40 and self.record['setup_payload_count']==13 and self.record['qualification_count']==11
                and self.record['runtime_count']==16,'fixed full 40-command ledger')
        self.record['outputs']=worker_output_pins(t)
        self.record['complete']=True;self.save()
    def prepare_fixture(self):
        t=self.folder;work=t/'builtin-work';work.mkdir();(work/'queries').mkdir()
        (work/'Fixture.emlf').write_bytes(FIXTURE)
        fields=['MLF-CRATE-1','compiler-shapes/builtin','','false',pack([pack(['Fixture',str(work/'Fixture.emlf')])]),'',str(work/'queries'),str(t/'builtin')]
        (work/'fixture.spec').write_text(pack(fields))
        require(not any((t/('builtin'+s)).exists() for s in ['.mlfci','.mlfco','.lock']),'fixed builtin must be genuinely absent')
    def show_specs(self):
        t=self.folder
        return [('fixture',t/'builtin-work/fixture','compiler-shapes/builtin',['Fixture'],{BUILTIN:str(t/'builtin.mlfci')}),
                ('builtin',t/'builtin',BUILTIN,['Prelude','MLF.Primitive'],{})]
    def fixture_snapshot(self,root=None,locks=True):
        root=root or self.folder;work=root/'builtin-work'
        require((work/'Fixture.emlf').read_bytes()==FIXTURE,'fixed fixture source changed')
        fresh_fixture(load(work/'fixture.queries'))
        for p in [work/'fixture.mlfci',work/'fixture.mlfco',root/'builtin.mlfci',root/'builtin.mlfco']:
            require(p.is_file() and p.stat().st_size>0,'complete checked pair missing')
        files=[*tree_pins(work),*[pin(p) for p in sorted(root.glob('builtin.*'))]]
        result={str(Path(p['path']).relative_to(root)):{'sha256':p['sha256'],'bytes':p['bytes']} for p in files}
        require(any('/results/' in p and p.endswith('.mlfqr') for p in result)
                and any('/generations/' in p and p.endswith('.mlfqg') for p in result)
                and 'builtin-work/queries/query-graph-v2/CURRENT' in result,'complete query publication required')
        if locks:
            for lock in [work/'queries/.lock',root/'builtin.lock']:
                st=safe(lock,existing=True).stat()
                self.guard.reacquire_locks([dict(path=str(lock),device=st.st_dev,inode=st.st_ino,kind='posix')])
        return result


def setup(path,digest):
    a,c,env,guard=validate(path,digest,'SETUP')
    require(dict(os.environ)==env,'exact explicit setup environment')
    require(load(WORK/'claims/SETUP.json')=={'phase':'SETUP','admission':pin(path),'retry_allowed':False},'one-use setup claim')
    verify_qualifier_scope(a,c,guard,path,digest)
    worker=Setup(a,c,env,guard,path,digest)
    try:
        worker.run()
        validate(path,digest,'SETUP');verify_qualifier_scope(a,c,guard,path,digest)
    except BaseException as error:
        worker.record.update(complete=False,error=repr(error));worker.save();raise

def main():
    require(READY,'READY=False: disabled source package; no preparation or execution permitted')
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('phase',choices=list(BUDGETS))
    p.add_argument('--source-review',type=Path,required=True);p.add_argument('--source-review-sha256',required=True)
    p.add_argument('--build-review',type=Path,required=True);p.add_argument('--build-review-sha256',required=True)
    p.add_argument('--controls-review',type=Path,required=True);p.add_argument('--controls-review-sha256',required=True)
    r=sub.add_parser('run');r.add_argument('phase',choices=list(BUDGETS))
    w=sub.add_parser('_setup')
    for p in [r,w]:p.add_argument('--admission',type=Path,required=True);p.add_argument('--sha256',required=True)
    args=parser.parse_args()
    if args.command=='prepare':
        review=pin(args.source_review);require(review['sha256']==args.source_review_sha256,'source review digest mismatch')
        prior={'BUILD':pin(args.build_review),'CONTROLS':pin(args.controls_review)}
        require(prior['BUILD']['sha256']==args.build_review_sha256 and prior['CONTROLS']['sha256']==args.controls_review_sha256,'actual producer review digests differ')
        prepare(args.phase,review,prior)
    elif args.command=='_setup':setup(args.admission,args.sha256)
    else:print(json.dumps(launch(args.phase,args.admission,args.sha256),indent=2,sort_keys=True))


if __name__=='__main__':
    main()
