#!/usr/bin/env python3
"""Fixed A/B blocks using the existing shape worker and exact-child guard.

The JSON configuration chooses immutable inputs, independent raw references,
ordinary producers and the complete schedule before the first measured leg.
Failure stops the window; no sample replacement or adaptive extension.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    hp = HERE.parent/'a1-private-index/helper.py'
    H = types.ModuleType('unchanged_helper'); H.__file__ = str(hp)
    exec(compile(hp.read_bytes(), str(hp), 'exec'), H.__dict__)
    cfg = H.load(args.config.resolve())
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    source_plan = H.load(Path(cfg['workload']))
    controls = H.load(Path(cfg['controls']))
    H.require(controls['complete'] and controls['ordinary_candidate_authenticated'], 'qualified ordinary process behavior')
    sides = cfg['sides']
    H.require(set(sides) == {'A', 'B'}, 'explicit performance baseline and candidate')
    auth = {side: H.authenticate(Path(v['producer']), Path(v['source'])) for side,v in sides.items()}
    pins = {str(p.resolve()): H.sha(p) for p in [args.config, Path(cfg['workload']), Path(cfg['controls']),
        Path(__file__), hp, HERE/'with_scope.py']}
    for name in ['compare.py', 'with_scope.py']:
        shutil.copy2(HERE/name, out/name)
    shutil.copy2(args.config, out/'config-used.json')
    if cfg.get('gates'):
        H.require(H.load(cfg['gates'])['complete'], 'complete retained semantic gate')
        pins[cfg['gates']] = H.sha(cfg['gates'])
    if cfg['purpose'] == 'confirmation':
        H.require(cfg.get('gates') and cfg.get('analysis'), 'confirmation protocol and full gates frozen')
        analyzer = Path(cfg['analysis']['analyzer'])
        H.require(H.sha(analyzer) == cfg['analysis']['analyzer_sha256'], 'analysis frozen before first sample')
        pins[str(analyzer)] = cfg['analysis']['analyzer_sha256']
    refs = {}; cases = {}; plans = {}
    if cfg['kind'] == 'shapes':
        worker = HERE.parent/'compiler-shapes/worker.py'
        pins[str(worker)] = H.sha(worker)
        shutil.copy2(worker, out/'shape-worker.py')
        cases = {c['id']: c for c in source_plan['cases'] if c['id'] in cfg['references']}
        H.require(set(cases) == set(cfg['references']), 'all explicitly selected cases exist')
        for path,digest in source_plan['inputs'].items():
            # Historical generator/runner code is evidence, not executed here.
            # Check its archived original bytes; the current worker is pinned
            # separately above. Generated programs and dependencies stay fixed.
            if Path(path).parent == Path(sides['A']['source'])/'tools/performance/compiler-shapes':
                path = str(Path(cfg['workload']).parent/'scripts'/Path(path).name)
            pins[path] = digest
        for side,v in sides.items():
            plans[side] = out/('worker-'+side+'.json')
            H.save(plans[side], {'setup': {**source_plan['setup'], 'producer': v['producer']}, 'cases': list(cases.values())})
            pins[str(plans[side])] = H.sha(plans[side])
    else:
        H.require(cfg['kind'] == 'target', 'known workload kind')
        pins.update(source_plan['input_files'])
        cases = {'compiler': None}
    for case,reference in cfg['references'].items():
        prefix = Path(reference['prefix']); qpath = Path(reference['queries'])
        q = H.load(qpath)
        H.require(q['reused_groups'] == 0 and q['inferred_groups'] == len(q['groups']) > 0
            and all(g['cached'] is False for g in q['groups']), 'independent reference was fresh')
        raw = {s: Path(str(prefix)+s).read_bytes() for s in ['.mlfci', '.mlfco']}
        refs[case] = {'raw': raw, 'groups': [{k:g[k] for k in ['id','members']} for g in q['groups']]}
        pins[str(qpath)] = H.sha(qpath)
        for s in raw: pins[str(prefix)+s] = H.sha(str(prefix)+s)
    H.require(set(cases) == set(refs), 'a reference for every case')
    for v in sides.values():
        for name in ['receipt.json', 'bin/emlf']: pins[str(Path(v['producer'])/name)] = H.sha(Path(v['producer'])/name)
    H.require(cfg['blocks'] and all(b['case'] in cases and b['order'] in ['ABBA','BAAB'] for b in cfg['blocks']), 'balanced fixed blocks')
    boot = subprocess.check_output(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],text=True).strip()
    plan = {**cfg, 'inputs': pins, 'authentication': auth, 'host': H.host(), 'boot_session':boot,
        'scope': 'both sides use MLF_BUILD_SCOPE equal to the runner-owned process group',
        'timing': 'unchanged exact-child wait4; scope wrapper included equally; preparation and verification excluded',
        'failure_rule': 'stop and retain any failed run; no replacement or extra samples'}
    H.save(out/'plan.json', plan); plan_sha = H.sha(out/'plan.json')
    record = {'complete': False, 'plan_sha256': plan_sha, 'runs': [], 'blocks': []}
    def save(): H.save(out/'receipt.json', record)
    save()
    try:
        with H.SerialLock(ROOT/'.mlf-build'):
            H.check_pins(pins)
            for block_index,block in enumerate(cfg['blocks']):
                H.require(H.tree_bytes(out) <= cfg['max_output_bytes'], 'retained output bound between complete blocks')
                blockdir = out/('block-%02d'%block_index); blockdir.mkdir()
                for position,side in enumerate(block['order']):
                    H.require(H.sha(out/'plan.json') == plan_sha, 'frozen plan unchanged')
                    leg = blockdir/('%d-%s'%(position,side)); leg.mkdir()
                    build = leg/'build'; case = block['case']; ref = refs[case]
                    row = {'block': block_index, 'position': position, 'side': side, 'case': case, 'complete': False}
                    record['runs'].append(row); save()
                    if cfg['kind'] == 'shapes':
                        argv = [sys.executable, '-B', worker, '--plan', plans[side], '--case', case, '--lane', 'mlf', '--out', build]
                    else:
                        build.mkdir(); query = build/'queries'; query.mkdir()
                        fields = list(source_plan['spec_fields']); fields[6] = str(query); fields[7] = str(build/'unused-builtin')
                        spec = build/'crate.spec'; spec.write_text(''.join(str(len(x))+':'+x for x in fields))
                        argv = [Path(sides[side]['producer'])/'bin/emlf', '--compile-crate', spec, '-o', build/'unit']
                    row['command'] = H.Runner(leg, cfg['limits']).run([sys.executable,'-B',HERE/'with_scope.py',*argv],ROOT,leg/'command',timed=True)
                    H.require(H.tree_bytes(leg) <= cfg['limits']['max_work_bytes'], 'completed leg output within the existing work bound')
                    q = H.load(build/'unit.queries')
                    groups = [{k:g[k] for k in ['id','members']} for g in q['groups']]
                    H.require(q['inferred_groups'] == len(ref['groups']) == len(q['groups']) and q['reused_groups'] == 0
                        and all(g['cached'] is False for g in q['groups']) and groups == ref['groups'], 'fresh ordered target groups')
                    H.require({s:(build/('unit'+s)).read_bytes() for s in ref['raw']} == ref['raw'], 'raw checked bytes equal independent baseline reference')
                    if cfg['kind'] == 'shapes':
                        row['stages'] = H.load(build/'stages.json'); H.require(row['stages']['complete'], 'all ordinary native compilation stages')
                        for index,(value,expected) in enumerate(zip(cases[case]['inputs'],cases[case]['expected_stdout'])):
                            d = leg/('oracle-%d'%index)
                            H.Runner(leg,cfg['limits']).run([build/'program',str(value)],ROOT,d)
                            H.require((d/'stdout').read_bytes() == expected.encode() and not (d/'stderr').read_bytes(), 'independent native output oracle')
                    row.update(complete=True, fresh=q['inferred_groups'], reused=0, raw_bytes_equal=True)
                    save(); print(f'block {block_index+1}/{len(cfg["blocks"])} {position+1}/4 {case} {side}: {row["command"]["wall_seconds"]:.3f}s; fresh/raw pass',flush=True)
                # Inventory and remove only this block's owned disposable query
                # caches, after all timing legs. Keep checked bytes and logs.
                for leg in sorted(blockdir.iterdir()):
                    query = leg/'build/queries'
                    H.save(leg/'cache-inventory.json',{str(p.relative_to(query)):{'bytes':p.stat().st_size,'sha256':H.sha(p)}
                        for p in sorted(query.rglob('*')) if p.is_file()})
                    shutil.rmtree(query)
                record['blocks'].append({'index':block_index,'complete':True});save()
            H.check_pins(pins)
            H.require(subprocess.check_output(['/usr/sbin/sysctl','-n','kern.bootsessionuuid'],text=True).strip() == boot, 'same boot session')
            H.require({s:H.authenticate(Path(v['producer']),Path(v['source'])) for s,v in sides.items()} == auth, 'ordinary producers unchanged')
            record['complete'] = True;save()
    except BaseException as error:
        record['error'] = repr(error); save(); raise


if __name__ == '__main__': main()
