#!/usr/bin/env python3
"""Independent controls for slot supplies, rank views and integer state stores."""
from pathlib import Path
import argparse, hashlib, json, types, subprocess, traceback

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
HISTORICAL_BASE = 'fc300bc9fdc389b585cbef0630fc8915d53e89c5'
HISTORICAL_TREE = '386f0b41ab5f9b39fca273f3040f51d73df924a1'
MAP_PATH = 'libraries/mlf-foundation/Bootstrap/Map.hs'
SET_PATH = 'libraries/mlf-foundation/Bootstrap/Set.hs'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def reversible(raw, replacements):
    changed = raw
    for old, new in replacements:
        require(changed.count(old) == 1 and new not in changed, 'unique oracle adaptation')
        changed = changed.replace(old, new)
    restored = changed
    for old, new in reversed(replacements):
        require(restored.count(new) == 1, 'unique inverse oracle adaptation')
        restored = restored.replace(new, old)
    require(restored == raw, 'exact inverse oracle adaptation')
    return changed


def isolated_sources(old_map, old_set, collector, inventory):
    require(set(inventory['dependencies']) == {MAP_PATH, SET_PATH}, 'exact frozen dependency inventory')
    for path, raw in ((MAP_PATH, old_map), (SET_PATH, old_set)):
        require(digest(raw) == inventory['dependencies'][path], 'frozen dependency bytes: ' + path)
    require(digest(collector) == inventory['frozen_sha256'], 'frozen identity inventory')
    start, end = b'  typeIdentities ::', b'}\n'
    require(collector.count(start) == 1 and collector.endswith(end), 'collector body delimiters')
    body = collector[collector.index(start):collector.rindex(end)]
    require(digest(body) == inventory['body_sha256'], 'unchanged identity collector bodies')
    result = {
        'FrozenDesignMap.hs': reversible(old_map, [(b'module Bootstrap.Map where {', b'module FrozenDesignMap where {')]),
        'FrozenDesignSet.hs': reversible(old_set, [
            (b'module Bootstrap.Set where {', b'module FrozenDesignSet where {'),
            (b'import qualified Bootstrap.Map as M;', b'import qualified FrozenDesignMap as M;')]),
        'FrozenDesignIdentityInventory.hs': reversible(collector, [
            (b'module FrozenIdentityInventory where {', b'module FrozenDesignIdentityInventory where {'),
            (b'import qualified Bootstrap.Set as Set;', b'import qualified FrozenDesignSet as Set;')]),
    }
    adapted = result['FrozenDesignIdentityInventory.hs']
    require(adapted[adapted.index(start):adapted.rindex(end)] == body, 'adapted collector body unchanged')
    return result


def historical_dependencies(root, output=subprocess.check_output):
    git = ['git', '--no-replace-objects', '-C', str(root)]
    tree = output([*git, 'rev-parse', HISTORICAL_BASE + '^{tree}'], timeout=30).decode().strip()
    require(tree == HISTORICAL_TREE, 'fixed historical dependency tree')
    return tuple(output([*git, 'show', HISTORICAL_BASE + ':' + path], timeout=30)
                 for path in (MAP_PATH, SET_PATH))


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
    p.add_argument('--reference-producer', type=Path, required=True)
    p.add_argument('--reference-source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    record = dict(complete=False, performance_samples=0, checks=[], stage='created')
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
    raw = (controls/'FrozenClassDemand.hs').read_bytes()
    H.require(H.sha(controls/'FrozenClassDemand.hs') == oracle['frozen_sha256'], 'frozen oracle bytes')
    restored = raw.replace(b'module FrozenClassDemand where {', b'module Bootstrap.ClassDemand where {')
    H.require(hashlib.sha256(restored).hexdigest() == oracle['source_sha256'], 'module-only oracle adaptation')
    inventory=oracle['identity_inventory']
    raw=(controls/'FrozenIdentityInventory.hs').read_bytes()
    H.require(hashlib.sha256(raw).hexdigest()==inventory['frozen_sha256'],'frozen identity inventory')
    body=raw[raw.index(b'  typeIdentities ::'):raw.rindex(b'}\n')]
    H.require(hashlib.sha256(body).hexdigest()==inventory['body_sha256'],'unchanged identity collector bodies')
    stage('historical-dependencies')
    old_map, old_set = historical_dependencies(ROOT)
    stage('isolate-frozen-dependencies')
    generated = isolated_sources(old_map, old_set, raw, inventory)
    isolated = out/'frozen-dependencies'; isolated.mkdir()
    for name, source in generated.items():
        (isolated/name).write_bytes(source)
    record['historical_dependencies'] = dict(commit=HISTORICAL_BASE, tree=HISTORICAL_TREE,
        original_sha256={MAP_PATH: digest(old_map), SET_PATH: digest(old_set),
                         'FrozenIdentityInventory.hs': digest(raw)},
        generated_sha256={name: digest(source) for name, source in generated.items()},
        adaptation='unique module/import replacements with exact inverse bytes; collector bodies unchanged',
        shared_base='Types (including Map/Set data constructors), Std, Primitive, X.Syntax and host/runtime remain current; historical Map/Set algorithms are isolated')
    save()
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
    inputs += [Path(__file__), hp, identity_helper, ROOT/'shared-sources.json', *isolated.iterdir()]
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
            auth = H.authenticate(a.reference_producer.resolve(), a.reference_source.resolve())
            for rel in ['host/ghc/cbits/host.c','runtime/mlf_process_supervisor.c']:
                H.require(H.sha(ROOT/rel)==H.sha(a.reference_source/rel),'borrowed C object source '+rel)
            stage('full-typecheck')
            H.Runner(out,limits).run([auth['ghc']['path'],'--make','-j1','-O0','-fno-code','-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns',
                '-Werror=incomplete-uni-patterns','-package-env','-','-i',
                *['-i'+str(ROOT/x) for x in manifest['source_roots']],
                '-odir',out/'typecheck-objects','-hidir',out/'typecheck-objects',
                *[ROOT/x['path'] for x in manifest['modules']]],ROOT,out/'full-typecheck',timed=False)
            record['checks'].append('all shared source typecheck');save()
            for label,flags in [('O0',['-O0']),('O2',['-O2']),('O2-narrow',['-O2','-DMLF_TEST_NARROW_INT_TABLE'])]:
                objects=out/(label+'-objects');binary=out/(label+'-binary')
                common=['-fpedantic-bottoms','-fno-state-hack','-Werror=incomplete-patterns',
                    '-Werror=incomplete-uni-patterns','-package-env','-','-i','-i'+str(isolated),'-i'+str(controls),
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
            H.authenticate(a.reference_producer.resolve(),a.reference_source.resolve())
            record['complete']=True;record['stage']='complete';save()
    except BaseException as error:
        record['error']=repr(error);save();raise

if __name__=='__main__':main()
