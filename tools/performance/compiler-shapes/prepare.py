#!/usr/bin/env python3
"""Prepare fixed dependencies once. Does not alter any global GHC package DB."""
from pathlib import Path
import argparse
import shlex
import subprocess
import types

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True)
    p.add_argument('--builtin-prefix',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--clang',default='/usr/bin/clang')
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('unchanged_resource_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    producer=a.producer.resolve();builtin=a.builtin_prefix.resolve();auth=H.authenticate(producer,ROOT)
    for suffix in ['.mlfci','.mlfco']:H.require(Path(str(builtin)+suffix).is_file(),'prebuilt fixed builtin dependency')
    limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,
            'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,
            'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
    ghc=Path(auth['ghc']['path']);pkg=ghc.with_name('ghc-pkg');deps=out/'dependencies';deps.mkdir()
    objects=deps/'objects';objects.mkdir();db=deps/'package-db'
    packages=['base','array','bytestring','text','containers','directory']
    flags=['-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages']
    for name in packages:flags+=['-package',name]
    def run(name,argv):return H.Runner(out,limits).run(argv,ROOT,out/name)
    with H.SerialLock(ROOT/'.mlf-build'):
        run('build-host-package',[ghc,'--make','-j1','-no-link','-O2','-this-unit-id','mlf-shape-primitives-0.1',
            *flags,'-i','-i'+str(ROOT/'host/ghc'),'-odir',objects,'-hidir',objects,ROOT/'host/ghc/MLF/Primitive.hs'])
        run('archive-host-package',['/usr/bin/ar','rcs',deps/'libHSmlf-shape-primitives-0.1.a',
            *sorted(objects.rglob('*.o')),producer/'host.o',producer/'supervisor.o'])
        run('init-package-db',[pkg,'init',db])
        ids=[subprocess.check_output([pkg,'--global','field',name,'id','--simple-output'],text=True).strip() for name in packages]
        conf=deps/'package.conf'
        conf.write_text('name: mlf-shape-primitives\nversion: 0.1\nid: mlf-shape-primitives-0.1\nkey: mlf-shape-primitives-0.1\n'
            'exposed: True\nexposed-modules: MLF.Primitive\nhidden-modules: MLF.Host.Base MLF.Host.IO MLF.Host.Async\n'
            +'import-dirs: '+str(objects)+'\nlibrary-dirs: '+str(deps)+'\nhs-libraries: HSmlf-shape-primitives-0.1\ndepends: '+' '.join(ids)+'\n')
        run('register-package',[pkg,'--package-db',db,'register',conf])
        cflags=shlex.split(subprocess.check_output(['pkg-config','--cflags','bdw-gc','gmp'],text=True))
        libs=shlex.split(subprocess.check_output(['pkg-config','--libs','bdw-gc','gmp'],text=True))
        clang=Path(a.clang).resolve();runtime=deps/'runtime.o'
        run('runtime',[clang,'-O2','-std=c11',*cflags,'-I'+str(ROOT/'runtime'),'-c',ROOT/'runtime/mlf_runtime.c','-o',runtime])
    H.save(out/'setup.json',{'complete':True,'producer':str(producer),'ghc':str(ghc),'package_db':str(db),
        'clang':str(clang),'runtime':str(runtime),'libs':libs,'limits':limits,'builtin':str(builtin)})
    H.save(out/'preparation.json',{'producer_receipt_sha256':H.sha(producer/'receipt.json'),
        'source_pins':H.file_pins(ROOT/'host/ghc'),'runtime_pins':H.file_pins(ROOT/'runtime'),
        'host':H.host(),'tool_versions':{'ghc':auth['ghc'],
            'clang':subprocess.check_output([clang,'--version'],text=True)}})


if __name__=='__main__':main()
