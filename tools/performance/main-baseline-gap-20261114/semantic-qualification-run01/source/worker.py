"""Disabled-stage payload implementation. No entry point and no execution on import.
Only the separately reviewed controller may instantiate this under its fresh outer
scope; accepted SETUP records and absolute deadline must be supplied by that controller.
"""
from pathlib import Path
import json,os,time

READY = False

class Semantic:
    def __init__(self,C,c,a,env,guard,path,digest,accepted,deadline,oracle,parsers,stats,runtime):
        C.require(C.READY and c['stage']=='SEMANTIC','disabled/unreviewed stage')
        self.C,self.c,self.a,self.env,self.guard,self.path,self.digest=C,c,a,env,guard,path,digest
        self.E=Path(c['setup_work']);self.Q=self.E/'semantic-qualification-01';self.folder=self.Q
        self.oracle,self.parsers,self.stats,self.rp=oracle,parsers,stats,runtime
        self.accepted=accepted;self.deadline=deadline;self.number=0;self.outputs=[];self.archives={};self.current_cell=None
        new_inputs=[c[k] for k in ['worker','publication_oracle','semantic_parsers','environment','route_contract']]
        historical=C.load(C.verify_pin(c['setup_scope_inventory']))
        old_scope=[{k:p[k] for k in ['path','bytes','sha256']} for p in historical['files']]
        all_inputs=accepted['immutable_inputs']+accepted['immutable_outputs']+c['source_inputs']+new_inputs+old_scope+list(accepted['actual_pins'].values())+[
            c['setup_review'],accepted['review']['configuration'],accepted['review']['immutable_inputs'],accepted['review']['immutable_outputs']]
        bypath={}
        for p in all_inputs:
            C.require(p['path'] not in bypath or bypath[p['path']]==p,'conflicting repeated input pins')
            bypath[p['path']]=p
        self.inputs=list(bypath.values())
        self.rows=parsers.resolved_commands(C.load(c['plan_commands']['path']),str(self.E),accepted['worker'])
        self.record={'schema':'main-gap-semantic-worker-v1','complete':False,'commands':[],'statistics':[],
            'setup_review':c['setup_review'],'setup_actual_pins':accepted['actual_pins'],'source_commit':c['source_commit'],
            'admission':C.pin(path),'configuration':C.pin(C.PB/'BINDINGS.json'),'counts':{},'cells':{},'outputs':[],
            'performance_samples':0,'sampling_authorized':False,'dynamic_oracles_accepted':False,'native_execution':False}
        C.require(type(deadline['start_ns']) is int and type(deadline['deadline_ns']) is int and
                  deadline['deadline_ns']==deadline['start_ns']+595*10**9,'whole outer-start deadline minus fixed5s headroom')
    def save(self):self.C.save(self.folder/'semantic-receipt.json',self.record)
    def recheck(self):
        for item in self.inputs+self.outputs:self.C.verify_pin(item)
        self.C.verify_setup_file_set(self.accepted)
        self.C.verify_setup_scope(self.c,hash_files=False);self.C.live_scope_structure(self.current_cell)
        for root,(pins,dirs) in self.archives.items():
            self.C.require(self.C.tree_pins(Path(root))==pins and self.C.directory_paths(Path(root))==dirs,'completed archive inventory/bytes changed')
        # Same exact read-only binding/config predicates as the mature worker;
        # loader execution occurs only in the frozen ten runtime commands.
        for role in ['python','shell','ghc','producer','stats-emlf']:
            runtime=self.accepted['worker']['runtime_after'][role]
            for value in [runtime['executable'],runtime['loader'],*runtime['config']['files'],*[x['binding'] for x in runtime['libraries']]]:
                self.C.require(self.rp.binding(value['path'])==value,'runtime binding drift')
            self.C.require(self.rp.config_snapshot(runtime['config_paths'],runtime['config_dirs'])==runtime['config'],'runtime config drift')
        gp=self.C.load(self.c['global_packages']['path'])
        self.C.require(sorted(str(p) for p in Path(gp['directory']).iterdir())==gp['entries'],'global package file set drift')
        self.C.require(not os.path.lexists('/etc/ld.so.preload'),'unexpected loader preload')
        self.C.verify_pin(self.record['launch_binding'])
        self.C.require(time.monotonic_ns()<self.deadline['deadline_ns'],'whole-stage deadline including prechecks')
    def remember_archive(self,root):
        pins=self.C.tree_pins(root);self.outputs.extend(pins);self.archives[str(root)]=(pins,self.C.directory_paths(root));return pins
    def command(self,label,argv,reports=()):
        C=self.C;row=self.rows[self.number]
        C.require(label==row['label'] and list(map(str,argv))==row['argv_template'],'exact91 command argv/order')
        expected_reports=() if 'report_sink' not in row else (row['report_sink'],)
        C.require(tuple(map(str,reports))==expected_reports,'exact mandatory report sink')
        self.recheck()
        seconds=min(row['maximum_seconds'],(self.deadline['deadline_ns']-time.monotonic_ns())//10**9)
        C.require(seconds>=1,'shared semantic absolute deadline exhausted')
        self.number+=1;output=self.folder/'commands'/('%03d-%s'%(self.number,label.replace('/','-')))
        C.require(not output.exists() and output.parent.is_dir(),'guard child absent and parent present')
        for report in reports:C.require(not os.path.lexists(report),'report sink empty before child')
        value=self.guard.run_child(list(map(str,argv)),cwd=Path(self.c['source']),output=output,seconds=int(seconds),reports=list(map(Path,reports)),bounded_root=self.E,accepted_exit_codes=[row.get('expected_exit',0)])
        self.record['commands'].append({'label':label,'kind':row['kind'],'guard':value,'receipt':C.pin(output/'guard.json')})
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
        C=self.C;self.recheck()
        C.require(C.safe(self.E/'active',existing=True).is_dir() and not list((self.E/'active').iterdir()),'accepted setup active directory must be exactly empty')
        for name in ['commands','reference','reference-contracts','stats','ghc']:C.safe(self.folder/name).mkdir(mode=0o700,exist_ok=False)
        C.safe(self.E/'active/cells').mkdir(mode=0o700,exist_ok=False)
        roles=['python','shell','ghc','producer','stats-emlf']
        for role in roles:self.runtime(role,'before')
        cells=[r['cell'] for r in self.rows if r['kind']=='reference_compile'];C.require(len(cells)==12,'exact12 cells')
        for cell in cells:
            row=self.rows[self.number];C.require(row['kind']=='reference_compile' and row['cell']==cell,'reference order')
            spec=self.pack([self.spec_value(x) for x in row['crate_spec_fields_template']]).encode('utf8');active=self.new_cell(cell,spec)
            self.command(row['label'],row['argv_template']);self.recheck_query_lock(active)
            old=self.raw(active);meta=self.rows[self.number];contract=meta['stdout_contract'];route=self.c['cell_route_contracts'][cell]
            C.require(route['route_format_source_evidence'] is not None and route['config'][-1] is None and route['checked_schema']==8,'reviewed reference-observation contract required')
            query=self.parsers.fresh_queries(old['unit.queries'],contract['crate'])
            shown,_,_=self.command(meta['label'],meta['argv_template']);C.interface(shown.decode(),contract['crate'],contract['owned_modules'],{k:v.replace('<INDEPENDENTLY_ACCEPTED_SETUP_WORK>',str(self.E)) for k,v in contract['dependencies'].items()})
            formula=[]
            while self.rows[self.number]['kind']=='reference_formula':
                q=self.rows[self.number];out,_,_=self.command(q['label'],q['argv_template']);formula.append({'input':q['argv_template'][-1],'stdout':out.decode()})
            C.require(self.raw(active)==old,'read-only reference controls changed artifacts')
            ref,old,refpins=self.archive(active,'reference',cell)
            observed=self.oracle.reference_cell(old,C.sha(C.verify_pin(self.accepted['original_binary'])),route['config'])
            # Freeze once before any B invocation. It is not a route chosen from B.
            baseline={'schema':'main-gap-cell-original-reference-v3','cell':cell,'source_commit':self.c['source_commit'],
                'source_inputs':self.c['source_inputs'],'setup_review':self.c['setup_review'],'original_binary':self.accepted['original_binary'],
                'original_active_path':str(active),'spec_sha256':self.oracle.sha(spec),'reference_files':refpins,
                'reference_commands':[r for r in self.record['commands'] if r['label'].startswith(cell+'/')],
                'query_observation':query,'formula_outputs':formula,'show_stdout':shown.decode(),'observed':observed,
                'performance_sample':False,'candidate_invoked':False,'retry_allowed':False}
            frozen=C.safe(self.folder/'reference-contracts'/(cell+'.json'))
            with frozen.open('x') as stream:
                json.dump(baseline,stream,sort_keys=True,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
            baseline_pin=C.pin(frozen);self.outputs.append(baseline_pin)
            C.require(C.load(C.verify_pin(baseline_pin))==baseline and self.raw(ref)==old,'immutable original reference before B')
            self.recheck()
            active=self.new_cell(cell,spec);row=self.rows[self.number];C.require(row['kind']=='stats_compile','stats order')
            self.command(row['label'],row['argv_template'],[Path(row['report_sink'])]);self.recheck_query_lock(active)
            actual=self.raw(active);self.parsers.fresh_queries(actual['unit.queries'],contract['crate'])
            C.require(C.load(C.verify_pin(baseline_pin))==baseline and self.raw(ref)==old,'immutable original reference after B')
            proof=self.oracle.compare_cell(old,actual,C.sha(C.verify_pin(self.accepted['original_binary'])),C.sha(C.verify_pin(self.accepted['stats_binary'])),observed['configuration_template'],8)
            b,braw,bpins=self.archive(active,'stats',cell)
            row=self.rows[self.number];C.require(row['kind']=='ghc_typed','GHC order');C.safe(active).mkdir();C.safe(active/'objects').mkdir();self.current_cell=cell
            out,err,_=self.command(row['label'],row['argv_template'],[Path(row['report_sink'])])
            events=self.parsers.ghc_compiling(out,err,row['expected_home_modules'])
            files=self.raw(active);C.require(set(files)=={'objects/'+x for x in row['expected_relative_interfaces']} and all(files.values()),'exact fresh nonempty typed interfaces only')
            g,graw,gpins=self.archive(active,'ghc',cell)
            self.record['cells'][cell]={'complete':True,'query':query,'show_stdout':shown.decode(),'formula_outputs':formula,'reference_contract':baseline_pin,'reference':refpins,'stats':bpins,'ghc':gpins,'cross_producer':proof,'ghc_compiling':events,'original_active_path':str(active),'dynamic_oracles_accepted':False}
            self.save()
        for role in roles:self.runtime(role,'after')
        C.require(self.number==91 and len(self.record['statistics'])==24 and len(self.record['cells'])==12,'complete91/24/12 stage')
        expected=C.load(self.c['plan_commands']['path'])['counts'];C.require(self.record['counts']==expected,'exact command kind counts')
        C.require(not list((self.E/'active/cells').iterdir()) and not (self.E/'active/mlf.stats').exists(),'active cells and stats sink empty')
        self.recheck();self.record['outputs']=self.outputs;self.record['complete']=True;self.save()
