#!/usr/bin/env python3
"""Finite permission-value, physical-graph and demand controls against frozen HEAD."""
from pathlib import Path
import argparse
import hashlib
import shutil
import subprocess
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MODULE = 'libraries/mlf-inference/Bootstrap/Graph.hs'
BASELINE = '01ef8e70741c9f9ac4f27e489d059c96a4b33df5'
BASELINE_SHA = 'c515ef78483563eea91a4d9a26a0ef3165586961f7d3271d4a470816951aa6b4'
EXPECTED = (
    'PASS 720 permission views and admission decisions\n'
    'PASS admitted cache sharing and fallback isolation\n'
    'PASS 10 authored demand and exception-order cases\n'
    'PASS 720 exact public graph and first-error results\n').encode()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--producer', type=Path, required=True)
    p.add_argument('--producer-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--optimization', choices=['0', '2'], required=True)
    a = p.parse_args()
    out = a.output.resolve()
    producer = a.producer.resolve()
    hp = ROOT/'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('transport'); H.__file__ = str(hp)
    exec(compile(hp.read_bytes(), str(hp), 'exec'), H.__dict__)
    H.require(not out.exists() and not out.is_relative_to(producer)
              and not producer.is_relative_to(out), 'fresh isolated output')
    out.mkdir(parents=True)
    record = dict(complete=False, performance_samples=0, optimization=a.optimization,
                  baseline_ref=BASELINE, commands=[])
    save = lambda: H.save(out/'receipt.json', record)
    save()
    limits = dict(address_space_per_process_bytes=6*1024**3, disk_free_floor_bytes=5*1024**3,
                  host_available_floor_bytes=3*1024**3, max_work_bytes=3*1024**3,
                  process_tree_rss_bytes=5*1024**3, wall_seconds=600)
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth = H.authenticate(producer, a.producer_source)
            frozen = subprocess.check_output(['git', 'show', BASELINE+':'+MODULE], cwd=ROOT)
            H.require(hashlib.sha256(frozen).hexdigest() == BASELINE_SHA, 'frozen full Graph oracle')
            sources = {}
            for name, raw in [('LegacyGraph', frozen), ('CandidateGraph', (ROOT/MODULE).read_bytes())]:
                before = b'module Bootstrap.Graph where {'
                after = ('module '+name+' where {').encode()
                H.require(raw.count(before) == 1 and after not in raw, 'unique module header')
                changed = raw.replace(before, after)
                H.require(changed.replace(after, before) == raw, 'module-only reversible adaptation')
                path = out/(name+'.hs'); path.write_bytes(changed); sources[name] = path
            objects = out/'objects'; shutil.copytree(producer/'objects', objects)
            for suffix in ['.o', '.hi']: (objects/('Main'+suffix)).unlink(missing_ok=True)
            original_objects = H.file_pins(objects)
            H.require(all(H.sha(producer/Path(path).relative_to(out)) == digest
                          for path, digest in original_objects.items()), 'unchanged borrowed producer objects')
            pins = {str(path): H.sha(path) for path in [hp, Path(__file__), HERE/'Main.hs', ROOT/MODULE,
                    producer/'receipt.json', producer/'host.o', producer/'supervisor.o', *sources.values()]}
            record.update(inputs=pins, authentication=auth, borrowed_objects=original_objects)
            save()
            flags=[]; original=auth['flags']; i=0
            while i < len(original):
                flag=original[i]
                if flag in ['-odir','-hidir']: i+=2
                elif flag.startswith('-i'): i+=1
                else:
                    flags.append('-O'+a.optimization if flag in ['-O0','-O2'] else flag); i+=1
            flags += ['-i', '-i'+str(objects), '-odir', str(objects), '-hidir', str(objects)]
            def run(name, argv):
                record['commands'].append(H.Runner(out,limits).run(argv,ROOT,out/name)); save()
            ghc=auth['ghc']['path']
            for source in [*sources.values(),HERE/'Main.hs']:
                run('compile-'+source.stem,[ghc,*flags,'-c',source])
            H.check_pins(original_objects)
            binary=out/'controls'
            run('link',[ghc,*flags,*sorted(objects.rglob('*.o')),producer/'host.o',producer/'supervisor.o','-o',binary])
            run('run',[binary])
            H.require((out/'run/stdout').read_bytes()==EXPECTED, 'complete fixed control inventory')
            H.require(not (out/'run/stderr').read_bytes(), 'empty control stderr')
            H.check_pins(pins)
            H.require(H.authenticate(producer,a.producer_source)==auth, 'ordinary producer unchanged')
            record.update(complete=True, executable_sha256=H.sha(binary))
            save()
            print(EXPECTED.decode(),end='',flush=True)
    except BaseException as error:
        record['error']=repr(error); save(); raise


if __name__ == '__main__': main()
