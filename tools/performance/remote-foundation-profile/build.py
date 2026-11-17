"""Fresh exact-source A/C producers on one isolated GitHub runner. No timing claim."""
import argparse,json,os,re,shutil,subprocess,sys
from bounded import *
HERE=P(__file__).resolve().parent
REFS={'A':'fc300bc9fdc389b585cbef0630fc8915d53e89c5'}
def main():
    ci_only();p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--a-source',required=True);a=p.parse_args()
    root=P(a.root).resolve();art=root/'artifacts';build=root/'producers';need(not build.exists(),'fresh producer directory');build.mkdir()
    sup=Supervisor(art,900,870,'build');env=safe_env(root,root/'ghc');rec={'complete':False,'errors':[],'ci_identity':ci_identity(),'sources':{},'builds':{},'native':False}
    pins=json.loads((HERE/'source-pins.json').read_text())['rows'];homes=[x for x in pins if x['module']];need(len(homes)==95 and len(pins)==111,'exact closure size')
    try:
        rec['resources']=resource_floor(root,8)
        installed=json.loads((art/'toolchain-inventory.json').read_text())
        need(inventory(root/'ghc',sup.check)==installed,'installed GHC identity before build')
        rec['gcc_before']=identity(P('/usr/bin/gcc'),sup.check)
        sup.run('gcc-version',['/usr/bin/gcc','--version'],root,5,env)
        for side,source in [('A',P(a.a_source).resolve())]:
            head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip();need(head==REFS[side],'source checkout ref')
            need(not subprocess.check_output(['git','status','--porcelain','--untracked-files=no'],cwd=source),'dirty source checkout')
            dst=build/side;dst.mkdir();(dst/'src').mkdir();(dst/'csrc').mkdir();(dst/'obj').mkdir();(dst/'stubs').mkdir();(dst/'bin').mkdir()
            rows=[]
            for row in pins:
                sup.check();src=source/row['repo_path'];expected=row[side];need(src.is_file()and not src.is_symlink(),'source file type')
                need(src.stat().st_size==expected['bytes']and sha(src,sup.check)==expected['sha256'],'source pin '+row['repo_path'])
                rel=('src/'+row['module'].replace('.','/')+'.hs')if row['module']else row['C_stage']
                out=dst/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(src.read_bytes())
                rows.append({'repo_path':row['repo_path'],'stage':str(out),'module':row['module'],'sha256':sha(out,sup.check),'bytes':out.stat().st_size})
            write(art/('source-'+side+'.json'),dict(ref=head,files=rows));rec['sources'][side]=head
            objects=[]
            for label,name in [('host','host.c'),('supervisor','mlf_process_supervisor.c')]:
                obj=dst/(label+'.o');sup.run(side+'-c-'+label,['/usr/bin/gcc','-O2','-std=c11','-I'+str(dst/'csrc'),'-c',dst/'csrc'/name,'-o',obj],dst,30,env);objects.append(obj)
            cmd=[root/'ghc/bin/ghc','--make','-j1','-fforce-recomp','-XHaskell2010','-O2','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-rtsopts=ignoreAll','-i','-i'+str(dst/'src'),'-odir',dst/'obj','-hidir',dst/'obj','-stubdir',dst/'stubs']
            for package in ['base','array','bytestring','text','containers','directory']:cmd+=['-package',package]
            cmd += [dst/'src/Main.hs',*objects,'-o',dst/'bin/emlf']
            log,elapsed=sup.run(side+'-ghc',cmd,dst,420,env)
            actual=re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)',P(str(log)+'.stdout').read_text(),re.M)
            need(len(actual)==95 and set(actual)=={r['module']for r in homes},'actual home-module closure')
            liblog,_=sup.run(side+'-ldd',['/usr/bin/ldd',dst/'bin/emlf'],dst,5,env)
            libraries=[]
            for line in P(str(liblog)+'.stdout').read_text().splitlines():
                need('not found'not in line,'missing runtime library')
                m=re.search(r'(?:=>\s*)?(/\S+)\s+\(',line)
                if m:libraries.append({'reported_path':m.group(1),**identity(P(m.group(1)),sup.check)})
            need(libraries,'runtime library capture')
            rec['builds'][side]={'producer':identity(dst/'bin/emlf',sup.check),'runtime':libraries,'home_modules':actual,'build_wall_s':elapsed}
        for side in REFS:
            for row in pins:
                rel=('src/'+row['module'].replace('.','/')+'.hs')if row['module']else row['C_stage']
                need(sha(build/side/rel,sup.check)==row[side]['sha256'],'staged source changed')
        need(inventory(root/'ghc',sup.check)==installed,'installed GHC identity after build')
        need(identity(P('/usr/bin/gcc'),sup.check)==rec['gcc_before'],'GCC changed during build')
        rec['ghc_full_inventory_pre_post_equal']=True
        rec['gcc_after']=identity(P('/usr/bin/gcc'),sup.check)
        rec['complete']=True
    except BaseException as e:rec['errors'].append(repr(e))
    finally:
        rec.update(sup.finish());rec['complete']=rec['complete']and rec['cleanup']and rec['within_whole']and not rec['errors'];write(art/'build-receipt.json',rec)
    return 0 if rec['complete']else 1
if __name__=='__main__':sys.exit(main())

