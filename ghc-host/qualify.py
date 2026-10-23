#!/usr/bin/env python3
"""Serial qualification of the GHC compiler, using unchanged repository gates.

Run after build.py and test.py/test_async.py. Bootstrap is intentionally separate:
the native self-host gate requires the actual native producer report, not H0's
inherited source-implementation label. Selected groups are always marked partial.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
GROUPS=['tuple-list','async','unit','parity','packages','backends','port']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir',type=Path,default=ROOT/'.mlf-build/ghc-host')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--groups',nargs='+',choices=GROUPS,default=GROUPS)
    options=parser.parse_args()
    build=options.build_dir.resolve()
    out=options.output.resolve()
    # Never overwrite another qualification or turn a previous pass into a stale
    # receipt while reusing its process fixtures. Resume with a new output path.
    out.mkdir(parents=True,exist_ok=False)
    compiler,manager,runner=(build/'bin'/name for name in ['emlf','mlfpkg','compiler-tests'])
    binaries={str(p):sha(p) for p in [compiler,manager,runner,build/'bin/mlf-build-runner',build/'bin/tuple-list']}
    source_paths=[p for directory in ['bootstrap','package','libraries','runtime','tests','testing','scripts','tools/release','ghc-host']
                  for p in (ROOT/directory).rglob('*') if p.is_file() and not any(part in ['.mlf-build','__pycache__'] for part in p.parts)]
    inputs={str(p.relative_to(ROOT)):sha(p) for p in source_paths}
    evidence={'format':1,'host':'GHC','complete':False,'scope':'full-local' if options.groups==GROUPS else 'partial',
              'groups':options.groups,'bootstrap_included':False,'performance_included':False,
              'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'binaries':binaries,'inputs':inputs,'commands':[],
              'build_receipt':str(build/'build-evidence.json'),'build_receipt_sha256':sha(build/'build-evidence.json')}
    env=dict(os.environ,EMLF=str(compiler),MLF_ASYNC_COMPLETION_BUILD_DIR=str(out/'async-completion'))
    receipt=out/'qualification.json'
    def save():
        receipt.write_text(json.dumps(evidence,indent=2)+'\n')
    save()
    def run(label,args,child_receipt=None):
        print('+',label, ' '.join(map(str,args)),flush=True)
        start=time.monotonic()
        log=out/(label+'.log')
        with log.open('wb') as stream:
            result=subprocess.run(list(map(str,args)),cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)
        entry={'label':label,'argv':list(map(str,args)),'status':result.returncode,
               'seconds':time.monotonic()-start,'log':str(log),'log_sha256':sha(log)}
        evidence['commands'].append(entry)
        save()
        if result.returncode:
            raise RuntimeError(label+' failed; see '+str(log))
        if child_receipt:
            child=json.loads(child_receipt.read_text())
            if child.get('complete') is not True:
                raise RuntimeError(label+' did not produce a complete receipt')
            entry['receipt']=str(child_receipt)
            entry['receipt_sha256']=sha(child_receipt)
            save()
        print('PASS',label,flush=True)
    for group in options.groups:
        if group=='tuple-list':
            run('tuple-list',[build/'bin/tuple-list'])
            run('tuple-list-native',['bash','tools/release/test-tuple-list.sh',compiler,out/'tuple-list-native'])
        elif group=='async':
            # The representation counterexample is only compiled and checked
            # by this unchanged script. Never execute its accepted bad interface.
            run('async-representation',['sh','tests/fixtures/async-gate/check.sh'])
            run('async-completion',['bash','tests/fixtures/async-completion/check.sh'],out/'async-completion/result.json')
            for name in ['process','task']:
                directory=out/('async-'+name)
                run('async-'+name,['bash','tools/release/test-async-'+name+'.sh',compiler,directory],directory/'result.json')
            run('async-package',['bash','tools/release/test-async-package.sh',compiler,manager,out/'async-package'],out/'async-package/result.json')
        else:
            run(group,[runner,group,'--compiler',compiler,'--manager',manager,'--build-dir',out/group,
                       '--cache-dir',out/'cache'],out/group/'verification.json')
    for path,expected in binaries.items():
        assert sha(Path(path))==expected,path+' changed during qualification'
    for path,expected in inputs.items():
        assert sha(ROOT/path)==expected,path+' changed during qualification'
    evidence['complete']=True
    save()
    print('Qualification receipt:',receipt)


if __name__=='__main__':
    main()
