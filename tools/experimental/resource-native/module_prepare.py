"""Opt-in bounded module snapshot and actual-compiler custody.

This is a cooperative reproducibility guard, not a hostile-filesystem sandbox.
Only source text snapshots feed the original loader; no cached CheckedTerm enters.
"""
from pathlib import Path
import hashlib,json,os,resource,stat,subprocess,tempfile,time
import module_transport

MAX_FILES=32
MAX_FILE_BYTES=1<<20
MAX_TOTAL_BYTES=8<<20
MAX_EXPORT_BYTES=32<<20
BUDGET={'cpu_seconds':180,'wall_seconds':240,'address_space_bytes':1536<<20,
        'stdout_bytes':MAX_EXPORT_BYTES,'stderr_bytes':MAX_EXPORT_BYTES}

def sha(blob):return hashlib.sha256(blob).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)

def inventory(root):
    """Bound the WHOLE copied inventory, including unimported .emlf files."""
    root=Path(os.path.abspath(root))
    if root.resolve(strict=True)!=root or not root.is_dir():raise ValueError('module root must be a real canonical directory without symlinks')
    found={};total=0
    for current,dirs,files in os.walk(root,followlinks=False):
        for n in sorted(dirs+files):
            p=Path(current)/n;mode=p.lstat().st_mode
            if stat.S_ISLNK(mode):raise ValueError('module snapshot rejects file/directory symlinks')
            if p.resolve(strict=True)!=p:raise ValueError('module snapshot canonical path escaped')
            if stat.S_ISDIR(mode):continue
            if not stat.S_ISREG(mode):raise ValueError('module snapshot rejects special files')
            if p.suffix=='.hs':raise ValueError('module snapshot rejects guest .hs ambiguity')
            if p.suffix!='.emlf':continue
            rel=p.relative_to(root).as_posix()
            if '\\' in rel or any(part in ('','.','..')for part in Path(rel).parts):raise ValueError('unsafe logical guest source path')
            if rel in found or len(found)>=MAX_FILES:raise ValueError('module snapshot file count exceeds32 or duplicates')
            if p.stat().st_size>MAX_FILE_BYTES:raise ValueError('module snapshot source exceeds1MiB')
            blob=p.read_bytes()
            if len(blob)>MAX_FILE_BYTES:raise ValueError('module source changed beyond1MiB during capture')
            blob.decode('utf-8',errors='strict');total+=len(blob)
            if total>MAX_TOTAL_BYTES:raise ValueError('module snapshot exceeds8MiB total')
            found[rel]=blob
    if not found:raise ValueError('empty module source inventory')
    return root,dict(sorted(found.items()))

def summary(files):return {p:{'sha256':sha(b),'bytes':len(b)}for p,b in files.items()}

def verify_source_package(evidence):
    if 'module_package' not in evidence:return
    package=evidence['module_package'];_,live=inventory(package['live_root'])
    if summary(live)!=package['files']:raise ValueError('stale imported/source package bytes after snapshot')
    _,snap=inventory(package['snapshot_root'])
    if summary(snap)!=package['files']:raise ValueError('private module snapshot bytes changed')
    if sha(live[package['root_relative']])!=evidence['source_sha256']:raise ValueError('live module entry changed')

def snapshot(source_path,module_root,parent):
    root,files=inventory(module_root);source=Path(os.path.abspath(source_path))
    if source.resolve(strict=True)!=source:raise ValueError('module entry cannot traverse a symlink')
    try:relative=source.relative_to(root).as_posix()
    except ValueError as e:raise ValueError('module entry must be inside module root')from e
    if relative not in files:raise ValueError('module entry must be a captured .emlf regular file')
    parent=Path(parent);parent.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='module-capture-',dir=parent)).resolve();private=folder/'sources';private.mkdir()
    for rel,blob in files.items():
        dst=private/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(blob)
    table=summary(files)
    package={'policy':'bounded-module-snapshot/1','live_root':str(root),'snapshot_root':str(private),
             'root_relative':relative,'files':table,'inventory_sha256':sha(encode(table).encode()),
             'total_bytes':sum(len(b)for b in files.values()),'copied_files':len(files),
             'ignored_regular_non_source_files_are_not_claimed_checked':True}
    (folder/'PACKAGE.json').write_text(json.dumps(package,indent=2)+'\n')
    if inventory(root)[1]!=files or inventory(private)[1]!=files:raise ValueError('module package changed during capture')
    return folder,package,files[relative]

