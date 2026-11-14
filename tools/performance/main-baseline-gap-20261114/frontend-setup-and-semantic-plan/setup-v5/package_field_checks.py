"""Pure AST-extracted parsing/validation of real complete run02 configurations.
No original module is imported; no helper entry/loader/guard/compiler/lock runs.
Negative edits are in-memory copies, never changes to original .conf artifacts.
"""
from pathlib import Path
import ast, copy, hashlib, json, re, shlex
D=Path(__file__).resolve().parent;R=D.parent;OLD=R/'main-gap-setup-v3-source'
config=json.loads((D/'CONFIG.json').read_text());source=(D/'controller.py').read_text();tree=ast.parse(source)
functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
helper=Path(config['runtime_helper']['path']);ht=ast.parse(helper.read_text());parser=next(n for n in ht.body if isinstance(n,ast.FunctionDef) and n.name=='package_records')
names=['require','registered_unit_fields'];nodes=[functions[n] for n in names]+[parser]
for node in nodes:
 for n in ast.walk(node):
  if isinstance(n,ast.Name):assert n.id not in {'subprocess','module','fcntl','os','open','exec','eval','compile','save'}
  if isinstance(n,ast.Attribute):assert n.attr not in {'read_text','read_bytes','write_text','write_bytes','mkdir','rename','unlink','flock','resolve'}
unit=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='UNIT')
ns={'re':re,'shlex':shlex,'UNIT':unit}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<exact-pure-parser-and-validator>','exec'),ns)
P=R/'main-gap-setup-run02/setup/dependencies';authored=P/'package.conf';registered=P/'package-db/mlf-shape-primitives-0.1.conf'
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
input_pins=[pin(authored),pin(registered),pin(helper)]
assert input_pins[-1]['sha256']==config['runtime_helper']['sha256']
orig_bytes=authored.read_bytes();reg_bytes=registered.read_bytes()
orig=ns['package_records'](orig_bytes.decode());actual=ns['package_records'](reg_bytes.decode())
checks=[]
def check(name,fn):fn();checks.append(dict(name=name,passed=True))
def yes(v):assert v
def rejects(fn):
 try:fn()
 except (RuntimeError,ValueError,TypeError,KeyError):return
 raise AssertionError('negative accepted')
def validate(records):
 ns['require'](set(records)=={unit},'registered private unit identity')
 ns['registered_unit_fields'](records[unit],P/'objects',P,ids)
# Actual six completed package-id commands, never a shell or package invocation.
worker=json.loads((R/'main-gap-setup-run02/setup/setup-receipt.json').read_text())
names6=['base','array','bytestring','text','containers','directory'];ids=[]
for name in names6:
 rows=[r for r in worker['commands'] if r['label']=='global-unit-id-'+name];assert len(rows)==1
 p=Path(rows[0]['guard']['output'])/'stdout';input_pins.append(pin(p))
 raw=p.read_text();assert re.fullmatch(r'[A-Za-z0-9_.+-]+\n',raw);ids.append(raw[:-1])
check('actual run02 six guarded IDs are exact ordered authored depends',lambda:yes(shlex.split(orig[unit]['depends'])==ids))
check('original authored full package accepted',lambda:validate(orig))
check('actual full registered package accepted',lambda:validate(actual))
expected_lists={'exposed-modules':['MLF.Primitive'],'hidden-modules':['MLF.Host.Base','MLF.Host.IO','MLF.Host.Async'],
 'import-dirs':[str(P/'objects')],'library-dirs':[str(P)],'hs-libraries':['HS'+unit],'depends':ids}
old_mismatches=[k for k,want in expected_lists.items() if actual[unit][k]!=' '.join(want)]
check('old exact-string failure reproduced on actual three fields',lambda:yes(old_mismatches==['import-dirs','library-dirs','depends']))
check('original parser retains real continuation leading space',lambda:yes(all(actual[unit][k].startswith(' ') for k in old_mismatches)))
for key,want in expected_lists.items():
 good=copy.deepcopy(actual);good[unit][key]=' \n\t'+' \n\t'.join(want)+' \n'
 check('legal list whitespace '+key,lambda good=good:validate(good))
 good=copy.deepcopy(actual);good[unit][key]=' '.join('"'+x+'"' for x in want)
 check('identical complete double-quoted tokens '+key,lambda good=good:validate(good))
 for suffix in [' "extra-value"',' '+want[0]]:
  bad=copy.deepcopy(actual);bad[unit][key]+=(suffix)
  check('extra or duplicate token '+key+' '+suffix,lambda bad=bad:rejects(lambda:validate(bad)))
 bad=copy.deepcopy(actual);bad[unit][key]='"unterminated'
 check('malformed quote '+key,lambda bad=bad:rejects(lambda:validate(bad)))
 bad=copy.deepcopy(actual);bad[unit][key]=None
 check('nonstring list '+key,lambda bad=bad:rejects(lambda:validate(bad)))
