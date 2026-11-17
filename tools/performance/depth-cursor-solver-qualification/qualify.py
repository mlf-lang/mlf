"""Finite real Solver transaction semantics, never a performance benchmark."""
import argparse,json,os,pathlib,re,shutil,sys
from bounded import *
HERE=P(__file__).resolve().parent
MODULES=None
def check_sources(rows,check):
    actual={str(p.relative_to(HERE))for root in ['src','csrc']for p in(HERE/root).rglob('*')if not p.is_dir()}
    need(actual=={r['path']for r in rows},'source closure file set')
    for r in rows:
        p=HERE/r['path'];need(p.is_file()and not p.is_symlink()and p.stat().st_size==r['bytes']and sha(p,check)==r['sha256'],'source pin '+r['path'])
def focused(out,contract,log):
    need({p.name for p in out.iterdir()}==set(contract['files']),'exact32 files')
    values={}
    for n in contract['files']:
        p=out/n;need(p.is_file()and not p.is_symlink()and p.stat().st_size<=contract['per_file_max_bytes'],'focused file bound');values[n]=p.read_bytes()
    need(sum(map(len,values.values()))<=contract['total_max_bytes'],'focused aggregate bytes')
    need(P(str(log)+'.stdout').read_bytes()==contract['stdout'].encode()and P(str(log)+'.stderr').read_bytes()==b'','target raw stdout/stderr')
    for name in contract['cases']:
        need(values[name+'.result']==b'PASS\n','case FAIL '+name)
        need(values[name+'.A']==values[name+'.C']==values[name+'.expected'],'raw output/expected '+name)
        snapshots=[values[name+suffix]for suffix in ['.snapshot-A-before','.snapshot-A-after','.snapshot-C-before','.snapshot-C-after']]
        need(all(value==snapshots[0]for value in snapshots),'snapshot preservation/equality '+name)
def runtime(log,check):
    text=P(str(log)+'.stdout').read_text();need(P(str(log)+'.stderr').read_bytes()==b''and'not found'not in text,'ldd error')
    paths=sorted(set(re.findall(r'(?:=>\s+)?(/[^\s(]+)',text)))
    need({P(x).name for x in paths}=={'libc.so.6','libgmp.so.10','libm.so.6','ld-linux-x86-64.so.2'},'unexpected runtime closure')
    return {x:identity(P(x),check)for x in paths}
