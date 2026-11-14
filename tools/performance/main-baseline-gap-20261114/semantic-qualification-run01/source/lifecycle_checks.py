"""Independent source-preparation checks: whitelisted read/hash functions only.
Never import the controller, run a worker/guard, inspect locks or invoke a loader.
Temporary directories below this package are only plain filesystem test data.
"""
from pathlib import Path
import ast,copy,hashlib,json,re,tempfile
D=Path(__file__).resolve().parent;R=D.parent
source=(D/'controller.py').read_text();tree=ast.parse(source)
names={'require','safe','sha','pin','verify_pin','load','inventory','row_sha',
       'completed_epoch_identity','accepted_setup','envelope_ns','entry_ns','deadline_fields'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
assert {n.name for n in nodes}==names
for n in ast.walk(ast.Module(body=nodes,type_ignores=[])):
    if isinstance(n,ast.Name):assert n.id not in {'subprocess','module','fcntl','time','os','sys','exec','eval','__import__'}
    if isinstance(n,ast.Attribute):assert n.attr not in {'write_text','write_bytes','mkdir','rename','unlink','open'} or n.attr=='open'
# sha's rb open is the sole file-open call; no writes in this extracted graph.
opens=[n for n in ast.walk(ast.Module(body=nodes,type_ignores=[])) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='open']
assert len(opens)==1 and ast.literal_eval(opens[0].args[0])=='rb'
ns={'Path':Path,'hashlib':hashlib,'json':json,'re':re,'R':R,'E':R/'main-gap-setup-run04',
    'WORK':R/'main-gap-setup-run04/semantic-qualification-01','MAX_NS':600*10**9,'POST_SETUP_MAX_NS':1800*10**9,'HEADROOM_NS':5*10**9}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<read-only-audited-definitions>','exec'),ns)
checks=[]
def yes(v):assert v
def case(name,fn):fn();checks.append({'name':name,'passed':True})
def bad(fn):
    try:fn()
    except (RuntimeError,KeyError,TypeError,ValueError,FileNotFoundError,FileExistsError):return
    raise AssertionError('negative accepted')
c=json.loads((D/'BINDINGS.json').read_bytes())
accepted=ns['accepted_setup'](c)
case('genuine actual SETUP serialized full chain and inventories',lambda:yes(len(accepted['immutable_inputs'])==6393 and len(accepted['immutable_outputs'])==365))
case('load accepts actual serialized path string',lambda:yes(ns['load'](c['setup_review']['path'])['actual_SETUP_passed'] is True))
case('load accepts identical Path',lambda:yes(ns['load'](Path(c['setup_review']['path']))==ns['load'](c['setup_review']['path'])))
x=copy.deepcopy(c);x['stats_binary']['sha256']='0'*64
case('reject config different actual stats binary',lambda:bad(lambda:ns['accepted_setup'](x)))
for key in ['setup_review','setup_configuration']:
    x=copy.deepcopy(c);x[key]['sha256']='0'*64
    case('reject wrong '+key+' pin',lambda x=x:bad(lambda:ns['accepted_setup'](x)))
e={'schema':'main-gap-semantic-guard-envelope-v1','clock':'monotonic_ns','guard_call_returned':True,'start_ns':9,'return_ns':20,'elapsed_ns':11}
case('exact integer returned duration',lambda:yes(ns['envelope_ns'](e)==11))
for key,value in [('start_ns',True),('return_ns',False),('elapsed_ns',11.0),('guard_call_returned',False),('return_ns',8),('elapsed_ns',12)]:
    x=dict(e);x[key]=value;case('bad envelope '+key+repr(value),lambda x=x:bad(lambda:ns['envelope_ns'](x)))
case('first600 cap fits explicit postsetup1800',lambda:yes(ns['entry_ns'](0,'SEMANTIC')==0))
for value in [True,-1,1,0.0]:case('reject wrong prior '+repr(value),lambda value=value:bad(lambda:ns['entry_ns'](value,'SEMANTIC')))
with tempfile.TemporaryDirectory(prefix='pure-lifecycle-',dir=D) as t:
    t=Path(t);ns['WORK']=t;ns['E']=t.parent;(t/'claims').mkdir()
    ap=t/'admission.json';ap.write_text('{"example":"plain test data"}\n');cp=t/'claims/SEMANTIC.json';cp.write_text('{}\n')
    a={'epoch':{'path':'/test/epoch','bytes':1,'sha256':'e'*64},'locks':[{'test':1},{'test':2}]};argv=['test-only-not-executed']
    d={'schema':'main-gap-semantic-launch-binding-v1','clock':'monotonic_ns','start_ns':100,'deadline_ns':595000000100,
       'admission':ns['pin'](ap),'epoch':a['epoch'],'locks':a['locks'],'command_without_binding':argv,'claim':ns['pin'](cp),'scope':str(t),'bounded_root':str(t.parent)}
    case('plain data immutable deadline linkage',lambda:yes(ns['deadline_fields'](d,a,ap,argv,101)==d))
    for key,value in [('start_ns',True),('deadline_ns',False),('deadline_ns',100),('deadline_ns',596000000100),('scope',str(t.parent)),('epoch',{'wrong':1}),('command_without_binding',['wrong']),('claim',{'wrong':1})]:
        x=copy.deepcopy(d);x[key]=value;case('deadline reject '+key+repr(value),lambda x=x:bad(lambda:ns['deadline_fields'](x,a,ap,argv,101)))
    case('deadline future start rejected',lambda:bad(lambda:ns['deadline_fields'](d,a,ap,argv,99)))
    case('deadline exhausted rejected',lambda:bad(lambda:ns['deadline_fields'](d,a,ap,argv,d['deadline_ns'])))
    case('missing launch field rejected',lambda:bad(lambda:ns['deadline_fields']({},a,ap,argv,101)))
    # Same exclusive create semantics, without a guard, epoch or lock.
    binding=t/'plain-binding.json'
    with binding.open('x') as stream:json.dump(d,stream)
    bp=ns['pin'](binding)
    case('exclusive repeat binding rejected',lambda:bad(lambda:binding.open('x')))
    binding.write_text('{}')
    case('changed immutable binding rejected',lambda:bad(lambda:ns['verify_pin'](bp)))
    commands=t/'commands';commands.mkdir();child=commands/'001-example'
    case('real temporary parent exists and child absent',lambda:yes(commands.is_dir() and not child.exists()))
# Structural, not execution proof: actual lock and guard behavior require admission.
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
launch=ast.get_source_segment(source,functions['launch']);binding=ast.get_source_segment(source,functions['launch_binding'])
case('guard remains600 bounded at accepted SETUP root',lambda:yes('seconds=600,bounded_root=E' in launch))
case('binding same original locks and exclusive files',lambda:yes("for item in a['locks']" in binding and 'fcntl.LOCK_EX|fcntl.LOCK_NB' in binding and "(WORK/'launch-binding.json').open('x')" in binding))
case('returned ns saved before outer acceptance',lambda:yes(launch.index('guard_return_ns=time.monotonic_ns()')<launch.index('save(output,record)',launch.index('guard_return_ns'))<launch.index('check_outer(')))
case('entry call is final AST node only',lambda:yes(isinstance(tree.body[-1],ast.If) and sum(isinstance(n,ast.If) for n in tree.body)==1))
result={'schema':'main-gap-semantic-lifecycle-pure-checks-v1','complete':True,'count':len(checks),'checks':checks,
        'scope':'Own read-only AST whitelist over genuine SETUP JSON; ordinary temporary-directory data; no controller top level, runtime, guard, lock or payload executed.',
        'actual_semantic_run':False,'source_gate_passed':None}
(D/'lifecycle-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print('lifecycle pure checks',len(checks))
