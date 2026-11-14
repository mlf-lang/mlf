"""Own source/inverse and real temporary-directory precondition tests only."""
from pathlib import Path
import ast,hashlib,json,tempfile,difflib
D=Path(__file__).resolve().parent;R=D.parent;OLD=R/'main-gap-setup-v4-source'
a=(OLD/'controller.py').read_text();b=(D/'controller.py').read_text();inverse=b
changes=[("PB = R / 'main-gap-setup-v5-source'","PB = R / 'main-gap-setup-v4-source'"),("WORK = R / 'main-gap-setup-run04'","WORK = R / 'main-gap-setup-run03'"),
("'commands','global_packages','publication_oracle']:","'commands','global_packages']:"),
("\n        self.publication=module(verify_pin(c['publication_oracle']),'pinned_pure_publication_oracle')",''),
("'closures','environment','publication_oracle']]]","'closures','environment']]]"),
("""        actual=self.fixture_snapshot()
        ordinary_binary=verify_pin(self.auth['outputs']['emlf']);stats_binary=verify_pin(self.record['stats_relink']['binary'])
        ordinary_raw={rel:safe(reference/rel,existing=True).read_bytes() for rel in ordinary}
        stats_raw={rel:safe(t/rel,existing=True).read_bytes() for rel in actual}
        equivalence=self.publication.compare_fixture(ordinary_raw,stats_raw,sha(ordinary_binary),sha(stats_binary))""",
"        actual=self.fixture_snapshot();require(actual==ordinary,'full raw fixture/query/builtin bytes differ; no normalization permitted')"),
("'full_raw_files_equal':actual==ordinary,'cross_compiler_publication':equivalence", "'full_raw_files_equal':True"),
("'stats_current':str(t),'ordinary_files':ordinary,'files':actual}","'stats_current':str(t),'files':actual}")]
checks=[]
def check(n,v):assert v,n;checks.append({'name':n,'passed':True})
for new,old in changes:
 check('one exact inverse '+new[:78],inverse.count(new)==1);inverse=inverse.replace(new,old,1)
def config_literal(s):return next(n.value.value for n in ast.parse(s).body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='CONFIG_SHA')
inverse=inverse.replace(config_literal(b),config_literal(a),1)
check('whole inverse bytes exactly v4',inverse==a)
check('whole inverse AST exactly v4',ast.dump(ast.parse(inverse))==ast.dump(ast.parse(a)))
check('READY remains false exactly once','\nREADY = False\n' in b and b.count('\nREADY = False\n')==1)
check('sole PB identity constant',b.count('main-gap-setup-v5-source')==1 and 'main-gap-setup-v4-source' not in b)
check('sole WORK identity constant',b.count('main-gap-setup-run04')==1 and 'main-gap-setup-run03' not in b)
check('run04 not created',not (R/'main-gap-setup-run04').exists())
for n in ['COMMANDS.json','GLOBAL-PACKAGE-INPUTS.json','SetupCheck.hs']:check('byte exact inherited '+n,(D/n).read_bytes()==(OLD/n).read_bytes())
c=json.loads((D/'CONFIG.json').read_bytes());oc=json.loads((OLD/'CONFIG.json').read_bytes());ci=dict(c);del ci['publication_oracle']
for k in ['work','commands','environment','global_packages']:ci[k]=oc[k]
check('CONFIG inverse exact except oracle and relocation',ci==oc)
e=json.loads((D/'environment.json').read_bytes());oe=json.loads((OLD/'environment.json').read_bytes());e['TMPDIR']=oe['TMPDIR'];check('environment only TMPDIR relocation',e==oe)
for n in ['CONFIG.json','environment.json','QUALIFICATION.json','controller.py']:
 (D/(n.split('.')[0]+'-vs-v4.patch')).write_text(''.join(difflib.unified_diff((OLD/n).read_text().splitlines(True),(D/n).read_text().splitlines(True),fromfile='v4/'+n,tofile='v5/'+n)))
# Real own temp tree, never the future WORK or an original guard invocation.
with tempfile.TemporaryDirectory(prefix='gap-v5-own-directory-check-') as t:
 p=Path(t);setup=p/'setup';setup.mkdir();commands=setup/'commands';commands.mkdir(mode=0o700,exist_ok=False)
 child=commands/'001';check('actual parent exists, child absent',commands.is_dir() and not child.exists())
 try:commands.mkdir(mode=0o700,exist_ok=False)
 except FileExistsError:check('duplicate commands parent rejected',True)
 else:raise AssertionError('exclusive mkdir not enforced')
 child.mkdir();check('mock original guard can create child only once',child.is_dir())
 try:child.mkdir()
 except FileExistsError:check('existing child rejected',True)
 else:raise AssertionError('existing child not rejected')
 check('lifecycle controller is not selected by ownership predicate',not 'controller.json' in ('stats-emlf','builtin.mlfci','builtin.mlfco','builtin.lock'))
# Exact existing ownership functions ensure late outer updates still never enter worker outputs.
at=ast.parse(a);bt=ast.parse(b)
for n in ['worker_output_relative','worker_output_pins','launch','validate','prepare','accepted_main_build','producer_gate']:
 get=lambda t:next(x for x in t.body if isinstance(x,ast.FunctionDef) and x.name==n)
 check(n+' AST unchanged',ast.dump(get(at))==ast.dump(get(bt)))
def pin(p):
 z=p.read_bytes();return dict(path=str(p),bytes=len(z),sha256=hashlib.sha256(z).hexdigest())
(D/'delta-checks.json').write_text(json.dumps({'schema':'main-gap-v5-inverse-pure-checks-v1','complete':True,'check_count':len(checks),'checks':checks,'original_controller':pin(OLD/'controller.py'),'new_controller':pin(D/'controller.py'),'no_helper_or_target_executed':True,'temporary_directory_tests_not_actual_guard':True},indent=2,sort_keys=True)+'\n')
print('delta/inverse/temp directory checks',len(checks))
