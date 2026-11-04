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
NATIVE_ACCEPTANCE_SHA256="8a3d126888fe1e556ef0582d835e2076dcdd4b92d68c773b7094c7c2d64c6c7f"  # independently accepted exact C runtime
MODULE_BYTES={name:(BASE/(name+'.py')).read_bytes() for name in ['prepare','codegen']}
if hashlib.sha256(MODULE_BYTES['codegen']).hexdigest()!='a07c17655f08bd576363ce49ec81d6c7a0075b278d2680733d06e3218b082200':raise ValueError('accepted codegen changed before source-byte import')
for name,blob in MODULE_BYTES.items():
    module=types.ModuleType(name);module.__file__=str(BASE/(name+'.py'));sys.modules[name]=module
    exec(compile(blob,module.__file__,'exec'),module.__dict__)
prepare=sys.modules['prepare'];codegen=sys.modules['codegen']

EXPECTED_METRICS=set("steps groups_allocated groups_closed nodes_allocated nodes_freed peak_groups peak_nodes peak_owner_handles owner_handle_acquisitions owner_handle_releases loan_handle_acquisitions loan_handle_releases force_calls max_force_depth callback_calls ordinary_calls applications_allocated raw_deferred_returns memo_writes internal_memo_slots cross_group_memo_slots memo_fast_paths groups_closed_during_force borrowed_slot_publications ir_retain_ops ir_drop_ops ir_borrow_ops ir_end_borrow_ops ir_application_borrow_ops max_activation_depth rc_inc_total rc_dec_total repeat_calls".split()) | {"rc_"+way+"_"+kind for way in ["inc","dec"] for kind in ["owner","builder","pin","key","slot"]}
EXPECTED_METRICS.add('entries_completed')
MEMORY_FIELDS=set("allocated_bytes freed_bytes live_bytes peak_bytes allocations frees live_blocks peak_blocks".split())
MEMORY_CATEGORIES={"context","groups","nodes","slots","handles","captures","pending"}

class NativeError(ValueError):pass

def compare_event_streams(native_events, model_events, program):
    """Validate native-only explicit-Force markers, then compare ALL common events.

    No raw event is discarded from receipts. The model has no ir_force_result
    opcode-location marker; each native marker must match its checked block's
    next Force and the immediately preceding real force_return payload. Complete
    executions must account for every Force in each observed straight-line frame.
    """
    frames={};common=[];markers=[]
    for index,event in enumerate(native_events):
        if event.get('event')=='frame_enter':
            frame=event['frame'];context=event['context'];kind=context['kind']
            if type(frame) is not int or frame in frames:raise NativeError('duplicate/invalid observed frame')
            if kind=='entry':body=program['entry']
            elif kind=='thunk':body=program['codes'][context['name']]['body']
            elif kind=='function':body=program['functions'][context['name']]['body']
            else:raise NativeError('unsupported observed native frame kind')
            frames[frame]={'forces':[item for item in body if item['op']=='force'],'seen':0}
        if event.get('event')!='ir_force_result':
            common.append(event);continue
        if set(event)!={'event','result','group','layout','owner','frame','out','source_variable'}:
            raise NativeError('native explicit-Force marker schema differs')
        if index==0 or native_events[index-1].get('event')!='force_return':
            raise NativeError('native explicit-Force marker lacks preceding force_return')
        previous=native_events[index-1]
        if any(event[key]!=previous[key] for key in ['result','group','layout','owner']):
            raise NativeError('native explicit-Force marker payload differs')
        frame=frames.get(event['frame'])
        if frame is None or frame['seen']>=len(frame['forces']):raise NativeError('extra native explicit-Force marker')
        instruction=frame['forces'][frame['seen']]
        if event['out']!=instruction['out'] or event['source_variable']!=instruction['value']:
            raise NativeError('native explicit-Force marker differs from checked IR binding/order')
        frame['seen']+=1;markers.append(event)
    if any(frame['seen']!=len(frame['forces']) for frame in frames.values()):
        raise NativeError('missing native explicit-Force markers')
    if common!=model_events:raise NativeError('native/Python complete common ordered event mismatch')
    return {'complete_common_event_sequence_equal':True,'native_only_force_markers_checked':len(markers),
            'raw_native_events':len(native_events),'model_common_events':len(model_events),
            'raw_native_trace_retained_without_deletion':True}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def local_identity():
    if sha(__file__)!=RUNNER_SHA:raise NativeError('native runner changed since source-byte load')
    for name,blob in MODULE_BYTES.items():
        if (BASE/(name+'.py')).read_bytes()!=blob:raise NativeError('native module changed since source-byte load: '+name)
    prepare.frozen_reference()


