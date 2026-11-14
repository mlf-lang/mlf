"""Pure route-observation/freeze negatives using existing actual wire bytes.
All coherent mutations and filename projections are memory-only test data.
No future-cell output is invented and no original target/helper is run.
"""
from pathlib import Path
import ast,copy,hashlib,json,re,struct,tempfile,zlib,types
D=Path(__file__).resolve().parent;R=D.parent
t=ast.parse((D/'publication_oracle.py').read_text())
body=[n for n in t.body if isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Assign))]
for n in ast.walk(ast.Module(body=body,type_ignores=[])):
    if isinstance(n,ast.Name):assert n.id not in {'Path','open','os','sys','subprocess','module','eval','exec','compile','__import__'}
ns={'hashlib':hashlib,'json':json,'re':re,'struct':struct,'zlib':zlib}
exec(compile(ast.Module(body=body,type_ignores=[]),'<pure-reference-oracle>','exec'),ns)
checks=[]
def yes(v):assert v
def case(name,fn):fn();checks.append({'name':name,'passed':True})
def bad(fn):
    try:fn()
    except (ValueError,KeyError,TypeError,IndexError,RuntimeError,FileExistsError,AssertionError):return
    raise AssertionError('negative accepted')
def read(root):
    names={'fixture.spec':'crate.spec','fixture.mlfci':'unit.mlfci','fixture.mlfco':'unit.mlfco','fixture.queries':'unit.queries'}
    return {names.get(str(p.relative_to(root)),str(p.relative_to(root))):p.read_bytes() for p in root.rglob('*') if p.is_file() and p.name!='Fixture.emlf'}
H=R/'main-gap-setup-run04/setup';a=read(H/'ordinary-reference/builtin-work');b=read(H/'builtin-work')
review=json.loads((R/'main-gap-setup-run04-actual-review/report.json').read_bytes());asha=review['original_binary']['sha256'];bsha=review['stats_binary']['sha256']
template=['compiler-shapes/builtin',None,'MLF-SOURCE-CRATE-QUERY-7','open-fragment-checker-1/finish-receipt-1',None]
observed=ns['reference_cell'](a,asha,template)
case('unmodified actual run04 wire projection reference source observed',lambda:yes(observed['observed_route']=='source'))
case('actual run04 bytes cross-producer strictly match frozen observed route',lambda:yes(ns['compare_cell'](a,b,asha,bsha,observed['configuration_template'],8)['all_other_raw_bytes_equal']))
P=ns['PREFIX'];cur=P+'CURRENT'
def crc(raw):
    x=bytearray(raw);x[76:80]=bytes(4);x[76:80]=struct.pack('<I',zlib.crc32(x));return bytes(x)
def var(n):
    out=bytearray()
    while n>=128:out.append((n&127)|128);n>>=7
    out.append(n);return bytes(out)
def reconfig(files,producer,fields):
    out=dict(files);old=ns['reference_cell'](out,producer,template);key=old['generation'];raw=out.pop(key)
    graph=ns['decode'](raw,6);root=ns['node'](graph,graph['roots'][0],412);sym=graph['symbols'][graph['nodes'][root[1]][1]]
    text=''.join(str(len(x))+':'+x for x in fields).encode();piece=var(len(text))+text
    start,end=sym['prefix'],sym['start']+sym['bytes'];delta=len(piece)-(end-start)
    raw=bytearray(raw[:start]+piece+raw[end:])
    names=list(graph['header'])
    for name in ['total_bytes','symbol_bytes','node_offset','root_offset']:
        off=8+4*names.index(name);raw[off:off+4]=struct.pack('<I',graph['header'][name]+delta)
    raw=crc(raw);address=hashlib.sha256(raw).hexdigest();out[P+'generations/'+address+'.mlfqg']=raw
    cg=ns['decode'](out[cur],6);cs=cg['symbols'][0]['start'];out[cur]=crc(out[cur][:cs]+address.encode()+out[cur][cs+64:])
    return out
full=[template[0],asha,*template[2:4],'lowered'];lower=reconfig(a,asha,full)
lo=ns['reference_cell'](lower,asha,template)
case('legal lowered syntax accepted as pre-freeze pure data, not claimed actual branch',lambda:yes(lo['observed_route']=='lowered'))
bstats_lower=reconfig(b,bsha,[template[0],bsha,*template[2:4],'lowered'])
case('candidate legal but different route rejected against source reference',lambda:bad(lambda:ns['compare_cell'](a,bstats_lower,asha,bsha,observed['configuration_template'],8)))
case('same binary changed route never grants raw exemption',lambda:bad(lambda:ns['compare_cell'](a,lower,asha,asha,observed['configuration_template'],8)))
for i,value in [(0,'wrong-crate'),(1,'0'*64),(2,'wrong-format'),(3,'wrong-checker'),(4,'unknown')]:
    fields=[template[0],asha,*template[2:4],'source'];fields[i]=value;x=reconfig(a,asha,fields)
    case('coherently resealed wrong reference field '+str(i),lambda x=x:bad(lambda:ns['reference_cell'](x,asha,template)))
