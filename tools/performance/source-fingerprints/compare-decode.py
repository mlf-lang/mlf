#!/usr/bin/env python3
"""Replay the wire-only study against two complete GHC producer builds."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path, help='producer directory')
    p.add_argument('candidate', type=Path)
    p.add_argument('sequence', type=Path, help='candidate run from compare.py')
    p.add_argument('out', type=Path)
    a = p.parse_args()
    out = a.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    executables = {}
    for name,producer in [('baseline',a.baseline.resolve()),('candidate',a.candidate.resolve())]:
        receipt = json.loads((producer/'receipt.json').read_bytes())
        if not receipt['complete'] or receipt['optimization'] != '2':
            raise ValueError('both producers must be complete -O2 builds')
        directory = out/name
        directory.mkdir()
        common = [receipt['ghc']['path'],'-O2','-fpedantic-bottoms','-fno-state-hack',
                  '-package-env','-','-clear-package-db','-global-package-db','-no-user-package-db',
                  '-hide-all-packages',*sum((['-package',n] for n in
                      ['base','array','bytestring','text','containers','directory']),[])]
        obj = directory/'Decode.o'
        with (directory/'build.log').open('wb') as log:
            subprocess.run([*common,'-c','-i','-i'+str(producer/'objects'),'-o',obj,
                            '-ohi',directory/'Decode.hi',Path(__file__).with_name('Decode.hs')],
                           check=True,stdout=log,stderr=log)
            objects = []
            for rel,expected in sorted(receipt['object_inputs'].items()):
                if rel.endswith('.o') and rel != 'objects/Main.o':
                    if sha(producer/rel) != expected:
                        raise ValueError('producer object changed: '+rel)
                    objects.append(producer/rel)
            probe = directory/'probe'
            subprocess.run([*common,'-rtsopts=ignoreAll',obj,*objects,producer/'host.o',
                            producer/'supervisor.o','-o',probe],check=True,stdout=log,stderr=log)
            executables[name] = probe
    reports = json.loads((a.sequence/'cold.queries').read_bytes())['groups']
    paths = [(a.sequence/'cache'/(g['query_key']+'.mlfq')).resolve(strict=True) for g in reports]
    if len(set(paths)) != 504:
        raise ValueError('unexpected cold inventory')
    hashes = [sha(path) for path in paths]
    manifest = out/'paths'
    manifest.write_text(''.join(str(path)+'\n' for path in paths))
    eligible = eligible_bytes = symbol_bytes = 0
    for path in paths:
        raw = path.read_bytes()
        count,_,size = struct.unpack_from('<III',raw,28)
        symbol_bytes += size
        if len(raw)>=1024 and 0<count<=1024 and size<=65536:
            eligible += 1
            eligible_bytes += size
    record = {'record_count':len(paths),'eligible':eligible,
              'total_symbol_section_bytes':symbol_bytes,'eligible_symbol_section_bytes':eligible_bytes,
              'manifest_sha256':hashlib.sha256(''.join(hashes).encode()).hexdigest(),
              'probe_sha256':{k:sha(v) for k,v in executables.items()},'samples':[]}
    for name in ['baseline','candidate','candidate','baseline']*2:
        wall,cpu = ast.literal_eval(subprocess.check_output([executables[name],manifest],text=True))
        record['samples'].append(dict(arm=name,wall_s=wall,cpu_s=cpu))
        (out/'results.json').write_text(json.dumps(record,indent=2)+'\n')
    if hashes != [sha(path) for path in paths]:
        raise ValueError('corpus changed during measurement')


if __name__=='__main__':
    main()
