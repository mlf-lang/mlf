#!/usr/bin/env python3
"""Record serial same-source shape builds and report their performance checks."""
from pathlib import Path
from dataclasses import replace
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
import command_runner
import fit_growth
import framework_results as framework
import generate as G
import compiler_reference
import query_cache as Q
import provenance
import worker


def native_target_policy(producer, triple):
    emlf = Path(producer) / 'bin/emlf'
    help_text = subprocess.check_output([emlf, '--help'], text=True)
    option = '--native-target-flags'
    if option not in help_text.split():
        return {'origin': 'legacy native driver', 'flags': []}
    flags = json.loads(subprocess.check_output([emlf, option, triple], text=True))
    if not isinstance(flags, list) or not all(isinstance(flag, str) and flag.startswith('-') for flag in flags):
        raise ValueError(f'Invalid native target flags from {emlf}: {flags!r}')
    return {'origin': option, 'flags': flags}


ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent


def registry():
    return json.loads((HERE/'matrix.json').read_text())


def lanes_for(index,repeats):
    """Alternate which compiler starts each pair within and across cells."""
    lanes=[]
    for round_index in range(repeats):
        first='ghc' if (round_index+index)%2==0 else 'mlf'
        lanes.extend([first,'mlf' if first=='ghc' else 'ghc'])
    return lanes


