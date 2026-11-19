"""Frozen candidate-selection controls with explicit actual-capture batch vector projections.
No fresh-process equivalence claim. Must run inside the pinned owned-tree guard.
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
import types

HERE = Path(__file__).resolve().parent
CLASSES_PATH = '../../libraries/mlf-inference/Bootstrap/Classes.hs'
CLASSES_SUCCESSORS = (
    'b4a2ce4772e168f2013a77d0113298103557d955',
    '9f3597afc8b5415339f05291b4ce6342ea057d21',
    '54dd1eedb8736aa9cea55d40c4de979e08e2df17',
    '3ff1b6a5668928661b112f6ab4225880f3408a1a',
    '6f1bc8e923c6333d20f38b421ae43672fa0721c3',
    'b7caa275f2b1b90718e5da59152c8ccf9b96d538',
)
PINS = {
 'test_direct.py':'a46bd66949e81c5761dff3446201640837ec8f68',
 'test_candidate_selection.py':'c2a16944fe4e19c1f8de0ac24ff06d95d94c031c',
 'fixtures/CandidateSelectionControls.hs':'928d4511289a780af1685dcc4ea28d0ae0c404d2',
 CLASSES_PATH:'bbcc794dc1ce447ccfc1450378e951df1b427819',
 'default_stdlib.py':'33f84ec682f78c064322de8e9d303b76b6040871',
 'crc_process_supervisor.py':'620e88b557139a6b19ca63097decaa9148bdd819',
 'test_direct_crc_successor.py':'789dc7e641fdbd8aace2f9395914d786c18eadb1',
 'test_direct_bounded.py':'40c07dbea8b42da414997270ede4c49ef9b564ac',
 'utf8_batch_worker.py':'3bb35f2e81ab8dbb51c27d3097934c9b35a36083',
 'utf8_batch_contract.py':'51942bc8df2c8cd779fe50abb7eca92734530933',
 'test_utf8_length.py':'73fe9e2c4dc4201a03d342ad146b7227a9b57330',
 'test_crc32.py':'f906dde582c2aef13d56ec608accedec7f746dae',
 'fixtures/utf8-length/Main.hs':'5dc5eddae94e609328404febc90db226a82167cd',
 'fixtures/utf8-length/Length.hs':'dcef64296a26296b720d0ffa00016d808f7cee1e',
}
HELPERS = ('candidate_batch_worker.py','candidate_batch_contract.py','test_direct_candidate_successor.py')
_receipt_created=False
def require(ok, message):
    if not ok: raise ValueError(message)
def digest(raw): return hashlib.sha256(raw).hexdigest()
def blob(raw): return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
def snapshot(here=HERE):
    raws = {name: (here/name).read_bytes() for name in (*PINS, *HELPERS)}
    for name, pin in PINS.items():
        actual = blob(raws[name])
        require(actual == pin or (name == CLASSES_PATH and actual in CLASSES_SUCCESSORS),
                'frozen input changed: '+name)
    return raws, {name:digest(raw) for name,raw in raws.items()}
def load(raw, name, path):
    module=types.ModuleType(name); module.__file__=str(path)
    exec(compile(raw,str(path),'exec'),module.__dict__)
    return module
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
        host_gate='unchanged actual Classes host gate: 8254 + 12369 cases and 2 + 5 demand checks',
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
           'scope':'original controls unchanged; 24 interpreter vector startups replaced by four-lane actual batch projections; not fresh-process equivalence'}
    state['fixture_generation']='candidate-monomorphic-runtime-loop-v1'
    state['source_basis']='8d80e0fb1dbf4e6d40c53de35b727674b5c74817'
    require(not state_path.exists(),'fresh worker receipt required')
    save(state_path,state)
    _receipt_created=True
    raws,pins=snapshot(); state['input_pins']=pins
    direct=load(raws['test_direct.py'],'candidate_direct_frozen',HERE/'test_direct.py')
    contract=load(raws['candidate_batch_contract.py'],'candidate_contract_bound',HERE/'candidate_batch_contract.py')
    old_modules={n:sys.modules.get(n) for n in ('test_direct','default_stdlib')}
    producer=None; initial_receipt=digest(receipt.read_bytes()); captured=[]
    original_auth=direct.authenticate_build
    def auth(*args,**kwargs):
        nonlocal producer
        value=original_auth(*args,**kwargs)
        require(Path(args[0]).resolve()==receipt and digest(receipt.read_bytes())==initial_receipt,'producer identity changed')
        if producer is None: producer=value
        captured.append(value)
        return value
    direct.authenticate_build=auth
    templates={}; generated={}; batch_results={}; original_record=None
    state['generated_artifacts']=generated
    def persist(): save(state_path,state)
    class Runner:
        def __init__(self,root,out,record,original_save):
            nonlocal original_record
            self.root,self.output,self.receipt,self.original_save=root,out,record,original_save
            original_record=record
            # Keep the frozen script's original scope and counters intact, but
            # make a standalone reading of its receipt unambiguous.
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
                require(process.returncode==status and (expected is None or stdout==expected) and (status!=0 or not stderr),'physical command failed: '+name)
                row['state']='passed'
                return subprocess.CompletedProcess(argv,process.returncode,stdout,stderr),row
            except BaseException as error:
                row.update(state='failed',error=repr(error)); raise
            finally:
                for label,data in (('stdout',stdout),('stderr',stderr)):
                    path=self.output/(identity+'.'+label); path.write_bytes(data)
                    row[label+'_path']=str(path); row[label+'_sha256']=digest(data)
                row['seconds']=time.monotonic()-start; self.original_save(); persist()
        def batches(self):
            require(producer is not None and set(templates)=={'compile','link'},'authenticated actual host build templates')
            script=raws['test_candidate_selection.py']
            classes=raws['../../libraries/mlf-inference/Bootstrap/Classes.hs']
            original=contract.original_fixture(script,classes)
            fixture=self.output/'CandidateSelection.hs'
            require(fixture.read_bytes()==original,'whole original fixture identity')
            generated[str(fixture)]=digest(original)
            build=receipt.parent
            for direction in ('forward','reverse'):
                raw=contract.generate(original,direction,script,classes)
                require(contract.restore(raw,direction,script,classes)==original,'full generated inverse')
                source=self.output/('batch-'+direction+'.hs');source.write_bytes(raw)
                generated[str(source)]=digest(raw)
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
                for lane,argv in [('host',[binary]),
                    ('interpreter',[build/'bin/emlf','-i',self.root/'libraries/mlf-foundation','--run',source,'--'])]:
                    for artifact in (source,obj,hi,binary):
                        require(digest(artifact.read_bytes())==generated[str(artifact)],'batch artifact drift before target')
                    result,row=self.physical('batch-'+lane+'-'+direction,argv,timeout=120,kind='batch')
                    for artifact in (source,obj,hi,binary):
                        require(digest(artifact.read_bytes())==generated[str(artifact)],'batch artifact drift after target')
                    stdout=Path(row['stdout_path']).read_bytes();stderr=Path(row['stderr_path']).read_bytes()
                    require(stdout==result.stdout and stderr==result.stderr,'actual capture identity')
                    physical=contract.physical_record(row['id'],lane,direction,row['argv'],stdout,stderr,result.returncode)
                    state['batch_commands'].append(physical);batch_results[physical['id']]=(physical,stdout,stderr)
                    for index in contract.FORWARD:
                        original_argv=[str(build/'bin/emlf'),'-i',str(self.root/'libraries/mlf-foundation'),
                            '--run',str(fixture),'--',*contract.cases()[index]['arguments']]
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
                        '--run',str(self.output/'CandidateSelection.hs'),'--']
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
            if name=='emit-native':
                require((self.output/'CandidateSelection.hs').read_bytes()==contract.original_fixture(
                    raws['test_candidate_selection.py'],raws['../../libraries/mlf-inference/Bootstrap/Classes.hs']),
                    'native fixture exact original body')
            result,row=self.physical(name,argv,expected=expected,status=status,timeout=timeout)
            return result
    try:
        persist()
        sys.modules['test_direct']=direct
        sys.modules['default_stdlib']=load(raws['default_stdlib.py'],'default_stdlib',HERE/'default_stdlib.py')
        original=load(raws['test_candidate_selection.py'],'candidate_original_frozen',HERE/'test_candidate_selection.py')
        original.CommandRunner=Runner
        original.main()
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
        try: persist()
        finally:
            for name,value in old_modules.items():
                if value is None: sys.modules.pop(name,None)
                else: sys.modules[name]=value
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