def native_identity(lock_path:Path|None=None):
    path=lock_path or BASE/'validation/native-runtime-lock.json'
    if not path.is_file():raise NativeError('native lifecycle lock is absent')
    lock=json.loads(path.read_text());receipt=BASE/lock['audit_receipt']
    if (lock.get('schema')!='source-terminal-native-lock/1' or
        lock.get('audit_receipt_sha256')!=NATIVE_ACCEPTANCE_SHA256 or sha(receipt)!=NATIVE_ACCEPTANCE_SHA256):
        raise NativeError('native lifecycle lock does not name pinned independent receipt')
    accepted=json.loads(receipt.read_text())
    if (accepted.get('schema')!='terminal-destroy-native-independent-acceptance/1' or
        accepted.get('verdict')!='ACCEPTED_BOUNDED_OPT_IN_LIFECYCLE' or
        accepted.get('identity')!='resource-ir-terminal-destroy/1'):
        raise NativeError('native lifecycle acceptance differs')
    if (lock.get('identity')!=accepted['identity'] or lock.get('files')!=accepted['native_sha256'] or
        lock.get('implementation_manifest_sha256')!=accepted['implementation_manifest_sha256']):
        raise NativeError('native lifecycle lock differs from accepted source map')
    manifest_path=BASE/lock['implementation_manifest']
    if sha(manifest_path)!=accepted['implementation_manifest_sha256']:raise NativeError('native implementation manifest changed')
    manifest=json.loads(manifest_path.read_text())
    if set(lock['files'])!={'rir_runtime.c','rir_runtime.h'}:raise NativeError('native ABI inventory differs')
    root=BASE/lock['runtime_location'];blobs={}
    for file,digest in lock['files'].items():
        blob=(root/file).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=digest:raise NativeError('accepted native runtime bytes changed: '+file)
        if manifest['files']['native/'+file]!={'bytes':len(blob),'sha256':digest}:raise NativeError('native manifest map differs')
        blobs[file]=blob
    return lock,blobs


def evaluation_envelope(raw,policy):
    if policy=='diagnostic':
        if not isinstance(raw,dict) or 'schema' in raw:raise NativeError('diagnostic report schema changed')
        return raw,None
    if policy!='destroy-terminal':raise NativeError('unsupported failure policy')
    if not isinstance(raw,dict) or set(raw)!={'schema','evaluation','destruction'} or raw['schema']!='resource-ir-terminal-run/1':
        raise NativeError('terminal runner envelope differs')
    native=raw['evaluation'];d=raw['destruction']
    if not isinstance(native,dict) or not isinstance(d,dict) or set(d)!={'status','retired_blocks','retired_bytes','totals_overflow','categories'}:
        raise NativeError('terminal destruction schema differs')
    if any(type(d[k]) is not int or d[k]<0 for k in ['status','retired_blocks','retired_bytes']):raise NativeError('invalid destruction counter')
    if d['totals_overflow'] is not False or set(d['categories'])!=MEMORY_CATEGORIES:raise NativeError('destruction overflow/category mismatch')
    for c in d['categories'].values():
        if not isinstance(c,dict) or set(c)!={'blocks','bytes'} or any(type(v) is not int or v<0 for v in c.values()):raise NativeError('invalid destruction category')
    if sum(c['blocks'] for c in d['categories'].values())!=d['retired_blocks'] or sum(c['bytes'] for c in d['categories'].values())!=d['retired_bytes']:raise NativeError('destruction category sum differs')
    normal=native.get('status')=='complete'
    if d['status']!=(2 if normal else 1):raise NativeError('unexpected source destruction status')
    # This source admission has successful open; OOM before context is not qualified here.
    expected=(0,0) if normal else (native['memory']['live_blocks'],native['memory']['live_bytes'])
    if (d['retired_blocks'],d['retired_bytes'])!=expected:raise NativeError('source destruction totals differ from preserved pre-destroy ledger')
    for name,c in d['categories'].items():
        before=native['memory_categories'][name]
        if (c['blocks'],c['bytes'])!=((0,0) if normal else (before['live_blocks'],before['live_bytes'])):raise NativeError('source destruction category differs from preserved ledger')
    return native,d


