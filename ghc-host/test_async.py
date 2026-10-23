#!/usr/bin/env python3
"""Run existing literal Async contract oracles directly on the GHC host.

This complements the interpreter/native release gates. The white-box test uses
the same export-only overlay as test-async-task.sh; production exports stay intact.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=Path, default=ROOT/'.mlf-build/ghc-host')
    parser.add_argument('--optimization', choices=['0','2'], default='2')
    options = parser.parse_args()
    build = options.build_dir.resolve()
    out = build/('direct-async-O'+options.optimization)
    # Fresh work directories keep process/file observations independent of old runs.
    out.mkdir(parents=True, exist_ok=True)
    import tempfile
    work = Path(tempfile.mkdtemp(prefix='run-', dir=out))
    inputs = {str(p.relative_to(ROOT)):digest(p)
              for folder in ['ghc-host','runtime','libraries','tests/async-process','tests/async-task']
              for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    evidence = {'complete':False,'optimization':options.optimization,'work':str(work),
                'inputs':inputs,'observations':[], 'ghc':subprocess.check_output(['ghc','--numeric-version'],text=True).strip(),
                'converter_sha256':digest(build/'mlf-to-haskell')}
    receipt = out/'result.json'
    def save():
        receipt.write_text(json.dumps(evidence,indent=2)+'\n')
    save()

    def run(label, command, expected=None, env=None, status=0):
        result = subprocess.run(list(map(str,command)),cwd=ROOT,env=env,stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
        (work/(label+'.stdout')).write_bytes(result.stdout)
        (work/(label+'.stderr')).write_bytes(result.stderr)
        evidence['observations'].append({'label':label,'command':list(map(str,command)),
                                        'status':result.returncode,'stdout_sha256':hashlib.sha256(result.stdout).hexdigest(),
                                        'stderr_sha256':hashlib.sha256(result.stderr).hexdigest()})
        save()
        if result.returncode != status or (expected is not None and (result.stdout != expected or result.stderr)):
            raise RuntimeError(label+' failed: '+str(work))
        print('PASS',label,flush=True)
        return result

    for kind in ['task','process']:
        run(kind+'-fixture',['clang','-O2','-std=c11','-Wall','-Wextra','-Werror',
                            ROOT/('tests/async-'+kind+'/fixture.c'),'-o',work/(kind+'-fixture')])
    suites = [('task-main','task','Main.emlf','suite.stdout'),
              ('task-processes','task','Processes.emlf','processes.stdout'),
              ('task-wait-graph','task','WaitGraph.emlf','wait-graph.stdout'),
              ('process-main','process','Main.emlf','suite.stdout'),
              ('process-panic','process','Panic.emlf',None)]
    for label,kind,entry,oracle in suites:
        directory = work/label
        directory.mkdir()
        generated = directory/'generated'
        jobs=[]
        for row in (build/'sources.tsv').read_text().splitlines():
            source,_,module=row.split('\t')
            target=generated/(module.replace('.','/')+'.hs')
            target.parent.mkdir(parents=True,exist_ok=True)
            if label=='task-wait-graph' and module=='Async.Task.Internal':
                original=(ROOT/source).read_text().splitlines(keepends=True)
                header=next(i for i,line in enumerate(original) if line.rstrip().endswith('where'))
                overlay=directory/'Internal.emlf'
                overlay.write_text('module Async.Task.Internal where\n'+''.join(original[header+1:]))
                source=str(overlay)
                evidence['whitebox_sha256']=digest(overlay)
            jobs.append('\t'.join([source,str(target),module]))
        fixture=ROOT/('tests/async-'+kind)/entry
        jobs.append('\t'.join([str(fixture),str(generated/'HostFixture.hs'),'HostFixture']))
        manifest=directory/'sources.tsv'
        manifest.write_text('\n'.join(jobs)+'\n')
        run(label+'-translate',[build/'mlf-to-haskell','--batch',manifest])
        wrapper=directory/'Main.hs'
        wrapper.write_text('module Main where\nimport MLF.Host.IO (runEntry)\nimport qualified HostFixture\nmain = runEntry HostFixture.v_main\n')
        binary=directory/'suite'
        run(label+'-build',['ghc','-O'+options.optimization,'-w','-ighc-host/runtime','-i'+str(generated),
                           '-outputdir',directory/'objects',wrapper,'ghc-host/cbits/host.c',
                           'runtime/mlf_process_supervisor.c','-Iruntime','-o',binary])
        env=dict(os.environ,MLF_ASYNC_FIXTURE=str(work/(kind+'-fixture')),MLF_ASYNC_WORK=str(directory))
        if oracle:
            run(label,[binary],(ROOT/('tests/async-'+kind)/oracle).read_bytes(),env)
        else:
            result=run(label,[binary],env=env,status=1)
            assert result.stdout==b'' and b'async-scope-panic' in result.stderr
            run(label+'-reaped',[work/'process-fixture','assert-gone',directory/'panic.pid'],b'',env)
        evidence.setdefault('executables',{})[label]=digest(binary)
    for relative,expected in inputs.items():
        assert digest(ROOT/relative)==expected, relative+' changed during execution'
    evidence['complete']=True
    save()
    print('Direct GHC Async library contracts passed:',receipt)


if __name__=='__main__':
    main()
