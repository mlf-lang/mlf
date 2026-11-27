"""Candidate-selection controls with explicit actual-capture batch vector projections.
No fresh-process equivalence claim. Must run inside the owned-tree supervisor.
"""
import collections
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import test_direct as direct
import candidate_batch_contract as contract
import test_candidate_selection as suite

HERE = Path(__file__).resolve().parent
INPUTS = ('test_direct.py', 'test_candidate_selection.py', 'crc_process_supervisor.py', 'default_stdlib.py', 'direct_managed.py', 'candidate_batch_worker.py', 'candidate_batch_contract.py', 'fixtures/CandidateSelection.hs', 'fixtures/CandidateSelectionControls.hs')
_receipt_created=False
def require(ok, message):
    if not ok: raise ValueError(message)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def snapshot(here=HERE):
    """Record this invocation's source bytes; edits between runs are supported."""
    raws = {name: (here/name).read_bytes() for name in INPUTS}
    return raws, {name:digest(raw) for name,raw in raws.items()}
def save(path, value):
    temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(value,indent=2)+'\n'); temp.replace(path)

class BatchVectorResult:
    """Logical observation, deliberately not a subprocess.CompletedProcess."""
    def __init__(self, projections, stderr):
        require(type(projections)is list and len(projections)==4 and stderr==b'' and
                all(type(r)is dict and type(r.get('index'))is int and 0<=r['index']<24 and
                    type(r.get('physical_command_id'))is str and bool(r['physical_command_id']) and
                    r.get('kind')=='verified-batch-projection' and r.get('fresh_process')is False
                    for r in projections) and
                len({r['physical_command_id'] for r in projections})==4 and
                len({r['index'] for r in projections})==1,
                'four clean actual projections with one strict 0..23 index required')
        self.projections=projections
        self.stderr=stderr

def execution_policy(worker_receipt):
    return dict(vector_execution_modes={
        'interpreter':{'mode':'24 logical projections from four real host/interpreter batches',
                       'required_vectors':24,'required_batch_executions':{'host':2,'interpreter':2}},
        'native-O0':{'mode':'original fresh process per vector','required_vectors':124},
        'native-O2':{'mode':'original fresh process per vector','required_vectors':124}},
        host_gate='current Classes host gate: 8254 + 12369 cases and 2 + 5 demand checks',
        commands_semantics='physical commands only; 24 logical interpreter vectors have no invented subprocess timing or exit status',
        batch_worker_receipt=str(worker_receipt),fresh_process_equivalence_claimed=False,
        execution_policy_is_not_completion_evidence=True)

def expected_original_names():
    names=['host-compile','host-link','host-controls','emit-native','runtime','native-link-O0','native-link-O2']
    names += [lane+'-'+selector+'-'+str(i) for lane in ('native-O0','native-O2')
              for selector in ('named','ids') for i in range(62)]
    return collections.Counter(names)

def validate_inventory(record,physical,logical_indices,batches):
    require(record.get('complete')is True,'original complete gate')
    require(record.get('vector_counts')=={'interpreter':24,'native-O0':124,'native-O2':124},
            '272 original logical vectors')
    require(type(logical_indices)is list and all(type(i)is int for i in logical_indices) and
            logical_indices==list(range(24)),'24 strict integer ordered interpreter observations')
    # Validate both ledgers independently: Python equality alone accepts False
    # for zero, including in a separately tampered original command receipt.
    for ledger in (physical,record.get('commands')):
        require(type(ledger)is list and len(ledger)==263,'263 actual physical rows in each ledger')
        require(all(type(r)is dict and type(r.get('id'))is str and bool(r['id']) and
                    type(r.get('kind'))is str and r['kind'] in ('original','batch') and
                    r.get('state')=='passed' and
                    type(r.get('exit_code'))is int and r['exit_code']==0 and
                    type(r.get('expected_status'))is int and r['expected_status']==0
                    for r in ledger),'strict passed zero-exit physical rows')
        require(len({r['id'] for r in ledger})==263,'unique nonempty physical identities')
    require(record['commands']==physical,'original command receipt must equal full physical ledger')
    require(collections.Counter(r['original_name'] for r in physical if r['kind']=='original')==
            expected_original_names(),'complete unchanged host/native physical inventory')
    require(collections.Counter(r['original_name'] for r in physical if r['kind']=='batch')==
            collections.Counter('batch-'+step+'-'+direction
                for direction in ('forward','reverse') for step in ('compile','link','host','interpreter')),
            'eight additional batch physical commands')
    require(len(physical)==263 and len({r['id'] for r in physical})==263 and
            all(r.get('state')=='passed' for r in physical),'263 unique passed physical commands')
    require(len(batches)==4 and {r['id'] for r in batches}==
            {r['id'] for r in physical if r['original_name'] in
                ('batch-host-forward','batch-host-reverse','batch-interpreter-forward','batch-interpreter-reverse')},
            'four actual batch subset identities')

