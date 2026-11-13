#!/usr/bin/env python3
"""Five independently admitted sparse-SCC stages. Preparation never launches GHC.

An admission is a coordinator-authored, SHA-bound review artifact, not an approval
that this program generates. Failure consumes the stage claim; no retry/resume.
"""
from pathlib import Path
import argparse, json, os, re, sys, time
import guard, mirror, oracles as O
import profile as allocation
HERE=Path(__file__).resolve().parent
BUDGETS={'BUILD':600,'QUALIFY':180,'PROBE-CONTROLS':420,'TARGET-QUALIFICATION':420,'ATTRIBUTION':240}
ORDER=list(BUDGETS)
EXHAUSTIVE=['-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns']
CONTROL_OUTPUTS=[('version',0,b'emlf 0.3.0\n',b''),('identity',0,b'MLF/shared-haskell-v1 GHC\n',b''),('semantic-42',0,b'42\n',b''),('unicode-positive',0,'λ雪🙂\n'.encode(),b''),('type-rejection',1,b'',b'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n')]

def code_pins():
    files=[*HERE.glob('*.py'),HERE/'insertion-map.json',HERE/'foundation14-source.json',*sorted((HERE/'fixtures').rglob('*'))]
    return {str(p):O.sha(p) for p in sorted(set(files)) if p.is_file()}

def prepare(source,work):
    source=O.safe(source,True); work=O.safe(work); O.absent(work)
    manifest=O.frozen_source(source); rows=O.foundation(source,HERE/'foundation14-source.json')
    work.mkdir(mode=0o700); m=mirror.prepare(source,work/'mirror')
    for name in ['claims','guards','stages','active','tmp']: (work/name).mkdir(mode=0o700)
    source_pins={str(source/r['path']):O.sha(source/r['path']) for r in manifest['modules']}
    source_pins.update({str(source/p):O.sha(source/p) for p in m['files']})
    for p in [source/'shared-sources.json',source/'tools/shared/build.py',source/'tools/shared/test_direct.py',source/'tools/shared/verify_builtin_prelude.py',source/'tools/shared/builtin_prelude_identity.py',source/'tools/shared/verify_prepared_libraries.py',source/'tools/performance/a1-private-index/helper.py',source/'host/ghc/cbits/host.c',source/'runtime/mlf_process_supervisor.c',*sorted((source/'runtime').glob('*.h'))]: source_pins[str(p)]=O.sha(p)
    plan=dict(schema='sparse-scc-plan-v1',execution_authorized=False,source_commit=O.BASE,source=str(source),work=str(work),source_pins=source_pins,foundation=rows,stages=BUDGETS,full_shared_count=137,diagnostic_union_count=95,diagnostic_shared_count=91,host_count=4,main_count=2,target_bytes=173594,target_fresh=475,mirror_manifest=O.pin(work/'mirror/mirror-manifest.json'),sprint_start='2026-11-10',native_ab=False,fixed_point=False,ordinary_cpu_attribution=False)
    O.save(work/'plan.json',plan)
    return plan

def validate_original_environment(environment,original,work):
    """Preserve exact ordinary toolchain entries; only bound temporary output."""
    O.require(environment==dict(original,TMPDIR=str(Path(work)/'tmp')),
              'only TMPDIR may differ from authenticated ordinary environment')


