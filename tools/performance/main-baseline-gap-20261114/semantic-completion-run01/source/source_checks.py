"""Independent local AST/read/temporary-file checks. No target/helper entry point.
Whitelist extraction executes only declared read/hash or pure function bodies;
no original module import, guard, loader, subprocess, locks or real scope writes.
"""
from pathlib import Path
import ast,hashlib,json,os,re,stat,tempfile
R=Path('<EXPERIMENT_ROOT>');D=R/'main-gap-semantic-completion-v2-source';S=R/'main-gap-semantic-qualification-v1-source';E=R/'main-gap-setup-run04';Q=E/'semantic-completion-01';FAILED=E/'semantic-qualification-01'
checks=[]
def check(name,value):
 if not value:raise AssertionError(name)
 checks.append(name)
def extract(path,names,namespace):
 tree=ast.parse(path.read_bytes());nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 check('whitelist '+path.name,set(n.name for n in nodes)==set(names))
 for n in nodes:
  for x in ast.walk(n):
   if isinstance(x,(ast.Import,ast.ImportFrom)):raise AssertionError('function import forbidden')
 exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),namespace)
 return namespace
def j(p):return json.loads(Path(p).read_bytes())
c=j(D/'BINDINGS.json');ct=ast.parse((D/'controller.py').read_bytes());wt=ast.parse((D/'worker.py').read_bytes());it=ast.parse((D/'identity.py').read_bytes())
check('no actual new scope created',not Q.exists())
check('disabled',any(isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READY' for t in n.targets) and isinstance(n.value,ast.Constant) and n.value.value is False for n in ct.body))
check('real failure pin',c['failure_review']['sha256']=='331a7e79f7e47927faed87420c57c00935a65495273b74711f93376f4502b7a8')
check('fixed caps',c['outer_cap_seconds']==180 and c['cleanup_headroom_seconds']==5 and c['post_setup_prior_ns']==596647140326 and c['post_setup_total_ns']==1800*10**9)
ns={'Path':Path,'os':os,'stat':stat,'hashlib':hashlib,'json':json,'re':re,'R':R,'PB':D,'E':E,'WORK':Q,'FAILED':FAILED,'MAX_NS':180*10**9,'POST_SETUP_MAX_NS':1800*10**9}
read_names=['require','safe','sha','pin','verify_pin','load','row_sha','completed_epoch_identity','inventory','accepted_prefix','verify_setup_scope','entry_ns']
extract(D/'controller.py',read_names,ns)
previous=ns['accepted_prefix'](c);old=ns['verify_setup_scope'](c,hash_files=True)
check('actual serialized failed prefix',len(previous['worker']['commands'])==84 and len(previous['pins'])==5925 and previous['review']['elapsed_ns']==596647140326)
check('exact old full scope union',len(old)==379+5925 and len({p['path'] for p in old})==len(old))
check('real prefix full cap fits',ns['entry_ns'](596647140326,'COMPLETION')==596647140326)
for value in [0,True,-1,596647140325,600*10**9,None,596647140326.0]:
 try:ns['entry_ns'](value,'COMPLETION')
 except (RuntimeError,TypeError):checks.append('reject bad prior '+repr(value))
 else:raise AssertionError('bad prior accepted')
pns={'json':json,'re':re};extract(S/'semantic_parsers.py',['need','resolved_commands'],pns)
setup=j(c['setup_worker']['path']);resolved=pns['resolved_commands'](j(c['plan_commands']['path']),str(E),setup);missing=j(previous['review']['remaining_original_commands']['path'])
check('genuine exact seven remaining commands',missing==[dict(x,executed=False) for x in resolved[84:]])
check('all old 84 exact actual argv',all(a['label']==b['label'] and a['guard']['command']==b['argv_template'] for a,b in zip(previous['worker']['commands'],resolved[:84])))
rows=resolved[:5]+resolved[84:]
check('12 count and only two targets',len(rows)==12 and [x['kind'] for x in rows]==['runtime']*5+['stats_compile','ghc_typed']+['runtime']*5)
check('same source argv active scratch',all(str(E/'active/cells/foundation14') in ' '.join(r['argv_template']) for r in rows[5:7]))
check('unchanged required2 RTS',sum('report_sink' in x for x in rows)==2)
check('only current cell foundation',not any('source-smoke' in ' '.join(x['argv_template']) for x in rows))
# Pure ownership/hash identity regression using only our temporary files.
ins={'Path':Path,'os':os,'stat':stat,'hashlib':hashlib};extract(D/'identity.py',['need','shape','attest','capture','check','finish','extend','runtime_shape','runtime_rows','runtime_check'],ins)
def fpin(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def reject(name,fn):
 try:fn()
 except (RuntimeError,FileNotFoundError,ValueError):checks.append(name)
 else:raise AssertionError(name)
with tempfile.TemporaryDirectory(prefix='completion-pure-') as t:
 p=Path(t)/'old';p.write_bytes(b'AAAA');snap=ins['capture']([fpin(p)]);ins['check'](snap);ins['finish'](snap);checks.append('stable boundary/light/exit')
 p.write_bytes(b'BBBB');reject('same-size content write detected metadata',lambda:ins['check'](snap));reject('changed bytes fail end hash',lambda:ins['finish'](snap))
 p.write_bytes(b'AAAA');reject('restore bytes cannot restore original ctime gate',lambda:ins['check'](snap))
 snap=ins['capture']([fpin(p)]);os.chmod(p,0o600 if p.stat().st_mode&0o077 else 0o644);reject('mode change',lambda:ins['check'](snap))
 snap=ins['capture']([fpin(p)]);q=Path(t)/'replacement';q.write_bytes(b'AAAA');q.replace(p);reject('inode replacement',lambda:ins['check'](snap))
 p.unlink();p.symlink_to(Path(t)/'none');reject('symlink',lambda:ins['shape'](p));p.unlink();p.write_bytes(b'AAAA');q=Path(t)/'alias';os.link(p,q)
 reject('new hardlink',lambda:ins['extend']({},[fpin(p)]));q.unlink();snap=ins['capture']([fpin(p)]);p.unlink();reject('missing immutable input',lambda:ins['check'](snap))
 os.mkfifo(p);reject('FIFO',lambda:ins['shape'](p));p.unlink();p.mkdir();reject('directory not file',lambda:ins['shape'](p))
 p.rmdir();p.write_bytes(b'AAAA');link=Path(t)/'link';link.symlink_to(p);reject('symlink ancestor',lambda:ins['shape'](link))
 st=p.stat();value={'path':str(p),'resolved':str(p),'links':[],'device':st.st_dev,'inode':st.st_ino,'bytes':st.st_size}
 check('runtime shape same path',ins['runtime_shape'](value)==p)
 for k,bad in [('inode',st.st_ino+1),('bytes',5),('resolved',str(link)),('links',[{'path':'wrong'}])]:
  v=dict(value);v[k]=bad;reject('runtime wrong '+k,lambda v=v:ins['runtime_shape'](v))
# Literal policy and phase safety (source tests, not execution mocks).
worker=(D/'worker.py').read_text();controller=(D/'controller.py').read_text()
check('entry and exit full SHA',"self.full_recheck('entry')" in worker and "self.full_recheck('exit')" in worker)
check('light avoids full hash inventory loop','for item in self.inputs+self.outputs' not in worker)
check('original raw after B unchanged',"self.raw(ref)==old" in worker and "self.oracle.compare_cell(old,actual" in worker)
check('constant original source scratch',"str(cells/cell)" in worker and "self.new_cell(cell,spec)" in worker)
check('new claims identity',"('claims',{'COMPLETION.json'})" in controller)
check('original guard bytes same',(Path(c['guard']['path']).read_bytes() and hashlib.sha256(Path(c['guard']['path']).read_bytes()).hexdigest())=='53a5b322fe8ed9e1a527dda0596215ffc81322b43b1864442827c9056c313d0e')
check('no prefix repeated target loop',"for cell in cells:" not in worker)
check('original source package untouched',hashlib.sha256((S/'MANIFEST.json').read_bytes()).hexdigest()=='0e1537a67c1ebdc3405c104d7c99771f8853ae9a459843f497cb23cd430371b8')
report={'schema':'main-gap-completion-source-checks-v1','complete':True,'checks':checks,'count':len(checks),'actual_prefix_read_only_verified':True,'actual_prefix_elapsed_ns':596647140326,'no_module_top_level_target_or_helper_execution':True,'no_actual_scope_created':not Q.exists(),'temporary_file_only_tests':True,'actual_stage_passed':False}
(D/'source-check-report.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n');print(json.dumps({'checks':len(checks),'actual_prefix_ns':596647140326}))
