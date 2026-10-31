#!/usr/bin/env python3
"""Independent controls for slot supplies, rank views and integer state stores."""
from pathlib import Path
import argparse, hashlib, json, types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference-producer', type=Path, required=True)
    p.add_argument('--reference-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    hp = ROOT/'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('guard'); H.__file__ = str(hp)
    exec(compile(hp.read_bytes(), str(hp), 'exec'), H.__dict__)
    controls = HERE/'design-controls'
    oracle = H.load(controls/'oracle.json')
    raw = (controls/'FrozenClassDemand.hs').read_bytes()
    H.require(H.sha(controls/'FrozenClassDemand.hs') == oracle['frozen_sha256'], 'frozen oracle bytes')
    restored = raw.replace(b'module FrozenClassDemand where {', b'module Bootstrap.ClassDemand where {')
    H.require(hashlib.sha256(restored).hexdigest() == oracle['source_sha256'], 'module-only oracle adaptation')
    inventory=oracle['identity_inventory']
    raw=(controls/'FrozenIdentityInventory.hs').read_bytes()
    H.require(hashlib.sha256(raw).hexdigest()==inventory['frozen_sha256'],'frozen identity inventory')
    body=raw[raw.index(b'  typeIdentities ::'):raw.rindex(b'}\n')]
    H.require(hashlib.sha256(body).hexdigest()==inventory['body_sha256'],'unchanged identity collector bodies')
    H.check_pins({str(ROOT/k):v for k,v in inventory['dependencies'].items()})
    identity_helper = ROOT/'tools/shared/builtin_prelude_identity.py'
    identity_module = H.module(identity_helper, 'design_builtin_identity')
    identity, _ = identity_module.source_identity(ROOT)
    literal = (ROOT/'bootstrap/MLF/BuiltinPreludeData.hs').read_bytes()
    H.require(literal.count(b'builtin-source-v1:') == 1 and literal.count(identity.encode()) == 1,
        'regenerate the canonical builtin before qualifying the changed source closure')
    manifest = H.load(ROOT/'shared-sources.json')
    inputs = [ROOT/x['path'] for x in manifest['modules']]
    inputs += list((ROOT/'host/ghc').rglob('*.hs')) + list(controls.iterdir())
    inputs += [Path(__file__), hp, identity_helper, ROOT/'shared-sources.json']
    pins = {str(f):H.sha(f) for f in inputs if f.is_file()}
    limits = dict(address_space_per_process_bytes=6*1024**3, disk_free_floor_bytes=5*1024**3,
        host_available_floor_bytes=3*1024**3, process_tree_rss_bytes=5*1024**3,
        max_work_bytes=2*1024**3, wall_seconds=600)
    record = dict(complete=False, performance_samples=0, inputs=pins, checks=[], oracle=oracle,
        builtin_source_identity=identity,
        narrow_scope='selects the lossless fallback on this host; not a 32-bit ABI emulation')
    save = lambda:H.save(out/'receipt.json',record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            auth = H.authenticate(a.reference_producer.resolve(), a.reference_source.resolve())
            for rel in ['host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c']:
                H.require(H.sha(ROOT/rel)==H.sha(a.reference_source/rel),'borrowed C object source '+rel)
            H.Runner(out,limits).run([auth['ghc']['path'],'--make','-j1','-O0','-fno-code','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns',
                '-Werror=incomplete-uni-patterns','-package-env','-','-i',
                *['-i'+str(ROOT/x) for x in manifest['source_roots']],
                '-odir',out/'typecheck-objects','-hidir',out/'typecheck-objects',
                *[ROOT/x['path'] for x in manifest['modules']]],ROOT,out/'full-typecheck',timed=False)
            record['checks'].append('all shared source typecheck');save()
            for label,flags in [('O0',['-O0']),('O2',['-O2']),('O2-narrow',['-O2','-DMLF_TEST_NARROW_INT_TABLE'])]:
                objects=out/(label+'-objects');binary=out/(label+'-binary')
                common=['-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns',
                    '-Werror=incomplete-uni-patterns','-package-env','-','-i','-i'+str(controls),
                    *['-i'+str(ROOT/x) for x in manifest['source_roots']]]
                run=lambda name,argv:H.Runner(out,limits).run(argv,ROOT,out/name,timed=False)
                run(label+'-build',[auth['ghc']['path'],'--make','-j1',*flags,*common,
                    '-odir',objects,'-hidir',objects,controls/'Main.hs',
                    a.reference_producer/'host.o',a.reference_producer/'supervisor.o','-o',binary])
                run(label+'-run',[binary])
                H.require((out/(label+'-run/stdout')).read_bytes().startswith(b'PASS index design:'),'all design controls')
                H.require(not (out/(label+'-run/stderr')).read_bytes(),'no control stderr')
                record['checks'].append(label);save()
            H.check_pins(pins)
            H.authenticate(a.reference_producer.resolve(),a.reference_source.resolve())
            record['complete']=True;save()
    except BaseException as error:
        record['error']=repr(error);save();raise
    print('PASS independent index design qualification: '+', '.join(record['checks']),flush=True)

if __name__=='__main__':main()
