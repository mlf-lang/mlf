#!/usr/bin/env python3
"""Serial exploratory same-source shape matrix; no optimization acceptance claim."""
from pathlib import Path
import argparse
import hashlib
import json
import random
import shutil
import sys
import types
import generate as G

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--setup',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--pilot',action='store_true')
    parser.add_argument('--family',action='append',choices=G.FAMILIES)
    parser.add_argument('--size',action='append',type=int)
    args=parser.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    hp=ROOT/'tools/performance/a1-private-index/helper.py'
    H=types.ModuleType('unchanged_resource_helper');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
    setup=H.load(args.setup.resolve()); H.require(setup['complete'],'qualified fixed dependencies')
    auth=H.authenticate(Path(setup['producer']),ROOT)
    sizes=args.size or ((8,) if args.pilot else (8,32,128))
    H.require(all(0<n<=1024 for n in sizes),'bounded positive sizes')
    cases=G.generate(out/'sources',sizes=sizes,families=args.family)
    seed=20261031; rng=random.Random(seed); order=list(cases);rng.shuffle(order)
    schedule=[]
    for index,case in enumerate(order):
        if args.pilot:
            lanes=['ghc','mlf']
        else:
            # Three paired rounds; balance which side starts across cases.
            lanes=['ghc','mlf','mlf','ghc','ghc','mlf'] if index%2==0 else ['mlf','ghc','ghc','mlf','mlf','ghc']
        for position,lane in enumerate(lanes):
            schedule.append({'case':case['id'],'position':position,'lane':lane})
    inputs={str(p.resolve()):H.sha(p) for p in [args.setup,hp,HERE/'run.py',HERE/'worker.py',HERE/'generate.py',
        Path(setup['producer'])/'receipt.json',Path(setup['producer'])/'bin/emlf',Path(setup['ghc']),
        Path(setup['clang']),Path(setup['runtime']),Path(setup['builtin']+'.mlfci'),Path(setup['builtin']+'.mlfco')]}
    inputs.update(H.file_pins(Path(setup['package_db']).parent))
    inputs.update({c['source']:c['source_sha256'] for c in cases})
    limits={**setup['limits'],'wall_seconds':90,'max_work_bytes':512*1024**2}
    plan={'purpose':'generator/transport qualification' if args.pilot else 'fixed exploratory shape screen; no confidence or universal speedup claim',
        'source_commit':__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'setup':setup,'cases':cases,'seed':seed,'schedule':schedule,'inputs':inputs,'limits':limits,'host':H.host(),
        'endpoint':'fresh source to native executable; fixed primitive/runtime/builtin dependencies may be reused',
        'failure_rule':'retain failure, mark case incomplete and skip its remaining scheduled legs; never replace samples',
        'syntax_adaptations':False,'parallel_compilers':1,'ordinary_clang_flags':['-O2','-Wno-override-module'],
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
            H.require(H.tree_bytes(out)<=setup['limits']['max_work_bytes'],'aggregate experiment output budget between legs')
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
        H.require(H.authenticate(Path(setup['producer']),ROOT)==auth,'ordinary producer unchanged')
    record.update(complete=True,all_cases_passed=not blocked,failed_cases=sorted(blocked));save()
    print('Completed; failures retained:',len(record['failures']),flush=True)


if __name__=='__main__':main()