def validate_admission(path,digest,phase):
    O.require(phase in BUDGETS,'unknown stage'); O.require(O.sha(path)==digest,'admission SHA')
    a=O.load(path); O.require(a['schema']=='sparse-scc-admission-v1' and a['approved'] is True and a['phase']==phase,'separate stage admission required')
    plan=O.load(O.verify_pin(a['plan'])); work=O.safe(plan['work'],True)
    O.absent(work/'quarantine.json')
    O.require(plan['schema']=='sparse-scc-plan-v1' and plan['source_commit']==O.BASE and plan['stages']==BUDGETS,'fixed protocol plan')
    O.require(a['code_pins']==code_pins(),'reviewed implementation inventory changed')
    O.check_pins(a['code_pins']); O.check_pins(plan['source_pins'])
    O.require(a['review']['complete'] is True and a['review']['scc_inverse_and_grouping'] is True and a['review']['fixtures_and_coverage'] is True,'independent implementation review required')
    O.verify_pin(a['review']['receipt'])
    tests=O.load(O.verify_pin(a['static_tests']))
    O.require(tests['complete'] is True and tests['compiler_started'] is False and tests['tested_code']==a['code_pins'],'fresh lightweight test receipt required')
    epoch=O.load(O.verify_pin(a['epoch']))
    O.require(epoch['boot_id']==Path('/proc/sys/kernel/random/boot_id').read_text().strip() and epoch['schema']=='astra-lock-epoch-v1' and epoch['new_epoch'] is True and epoch['historical_continuity_claimed'] is False,'current boot/epoch required')
    workspace=O.safe(a['workspace'],True)
    O.require(work.is_relative_to(workspace) and Path(a['locks'][0]['path'])==workspace/'.astra-resource-locks/heavy.lock','current shared lock path')
    O.absent(guard.epoch_quarantine_path(a['locks'],a['epoch']))
    O.require(len(a['locks'])==2 and [epoch['shared'],epoch['reproduction']]==a['locks'] and epoch['workspace']==str(workspace) and epoch['shared_peer_contention_passed'] is True and epoch['reproduction_reacquired'] is True,'two current epoch locks')
    O.require(O.safe(a['locks'][1]['path'])==Path(plan['source'])/'.mlf-build/.reproduction.lock','required source reproduction lock')
    O.require(a['budget_seconds']==BUDGETS[phase] and a['per_compile_seconds']==180,'fixed time bounds')
    O.require(not any(k in os.environ for k in O.FORBIDDEN),'semantic/query instrumentation forbidden even empty')
    O.require(a['environment']['GHC_ENVIRONMENT']=='-' and a['environment']['GHCRTS']=='' and a['environment']['LC_ALL']=='C.UTF-8','fixed runtime environment')
    O.require(not any(k in a['environment'] for k in O.FORBIDDEN),'query instrumentation forbidden')
    O.require(not any(k in a['environment'] for k in ['LD_PRELOAD','LD_AUDIT','LD_DEBUG','LD_DEBUG_OUTPUT','LD_PROFILE','LD_ASSUME_KERNEL','GLIBC_TUNABLES','GHC_PACKAGE_PATH','GHC_CHARENC','HPCTIXFILE']),'unadmitted loader/compiler override')
    O.require(a['environment'].get('PYTHONDONTWRITEBYTECODE')=='1','no bytecode writes')
    O.require(a['environment'].get('TMPDIR')==str(work/'tmp') and (work/'tmp').is_dir(),'all compiler temporary output must be bounded')
    O.require(all(isinstance(k,str) and isinstance(v,str) for k,v in a['environment'].items()),'environment strings required')
    O.require(set(a['environment']).issubset({'HOME','PATH','LD_LIBRARY_PATH','LC_ALL','LANG','TZ','GHC_ENVIRONMENT','GHCRTS','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MAKEFLAGS','PYTHONDONTWRITEBYTECODE','TMPDIR','CC','TC','LIBRARY_PATH','PKG_CONFIG_PATH'}),'only explicit non-secret execution environment keys allowed')
    validate_original_environment(a['environment'],O.load(O.verify_pin(a['ordinary']['environment'])),work)
    O.require(set(a['prior'])==set(ORDER[:ORDER.index(phase)]),'all prior stages, no automatic continuation')
    for previous,binding in a['prior'].items():
        receipt=O.load(O.verify_pin(binding['receipt'])); outer=O.load(O.verify_pin(binding['outer']))
        O.require(receipt['complete'] is True and receipt['phase']==previous and receipt['plan']==a['plan'] and receipt['epoch']==a['epoch'] and receipt['code_pins']==a['code_pins'],'prior stage binding')
        O.require(outer['complete'] is True and outer['test_only'] is False and outer['cleanup'] is True and outer['lock_reacquired'] is True and outer['standalone_admission'] is True and outer.get('lease_cleared') is True,'prior stage outer cleanup')
        O.require(outer['command']==receipt['worker_command'] and outer['seconds']==BUDGETS[previous] and outer['limits']==guard.LIMITS and outer['locks']==a['locks'] and outer['epoch']==a['epoch'] and outer['bounded_root']==str(work) and outer['output']==str(work/'guards'/previous) and outer['cwd']==str(HERE),'prior command, lock epoch and bound')
        O.require(receipt['environment']==a['environment'],'runtime environment changed between stages')
        import runtime_pins
        for binding in receipt.get('alias_bindings',[]): O.require(runtime_pins.binding(binding['path'])==binding,'prior runtime alias binding changed')
        O.check_pins(receipt['output_pins']); O.check_pins(receipt['input_pins'])
    return a,plan