for value in [' '.join(ids[:-1]),' '.join(reversed(ids)),' '.join([ids[0],ids[0],*ids[2:]]),' '.join([*ids,'other-9.0']),'"'+' '.join(ids)+'"']:
 bad=copy.deepcopy(actual);bad[unit]['depends']=value
 check('missing/reordered/replaced/extra/wholequoted depends '+value,lambda bad=bad:rejects(lambda:validate(bad)))
for key in ['import-dirs','library-dirs']:
 want=expected_lists[key][0]
 for value in [want+'/',want+'/../'+Path(want).name,want.replace('run02','run03'),'"'+want+' wrong"','"'+want+'/other"','relative/path']:
  bad=copy.deepcopy(actual);bad[unit][key]=value
  check('exact nonnormalized path '+key+' '+value,lambda bad=bad:rejects(lambda:validate(bad)))
for key in ['name','version','id','key','exposed']:
 for value in [actual[unit][key]+' ', '"'+actual[unit][key]+'"', 'wrong']:
  bad=copy.deepcopy(actual);bad[unit][key]=value
  check('strict scalar '+key+' '+value,lambda bad=bad:rejects(lambda:validate(bad)))
bad=copy.deepcopy(actual);bad[unit]['visibility']='private'
check('visibility public cannot become private',lambda:rejects(lambda:validate(bad)))
bad=copy.deepcopy(actual);bad[unit]['extra-libraries']='unapproved'
check('unknown semantic field not silently stripped',lambda:rejects(lambda:validate(bad)))
bad=copy.deepcopy(actual);del bad[unit]['hidden-modules']
check('missing list field rejected',lambda:rejects(lambda:validate(bad)))
check('duplicate field rejected by exact unchanged parser',lambda:rejects(lambda:ns['package_records'](reg_bytes.decode()+'depends: '+ids[0]+'\n')))
check('duplicate unit rejected by unchanged parser',lambda:rejects(lambda:ns['package_records'](reg_bytes.decode()+'\n---\n'+reg_bytes.decode())))
check('extra different unit rejected',lambda:rejects(lambda:validate(ns['package_records'](reg_bytes.decode()+'\n---\nid: other-1\nname: other\n'))))
check('changed record unit ID rejected',lambda:rejects(lambda:validate(ns['package_records'](reg_bytes.decode().replace('id:              '+unit,'id:              wrong-0')))))
# The v4 package validator is inherited exactly; the separate v5 inverse checks
# account for the intentional cross-compiler publication contract change.
v4=ast.parse((R/'main-gap-setup-v4-source/controller.py').read_text())
oldfn=next(n for n in v4.body if isinstance(n,ast.FunctionDef) and n.name=='registered_unit_fields')
newfn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='registered_unit_fields')
check('registered validator exact v4 AST retained',lambda:yes(ast.dump(oldfn,include_attributes=False)==ast.dump(newfn,include_attributes=False)))
for name in ['COMMANDS.json','GLOBAL-PACKAGE-INPUTS.json','SetupCheck.hs']:
 check('unchanged '+name,lambda name=name:yes((D/name).read_bytes()==(OLD/name).read_bytes()))
check('raw artifacts remain byte-exact unchanged',lambda:yes(authored.read_bytes()==orig_bytes and registered.read_bytes()==reg_bytes))
check('run04 absent',lambda:yes(not (R/'main-gap-setup-run04').exists()))
for p in input_pins:assert pin(Path(p['path']))==p
result={'schema':'main-gap-setup-registered-package-pure-regression-v1','complete':True,'checks':checks,'check_count':len(checks),'actual_input_pins':input_pins,'actual_fields_original_string_mismatches':old_mismatches,'all_negative_edits_in_memory':True,'no_module_top_level_or_original_helper_entry_executed':True,'only_original_function_extracted':'runtime_pins.package_records pure text parser','no_loader_compiler_guard_lock_target_or_admission':True,'raw_artifact_byte_oracles_not_normalized':True,'source':pin(D/'controller.py')}
(D/'package-field-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'package_field_checks':len(checks),'target_executed':False}))
