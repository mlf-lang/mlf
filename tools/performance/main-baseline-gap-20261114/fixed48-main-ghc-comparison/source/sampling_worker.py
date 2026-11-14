"""Disabled sampling payload skeleton. No entry point or import-time activity.
The final coordinator supplies independently accepted semantic oracles, source
pins and fresh admission/deadline. No value is inferred from a live run here.
"""
from pathlib import Path
import json,os,time,stat
READY = False

class Sampling:
    def __init__(self,C,c,a,env,guard,path,digest,accepted,deadline,oracle,parsers,stats,runtime,identity):
        C.require(C.READY and c['configuration_complete'] is True and c['block'] in (1,2),'unbound disabled sampler')
        self.C,self.c,self.a,self.env,self.guard,self.path,self.digest=C,c,a,env,guard,path,digest
        self.E=Path(c['setup_work']);self.Q=self.E/('sampling-%02d'%c['block']);self.folder=self.Q
        self.accepted,self.deadline=accepted,deadline
        self.oracle,self.parsers,self.stats,self.rp,self.identity=oracle,parsers,stats,runtime,identity
        self.number=0;self.outputs=[];self.archives={};self.current_cell=None;self.identity_snapshot=None
        self.rows=C.resolved_sampling_rows(c,accepted)
        C.require(len(self.rows)==32 and sum(r['kind']=='measured_leg' for r in self.rows)==24,'fixed24 plus8 support')
        all_inputs=accepted['immutable_inputs']+accepted['immutable_outputs']+accepted['prior']['scope_files']+accepted['prior']['pins']+c['source_inputs']
        all_inputs += C.load(C.PB/'MANIFEST.json')['files']+[C.pin(C.PB/'MANIFEST.json'),C.pin(C.PB/'BINDINGS.json'),
            C.pin(self.Q/'controller.py'),C.pin(self.Q/'controller.disabled.py'),C.pin(path),C.pin(self.Q/'launch-binding.json')]
        claim=deadline['claim']
        C.require(type(claim) is dict and set(claim)=={'path','bytes','sha256'} and claim['path']==str(self.Q/'claims'/('SAMPLE'+str(c['block'])+'.json')),'original launch-binding claim pin at exact sampling path')
        all_inputs += [claim]
        for role in ['python','shell','ghc','stats-emlf']:
            for value in identity.runtime_rows(accepted['worker']['runtime_after'][role]):
                all_inputs.append({'path':value['resolved'],'bytes':value['bytes'],'sha256':value['sha256']})
        bypath={}
        for p in all_inputs:
            C.require(p['path'] not in bypath or bypath[p['path']]==p,'conflicting preserved pin');bypath[p['path']]=p
        self.inputs=list(bypath.values())
        self.record={'schema':'main-gap-sampling-worker-v1','complete':False,'block':c['block'],'commands':[],
            'statistics':[],'samples':[],'counts':{},'outputs':[],'combined_qualification_review':c['combined_qualification_review'],'completion_actual_review':c['completion_actual_review'],
            'accepted_oracle_inventory':c['semantic_oracle_inventory'],'admission':C.pin(path),
            'configuration':C.pin(C.PB/'BINDINGS.json'),'source_commit':c['source_commit'],
            'sampling_oracles_rebased':False,'native_execution':False,'stop_for_independent_review':True,
            'prechecks':{'full_sweeps':[],'light_check_count':0,'light_elapsed_ns':0,'new_archive_hash_checks':0}}
        C.require(type(deadline['start_ns']) is int and type(deadline['deadline_ns']) is int and
                  deadline['deadline_ns']==deadline['start_ns']+595*10**9,'whole-scope595 deadline')
    def recheck(self):
        start=time.monotonic_ns();C=self.C
        C.require(self.identity_snapshot is not None,'full entry SHA required')
        self.identity.check(self.identity_snapshot)
        C.verify_preserved_scope(self.c,self.accepted,hash_files=False)
        C.live_scope_structure(self.current_cell)
        for root,(pins,dirs) in self.archives.items():
            actual=[]
            for p in Path(root).rglob('*'):
                st=p.lstat();C.require(stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode),'new archive special type')
                if p.is_file():C.require(st.st_nlink==1,'new archive hardlink');actual.append(str(p))
            C.require(sorted(actual)==sorted(p['path'] for p in pins) and C.directory_paths(Path(root))==dirs,'completed sampling archive set')
        for role in ['python','shell','ghc','stats-emlf']:self.identity.runtime_check(self.accepted['worker']['runtime_after'][role])
        for p in [self.record['launch_binding'],self.record['admission'],self.record['configuration']]:C.verify_pin(p)
        C.verify_sampling_scope(self.a,self.c,self.guard,self.path,self.digest,self.record['launch_binding']['sha256'])
        end=time.monotonic_ns();self.record['prechecks']['light_check_count']+=1;self.record['prechecks']['light_elapsed_ns']+=end-start
        C.require(end<self.deadline['deadline_ns'],'sampling deadline including prechecks')
    def full_recheck(self,phase):
        start=time.monotonic_ns()
        if phase=='entry':
            self.C.require(self.identity_snapshot is None,'single entry');self.identity_snapshot=self.identity.capture(self.inputs)
        else:
            self.C.require(phase=='exit' and self.identity_snapshot is not None,'valid exit');self.identity.finish(self.identity_snapshot)
        end=time.monotonic_ns();self.record['prechecks']['full_sweeps'].append({'phase':phase,'start_ns':start,'end_ns':end,'elapsed_ns':end-start,
            'unique_files':len(self.identity_snapshot),'unique_bytes':sum(x['pin']['bytes'] for x in self.identity_snapshot.values())})
        self.recheck()
    def save(self):self.C.save(self.folder/'sampling-receipt.json',self.record)

    def remember_archive(self,root):
        pins=self.C.tree_pins(root);self.outputs.extend(pins);self.archives[str(root)]=(pins,self.C.directory_paths(root))
        self.identity.extend(self.identity_snapshot,pins);self.record['prechecks']['new_archive_hash_checks']+=1;return pins

    def command(self,label,argv,reports=()):
        C=self.C;row=self.rows[self.number]
        C.require(label==row['label'] and list(map(str,argv))==row['argv_template'],'exact32 frozen sampling command argv/order')
        expected_reports=() if 'report_sink' not in row else (row['report_sink'],)
        C.require(tuple(map(str,reports))==expected_reports,'exact mandatory report sink')
        self.recheck()
        seconds=min(row['maximum_seconds'],(self.deadline['deadline_ns']-time.monotonic_ns())//10**9)
        C.require(seconds>=1,'shared sampling absolute deadline exhausted')
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
            and value['cwd']==self.c['source'] and value['output']==str(output) and value['seconds']==seconds and value['limits']==self.guard.LIMITS,'bounded sampling child failed')
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
            self.record['statistics'].append({'command':label,'raw':item,'parsed':self.stats.parse_statistics(raw),'qualification_only':False,'sampling_leg':row.get('leg_id')})
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
        C.require(active_root.is_dir() and cells.is_dir() and {p.name for p in active_root.iterdir()}=={'cells'}
                  and not list(cells.iterdir()),'qualified original active paths must be present and empty')
        for name in ['commands','legs']:C.safe(self.folder/name).mkdir(mode=0o700,exist_ok=False)
        roles=['python','shell','ghc','stats-emlf']
        for role in roles:self.runtime(role,'before')
        measured=[r for r in self.rows if r['kind']=='measured_leg']
        for expected in measured:
            row=self.rows[self.number];C.require(row==expected,'fixed unchanged48-leg order')
            cell=row['cell'];lane=row['lane'];witness=self.accepted['cells'][cell]
            # This consumer verifies original proof, B/G raw inventory pins and
            # exact original active path. It cannot regenerate/rebase an oracle.
            C.verify_cell_oracle(witness,self.accepted)
            active=C.safe(cells/cell);C.require(not active.exists() and str(active)==witness['original_active_path'],'fresh identical active path')
            active.mkdir();self.current_cell=cell
            if lane=='M':
                C.safe(active/'queries').mkdir()
                spec=C.verify_pin(witness['spec']).read_bytes()
                with C.safe(active/'crate.spec').open('xb') as stream:stream.write(spec)
            else:
                C.require(lane=='G','fixed endpoint');C.safe(active/'objects').mkdir()
            before=len(self.record['statistics'])
            stdout,stderr,guard=self.command(row['label'],row['argv_template'],[Path(row['report_sink'])])
            C.require(len(self.record['statistics'])==before+1,'one genuine RTS per measured leg')
            if lane=='M':self.recheck_query_lock(active)
            raw=self.raw(active);frozen=C.raw_oracle(witness['stats'] if lane=='M' else witness['ghc'])
            C.require(raw==frozen,'same binary/tool full raw names and bytes, no exceptions')
            if lane=='M':
                query=self.parsers.fresh_queries(raw['unit.queries'],witness['crate'])
                C.require(query==witness['accepted_stats_query_report'],'actual frozen fresh ordered query report')
                cfg=list(witness['configuration_template']);cfg[1]=C.sha(C.verify_pin(self.accepted['stats_binary']))
                self.oracle.publication(raw,cfg[1],cfg,8)
                events=None
            else:
                query=None;events=self.parsers.ghc_compiling(stdout,stderr,witness['expected_home_modules'])
                C.require(set(raw)=={'objects/'+x for x in witness['expected_relative_interfaces']} and all(raw.values()),'only actual accepted typed interfaces')
            C.verify_cell_oracle(witness,self.accepted)
            destination,_,pins=self.archive(active,'legs',row['leg_id'])
            statistics=self.record['statistics'][-1]
            self.record['samples'].append({'leg_ordinal':row['leg_ordinal'],'leg_id':row['leg_id'],'cell':cell,'lane':lane,
                'actual_guard':C.pin(Path(guard['output'])/'guard.json'),'guard_elapsed_seconds':guard['elapsed_seconds'],
                'RTS':statistics,'raw_artifacts':pins,'accepted_oracle':witness['proof_pin'],
                'query':query,'ghc_compiling':events,'exact_process_wall_ns':None,'child_user_cpu':None,'child_system_cpu':None,
                'runtime_graph_visit_copy_constraint_counters':None,'stable_speedup_claimed':False})
            self.save()
        for role in roles:self.runtime(role,'after')
        C.require(self.number==32 and self.record['counts']=={'runtime':8,'measured_leg':24}
                  and len(self.record['samples'])==24 and len(self.record['statistics'])==24,'complete single sampling block')
        C.require([r['leg_ordinal'] for r in self.record['samples']]==list(range((self.c['block']-1)*24+1,self.c['block']*24+1)), 'fixed consecutive24 legs')
        self.full_recheck('exit');C.require(not list(cells.iterdir()) and not (active_root/'mlf.stats').exists(),'active paths and shared sink clean')
        self.record['outputs']=self.outputs;self.record['complete']=True;self.save()

