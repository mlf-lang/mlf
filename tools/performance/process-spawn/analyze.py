#!/usr/bin/env python3
"""Offline block analysis with SciPy; exploration and confirmation stay separate."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import statistics as S


def require(value, message):
    if not value: raise ValueError(message)


def load(path):
    def pairs(items):
        result = {}
        for k,v in items:
            require(k not in result, 'duplicate JSON key'); result[k] = v
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_window(folder):
    folder = Path(folder)
    plan = load(folder/'plan.json'); receipt = load(folder/'receipt.json')
    require(receipt['complete'] and not receipt.get('error'), 'whole window complete without omitted failures')
    require(sha(folder/'plan.json') == receipt['plan_sha256'], 'frozen plan identity')
    expected = [(i,j,b['case'],s) for i,b in enumerate(plan['blocks']) for j,s in enumerate(b['order'])]
    rows = receipt['runs']
    require([(r['block'],r['position'],r['case'],r['side']) for r in rows] == expected, 'exact schedule, no missing/reordered/duplicate samples')
    require(receipt['blocks'] == [{'index':i,'complete':True} for i in range(len(plan['blocks']))], 'every block completed')
    for name in ['compare.py','with_scope.py']:
        original = next(p for p in plan['inputs'] if p.endswith('/process-spawn/'+name))
        require(sha(folder/name) == plan['inputs'][original], 'archived measurement controller identity')
    references = {case:{s:Path(ref['prefix']+s).read_bytes() for s in ['.mlfci','.mlfco']}
        for case,ref in plan['references'].items()}
    for r in rows:
        command = r['command']
        require(r['complete'] and r['raw_bytes_equal'] and r['fresh'] > 0 and r['reused'] == 0, 'qualified fresh/raw run')
        require(command['complete'] and command['timed_target_leg'] and command['exit_code'] == 0
            and command['reason'] is None and not command['terminal_live_descendants'], 'successful ordinary timing only')
        for key in ['wall_seconds','child_user_seconds','child_system_seconds']:
            require(type(command[key]) in [float,int] and math.isfinite(command[key]) and command[key] >= 0, 'finite nonnegative timing')
        require(command['wall_seconds'] > 0 and command['limits'] == plan['limits'], 'positive wall and unchanged guards')
        leg = folder/('block-%02d'%r['block'])/('%d-%s'%(r['position'],r['side']))
        require(load(leg/'command/command.json') == command, 'unaltered individual timing receipt')
        require({s:(leg/'build'/('unit'+s)).read_bytes() for s in references[r['case']]} == references[r['case']], 'raw bytes rechecked offline against independent reference')
        query = load(leg/'build/unit.queries')
        require(query['inferred_groups'] == r['fresh'] == len(query['groups']) and query['reused_groups'] == 0
            and all(g['cached'] is False for g in query['groups']), 'fresh work rechecked offline')
    return plan,rows


def block_interval(log_ratios):
    import scipy.stats as stats
    # The independent analysis unit is the whole balanced block, not a module
    # or an individual compilation. No home-grown distribution implementation.
    require(len(log_ratios) >= 2 and all(math.isfinite(x) for x in log_ratios), 'finite block effects')
    theta = S.mean(log_ratios)
    interval = stats.ttest_1samp(log_ratios, 0).confidence_interval(confidence_level=.95)
    return {'log_ratio':theta, 'ratio':math.exp(theta), 'gain':1-math.exp(theta),
        'log_ratio_95ci':[float(interval.low),float(interval.high)],
        'gain_95ci':[1-math.exp(float(interval.high)),1-math.exp(float(interval.low))],
        'block_log_ratio_sd':S.stdev(log_ratios)}


def summarize(folder):
    plan,rows = read_window(folder)
    result = {'purpose':plan['purpose'],'plan_sha256':sha(Path(folder)/'plan.json'),
        'receipt_sha256':sha(Path(folder)/'receipt.json'),'runs':len(rows),'blocks':len(plan['blocks']),'cases':[]}
    for case in dict.fromkeys(b['case'] for b in plan['blocks']):
        selected = [r for r in rows if r['case'] == case]
        values = {s:{key:S.median(r['command'][key] for r in selected if r['side'] == s)
            for key in ['wall_seconds','child_user_seconds','child_system_seconds']} for s in 'AB'}
        item = {'case':case,'fresh_per_leg':selected[0]['fresh'],'medians':values,
            'descriptive_ratio_of_medians':values['B']['wall_seconds']/values['A']['wall_seconds']}
        if plan['kind'] == 'shapes':
            item['stage_medians'] = {s:{stage:{metric:S.median(next(t for t in r['stages']['stages'] if t['name'] == stage)[metric]
                for r in selected if r['side'] == s) for metric in ['wall_seconds','user_seconds','system_seconds']}
                for stage in ['source-to-checked','checked-to-llvm','llvm-to-executable']} for s in 'AB'}
        result['cases'].append(item)
    if plan['purpose'] == 'confirmation':
        import scipy
        protocol = plan['analysis']
        require(protocol['scipy_version'] == scipy.__version__ and protocol['independent_units'] == len(plan['blocks']) == 6,
            'frozen analysis version and unit count')
        effects = []
        for i,b in enumerate(plan['blocks']):
            legs = [r for r in rows if r['block'] == i]
            pairs = [legs[:2],legs[2:]]
            ratios = [math.log(next(r['command']['wall_seconds'] for r in p if r['side']=='B') /
                next(r['command']['wall_seconds'] for r in p if r['side']=='A')) for p in pairs]
            effects.append({'block':i,'order':b['order'],'log_ratio':S.mean(ratios),'gain':1-math.exp(S.mean(ratios))})
        result['block_effects'] = effects
        result['primary'] = block_interval([b['log_ratio'] for b in effects])
        result['by_order'] = {order:1-math.exp(S.mean(b['log_ratio'] for b in effects if b['order']==order)) for order in ['ABBA','BAAB']}
        result['meets_frozen_acceptance_rule'] = (result['primary']['gain'] >= protocol['minimum_point_gain']
            and result['primary']['gain_95ci'][0] > 0 and min(result['by_order'].values()) > 0)
        result['qualification'] = 'Nominal block t interval, conditional on fixed binaries, workload and Mac session; six blocks do not establish independence or portability.'
    return result,plan,rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--shapes',type=Path,required=True);p.add_argument('--target',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true')
    a = p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    shape,_,_ = summarize(a.shapes);target,plan,rows = summarize(a.target)
    report = {'shape_discovery':shape,'target':target,'analysis_sha256':sha(__file__)}
    (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,(left,right) = plt.subplots(1,2,figsize=(12,5),gridspec_kw={'width_ratios':[1,1.35]})
        labels = {'flat_functions-512':'Independent functions','inferred_chain-512':'Inferred chain','local_functions-512':'Local functions'}
        colors = {'A':'#8597a5','B':'#176b80'}
        for i,s in enumerate('AB'):
            y = [j+(i-.5)*.32 for j in range(len(shape['cases']))]
            v = [c['medians'][s]['wall_seconds'] for c in shape['cases']]
            left.barh(y,v,height=.29,color=colors[s],label='Before' if s=='A' else 'Spawn')
            for height,value in zip(y,v):left.text(value+.07,height,f'{value:.2f}',va='center',fontsize=9)
        left.set_yticks(range(len(shape['cases'])),[labels[c['case']] for c in shape['cases']]);left.invert_yaxis()
        left.set_xlim(0,max(c['medians']['A']['wall_seconds'] for c in shape['cases'])*1.2)
        left.set_xlabel('Seconds, median of 2 fresh native builds');left.set_title('Discovery: n = 512');left.legend(frameon=False)
        for s in 'AB':
            xs = [i+1 for i,r in enumerate(rows) if r['side']==s];ys = [r['command']['wall_seconds'] for r in rows if r['side']==s]
            right.plot(xs,ys,'o-',color=colors[s],linewidth=1,label='Before' if s=='A' else 'Spawn')
        for i in range(1,len(plan['blocks'])):right.axvline(i*4+.5,color='#dddddd',linewidth=.8)
        right.set_xlabel('Actual run order, four legs per block');right.set_ylabel('Compiler task wall, seconds')
        right.set_title('Independent confirmation: 711 fresh / 0 reused');right.legend(frameon=False)
        for ax in [left,right]:ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.12);ax.set_axisbelow(True)
        fig.suptitle('Darwin process launch | ordinary GHC 9.14.1 -O2 | serial Clang -O2',fontsize=12)
        fig.text(.5,.015,'Discovery and confirmation are separate cohorts. Fixed local Mac, binaries and inputs; no cross-platform speed claim.',ha='center',fontsize=8)
        fig.tight_layout(rect=[0,.04,1,.95]);fig.savefig(a.output/'spawn-compilation.png',dpi=170);plt.close(fig)
    print(json.dumps(target.get('primary',target['cases']),indent=2))


if __name__ == '__main__': main()
