#!/usr/bin/env python3
"""Use genuine v6 and v7 records with one executable identity and source path."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

if not __debug__:
    raise RuntimeError('migration assertions require a normal Python invocation')
binary = Path(sys.argv[1]).resolve(strict=True)
root = Path(sys.argv[2]).resolve()
root.mkdir(parents=True,exist_ok=False)
source, spec, cache = root/'Input.hs', root/'crate.spec', root/'cache'

def pack(fields):
    return ''.join(f'{len(x)}:{x}' for x in fields)

def change(value):
    source.write_text(f'''-- mlf:syntax shared-haskell-v1
{{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}}
module Input where {{
  import MLF.Primitive;
  answer :: Int;
  answer = {value}
}}
''')

builtin = root/'builtin'
subprocess.run([binary,'builtin',builtin],check=True,timeout=180)
spec.write_text(pack(['MLF-CRATE-1','migration/1/library','','false',pack([pack(['Input',str(source)])]),'',str(cache),str(builtin)]))
def run(arm,stage,hits):
    prefix = root/stage
    subprocess.run([binary,arm,spec,prefix],check=True,timeout=180)
    report = json.loads(prefix.with_suffix('.queries').read_text())
    assert (report['inferred_groups'],report['reused_groups'])==(1-hits,hits)
    key = report['groups'][0]['query_key']
    artifact = tuple(prefix.with_suffix(ext).read_bytes() for ext in ['.mlfci','.mlfco'])
    print(stage,1-hits,hits,key,*(hashlib.sha256(x).hexdigest() for x in artifact))
    return cache/(key+'.mlfq'),artifact

change(41)
old,original = run('Old','old-cold',0)
old_bytes = old.read_bytes()
current,output = run('New','v6-only-cache',0)
pristine = current.read_bytes()
assert current!=old and original==output and old.read_bytes()==old_bytes
assert run('New','v7-warm',1)==(current,original)
change(42)
old_changed,changed = run('Old','old-edit',0)
new_changed,current_changed = run('New','new-edit',0)
assert changed==current_changed and changed!=original
change(41)
for stage,wrong in [('v6-at-v7-address',old_changed.read_bytes()),
                    ('v7-at-colliding-address',new_changed.read_bytes()),
                    ('truncated-binary',pristine[:32])]:
    assert wrong != pristine
    current.write_bytes(wrong)
    assert run('New',stage,0)==(current,original) and current.read_bytes()==pristine
assert run('New','repaired-warm',1)==(current,original) and old.read_bytes()==old_bytes
