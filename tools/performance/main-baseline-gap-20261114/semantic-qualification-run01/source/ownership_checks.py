"""Exact new ownership functions over genuine read-only inventory and plain temp trees.
No target/controller entry/guard/loader/locks are executed.
"""
from pathlib import Path
import ast,hashlib,json,os,stat,tempfile
D=Path(__file__).resolve().parent;R=D.parent;t=ast.parse((D/'controller.py').read_text())
names={'require','safe','sha','pin','verify_pin','load','tree_pins','directory_paths','verify_setup_scope','live_scope_structure'}
nodes=[n for n in t.body if isinstance(n,ast.FunctionDef) and n.name in names];assert {n.name for n in nodes}==names
for n in ast.walk(ast.Module(body=nodes,type_ignores=[])):
    if isinstance(n,ast.Name):assert n.id not in {'subprocess','fcntl','module','sys','time','eval','exec','__import__'}
ns={'Path':Path,'hashlib':hashlib,'json':json,'os':os,'stat':stat,'E':R/'main-gap-setup-run04','WORK':R/'main-gap-setup-run04/semantic-qualification-01',
    'WORKER_OUTPUT_DIRS':('commands','reference','reference-contracts','stats','ghc')}
exec(compile(ast.Module(body=nodes,type_ignores=[]),'<audited-read-only-ownership-functions>','exec'),ns)
checks=[]
def yes(v):assert v
def case(name,fn):fn();checks.append({'name':name,'passed':True})
def bad(fn):
    try:fn()
    except (RuntimeError,FileNotFoundError,ValueError):return
    raise AssertionError('negative accepted')
