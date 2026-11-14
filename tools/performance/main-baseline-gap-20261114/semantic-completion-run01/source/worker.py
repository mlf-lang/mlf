"""Disabled-stage payload implementation. No entry point and no execution on import.
Only the separately reviewed controller may instantiate this under its fresh outer
scope; accepted SETUP records and absolute deadline must be supplied by that controller.
"""
from pathlib import Path
import json,os,time,stat

READY = False

class Completion:
    def __init__(self,C,c,a,env,guard,path,digest,accepted,previous,deadline,oracle,parsers,stats,runtime,identity):
        C.require(C.READY and c['stage']=='COMPLETION','disabled/unreviewed separate completion')
        self.C,self.c,self.a,self.env,self.guard,self.path,self.digest=C,c,a,env,guard,path,digest
        self.E=Path(c['setup_work']);self.Q=self.E/'semantic-completion-01';self.folder=self.Q
        self.oracle,self.parsers,self.stats,self.rp,self.identity=oracle,parsers,stats,runtime,identity
        self.accepted,self.previous,self.deadline=accepted,previous,deadline
        self.number=0;self.outputs=[];self.archives={};self.current_cell=None
        all_inputs=accepted['immutable_inputs']+accepted['immutable_outputs']+previous['immutable_inputs']+previous['pins']+c['source_inputs']+C.verify_setup_scope(c)
        all_inputs += [c[k] for k in ['worker','publication_oracle','semantic_parsers','environment','route_contract','identity_helper','failure_review']]
        all_inputs += [C.pin(C.PB/'BINDINGS.json'),C.pin(C.PB/'controller.py'),C.pin(self.Q/'controller.py'),C.pin(self.Q/'controller.disabled.py'),C.pin(path),C.pin(self.Q/'launch-binding.json')]
        claim = deadline['claim']
        C.require(type(claim) is dict and set(claim)=={'path','bytes','sha256'}
                  and claim['path']==str(self.Q/'claims/COMPLETION.json'),
                  'original launch-binding claim pin at exact completion path required')
        all_inputs += [claim]
        all_inputs += [previous['review'][key] for key in ['scope_inventory','scope_directories','immutable_inputs','partial_outputs_inventory','cell_evidence_inventory','foundation_reference_contract','remaining_original_commands','configuration']]
        all_inputs += list(accepted['actual_pins'].values())+[c['setup_review'],accepted['review']['configuration'],accepted['review']['immutable_inputs'],accepted['review']['immutable_outputs']]
        for role in ['python','shell','ghc','producer','stats-emlf']:
            for value in identity.runtime_rows(accepted['worker']['runtime_after'][role]):
                all_inputs.append({'path':value['resolved'],'bytes':value['bytes'],'sha256':value['sha256']})
        bypath={}
        for p in all_inputs:
            C.require(p['path'] not in bypath or bypath[p['path']]==p,'conflicting repeated input pins');bypath[p['path']]=p
        self.inputs=list(bypath.values());self.identity_snapshot=None
        original=parsers.resolved_commands(C.load(c['plan_commands']['path']),str(self.E),accepted['worker'])
        missing=C.load(C.verify_pin(previous['review']['remaining_original_commands']))
        C.require(len(original)==91 and missing==[dict(x,executed=False) for x in original[84:]],'exact independently frozen seven original missing rows')
        for old,row in zip(previous['worker']['commands'],original[:84]):
            C.require(old['label']==row['label'] and old['kind']==row['kind'] and old['guard']['command']==row['argv_template'],'unchanged exact84 original prefix')
        self.rows=[dict(x,original_ordinal=None,extra_freshness=True) for x in original[:5]]+[dict(x,original_ordinal=x['ordinal'],extra_freshness=False) for x in original[84:]]
        C.require(len(self.rows)==12 and [x['original_ordinal'] for x in self.rows[5:]]==list(range(85,92)),'fixed5+7 completion sequence')
        self.record={'schema':'main-gap-completion-worker-v1','complete':False,'commands':[],'statistics':[],'counts':{},'cells':{},'outputs':[],
            'setup_review':c['setup_review'],'setup_actual_pins':accepted['actual_pins'],'failed_prefix_review':c['failure_review'],
            'original_stage_remains_failed':True,'original_suffix_ordinals':list(range(85,92)),'extra_freshness_commands':5,
            'source_commit':c['source_commit'],'admission':C.pin(path),'configuration':C.pin(C.PB/'BINDINGS.json'),
            'performance_samples':0,'sampling_authorized':False,'dynamic_oracles_accepted':False,'native_execution':False,
            'prechecks':{'full_sweeps':[],'light_check_count':0,'light_elapsed_ns':0,'new_archive_hash_checks':0,
                'scope':'worker precheck intervals only, not controller checks or compiler RTS; sequential wall intervals not CPU attribution'}}
        C.require(type(deadline['start_ns']) is int and type(deadline['deadline_ns']) is int and deadline['deadline_ns']==deadline['start_ns']+175*10**9,'fixed175s whole-start deadline')
    def save(self):self.C.save(self.folder/'completion-receipt.json',self.record)
    def recheck(self):
        start=time.monotonic_ns();C=self.C
        C.require(self.identity_snapshot is not None,'boundary full SHA sweep must precede all children')
        self.identity.check(self.identity_snapshot)
        C.verify_setup_file_set(self.accepted);C.verify_setup_scope(self.c,hash_files=False);C.live_scope_structure(self.current_cell)
        for root,(pins,dirs) in self.archives.items():
            actual=[];r=Path(root)
            for p in r.rglob('*'):
                st=p.lstat();C.require(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode),'new archive special type')
                if p.is_file():C.require(st.st_nlink==1,'new archive hardlink');actual.append(str(p))
            C.require(sorted(actual)==sorted(x['path'] for x in pins) and C.directory_paths(r)==dirs,'completed archive name/type set changed')
        for role in ['python','shell','ghc','producer','stats-emlf']:
            self.identity.runtime_check(self.accepted['worker']['runtime_after'][role])
        gp=C.load(self.c['global_packages']['path']);C.require(sorted(str(p) for p in Path(gp['directory']).iterdir())==gp['entries'],'global packages file set drift')
        C.require(not os.path.lexists('/etc/ld.so.preload'),'unexpected loader preload')
        for item in [self.record['launch_binding'],self.record['admission'],self.record['configuration']]:C.verify_pin(item)
        C.verify_qualifier_scope(self.a,self.c,self.guard,self.path,self.digest,self.record['launch_binding']['sha256'])
        end=time.monotonic_ns();self.record['prechecks']['light_check_count']+=1;self.record['prechecks']['light_elapsed_ns']+=end-start
        C.require(end<self.deadline['deadline_ns'],'whole completion deadline including prechecks')

    def full_recheck(self,phase):
        start=time.monotonic_ns()
        if phase=='entry':
            self.C.require(self.identity_snapshot is None,'single entry attestation');self.identity_snapshot=self.identity.capture(self.inputs)
        else:
            self.C.require(phase=='exit' and self.identity_snapshot is not None,'single completion exit attestation');self.identity.finish(self.identity_snapshot)
        end=time.monotonic_ns()
        self.record['prechecks']['full_sweeps'].append({'phase':phase,'start_ns':start,'end_ns':end,'elapsed_ns':end-start,
            'unique_files':len(self.identity_snapshot),'unique_bytes':sum(x['pin']['bytes'] for x in self.identity_snapshot.values())})
        self.recheck()
    def remember_archive(self,root):
        pins=self.C.tree_pins(root);self.outputs.extend(pins);self.archives[str(root)]=(pins,self.C.directory_paths(root))
        self.identity.extend(self.identity_snapshot,pins);self.record['prechecks']['new_archive_hash_checks']+=1
        return pins
    def command(self,label,argv,reports=()):
        C=self.C;row=self.rows[self.number]
        C.require(label==row['label'] and list(map(str,argv))==row['argv_template'],'exact12 completion argv/order')
        expected_reports=() if 'report_sink' not in row else (row['report_sink'],)
        C.require(tuple(map(str,reports))==expected_reports,'exact mandatory report sink')
        self.recheck()
        seconds=min(row['maximum_seconds'],(self.deadline['deadline_ns']-time.monotonic_ns())//10**9)
        C.require(seconds>=1,'shared semantic absolute deadline exhausted')
        self.number+=1;output=self.folder/'commands'/('%03d-%s'%(self.number,label.replace('/','-')))
        C.require(not output.exists() and output.parent.is_dir(),'guard child absent and parent present')
        for report in reports:C.require(not os.path.lexists(report),'report sink empty before child')
        value=self.guard.run_child(list(map(str,argv)),cwd=Path(self.c['source']),output=output,seconds=int(seconds),reports=list(map(Path,reports)),bounded_root=self.E,accepted_exit_codes=[row.get('expected_exit',0)])
        self.record['commands'].append({'label':label,'kind':row['kind'],'guard':value,'receipt':C.pin(output/'guard.json'),'original_ordinal':row['original_ordinal'],'extra_freshness':row['extra_freshness']})
        self.record['counts'][row['kind']]=self.record['counts'].get(row['kind'],0)+1
        self.save()
        C.require(value['complete'] is True and value['cleanup'] is True and value['reason'] is None and value['exit_code']==row.get('expected_exit',0)
            and value['test_only'] is False and value['standalone_admission'] is False and value['locks']==[] and value['epoch'] is None
            and value['lock_reacquired'] is False and value['bounded_root']==str(self.E) and value['command']==list(map(str,argv))
            and value['cwd']==self.c['source'] and value['output']==str(output) and value['seconds']==seconds and value['limits']==self.guard.LIMITS,'bounded semantic child failed')
        C.require(value['config_sha256']==C.sha(output/'guard-config.json') and set(value['archived'])==set(map(str,reports)),'exactchild config/report set')
        childpins=C.tree_pins(output)
        C.require({str(Path(p['path']).relative_to(output)) for p in childpins}=={'guard.json','guard-config.json','stdout','stderr'}|
                  {str(Path(p['path']).relative_to(output)) for p in value['archived'].values()}
                  and C.directory_paths(output)==['reports'],'exact complete child file/directory inventory')
        stdout=(output/'stdout').read_bytes();stderr=(output/'stderr').read_bytes()
        for field,raw in [('expected_stdout_utf8',stdout),('expected_stderr_utf8',stderr)]:
            if field in row:C.require(raw==row[field].encode('utf8'),'exact byte oracle '+label+' '+field)
        for report in reports:
            item=value['archived'][str(report)];raw=C.verify_pin(item).read_bytes()
            self.record['statistics'].append({'command':label,'raw':item,'parsed':self.stats.parse_statistics(raw),'qualification_only':True})
            C.require(not os.path.lexists(report),'report sink not empty after archive')
        self.remember_archive(output);self.save();self.recheck();return stdout,stderr,value
    def runtime(self,role,when):
        expected=self.accepted['worker']['runtime_after'][role];exe=expected['executable']['path']
        def callback(argv):
            out,err,value=self.command('runtime-'+role+'-'+when,argv)
            self.C.require(err==b'','loader stderr')
            return {'stdout':out.decode(),'stderr':err.decode(),'returncode':0,'auth':self.C.pin(Path(value['output'])/'guard.json')}
        value=self.rp.pin_runtime(exe,callback)
        identity=lambda x:{k:v for k,v in x.items() if k!='command_auth'}
        self.C.require(identity(value)==identity(expected),'runtime differs from qualified setup')
        self.record.setdefault('runtime_'+when,{})[role]=value
    def pack(self,values):return ''.join(str(len(v))+':'+v for v in values)
    def spec_value(self,x):
        if type(x) is str:return x
        self.C.require(type(x) is dict and set(x)=={'pack'} and type(x['pack']) is list,'exact nested spec template')
        return self.pack([self.spec_value(v) for v in x['pack']])
    def new_cell(self,cell,spec):
        C=self.C;p=C.safe(self.E/'active/cells'/cell);C.require(not p.exists(),'fresh active cell required')
        p.mkdir();C.safe(p/'queries').mkdir()
        with C.safe(p/'crate.spec').open('xb') as stream:stream.write(spec)
        self.current_cell=cell;return p
    def raw(self,p):
        rows=self.C.tree_pins(p)
        self.C.require(len(rows)<=self.oracle.MAX_NODES and sum(r['bytes'] for r in rows)<=self.oracle.MAX_BYTES,'bounded whole raw cell inventory before read')
        required_dirs={str(parent) for r in rows for parent in Path(r['path']).relative_to(p).parents if str(parent)!='.'}
        if 'queries/query-graph-v2' in required_dirs:
            required_dirs.add('queries/query-graph-v2/staging')  # production's explicitly empty publication staging directory
        self.C.require(set(self.C.directory_paths(p))==required_dirs,'no unreferenced empty raw artifact directories')
        return {str(Path(r['path']).relative_to(p)):self.C.verify_pin(r).read_bytes() for r in rows}
    def archive(self,p,kind,cell):
        target=self.C.safe(self.folder/kind/cell);self.C.require(not target.exists(),'append-only cell archive')
        before=self.raw(p);p.rename(target);self.C.require(self.raw(target)==before,'archive changed complete bytes')
        self.current_cell=None;pins=self.remember_archive(target);return target,before,pins
    def recheck_query_lock(self,p):
        lock=self.C.safe(p/'queries/.lock',existing=True);st=lock.stat()
        self.guard.reacquire_locks([{'path':str(lock),'device':st.st_dev,'inode':st.st_ino,'kind':'posix'}])
    def run(self):
        C=self.C;self.full_recheck('entry')
        active_root=C.safe(self.E/'active',existing=True);cells=C.safe(active_root/'cells',existing=True)
        C.require(active_root.is_dir() and cells.is_dir() and {x.name for x in active_root.iterdir()}=={'cells'} and not list(cells.iterdir()),'existing active/cells must be real and empty')
        for name in ['commands','stats','ghc']:C.safe(self.folder/name).mkdir(mode=0o700,exist_ok=False)
        roles=['python','shell','ghc','producer','stats-emlf']
        for role in roles:self.runtime(role,'before')
        foundation=self.previous['foundation'];cell='foundation14';ref=C.FAILED/'reference'/cell
        baseline_pin=self.previous['review']['foundation_reference_contract'];C.require(C.load(C.verify_pin(baseline_pin))==foundation,'original immutable reference contract')
        old=self.raw(ref);spec=old['crate.spec'];route=foundation['observed']
        C.require(self.oracle.sha(spec)==foundation['spec_sha256'] and foundation['original_active_path']==str(cells/cell),'unchanged original active path/spec')
        authenticated=self.oracle.reference_cell(old,C.sha(C.verify_pin(self.accepted['original_binary'])),self.c['cell_route_contracts'][cell]['config'])
        C.require(authenticated==route,'original full reference reauthentication before B')
        # Same original logical scratch spelling; no old archive is moved or rewritten.
        active=self.new_cell(cell,spec);row=self.rows[self.number];C.require(row['original_ordinal']==85 and row['kind']=='stats_compile','only original Foundation B remains')
        self.command(row['label'],row['argv_template'],[Path(row['report_sink'])]);self.recheck_query_lock(active)
        actual=self.raw(active);query=self.parsers.fresh_queries(actual['unit.queries'],foundation['query_observation']['crate'])
        C.require(C.load(C.verify_pin(baseline_pin))==foundation and self.raw(ref)==old,'original reference immutable after B')
        proof=self.oracle.compare_cell(old,actual,C.sha(C.verify_pin(self.accepted['original_binary'])),C.sha(C.verify_pin(self.accepted['stats_binary'])),route['configuration_template'],8)
        _,_,bpins=self.archive(active,'stats',cell)
        row=self.rows[self.number];C.require(row['original_ordinal']==86 and row['kind']=='ghc_typed','only original Foundation G remains')
        C.safe(active).mkdir();C.safe(active/'objects').mkdir();self.current_cell=cell
        out,err,_=self.command(row['label'],row['argv_template'],[Path(row['report_sink'])]);events=self.parsers.ghc_compiling(out,err,row['expected_home_modules'])
        raw=self.raw(active);C.require(set(raw)=={'objects/'+x for x in row['expected_relative_interfaces']} and all(raw.values()),'exact14 fresh nonempty GHC typed interfaces')
        _,_,gpins=self.archive(active,'ghc',cell)
        self.record['cells'][cell]={'complete':True,'query':query,'show_stdout':foundation['show_stdout'],'formula_outputs':[],
            'reference_contract':baseline_pin,'reference':foundation['reference_files'],'stats':bpins,'ghc':gpins,'cross_producer':proof,
            'ghc_compiling':events,'original_active_path':foundation['original_active_path'],'dynamic_oracles_accepted':False}
        self.save()
        for role in roles:self.runtime(role,'after')
        C.require(self.number==12 and len(self.record['statistics'])==2 and self.record['counts']=={'runtime':10,'stats_compile':1,'ghc_typed':1},'complete exact12/2 suffix')
        C.require([x['original_ordinal'] for x in self.record['commands']]==[None]*5+list(range(85,92)),'original91 spine remains84+7 with5 freshness only')
        C.require(not list(cells.iterdir()) and not (active_root/'mlf.stats').exists(),'active scratch and fixed sink restored empty')
        self.full_recheck('exit');self.record['outputs']=self.outputs;self.record['complete']=True;self.save()