def validate_observer(observed,native,destruction):
    required={'schema','memory','context_requested_bytes','context_freed_last','live_allocations','report_status','report_fault'}
    if not isinstance(observed,dict) or set(observed)!=required or observed['schema']!='runtime-physical-observer/1':raise NativeError('physical observer schema differs')
    memory=observed['memory']
    if set(memory)!=MEMORY_FIELDS or any(type(v) is not int or v<0 for v in memory.values()):raise NativeError('physical observer counters differ')
    if type(observed['context_requested_bytes']) is not int or observed['context_requested_bytes']<=0 or type(observed['context_freed_last']) is not bool:raise NativeError('physical context observation differs')
    if observed['report_status']!=native['status'] or observed['report_fault']!=native['fault']:raise NativeError('post-wrapper report pointers changed')
    if memory['allocated_bytes']!=native['memory']['allocated_bytes'] or memory['allocations']!=native['memory']['allocations']:raise NativeError('physical allocation totals differ')
    if memory['allocated_bytes']-memory['freed_bytes']!=memory['live_bytes'] or memory['allocations']-memory['frees']!=memory['live_blocks']:raise NativeError('physical accounting imbalance')
    rows=observed['live_allocations']
    if not isinstance(rows,list) or len(rows)!=memory['live_blocks']:raise NativeError('physical live map count differs')
    seen=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'pointer','bytes'} or not isinstance(row['pointer'],str) or row['pointer'] in seen or type(row['bytes']) is not int or row['bytes']<=0:raise NativeError('physical live map row differs')
        seen.add(row['pointer'])
    if sum(row['bytes'] for row in rows)!=memory['live_bytes']:raise NativeError('physical live map bytes differ')
    retired=destruction or {'retired_bytes':0,'retired_blocks':0}
    if memory['freed_bytes']!=native['memory']['freed_bytes']+retired['retired_bytes'] or memory['frees']!=native['memory']['frees']+retired['retired_blocks']:raise NativeError('physical frees differ from ordinary plus terminal retirements')
    zero=native['status']=='complete' or destruction is not None
    if zero:
        if memory['live_blocks'] or memory['live_bytes'] or not observed['context_freed_last']:raise NativeError('runtime allocations remain after terminal/ordinary close')
    elif memory['live_blocks']!=native['memory']['live_blocks'] or memory['live_bytes']!=native['memory']['live_bytes'] or observed['context_freed_last']:
        raise NativeError('diagnostic physical retention differs')
    return observed


OBSERVER_PINS={'allocation_observer.c': '20e61a6bbbbeb382df307ffbb89dc43436260c93f9014ee79bfa1caa43e44d3c', 'allocation_observer.h': 'fdcceca45b2ff972e6136697c610f599e30536daa352b7ef8ee6e45e17179093'}
def observer_identity():
    if set(OBSERVER_PINS)!={'allocation_observer.c','allocation_observer.h'}:raise NativeError('observer identity pending')
    blobs={}
    for name,digest in OBSERVER_PINS.items():
        blob=(BASE/'observation'/name).read_bytes()
        if hashlib.sha256(blob).hexdigest()!=digest:raise NativeError('physical observer source changed: '+name)
        blobs[name]=blob
    return blobs

