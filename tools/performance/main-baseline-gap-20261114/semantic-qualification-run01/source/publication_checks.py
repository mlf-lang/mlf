"""Own isolated pure bytes/AST checks on actual frozen run03 files and mutations.
No module top-level import, controller/helper/loader/guard/target execution.
"""
from pathlib import Path
import ast,hashlib,json,re,struct,zlib,copy
D=Path(__file__).resolve().parent;R=D.parent;H=R/'main-gap-setup-run03/setup'
p=D/'publication_oracle.py';t=ast.parse(p.read_text());allowed=[]
for n in t.body:
 if isinstance(n,(ast.FunctionDef,ast.ClassDef,ast.Assign)):allowed.append(n)
 elif isinstance(n,(ast.Import,ast.Expr)):continue
 else:raise AssertionError(type(n).__name__)
for n in ast.walk(ast.Module(body=allowed,type_ignores=[])):
 if isinstance(n,ast.Name):assert n.id not in {'open','Path','os','sys','subprocess','module','eval','exec','compile','input','__import__'}
 if isinstance(n,ast.Attribute):assert n.attr not in {'write_text','write_bytes','mkdir','unlink','rename','replace','read_bytes','read_text','system','run','Popen'}
ns={'hashlib':hashlib,'re':re,'struct':struct,'zlib':zlib}
exec(compile(ast.Module(body=allowed,type_ignores=[]),'<audited-pure-publication-definitions>','exec'),ns)
checks=[]
def check(name,fn):
 fn();checks.append({'name':name,'passed':True})
def yes(x):assert x

def rejects(fn):
 try:fn()
 except (ValueError,UnicodeError,IndexError,KeyError,TypeError,struct.error):return
 raise AssertionError('negative accepted')
def read(root):
 # Pure test projection only: no artifact on disk is renamed, normalized or admitted.
 # Actual fixed-Fixture content is mapped into generic cell field names so the
 # unchanged wire bytes exercise the new parameterized decoder. It is not a new
 # actual cell, and fixed builtin inputs remain external authenticated inputs.
 result={}
 names={'fixture.spec':'crate.spec','fixture.mlfci':'unit.mlfci','fixture.mlfco':'unit.mlfco','fixture.queries':'unit.queries'}
 for p in (root/'builtin-work').rglob('*'):
  if not p.is_file():continue
  key=str(p.relative_to(root/'builtin-work'))
  if key=='Fixture.emlf':continue
  result[names.get(key,key)]=p.read_bytes()
 return result
a=read(H/'ordinary-reference');b=read(H)
asha=hashlib.sha256((R/'main-baseline-ordinary-run01/build/producer/bin/emlf').read_bytes()).hexdigest()
bsha=hashlib.sha256((H/'stats-emlf').read_bytes()).hexdigest()
template=['compiler-shapes/builtin',None,'MLF-SOURCE-CRATE-QUERY-7','open-fragment-checker-1/finish-receipt-1','source']
def cmp(a,b,sa,sb):return ns['compare_cell'](a,b,sa,sb,template,8)
def pub(a,sa):
 cfg=list(template);cfg[1]=sa
 return ns['publication'](a,sa,cfg,8)
dec=ns['decode'];P=ns['PREFIX'];current=P+'CURRENT' 
proof=cmp(a,b,asha,bsha)
check('actual run03 wire bytes in pure generic field-name projection accepted; not cell execution',lambda:yes(proof['files_each']==85 and proof['result_files']==78 and proof['rows']==172 and proof['all_other_raw_bytes_equal']))
check('old raw comparison remains false',lambda:yes(a!=b))
check('same actual ordinary bytes self compare strictly identical',lambda:yes(cmp(a,a,asha,asha)['full_cross_compiler_raw_equality_claimed']))
check('same actual stats bytes self compare strictly identical',lambda:yes(cmp(b,b,bsha,bsha)['full_cross_compiler_raw_equality_claimed']))
# Pure mutable copies only; production/original files are never changed.
def crc(raw):
 x=bytearray(raw);x[76:80]=bytes(4);x[76:80]=struct.pack('<I',zlib.crc32(x));return bytes(x)
def one(raw,at,new):return raw[:at]+new+raw[at+len(new):]
def generation_map(base,transform):
 out=dict(base);g=next(k for k in out if k.endswith('.mlfqg'));old=out.pop(g);new=crc(transform(old));address=hashlib.sha256(new).hexdigest();out[P+'generations/'+address+'.mlfqg']=new
 cg=dec(out[current],6);start=cg['symbols'][0]['start'];out[current]=crc(one(out[current],start,address.encode()));return out
