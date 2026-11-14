"""Read-only verification of final reduction; no target or original helper calls."""
import ast
import hashlib
import json
from pathlib import Path
R=Path('<EXPERIMENT_ROOT>')
D=Path(__file__).parent

def pin(p):
    b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def load(p):return json.loads(Path(p).read_bytes())
def checked(p):assert pin(Path(p['path']))==p;return load(p['path'])

result=load(D/'results.json');spec=load(D/'actual-input.json')
combined=load(R/'main-gap-sampling-02-actual-review/combined-final.json')
checks=[]
def ok(name,value):
    assert value,name;checks.append(name)
ok('two actual review and combined identities',spec['blocks'][0]['actual_review']['sha256']=='9d0f20dd831a4943bb3672b1889bb1772397c5c9014f8939754adaba1b5cc924' and spec['blocks'][1]['actual_review']['sha256']=='cf5bf9fe5364b6cdaa850629238aaa36517ace48c93d33ecd92f895e56de591f' and pin(R/'main-gap-sampling-02-actual-review/combined-final.json')['sha256']=='33829f5e71c9a1ed5cc530566450ef06d473dba8de4b5abbc6c554657983c408')
for p in load(D/'verified-input-pins.json'):assert pin(Path(p['path']))==p
ok('all source and both actual review manifest members unchanged',True)
for p in spec['blocks']:
    report=checked(p['actual_review']);worker=checked(p['worker'])
    ok('block '+str(p['block'])+' exact actual worker binding',report['actual_pins']['worker']==p['worker'] and worker['complete'] is True)
ok('actual combined complete and no raw exceptions',combined['complete'] is True and combined['combined_48leg_sampling_passed'] is True and combined['blockers']==[] and combined['exceptions']==[] and combined['all_same_binary_raw_exact'] is True)
ok('48 complete and independently reviewed',result['observations_present']==48 and result['complete_48_observations'] is True and result['all_48_independently_stage_reviewed'] is True)
samples=checked(combined['samples']);statistics=checked(combined['statistics'])
ok('48 actual independent sample rows and RTS',len(samples)==48 and len(statistics)==48)
for a,b in zip(result['raw_observations'],samples):
    ok(a['leg_id']+' full raw metric equality with independent review',
       (a['leg_id'],a['ordinal'],a['cell'],a['lane'],a['guard'],a['RTS'])==(b['leg_id'],b['leg_ordinal'],b['cell'],b['lane'],b['guard'],b['RTS']['raw']) and a['metrics']['guard_elapsed_seconds']==b['guard_elapsed_seconds'] and
       all(a['metrics'][k+'_cpu_seconds']==b['RTS']['parsed']['times'][k]['cpu_seconds'] for k in ('MUT','GC','Total')) and
       all(a['metrics'][k]==b['RTS']['parsed'][k] for k in ('allocated_bytes','copied_bytes','maximum_residency_bytes')))
    assert pin(Path(a['guard']['path']))==a['guard'] and pin(Path(a['RTS']['path']))==a['RTS']
ok('exact global order1..48', [x['ordinal'] for x in result['raw_observations']]==list(range(1,49)))
ok('actual Foundation missing-size and baseline zero unnormalized',result['cells'][0]['size']==0 and result['cells'][-1]['size'] is None and all(result['cells'][i][lane]['per_size'] is None for i in (0,-1) for lane in ('M','G')))
# Isolated pure function from the minimal v2 copy; no module top-level execution.
source=(R/'main-gap-sampling-summary-v2-source/reduce.py').read_text();tree=ast.parse(source)
node=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='pair_summary')
metrics=tuple(result['raw_observations'][0]['metrics']);ns={'METRICS':metrics,'need':lambda v,msg: None if v else (_ for _ in ()).throw(ValueError(msg))}
exec(compile(ast.Module(body=[node],type_ignores=[]),'<pure pair_summary>','exec'),ns)
rows=result['cells'][0]['M']['observations']
for n in (None,0,-1,True,False,1.5,'16'):
    ok('size '+repr(n)+' not silently coerced/divided',ns['pair_summary'](rows,n,396)['per_size'] is None)
ok('positive integer normalized exactly',ns['pair_summary'](rows,16,396)['per_size']['allocated_bytes']==[x['metrics']['allocated_bytes']/16 for x in rows])
v1=(R/'main-gap-sampling-summary-v1-source/reduce.py').read_text()
ok('v2 single-predicate inverse exact',source.replace('if type(n) is int and n>0 else None','if n>0 else None')==v1)
print(json.dumps({'schema':'main-gap-final-numeric-crosscheck-v1','complete':True,'checks':checks,'count':len(checks),'target_executions':0,'independent_combined_review':pin(R/'main-gap-sampling-02-actual-review/combined-final.json')},indent=2,sort_keys=True))
