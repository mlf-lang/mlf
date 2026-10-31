#!/usr/bin/env python3
"""Genuine checked source → native C build/run, gated on exact runtime acceptance.

No runtime JSON/opcode interpreter. Compiled C owns the target heap directly.
Native source/runtime/toolchain receipts are cooperative reproducibility evidence,
not a code-signing service or sandbox against hostile concurrent filesystem edits.
"""
from pathlib import Path
import argparse,hashlib,json,os,resource,shutil,subprocess,sys,tempfile,time,types
BASE=Path(__file__).resolve().parent
RUNNER_BYTES=Path(__file__).read_bytes();RUNNER_SHA=hashlib.sha256(RUNNER_BYTES).hexdigest()
NATIVE_ACCEPTANCE_SHA256="f9f7f07886608d15bc97e370964757e72e2f9295d32a6ec35f78b4d663954bfe"  # independently accepted exact C runtime
MODULE_BYTES={name:(BASE/(name+'.py')).read_bytes() for name in ['prepare','codegen']}
if hashlib.sha256(MODULE_BYTES['codegen']).hexdigest()!='1899d2681aaab0c2b1730a0b6f76c9cbbe5f1cb98aba630a38d5b1b528f65845':raise ValueError('accepted codegen changed before source-byte import')
for name,blob in MODULE_BYTES.items():
    module=types.ModuleType(name);module.__file__=str(BASE/(name+'.py'));sys.modules[name]=module
    exec(compile(blob,module.__file__,'exec'),module.__dict__)
prepare=sys.modules['prepare'];codegen=sys.modules['codegen']

EXPECTED_METRICS=set("steps groups_allocated groups_closed nodes_allocated nodes_freed peak_groups peak_nodes peak_owner_handles owner_handle_acquisitions owner_handle_releases loan_handle_acquisitions loan_handle_releases force_calls max_force_depth callback_calls ordinary_calls applications_allocated raw_deferred_returns memo_writes internal_memo_slots cross_group_memo_slots memo_fast_paths groups_closed_during_force borrowed_slot_publications ir_retain_ops ir_drop_ops ir_borrow_ops ir_end_borrow_ops ir_application_borrow_ops max_activation_depth rc_inc_total rc_dec_total repeat_calls".split()) | {"rc_"+way+"_"+kind for way in ["inc","dec"] for kind in ["owner","builder","pin","key","slot"]}
MEMORY_FIELDS=set("allocated_bytes freed_bytes live_bytes peak_bytes allocations frees live_blocks peak_blocks".split())
MEMORY_CATEGORIES={"context","groups","nodes","slots","handles","captures","pending"}

class NativeError(ValueError):pass

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def local_identity():
    if sha(__file__)!=RUNNER_SHA:raise NativeError('native runner changed since source-byte load')
    for name,blob in MODULE_BYTES.items():
        if (BASE/(name+'.py')).read_bytes()!=blob:raise NativeError('native module changed since source-byte load: '+name)
    prepare.frozen_reference()


def native_identity(lock_path:Path|None=None):
    if NATIVE_ACCEPTANCE_SHA256 is None:raise NativeError('independent native runtime acceptance gate is pending')
    path=lock_path or BASE/'validation/native-runtime-lock.json'
    if not path.is_file():raise NativeError('native accepted runtime lock is absent')
    lock=json.loads(path.read_text());receipt=BASE/lock['audit_receipt']
    if lock.get('audit_status')!='accepted' or lock.get('audit_receipt_sha256')!=NATIVE_ACCEPTANCE_SHA256 or sha(receipt)!=NATIVE_ACCEPTANCE_SHA256:
        raise NativeError('native runtime lock does not name the pinned accepted receipt')
    accepted=json.loads(receipt.read_text())
    if accepted.get('status')!='accepted' or accepted.get('audit_gate_allows_source_integration') is not True:
        raise NativeError('native runtime receipt does not authorize source integration')
    if (lock['runtime_root']!=accepted['runtime_root'] or lock['files']!=accepted['source_sha256'] or
        lock['implementation_manifest_sha256']!=accepted['implementation_manifest_sha256']):
        raise NativeError('native lock differs from the accepted source inventory')
    if set(lock['files'])!={'rir_runtime.c','rir_runtime.h'}:raise NativeError('native ABI source inventory differs')
    root=BASE/lock.get('runtime_location',lock['runtime_root']);blobs={}
    for file,digest in lock['files'].items():
        blob=(root/file).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=digest:raise NativeError('accepted native runtime bytes changed: '+file)
        blobs[file]=blob
    return lock,blobs