bp=pub(b,bsha);gkey=bp['generation'];graw=b[gkey];g=bp['graph'];span=bp['snapshot']['compiler_span']
for name,sa,sb in [('wrong ordinary expected exe SHA','0'*64,bsha),('wrong stats expected exe SHA',asha,'0'*64),('swapped actual executable binding',bsha,asha),('one SHA assigned both sides',asha,asha)]:
 check(name,lambda sa=sa,sb=sb:rejects(lambda:cmp(a,b,sa,sb)))
for name,v in [('missing key',{k:x for k,x in b.items() if k!='unit.mlfco'}),('extra lifecycle file',{**b,'controller.json':b'{}'}),('extra stale generation',{**b,P+'generations/'+'0'*64+'.mlfqg':graw}),('extra arbitrary blob',{**b,P+'results/'+'0'*64+'.mlfqr':b'garbage'})]:
 check(name,lambda v=v:rejects(lambda:cmp(a,v,asha,bsha)))
result=next(k for k in b if k.endswith('.mlfqr'))
check('missing referenced result file',lambda:rejects(lambda:cmp(a,{k:v for k,v in b.items() if k!=result},asha,bsha)))
extra=next(v for k,v in b.items() if k.endswith('unit.mlfci'));ename=P+'results/'+hashlib.sha256(extra).hexdigest()+'.mlfqr'
check('extra correctly content addressed blob',lambda:rejects(lambda:cmp(a,{**b,ename:extra},asha,bsha)))
for rel in ['unit.mlfci','unit.mlfco','crate.spec','crate.spec','unit.mlfci','unit.mlfco','unit.queries','queries/.lock','queries/.lock',result]:
 v=dict(b);v[rel]=v[rel]+b'x'
 check('changed raw semantic file '+rel,lambda v=v:rejects(lambda:cmp(a,v,asha,bsha)))
# Re-sign all affected CRC/SHA/CURRENT fields so semantic negatives are not merely checksum failures.
for name,at,value in [('forged embedded compiler SHA',span[0],b'0'*64),('unrelated crate config',g['symbols'][bp['snapshot']['config_symbol']]['start']+3,b'X'),('unrelated source version',graw.index(b'MLF-SOURCE-CRATE-QUERY-7')+21,b'8'),('unrelated checker version',graw.index(b'open-fragment-checker-1')+21,b'2'),('unrelated flavor',graw.index(b'6:source')+2,b'X')]:
 v=generation_map(b,lambda raw,at=at,value=value:one(raw,at,value))
 check(name+' with complete CRC/name/CURRENT reseal',lambda v=v:rejects(lambda:cmp(a,v,asha,bsha)))
# Invalid field/schema/layout/count bytes with valid recomputed CRC and derived addresses.
for field,value in [('version',2),('flags',1),('schema',5),('header_bytes',81),('total_bytes',len(graw)-1),('symbol_offset',81),('symbol_bytes',g['header']['symbol_bytes']-1),('node_offset',g['header']['node_offset']+1),('node_bytes',g['header']['node_bytes']-1),('edges',g['header']['edges']+1),('roots',2),('root_offset',g['header']['root_offset']-1),('root_bytes',g['header']['root_bytes']+1),('node_width',g['header']['node_width']+1),('symbol_width',g['header']['symbol_width']+1)]:
 fields=list(g['header']);at=8+4*fields.index(field);v=generation_map(b,lambda raw,at=at,value=value:one(raw,at,struct.pack('<I',value)))
 check('header '+field+' with reseal',lambda v=v:rejects(lambda:cmp(a,v,asha,bsha)))
for name,transform in [('trailing bytes',lambda raw:raw+b'junk'),('truncated root section',lambda raw:raw[:-1]),('invalid UTF8',lambda raw:one(raw,g['symbols'][0]['start'],b'\xff')),('node bit change',lambda raw:one(raw,g['header']['node_offset'],bytes([raw[g['header']['node_offset']]^1]))),('root bit change',lambda raw:one(raw,g['header']['root_offset'],bytes([raw[g['header']['root_offset']]^1])))]:
 v=generation_map(b,transform);check(name+' with reseal',lambda v=v:rejects(lambda:cmp(a,v,asha,bsha)))