def compiler_identity():
    path=shutil.which('cc')
    if path is None:raise NativeError('existing C compiler unavailable; no installation attempted')
    path=Path(path).resolve();version=subprocess.check_output([str(path),'--version'],text=True,timeout=10,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
    if 'gcc' not in version.lower() and 'free software foundation' not in version.lower():
        raise NativeError('this bounded native stack-evidence profile requires GCC')
    stack=resource.getrlimit(resource.RLIMIT_STACK)
    if stack[0]!=8192*1024:raise NativeError('platform-tested native profile requires current8192KiB soft stack limit; no limit change attempted')
    return {'path':str(path),'sha256':sha(path),'version':version,'rlimit_stack':list(stack)}


def check_stack_usage(folder,observe_allocations=False):
    reports={}
    for name in ['program.su','runtime.su']+(['observer.su'] if observe_allocations else []):
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
               native_lock:Path|None=None,build_parent:Path|None=None,compare_python=True,no_prelude=False,module_root:Path|None=None,
               failure_policy='diagnostic',observe_allocations=False):
    if failure_policy not in ('diagnostic','destroy-terminal'):raise NativeError('unsupported failure policy')
    if type(observe_allocations) is not bool:raise NativeError('observer flag must be boolean')
    local_identity();lock,runtime_blobs=native_identity(native_lock)  # gate before native compilation
    observer_blobs=observer_identity() if observe_allocations else {}
    if profile not in ['optimized','sanitized']:raise NativeError('unknown native build profile')
    if type(trace) is not bool or type(compare_python) is not bool:raise NativeError('native flags must be booleans')
    if module_root is None:
        source=Path(source_path).read_bytes();prepared=prepare.prepare_source(source,groups=groups,borrows=borrows,no_prelude=no_prelude)
    else:
        prepared=prepare.prepare_module_source(source_path,module_root=module_root,build_parent=build_parent or BASE/'build',
            groups=groups,borrows=borrows,no_prelude=no_prelude)
        source=prepared.source
    prepare.verify_source_package(prepared.evidence())
    generated=codegen.generate(prepared.program(),expected_sha256=prepared.evidence()['resource_check']['sha256'],
                               failure_policy=failure_policy,observe_allocations=observe_allocations)
    compiler=compiler_identity()
    parent=build_parent or BASE/'build';parent.mkdir(parents=True,exist_ok=True)
    folder=Path(tempfile.mkdtemp(prefix='native-'+profile+'-',dir=parent))
    for name,blob in runtime_blobs.items():(folder/name).write_bytes(blob)
    for name,blob in observer_blobs.items():(folder/name).write_bytes(blob)
    if observe_allocations:
        (folder/'runtime-observed.c').write_text('#include "allocation_observer.h"\n#define malloc rir_observer_malloc\n#define calloc rir_observer_calloc\n#define free rir_observer_free\n#include "rir_runtime.c"\n')
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
    command([cc,*common,*options,'-I'+str(folder),'-c','runtime-observed.c' if observe_allocations else 'rir_runtime.c','-o','runtime.o'],'compile-runtime')
    if observe_allocations:command([cc,*common,*options,'-I'+str(folder),'-c','allocation_observer.c','-o','observer.o'],'compile-observer')
    stack=check_stack_usage(folder,observe_allocations)
    command([cc,*options,'program.o','runtime.o',*(['observer.o'] if observe_allocations else []),'-o','program'],'link')
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
    prepare.verify_source_package(prepared.evidence())
    start=time.monotonic();execution=subprocess.run(native_argv,capture_output=True,cwd=folder,env=environment,timeout=30);elapsed=time.monotonic()-start
    (folder/'native.stdout.json').write_bytes(execution.stdout);(folder/'native.stderr').write_bytes(execution.stderr)
    if execution.stderr:raise NativeError('native executable wrote diagnostics: '+execution.stderr.decode(errors='replace'))
    if execution.returncode not in [0,2]:raise NativeError('native executable terminated unexpectedly: '+str(execution.returncode))
    def no_duplicates(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise NativeError('duplicate native JSON key')
            out[k]=v
        return out
    raw_native=json.loads(execution.stdout,object_pairs_hook=no_duplicates,
                      parse_constant=lambda x:(_ for _ in ()).throw(NativeError('nonfinite native JSON')))
    native,destruction=evaluation_envelope(raw_native,failure_policy)
    physical=None
    if observe_allocations:
        physical=json.loads((folder/'allocation-observer.json').read_text(),object_pairs_hook=no_duplicates)
        validate_observer(physical,native,destruction)
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
        if native['metrics']['entries_completed']!=1:raise NativeError('single-source entry completion count differs')
        checked_type=prepared.evidence()['actual_checked_export']['checked_type']
        while checked_type['tag']=='forall':checked_type=checked_type['body']
        actual=native.get('result')
        if checked_type=={'tag':'constructor','name':'()','arguments':[]}:
            if actual is not None:raise NativeError('Unit entry reported scalar result')
        else:
            kind={'Int':'i64','Bool':'bool'}.get(checked_type.get('name'))
            if type(actual) is not dict or set(actual)!={'kind','value'} or actual['kind']!=kind:
                raise NativeError('native scalar result schema/type differs from actual checked source')
            value=actual['value']
            if kind=='i64' and (type(value) is not int or not -(1<<63)<=value<(1<<63)):
                raise NativeError('native Int64 result is not canonical')
            if kind=='bool' and type(value) is not bool:raise NativeError('native Bool result is not intrinsic boolean')
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
            if native.get('result')!=py.get('result'):raise NativeError('native/Python actual scalar result mismatch')
            for key,value in native['metrics'].items():
                if key in py['metrics'] and py['metrics'][key]!=value:raise NativeError('native/Python actual metric mismatch: '+key)
            if trace:
                comparisons['event_contract']=compare_event_streams(native['events'],py['events'],prepared.program())
                for kind in ['invoke_enter','invoke_raw_return','force_enter','force_return','field_project','fill']:
                    a=[e for e in native['events'] if e['event']==kind];b=[e for e in py['events'] if e['event']==kind]
                    if a!=b:raise NativeError('native/Python ordered observation mismatch: '+kind)
            comparisons['actual_scalar_result_equal']=True
            comparisons['common_metrics_equal']=True;comparisons['ordered_observations_equal']=trace
        elif native['status']!='fault' or native['fault']!=py['fault_code']:
            raise NativeError('native/Python terminal-fault mismatch')
    local_identity();native_identity(native_lock)
    prepare.verify_source_package(prepared.evidence())
    if observe_allocations:
        if observer_identity()!=observer_blobs:raise NativeError('observer changed during invocation')
        for name,blob in observer_blobs.items():
            if (folder/name).read_bytes()!=blob:raise NativeError('observer snapshot changed during invocation')
    if sha(binary)!=binary_sha or sha(compiler['path'])!=compiler['sha256']:raise NativeError('native executable/compiler changed during invocation')
    if (folder/'program.c').read_text()!=generated.source:raise NativeError('saved generated C changed during build/run')
    for name,blob in runtime_blobs.items():
        if (folder/name).read_bytes()!=blob:raise NativeError('native source snapshot changed during build/run')
    receipt={'status':native['status'],'failure_policy':failure_policy,'raw_native_envelope':raw_native,
             'destruction':destruction,'physical_observer':physical,
             'observer_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in observer_blobs.items()},
             'source_evidence':prepared.evidence(),'codegen_binding':generated.binding(),
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
    p.add_argument('--no-model',action='store_true',help='execute native target only; still perform actual source and resource checking')
    p.add_argument('--failure-policy',choices=['diagnostic','destroy-terminal'],default='diagnostic')
    p.add_argument('--observe-allocations',action='store_true',help='bounded qualification-only external runtime allocation observer')
    p.add_argument('--native-lock',type=Path);p.add_argument('--build-parent',type=Path)
    p.add_argument('--module-root',type=Path,help='opt-in bounded actual module loader/full-check/projection route; requires --no-prelude and coarse-owned')
    args=p.parse_args()
    try:r=run_source(args.source,groups=args.fine,borrows=args.borrow,trace=not args.no_trace,profile=args.profile,native_lock=args.native_lock,build_parent=args.build_parent,no_prelude=args.no_prelude,compare_python=not args.no_model,module_root=args.module_root,failure_policy=args.failure_policy,observe_allocations=args.observe_allocations)
    except (ValueError,subprocess.TimeoutExpired) as error:print(str(error),file=sys.stderr);return 1
    print(json.dumps(r,indent=2));return 0 if r['status']=='complete' else 2
if __name__=='__main__':sys.exit(main())