def verified_builtin_pins(verified,receipt):
    """Import an already authenticated original verifier receipt by its schema.

    source_identity_inputs.modules contains RELATIVE semantic source names. Do
    not recursively reinterpret that metadata as absolute filesystem identities.
    The unchanged verifier authenticates its complete absolute inputs map and
    exact two command outputs before this function is called.
    """
    O.require(verified['complete'] is True and verified['immutable_inputs_verified_after'] is True,
              'completed authenticated builtin verification required')
    inputs=dict(verified['inputs']);O.require(bool(inputs),'builtin absolute inputs missing')
    O.check_pins(inputs)
    outputs={str(O.regular(receipt)):O.sha(receipt)}
    rows=verified['commands']
    O.require([r['label'] for r in rows]==['check-candidate','fresh-literal'],'builtin verification commands')
    for row in rows:
        for key in ['stdout','stderr']:
            path=O.verify_pin(row[key]);outputs[str(path)]=row[key]['sha256']
    return inputs,outputs


def profile_flags(original,source,producer,mirror_root,objects):
    # Only source/output relocation plus explicit profiling way. All demand,
    # package and optimization switches are copied from exact original flags.
    result=[]
    for value in original:
        if value.startswith('-i') and value!='-i':
            p=Path(value[2:]); O.require(p.is_relative_to(source),'foreign include root')
            target=Path(mirror_root)/p.relative_to(source)
            if target.is_dir(): result.append('-i'+str(target))
        elif value==str(Path(producer)/'objects'): result.append(str(objects))
        else: result.append(value)
    return ['-prof','-osuf','p_o','-hisuf','p_hi',*result]

def main_profile_flags(flags,objects,main_dir):
    """One-shot imports use common -hidir; only Main output is redirected."""
    result=list(flags)
    for key in ['-odir','-hidir']:
        O.require(result.count(key)==1,'one pinned '+key+' required')
        index=result.index(key)
        O.require(index+1<len(result) and result[index+1]==str(objects),'common profile '+key+' binding')
    O.require('-ohi' not in result,'unexpected interface override')
    result[result.index('-odir')+1]=str(main_dir)
    return [*result,'-i'+str(objects),'-ohi',str(Path(main_dir)/'Main.p_hi')]


def build_entry_roots(manifest,mirror_root):
    """Two original entry roots; the observed compile union must still be all95."""
    return [Path(mirror_root)/manifest['union'][name]
            for name in ['MLF.Entry.Emlf','MLF.Entry.BuiltinPrelude']]


def compile_records(raw,manifest,objects,role,cwd):
    rows=[]
    for name,path in re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),',raw):
        p=Path(path.strip()); p=p if p.is_absolute() else Path(cwd)/p
        obj=Path(objects)/(name.replace('.','/')+'.p_o')
        rows.append(dict(module=name,source=str(p),object=str(obj),interface=str(obj.with_suffix('.p_hi'))))
    mirror.validate_provenance(rows,manifest,role)
    for row in rows:
        for key in ['object','interface']: O.regular(row[key])
    return rows