v=dict(b);v[gkey]=one(v[gkey],76,bytes([v[gkey][76]^1]));check('bad generation CRC',lambda:rejects(lambda:cmp(a,v,asha,bsha)))
v=dict(b);v[P+'generations/'+'a'*64+'.mlfqg']=v.pop(gkey);check('wrong generation filename',lambda:rejects(lambda:cmp(a,v,asha,bsha)))
for name,transform in [('bad CRC',lambda raw:one(raw,76,bytes([raw[76]^1]))),('wrong digest',lambda raw:crc(one(raw,dec(raw,6)['symbols'][0]['start'],b'0'*64))),('trailing data',lambda raw:crc(raw+b'\0')),('wrong schema',lambda raw:crc(one(raw,16,struct.pack('<I',7))))]:
 v=dict(b);v[current]=transform(v[current]);check('CURRENT '+name,lambda v=v:rejects(lambda:cmp(a,v,asha,bsha)))
# Direct decoded literal mutations exercise alias and descriptor bounds without a synthetic encoder.
for name,modify in [('config alias',lambda gg:gg['nodes'].__setitem__(gg['roots'][0],('node',412,(*gg['nodes'][gg['roots'][0]][2][:2],gg['nodes'][gg['roots'][0]][2][1],*gg['nodes'][gg['roots'][0]][2][3:])))),('root extra field',lambda gg:gg['nodes'].__setitem__(gg['roots'][0],('node',412,(*gg['nodes'][gg['roots'][0]][2],0)))),('negative descriptor',lambda gg:gg['nodes'].__setitem__(bp['snapshot']['rows'][0]['key'],('int',-1)))]:
 gg=copy.deepcopy(g);modify(gg);check('literal parsed '+name,lambda gg=gg:rejects(lambda:ns['snapshot'](gg,bsha,[template[0],bsha,*template[2:]])))
for text in ['01:a','-1:x','1','2:a','1:a0:x','999999999999999999999:a']:
 check('invalid packed '+text,lambda text=text:rejects(lambda:ns['packed'](text)))
# Unmodified blocks must stay exact; allowed extents never implement a global substitution.
check('raw before compiler field changed rejects direct span predicate',lambda:rejects(lambda:ns['exact_except'](b'abc',b'xbc',[(1,2)])))
check('raw after compiler field changed rejects direct span predicate',lambda:rejects(lambda:ns['exact_except'](b'abc',b'abx',[(1,2)])))
check('overlapping allowance rejects',lambda:rejects(lambda:ns['exact_except'](b'abc',b'abc',[(0,2),(1,3)])))
# Explicit low-level canonical rejection and same-stats no-exception checks.
for name,raw in [('overlong varint',b'\x80\x00'),('uint64 overflow',b'\xff'*9+b'\x02'),('unterminated varint',b'\x80'*10)]:
 check(name,lambda raw=raw:rejects(lambda:ns['Bits'](raw,0,len(raw)).var()))