def main():
    ci_only();parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args()
    root=P(args.root).resolve();art=root/'artifacts';prefix=root/'ghc';out=art/'focused';need(not out.exists(),'fresh focused output required');out.mkdir()
    sup=Supervisor(art,180,150,phase='focused');rec=dict(complete=False,errors=[],ci_identity=ci_identity(),performance=False,native=False,compile_s=0,target_s=0,source_files=33,homes_each=17,cases_each=4)
    binaries={};runtimes={};env=safe_env(root,prefix);rows=json.loads((HERE/'source-pins.json').read_text());contract=json.loads((HERE/'contract.json').read_text());modules=sorted(r['module']for r in rows if'module'in r)
    try:
        rec['resources']=resource_floor(root);metadata_before={n:identity(HERE/n,sup.check)for n in ['source-pins.json','contract.json','bounded.py','install.py','qualify.py']};write(out/'experiment-metadata-before.json',metadata_before);need(len(rows)==33 and len(modules)==17 and len(set(modules))==17,'source cardinality')
        need(len(contract['cases'])==4 and len(set(contract['cases']))==4 and len(contract['files'])==32 and len(set(contract['files']))==32,'contract cardinality')
        need(set(contract['files'])=={name+suffix for name in contract['cases'] for suffix in ['.A','.C','.expected','.snapshot-A-before','.snapshot-A-after','.snapshot-C-before','.snapshot-C-after','.result']},'contract suffix set')
        install=json.loads((art/'install-receipt.json').read_text());need(install['ci_identity']==rec['ci_identity'],'installation from another CI identity');need(install['limit_policy_phase']=='install'and install['child_fsize_limit_bytes']==1024*MIB,'installation limit policy differs');need(install['complete']and install['archive_verified']and install['expected_sha256']=='60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841','installation not qualified')
        expected=json.loads((art/'toolchain-inventory.json').read_text());need(sha(art/'toolchain-inventory.json')==install['toolchain_inventory_sha256'],'toolchain inventory receipt')
        need(inventory(prefix,sup.check)==expected,'toolchain changed before gate');check_sources(rows,sup.check)
        host={name:identity(P(shutil.which(name, path=env['PATH'])),sup.check)for name in ['gcc','ldd','as','ld','ar']};write(out/'host-tools-before.json',host)
        (out/'c').mkdir();(out/'bin').mkdir()
        for name,source in [('host','host.c'),('supervisor','mlf_process_supervisor.c')]:
            _,elapsed=sup.run('c-'+name,['gcc','-O2','-std=c11','-I'+str(HERE/'csrc'),'-c',HERE/'csrc'/source,'-o',out/'c'/(name+'.o')],root,min(15,120-rec['compile_s']),env);rec['compile_s']+=elapsed
        for opt in ['O0','O2']:
            obj=out/('obj-'+opt);stubs=out/('stubs-'+opt);target=out/('target-'+opt)
            obj.mkdir();stubs.mkdir();target.mkdir();binary=out/'bin'/('focused-'+opt)
            argv=[prefix/'bin/ghc','--make','-j1','-fforce-recomp','-XHaskell2010','-'+opt,'-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns','-Werror=incomplete-uni-patterns','-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages','-rtsopts=ignoreAll','-i','-i'+str(HERE/'src'),'-odir',obj,'-hidir',obj,'-stubdir',stubs]
            for package in ['base','array','bytestring','text','containers','directory']:argv+=['-package',package]
            argv += [out/'c/host.o',out/'c/supervisor.o','-o',binary,HERE/'src/Main.hs']
            log,elapsed=sup.run('ghc-'+opt,argv,root,120-rec['compile_s'],env);rec['compile_s']+=elapsed
            compiled=re.findall(r'Compiling ([A-Za-z0-9_.]+)\s',P(str(log)+'.stdout').read_text());need(sorted(compiled)==modules,'actual home mapping '+opt)
            for extension in ['.hi','.o']:need({str(p.relative_to(obj))for p in obj.rglob('*'+extension)}=={n.replace('.','/')+extension for n in modules},'object/interface mapping '+opt)
            binaries[opt]=identity(binary,sup.check);write(out/('binary-'+opt+'.json'),binaries[opt])
            log,_=sup.run('ldd-'+opt,['ldd',binary],root,5,env);runtimes[opt]=runtime(log,sup.check);write(out/('runtime-'+opt+'.json'),runtimes[opt])
            check_sources(rows,sup.check);need(not any(target.iterdir()),'target cwd not fresh')
            log,elapsed=sup.run('target-'+opt,[binary],target,min(10,20-rec['target_s']),env);rec['target_s']+=elapsed
            focused(target,contract,log);need(identity(binary,sup.check)==binaries[opt],'binary changed')
            for path,value in runtimes[opt].items():need(identity(P(path),sup.check)==value,'runtime changed')
            write(out/('qualified-'+opt+'.json'),dict(cases=4,files=32,snapshot_files=16,performance=False))
        rec['complete']=True
    except BaseException as e:rec['errors'].append(repr(e))
    finally:
        sup.work=165
        try:
            check_sources(rows,sup.check)
            if 'metadata_before'in locals():need({n:identity(HERE/n,sup.check)for n in metadata_before}==metadata_before,'experiment metadata changed')
            if 'expected'in locals():need(inventory(prefix,sup.check)==expected,'toolchain after mismatch')
            for opt,value in binaries.items():need(identity(out/'bin'/('focused-'+opt),sup.check)==value,'binary after mismatch')
            for values in runtimes.values():
                for path,value in values.items():need(identity(P(path),sup.check)==value,'runtime after mismatch')
            if 'host'in locals():need({name:identity(P(shutil.which(name,path=env['PATH'])),sup.check)for name in host}==host,'host tool changed')
            rec['postchecks']=True
        except BaseException as e:rec['postchecks']=False;rec['errors'].append('postcheck:'+repr(e))
        rec['compile_s']=sum(x['elapsed_s']for x in sup.records if x['name'].startswith(('c-','ghc-')))
        rec['target_s']=sum(x['elapsed_s']for x in sup.records if x['name'].startswith('target-'))
        rec.update(sup.finish());rec['complete']=rec['complete']and rec['postchecks']and rec['cleanup']and rec['within_whole']and not rec['errors']
        write(art/'focused-receipt.json',rec);print(json.dumps(rec));artifact_budget(art,96*MIB)
    return 0 if rec['complete']else 1
if __name__=='__main__':sys.exit(main())
