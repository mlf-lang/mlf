"""Finite binder fusion candidate gate. No compiler benchmark or native work."""
import json,re,sys,subprocess
from bounded import *
from instrument import instrument
HERE=P(__file__).resolve().parent
root=P(sys.argv[1]).resolve();source=P(sys.argv[2]).resolve();art=root/'artifacts'
ci_only();sup=Supervisor(art,420,400,'build');env=safe_env(root,root/'ghc')
rec=dict(complete=False,errors=[],production=False,performance_claim=False)
try:
    need(subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()=='fc300bc9fdc389b585cbef0630fc8915d53e89c5','baseline head')
    need(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source),'baseline dirty')
    rec['resources']=resource_floor(root,8)
    installed=json.loads((art/'toolchain-inventory.json').read_text())
    need(inventory(root/'ghc',sup.check)==installed,'toolchain before')
    pins=json.loads((HERE/'source-pins.json').read_text())['rows']
    for opt in ['O0','O2']:
        dst=root/opt;dst.mkdir();(dst/'src').mkdir();(dst/'csrc').mkdir();(dst/'obj').mkdir();(dst/'stubs').mkdir()
        for row in pins:
            src=source/row['repo_path'];need(src.is_file() and not src.is_symlink(),'source type')
            need(src.stat().st_size==row['A']['bytes'] and sha(src,sup.check)==row['A']['sha256'],'source pin')
            rel=('src/'+row['module'].replace('.','/')+'.hs') if row['module'] else row['C_stage']
            out=dst/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(src.read_bytes())
        for name,rel in [('Main.hs','Main.hs')]:
            out=dst/'src'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes((HERE/name).read_bytes())
        candidate=dst/'src/Prototype/BinderFusion.hs';candidate.parent.mkdir(parents=True,exist_ok=True)
        candidate.write_text(instrument((dst/'src/Bootstrap/Graph.hs').read_text()).replace('module Bootstrap.Graph where','module Prototype.BinderFusion where',1))
        objects=[]
        for label,name in [('host','host.c'),('supervisor','mlf_process_supervisor.c')]:
            obj=dst/(label+'.o');sup.run(opt+'-c-'+label,['/usr/bin/gcc','-O2','-std=c11','-I'+str(dst/'csrc'),'-c',dst/'csrc'/name,'-o',obj],dst,30,env);objects.append(obj)
        cmd=[root/'ghc/bin/ghc','--make','-j1','-fforce-recomp','-XHaskell2010','-'+opt,'-fpedantic-bottoms','-fno-state-hack','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-rtsopts=ignoreAll','-i','-i'+str(dst/'src'),'-odir',dst/'obj','-hidir',dst/'obj','-stubdir',dst/'stubs']
        for pkg in ['base','array','bytestring','text','containers','directory']:cmd+=['-package',pkg]
        cmd += [dst/'src/Main.hs',*objects,'-o',dst/'finite']
        sup.run(opt+'-ghc',cmd,dst,150,env)
        results=art/opt;results.mkdir()
        log,_=sup.run(opt+'-finite',[dst/'finite'],results,15,env)
        need(P(str(log)+'.stdout').read_bytes()==b'PASS 33 binder fusion finite cases; no performance claim\n','marker')
        need(P(str(log)+'.stderr').read_bytes()==b'','fixture stderr')
        sup.run(opt+'-cycle-control',['/usr/bin/python3',HERE/'cycle_gate.py',dst/'finite',art/(opt+'-cycle.json')],dst,15,env)
    left={p.name:p.read_bytes() for p in (art/'O0').iterdir()};right={p.name:p.read_bytes() for p in (art/'O2').iterdir()}
    need(len(left)==132 and left==right,'O0/O2 complete sidecar equality')
    need(inventory(root/'ghc',sup.check)==installed,'toolchain after')
    rec.update(complete=True,sidecars=132,optimization_levels=['O0','O2'],full_sidecars_equal=True)
except BaseException as e:rec['errors'].append(repr(e))
finally:
    rec.update(sup.finish());rec['complete']=rec['complete'] and rec['cleanup'] and rec['within_whole'] and not rec['errors']
    write(art/'finite-receipt.json',rec);print(json.dumps(rec))
sys.exit(0 if rec['complete'] else 1)
