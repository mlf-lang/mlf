#!/usr/bin/env python3
"""Mutate the real inference builtin list and force a compiler identity collision."""
import json
import subprocess
import sys
from pathlib import Path

if not __debug__:
    raise RuntimeError('mutation assertions require a normal Python invocation')
here = Path(__file__).resolve().parent
root = here.parents[2]
out = Path(sys.argv[1]).resolve()
out.mkdir(parents=True,exist_ok=False)
cache = out/'cache'
cache.mkdir()
roots = json.loads((root/'shared-sources.json').read_text())['source_roots']
source = (root/'libraries/mlf-language-core/Bootstrap/Data.hs').read_text()
before = 'unitDeclaration = DataDecl "MLFLegacyUnit" [] ((:) (ConstructorDecl "MLFLegacyUnit" []) []);'
after = 'unitDeclaration = DataDecl "MLFLegacyUnit" [] [ConstructorDecl "MLFLegacyUnit" [], ConstructorDecl "ExtraUnit" []];'
assert source.count(before)==1
overlay = out/'changed/Bootstrap/Data.hs'
overlay.parent.mkdir(parents=True)
overlay.write_text(source.replace(before,after))
for mode in ['original','changed']:
    d = out/mode
    d.mkdir(exist_ok=True)
    with (d/'build.log').open('wb') as log:
        subprocess.run(['ghc','--make','-j2','-O0','-fpedantic-bottoms','-fno-state-hack','-package-env','-',
                        '-i','-i'+str(d),*['-i'+str(root/r) for r in roots],'-outputdir',d/'obj',
                        '-optc-I'+str(root/'runtime'),here/'BuiltinMutation.hs',root/'host/ghc/cbits/host.c',
                        root/'runtime/mlf_process_supervisor.c','-o',d/'probe'],check=True,stdout=log,stderr=log)
    if mode=='changed':
        assert str(overlay) in (d/'build.log').read_text()

def run(mode, expected, *identity):
    report = json.loads(subprocess.check_output([out/mode/'probe',mode,cache,expected,*identity],timeout=90))
    print(mode,expected,report['inferred_groups'],report['reused_groups'],report['groups'][0]['query_key'])
    return cache/(report['groups'][0]['query_key']+'.mlfq')

original = run('original','miss')
pristine = original.read_bytes()
assert run('original','hit')==original
changed = run('changed','miss')
alternate = changed.read_bytes()
assert changed!=original and alternate!=pristine
assert run('changed','hit')==changed
# Put the foreign record in the right bucket in *both* directions. Compiler,
# source, user datatypes, dependencies and expected raw result are identical.
original.write_bytes(alternate)
assert run('original','miss')==original and original.read_bytes()==pristine
changed.write_bytes(pristine)
assert run('changed','miss')==changed and changed.read_bytes()==alternate
assert run('changed','hit')==changed and run('original','hit')==original

# Isolate the compiler field: same executable, source group and actual builtin.
identity = 'b' * 64
foreign = run('original', 'miss', identity)
assert foreign != original
foreign_clean = foreign.read_bytes()
foreign.write_bytes(pristine)
assert run('original', 'miss', identity) == foreign and foreign.read_bytes() == foreign_clean
assert run('original', 'hit', identity) == foreign