def execute():
    global _receipt_created
    # This worker's only CLI is the original three option/value pairs.
    require(len(sys.argv)==7 and sys.argv[1]=='--build-receipt' and sys.argv[3]=='--clang' and sys.argv[5]=='--output','exact worker argv')
    receipt=Path(sys.argv[2]).resolve(strict=True); output=Path(sys.argv[6]).resolve()
    state_path=output.parent/(output.name+'-batch-worker.json')
    state={'complete':False,'physical_commands':[],'logical_vectors':[], 'logical_indices':[], 'batch_commands':[],
           'scope':'current Classes host gate and portable selector reference; 24 interpreter vectors observed through four actual batches; not fresh-process equivalence'}
    state['fixture_mode']='ordinary-shared-case-and-batch-entry'
    require(not state_path.exists(),'fresh worker receipt required')
    save(state_path,state)
    _receipt_created=True
    raws,pins=snapshot(); state['input_pins']=pins
    producer=None; initial_receipt=digest(receipt.read_bytes()); captured=[]
    original_auth=direct.authenticate_build
    def auth(*args,**kwargs):
        nonlocal producer
        value=original_auth(*args,**kwargs)
        require(Path(args[0]).resolve()==receipt and digest(receipt.read_bytes())==initial_receipt,'producer identity changed')
        if producer is None: producer=value
        captured.append(value)
        return value
    templates={}; generated={}; batch_results={}; original_record=None
    state['generated_artifacts']=generated
    def persist(): save(state_path,state)
    class Runner:
        def __init__(self,root,out,record,original_save):
            nonlocal original_record
            self.root,self.output,self.receipt,self.original_save=root,out,record,original_save
            original_record=record
            # State explicitly which observations came from physical batches.
            record.update(execution_policy(state_path))
        def physical(self,name,argv,*,expected=None,status=0,timeout=180,kind='original'):
            argv=list(map(str,argv)); identity='%04d-%s'%(len(state['physical_commands'])+1,name)
            row=dict(id=identity,original_name=name,kind=kind,argv=argv,timeout_seconds=timeout,expected_status=status,state='running')
            state['physical_commands'].append(row); self.receipt['commands'].append(row); persist(); self.original_save()
            start=time.monotonic(); stdout=stderr=b''; process=None
            try:
                # No setsid. Timeout aborts worker; outer subreaper owns cleanup.
                process=subprocess.Popen(argv,cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                row['pid']=process.pid
                try: stdout,stderr=process.communicate(timeout=timeout)
                except subprocess.TimeoutExpired as error:
                    stdout,stderr=error.stdout or b'',error.stderr or b''
                    row['cleanup_delegated_to_supervisor']=True
                    raise
                row['exit_code']=process.returncode
                modes, diagnostics = direct.command_diagnostics(argv, stderr)
                if modes:
                    row['dependency_modes'] = modes
                require(process.returncode==status and (expected is None or stdout==expected) and (status!=0 or not diagnostics),'physical command failed: '+name)
                row['state']='passed'
                return subprocess.CompletedProcess(argv,process.returncode,stdout,diagnostics),row
            except BaseException as error:
                row.update(state='failed',error=repr(error)); raise
            finally:
                for label,data in (('stdout',stdout),('stderr',stderr)):
                    path=self.output/(identity+'.'+label); path.write_bytes(data)
                    row[label+'_path']=str(path); row[label+'_sha256']=digest(data)
                row['seconds']=time.monotonic()-start; self.original_save(); persist()
        def batches(self):
            require(producer is not None and set(templates)=={'compile','link'},'authenticated actual host build templates')
            source=HERE/'fixtures/CandidateSelection.hs'
            generated[str(source)]=digest(source.read_bytes())
            build=receipt.parent
            for direction in ('forward','reverse'):
                obj=self.output/('batch-'+direction+'.o');hi=self.output/('batch-'+direction+'.hi')
                binary=self.output/('batch-'+direction)
                compile_argv=list(templates['compile']);link_argv=list(templates['link'])
                def replace_once(argv,old,new):
                    require(argv.count(str(old))==1,'unique actual host operand')
                    argv[argv.index(str(old))]=str(new)
                replace_once(compile_argv,HERE/'fixtures/CandidateSelectionControls.hs',source)
                replace_once(compile_argv,self.output/'Main.o',obj)
                replace_once(compile_argv,self.output/'Main.hi',hi)
                replace_once(link_argv,self.output/'Main.o',obj)
                replace_once(link_argv,self.output/'host-controls',binary)
                self.physical('batch-compile-'+direction,compile_argv,kind='batch')
                self.physical('batch-link-'+direction,link_argv,kind='batch')
                for artifact in (obj,hi,binary):generated[str(artifact)]=digest(artifact.read_bytes())
                for lane,argv in [('host',[binary,'batch-'+direction]),
                    ('interpreter',[build/'bin/emlf','-i',self.root/'libraries/mlf-foundation','--run',source,'--','batch-'+direction])]:
                    for artifact in (source,obj,hi,binary):
                        require(digest(artifact.read_bytes())==generated[str(artifact)],'batch artifact drift before target')
                    result,row=self.physical('batch-'+lane+'-'+direction,argv,timeout=120,kind='batch')
                    for artifact in (source,obj,hi,binary):
                        require(digest(artifact.read_bytes())==generated[str(artifact)],'batch artifact drift after target')
                    stdout=Path(row['stdout_path']).read_bytes();stderr=Path(row['stderr_path']).read_bytes()
                    require(stdout==result.stdout and direct.command_diagnostics(row['argv'],stderr)[1]==result.stderr,'actual capture identity')
                    physical=contract.physical_record(row['id'],lane,direction,row['argv'],stdout,stderr,result.returncode)
                    state['batch_commands'].append(physical);batch_results[physical['id']]=(physical,stdout,result.stderr)
                    for index in contract.FORWARD:
                        original_argv=[str(build/'bin/emlf'),'-i',str(self.root/'libraries/mlf-foundation'),
                            '--run',str(HERE/'fixtures/CandidateSelection.hs'),'--',*contract.cases()[index]['arguments']]
                        state['logical_vectors'].append(contract.project(physical,stdout,index,
                            original_argv,contract.cases()[index]['expected']))
            state['batch_aggregate']=contract.aggregate(state['batch_commands'],state['logical_vectors']);persist()
        def run(self,name,command,*,overrides=None,status=0,expected=None,timeout=180):
            require(not overrides,'unexpected environment override')
            argv=list(map(str,command))
            if name.startswith('interpreter-'):
                names={'interpreter-'+row['selector']+'-'+str(row['index']):i
                       for i,row in contract.cases().items()}
                require(name in names,'exact interpreter selector/index')
                index=names[name];case=contract.cases()[index]
                prefix=[str(receipt.parent/'bin/emlf'),'-i',str(self.root/'libraries/mlf-foundation'),
                        '--run',str(HERE/'fixtures/CandidateSelection.hs'),'--']
                require(argv==prefix+case['arguments'] and type(timeout)is int and timeout==120 and
                        type(status)is int and status==0 and expected==case['expected'],
                        'exact original interpreter contract')
                require(index==len(state['logical_indices']),'ordered interpreter index once')
                if not batch_results:self.batches()
                rows=[r for r in state['logical_vectors'] if r['index']==index]
                for physical,raw,err in batch_results.values():
                    contract.project(physical,raw,index,argv,expected)
                    require(err==b'','actual batch diagnostic')
                state['logical_indices'].append(index);persist()
                return BatchVectorResult(rows,b''.join(v[2] for v in batch_results.values()))
            if name=='host-compile':
                require(str(HERE/'fixtures/CandidateSelectionControls.hs') in argv,'original host fixture')
                require('compile' not in templates,'unique host compile')
                templates['compile']=argv
            if name=='host-link':
                require('link' not in templates,'unique host link');templates['link']=argv
            result,row=self.physical(name,argv,expected=expected,status=status,timeout=timeout)
            return result
    try:
        persist()
        suite.main(runner_factory=Runner, authenticate=auth)
        validate_inventory(original_record,state['physical_commands'],state['logical_indices'],state['batch_commands'])
        require(len(captured)==2,'original two actual authentications required')
        require(snapshot()[1]==pins and digest(receipt.read_bytes())==initial_receipt,'source/helper/producer drift')
        for path,pin in generated.items(): require(digest(Path(path).read_bytes())==pin,'generated source/artifact drift')
        for row in state['physical_commands']:
            for label in ('stdout','stderr'): require(digest(Path(row[label+'_path']).read_bytes())==row[label+'_sha256'],'physical capture drift')
        for physical,raw,err in batch_results.values():
            row=next(x for x in state['physical_commands'] if x['id']==physical['id'])
            reconstructed=contract.physical_record(row['id'],physical['lane'],physical['direction'],row['argv'],
                Path(row['stdout_path']).read_bytes(),Path(row['stderr_path']).read_bytes(),row['exit_code'])
            require(reconstructed==physical,'batch physical evidence changed')
        contract.aggregate(state['batch_commands'],state['logical_vectors'])
        state.update(complete=True,generated_artifacts=generated,original_receipt=original_record,
                     producer_receipt_path=str(receipt),producer_receipt_sha256=initial_receipt)
    except BaseException as error:
        state.update(complete=False,error=repr(error),traceback=traceback.format_exc()); raise
    finally:
        persist()
def main():
    try: execute()
    except BaseException as error:
        # Preserve the original failure and partial evidence on preflight errors
        # before the execution-level try/finally was installed.
        if _receipt_created and len(sys.argv)==7 and sys.argv[5]=='--output':
            out=Path(sys.argv[6]).resolve(); path=out.parent/(out.name+'-batch-worker.json')
            if path.is_file():
                value=json.loads(path.read_text())
                if not value.get('complete') and 'error' not in value:
                    value.update(complete=False,error=repr(error),traceback=traceback.format_exc())
                    save(path,value)
        raise
if __name__=='__main__': main()