class Stage:
    def __init__(self,a,plan,phase,admission,digest):
        self.a=a; self.plan=plan; self.phase=phase; self.source=Path(plan['source']); self.work=Path(plan['work']); self.out=self.work/'stages'/phase
        O.absent(self.out); self.out.mkdir(mode=0o700); (self.out/'commands').mkdir()
        self.start=time.monotonic(); self.counter=0; self.alias_bindings=[]; self.alias_binding_keys=set()
        self.record=dict(schema='sparse-scc-stage-v1',phase=phase,complete=False,plan=a['plan'],epoch=a['epoch'],code_pins=a['code_pins'],environment=a['environment'],alias_bindings=[],input_pins={**plan['source_pins'],**a['code_pins'],str(admission):digest},output_pins={},commands=[],worker_command=worker_command(phase,admission,digest),interpretation='profiled source-demand allocation, not ordinary exclusive CPU or speedup')
        for previous,binding in a['prior'].items():
            saved=O.load(O.verify_pin(binding['receipt']))
            self.record['input_pins'].update(saved['input_pins']); self.record['input_pins'].update(saved['output_pins'])
            self.pin_inputs(saved.get('alias_bindings',[]))
        self.save()
    def save(self): O.save(self.out/'receipt.json',self.record)
    def pin_inputs(self,value):
        if isinstance(value,dict):
            if isinstance(value.get('path'),str) and isinstance(value.get('sha256'),str):
                if 'resolved' in value and 'links' in value:
                    import runtime_pins
                    O.require(runtime_pins.binding(value['path'])==value,'runtime alias binding changed')
                    # Verify every encounter above, including duplicates. Only
                    # exact-value retained entries collapse; checkpoints still
                    # reverify every distinct alias and all content hashes.
                    key=json.dumps(value,sort_keys=True,separators=(',',':'))
                    if key not in self.alias_binding_keys:
                        self.alias_binding_keys.add(key)
                        self.alias_bindings.append(value); self.record['alias_bindings'].append(value)
                    p=O.regular(value['resolved'])
                else: p=O.verify_pin(value)
                self.record['input_pins'][str(p)]=value['sha256']
            for v in value.values(): self.pin_inputs(v)
        elif isinstance(value,list):
            for v in value: self.pin_inputs(v)
    def recheck(self):
        O.check_pins(self.record['input_pins']); O.check_pins(self.record['output_pins']); O.frozen_source(self.source)
        if self.alias_bindings:
            import runtime_pins
            for binding in self.alias_bindings: O.require(runtime_pins.binding(binding['path'])==binding,'runtime alias drift')
    def output_pin(self,path): self.record['output_pins'][str(O.regular(path))]=O.sha(path)
    def reports(self,role): return [self.work/'active'/(role+'.prof'),self.work/'active'/(role+'.stats')]
    def command(self,label,argv,maximum=15,roles=(),accepted=(0,)):
        self.recheck(); self.counter+=1; folder=self.out/'commands'/('%03d-%s'%(self.counter,label))
        left=BUDGETS[self.phase]-(time.monotonic()-self.start); O.require(left>0,'stage deadline exhausted')
        reports=[p for role in roles for p in self.reports(role)]
        for p in reports: O.absent(p)
        row=guard.run_child(list(map(str,argv)),cwd=self.source,output=folder,seconds=min(maximum,left),reports=reports,bounded_root=self.work,accepted_exit_codes=accepted)
        self.record['commands'].append(dict(label=label,guard=O.pin(folder/'guard.json') if (folder/'guard.json').exists() else None,**row)); self.save()
        O.require(row['complete'] and not row['test_only'] and row['standalone_admission'] is False,'command failed: '+label+': '+str(row.get('reason')))
        self.recheck()
        for path in [folder/'stdout',folder/'stderr',folder/'guard.json',folder/'guard-config.json']: self.output_pin(path)
        for item in row['archived'].values():
            self.output_pin(item['path'])
            if item['path'].endswith('.prof'):
                allocation.parse_profile(Path(item['path']).read_bytes())
            elif item['path'].endswith('.stats'):
                import stats
                stats.parse_statistics(Path(item['path']).read_bytes())
        return (folder/'stdout').read_bytes(),(folder/'stderr').read_bytes(),row
    def clean_command(self,*args,expected=b'',**kwargs):
        out,err,row=self.command(*args,**kwargs); O.require(out==expected and not err,'exact stdout/empty stderr'); return row
    def provenance(self):
        self.pin_inputs(self.a['ordinary']); producer=Path(self.a['ordinary']['producer'])
        auth=O.authenticate(producer,self.source); O.require(O.sha(producer/'receipt.json')==self.a['ordinary']['receipt']['sha256'],'current ordinary receipt')
        self.pin_inputs(auth)
        for group in ['toolchain','installed_dependencies']:
            for p,h in auth[group]['files'].items(): self.record['input_pins'][p]=h
        for p,h in auth['object_inputs'].items(): self.record['input_pins'][str(producer/p)]=h
        controls=O.load(O.verify_pin(self.a['ordinary']['controls'])); self.pin_inputs(controls)
        O.require(controls['complete'] is True and controls['full_object_inputs_verified'] is True,'new ordinary focused qualification required')
        O.require(controls['producer_receipt']['sha256']==self.a['ordinary']['receipt']['sha256'],'ordinary controls producer binding')
        rows=controls['commands']; O.require(len(rows)==len(CONTROL_OUTPUTS),'ordinary focused controls inventory')
        for row,(label,code,out,err) in zip(rows,CONTROL_OUTPUTS):
            O.require(row['label']==label and row['passed'] is True and row['exit_code']==code and row['argv'][0]==auth['outputs']['emlf']['path'] and row['cwd']==str(self.source),'ordinary focused control binding')
            O.require(O.verify_pin(row['stdout']).read_bytes()==out and O.verify_pin(row['stderr']).read_bytes()==err,'authored ordinary control result')
        # New producer guard must name this exact original build. Old hashes are
        # never substituted for these actual files/current successful execution.
        outer=O.load(O.verify_pin(self.a['ordinary']['build_outer']))
        O.require(outer['complete'] is True and outer['exit_code']==0 and outer['reason'] is None,'ordinary build not successfully guarded')
        expected=['-B',str(self.source/'tools/shared/build.py'),'--bootstrap-only','--optimization','2','--build-dir',str(producer)]
        O.require(outer['command'][-len(expected):]==expected,'original ordinary build command')
        self.auth=auth; self.producer=producer; self.controls=controls; self.manifest=mirror.verify_mirror(self.source,self.work/'mirror')
        self.record['ordinary_receipt']=self.a['ordinary']['receipt']; self.recheck(); self.save()
    def runtime(self,label,include_profile):
        import runtime_pins
        executables={'ordinary':self.auth['outputs']['emlf']['path'],'python':str(Path(sys.executable).resolve()),'ghc':self.auth['toolchain']['actual_ghc']['path'],'cc':self.auth['cc']['path']}
        if include_profile:
            executables.update({r:str(self.work/'build/bin'/r) for r in ['emlf','builtin-prelude']})
        records={}
        for role,path in executables.items():
            def run(argv):
                out,err,row=self.command(label+'-'+role,argv)
                return dict(stdout=out.decode(),stderr=err.decode(),returncode=row['exit_code'],auth=O.pin(self.out/'commands'/('%03d-%s'%(self.counter,label+'-'+role))/'guard.json'))
            records[role]=runtime_pins.pin_runtime(path,run)
            self.pin_inputs(records[role])
            records[role].pop('command_auth')
        if include_profile and hasattr(self,'build_runtime'): O.require(records==self.build_runtime,'runtime differs from authenticated BUILD')
        return records
    def built(self):
        prior=O.load(O.verify_pin(self.a['prior']['BUILD']['receipt']))
        O.require(prior['build']['union_count']==95 and prior['build']['mains']==2,'diagnostic build scope')
        self.record['input_pins'].update(prior['input_pins']); self.record['input_pins'].update(prior['output_pins']); self.pin_inputs(prior.get('alias_bindings',[])); self.recheck()
        import runtime_pins
        runtime_pins.verify_packages(prior['profiling_packages'],self.a['profiling_packages']['configurations'],pkgroot=self.a['profiling_packages']['pkgroot'])
        self.build_runtime=prior['runtime_after']
        return {r:self.work/'build/bin'/r for r in ['emlf','builtin-prelude']}
    def build(self):
        import runtime_pins
        dest=self.work/'build'; O.absent(dest); dest.mkdir(); objects=dest/'objects';objects.mkdir(); (dest/'bin').mkdir()
        profiling=runtime_pins.profile_packages(self.producer/'packages.txt',self.auth['package_database_sha256'],self.a['profiling_packages']['configurations'],pkgroot=self.a['profiling_packages']['pkgroot'])
        self.record['profiling_packages']=profiling; self.pin_inputs(profiling)
        before=self.runtime('runtime-before',False); self.record['runtime_before']=before
        c_objects=[]
        for label,relative in [('host','host/ghc/cbits/host.c'),('supervisor','runtime/mlf_process_supervisor.c')]:
            original=[self.auth['cc']['path'],'-O2','-std=c11','-I'+str(self.source/'runtime'),'-c',str(self.source/relative),'-o',str(self.producer/(label+'.o'))]
            matches=[r for r in self.auth['commands'] if r['argv']==original and r['cwd']==str(self.source) and r['exit_code']==0]
            O.require(len(matches)==1,'original C command reconstruction')
            target=dest/(label+'.o'); self.command('rebuild-'+label,[*original[:-1],target],maximum=600)
            O.require(target.read_bytes()==Path(original[-1]).read_bytes(),'C raw object mismatch'); self.output_pin(target); c_objects.append(target)
        flags=profile_flags(self.auth['flags'],self.source,self.producer,self.work/'mirror',objects)
        argv=[self.auth['ghc']['path'],'--make','-j1','-fforce-recomp','-v','-ddump-types','-no-link',*EXHAUSTIVE,*flags,*build_entry_roots(self.manifest,self.work/'mirror')]
        out,err,_=self.command('compile-union',argv,maximum=600)
        observed=compile_records((out+err).decode(),self.manifest,objects,'union',self.source)
        for row in observed:
            for k in ['object','interface']: self.output_pin(row[k])
        for role in ['emlf','builtin-prelude']:
            main_dir=dest/(role+'-main'); main_dir.mkdir(); main=self.work/'mirror'/self.manifest['mains'][role]
            main_flags=main_profile_flags(flags,objects,main_dir)
            # -c only uses already-qualified profiled interfaces, never ordinary.
            out,err,_=self.command('compile-'+role+'-main',[self.auth['ghc']['path'],'-c','-fforce-recomp','-v',*EXHAUSTIVE,*main_flags,main,'-o',main_dir/'Main.p_o'],maximum=600)
            # One-shot -c need not print --make's progress grammar. Its command,
            # separate source pin and exclusive fresh outputs are retained.
            row=dict(module='Main',source=str(main),object=str(main_dir/'Main.p_o'),interface=str(main_dir/'Main.p_hi'))
            mirror.validate_provenance([row],self.manifest,role+'-main')
            for k in ['object','interface']: self.output_pin(row[k])
            shown,errors,_=self.command('inspect-'+role+'-main',[self.auth['ghc']['path'],'--show-iface',row['interface']],maximum=30)
            text=shown.decode(); expected_entry='MLF.Entry.Emlf' if role=='emlf' else 'MLF.Entry.BuiltinPrelude'
            O.require(not errors and re.search(r'(?m)^interface Main\b',text) and expected_entry in text and re.search(r'\bmain ::',text),'actual Main interface provenance')
            names=self.manifest['emlf_modules' if role=='emlf' else 'generator_modules']
            profile_base=self.work/'active'/role; stats=self.work/'active'/(role+'.stats')
            for p in self.reports(role): O.absent(p)
            self.command('link-'+role,[self.auth['ghc']['path'],*flags,'-rtsopts=ignoreAll','-with-rtsopts=-pj -po'+str(profile_base)+' -s'+str(stats),main_dir/'Main.p_o',*[objects/(n.replace('.','/')+'.p_o') for n in names],*c_objects,'-o',dest/'bin'/role],maximum=600)
            self.output_pin(dest/'bin'/role)
        O.require(not list(dest.rglob('*.o')) or set(dest.rglob('*.o'))==set(c_objects),'ordinary Haskell object mixing')
        after=self.runtime('runtime-after',True)
        O.require({k:v for k,v in after.items() if k in before}==before,'runtime drift during build')
        self.record.update(build=dict(union_count=95,mains=2,actual_union=observed,flags=flags),runtime_after=after)
    def qualify(self):
        binaries=self.built(); before=self.runtime('runtime-before',True); self.record['runtime_before']=before
        manifest=O.frozen_source(self.source)
        self.clean_command('all137-check-shared',[binaries['emlf'],'--check-shared',*[self.source/r['path'] for r in manifest['modules']]],maximum=180,roles=['emlf'],expected=b'PASS shared syntax/name resolution: 137 modules\n')
        for row,(label,code,out,err) in zip(self.controls['commands'],CONTROL_OUTPUTS):
            actual_out,actual_err,_=self.command(label,[binaries['emlf'],*row['argv'][1:]],maximum=30,roles=['emlf'],accepted=(code,))
            O.require((actual_out,actual_err)==(out,err),'profiled authored CLI/semantic result')
        verification=self.out/'builtin-verification'
        self.clean_command('fresh-builtin-verifier',[sys.executable,'-B',self.source/'tools/shared/verify_builtin_prelude.py','--root',self.source,'--compiler',binaries['emlf'],'--generator',binaries['builtin-prelude'],'--output',verification,'--timeout','180'],maximum=180,roles=['emlf','builtin-prelude'],expected=(str(verification/'receipt.json')+'\n').encode())
        verifier=O.module(self.source/'tools/shared/verify_builtin_prelude.py')
        verified=verifier.authenticate(O.pin(verification/'receipt.json'),self.source,binaries['emlf'],binaries['builtin-prelude'])
        self.record['builtin_verification']=O.pin(verification/'receipt.json')
        verified_inputs,verified_outputs=verified_builtin_pins(verified,verification/'receipt.json')
        self.record['input_pins'].update(verified_inputs);self.record['output_pins'].update(verified_outputs)
        self.setup_builtin()
        after=self.runtime('runtime-after',True); O.require(after==before,'runtime changed'); self.record['runtime_after']=after
    def query_lock(self,path):
        from guard import reacquire_locks
        p=O.regular(path); st=p.stat()
        reacquire_locks([dict(path=str(p),device=st.st_dev,inode=st.st_ino,kind='posix')])
    def setup_builtin(self):
        folder=self.work/'builtin'; O.absent(folder);folder.mkdir();(folder/'queries').mkdir()
        fixture=folder/'Fixture.emlf';fixture.write_bytes(b'module Fixture where\nvalue = 42\n')
        prefix=folder/'fixture';builtin=folder/'builtin';spec=folder/'crate.spec'
        fields=['MLF-CRATE-1','compiler-shapes/builtin','','false',O.pack([O.pack(['Fixture',str(fixture)])]),'',str(folder/'queries'),str(builtin)]
        spec.write_text(O.pack(fields)); self.output_pin(fixture);self.output_pin(spec)
        self.clean_command('fresh-fixed-builtin',[self.auth['outputs']['emlf']['path'],'--compile-crate',spec,'-o',prefix],maximum=120)
        O.fresh(O.load(str(prefix)+'.queries'),'compiler-shapes/builtin',1)
        for suffix in O.SUFFIXES: self.output_pin(str(prefix)+suffix)
        for suffix in O.SUFFIXES[:2]: self.output_pin(str(builtin)+suffix)
        self.show(prefix,'compiler-shapes/builtin',['Fixture'],{O.BUILTIN:str(builtin)+'.mlfci'})
        self.show(builtin,O.BUILTIN,['Prelude','MLF.Primitive'],{})
        self.query_lock(folder/'queries/.lock')
        self.record['builtin_setup']=dict(complete=True,prefix=str(builtin),fresh_groups=1,reused_groups=0,query_lock_reacquired=True)
    def show(self,prefix,identity,modules,deps):
        out,err,_=self.command('show-'+Path(prefix).parent.name+'-'+Path(prefix).name,[self.auth['outputs']['emlf']['path'],'--show-crate',str(prefix)+'.mlfci'])
        O.require(not err,'show-crate stderr'); O.interface(out.decode(),identity,modules,deps)
    def targets(self,attribution=False):
        binaries=self.built(); q=O.load(O.verify_pin(self.a['prior']['QUALIFY']['receipt']))
        self.record['input_pins'].update(q['output_pins']); self.recheck()
        O.require(q['builtin_setup']['complete'] is True and q['builtin_setup']['prefix']==str(self.work/'builtin/builtin'),'fresh fixed builtin setup')
        before=self.runtime('runtime-before',True); self.record['runtime_before']=before; builtin=self.work/'builtin/builtin'
        self.show(builtin,O.BUILTIN,['Prelude','MLF.Primitive'],{})
        reference=self.work/'stages/TARGET-QUALIFICATION/ordinary-Q/unit'
        roles=['attribution-P'] if attribution else ['ordinary-Q','qualification-P']
        self.record['legs']=[]
        for role in roles:
            folder=self.out/role;O.absent(folder);folder.mkdir();(folder/'queries').mkdir()
            prefix=folder/'unit';spec=folder/'crate.spec'
            rows=O.foundation(self.source,HERE/'foundation14-source.json')
            fields=['MLF-CRATE-1',O.IDENTITY,'','false',O.pack([O.pack([r['module'],str(self.source/r['relative'])]) for r in rows]),O.pack([str(builtin)+'.mlfci']),str(folder/'queries'),str(builtin)]
            spec.write_text(O.pack(fields)); O.require(O.unpack(spec.read_text())==fields,'exact spec'); self.output_pin(spec)
            for s in O.SUFFIXES: O.absent(str(prefix)+s)
            ordinary=role=='ordinary-Q'; binary=self.auth['outputs']['emlf']['path'] if ordinary else binaries['emlf']
            row=self.clean_command(role,[binary,'--compile-crate',spec,'-o',prefix],maximum=180,roles=[] if ordinary else ['emlf'])
            self.record['output_pins'].update(O.three_artifacts(prefix,None if ordinary else reference))
            self.show(prefix,O.IDENTITY,[r['module'] for r in rows],{O.BUILTIN:str(builtin)+'.mlfci'});self.query_lock(folder/'queries/.lock')
            leg=dict(role=role,complete=True,fresh=475,reused=0,all14_owners_checked=True,builtin_checked=True,full_ordered_query_checked=True,three_raw_equal=not ordinary,query_lock_reacquired=True,guard=row)
            if attribution:
                raw=next(v for k,v in row['archived'].items() if k.endswith('.prof'))
                summary=allocation.parse_profile(O.verify_pin(raw).read_bytes())
                control_binding=self.a['prior']['PROBE-CONTROLS']['receipt']; control=O.load(O.verify_pin(control_binding))
                unit=control['allocation_unit_control']; O.require(control['probe_controls_complete'] is True and unit['complete'] is True and unit['unit']=='bytes','real allocation unit controls required')
                self.pin_inputs(unit['writer'])
                evidence=dict(toolchain_sha256=self.auth['toolchain']['actual_ghc']['sha256'],installed_rts_definition_sha256=unit['writer']['sha256'],control_receipt_sha256=control_binding['sha256'],writer_alloc_unit='bytes',control_expected_bytes=unit['expected_byte_delta'],control_observed_raw=unit['raw_delta'],control_passed=True)
                summary=allocation.qualify_units(summary,evidence,toolchain_sha256=self.auth['toolchain']['actual_ghc']['sha256'])
                O.save(self.out/'allocation-raw-partition.json',summary);self.output_pin(self.out/'allocation-raw-partition.json')
                import stats
                raw_stats=next(v for k,v in row['archived'].items() if k.endswith('.stats'))
                self.record['rts_statistics']=stats.parse_statistics(O.verify_pin(raw_stats).read_bytes())
                self.record['allocation_units']='bytes qualified by installed writer expression and real byte-array allocation delta; no equality to RTS required'
            self.record['legs'].append(leg); self.save()
        after=self.runtime('runtime-after',True);O.require(after==before,'runtime drift');self.record['runtime_after']=after
    def controls_phase(self):
        self.built()
        import controls
        controls.run(self)
    def run(self):
        try:
            self.provenance()
            {'BUILD':self.build,'QUALIFY':self.qualify,'PROBE-CONTROLS':self.controls_phase,'TARGET-QUALIFICATION':self.targets,'ATTRIBUTION':lambda:self.targets(True)}[self.phase]()
            self.recheck(); O.require(time.monotonic()-self.start<BUDGETS[self.phase],'phase deadline')
            self.record.update(complete=True,elapsed_seconds=time.monotonic()-self.start);self.save()
        except BaseException as error:
            self.record.update(error=repr(error),elapsed_seconds=time.monotonic()-self.start);self.save();raise

