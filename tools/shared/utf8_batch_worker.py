"""UTF8 controls with explicit actual-capture batch vector projections.
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
import utf8_batch_contract as contract
import test_utf8_length as suite

HERE = Path(__file__).resolve().parent
INPUTS = ('test_direct.py', 'test_utf8_length.py', 'crc_process_supervisor.py', 'default_stdlib.py', 'direct_managed.py', 'utf8_batch_worker.py', 'utf8_batch_contract.py', 'fixtures/utf8-length/Length.hs', 'fixtures/utf8-length/Main.hs')
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
        require(len(projections)==4 and stderr==b'' and
                len({r['physical_command_id'] for r in projections})==4 and
                len({r['index'] for r in projections})==1 and
                all(r['kind']=='verified-batch-projection' and r['fresh_process'] is False for r in projections),
                'four clean actual projections required')
        self.projections=projections
        self.stderr=stderr

def execution_policy(worker_receipt):
    """Declared execution modes, never a claim that a run already completed."""
    return {
        'vector_execution_modes': {
            'host': {'mode':'original fresh process per vector','required_vectors':29},
            'native-O0': {'mode':'original fresh process per vector','required_vectors':29},
            'native-O2': {'mode':'original fresh process per vector','required_vectors':29},
            'interpreter': {'mode':'logical projections of actual batch captures','required_vectors':25,
                            'required_batch_executions':{'interpreter':2,'host':2}}},
        'interpreter_demand_execution_mode': 'three original demand cases, each in its own fresh interpreter process',
        'commands_semantics': 'physical execution ledger only; excludes 25 logical interpreter vectors; no virtual process records',
        'batch_worker_receipt':str(worker_receipt),
        'fresh_process_equivalence_claimed':False,
        'execution_policy_is_not_completion_evidence':True,
    }


def expected_original_names():
    names=['compile-host','compile-supervisor','compile-oracle','link-oracle','compile-host','link-host','host-oracle','emit-native']
    for opt in ('0','2'):
        names += ['compile-runtime-O'+opt,'link-native-O'+opt,'link-probe-O'+opt]
        names += ['runtime-'+mode+'-O'+opt for mode in ('success','no-interior','bottom','wrong-type','invalid-utf8','overflow')]
    for lane in ('host','interpreter','native-O0','native-O2'):
        if lane!='interpreter': names += [lane+'-vector-'+str(i) for i in range(29)]
        names += [lane+'-'+mode for mode in ('unused','argument','invalid')]
    return collections.Counter(names)

def validate_inventory(record, physical, logical_indices, batches):
    require(record.get('complete') is True, 'original full controls incomplete')
    require(record.get('vector_counts')=={'host':29,'interpreter':25,'native-O0':29,'native-O2':29}, '112 original vectors required')
    require(record.get('demand_counts')==dict.fromkeys(('host','interpreter','native-O0','native-O2'),3),'12 original demands required')
    runtime={(o,c) for o in ('0','2') for c in ('success','no-interior','bottom','wrong-type','invalid-utf8','overflow')}
    rows=record.get('direct_runtime_cases',[])
    require(len(rows)==12 and {(x['optimization'],x['case']) for x in rows}==runtime,'12 runtime cases required')
    require(logical_indices==list(range(6))+list(range(10,29)), '25 original interpreter indices once in order')
    require(collections.Counter(x['original_name'] for x in physical if x['kind']=='original')==expected_original_names(), 'complete original physical inventory')
    extra=collections.Counter(x['original_name'] for x in physical if x['kind']=='batch')
    require(extra==collections.Counter('batch-'+step+'-'+direction for direction in ('forward','reverse') for step in ('compile','link','host','interpreter')), 'eight batch physical commands required')
    require(len(physical)==133 and len({x['id'] for x in physical})==133, 'unique full physical inventory')
    require(all(x.get('state')=='passed' for x in physical), 'failed physical command')
    require(len(batches)==4 and len({x['id'] for x in batches})==4,'four distinct batch captures')
    require({x['id'] for x in batches}=={x['id'] for x in physical if x['original_name'] in ('batch-host-forward','batch-host-reverse','batch-interpreter-forward','batch-interpreter-reverse')},'batch subset is not full physical inventory')


def execute():
    global _receipt_created
    # This worker's only CLI is the original three option/value pairs.
    require(len(sys.argv)==7 and sys.argv[1]=='--build-receipt' and sys.argv[3]=='--clang' and sys.argv[5]=='--output','exact worker argv')
    receipt=Path(sys.argv[2]).resolve(strict=True); output=Path(sys.argv[6]).resolve()
    state_path=output.parent/(output.name+'-batch-worker.json')
    state={'complete':False,'physical_commands':[],'logical_vectors':[], 'logical_indices':[], 'batch_commands':[],
           'scope':'current UTF8 controls; 25 interpreter vectors observed through four actual batches; not fresh-process equivalence'}
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
    host_outputs={}; templates={}; generated={}; batch_results={}; original_record=None
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
            require(producer is not None and set(host_outputs)==set(contract.FORWARD),'authenticated producer and complete original host observations required')
            source=HERE/'fixtures/utf8-length/Length.hs'; build=receipt.parent
            generated[str(source)]=digest(source.read_bytes())
            for direction in ('forward','reverse'):
                obj=self.output/('batch-'+direction+'.o'); hi=self.output/('batch-'+direction+'.hi'); binary=self.output/('batch-'+direction)
                compile_argv=list(templates['compile']); link_argv=list(templates['link'])
                def replace_once(argv,old,new):
                    require(argv.count(str(old))==1,'unique host template operand')
                    argv[argv.index(str(old))]=str(new)
                replace_once(compile_argv,self.output/'host-Main.o',obj); replace_once(compile_argv,self.output/'host-Main.hi',hi)
                replace_once(link_argv,self.output/'host-Main.o',obj); replace_once(link_argv,self.output/'host',binary)
                self.physical('batch-compile-'+direction,compile_argv,kind='batch')
                self.physical('batch-link-'+direction,link_argv,kind='batch')
                for artifact in (obj,hi,binary): generated[str(artifact)]=digest(artifact.read_bytes())
                for lane,argv in [('host',[binary,'batch-'+direction]),('interpreter',[build/'bin/emlf','-i',self.root/'libraries/mlf-foundation','--run',source,'--','batch-'+direction])]:
                    result,row=self.physical('batch-'+lane+'-'+direction,argv,timeout=120,kind='batch')
                    stdout=Path(row['stdout_path']).read_bytes(); stderr=Path(row['stderr_path']).read_bytes()
                    require(stdout==result.stdout and direct.command_diagnostics(row['argv'],stderr)[1]==result.stderr,'captured execution bytes changed')
                    physical=contract.physical_record(row['id'],lane,direction,row['argv'],stdout,stderr,result.returncode)
                    state['batch_commands'].append(physical); batch_results[physical['id']]=(physical,stdout,result.stderr)
                    for index in contract.FORWARD:
                        original_argv=[str(build/'bin/emlf'),'-i',str(self.root/'libraries/mlf-foundation'),'--run',str(HERE/'fixtures/utf8-length/Length.hs'),'--',*contract.vectors()[index]['arguments']]
                        state['logical_vectors'].append(contract.project(physical,stdout,index,original_argv,host_outputs[index]))
            state['batch_aggregate']=contract.aggregate(state['batch_commands'],state['logical_vectors'],host_outputs); persist()
        def run(self,name,command,*,overrides=None,status=0,expected=None,timeout=180):
            require(not overrides,'unexpected environment override')
            argv=list(map(str,command))
            if name.startswith('interpreter-vector-'):
                index=int(name[len('interpreter-vector-'):]); cases=contract.vectors()
                require(index in cases and name=='interpreter-vector-'+str(index),'exact interpreter index')
                prefix=[str(receipt.parent/'bin/emlf'),'-i',str(self.root/'libraries/mlf-foundation'),'--run',str(HERE/'fixtures/utf8-length/Length.hs'),'--']
                require(argv==prefix+list(cases[index]['arguments']) and timeout==120 and type(status)is int and status==0 and expected==host_outputs[index],'exact original interpreter vector contract')
                require(index not in state['logical_indices'],'duplicate interpreter vector')
                if not batch_results: self.batches()
                rows=[r for r in state['logical_vectors'] if r['index']==index]
                for physical,raw,err in batch_results.values():
                    contract.project(physical,raw,index,argv,expected)
                    require(err==b'','actual batch diagnostic')
                state['logical_indices'].append(index); persist()
                return BatchVectorResult(rows,b''.join(x[2] for x in batch_results.values()))
            if name=='compile-host' and str(HERE/'fixtures/utf8-length/Length.hs') in argv: templates['compile']=argv
            if name=='link-host': templates['link']=argv
            result,row=self.physical(name,argv,expected=expected,status=status,timeout=timeout)
            if name.startswith('host-vector-'):
                index=int(name[len('host-vector-'):])
                if index in contract.FORWARD: host_outputs[index]=result.stdout
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
        contract.aggregate(state['batch_commands'],state['logical_vectors'],host_outputs)
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