check('nonzero bit padding',lambda:rejects(lambda:ns['Bits'](b'\x80',0,1).finish()))
check('same stats binary never grants changed raw file exception',lambda:rejects(lambda:cmp(b,{**b,'crate.spec':b['crate.spec']+b' '},bsha,bsha)))
# Execute exactly the reviewed snapshot closure loop, on explicit finite literals.
# This is not a substitute for real Haskell execution; it tests this pure Python predicate.
snap_ast=next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='snapshot')
first=next(i for i,n in enumerate(snap_ast.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='done')
last=next(i for i,n in enumerate(snap_ast.body) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='key' and i>first)
loop=ast.Module(body=snap_ast.body[first:last+1],type_ignores=[])
for n in ast.walk(loop):
 if isinstance(n,ast.Name):assert n.id not in {'Path','open','os','sys','module','exec','eval','compile','subprocess'}
def closure(rows):
 scope={**ns,'bydesc':{k:{'reads':tuple(v)} for k,v in rows.items()}}
 exec(compile(loop,'<exact-pure-snapshot-closure-loop>','exec'),scope)
 return scope['done']
check('exact DFS accepts diamond sharing',lambda:yes(closure({0:[1,2],1:[3],2:[3],3:[]})=={0,1,2,3}))
check('exact DFS preserves repeated reads without false cycle',lambda:yes(closure({0:[1,2,1],1:[3,3],2:[3],3:[]})=={0,1,2,3}))
check('exact DFS accepts dependency roots before users',lambda:yes(closure({3:[],1:[3],2:[3],0:[1,2]})=={0,1,2,3}))
check('exact DFS rejects back edge',lambda:rejects(lambda:closure({0:[1],1:[2],2:[0]})))
check('exact DFS rejects self edge',lambda:rejects(lambda:closure({0:[0]})))
# Production resource-policy boundaries on the exact pure decoder predicates.
check('symbol size exact limit accepted',lambda:yes(ns['symbol_budget'](16777216,0)==16777216))
check('symbol size over limit rejected',lambda:rejects(lambda:ns['symbol_budget'](16777217,0)))
check('total symbol exact limit accepted',lambda:yes(ns['symbol_budget'](1,134217727)==134217728))
check('total symbol over limit rejected',lambda:rejects(lambda:ns['symbol_budget'](1,134217728)))
check('constructor tag max accepted',lambda:yes(ns['node_resources'](('node',2147483647,()),[],[],[])==(1,1)))
check('constructor tag overflow rejected',lambda:rejects(lambda:ns['node_resources'](('node',2147483648,()),[],[],[])))
check('node depth exact limit accepted',lambda:yes(ns['node_resources'](('node',1,(0,)),[],[16383],[1])==(16384,2)))
check('node depth over limit rejected',lambda:rejects(lambda:ns['node_resources'](('node',1,(0,)),[],[16384],[1])))
check('node work exact limit accepted',lambda:yes(ns['node_resources'](('node',1,(0,)),[],[1],[67108863])==(2,67108864)))
check('node work repeated child over limit rejected',lambda:rejects(lambda:ns['node_resources'](('node',1,(0,0)),[],[1],[33554432])))
check('text work over limit rejected',lambda:rejects(lambda:ns['node_resources'](('text',0),[{'bytes':67108864}],[],[])))
check('identity table exact budget accepted',lambda:yes(ns['identity_lengths']([67108864])==[67108864]))
check('identity table over budget rejected',lambda:rejects(lambda:ns['identity_lengths']([67108864,1])))
check('empty individual identity rejected',lambda:rejects(lambda:ns['identity_lengths']([0])))
check('packed identity framing charged',lambda:yes(ns['packed_size']([3,0])==7))
check('packed identity over budget rejected',lambda:rejects(lambda:ns['packed_size']([67108864])))
check('query longest path4096 accepted',lambda:yes(len(closure({i:([i+1] if i<4095 else []) for i in range(4096)}))==4096))
check('query longest path4097 rejected',lambda:rejects(lambda:closure({i:([i+1] if i<4096 else []) for i in range(4097)})))
root_need=next(n for n in ast.walk(next(n for n in t.body if isinstance(n,ast.FunctionDef) and n.name=='decode')) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='need' and len(n.args)==2 and isinstance(n.args[1],ast.Constant) and n.args[1].value=='aggregate expanded root work')
def root_policy(works,roots):
 exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.Expr(value=root_need)],type_ignores=[])),'<exact-root-work-predicate>','exec'),{**ns,'works':works,'roots':roots})
check('aggregate repeated root exact limit accepted',lambda:root_policy([33554432],[0,0]))
check('aggregate repeated root overflow rejected',lambda:rejects(lambda:root_policy([33554433],[0,0])))
# Exact typed-field predicates preserve order and reject only production-invalid data.
def typed_predicate(message,values):
 test=next(n for n in ast.walk(snap_ast) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='need' and len(n.args)==2 and isinstance(n.args[1],ast.Constant) and n.args[1].value==message)
 expr=ast.fix_missing_locations(ast.Module(body=[ast.Expr(value=test)],type_ignores=[]))
 exec(compile(expr,'<exact-typed-field-predicate>','exec'),{**ns,**values})
check('unsorted valid group members accepted in original order',lambda:typed_predicate('group indices',{'row':(2,0),'ds':['a','b','c']}))
check('duplicate group members rejected',lambda:rejects(lambda:typed_predicate('group indices',{'row':(0,0),'ds':['a']})))
check('empty evidence goal rejected',lambda:rejects(lambda:typed_predicate('evidence indices/site/nonempty goal',{'row':(0,0,''),'gs':[(0,)]})))
check('nonempty Unicode evidence goal accepted',lambda:typed_predicate('evidence indices/site/nonempty goal',{'row':(0,0,'λ雪🙂'),'gs':[(0,)]}))
# Actual raw inputs pinned after every test; no file writes occurred outside this new package.
def pin(p):
 raw=p.read_bytes();return {'path':str(p),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
assert read(H/'ordinary-reference')==a and read(H)==b
result={'schema':'main-gap-cross-compiler-pure-checks-v1','complete':True,'checks':checks,'check_count':len(checks),'actual_run03_wire_test_projection_positive':proof,'old_run03_qualification_changed':False,'target_or_helper_executed':False,'oracle':pin(p),'actual_fixture_bytes_unchanged':True,'actual_executable_pins':[pin(R/'main-baseline-ordinary-run01/build/producer/bin/emlf'),pin(H/'stats-emlf')]}
(D/'publication-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'passed':len(checks),'actual_test_projection_files_per_side':85,'decoder_rows':proof['rows']}))
