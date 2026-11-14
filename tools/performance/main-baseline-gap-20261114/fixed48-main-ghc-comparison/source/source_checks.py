"""Source/read-only real-consumer and isolated pure budget checks.
No controller/module entry, compiler, guard, loader, repo script or lock is run.
"""
from pathlib import Path
import ast,hashlib,json,os,re,stat,types,tempfile
R=Path('<EXPERIMENT_ROOT>');D=R/'main-gap-sampling-v1-source';E=R/'main-gap-setup-run04'
checks=[]
def check(name,value):
 if not value:raise AssertionError(name)
 checks.append(name)
def reject(name,fn):
 try:fn()
 except (RuntimeError,ValueError,TypeError,KeyError,FileNotFoundError):checks.append(name)
 else:raise AssertionError(name)
def pin(p):
 b=Path(p).read_bytes();return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def extract(path,names,env):
 tree=ast.parse(Path(path).read_bytes());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 check('exact whitelist '+Path(path).name,set(n.name for n in nodes)==set(names))
 for n in nodes:
  check('no function import '+n.name,not any(isinstance(x,(ast.Import,ast.ImportFrom)) for x in ast.walk(n)))
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),env);return env
c=json.loads((D/'BINDINGS.json').read_bytes());r=json.loads(Path(c['combined_qualification_review']['path']).read_bytes())
check('actual combined report exact',pin(c['combined_qualification_review']['path'])==c['combined_qualification_review'] and c['combined_qualification_review']['sha256']=='9293db948fe9393f28f6153ee514eb16e1c1ee3c8b1ec0fe15ffa9d762232a41')
check('both scopes absent',all(not (E/('sampling-%02d'%i)).exists() for i in [1,2]))
constants={}
for n in ast.parse((D/'controller.py').read_bytes()).body:
 if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in {'READY','CONFIG_SHA'} for x in n.targets):constants[n.targets[0].id]=ast.literal_eval(n.value)
check('READY false',constants['READY'] is False);check('config exact',constants['CONFIG_SHA']==pin(D/'BINDINGS.json')['sha256'])
def pure_module(path,name):
 path=Path(path)
 if path==Path(c['semantic_parsers']['path']):names={'need','json_object','fresh_queries','ghc_compiling','resolved_commands'}
 elif path==D/'sampling_contract.py':names={'require','prefix','poststage','resolved_rows'}
 else:raise AssertionError('test forbidden module load '+str(path))
 env=extract(path,names,{'json':json,'re':re});return types.SimpleNamespace(**{k:env[k] for k in names})
