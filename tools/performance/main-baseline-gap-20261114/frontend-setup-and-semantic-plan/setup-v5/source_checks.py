"""Own AST/read/hash regression only. Never import an original controller/helper.
No subprocess, loader, compiler, guard, lock, target or source materialization.
"""
from pathlib import Path
import ast, copy, hashlib, json, os, re, sys
D=Path(__file__).resolve().parent;R=D.parent
source=(D/'controller.py').read_text();tree=ast.parse(source)
N={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
allowed=['require','safe','sha','pin','verify_pin','load','configuration','static_inputs','envelope_ns','entry_ns','row_sha','inner_command','command','import_flags','pack','interface','fresh_fixture','unit_id','tree_pins','completed_epoch_identity']
for name in allowed:
 for n in ast.walk(N[name]):
  if isinstance(n,ast.Name):assert n.id not in {'subprocess','module','fcntl','save','exec','eval','compile'},(name,n.id)
  if isinstance(n,ast.Attribute):assert n.attr not in {'write_text','write_bytes','mkdir','rename','replace','unlink','rmdir','flock'},(name,n.attr)
values={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ['READY','CONFIG_SHA','BUDGETS','ALLOWED_ENV','FORBIDDEN_ENV','PACKAGES','UNIT','BUILTIN','FIXTURE']}
ns={'Path':Path,'hashlib':hashlib,'json':json,'os':os,'sys':sys,'re':re,'PB':D,'R':R,'WORK':R/'main-gap-setup-run04','MAX_NS':600*10**9,**values}
exec(compile(ast.Module(body=[N[k] for k in allowed],type_ignores=[]),'<explicit-readonly-whitelist>','exec'),ns)
checks=[]
def check(name,fn):
 fn();checks.append({'name':name,'passed':True})
def yes(value):assert value

def rejects(fn):
 try:fn()
 except (RuntimeError,ValueError,KeyError,TypeError,FileNotFoundError,UnicodeError):return
 raise AssertionError('negative accepted')
c=ns['configuration']()
check('disabled only; SETUP600 independent ceiling600',lambda:yes(values['READY'] is False and values['BUDGETS']=={'SETUP':600}))
check('real serialized config string/Path equivalent',lambda:yes(ns['load'](str(D/'CONFIG.json'))==ns['load'](D/'CONFIG.json')))
check('all actual serialized static inputs close read-only',lambda:yes(ns['static_inputs'](json.loads(json.dumps(c)))[0]==Path(c['source'])))
for key in ['source_inventory','baseline_controller','contract_manifest','closures','stats_parser','runtime_helper','ghc_pkg','ghc_pkg_elf','ar','shell','commands']:
 bad=copy.deepcopy(c);bad[key]['sha256']='0'*64
 check('changed real '+key+' rejects',lambda bad=bad,key=key:rejects(lambda:ns['verify_pin'](bad[key])))
check('0 plus600 fits exact600',lambda:yes(ns['entry_ns'](0,'SETUP')==0))
for n in [1,-1,True,0.0,None]:check('nonzero or invalid independent prefix '+repr(n),lambda n=n:rejects(lambda:ns['entry_ns'](n,'SETUP')))
check('unknown next stage rejects',lambda:rejects(lambda:ns['entry_ns'](0,'BENCH')))
e={'schema':'main-gap-setup-guard-envelope-v1','clock':'monotonic_ns','guard_call_returned':True,'start_ns':23,'return_ns':29,'elapsed_ns':6}
check('exact integer return envelope',lambda:yes(ns['envelope_ns'](e)==6))
for k,v in [('guard_call_returned',False),('elapsed_ns',True),('elapsed_ns',6.0),('start_ns',-1),('elapsed_ns',7),('return_ns',22)]:
 bad={**e,k:v};check('bad real envelope field '+k+' '+repr(v),lambda bad=bad:rejects(lambda:ns['envelope_ns'](bad)))
# Source-only reading of the now-existing BUILD receipt proves concrete data interfaces,
# not actual producer acceptance and not permission to call authenticate_build.
p=Path(c['baseline_work'])/'build/producer/receipt.json';auth=ns['load'](str(p))
check('actual installed package inventory is list, not guessed dictionary',lambda:yes(type(auth['installed_dependencies']['packages']) is list))
for name in values['PACKAGES']:
 ids=[u for u in auth['installed_dependencies']['packages'] if re.fullmatch(re.escape(name)+r'-[0-9].*',u)];assert len(ids)==1
 check('actual serialized '+name+' unit id/config closes',lambda name=name,unit=ids[0]:yes(ns['unit_id']((unit+'\n').encode(),name,auth)==unit))
 check('wrong named package id '+name+' rejects',lambda name=name:rejects(lambda:ns['unit_id'](b'wrong-0\n',name,auth)))
for raw in [b'',b'base',b'base\nbase\n',b'base  foo\n',b'base\r\n',b'\xff\n']:
 check('noncanonical package output '+repr(raw),lambda raw=raw:rejects(lambda:ns['unit_id'](raw,'base',auth)))
closure=ns['load'](c['closures']['path']);rows=closure['emlf_non_main_shared']+closure['private_primitive_modules'];producer=p.parent
check('source closure exactly90 shared plus4 host',lambda:yes(len(rows)==94 and len({x['module'] for x in rows})==94))
for row in rows:
 ns['verify_pin'](row)
 ownership=(auth['resolved_modules'] if row['module'] in auth['resolved_modules'] else auth['resolved_host_modules'])[row['module']]
 assert ownership['path']==row['path'] and ownership['sha256']==row['sha256']
 for suffix in ['.o','.hi']:
  rel='objects/'+row['module'].replace('.','/')+suffix
  assert ns['sha'](producer/rel)==auth['object_inputs'][rel]
check('actual serialized94 source/object/interface joins all close read-only',lambda:yes(True))
f=ns['import_flags'](auth,producer,ns['WORK']/'setup/stats-main')
check('actual import transform retains demand/O2 and strips source search',lambda:yes(all(x in f for x in ['-O2','-fpedantic-bottoms','-fno-state-hack']) and '-i'+str(producer/'objects') in f and not any(x.startswith('-i'+c['source']) for x in f)))
check('never borrows last Main',lambda:yes(all(x['module']!='Main' for x in rows)))
q={'format':1,'crate':'compiler-shapes/builtin','inferred_groups':1,'reused_groups':0,'groups':[{'cached':False,'id':'literal-protocol-test'}]}
check('literal one fresh fixture',lambda:ns['fresh_fixture'](q))
for k,v in [('inferred_groups',True),('reused_groups',1),('format',True),('crate','wrong'),('groups',[]),('groups',[{'cached':True,'id':'x'}])]:
 bad={**q,k:v};check('bad fixture field '+k+' '+repr(v),lambda bad=bad:rejects(lambda:ns['fresh_fixture'](bad)))
check('raw pack framing Unicode scalar lengths',lambda:yes(ns['pack'](['','λ雪🙂'])=='0:3:λ雪🙂'))
check('exact builtin owners accepted',lambda:ns['interface']('crate '+values['BUILTIN']+'\nmodule Prelude\nmodule MLF.Primitive\n',values['BUILTIN'],['Prelude','MLF.Primitive'],{}))
check('missing owner rejected',lambda:rejects(lambda:ns['interface']('crate '+values['BUILTIN']+'\nmodule Prelude\n',values['BUILTIN'],['Prelude','MLF.Primitive'],{})))
check('missing dependency rejected',lambda:rejects(lambda:ns['interface']('crate compiler-shapes/builtin\nmodule Fixture\n','compiler-shapes/builtin',['Fixture'],{values['BUILTIN']:'/literal/builtin.mlfci'})))
commands=ns['load'](c['commands']['path'])['rows']
check('fixed40 ledger exact13+11+16',lambda:yes(len(commands)==40 and {k:sum(x['kind']==k for x in commands) for k in ['setup_payload','qualification','runtime']}=={'setup_payload':13,'qualification':11,'runtime':16}))
check('six package ID reads are guarded payload commands',lambda:yes(len([x for x in commands if x['label'].startswith('global-unit-id-')])==6))
check('only one baseline controller launch per setup phase',lambda:yes(len([n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='run_guard'])==1))
check('exactly one bounded nested target call site',lambda:yes(len([n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='run_child'])==1))
check('payload setup contains no subprocess calls',lambda:yes(not any(isinstance(n,ast.Name) and n.id=='subprocess' for n in ast.walk(next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Setup')))))
check('no native setup helpers or full suite call sites',lambda:yes(not any(s in source for s in ['prepare.main(','.test_direct.main(',"'pkg-config'","'clang'",'mlf_runtime.c'])))
# Compare inherited small functions exactly, without loading old controller.
old=ast.parse(Path(c['baseline_controller']['path']).read_text());oldf={n.name:n for n in old.body if isinstance(n,ast.FunctionDef)}
for name in ['require','safe','sha','pin','verify_pin','load','save','module','source_check','entry_ns','row_sha','resource_snapshot','command']:
 check('mature '+name+' AST unchanged',lambda name=name:yes(ast.dump(N[name],include_attributes=False)==ast.dump(oldf[name],include_attributes=False)))
# Same original guard call, same held73/free0 peer probe text and lock-loop body.
call=lambda t,name:[ast.dump(n,include_attributes=False) for n in ast.walk(t) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr==name]
check('original run_guard call AST exact',lambda:yes(call(N['launch'],'run_guard')==call(oldf['launch'],'run_guard')))
lockloop=lambda t:next(n for n in ast.walk(t) if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='path')
check('original dual lock held/free loop AST exact',lambda:yes(ast.dump(lockloop(N['prepare']),include_attributes=False)==ast.dump(lockloop(oldf['prepare']),include_attributes=False)))
check('source package self identity single constant',lambda:yes(sum(isinstance(n,ast.Constant) and n.value=='main-gap-setup-v5-source' for n in ast.walk(tree))==1))
check('no source or work writes in extracted functions',lambda:yes(not ns['WORK'].exists()))

# The full genuine predecessor consumer is also exercised, but never by importing
# its module. Only the exact reviewed read/hash functions exist in this namespace.
bnames=['require','safe','sha','pin','verify_pin','load','envelope_ns','entry_ns','prior_build','row_sha','check_outer','inner_command','command']
for name in bnames:
 for node in ast.walk(oldf[name]):
  if isinstance(node,ast.Name):assert node.id not in {'subprocess','module','fcntl','save','exec','eval','compile'},(name,node.id)
  if isinstance(node,ast.Attribute):assert node.attr not in {'write_text','write_bytes','mkdir','rename','replace','unlink','rmdir','flock'}
bns={'Path':Path,'hashlib':hashlib,'json':json,'os':os,'PB':Path(c['baseline_controller']['path']).parent,
     'WORK':Path(c['baseline_work']),'R':R,'BUDGETS':{'BUILD':600,'CONTROLS':120},'MAX_NS':900*10**9}
exec(compile(ast.Module(body=[oldf[name] for name in bnames],type_ignores=[]),'<baseline-exact-readonly-functions>','exec'),bns)
import types
baseline=types.SimpleNamespace(**bns)
def readonly_baseline_module(path,name):
 assert Path(path)==Path(c['baseline_controller']['path']) and name=='pinned_main_baseline_consumer'
 return baseline
# No other module import, function or target can be dispatched through this stub.
pg=N['producer_gate'];historical=N['accepted_main_build'];modulecalls=[n for n in ast.walk(pg) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='module']
assert len(modulecalls)==1 and ast.unparse(modulecalls[0])=="module(verify_pin(c['baseline_controller']), 'pinned_main_baseline_consumer')"
for node in [*ast.walk(pg),*ast.walk(historical)]:
 if isinstance(node,ast.Name):assert node.id not in {'subprocess','fcntl','save','exec','eval','compile'}
 if isinstance(node,ast.Attribute):
  assert node.attr not in {'write_text','write_bytes','mkdir','rename','unlink','rmdir','flock'}
  if node.attr=='replace':assert isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Attribute) and node.value.func.attr=='read_bytes'
ns['module']=readonly_baseline_module
# CASES differs only by one literal UTF-8 encode call. Evaluate that one assignment
# after verifying exact AST equality to the already frozen baseline assignment.
case=next(n for n in tree.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='CASES')
oldcase=next(n for n in old.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='CASES')
assert ast.dump(case)==ast.dump(oldcase)
assert all(isinstance(n.func,ast.Attribute) and n.func.attr=='encode' and isinstance(n.func.value,ast.Constant) and n.func.value.value=='λ雪🙂'+chr(10) and not n.args and not n.keywords for n in ast.walk(case) if isinstance(n,ast.Call))
exec(compile(ast.Module(body=[case,historical,pg],type_ignores=[]),'<only-literal-cases-and-readonly-consumer>','exec'),ns)
reviews=json.loads(json.dumps(c['producer_reviews']))
check('genuine full serialized BUILD+CONTROLS prefix consumer closes',lambda:yes(ns['producer_gate'](json.loads(json.dumps(c)),reviews)['baseline_elapsed_not_carried']==222555214358))
check('historical consumer never reads current boot',lambda:yes('/proc/sys/kernel/random/boot_id' not in ast.get_source_segment(source,historical) and '/proc/sys/kernel/random/boot_id' not in ast.get_source_segment(source,pg)))
check('new SETUP epoch still verifies current boot',lambda:yes('/proc/sys/kernel/random/boot_id' in ast.get_source_segment(source,N['validate']) and '/proc/sys/kernel/random/boot_id' in ast.get_source_segment(source,N['resource_snapshot'])))
# Explicit rule models, not a physical reboot and not forged evidence:
# authenticated historical pin/cleanup checks remain outside this pure predicate.
epoch=ns['load'](str(Path(c['baseline_work'])/'coordination/CONTROLS-epoch.json'))
check('original historical epoch identity predicate',lambda:ns['completed_epoch_identity'](epoch,c['baseline_work'],'CONTROLS'))
other=copy.deepcopy(epoch);other['boot_id']='00000000-0000-0000-0000-000000000001'
check('pure historical other-boot identity model accepted, not actual reboot proof',lambda:ns['completed_epoch_identity'](other,c['baseline_work'],'CONTROLS'))
for k,v in [('boot_id',''),('boot_id',True),('phase','SETUP'),('created_for',str(ns['WORK']))]:
 bad={**epoch,k:v};check('pure historical bad identity '+k,lambda bad=bad:rejects(lambda:ns['completed_epoch_identity'](bad,c['baseline_work'],'CONTROLS')))
check('independent setup entry remains zero',lambda:yes(ns['entry_ns'](0,'SETUP')==0))
for phase in ['BUILD','CONTROLS']:
 bad=copy.deepcopy(reviews);bad[phase]['sha256']='0'*64
 check('wrong real '+phase+' identity rejects before module use',lambda bad=bad:rejects(lambda:ns['producer_gate'](c,bad)))
check('missing controls does not qualify',lambda:rejects(lambda:ns['producer_gate'](c,{'BUILD':reviews['BUILD']})))
result={'schema':'main-gap-setup-pure-source-checks-v1','complete':True,'checks':checks,'check_count':len(checks),
 'only_whitelisted_AST_read_hash_literal_functions_executed':allowed,'actual_build_receipt_read_for_schema_only':ns['pin'](p),
 'actual_main_producer_qualification_claimed':False,'genuine_baseline_reviews_read':reviews,'baseline_actual_elapsed_consumed_readonly':222555214358,'setup_elapsed_inherited':0,'target_or_helper_or_guard_or_lock_executed':False}
(D/'source-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
print(json.dumps({'passed':len(checks),'actual_target_executed':False}))
