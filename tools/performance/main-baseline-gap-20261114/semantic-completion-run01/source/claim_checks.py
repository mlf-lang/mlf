"""C1 pure-AST and temporary-file regressions only. No controller/module entry.
The temporary bindings below are test data, never actual admissions or receipts.
"""
from pathlib import Path
import ast,json,hashlib,os,stat,tempfile,types
R=Path('<EXPERIMENT_ROOT>');O=R/'main-gap-semantic-completion-v1-source';D=R/'main-gap-semantic-completion-v2-source'
checks=[]
def need(ok,text):
 if not ok:raise RuntimeError(text)
def check(name,ok):
 assert ok,name;checks.append(name)
def reject(name,fn):
 try:fn()
 except (RuntimeError,FileNotFoundError,KeyError,TypeError,ValueError):checks.append(name)
 else:raise AssertionError(name)
def pin(p):
 b=p.read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def extract(p,names,env):
 nodes=[n for n in ast.parse(p.read_bytes()).body if isinstance(n,ast.FunctionDef) and n.name in names]
 assert {n.name for n in nodes}==names
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(p),'exec'),env)
 return env
revision=json.loads((D/'REVISION.json').read_bytes());source=(D/'worker.py').read_text();check('exact worker inverse',source.replace(revision['claim_insertion_exact'],'',1)==(O/'worker.py').read_text())
check('identity implementation byte identical',(D/'identity.py').read_bytes()==(O/'identity.py').read_bytes())
worker=ast.parse(source);cls=next(x for x in worker.body if isinstance(x,ast.ClassDef));init=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='__init__')
index=next(i for i,x in enumerate(init.body) if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='claim' for t in x.targets));snippet=init.body[index:index+3]
check('three nodes only',isinstance(snippet[0],ast.Assign) and isinstance(snippet[1],ast.Expr) and isinstance(snippet[2],ast.AugAssign))
check('no new pin call',not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='pin' for x in snippet for n in ast.walk(x)))
compiled=compile(ast.Module(body=snippet,type_ignores=[]),'<exact C1 claim insertion>','exec')
def select(deadline,q):
 env={'deadline':deadline,'self':types.SimpleNamespace(Q=q),'C':types.SimpleNamespace(require=need),'all_inputs':[]}
 exec(compiled,env);return env['all_inputs']
identity=extract(D/'identity.py',{'need','shape','attest','capture','check','finish','extend'},{'Path':Path,'hashlib':hashlib,'os':os,'stat':stat})
with tempfile.TemporaryDirectory(prefix='claim-pure-') as td:
 q=Path(td);(q/'claims').mkdir();p=q/'claims/COMPLETION.json';original=b'{"phase":"COMPLETION","retry_allowed":false}\n';p.write_bytes(original)
 original_pin=pin(p);bound={'claim':dict(original_pin)};selected=select(bound,q)
 check('uses binding original object',selected[0] is bound['claim'] and selected==[original_pin])
 snapshot=identity['capture'](selected);identity['check'](snapshot);identity['finish'](snapshot);checks.append('valid unchanged claim full/light/full')
 p.write_bytes(original.replace(b'false',b'false'))
 reject('same bytes rewritten after entry metadata change',lambda:identity['check'](snapshot))
 p.write_bytes(original);snapshot=identity['capture'](selected);p.write_bytes(original.replace(b'COMPLETION',b'CORRUPTION'))
 reject('same-name content rewrite light failure',lambda:identity['check'](snapshot));reject('same-name content rewrite full exit failure',lambda:identity['finish'](snapshot))
 reject('changed before entry uses original SHA not fresh current',lambda:identity['capture'](select(bound,q)))
 p.write_bytes(original);snapshot=identity['capture'](selected);replacement=q/'replacement';replacement.write_bytes(original);replacement.replace(p)
 reject('same-content inode replacement after entry',lambda:identity['check'](snapshot));reject('same-content inode replacement full exit',lambda:identity['finish'](snapshot))
 p.unlink();reject('missing claim',lambda:identity['capture'](selected));p.write_bytes(original)
 for label,claim in [('wrong scope',dict(original_pin,path=str(q/'other/COMPLETION.json'))),('wrong phase path',dict(original_pin,path=str(q/'claims/SEMANTIC.json'))),('extra field',dict(original_pin,extra=True)),('missing hash',{k:v for k,v in original_pin.items() if k!='sha256'}),('not dict',None)]:
  reject(label,lambda claim=claim:select({'claim':claim},q))
 reject('missing binding claim',lambda:select({},q))
 p.unlink();p.symlink_to(q/'missing');reject('claim symlink',lambda:identity['capture'](selected));p.unlink();os.mkfifo(p);reject('claim FIFO before read',lambda:identity['capture'](selected))
# Real serialized historical launch binding is a different scope; must not be
# accidentally adopted as the future completion one-use claim.
failed=R/'main-gap-setup-run04/semantic-qualification-01';actual=json.loads((failed/'launch-binding.json').read_bytes())
reject('actual historical claim path cannot become future completion claim',lambda:select(actual,R/'main-gap-setup-run04/semantic-completion-01'))
check('old source manifest unchanged',pin(O/'MANIFEST.json')['sha256']=='32a731107594df0fdd50f1a2e2b7650235d750886d227857a92d3012fcfc3272')
check('new scope remains absent',not (R/'main-gap-setup-run04/semantic-completion-01').exists())
# Controller delta is exactly package identity plus actual relocated config pin.
a=(O/'controller.py').read_text();b=(D/'controller.py').read_text();oldhash=pin(O/'BINDINGS.json')['sha256'];newhash=pin(D/'BINDINGS.json')['sha256']
expected=a.replace("PB = R/'main-gap-semantic-completion-v1-source'","PB = R/'main-gap-semantic-completion-v2-source'").replace(oldhash,newhash)
check('controller exact two-value mechanical delta',b==expected)
report={'schema':'completion-original-claim-pin-pure-checks-v1','complete':True,'count':len(checks),'checks':checks,'temporary_models_only':True,'actual_historical_binding_read_only':pin(failed/'launch-binding.json'),'actual_completion_claim_created':False,'no_original_helper_module_guard_loader_compiler_lock_or_target_execution':True}
(D/'claim-check-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps({'claim_checks':len(checks),'actual_scope_created':False}))
