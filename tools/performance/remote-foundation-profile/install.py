"""Official fixed bindist, bounded installation only. No project compilation."""
import argparse,json,os,pathlib,shutil,sys
from bounded import *
URL='https://downloads.haskell.org/~ghc/9.14.1/ghc-9.14.1-x86_64-deb12-linux.tar.xz'
SHA='60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841'
SIZE=306812040
def main():
    ci_only();parser=argparse.ArgumentParser();parser.add_argument('--root',required=True);args=parser.parse_args()
    root=P(args.root).resolve();need(not root.exists(),'fresh installation root required');root.mkdir()
    art=root/'artifacts';art.mkdir();sup=Supervisor(art,300,280,phase='install');rec=dict(complete=False,errors=[],ci_identity=ci_identity(),official_url=URL,expected_sha256=SHA,initial_disk_floor_bytes=12*1024**3)
    env=safe_env(root);prefix=root/'ghc';dist=root/'dist';dist.mkdir()
    try:
        rec['resources']=resource_floor(root,disk_floor_GiB=12)
        archive=root/'ghc.tar.xz'
        sup.run('install-download',['curl','--fail','--location','--proto','=https','--tlsv1.2','--connect-timeout','20','--max-time','100','--retry','0','--output',archive,URL],root,105,env)
        need(archive.stat().st_size==SIZE and sha(archive,sup.check)==SHA,'official bindist identity failed')
        rec['archive_verified']=True
        sup.run('install-extract',['tar','-xJf',archive,'--strip-components=1','-C',dist],root,60,env)
        sup.run('install-configure',['/bin/sh','./configure','--prefix='+str(prefix)],dist,60,env)
        sup.run('install-make',['make','-j1','install'],dist,150,env)
        log,_=sup.run('install-version',[prefix/'bin/ghc','--numeric-version'],root,5,env)
        need(P(str(log)+'.stdout').read_bytes()==b'9.14.1\n','wrong GHC version')
        sup.run('install-package-check',[prefix/'bin/ghc-pkg','--global','--no-user-package-db','check'],root,10,env)
        sup.run('install-package-dump',[prefix/'bin/ghc-pkg','--global','--no-user-package-db','dump'],root,10,env)
        inv=inventory(prefix,sup.check);write(art/'toolchain-inventory.json',inv)
        rec['toolchain_inventory_sha256']=sha(art/'toolchain-inventory.json');rec['toolchain_files']=len(inv);rec['complete']=True
    except BaseException as e:rec['errors'].append(repr(e))
    finally:
        rec.update(sup.finish());rec['complete']=rec['complete']and rec['cleanup']and rec['within_whole']and not rec['errors']
        write(art/'install-receipt.json',rec);print(json.dumps(rec));artifact_budget(art,96*MIB)
    return 0 if rec['complete']else 1
if __name__=='__main__':sys.exit(main())

