#!/usr/bin/env python3
"""Build both source drivers into one executable with one real compiler digest."""
import argparse
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('baseline', help='actual PR head SHA, with its objects available locally')
p.add_argument('output', type=Path)
p.add_argument('--baseline-only', action='store_true')
a = p.parse_args()
out = a.output.resolve()
out.mkdir(parents=True, exist_ok=True)
if not re.fullmatch(r'[0-9a-f]{40}', a.baseline):
    p.error('supply the full verified PR head commit SHA')
owners = {'libraries/mlf-crates/Bootstrap/CrateQuery.hs', 'libraries/mlf-crates/Bootstrap/CrateSession.hs'}
delta = subprocess.check_output(['git', 'diff', '--name-only', a.baseline, '--', 'libraries', 'host/ghc',
                                 'runtime', 'bootstrap', 'shared-sources.json', 'mlf-shared.cabal'], cwd=ROOT)
if set(delta.decode().splitlines()) - owners:
    p.error('another compiler input differs from the baseline, so the two drivers cannot share this build')
variants = ['Old', 'OldProbe'] if a.baseline_only else ['Old', 'OldProbe', 'New', 'NewProbe']

def replace_once(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError('non-unique instrumentation site: ' + anchor)
    return source.replace(anchor, replacement)

for variant in variants:
    for owner in ['CrateQuery', 'CrateSession']:
        relative = 'libraries/mlf-crates/Bootstrap/' + owner + '.hs'
        source = (subprocess.check_output(['git', 'show', a.baseline + ':' + relative],
                                          cwd=ROOT).decode() if variant.startswith('Old')
                  else (ROOT / relative).read_text())
        source = replace_once(source, 'module Bootstrap.' + owner, 'module ' + variant + owner)
        if owner == 'CrateSession':
            source = replace_once(source, 'import qualified Bootstrap.CrateQuery as Query;',
                                  'import qualified ' + variant + 'CrateQuery as Query;')
            if variant.endswith('Probe'):
                source = replace_once(source, '  import MLF.Primitive;', '  import Probe;\n  import MLF.Primitive;')
                for old, new in [
                    ('writeFile (cacheDir ++ "/query-key.new") key;', 'writeKey (cacheDir ++ "/query-key.new") key;'),
                    ('digest <- fileDigest (cacheDir ++ "/query-key.new");', 'digest <- hashKey (cacheDir ++ "/query-key.new");'),
                    ('observed <- Query.readSourceCacheFileWithWindow', 'observed <- readRecord (Query.readSourceCacheFileWithWindow'),
                    ('bindings datatypes names destination;', 'bindings datatypes names destination);'),
                    ('ioReturn (case observed of', 'admit (ioReturn (case observed of')
                ]:
                    source = replace_once(source, old, new)
                source = replace_once(source, '})\n        } else ioReturn ((,) [] (Left "cache miss"));',
                                      '}))\n        } else ioReturn ((,) [] (Left "cache miss"));')
        (out / (variant + owner + '.hs')).write_text(source)

imports = '\n'.join('import qualified ' + v + 'CrateSession as ' + v for v in variants)
cases = '\n'.join(f'    ["{v}", spec, prefix] -> run ({v}.compileSpecFile (B.literal spec) (B.literal prefix))' for v in variants)
(out / 'Main.hs').write_text(f'''module Main where
import Prelude
import qualified Bootstrap.Crate as C
import qualified Bootstrap.Types as T
import qualified MLF.Host.Base as B
import MLF.Host.IO (runEntry)
import System.Environment (getArgs)
{imports}
run op = runEntry (op >>= \\r -> case r of {{ T.Left err -> fail (B.unpack err); T.Right _ -> pure () }})
main = do
  args <- getArgs
  case args of
    ["builtin", prefix] -> run (C.ensureBuiltin (B.literal prefix))
{cases}
    _ -> fail "unknown study command"
''')
roots = json.loads((ROOT / 'shared-sources.json').read_text())['source_roots']
subprocess.run(['ghc', '--make', '-j3', '-O2', '-fpedantic-bottoms', '-fno-state-hack',
                '-package-env', '-', '-i', '-i' + str(out), '-i' + str(HERE),
                *['-i' + str(ROOT / x) for x in roots], '-outputdir', str(out/'obj'),
                '-optc-I' + str(ROOT/'runtime'), str(out/'Main.hs'),
                str(ROOT/'host/ghc/cbits/host.c'), str(ROOT/'runtime/mlf_process_supervisor.c'),
                '-o', str(out/'study')], cwd=out, check=True)
