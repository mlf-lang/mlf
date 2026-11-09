#!/usr/bin/env python3
"""Measure verification against already warm, identical candidate snapshots."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler',type=Path)
p.add_argument('study',type=Path,help='completed compare.py output, with original sources restored')
p.add_argument('output',type=Path)
a = p.parse_args()
tool = Path(__file__).resolve().parents[1]/'foundation-query/compare.py'
loader = importlib.util.spec_from_file_location('foundation_compare',tool)
compare = importlib.util.module_from_spec(loader)
loader.loader.exec_module(compare)
study = a.study.resolve()
output = a.output.resolve()
output.mkdir(parents=True,exist_ok=False)
report = json.loads((study/'results.json').read_bytes())
if not report['complete'] or compare.digest(a.compiler) != report['binaries']['candidate']:
    raise ValueError('benchmark compiler or run does not match')
source = study/'1-candidate'
spec = study/'foundation.spec'
samples = []
for index, mode in enumerate(['sample','full','full','sample']):
    cache, builtin = study/'cache', study/'builtin'
    if cache.exists() or builtin.exists():
        raise ValueError('active paths in use')
    # Stage independent copies at the same paths encoded in the measured spec.
    with tempfile.TemporaryDirectory(dir=study) as staging:
        temporary = Path(staging)
        shutil.copytree(source/'cache',temporary/'cache')
        shutil.copytree(source/'builtin',temporary/'builtin')
        (temporary/'cache').rename(cache)
        try:
            (temporary/'builtin').rename(builtin)
            try:
                prefix = output/(str(index)+'-'+mode)
                stats = compare.compile_crate(a.compiler.resolve(strict=True),spec,prefix,mode=='full')
                query = json.loads(prefix.with_suffix('.queries').read_bytes())
                if (query['inferred_groups'],query['reused_groups']) != (0,504):
                    raise ValueError('unexpected warm misses')
                for ext in ('.mlfci','.mlfco'):
                    if prefix.with_suffix(ext).read_bytes() != (source/('cold'+ext)).read_bytes():
                        raise ValueError('warm artifact mismatch')
                samples.append({'mode':mode,'verified_by_policy':sum(mode=='full' or int(g['query_key'][:2],16)<8
                               for g in query['groups']),**stats})
            finally:
                builtin.rename(temporary/'builtin')
        finally:
            cache.rename(temporary/'cache')
    (output/'results.json').write_text(json.dumps(samples,indent=2)+'\n')
