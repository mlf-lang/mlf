"""Provisional Linux recovery source; installation outputs are not qualification."""
import json
import subprocess
from recovery_common import arguments,new_output,download_verified,verify,check_resources,GIB
URL='https://downloads.haskell.org/~ghc/9.14.1/ghc-9.14.1-x86_64-deb12-linux.tar.xz'
SHA='60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841'
SIZE=306812040

def main():
    args=arguments('Install pinned GHC in a new task-local prefix (reserve 8 GiB)')
    root=new_output(args.output,8*GIB)
    archive=root/'ghc-9.14.1.tar.xz'
    download_verified(URL,archive,SHA,SIZE)
    (root/'ghc-download.json').write_text(json.dumps(dict(url=URL,sha256=SHA,bytes=SIZE),indent=2)+'\n')
    verify(archive,SHA,SIZE)
    subprocess.run(['tar','-xf',str(archive),'-C',str(root)],check=True)
    check_resources(root,4*GIB)
    staging=root/'ghc-9.14.1-x86_64-unknown-linux'
    with (root/'ghc-install.log').open('x') as log:
        subprocess.run(['./configure','--prefix='+str(root/'ghc')],cwd=staging,stdout=log,stderr=subprocess.STDOUT,check=True)
        subprocess.run(['make','install'],cwd=staging,stdout=log,stderr=subprocess.STDOUT,check=True)
    print('Installed, not independently qualified. Run maintained cleanup-ghc-install.py with RUNNER_TEMP='+str(root)+' and a fresh receipt OUTSIDE this directory. It validates before deleting only owned archive/staging. No automatic cleanup has run.')

if __name__=='__main__':main()
