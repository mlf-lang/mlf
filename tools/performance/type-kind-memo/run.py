#!/usr/bin/env python3
"""Small isolated mechanism/control diagnostic, not compiler qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ghc', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--optimization', choices=['0','2'], default='2')
    parser.add_argument('--controls-only', action='store_true')
    args = parser.parse_args()
    owner = ROOT/'libraries/mlf-xmlf/Bootstrap/X/Type.hs'
    if sha(owner) != '151c2b6966dce76abbaa7e9c8c982a01ab19f7199a576fc57469e357bfe914ed':
        raise RuntimeError('memo candidate is stopped; use the archived experimental checkpoint only for explicit historical reproduction')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((ROOT/'shared-sources.json').read_text())
    flags = ['-O'+args.optimization, '-fpedantic-bottoms', '-fno-state-hack',
             '-package-env', '-', '-clear-package-db', '-global-package-db',
             '-no-user-package-db', '-hide-all-packages']
    for package in ['base','array','bytestring','text','containers','directory']:
        flags += ['-package', package]
    command = [str(args.ghc), '--make', *flags,
        *['-i'+str(ROOT/r) for r in manifest['source_roots']],
        '-I'+str(ROOT/'runtime'), '-odir', str(out/'objects'), '-hidir', str(out/'objects'),
        str(Path(__file__).with_name('Main.hs')),
        str(ROOT/'host/ghc/cbits/host.c'), str(ROOT/'runtime/mlf_process_supervisor.c'),
        '-o', str(out/'probe')]
    inputs = [ROOT/item['path'] for item in manifest['modules']]
    inputs += list((ROOT/'host/ghc').rglob('*.hs'))
    inputs += [ROOT/'host/ghc/cbits/host.c', ROOT/'runtime/mlf_process_supervisor.c',
               *sorted((ROOT/'runtime').glob('*.h')), Path(__file__), Path(__file__).with_name('Main.hs'),
               ROOT/'shared-sources.json', ROOT/'tools/shared/resource_watchdog.py', args.ghc.resolve()]
    record = dict(complete=False, diagnostic_only=True, compiler_speedup_claim=False,
                  flags=flags, commands=[], inputs={str(p):sha(p) for p in inputs})
    def run(label, cmd):
        start=time.monotonic()
        guarded = [sys.executable, str(ROOT/'tools/shared/resource_watchdog.py'),
                   '--seconds','180','--address-space-mib','6144','--rss-mib','5120',
                   '--disk-free-mib','5120',str(out/(label+'-resources')),*cmd]
        result=subprocess.run(guarded,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                              timeout=200,env={**os.environ,'GHC_ENVIRONMENT':'-'})
        (out/(label+'.stdout')).write_bytes(result.stdout)
        (out/(label+'.stderr')).write_bytes(result.stderr)
        record['commands'].append(dict(label=label,command=cmd,exit_code=result.returncode,
                                       wall_seconds=time.monotonic()-start))
        (out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
        if result.returncode: raise RuntimeError(label+' failed')
        return (out/(label+'-resources')/'build.log').read_text()
    run('build', command)
    if run('controls',[str(out/'probe')]) != 'PASS type-kind memo: 5184 generated cases, 17 diamonds, 9 demand/kind controls\n':
        raise RuntimeError('unexpected control output')
    if not args.controls_only:
        for i,variant in enumerate(['old','memo','memo','old']):
            run('mechanism-'+str(i),[str(out/'probe'),'bench',variant,'20','3'])
    if any(sha(path) != digest for path,digest in record['inputs'].items()):
        raise RuntimeError('input changed during diagnostic')
    record['complete']=True
    (out/'receipt.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))

if __name__ == '__main__': main()
