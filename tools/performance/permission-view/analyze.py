#!/usr/bin/env python3
"""Descriptive fixed-block decision under the strict-positive structural rule."""
from pathlib import Path
import argparse
import importlib.util
import json
import math
import statistics

HERE = Path(__file__).resolve().parent
path = HERE.parent/'process-spawn/analyze.py'
spec = importlib.util.spec_from_file_location('retained_analysis', path)
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)


def summarize(window):
    plan, rows = retained.read_window(window)
    retained.require(retained.sha(Path(__file__)) == plan['analysis']['analyzer_sha256']
                     and retained.sha(path) == plan['analysis']['validation_analyzer_sha256'],
                     'predeclared decision and retained validation analyzers')
    result = {}
    for case in dict.fromkeys(b['case'] for b in plan['blocks']):
        chosen = [r for r in rows if r['case'] == case]
        effects=[]
        for index, block in enumerate(plan['blocks']):
            if block['case'] != case: continue
            legs=[r for r in chosen if r['block']==index]
            paired=[]
            for pair in [legs[:2],legs[2:]]:
                a=next(r['command']['wall_seconds'] for r in pair if r['side']=='A')
                b=next(r['command']['wall_seconds'] for r in pair if r['side']=='B')
                paired.append(math.log(b/a))
            effects.append(dict(block=index,order=block['order'],log_ratio=statistics.mean(paired)))
        theta=statistics.mean(e['log_ratio'] for e in effects)
        geometric={side:math.exp(statistics.mean(math.log(r['command']['wall_seconds'])
                       for r in chosen if r['side']==side)) for side in 'AB'}
        result[case]=dict(runs=len(chosen),ratio=math.exp(theta),gain=1-math.exp(theta),
                         geometric_seconds=geometric,blocks=effects,
                         median_seconds={side:statistics.median(r['command']['wall_seconds']
                           for r in chosen if r['side']==side) for side in 'AB'})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler',type=Path,required=True)
    p.add_argument('--guards',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    primary=summarize(a.compiler)
    retained.require(set(primary)=={'compiler'} and primary['compiler']['runs']==8,
                     'predeclared eight compiler runs')
    guards=summarize(a.guards) if a.guards else {}
    if a.guards:
        retained.require(set(guards)=={'flat_functions-512','higher_order_chain-128'}
                         and all(v['runs']==4 for v in guards.values()),'predeclared two guards')
    for row in guards.values():
        row['meaningful_regression']=(row['ratio']>1.05 and
          row['geometric_seconds']['B']-row['geometric_seconds']['A']>0.1)
    value=dict(complete=True,primary=primary,guards=guards,
               positive_primary=primary['compiler']['ratio']<1,
               guards_complete=bool(guards),
               timing_rule_passed=bool(guards) and primary['compiler']['ratio']<1
                 and not any(v['meaningful_regression'] for v in guards.values()),
               evidence='Fixed small descriptive window; no confidence interval, significance or portability claim.')
    retained.require(not a.output.exists(),'fresh analysis output')
    a.output.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')
    print(json.dumps(value,indent=2))


if __name__=='__main__': main()