ns={'Path':Path,'os':os,'stat':stat,'hashlib':hashlib,'json':json,'re':re,'R':R,'PB':D,'E':E,'WORK':E/'sampling-01','FAILED':E/'semantic-qualification-01','COMPLETION':E/'semantic-completion-01','BLOCK':1,'PHASE':'SAMPLE1','MAX_NS':600*10**9,'QUALIFICATION_NS':717873335365,'SAMPLING_MAX_NS':1200*10**9,'POST_SETUP_MAX_NS':1800*10**9,'CONFIG_SHA':constants['CONFIG_SHA'],'module':pure_module}
readers={'require','safe','sha','pin','verify_pin','load','row_sha','completed_epoch_identity','inventory','accepted_setup','accepted_prefix','accepted_qualification','accepted_prior','verify_preserved_scope','entry_ns','envelope_ns','configuration','verify_cell_oracle','resolved_sampling_rows'}
extract(D/'controller.py',readers,ns);actualc=ns['configuration']();accepted=ns['accepted_qualification'](actualc);prior=ns['accepted_prior'](actualc,c['combined_qualification_review'],accepted);scope=ns['verify_preserved_scope'](actualc,accepted,prior,hash_files=True)
check('true combined actual consumer12',accepted['combined_qualification_accepted'] and len(accepted['cells'])==12)
check('actual complete preserved7868 scope',len(scope)==7868 and len(accepted['scope_directories'])==490)
check('real prior ns not reset',prior['used_ns']==717873335365 and prior['sampling_prior_ns']==0)
check('one complete cap fits',ns['entry_ns'](prior['used_ns'],'SAMPLE1')==717873335365)
rows1=ns['resolved_sampling_rows'](actualc,accepted);ns.update(BLOCK=2,PHASE='SAMPLE2',WORK=E/'sampling-02');c2=ns['configuration']();rows2=ns['resolved_sampling_rows'](c2,accepted)
rows=rows1+rows2;legs=[x for x in rows if x['kind']=='measured_leg'];check('exact64child48sample',len(rows)==64 and len(legs)==48)
check('exact48 global sequence',[x['leg_ordinal'] for x in legs]==list(range(1,49)))
check('exact MGGM twelve times',all([r['lane'] for r in legs[i:i+4]]==['M','G','G','M'] for i in range(0,48,4)))
check('actual qualified argv for every sample',all(x['argv_template']==accepted['cells'][x['cell']]['stats_argv' if x['lane']=='M' else 'ghc_argv'] for x in legs))
check('no build show formulas',all(x['kind'] in ('runtime','measured_leg') and '--show-interface' not in x['argv_template'] and '--eval' not in x['argv_template'] for x in rows))
check('every measured leg has RTS',all(x.get('report_sink') for x in legs))
check('only4 roles eight perblock',[[x['label'] for x in rs if x['kind']=='runtime'] for rs in [rows1,rows2]]==[['runtime-'+r+'-'+w for w in ['before','after'] for r in ['python','shell','ghc','stats-emlf']]]*2)
check('no old Q writes in actual argv',not any(str(E/'semantic-qualification-01') in a or str(E/'semantic-completion-01') in a for x in rows for a in x['argv_template']))
for name,w in accepted['cells'].items():ns['verify_cell_oracle'](w,accepted)
check('all12 actual immutable witnesses',True)
# Ensure record hashes reject mutation without recapturing current witnesses.
w=next(iter(accepted['cells'].values()));saved=w['original_active_path'];w['original_active_path']=saved+'/elsewhere';reject('reject changed active oracle',lambda:ns['verify_cell_oracle'](w,accepted));w['original_active_path']=saved
contract=pure_module(D/'sampling_contract.py','pure_budget');failure=596647140326;completion=121226195039
check('actual budget first prefix',contract.prefix(1,failure,completion)['post_setup_prior_ns']==717873335365)
check('synthetic second prefix uses actual qualification',contract.prefix(2,failure,completion,100*10**9)['post_setup_prior_ns']==817873335365)
for label,fn in [('failed reset',lambda:contract.prefix(1,0,completion)),('bool failed',lambda:contract.prefix(1,True,completion)),('missing completion',lambda:contract.prefix(1,failure,None)),('completion above cap',lambda:contract.prefix(1,failure,180*10**9+1)),('missing block1',lambda:contract.prefix(2,failure,completion)),('bool block1',lambda:contract.prefix(2,failure,completion,True)),('negative prior',lambda:contract.prefix(2,failure,completion,-1)),('second whole cap does not fit',lambda:contract.prefix(2,failure,completion,500*10**9)),('bad block',lambda:contract.prefix(3,failure,completion)),('post actual above600',lambda:contract.poststage(contract.prefix(1,failure,completion),600*10**9+1))]:reject('pure reject '+label,fn)
# Runtime stage must be unbound for SAMPLE2 until real report exists, not a fake positive.
reject('no fake SAMPLE2 prior report',lambda:ns['accepted_prior'](c2,c['combined_qualification_review'],accepted))
worker=(D/'sampling_worker.py').read_text();controller=(D/'controller.py').read_text()
check('exact C1 original binding pin used',"claim=deadline['claim']" in worker and 'all_inputs += [claim]' in worker and "C.pin(self.Q/'claims'" not in worker)
check('entry and exit full SHA',"self.full_recheck('entry')" in worker and "self.full_recheck('exit')" in worker)
check('no perleg static fullhash loop','for item in self.inputs+self.outputs' not in worker)
check('strict same binary fullraw',"C.require(raw==frozen,'same binary/tool full raw names and bytes, no exceptions')" in worker)
check('whole parent not broadR',"bounded_root=self.E" in worker and 'bounded_root=E' in controller)
check('existing cells not recreated',"C.safe(active_root/'cells',existing=True)" in worker and "active_root/'cells').mkdir" not in worker)
check('positive immutable worker roots',"WORKER_OUTPUT_DIRS = ('commands','legs')" in controller)
check('new claim and epoch exact phase',"WORK/'claims'/f'{PHASE}.json'" in controller and "ep['boot_id']==Path('/proc/sys/kernel/random/boot_id')" in controller)
check('no native',c['sampling_runner_included'] and not any('native' in a for x in rows for a in x['argv_template']))
report={'schema':'main-gap-sampling-source-checks-v1','complete':True,'count':len(checks),'checks':checks,'actual_combined_review':c['combined_qualification_review'],'actual_preserved_scope_files':7868,'actual_qualification_ns':717873335365,'block2_actual_review_not_created_or_faked':True,'pure_hypotheticals_are_not_results':True,'no_original_module_entry_or_helper_guard_loader_target_or_lock_execution':True,'no_sampling_scope_created':True}
(D/'source-check-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps({'checks':len(checks),'actual_combined_cells':12,'sampling_commands':64,'samples':48}))
(D/'RESOLVED-COMMANDS.json').write_text(json.dumps({'schema':'sampling-real-qualified-argv-v1','actual_qualification':c['combined_qualification_review'],'executed':False,'rows':rows},sort_keys=True,indent=2)+'\n')