def compiler_identity():
    path=shutil.which('cc')
    if path is None:raise NativeError('existing C compiler unavailable; no installation attempted')
    path=Path(path).resolve();version=subprocess.check_output([str(path),'--version'],text=True,timeout=10,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
    if 'gcc' not in version.lower() and 'free software foundation' not in version.lower():
        raise NativeError('this bounded native stack-evidence profile requires GCC')
    stack=resource.getrlimit(resource.RLIMIT_STACK)
    if stack[0]!=8192*1024:raise NativeError('platform-tested native profile requires current8192KiB soft stack limit; no limit change attempted')
    return {'path':str(path),'sha256':sha(path),'version':version,'rlimit_stack':list(stack)}


def check_stack_usage(folder):
    reports={}
    for name in ['program.su','runtime.su']:
        path=folder/name
        if not path.is_file():raise NativeError('compiler did not produce required stack usage: '+name)
        rows=[]
        for line in path.read_text().splitlines():
            parts=line.split('\t')
            if len(parts)!=3:raise NativeError('unknown GCC stack usage record')
            amount=int(parts[1]);qualifier=parts[2]
            if amount>4096 or qualifier not in ['static','dynamic,bounded']:
                raise NativeError('native compiled frame exceeds accepted bounded stack profile: '+line)
            rows.append({'function_location':parts[0],'bytes':amount,'qualifier':qualifier})
        if not rows:raise NativeError('empty compiler stack usage report')
        reports[name]={'sha256':sha(path),'rows':rows}
    return reports


def run_source(source_path:Path,*,groups=False,borrows=False,trace=True,profile='optimized',
               native_lock:Path|None=None,build_parent:Path|None=None,compare_python=True,no_prelude=False):
    local_identity();lock,runtime_blobs=native_identity(native_lock)  # gate before native compilation
    if profile not in ['optimized','sanitized']:raise NativeError('unknown native build profile')
    if type(trace) is not bool or type(compare_python) is not bool:raise NativeError('native flags must be booleans')
    source=Path(source_path).read_bytes();prepared=prepare.prepare_source(source,groups=groups,borrows=borrows,no_prelude=no_prelude)
    generated=codegen.generate(prepared.program(),expected_sha256=prepared.evidence()['resource_check']['sha256'])
    compiler=compiler_identity()
    parent=build_parent or BASE/'build';parent.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='native-'+profile+'-',dir=parent))
    for name,blob in runtime_blobs.items():(folder/name).write_bytes(blob)
    (folder/'program.c').write_text(generated.source)
    (folder/'source.emlf').write_bytes(source)
    (folder/'checked-ir.json').write_text(generated.canonical_ir+'\n')
    common=['-std=c11','-Wall','-Wextra','-Werror','-pedantic','-fstack-usage','-Werror=frame-larger-than=4096']
    options=['-O2'] if profile=='optimized' else ['-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all']
    cc=compiler['path'];commands=[]
    tool_environment={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8','TMPDIR':str(folder)}
    def command(argv,label,stdin=None):
        start=time.monotonic();result=subprocess.run(argv,input=stdin,capture_output=True,cwd=folder,timeout=60,env=tool_environment)
        (folder/(label+'.stdout')).write_bytes(result.stdout);(folder/(label+'.stderr')).write_bytes(result.stderr)
        commands.append({'argv':argv,'cwd':str(folder),'stdin_sha256':hashlib.sha256(stdin).hexdigest() if stdin is not None else None,
                         'exit_code':result.returncode,'wall_seconds':time.monotonic()-start,
                         'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
        if result.returncode or result.stderr:raise NativeError(label+' failed/wrote diagnostics: '+result.stderr.decode(errors='replace'))
    command([cc,*common,*options,'-I'+str(folder),'-x','c','-','-c','-o','program.o'],'compile-program',generated.source.encode())
    command([cc,*common,*options,'-I'+str(folder),'-c','rir_runtime.c','-o','runtime.o'],'compile-runtime')
    stack=check_stack_usage(folder)
    command([cc,*options,'program.o','runtime.o','-o','program'],'link')
    # Inspect the actual target link, not the GHC compiler-host process.
    symbol_result=subprocess.run(['nm','-u',str(folder/'program')],capture_output=True,text=True,env=tool_environment,timeout=10)
    needed_result=subprocess.run(['readelf','-d',str(folder/'program')],capture_output=True,text=True,env=tool_environment,timeout=10)
    if symbol_result.returncode or needed_result.returncode:raise NativeError('native link inspection failed')
    undefined_symbols=symbol_result.stdout.splitlines()
    forbidden=('GC_','hs_init','hs_exit','stg_','Py_','_Py','python')
    if any(any(prefix in symbol for prefix in forbidden) for symbol in undefined_symbols):raise NativeError('unexpected collector/host-runtime symbol in native target')
    needed_libraries=[line.strip() for line in needed_result.stdout.splitlines() if '(NEEDED)' in line]
    if any(any(word in line.lower() for word in ['libgc.','libpython','libhsrts']) for line in needed_libraries):raise NativeError('unexpected GC/host-runtime library in native target')
    target_link={'undefined_symbols':undefined_symbols,'needed_libraries':needed_libraries,'host_GHC_gc_is_not_target_gc':True,
                 'no_tracing_collector_claim_scope':'accepted C group runtime plus actual target link; not compiler host or libc internals'}
    binary=folder/'program';binary_sha=sha(binary)
    environment=dict(tool_environment)
    if profile=='sanitized':environment.update(ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    native_argv=[str(binary)]+(['--trace'] if trace else [])
    start=time.monotonic();execution=subprocess.run(native_argv,capture_output=True,env=environment,timeout=30);elapsed=time.monotonic()-start
    (folder/'native.stdout.json').write_bytes(execution.stdout);(folder/'native.stderr').write_bytes(execution.stderr)
    if execution.stderr:raise NativeError('native executable wrote diagnostics: '+execution.stderr.decode(errors='replace'))
    if execution.returncode not in [0,2]:raise NativeError('native executable terminated unexpectedly: '+str(execution.returncode))
    def no_duplicates(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise NativeError('duplicate native JSON key')
            out[k]=v
        return out
    native=json.loads(execution.stdout,object_pairs_hook=no_duplicates,
                      parse_constant=lambda x:(_ for _ in ()).throw(NativeError('nonfinite native JSON')))
    if set(native.get('metrics',{}))!=EXPECTED_METRICS:raise NativeError('native metric schema missing/extra fields')
    if set(native.get('memory',{}))!=MEMORY_FIELDS or set(native.get('memory_categories',{}))!=MEMORY_CATEGORIES:
        raise NativeError('native full allocation ledger schema differs')
    if any(set(c)!=MEMORY_FIELDS for c in native['memory_categories'].values()):raise NativeError('native category ledger schema differs')
    for counters in [native['metrics'],native['memory'],*native['memory_categories'].values()]:
        if any(type(v) is not int or v<0 for v in counters.values()):raise NativeError('native counters must be nonnegative integers')
    if native.get('artifact_sha256')!=generated.checked_sha256:raise NativeError('native executable reported the wrong checked artifact')
    if (native.get('status')=='complete')!=(execution.returncode==0):raise NativeError('native status/exit mismatch')
    if trace and native['events_omitted']:raise NativeError('native trace truncated; cannot claim complete source observations')
    if native['status']=='complete':
        if native['fault'] is not None:raise NativeError('complete native execution reported a fault')
        m=native['memory']
        if m['live_bytes'] or m['live_blocks'] or m['allocations']!=m['frees'] or m['allocated_bytes']!=m['freed_bytes']:
            raise NativeError('successful native managed allocation ledger is not zero')
        for key in ['allocated_bytes','freed_bytes','live_bytes','allocations','frees','live_blocks']:
            if sum(c[key] for c in native['memory_categories'].values())!=m[key]:
                raise NativeError('native full-category allocation accounting mismatch: '+key)
        if any(c['live_bytes'] or c['live_blocks'] for c in native['memory_categories'].values()):
            raise NativeError('native successful category ledger retains blocks')
    py=prepare.python_observation(prepared) if compare_python else None
    comparisons={'python_executed_separately':compare_python,'timing_claim':False}
    if py is not None:
        if py['status']=='completed':
            if native['status']!='complete':raise NativeError('native/Python normal-outcome mismatch')
            for key,value in native['metrics'].items():
                if key in py['metrics'] and py['metrics'][key]!=value:raise NativeError('native/Python actual metric mismatch: '+key)
            if trace:
                for kind in ['invoke_enter','invoke_raw_return','force_enter','force_return','field_project','fill']:
                    a=[e for e in native['events'] if e['event']==kind];b=[e for e in py['events'] if e['event']==kind]
                    if a!=b:raise NativeError('native/Python ordered observation mismatch: '+kind)
            comparisons['common_metrics_equal']=True;comparisons['ordered_observations_equal']=trace
        elif native['status']!='fault' or native['fault']!=py['fault_code']:
            raise NativeError('native/Python terminal-fault mismatch')
    local_identity();native_identity(native_lock)
    if sha(binary)!=binary_sha or sha(compiler['path'])!=compiler['sha256']:raise NativeError('native executable/compiler changed during invocation')
    if (folder/'program.c').read_text()!=generated.source:raise NativeError('saved generated C changed during build/run')
    for name,blob in runtime_blobs.items():
        if (folder/name).read_bytes()!=blob:raise NativeError('native source snapshot changed during build/run')
    receipt={'status':native['status'],'source_evidence':prepared.evidence(),'codegen_binding':generated.binding(),
             'program':prepared.program(),'generated_c_sha256':hashlib.sha256(generated.source.encode()).hexdigest(),
             'runner_sha256':RUNNER_SHA,'module_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in MODULE_BYTES.items()},
             'native_runtime_lock':lock,'compiler':compiler,'profile':profile,'commands':commands,'stack_usage':stack,
             'compiler_environment':tool_environment,'native_environment':environment,
             'binary_sha256':binary_sha,'build_directory':str(folder),'native_argv':native_argv,
             'execution_wall_seconds_not_benchmark':elapsed,'native':native,'python_reference':py,'comparisons':comparisons,
             'target_link':target_link,'trace_enabled':trace,'LSan_claim':False,'C_runtime_interprets_JSON_or_opcodes':False}
    (folder/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    grouping=p.add_mutually_exclusive_group();grouping.add_argument('--fine',action='store_true');grouping.add_argument('--coarse',action='store_true')
    ownership=p.add_mutually_exclusive_group();ownership.add_argument('--borrow',action='store_true');ownership.add_argument('--owned',action='store_true')
    p.add_argument('--no-prelude',action='store_true');p.add_argument('--no-trace',action='store_true');p.add_argument('--profile',choices=['optimized','sanitized'],default='optimized')
    p.add_argument('--native-lock',type=Path);p.add_argument('--build-parent',type=Path)
    args=p.parse_args()
    try:r=run_source(args.source,groups=args.fine,borrows=args.borrow,trace=not args.no_trace,profile=args.profile,native_lock=args.native_lock,build_parent=args.build_parent,no_prelude=args.no_prelude)
    except (ValueError,subprocess.TimeoutExpired) as error:print(str(error),file=sys.stderr);return 1
    print(json.dumps(r,indent=2));return 0 if r['status']=='complete' else 2
if __name__=='__main__':sys.exit(main())
