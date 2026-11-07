"""Provisional recovery source. Linux only; no system install or automatic deletion."""
import json
import pathlib
import subprocess
from recovery_common import arguments,new_output,download_verified,extract_verified,check_resources,GIB

def main():
    args=arguments('Restore nine pinned Debian packages to a new task-local prefix')
    root=new_output(args.output,GIB)
    records=[]
    for row in pathlib.Path(__file__).with_name('pins.tsv').read_text().splitlines():
        package,name,size,sha=row.split()
        directory='l' if package=='llvm-toolchain-19' else ('libg' if package=='libgc' else 'libp')
        url=f'https://deb.debian.org/debian/pool/main/{directory}/{package}/{name}'
        archive=root/'downloads'/name
        download_verified(url,archive,sha,int(size))
        check_resources(root,GIB)
        extract_verified(archive,root/'debian-prefix',sha,int(size))
        dependencies=subprocess.check_output(['dpkg-deb','--field',str(archive),'Depends'],text=True).strip()
        records.append(dict(file=name,url=url,bytes=int(size),sha256=sha,dependencies=dependencies))
        (root/'debian-manifest.json').write_text(json.dumps(records,indent=2)+'\n')
    print('Packages verified and extracted. Scope environment and run independent probes before use.')

if __name__=='__main__':main()
