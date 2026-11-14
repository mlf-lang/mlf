"""Own AST and pure parsing tests. No worker/controller/helper/target execution."""
from pathlib import Path
import ast,hashlib,json,re,struct,zlib,copy
D=Path(__file__).resolve().parent;R=D.parent
checks=[]
def yes(v):assert v
def check(n,fn):fn();checks.append({'name':n,'passed':True})
def rejects(fn):
 try:fn()
 except (ValueError,KeyError,TypeError,UnicodeError,IndexError):return
 raise AssertionError('negative accepted')
def pure(path):
 t=ast.parse(path.read_text());body=[]
 for n in t.body:
  if isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Assign)):body.append(n)
  else:assert isinstance(n,(ast.Import,ast.Expr))
 for n in ast.walk(ast.Module(body=body,type_ignores=[])):
  if isinstance(n,ast.Name):assert n.id not in {'Path','open','os','sys','module','subprocess','__import__','exec','eval','compile'}
  if isinstance(n,ast.Attribute):assert n.attr not in {'write_text','write_bytes','mkdir','rmdir','rename','unlink','read_bytes','read_text'}
 ns={'hashlib':hashlib,'json':json,'re':re,'struct':struct,'zlib':zlib}
 exec(compile(ast.Module(body=body,type_ignores=[]),'<only-audited-pure-definitions>','exec'),ns);return ns
p=pure(D/'semantic_parsers.py');o=pure(D/'publication_oracle.py')
raw=(R/'main-gap-setup-run03/setup/builtin-work/fixture.queries').read_bytes()
q=p['fresh_queries'](raw,'compiler-shapes/builtin')
check('actual unmodified fixture JSON strict grammar accepted, not future cell oracle',lambda:yes(q['inferred_groups']==1))
for k,v in [('format',True),('inferred_groups',True),('reused_groups',1),('groups',[]),('crate','wrong')]:
 x=copy.deepcopy(q);x[k]=v;check('fresh query rejects '+k,lambda x=x:rejects(lambda:p['fresh_queries'](json.dumps(x).encode(),'compiler-shapes/builtin')))
x=copy.deepcopy(q);x['extra']=0;check('unknown JSON field rejected',lambda:rejects(lambda:p['fresh_queries'](json.dumps(x).encode(),'compiler-shapes/builtin')))
check('duplicate JSON key rejected',lambda:rejects(lambda:p['json_object'](b'{"format":1,"format":1}')))
x=copy.deepcopy(q);x['groups']*=2;x['inferred_groups']=2;check('duplicate group rejected',lambda:rejects(lambda:p['fresh_queries'](json.dumps(x).encode(),'compiler-shapes/builtin')))
folder=R/'main-gap-setup-run03/setup/commands/008-fresh-private-four-module-unit';stdout=(folder/'stdout').read_bytes();stderr=(folder/'stderr').read_bytes()
expected={n:str(R/'main-migration-source-20261114-1321/source/host/ghc'/Path(n.replace('.','/')).with_suffix('.hs')) for n in ['MLF.Host.Base','MLF.Host.Async','MLF.Host.IO','MLF.Primitive']}
check('actual full four-module GHC compilation event bytes parse, not typed-cell qualification',lambda:yes(len(p['ghc_compiling'](stdout,stderr,expected))==4))
check('hidden extra Main expected fails',lambda:rejects(lambda:p['ghc_compiling'](stdout,stderr,{**expected,'Main':'/abs/Main.hs'})))
check('duplicate actual Compiling event fails',lambda:rejects(lambda:p['ghc_compiling'](stdout+stdout.splitlines(keepends=True)[0],stderr,expected)))
check('unparsed Compiling line fails',lambda:rejects(lambda:p['ghc_compiling'](stdout+b'Compiling BAD\n',stderr,expected)))
# Decode same original raw generation directly, no renaming or normalized artifact map.
gen=next((R/'main-gap-setup-run03/setup/builtin-work/queries/query-graph-v2/generations').glob('*.mlfqg'));g=o['decode'](gen.read_bytes(),6)
sha=hashlib.sha256((R/'main-gap-setup-run03/setup/stats-emlf').read_bytes()).hexdigest();config=['compiler-shapes/builtin',sha,'MLF-SOURCE-CRATE-QUERY-7','open-fragment-checker-1/finish-receipt-1','source']
check('parameterized snapshot parser accepts exact actual generation',lambda:yes(len(o['snapshot'](g,sha,config)['rows'])==172))
for i,value in [(0,'wrong'),(1,'0'*64),(2,'wrong'),(3,'wrong'),(4,'lowered')]:
 x=list(config);x[i]=value;check('independently expected config mismatch field'+str(i),lambda x=x:rejects(lambda:o['snapshot'](g,sha,x)))
for file in ['worker.py','semantic_parsers.py','publication_oracle.py']:ast.parse((D/file).read_text())
bind=json.loads((D/'BINDINGS.json').read_bytes());check('actual SETUP genuine review bound, source still disabled',lambda:yes(bind['READY'] is False and bind['setup_review']['sha256']=='1b5addd5f3ce1821f43ef02f568df5552781f4e41ec1569284bb7554c83bec59' and bind['stats_binary']['sha256']=='b0b46ae804c6e55b64d7792fa7a6835f7805d2207d03b47ea2918e65eef49347'))
check('no guessed12cell query counts',lambda:yes(bind['actual_query_counts'] is None and bind['actual_owner_observations'] is None))
check('reference route remains unobserved, successful object schema8 source-proved',lambda:yes(all(x['config'][-1] is None and x['route_format_source_evidence'] is not None and x['checked_schema']==8 for x in bind['cell_route_contracts'].values())))
# Runtime plan resolution deliberately requires genuine serialized records, never dummy PASS.
check('unbound setup path rejected by resolver',lambda:rejects(lambda:p['resolved_commands']({'rows':[]},None,{})))
result={'schema':'main-gap-semantic-initial-pure-checks-v1','complete':True,'check_count':len(checks),'checks':checks,'scope':'Pure parsers/AST only; worker/coordinator not executed or accepted. Actual run03 raw input reused read-only, not12cell qualification.','target_helper_guard_lock_executed':False,'setup_gate_bound':True,'source_gate_passed':None}
(D/'pure-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print('pure checks',len(checks))