def worker_command(phase,admission,digest): return [str(Path(sys.executable).resolve()),'-B',str(HERE/'controller.py'),'_worker',phase,'--admission',str(admission),'--sha256',digest]

def launch(phase,admission,digest):
    a,plan=validate_admission(admission,digest,phase); work=Path(plan['work']); O.absent(guard.epoch_active_path(a['locks'],a['epoch']));claim=work/'claims'/(phase+'.json')
    with claim.open('x') as f: json.dump(dict(phase=phase,admission=O.pin(admission),retry_allowed=False),f)
    os.environ.clear();os.environ.update(a['environment'])
    row=guard.run_guard(worker_command(phase,admission,digest),cwd=HERE,output=work/'guards'/phase,locks=a['locks'],epoch=a['epoch'],seconds=BUDGETS[phase],bounded_root=work)
    O.require(row['complete'],'stage failed; claim spent; no automatic retry: '+str(row.get('reason')))
    result=O.load(work/'stages'/phase/'receipt.json'); O.require(result['complete'],'worker incomplete')
    return row

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    prep=sub.add_parser('prepare');prep.add_argument('--source',type=Path,required=True);prep.add_argument('--work',type=Path,required=True)
    for name in ['run','_worker']:
        q=sub.add_parser(name);q.add_argument('phase',choices=ORDER);q.add_argument('--admission',type=Path,required=True);q.add_argument('--sha256',required=True)
    a=p.parse_args()
    if a.command=='prepare': print(json.dumps(prepare(a.source,a.work),indent=2));return
    if a.command=='run': print(json.dumps(launch(a.phase,a.admission,a.sha256),indent=2));return
    admission,plan=validate_admission(a.admission,a.sha256,a.phase)
    guard.verify_worker_scope(worker_command(a.phase,a.admission,a.sha256),cwd=HERE,output=Path(plan['work'])/'guards'/a.phase,locks=admission['locks'],epoch=admission['epoch'],seconds=BUDGETS[a.phase],bounded_root=plan['work'],claim_path=Path(plan['work'])/'claims'/(a.phase+'.json'),claim_expected=dict(phase=a.phase,admission=O.pin(a.admission),retry_allowed=False))
    O.require(dict(os.environ)==admission['environment'],'worker did not inherit exact admitted environment')
    Stage(admission,plan,a.phase,a.admission,a.sha256).run()
if __name__=='__main__':main()
