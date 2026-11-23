#!/usr/bin/env python3
"""Prepare fixed dependencies once. Does not alter any global GHC package DB.

The setup records the compile endpoint it belongs to. A cohort may only reuse a
setup whose endpoint profile matches, so bootstrap-crate measurements can never
be mixed with installed-driver measurements.
"""
from pathlib import Path
import argparse
import json
import shlex
import subprocess
import command_runner

ROOT=Path(__file__).resolve().parents[3]

# Endpoint profiles that can be prepared here. emlf-source-v1 is declared in
# matrix.json but has no preparation path in this revision, so it is not listed.
PROFILES={name:{'producer_kind':'empty','label':'bootstrap crate producer (no installed native data)'}
          for name in ['crate-bootstrap-v1', 'crate-fused-v1', 'crate-plan-v1']}


def pack(values):
    return ''.join(str(len(x))+':'+x for x in values)


def prepare_host_package(ghc, source, producer, deps, run, *, expose_host_io=False):
    pkg=ghc.with_name('ghc-pkg');deps.mkdir()
    objects=deps/'objects';objects.mkdir();db=deps/'package-db'
    packages=['base','array','bytestring','text','containers','directory']
    flags=['-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db','-hide-all-packages']
    for name in packages:flags+=['-package',name]
    run('build-host-package',[ghc,'--make','-j1','-no-link','-O2','-this-unit-id','mlf-shape-primitives-0.1',
        *flags,'-i','-i'+str(source/'host/ghc'),'-odir',objects,'-hidir',objects,source/'host/ghc/MLF/Primitive.hs'])
    run('archive-host-package',['/usr/bin/ar','rcs',deps/'libHSmlf-shape-primitives-0.1.a',
        *sorted(objects.rglob('*.o')),producer/'host.o',producer/'supervisor.o'])
    run('init-package-db',[pkg,'init',db])
    ids=[subprocess.check_output([pkg,'--global','field',name,'id','--simple-output'],text=True).strip() for name in packages]
    conf=deps/'package.conf'
    exposed = 'MLF.Primitive MLF.Host.IO' if expose_host_io else 'MLF.Primitive'
    hidden = 'MLF.Host.Base MLF.Host.Async' if expose_host_io else 'MLF.Host.Base MLF.Host.IO MLF.Host.Async'
    conf.write_text('name: mlf-shape-primitives\nversion: 0.1\nid: mlf-shape-primitives-0.1\nkey: mlf-shape-primitives-0.1\n'
        f'exposed: True\nexposed-modules: {exposed}\nhidden-modules: {hidden}\n'
        +'import-dirs: '+str(objects)+'\nlibrary-dirs: '+str(deps)+'\nhs-libraries: HSmlf-shape-primitives-0.1\ndepends: '+' '.join(ids)+'\n')
    run('register-package',[pkg,'--package-db',db,'register',conf])
    return db


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer',type=Path,required=True)
    p.add_argument('--source',type=Path,default=ROOT)
    p.add_argument('--builtin-prefix',type=Path)
    p.add_argument('--build-builtin',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--clang',default='/usr/bin/clang')
    p.add_argument('--ghc')
    p.add_argument('--expose-host-io', action='store_true',
                   help='Expose MLF.Host.IO in the private dependency package for the full compiler Main wrapper.')
    p.add_argument('--endpoint',default=json.loads(Path(__file__).with_name('matrix.json').read_text())['default_endpoint'],choices=sorted(PROFILES))
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    H=command_runner.load_helper()
    producer=a.producer.resolve();source=a.source.resolve();auth=H.authenticate(producer,source)
    receipt=H.load(producer/'receipt.json')
    profile=PROFILES[a.endpoint]
    H.require(receipt.get('prepared_verification',{}).get('kind')==profile['producer_kind'],
              a.endpoint+' requires the '+profile['label']+'; found producer kind '+
              str(receipt.get('prepared_verification',{}).get('kind')))
    H.require(bool(a.builtin_prefix) != a.build_builtin,'choose exactly one builtin source')
    limits={'address_space_per_process_bytes':6*1024**3,'disk_free_floor_bytes':5*1024**3,
            'host_available_floor_bytes':3*1024**3,'max_work_bytes':2*1024**3,
            'process_tree_rss_bytes':5*1024**3,'wall_seconds':600}
    ghc=Path(a.ghc).resolve() if a.ghc else Path(auth['ghc']['path'])
    def run(name,argv):return H.Runner(out,limits).run(argv,ROOT,out/name)
    builtin_record={}
    with H.SerialLock(ROOT/'.mlf-build'):
        deps=out/'dependencies'
        db=prepare_host_package(ghc,source,producer,deps,run,expose_host_io=a.expose_host_io)
        cflags=shlex.split(subprocess.check_output(['pkg-config','--cflags','bdw-gc','gmp'],text=True))
        libs=shlex.split(subprocess.check_output(['pkg-config','--libs','bdw-gc','gmp'],text=True))
        clang=Path(a.clang).resolve();runtime=deps/'runtime.o'
        run('runtime',[clang,'-O2','-std=c11',*cflags,'-I'+str(source/'runtime'),'-c',source/'runtime/mlf_runtime.c','-o',runtime])
        if a.build_builtin:
            # The public crate path produces the fixed checked builtin pair once.
            # It is a reused dependency, never a timed target.
            work=out/'builtin-work';work.mkdir();fixture=work/'Fixture.emlf'
            fixture.write_text('module Fixture where\nvalue = 42\n')
            builtin=out/'builtin';queries=work/'queries';queries.mkdir()
            spec=work/'fixture.spec'
            spec.write_text(pack(['MLF-CRATE-1','compiler-shapes/builtin','','false',
                pack([pack(['Fixture',str(fixture)])]),'',str(queries),str(builtin)]))
            run('prepare-builtin',[producer/'bin/emlf','--compile-crate',spec,'-o',work/'fixture'])
            report=H.load(str(work/'fixture')+'.queries')
            H.require(report['inferred_groups']==1 and report['reused_groups']==0
                      and all(g['cached'] is False for g in report['groups']),'one fresh builtin fixture group')
            for suffix in ['.mlfci','.mlfco']:H.require(Path(str(builtin)+suffix).is_file(),'prepared builtin pair')
            builtin_record={'origin':'prepared by the public crate path','fixture_sha256':H.sha(fixture),
                'spec_sha256':H.sha(spec),'queries_sha256':H.sha(str(work/'fixture')+'.queries'),
                'groups':report['inferred_groups']}
        else:
            builtin=a.builtin_prefix.resolve()
            for suffix in ['.mlfci','.mlfco']:H.require(Path(str(builtin)+suffix).is_file(),'prebuilt fixed builtin dependency')
            builtin_record={'origin':'supplied prebuilt pair'}
    builtin_record.update({str(builtin)+s: H.sha(str(builtin)+s) for s in ['.mlfci','.mlfco']})
    H.save(out/'setup.json',{'complete':True,'endpoint':a.endpoint,'endpoint_label':profile['label'],
        'producer':str(producer),'source':str(source),'ghc':str(ghc),'package_db':str(db),
        'clang':str(clang),'runtime':str(runtime),'libs':libs,'limits':limits,'builtin':str(builtin),
        'builtin_record':builtin_record,
        'identity':{'producer_receipt_sha256':H.sha(producer/'receipt.json'),
            'producer_emlf_sha256':H.sha(producer/'bin/emlf'),
            'builtin_prelude_sha256':H.sha(producer/'bin/builtin-prelude'),
            'ghc_version':auth['ghc']['version'],'optimization':receipt.get('optimization'),
            'builtin_interface':receipt.get('builtin_interface'),
            'clang_version':subprocess.check_output([clang,'--version'],text=True).splitlines()[0]}})
    H.save(out/'preparation.json',{'producer_receipt_sha256':H.sha(producer/'receipt.json'),
        'source_pins':H.file_pins(source/'host/ghc'),'runtime_pins':H.file_pins(source/'runtime'),
        'host':H.host(),'tool_versions':{'ghc':auth['ghc'],
            'clang':subprocess.check_output([clang,'--version'],text=True)}})


if __name__=='__main__':main()