for fields in [[template[0],asha,*template[2:4]], [template[0],asha,*template[2:4],'source','extra']]:
    x=reconfig(a,asha,fields);case('coherently resealed wrong config arity '+str(len(fields)),lambda x=x:bad(lambda:ns['reference_cell'](x,asha,template)))
# The production worker's exact equality predicate after verify_pin is exercised
# below as plain immutable files. Provenance mismatch is not a wire-grammar test.
source=(D/'worker.py').read_text();wt=ast.parse(source)
exprs=[n.args[0] for n in ast.walk(wt) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='require' and len(n.args)>1 and isinstance(n.args[1],ast.Constant) and n.args[1].value=='immutable original reference before B']
assert len(exprs)==1
ct=ast.parse((D/'controller.py').read_text());cnames={'require','safe','sha','pin','verify_pin','load'}
cbody=[n for n in ct.body if isinstance(n,ast.FunctionDef) and n.name in cnames]
for n in ast.walk(ast.Module(body=cbody,type_ignores=[])):
    if isinstance(n,ast.Name):assert n.id not in {'os','sys','subprocess','module','fcntl'}
cns={'Path':Path,'hashlib':hashlib,'json':json}
exec(compile(ast.Module(body=cbody,type_ignores=[]),'<read-hash-only-contract-functions>','exec'),cns)
C=types.SimpleNamespace(**{k:cns[k] for k in cnames})
exprcode=compile(ast.fix_missing_locations(ast.Expression(exprs[0])),'<exact-worker-pre-B-predicate>','eval')
with tempfile.TemporaryDirectory(prefix='pure-reference-',dir=D) as tmp:
    tmp=Path(tmp);p=tmp/'reference.json'
    baseline={'schema':'main-gap-cell-original-reference-v3','cell':'test-data-only','source_commit':'main-pin','source_inputs':[{'test':'pin'}],
      'setup_review':review['actual_pins']['worker'],'original_binary':review['original_binary'],'original_active_path':'/test/active',
      'spec_sha256':hashlib.sha256(a['crate.spec']).hexdigest(),'reference_files':{'wire-test':hashlib.sha256(next(v for k,v in a.items() if k.endswith('.mlfqg'))).hexdigest()},
      'reference_commands':[{'argv':'frozen-actual-provenance-required'}],'observed':observed,'candidate_invoked':False,'retry_allowed':False}
    frozen=json.dumps(baseline,sort_keys=True).encode()
    with p.open('xb') as stream:stream.write(frozen)
    digest=hashlib.sha256(frozen).hexdigest();baseline_pin=C.pin(p)
    scope={'C':C,'baseline_pin':baseline_pin,'baseline':baseline,'self':types.SimpleNamespace(raw=lambda root:a),'ref':tmp,'old':a}
    def accept():yes(eval(exprcode,scope))
    case('plain immutable full reference contract accepted',accept)
    case('duplicate freeze fails exclusive create',lambda:bad(lambda:p.open('xb')))
    for k,v in [('cell','another-cell'),('source_commit','other-main'),('source_inputs',[]),('original_binary',review['stats_binary']),
                ('spec_sha256','0'*64),('original_active_path','/different/path'),('reference_commands',[]),('observed',lo),('candidate_invoked',True),('retry_allowed',True)]:
        x=copy.deepcopy(baseline);x[k]=v;p.write_text(json.dumps(x,sort_keys=True));case('frozen provenance rejects '+k,lambda:bad(accept));p.write_bytes(frozen)
    p.unlink();case('missing frozen reference rejected',lambda:bad(accept));p.write_bytes(frozen)
    p.write_text(json.dumps({**baseline,'observed':lo}));case('reference route rewritten after B failure cannot rebind original pin',lambda:bad(accept))
case('worker freeze and pin occur before B compile',lambda:yes(source.index("with frozen.open('x')")<source.index("C.require(row['kind']=='stats_compile'")))
case('worker has no reference restart or alternate route after B failure',lambda:yes('except' not in source and "observed['configuration_template']" in source and 'retry_allowed\':False' in source))
result={'schema':'main-gap-reference-freeze-pure-checks-v1','complete':True,'checks':checks,'count':len(checks),
    'actual_run04_bytes_read_only':True,'projection_is_not_actual_cell_evidence':True,'legitimate_lowered_mutation_is_only_synthetic_syntax':True,
    'claims_actual_branch_from_syntax':False,'controller_guard_helper_target_executed':False,'source_gate_passed':None}
(D/'reference-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print('reference checks',len(checks))
