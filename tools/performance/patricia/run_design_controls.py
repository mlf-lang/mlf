#!/usr/bin/env python3
"""Independent controls for slot supplies, rank views and integer state stores."""
from pathlib import Path
import argparse, json, sys, types, traceback

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'patricia-design/'
TYPECHECK = 'all shared source typecheck'
OPTIMIZATIONS = [('O0', ['-O0']), ('O2', ['-O2']), ('O2-narrow', ['-O2', '-DMLF_TEST_NARROW_INT_TABLE'])]
LABELS = [TYPECHECK, *[label for label, _ in OPTIMIZATIONS]]


def run_stage(record, save, stage, action):
    record['stage'] = stage
    save()
    try:
        return action()
    except BaseException as error:
        record.update(complete=False, error=repr(error), traceback=traceback.format_exc())
        save()
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    listing = '--framework-list' in sys.argv[1:]
    p.add_argument('--framework-list', action='store_true')
    p.add_argument('--reference-producer', type=Path, required=not listing)
    p.add_argument('--reference-source', type=Path, required=not listing)
    p.add_argument('--output', type=Path, required=not listing)
    a = p.parse_args()
    exact = select(PREFIX, LABELS)
    planned = [exact] if exact is not None else LABELS
    if a.framework_list:
        print(inventory_json(PREFIX, planned))
        return
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    record = dict(complete=False, performance_samples=0, checks=[], planned_checks=planned, stage='created')
    save = lambda: (out/'receipt.json').write_text(json.dumps(record, indent=2)+'\n')
    save()
    run_stage(record, save, 'preflight-and-qualification', lambda: qualify(a, out, record, save))
    print('PASS independent index design qualification: '+', '.join(record['checks']),flush=True)


def qualify(a, out, record, save):
    def stage(name):
        record['stage'] = name
        save()
    stage('load-helper')
    hp = ROOT/'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('guard'); H.__file__ = str(hp)
    exec(compile(hp.read_bytes(), str(hp), 'exec'), H.__dict__)
    stage('frozen-oracles')
    controls = HERE/'design-controls'
    oracle = H.load(controls/'oracle.json')
    H.require(H.sha(controls/'FrozenClassDemand.hs') == oracle['frozen_sha256'], 'frozen oracle bytes')
    direct_path=a.reference_source.resolve()/'tools/shared/test_direct.py'
    direct=H.module(direct_path,'design_control_authentication')
    def authenticate():
        producer=a.reference_producer.resolve()
        return direct.authenticate_build(producer/'receipt.json',producer/'bin',root=a.reference_source.resolve())
    stage('builtin-identity')
    identity_helper = ROOT/'tools/shared/builtin_prelude_identity.py'
    identity_module = H.module(identity_helper, 'design_builtin_identity')
    identity, _ = identity_module.source_identity(ROOT)
    literal = (ROOT/'bootstrap/MLF/BuiltinPreludeData.hs').read_bytes()
    H.require(literal.count(b'builtin-source-v1:') == 1 and literal.count(identity.encode()) == 1,
        'regenerate the canonical builtin before qualifying the changed source closure')
    manifest = H.load(ROOT/'shared-sources.json')
    inputs = [ROOT/x['path'] for x in manifest['modules']]
    inputs += list((ROOT/'host/ghc').rglob('*.hs')) + list(controls.iterdir())
    inputs += [Path(__file__), hp, direct_path, identity_helper, ROOT/'shared-sources.json', ROOT/'tools/testing/receipt_selection.py']
    pins = {str(f):H.sha(f) for f in inputs if f.is_file()}
    limits = dict(address_space_per_process_bytes=6*1024**3, disk_free_floor_bytes=5*1024**3,
        host_available_floor_bytes=3*1024**3, process_tree_rss_bytes=5*1024**3,
        max_work_bytes=2*1024**3, wall_seconds=600)
    record.update(inputs=pins, oracle=oracle,
        builtin_source_identity=identity,
        narrow_scope='selects the lossless fallback on this host; not a 32-bit ABI emulation')
    save()
    try:
        stage('qualification-lock')
        with H.SerialLock(ROOT/'.mlf-build'):
            stage('authenticate-producer')
            auth = authenticate()
            for rel in ['host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c']:
                H.require(H.sha(ROOT/rel)==H.sha(a.reference_source/rel),'borrowed C object source '+rel)
            if TYPECHECK in record['planned_checks']:
                stage('full-typecheck')
                H.Runner(out,limits).run([auth['ghc']['path'],'--make','-j1','-O0','-fno-code','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns',
                    '-Werror=incomplete-uni-patterns','-package-env','-','-i',
                    *['-i'+str(ROOT/x) for x in manifest['source_roots']],
                    '-odir',out/'typecheck-objects','-hidir',out/'typecheck-objects',
                    *[ROOT/x['path'] for x in manifest['modules']]],ROOT,out/'full-typecheck',timed=False)
                record['checks'].append(TYPECHECK);save()
            for label,flags in OPTIMIZATIONS:
                if label not in record['planned_checks']:
                    continue
                objects=out/(label+'-objects');binary=out/(label+'-binary')
                common=['-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns',
                    '-Werror=incomplete-uni-patterns','-package-env','-','-i','-i'+str(controls),
                    *['-i'+str(ROOT/x) for x in manifest['source_roots']]]
                run=lambda name,argv:H.Runner(out,limits).run(argv,ROOT,out/name,timed=False)
                stage(label+'-build')
                run(label+'-build',[auth['ghc']['path'],'--make','-j1',*flags,*common,
                    '-odir',objects,'-hidir',objects,controls/'Main.hs',
                    a.reference_producer/'host.o',a.reference_producer/'supervisor.o','-o',binary])
                stage(label+'-run')
                run(label+'-run',[binary])
                H.require((out/(label+'-run/stdout')).read_bytes().startswith(b'PASS index design:'),'all design controls')
                H.require(not (out/(label+'-run/stderr')).read_bytes(),'no control stderr')
                record['checks'].append(label);save()
            H.check_pins(pins)
            H.require(authenticate()==auth,'ordinary producer unchanged')
            record['complete']=True;record['stage']='complete';save()
    except BaseException as error:
        record['error']=repr(error);save();raise

if __name__=='__main__':main()
