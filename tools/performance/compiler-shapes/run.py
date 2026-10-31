#!/usr/bin/env python3
"""Serial same-source shape matrix; no optimization acceptance claim."""
from pathlib import Path
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import sys
import types
import generate as G

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent


def registry():
    return json.loads((HERE/'matrix.json').read_text())


def git(*argv):
    return subprocess.run(['git',*argv],cwd=ROOT,capture_output=True,text=True)


def source_identity(out):
    """Record the exact measured source state, including uncommitted patches."""
    commit=git('rev-parse','HEAD').stdout.strip()
    branch=git('rev-parse','--abbrev-ref','HEAD').stdout.strip()
    status=git('status','--porcelain').stdout
    patch=git('diff','HEAD').stdout.encode()
    untracked={}
    for name in git('ls-files','--others','--exclude-standard').stdout.splitlines():
        path=ROOT/name
        if path.is_file():untracked[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    record={'commit':commit,'branch':branch,'dirty':bool(status.strip()),
        'status_porcelain':status.splitlines(),'patch_sha256':hashlib.sha256(patch).hexdigest(),
        'patch_bytes':len(patch),'untracked':untracked}
    if patch:
        (out/'source-patch.diff').write_bytes(patch)
        record['patch_file']=str(out/'source-patch.diff')
    return record


def lanes_for(index,repeats):
    """Three paired rounds; balance which compiler starts within and across cells."""
    lanes=[]
    for round_index in range(repeats):
        first='ghc' if (round_index+index)%2==0 else 'mlf'
        lanes.extend([first,'mlf' if first=='ghc' else 'ghc'])
    return lanes


def main():
    data=registry()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--family',action='append',choices=G.FAMILIES+('baseline',))
    parser.add_argument('--size',action='append',type=int)
    parser.add_argument('--repeats',type=int,default=data['repeats'])
    parser.add_argument('--cohort')
    parser.add_argument('--endpoint',default='crate-bootstrap-v1',choices=sorted(data['endpoints']))
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('unchanged_resource_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    setup=H.load(args.setup.resolve()); H.require(setup['complete'],'qualified fixed dependencies')
    H.require(setup.get('endpoint')==args.endpoint,'setup belongs to endpoint profile '+str(setup.get('endpoint'))
              +', not '+args.endpoint)
    endpoint=data['endpoints'][args.endpoint]
    auth=H.authenticate(Path(setup['producer']),Path(setup.get('source',ROOT)))
    repeats=1 if args.pilot else args.repeats
    H.require(repeats>=1,'positive repeats')
    sizes=args.size or ((8,) if args.pilot else tuple(data['sizes']))
    H.require(all(0<n<=1024 for n in sizes),'bounded positive sizes')
    cases=G.generate(out/'sources',sizes=sizes,families=args.family)
    seed=data['seed']; rng=random.Random(seed); order=list(cases);rng.shuffle(order)
    schedule=[]
    for index,case in enumerate(order):
        lanes=['ghc','mlf'] if args.pilot else lanes_for(index,repeats)
        for position,lane in enumerate(lanes):
            schedule.append({'case':case['id'],'position':position,'lane':lane})
    inputs={str(p.resolve()):H.sha(p) for p in [args.setup,hp,HERE/'run.py',HERE/'worker.py',HERE/'generate.py',
        HERE/'matrix.json',Path(setup['producer'])/'receipt.json',Path(setup['producer'])/'bin/emlf',
        Path(setup['ghc']),Path(setup['clang']),Path(setup['runtime']),Path(setup['builtin']+'.mlfci'),
        Path(setup['builtin']+'.mlfco')]}
    inputs.update(H.file_pins(Path(setup['package_db']).parent))
    inputs.update({c['source']:c['source_sha256'] for c in cases})
    # Per-command output stays bounded at 512 MiB; the cohort bound covers the
    # deliberately retained evidence (69 native executables, LLVM IR and GHC
    # objects for 31 cells). It is a bound, not a target: a 31-cell cohort uses
    # about 2.6 GiB, and the earlier 2 GiB carry-over stopped a run at leg 149.
    limits={**setup['limits'],'wall_seconds':90,'max_work_bytes':512*1024**2,
            'aggregate_cohort_bytes':8*1024**3}
    identity=source_identity(out)
    cohort=args.cohort or out.name
    plan={'purpose':'generator/transport qualification' if args.pilot else 'fixed measured shape matrix; descriptive medians only',
        'benchmark':{'schema':2,'suite':data['suite'],'suite_version':data['version'],'cohort':cohort,
            'endpoint':{'id':args.endpoint,**endpoint},'repeats':repeats,
            'families':sorted({c['family'] for c in cases}),'sizes':sorted({c['size'] for c in cases}),
            'cells':len(cases),'timed_compilations':0 if args.pilot else len(schedule),
            'order':'seeded shuffle of cells; each cell runs paired rounds and alternates which compiler starts',
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
        'syntax_adaptations':False,'parallel_compilers':1,'ordinary_clang_flags':['-O2','-Wno-override-module'],
        'ghc_arguments':['--make','-j1','-O2','-fforce-recomp','-package-env','-','-clear-package-db',
            '-global-package-db','-package-db',setup['package_db'],'-no-user-package-db','-hide-all-packages',
            '-package','base','-package','mlf-shape-primitives','-i','-odir','<leg>','-hidir','<leg>','<source>','-o','<leg>/program'],
        'mlf_stages':['source-to-checked: PRODUCER/bin/emlf --compile-crate <spec> -o <leg>/unit',
            'checked-to-llvm: PRODUCER/bin/emlf --crate-to-llvm-gc <leg>/unit.mlfci',
            'llvm-to-executable: CLANG -O2 -Wno-override-module <leg>/unit.ll <runtime.o> <gc/gmp libs> -lm -lpthread -ldl'],
        'timing_boundary':'exact-child worker launch through wait4; common Python dispatcher included; preparation and validation excluded'}
    plan_path=out/'plan.json';H.save(plan_path,plan);plan_sha=H.sha(plan_path)
    scripts=out/'scripts';scripts.mkdir()
    for name in ['run.py','worker.py','generate.py']:
        shutil.copy2(HERE/name,scripts/name)
    record={'complete':False,'plan_sha256':plan_sha,'runs':[],'failures':[]}; refs={};blocked=set()
    def save():H.save(out/'receipt.json',record)
    save();H.check_pins(inputs)
    with H.SerialLock(ROOT/'.mlf-build'):
        for index,item in enumerate(schedule):
            if item['case'] in blocked:continue
            if H.tree_bytes(out)>limits['aggregate_cohort_bytes']:
                # Stop before writing more evidence, but leave the reason inside
                # the receipt so an incomplete cohort is self-describing.
                record['stop_reason']='aggregate cohort output budget between legs';save()
                raise RuntimeError(record['stop_reason'])
            case=next(c for c in cases if c['id']==item['case']);lane=item['lane']
            leg=out/'legs'/f'{index:03d}-{case["id"]}-{lane}';leg.mkdir(parents=True)
            build=leg/'build';r={'case':case['id'],'position':item['position'],'lane':lane,'complete':False}
            try:
                H.require(H.sha(plan_path)==plan_sha,'frozen schedule unchanged')
                H.require(H.sha(case['source'])==case['source_sha256'],'frozen same source')
                command=H.Runner(leg,limits).run([sys.executable,'-B',HERE/'worker.py','--plan',plan_path,
                    '--case',case['id'],'--lane',lane,'--out',build],ROOT,leg/'command',timed=not args.pilot)
                r['command']=command;r['stages']=H.load(build/'stages.json')
                H.require(r['stages']['complete'],'every compilation stage complete')
                r['executable_sha256']=H.sha(build/'program')
                if lane=='mlf':
                    q=H.load(build/'unit.queries');H.require(q['inferred_groups']==len(q['groups'])>0
                        and q['reused_groups']==0 and all(g['cached'] is False for g in q['groups']),'fresh target groups only')
                    r['fresh']=q['inferred_groups'];r['reused']=0
                    r['max_group_members']=max(len(g['members']) for g in q['groups'])
                    raw={s:(build/('unit'+s)).read_bytes() for s in ['.mlfci','.mlfco']}
                    groups=[{k:g[k] for k in ['id','members']} for g in q['groups']]
                    if case['id'] in refs:
                        old=refs[case['id']]
                        H.require(raw==old['raw'] and groups==old['groups'],'raw checked bytes and ordered groups stable')
                    else:refs[case['id']]={'raw':raw,'groups':groups}
                    r['checked_sha256']={s:hashlib.sha256(b).hexdigest() for s,b in raw.items()}
                    r['raw_compared_with_first_mlf_leg']=sum(x['case']==case['id'] and x['lane']=='mlf' for x in record['runs'])>0
                else:
                    H.require((build/'Main.o').is_file() and (build/'Main.hi').is_file(),'fresh GHC target objects')
                    r['ghc_compile_log']=(build/'source-to-executable.stdout').read_text()
                    H.require('Compiling Main' in r['ghc_compile_log'],'actual target compilation')
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
                    shutil.rmtree(query)
        H.check_pins(inputs)
        H.require(H.authenticate(Path(setup['producer']),Path(setup.get('source',ROOT)))==auth,'ordinary producer unchanged')
    record.update(complete=True,all_cases_passed=not blocked,failed_cases=sorted(blocked));save()
    print('Completed; failures retained:',len(record['failures']),flush=True)


if __name__=='__main__':main()