def invoke(argv,source,folder,private):
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU,(BUDGET['cpu_seconds'],BUDGET['cpu_seconds']))
        resource.setrlimit(resource.RLIMIT_AS,(BUDGET['address_space_bytes'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(MAX_EXPORT_BYTES,)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    (folder/'stdin.emlf').write_bytes(source)
    env=dict(os.environ,TMPDIR=str(folder),GHC_ENVIRONMENT='-',GHCRTS='',LC_ALL='C.UTF-8')
    start=time.monotonic();timed_out=False
    with (folder/'stdin.emlf').open('rb')as inp,(folder/'compiler.stdout').open('wb')as out,(folder/'compiler.stderr').open('wb')as err:
        process=subprocess.Popen(argv,stdin=inp,stdout=out,stderr=err,cwd=private,env=env,preexec_fn=limits)
        try:process.wait(timeout=BUDGET['wall_seconds'])
        except subprocess.TimeoutExpired:timed_out=True;process.kill();process.wait()
    stdout=(folder/'compiler.stdout').read_bytes();stderr=(folder/'compiler.stderr').read_bytes()
    record={'argv':argv,'cwd':str(private),'stdin_sha256':sha(source),'exit_code':process.returncode,
      'wall_seconds':time.monotonic()-start,'wall_timeout':timed_out,'budget':BUDGET,
      'stdout_sha256':sha(stdout),'stdout_bytes':len(stdout),'stderr_sha256':sha(stderr),'stderr_bytes':len(stderr),
      'stdout':str(folder/'compiler.stdout'),'stderr':str(folder/'compiler.stderr')}
    (folder/'COMPILER_INVOCATION.json').write_text(json.dumps(record,indent=2)+'\n')
    if timed_out:raise ValueError('bounded module compiler wall timeout; source outcome UNKNOWN; '+str(folder))
    if process.returncode:raise ValueError('module compiler rejected/failed rc='+str(process.returncode)+': '+stderr.decode(errors='replace').strip()+'; capture='+str(folder))
    if stderr:raise ValueError('successful module compiler wrote diagnostics; '+str(folder))
    if len(stdout)>MAX_EXPORT_BYTES:raise ValueError('module export byte bound exceeded')
    return stdout,record

def prepare_module_source(host,source_path,*,module_root,build_parent,groups=False,borrows=False,no_prelude=False):
    if not no_prelude:raise ValueError('module route requires explicit --no-prelude')
    if groups or borrows:raise ValueError('new module route initially admits coarse-owned mode only')
    host.frozen_reference();build=host.build_identity()
    folder,package,source=snapshot(source_path,module_root,build_parent)
    argv=[build['binary'],'--no-prelude','--emit-resource-module-json','-']
    try:raw,invocation=invoke(argv,source,folder,package['snapshot_root'])
    finally:
        verify_source_package({'module_package':package,'source_sha256':sha(source)})
        host.build_identity();host.frozen_reference()
    manifest=host.current_source_manifest()
    envelope=module_transport.parse_module_envelope(raw.decode('utf-8',errors='strict'),manifest=manifest)
    data=envelope.data();loaded=[]
    for row in data['module_custody']['loaded']:
        path=row['source']['path'];blob=row['text'].encode('utf-8')
        if row['is_root']:
            if path!='<stdin>' or blob!=source:raise ValueError('actual loaded root differs from captured entry')
            rel=package['root_relative']
        else:
            rel=path[2:]if path.startswith('./')else path
            if rel not in package['files']:raise ValueError('actual loader read outside captured source inventory')
            if (Path(package['snapshot_root'])/rel).read_bytes()!=blob:raise ValueError('actual loaded imported text differs from snapshot')
        loaded.append({'source_path':path,'snapshot_relative':rel,'sha256':sha(blob),'is_root':row['is_root']})
    package['loaded_sources']=loaded
    candidate=host._planner.plan(envelope,groups=groups,borrows=borrows)
    lock,blobs=host.kernel_identity();kernel=host.load_kernel(lock,blobs);checked=kernel.check(candidate['program'])
    if checked.sha256!=candidate['binding']['candidate_sha256']:raise ValueError('module plan digest binding changed')
    evidence={'scope':'actual complete module load/resolve/inference/check then separately replayed lazy outer-spine projection and strict retained runtime admission',
      'base_commit':manifest['source_commit'],'source_sha256':sha(source),'compiler_argv':argv,
      'compiler_binary_sha256':build['binary_sha256'],'compiler_build_receipt_sha256':host.sha(host.BASE/'validation/compiler-build.json'),
      'compiler_input_sha256':build['inputs'],'producer_revision':{'current_target_commit':manifest['source_commit'],'current_target_tree':manifest['source_tree'],
      'historical_anchors':manifest['historical_anchors'],
      'new_compiler_contract_sha256':host.COMPILER_CONTRACT_SHA,'modified_source_is_not_claimed_as_an_existing_git_commit':True,
      'export_source_commit_field_means':'unmodified current target dependency baseline only','current_transition_sha256':host.PRODUCER_TRANSITION_SHA},
      'actual_checked_export':data,'binding':candidate['binding'],'resource_check':checked.report(),
      'genuine_CheckedTerm_execution':True,'direct_XMLF_parser_used':False,'source_execution_used_to_generate_IR':False,
      'preparation_executed_IR':False,'no_prelude':True,'kernel_receipt_sha256':host.KERNEL_ACCEPTANCE,
      'module_package':package,'module_compiler_invocation':invocation,
      'module_route_source_sha256':host.MODULE_ROUTE_SHA256}
    verify_source_package(evidence);host.build_identity();host.frozen_reference()
    (folder/'PREPARATION.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return host.Prepared(checked.canonical_json,source,encode(evidence))