c=json.loads((D/'BINDINGS.json').read_bytes())
baseline=ns['verify_setup_scope'](c,hash_files=True)
case('actual entire completed SETUP379files109dirs unchanged; no semantic scope',lambda:yes(len(baseline['files'])==379 and len(baseline['directories'])==109 and not ns['WORK'].exists()))
with tempfile.TemporaryDirectory(prefix='pure-ownership-',dir=D) as tmp:
    tmp=Path(tmp);root=tmp/'new';root.mkdir();(root/'regular').write_bytes(b'x')
    case('fresh unique regular file accepted',lambda:yes(len(ns['tree_pins'](root))==1))
    os.link(root/'regular',root/'alias');case('new hardlink alias rejected',lambda:bad(lambda:ns['tree_pins'](root)));(root/'alias').unlink()
    outside=tmp/'outside';outside.mkdir();(root/'link').symlink_to(outside,target_is_directory=True)
    case('new directory symlink rejected',lambda:bad(lambda:ns['tree_pins'](root)));(root/'link').unlink()
    os.mkfifo(root/'fifo');case('FIFO never silently omitted',lambda:bad(lambda:ns['tree_pins'](root)));(root/'fifo').unlink()
    (root/'file-link').symlink_to(root/'regular');case('new file symlink rejected',lambda:bad(lambda:ns['tree_pins'](root)));(root/'file-link').unlink()
    # Model the whole old parent inventory plus only the approved new child.
    E=tmp/'E';E.mkdir();(E/'active').mkdir();(E/'setup').mkdir();(E/'setup/immutable').write_bytes(b'old');Q=E/'semantic-qualification-01'
    inventory={'schema':'main-gap-completed-setup-scope-inventory-v1','root':str(E),'allowed_new_root':str(Q),'baseline_active_entries':[],
        'directories':['active','setup'],'files':[{**ns['pin'](E/'setup/immutable'),'relative':'setup/immutable'}]}
    inv=tmp/'old.json';inv.write_text(json.dumps(inventory));cfg={'setup_scope_inventory':ns['pin'](inv)}
    ns['E']=E;ns['WORK']=Q
    case('exact old scope accepts before child',lambda:ns['verify_setup_scope'](cfg,True))
    Q.mkdir();(Q/'tmp').mkdir();(Q/'controller.py').write_bytes(b'not executable test data')
    case('single appended child root allowed',lambda:ns['verify_setup_scope'](cfg,True))
    case('empty exact active/child layout accepted',lambda:ns['live_scope_structure']())
    for p in [E/'junk',E/'setup/junk',E/'active/junk']:
        p.write_bytes(b'no');case('unexpected old-parent file '+str(p.relative_to(E)),lambda:bad(lambda:ns['verify_setup_scope'](cfg,True)));p.unlink()
    (E/'setup/newdir').mkdir();case('unknown old-parent empty directory rejected',lambda:bad(lambda:ns['verify_setup_scope'](cfg)));(E/'setup/newdir').rmdir()
    (E/'setup/immutable').write_bytes(b'new');case('old file bytes changed rejected',lambda:bad(lambda:ns['verify_setup_scope'](cfg,True)));(E/'setup/immutable').write_bytes(b'old')
    (E/'active').rmdir();(E/'active').symlink_to(outside,target_is_directory=True)
    case('active ancestor symlink rejected before creation',lambda:bad(lambda:ns['verify_setup_scope'](cfg)))
    case('safe forbids writing through active ancestor',lambda:bad(lambda:ns['safe'](E/'active/cells/test/crate.spec')))
    (E/'active').unlink();(E/'active').mkdir();(E/'active/cells').mkdir();(E/'active/cells/cell').mkdir()
    case('only declared live cell allowed',lambda:ns['live_scope_structure']('cell'))
    case('stale active cell rejected at empty boundary',lambda:bad(lambda:ns['live_scope_structure']()))
    (E/'active/cells/other').mkdir();case('second simultaneous cell rejected',lambda:bad(lambda:ns['live_scope_structure']('cell')));(E/'active/cells/other').rmdir()
    (E/'active/cells/cell').rmdir();(E/'active/mlf.stats').write_bytes(b'unarchived')
    case('unarchived shared RTS sink rejected',lambda:bad(lambda:ns['live_scope_structure']()));(E/'active/mlf.stats').unlink()
    (Q/'unexpected').write_bytes(b'x');case('unknown child-root file rejected',lambda:bad(lambda:ns['live_scope_structure']()));(Q/'unexpected').unlink()
    (Q/'tmp/stale').write_bytes(b'x');case('completed-child leftover tmp rejected',lambda:bad(lambda:ns['live_scope_structure']()));(Q/'tmp/stale').unlink()
    outer=Q/'outer';outer.mkdir();(outer/'reports').mkdir()
    for name in ['stdout','stderr','guard.json','guard-config.json']:(outer/name).write_bytes(b'live')
    (Q/'build.log').write_bytes(b'live');(Q/'bounded-receipt.json').write_bytes(b'live')
    case('exact live lifecycle owner files accepted independently of worker bytes',lambda:ns['live_scope_structure']())
    (Q/'bounded-receipt.json.tmp').write_bytes(b'transient')
    case('live watchdog atomic temporary allowed',lambda:ns['live_scope_structure']())
    case('final watchdog temporary rejected',lambda:bad(lambda:ns['live_scope_structure'](final=True)));(Q/'bounded-receipt.json.tmp').unlink()
    (outer/'junk').write_bytes(b'x');case('unknown outer lifecycle file rejected',lambda:bad(lambda:ns['live_scope_structure']()));(outer/'junk').unlink()
    (outer/'stdout').write_bytes(b'changed real live bytes');case('live log content is not premature worker immutable oracle',lambda:ns['live_scope_structure']())
    case('final exact typed lifecycle inventory accepted',lambda:ns['live_scope_structure'](final=True))
result={'schema':'main-gap-semantic-ownership-pure-checks-v1','complete':True,'checks':checks,'count':len(checks),
    'actual_scope_read_only':True,'temporary_plain_files_only':True,'guard_loader_lock_target_executed':False,'source_gate_passed':None}
(D/'ownership-checks.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print('ownership pure checks',len(checks))
