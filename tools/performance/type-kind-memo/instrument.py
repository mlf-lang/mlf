#!/usr/bin/env python3
"""Create a reversible diagnostic-only copy of the frozen Type owner."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess

BASE = 'f9bdb40a'
OWNER = 'libraries/mlf-xmlf/Bootstrap/X/Type.hs'
ROOT = Path(__file__).resolve().parents[3]

def instrument(raw):
    source = raw.decode()
    changes = [
      ('module Bootstrap.X.Type where {',
       '{-# OPTIONS_GHC -fno-cse -fno-full-laziness #-}\nmodule Bootstrap.X.Type where {'),
      ('  import MLF.Primitive;', '  import MLF.Primitive;\n  import qualified KindCounters;'),
      ('  kindOf ds bounds ty =\n    do {', '  kindOf ds bounds ty = KindCounters.root (\n    do {'),
      ('      kindIn ds (M.fromList compareTyVar kinds) ty\n    };',
       '      kindIn ds (M.fromList compareTyVar kinds) ty\n    });'),
      ('  visitKind ds bounds seen a =\n    if',
       '  visitKind ds bounds seen a = KindCounters.visit (tyVarId a) (\n    if'),
      ('         };\n  kindIn ::', '         });\n  kindIn ::'),
    ]
    for before,after in changes:
        if source.count(before) != 1:
            raise ValueError('non-unique instrumentation anchor: '+before)
        source = source.replace(before,after)
    inverse = source
    for before,after in reversed(changes):
        if inverse.count(after) != 1:
            raise ValueError('non-unique inverse anchor')
        inverse = inverse.replace(after,before)
    if inverse.encode() != raw:
        raise ValueError('instrumentation does not reverse exactly')
    return source,changes

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    raw=subprocess.check_output(['git','show',BASE+':'+OWNER],cwd=ROOT)
    source,changes=instrument(raw)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    owner=out/'Bootstrap/X/Type.hs';owner.parent.mkdir(parents=True)
    owner.write_text(source)
    (out/'KindCounters.hs').write_bytes(Path(__file__).with_name('Counters.hs').read_bytes())
    (out/'Main.hs').write_text('''module Main where
import Control.Exception(finally)
import MLF.Host.IO(runEntry)
import qualified MLF.Entry.Emlf as Entry
import qualified KindCounters
main = runEntry Entry.main `finally` KindCounters.report
''')
    (out/'source.json').write_text(json.dumps(dict(
        baseline=BASE,owner=OWNER,sha256=hashlib.sha256(raw).hexdigest(),
        transformed_sha256=hashlib.sha256(source.encode()).hexdigest(),
        reversible=True,edits=changes),indent=2)+'\n')

if __name__=='__main__':main()