def interleave_pairs(schedule, repeats, rng):
    """Visit every cell once per round, keeping each compiler pair adjacent."""
    rounds = [[] for _ in range(repeats)]
    for index in range(0, len(schedule), 2):
        pair = schedule[index:index + 2]
        rounds[pair[0]['position'] // 2].append(pair)
    interleaved = []
    for pairs in rounds:
        rng.shuffle(pairs)
        for pair in pairs:
            interleaved.extend(pair)
    return interleaved


def with_reference(schedule):
    """Place the candidate between the two controls, reversing all three next round."""
    result = []
    for i in range(0, len(schedule), 2):
        first = schedule[i]
        lanes = ('reference', 'mlf', 'ghc') if first['lane'] == 'mlf' else ('ghc', 'mlf', 'reference')
        start = 3 * (first['position'] // 2)
        result.extend(dict(case=first['case'], position=start+j, lane=lane) for j,lane in enumerate(lanes))
    return result


def main():
    data=registry()
    parser=argparse.ArgumentParser(description=__doc__)
    listing = '--framework-list' in sys.argv[1:]
    parser.add_argument('--framework-list',action='store_true')
    parser.add_argument('--setup',type=Path,required=not listing)
    parser.add_argument('--output',type=Path,required=not listing)
    parser.add_argument('--baseline-family')
    parser.add_argument('--sweep-reference', help=argparse.SUPPRESS)
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--framework-child',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--record-only',action='store_true',
                        help='leave growth reporting to the caller')
    parser.add_argument('--family',action='append',choices=G.FAMILIES+('baseline',))
    parser.add_argument('--size',action='append',type=int)
    parser.add_argument('--repeats',type=int,default=data['repeats'])
    parser.add_argument('--cohort')
    parser.add_argument('--interleave-pairs',action='store_true',
                        help='visit each case once per paired round in seeded random order')
    parser.add_argument('--cohort-output-gib',type=int,default=8,
                        help='aggregate retained evidence budget in GiB (default 8)')
    parser.add_argument('--endpoint',default=data['default_endpoint'],choices=sorted(data['endpoints']))
    args=parser.parse_args()
    if args.cohort_output_gib <= 0:
        parser.error('--cohort-output-gib must be positive')
    sizes=args.size or ((8,) if args.pilot else tuple(data['sizes']))
    if not all(0<n<=8192 for n in sizes):
        parser.error('sizes must be bounded and positive')
    matrix=data['matrices']['default']
    families=args.family or matrix['families']
    if 'baseline' not in families and fit_growth.include_baseline(families,sizes,matrix['baseline'] and not args.pilot):
        families=['baseline', *families]
    cells = G.coordinates(sizes, families)
    if args.framework_list:
        framework.list_cases(cells, args.pilot)
        return
    cells, selected = framework.select(cells, args.pilot, exclude=args.framework_child)
    if not cells or len(cells) != len(set(cells)):
        parser.error('shape coordinates must be nonempty and distinct')
    ids = selected if framework.active() and not args.framework_child else []
    if ids:
        framework.events.plan(ids)
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    H=command_runner.load_helper()
    setup=H.load(args.setup.resolve()); H.require(setup['complete'],'qualified fixed dependencies')
    H.require(setup.get('endpoint')==args.endpoint,'setup belongs to endpoint profile '+str(setup.get('endpoint'))
              +', not '+args.endpoint)
    setup.setdefault('source', str(ROOT))
    endpoint=data['endpoints'][args.endpoint]
    auth=H.authenticate(Path(setup['producer']),Path(setup.get('source',ROOT)))
    generated = [out, args.setup.parent, setup['producer']]
    if args.sweep_reference:
        sweep_dir = out.parent.parent
        generated.extend([out.parent, sweep_dir/'summary.csv', sweep_dir/'summary.md', sweep_dir/'growth.json'])
    selection = compiler_reference.select_revision(setup['source'], generated) if not args.pilot else None
    if args.sweep_reference and selection != json.loads(args.sweep_reference):
        raise ValueError('candidate revision or baseline changed during sweep')
    reference = compiler_reference.prepare(setup, selection, auth['ghc']['path']) if selection else None
    repeats=1 if args.pilot else args.repeats
    H.require(repeats>=1,'positive repeats')
    sizes = list(dict.fromkeys(size for _, size in cells if size))
    families = list(dict.fromkeys(family for family, _ in cells))
    cases=G.generate(out/'sources',sizes=sizes,families=families,baseline_family=args.baseline_family)
    H.require(args.endpoint=='crate-plan-v1' or not any(worker.dependencies(c) for c in cases),
              'the cold dependency family requires crate-plan-v1')
    seed=data['seed']; rng=random.Random(seed); order=list(cases);rng.shuffle(order)
    schedule=[]
    for index,case in enumerate(order):
        lanes=['ghc','mlf'] if args.pilot else lanes_for(index,repeats)
        for position,lane in enumerate(lanes):
            schedule.append({'case':case['id'],'position':position,'lane':lane})
    if args.interleave_pairs:
        schedule=interleave_pairs(schedule,repeats,rng)
    if reference:
        schedule = with_reference(schedule)
    lanes_per_round = 3 if reference else 2
    inputs={str(p.resolve()):H.sha(p) for p in [args.setup,Path(H.__file__),HERE/'command_runner.py',HERE/'bench.py',HERE/'run.py',HERE/'worker.py',HERE/'generate.py',
        HERE/'data_shapes.py',HERE/'rank_shapes.py',HERE/'fit_growth.py',HERE/'analyze.py',HERE/'compiler_reference.py',
        HERE/'framework_results.py',ROOT/'tools/testing/events.py',
        HERE/'matrix.json',HERE/'query_cache.py',HERE/'provenance.py',Q.SHARED/'artifact_binary_reference.py',
        Q.SHARED/'test_query_index.py',Q.SHARED/'artifact_binary_open.py',
        Path(setup['producer'])/'receipt.json',Path(setup['producer'])/'bin/emlf',
        Path(setup['ghc']),Path(setup['clang']),Path(setup['runtime']),Path(setup['builtin']+'.mlfci'),
        Path(setup['builtin']+'.mlfco')]}
    if reference:
        inputs.update({str(Path(reference['producer'])/'receipt.json'):reference['receipt_sha256'],
                       str(Path(reference['producer'])/'bin/emlf'):reference['emlf_sha256']})
    inputs.update(H.file_pins(Path(setup['package_db']).parent))
    inputs.update({c['source']:c['source_sha256'] for c in cases})
    inputs.update({lib['source']:lib['sha256'] for c in cases for lib in worker.dependencies(c)})
    # Per-command output stays bounded at 512 MiB; the cohort bound covers the
    # deliberately retained evidence (69 native executables, LLVM IR and GHC
    # objects for 31 cells). It is a bound, not a target: a 31-cell cohort uses
    # about 2.6 GiB, and the earlier 2 GiB carry-over stopped a run at leg 149.
    limits={**setup['limits'],'wall_seconds':90,'max_work_bytes':512*1024**2,
            'aggregate_cohort_bytes':args.cohort_output_gib*1024**3}
    identity=provenance.source_identity(ROOT, out)
    cohort=args.cohort or out.name
    plan={'purpose':'generator/transport qualification' if args.pilot else 'fixed measured shape matrix; paired build-time observations',
        'benchmark':{'schema':2,'suite':data['suite'],'suite_version':data['version'],'cohort':cohort,
            'endpoint':{'id':args.endpoint,**endpoint},'repeats':repeats,
            'families':sorted({c['family'] for c in cases}),'sizes':sorted({c['size'] for c in cases}),
            'cells':len(cases),'timed_compilations':0 if args.pilot else len(schedule),
            'order':('one pair per cell each round in seeded random order' if args.interleave_pairs else
                     'seeded shuffle of cells; each cell runs paired rounds and alternates which compiler starts'),
            'order_seed':seed,'parallel_compilers':1,'claim_limits':data['claim_limits']},
        'source_commit':identity['commit'],'source':identity,
        'toolchain':{'ghc':{'path':setup['ghc'],'version':auth['ghc']['version']},
            'clang':{'path':setup['clang'],'version':setup.get('identity',{}).get('clang_version')},
            'producer':{'path':setup['producer'],'receipt_sha256':H.sha(Path(setup['producer'])/'receipt.json'),
                'emlf_sha256':H.sha(Path(setup['producer'])/'bin/emlf'),
                'builtin_interface':setup.get('identity',{}).get('builtin_interface'),
                'optimization':setup.get('identity',{}).get('optimization')},
            'builtin':setup.get('builtin_record',{})},
        'setup':setup,'cases':cases,'seed':seed,'schedule':schedule,'inputs':inputs,'limits':limits,'host':H.host(),
        'endpoint':'fresh source to native executable; fixed primitive/runtime/builtin dependencies may be reused',
        'failure_rule':'retain failure, mark case incomplete and skip its remaining scheduled legs; never replace samples',
        'syntax_adaptations':False,'parallel_compilers':1,'ordinary_clang_flags':list(worker.ORDINARY_CLANG_FLAGS),
        'ghc_arguments':['--make','-j1','-O2','-fforce-recomp','-package-env','-','-clear-package-db',
            '-global-package-db','-package-db',setup['package_db'],'-no-user-package-db','-hide-all-packages',
            '-package','base','-package','mlf-shape-primitives','-i','-odir','<leg>','-hidir','<leg>','<source>','-o','<leg>/program'],
        'mlf_stages':worker.mlf_stage_names(args.endpoint),
        'timing_boundary':'exact-child worker launch through wait4; common Python dispatcher included; preparation and validation excluded'}
    if args.endpoint in worker.PRODUCTION_ENDPOINTS:
        triple = subprocess.check_output([setup['clang'], '-dumpmachine'], text=True).strip()
        if not triple or len(triple.split()) != 1:
            raise ValueError(f'Invalid Clang target triple: {triple!r}')
        policy = {'target': triple, 'mlf': native_target_policy(setup['producer'], triple)}
        if reference:
            policy['reference'] = native_target_policy(reference['producer'], triple)
        plan['native_target_policy'] = policy
    if selection:
        plan['baseline_selection'] = selection
    if reference:
        plan['compiler_reference'] = reference
        plan['benchmark']['schema'] = 3
        plan['benchmark']['order'] = 'candidate between GHC and the committed compiler, reversing each round; ' + ('interleaved cells' if args.interleave_pairs else 'grouped cells')
    plan_path=out/'plan.json';H.save(plan_path,plan);plan_sha=H.sha(plan_path)
    scripts=out/'scripts';scripts.mkdir()
    for name in ['run.py','worker.py','generate.py','data_shapes.py','rank_shapes.py','fit_growth.py','analyze.py',
                 'matrix.json','query_cache.py','provenance.py','framework_results.py','compiler_reference.py']:
        shutil.copy2(HERE/name,scripts/name)
    shutil.copy2(ROOT/'tools/testing/events.py', scripts/'events.py')
    record={'complete':False,'plan_sha256':plan_sha,'runs':[],'failures':[]}; refs={};blocked=set()
    def save():H.save(out/'receipt.json',record)
    save();H.check_pins(inputs)
    by_id = {case['id']: case for case in cases}
    remaining = {case['id']: repeats * lanes_per_round for case in cases}
    with H.SerialLock(ROOT/'.mlf-build'):
        for index,item in enumerate(schedule):
            if item['case'] in blocked:continue
            if H.tree_bytes(out)>limits['aggregate_cohort_bytes']:
                # Stop before writing more evidence, but leave the reason inside
                # the receipt so an incomplete cohort is self-describing.
                record['stop_reason']='aggregate cohort output budget between legs';save()
                raise RuntimeError(record['stop_reason'])
            case=by_id[item['case']];lane=item['lane']
            cell = (case['family'], case['size'])
            if remaining[case['id']] == repeats * lanes_per_round:
                framework.start(ids, cell, args.pilot, endpoint=args.endpoint,
                                oracle_inputs=case['inputs'], source_sha256=case['source_sha256'])
            leg=out/'legs'/f'{index:03d}-{case["id"]}-{lane}';leg.mkdir(parents=True)
            build=leg/'build';r={'case':case['id'],'position':item['position'],'lane':lane,'complete':False}
            try:
                H.require(H.sha(plan_path)==plan_sha,'frozen schedule unchanged')
                H.require(H.sha(case['source'])==case['source_sha256'],'frozen same source')
                libraries=worker.dependencies(case)
                for lib in libraries:
                    H.require(H.sha(lib['source'])==lib['sha256'],'frozen same dependency source')
                command=H.Runner(leg,limits).run([sys.executable,'-B',HERE/'worker.py','--plan',plan_path,
                    '--case',case['id'],'--lane',lane,'--out',build],ROOT,leg/'command',timed=not args.pilot)
                r['command']=command;r['stages']=H.load(build/'stages.json')
                H.require(r['stages']['complete'],'every compilation stage complete')
                r['executable_sha256']=H.sha(build/'program')
                if lane in ('mlf','reference'):
                    if args.endpoint == worker.CACHED_ENDPOINT:
                        producer = plan['toolchain']['producer'] if lane == 'mlf' else plan['compiler_reference']
                        r['codegen_cache'] = Q.cold_codegen_evidence(build, producer['emlf_sha256'])
                    q=H.load(build/'unit.queries');H.require(q['inferred_groups']==len(q['groups'])>0
                        and q['reused_groups']==0 and all(g['cached'] is False for g in q['groups']),'fresh target groups only')
                    r['fresh']=q['inferred_groups'];r['reused']=0
                    r['max_group_members']=max(len(g['members']) for g in q['groups'])
                    raw={s:(build/('unit'+s)).read_bytes() for s in ['.mlfci','.mlfco']}
                    groups=[{k:g[k] for k in ['id','members']} for g in q['groups']]
                    r['checked_sha256']={s:hashlib.sha256(b).hexdigest() for s,b in raw.items()}
                    if libraries:
                        def normal_interface(data):
                            doc=Q.read_document(data,3)
                            stable=replace(doc,symbols=tuple(value.replace(str(build)+'/', '<leg>/')
                                                            for value in doc.symbols)).values()
                            return json.dumps(stable,ensure_ascii=False).encode()
                        raw['.mlfci']=normal_interface(raw['.mlfci'])
                        r['cold_dependencies']=[]
                        for index, lib in enumerate(libraries):
                            dep=worker.dependency_folder(build,libraries,index)
                            report=H.load(dep/'unit.queries')
                            H.require(report['inferred_groups']==len(report['groups'])>0 and
                                      report['reused_groups']==0 and
                                      all(g['cached'] is False for g in report['groups']),
                                      'fresh target dependency groups only')
                            interface=(dep/'unit.mlfci').read_bytes()
                            body=(dep/'unit.mlfco').read_bytes()
                            raw[lib['module']+'.mlfci']=normal_interface(interface)
                            raw[lib['module']+'.mlfco']=body
                            groups.extend({'id':g['id'],'members':g['members']} for g in report['groups'])
                            r['cold_dependencies'].append({'module':lib['module'],
                                'fresh_groups':report['inferred_groups'],
                                'checked_sha256':{'.mlfci':hashlib.sha256(interface).hexdigest(),
                                                  '.mlfco':hashlib.sha256(body).hexdigest()}})
                        if len(libraries)==1:
                            r['dependency_fresh_groups']=r['cold_dependencies'][0]['fresh_groups']
                            r['dependency_checked_sha256']=r['cold_dependencies'][0]['checked_sha256']
                    key = (case['id'], lane)
                    if key in refs:
                        old=refs[key]
                        H.require(raw==old['raw'] and groups==old['groups'],'checked content and ordered groups stable')
                    else:refs[key]={'raw':raw,'groups':groups}
                    r['raw_compared_with_first_mlf_leg']=sum(x['case']==case['id'] and x['lane']==lane for x in record['runs'])>0
                else:
                    H.require((build/'Main.o').is_file() and (build/'Main.hi').is_file(),'fresh GHC target objects')
                    r['ghc_compile_log']=(build/'source-to-executable.stdout').read_text()
                    H.require('Compiling Main' in r['ghc_compile_log'],'actual target compilation')
                    for lib in libraries:
                        name=lib['module']
                        H.require((build/(name+'.o')).is_file() and (build/(name+'.hi')).is_file() and
                                  'Compiling '+name in r['ghc_compile_log'],'fresh GHC dependency compilation')
                for j,(value,expected) in enumerate(zip(case['inputs'],case['expected_stdout'])):
                    H.Runner(leg,limits).run([build/'program',str(value)],ROOT,leg/f'output-{j}')
                    H.require((leg/f'output-{j}/stdout').read_bytes()==expected.encode()
                              and not (leg/f'output-{j}/stderr').read_bytes(),'independent executable result')
                r.update(complete=True,oracle_inputs=case['inputs'],output_correct=True)
                record['runs'].append(r);save()
                print(f'{index+1}/{len(schedule)} {case["id"]} {lane}: {command["wall_seconds"]:.3f}s, outputs correct',flush=True)
            except BaseException as e:
                r['error']=repr(e);record['failures'].append(r);blocked.add(case['id']);save()
                print('FAILED '+case['id']+' '+lane+': '+repr(e),flush=True)
                if isinstance(e,(KeyboardInterrupt,SystemExit)):raise
            finally:
                query=build/'queries'
                if query.is_dir():
                    H.save(leg/'query-cache-inventory.json',{str(p.relative_to(query)):{'bytes':p.stat().st_size,'sha256':H.sha(p)} for p in sorted(query.rglob('*')) if p.is_file()})
                    Q.snapshot(query,build/'unit.queries',leg/'query-graph-evidence.json')
                    shutil.rmtree(query)
            remaining[case['id']] -= 1
            if case['id'] in blocked or not remaining[case['id']]:
                framework.result(ids, cell, 'fail' if case['id'] in blocked else 'pass',
                                 args.pilot, receipt=str(out/'receipt.json'),
                                 legs_checked=repeats * lanes_per_round - remaining[case['id']],
                                 **({'detail': r['error'], 'lane': lane} if 'error' in r else {}))
        H.check_pins(inputs)
        H.require(H.authenticate(Path(setup['producer']),Path(setup.get('source',ROOT)))==auth,'ordinary producer unchanged')
    record.update(complete=True,all_cases_passed=not blocked,failed_cases=sorted(blocked));save()
    print('Completed; failures retained:',len(record['failures']),flush=True)
    if not args.pilot and not args.record_only:
        from analyze import save_recorded_growth
        print(save_recorded_growth(out), flush=True)


if __name__=='__main__':main()

