#!/usr/bin/env python3
"""Predeclared four-leg full-task decision, reusing retained raw/fresh audits."""
from pathlib import Path
import argparse,importlib.util,json,math,statistics
HERE=Path(__file__).resolve().parent
READER=HERE.parent/'process-spawn/analyze.py'
spec=importlib.util.spec_from_file_location('retained_window_reader',READER)
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)


def summarize(folder):
    plan,rows=R.read_window(folder)
    R.require(R.sha(Path(__file__))==plan['analysis']['analyzer_sha256']
        and R.sha(READER)==plan['analysis']['validation_analyzer_sha256'],'predeclared analyzer composition')
    result={}
    for case in dict.fromkeys(b['case'] for b in plan['blocks']):
        selected=[r for r in rows if r['case']==case];effects=[]
        for index,b in enumerate(plan['blocks']):
            if b['case']!=case:continue
            legs=[r for r in selected if r['block']==index];pairs=[]
            for pair in [legs[:2],legs[2:]]:
                a=next(r['command']['wall_seconds'] for r in pair if r['side']=='A')
                c=next(r['command']['wall_seconds'] for r in pair if r['side']=='B')
                pairs.append(math.log(c/a))
            effects.append({'block':index,'order':b['order'],'pair_log_ratios':pairs,'log_ratio':statistics.mean(pairs)})
        theta=statistics.mean(x['log_ratio'] for x in effects)
        geometric={side:math.exp(statistics.mean(math.log(r['command']['wall_seconds']) for r in selected if r['side']==side)) for side in 'AB'}
        result[case]={'runs':len(selected),'ratio':math.exp(theta),'gain':1-math.exp(theta),'geometric_seconds':geometric,'blocks':effects,'median_seconds':{side:statistics.median(r['command']['wall_seconds'] for r in selected if r['side']==side) for side in 'AB'}}
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--guards',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    primary=summarize(a.compiler);R.require(set(primary)=={'compiler'} and primary['compiler']['runs']==4,'fixed four ordinary full compiler executions')
    guards=summarize(a.guards) if a.guards else {}
    if a.guards:R.require(set(guards)=={'flat_functions-512','higher_order_chain-128'} and all(x['runs']==4 for x in guards.values()),'two predeclared guard cells')
    for row in guards.values():row['meaningful_regression']=row['ratio']>1.05 and row['geometric_seconds']['B']-row['geometric_seconds']['A']>0.1
    value={'complete':True,'primary':primary,'guards':guards,'positive_primary':primary['compiler']['ratio']<1,'guards_complete':bool(guards),'timing_rule_passed':bool(guards) and primary['compiler']['ratio']<1 and not any(x['meaningful_regression'] for x in guards.values()),'evidence':'Fixed small descriptive window, one full-task block; no significance, confidence interval, stable/portable or native end-to-end claim.'}
    R.require(not a.output.exists(),'fresh analysis output');a.output.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n');print(json.dumps(value,indent=2))


if __name__=='__main__':main()
