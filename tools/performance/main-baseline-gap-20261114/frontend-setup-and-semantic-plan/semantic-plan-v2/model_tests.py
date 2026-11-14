"""Synthetic-only local model checks; not real artifact/parser/run qualification."""
from pathlib import Path
import copy,hashlib,json
from contract_model import ContractError,cross_producer_model,same_binary_raw_model,digest
HERE=Path(__file__).resolve().parent
checks=[]
def yes(name,f):
 assert f() is True;checks.append({'name':name,'expected':'accept','passed':True})
def no(name,f):
 try:f()
 except ContractError:checks.append({'name':name,'expected':'reject','passed':True});return
 raise AssertionError(name+' unexpectedly accepted')
raw=b'synthetic-payload';h=digest(raw);sourcehash=digest(b'synthetic-source');aexe=b'synthetic-original-binary';bexe=b'synthetic-stats-binary';crate='model/only';flavor='source'
base={'format':'MLF-CRATE-QUERY-GRAPH-2','configuration':[crate,digest(aexe),'MLF-SOURCE-CRATE-QUERY-7','open-fragment-checker-1/finish-receipt-1',flavor],
 'declarations':['model-a','model-b'],'groups':[['model-a','model-b']],'evidence':[],'types':['model-T'],
 'rows':[{'key':'Input','digest':sourcehash,'reads':[],'payload':None},{'key':'Result','digest':h,'reads':['Input','Input'],'payload':h}],
 'results':{h:raw},'query':{'format':1,'crate':crate,'semantic_fingerprint':'model-fingerprint','inferred_groups':1,'reused_groups':0,'groups':[{'id':'model-group','members':['model-a','model-b'],'cached':False,'semantic_fingerprint':'model-group-fp','query_key':h}]},
 'semantic_files':{'unit.mlfci':b'synthetic-ci','unit.mlfco':b'synthetic-co','unit.queries':b'synthetic-exact-ordered-query-json','queries/.lock':b''}}
a=copy.deepcopy(base);b=copy.deepcopy(base);b['configuration'][1]=digest(bexe)
f=lambda a=a,b=b:cross_producer_model(a,b,aexe,bexe,crate,flavor)
yes('distinct producers each correctly bound, all other fields exact',f)
yes('identical producer bytes are also correctly authenticated',lambda:cross_producer_model(a,a,aexe,aexe,crate,flavor))
yes('legal duplicate reads preserved in both sides',f)
mutations=[
 ('wrong original actual binary',lambda x:x['configuration'].__setitem__(1,'0'*64)),
 ('changed crate',lambda x:x['configuration'].__setitem__(0,'other')),
 ('changed format version',lambda x:x['configuration'].__setitem__(2,'other')),
 ('changed checker version',lambda x:x['configuration'].__setitem__(3,'other')),
 ('changed flavor',lambda x:x['configuration'].__setitem__(4,'lowered')),
 ('extra config field',lambda x:x['configuration'].append('extra')),
 ('dropped read occurrence',lambda x:x['rows'][1]['reads'].pop()),
 ('extra read occurrence',lambda x:x['rows'][1]['reads'].append('Input')),
 ('missing read target',lambda x:x['rows'][1]['reads'].append('Absent')),
 ('self-cycle',lambda x:x['rows'][1]['reads'].append('Result')),
 ('changed row digest',lambda x:x['rows'][0].update(digest='1'*64)),
 ('extra duplicate row identity',lambda x:x['rows'].append(copy.deepcopy(x['rows'][0]))),
 ('missing payload file',lambda x:x['results'].clear()),
 ('extra unreferenced payload',lambda x:x['results'].update({digest(b'extra'):b'extra'})),
 ('corrupt content-addressed payload',lambda x:x['results'].update({h:b'wrong'})),
 ('changed declaration table',lambda x:x['declarations'].append('extra')),
 ('changed group table',lambda x:x['groups'][0].reverse()),
 ('changed types table',lambda x:x['types'].append('extra')),
 ('changed evidence table',lambda x:x['evidence'].append({'fake':1})),
 ('changed checked bytes',lambda x:x['semantic_files'].update({'unit.mlfco':b'wrong'})),
 ('missing semantic file',lambda x:x['semantic_files'].pop('unit.mlfci')),
 ('extra semantic file',lambda x:x['semantic_files'].update({'unexpected':b'bytes'})),
 ('invented old475 inferred count',lambda x:x['query'].update(inferred_groups=475)),
 ('boolean inferred count',lambda x:x['query'].update(inferred_groups=True)),
 ('boolean zero reuse',lambda x:x['query'].update(reused_groups=False)),
 ('nonzero reuse',lambda x:x['query'].update(reused_groups=1)),
 ('cached integer0 instead ofFalse',lambda x:x['query']['groups'][0].update(cached=0)),
 ('extra schema field',lambda x:x.update(unexpected='metadata'))]
for name,mutate in mutations:
 changed=copy.deepcopy(b);mutate(changed);no(name,lambda changed=changed:cross_producer_model(a,changed,aexe,bexe,crate,flavor))
# Distinct read keys demonstrate order, and repeated targets remain legal.
ra=copy.deepcopy(a);rb=copy.deepcopy(b)
for x in [ra,rb]:
 x['rows'].insert(1,{'key':'Input2','digest':digest(b'input2'),'reads':[],'payload':None})
 x['rows'][-1]['reads']=['Input','Input2','Input']
yes('mixed ordered repeated reads accepted unchanged',lambda:cross_producer_model(ra,rb,aexe,bexe,crate,flavor))
rb['rows'][-1]['reads']=['Input2','Input','Input']
no('same read multiset but different order',lambda:cross_producer_model(ra,rb,aexe,bexe,crate,flavor))
# Model complete raw B oracle includes derived identity documents, not only payloads.
oracle={'unit.mlfci':b'ci','unit.mlfco':b'co','unit.queries':b'q','queries/CURRENT':b'B-current','queries/generations/B.mlfqg':b'B-generation','queries/results/r.mlfqr':b'payload','queries/.lock':b''}
yes('same-binary fullraw exact',lambda:same_binary_raw_model(oracle,copy.deepcopy(oracle),digest(bexe),bexe))
for name in oracle:
 changed=copy.deepcopy(oracle);changed[name]+=b'changed'
 no('same-binary no exception for '+name,lambda changed=changed:same_binary_raw_model(oracle,changed,digest(bexe),bexe))
no('same-binary rejects different producer',lambda:same_binary_raw_model(oracle,oracle,digest(bexe),aexe))
changed=copy.deepcopy(oracle);changed['queries/generations/other.mlfqg']=changed.pop('queries/generations/B.mlfqg')
no('same-binary rejects changed generation filename',lambda:same_binary_raw_model(oracle,changed,digest(bexe),bexe))
no('same-binary rejects missing file',lambda:same_binary_raw_model(oracle,{},digest(bexe),bexe))
assert a==base and b['configuration'][1]==digest(bexe)
(HERE/'MODEL-CHECKS.json').write_text(json.dumps({'schema':'semantic-v2-synthetic-contract-model-checks-v1','scope':'synthetic decoded data only, not actual MLFBIN decoder or qualification','check_count':len(checks),'checks':checks,'original_inputs_mutated':False,'real_workload_or_query_counts_used':False,'target_or_repo_helper_executed':False},indent=2,sort_keys=True)+'\n')
print(json.dumps({'synthetic_model_checks':len(checks),'actual_cells_qualified':0,'actual_legs_run':0}))
