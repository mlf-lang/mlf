#!/usr/bin/env python3
"""Offline descriptive analysis. Reject incomplete/duplicate/nonfinite samples."""
from pathlib import Path
import argparse
import collections
import csv
import hashlib
import json
import math
import statistics as S


def require(condition,message):
    if not condition:raise ValueError(message)


def load(path):
    def pairs(xs):
        result={}
        for k,v in xs:
            require(k not in result,'duplicate JSON key: '+k);result[k]=v
        return result
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze(folder):
    folder=Path(folder);plan=load(folder/'plan.json');receipt=load(folder/'receipt.json')
    require(receipt['complete'] and receipt['all_cases_passed'] and not receipt['failures'],'incomplete/failed cohort; do not silently omit failures')
    require(sha(folder/'plan.json')==receipt['plan_sha256'],'frozen plan digest')
    expected={(r['case'],r['position'],r['lane']) for r in plan['schedule']}
    actual=[(r['case'],r['position'],r['lane']) for r in receipt['runs']]
    require(len(actual)==len(set(actual)) and set(actual)==expected,'exact scheduled runs, no missing or duplicate samples')
    groups=collections.defaultdict(list)
    for r in receipt['runs']:
        require(r['complete'] and r['output_correct'] and r['command']['complete'],'qualified native run')
        require(r['command']['timed_target_leg'],'qualification data are not performance samples')
        for k in ['wall_seconds','child_user_seconds','child_system_seconds']:
            require(math.isfinite(r['command'][k]) and r['command'][k]>=0,'finite nonnegative timings')
        if r['lane']=='mlf':require(r['fresh']>0 and r['reused']==0,'fresh MLF target')
        groups[r['case'],r['lane']].append(r)
    rows=[]
    for case in plan['cases']:
        require(sha(case['source'])==case['source_sha256'],'unchanged shared source')
        row={'cohort':folder.name,'case':case['id'],'family':case['family'],'size':case['size'],
             'source_bytes':case['source_bytes'],'source_sha256':case['source_sha256']}
        for lane in ['ghc','mlf']:
            rs=groups[case['id'],lane];require(len(rs)==3,'exactly three samples per compiler')
            times=[r['command']['wall_seconds'] for r in rs]
            row[lane+'_wall_median']=S.median(times);row[lane+'_wall_min']=min(times);row[lane+'_wall_max']=max(times)
            row[lane+'_user_median']=S.median(r['command']['child_user_seconds'] for r in rs)
            row[lane+'_system_median']=S.median(r['command']['child_system_seconds'] for r in rs)
            row[lane+'_samples']=times
            if lane=='mlf':
                row['fresh']=rs[0]['fresh'];row['max_group_members']=rs[0]['max_group_members']
                require(all(r['fresh']==row['fresh'] for r in rs),'stable query group count')
                require(sum(r['raw_compared_with_first_mlf_leg'] for r in rs)==2,'actual raw-byte comparisons on both repetitions')
                for stage in ['source-to-checked','checked-to-llvm','llvm-to-executable']:
                    ss=[next(s for s in r['stages']['stages'] if s['name']==stage) for r in rs]
                    for metric in ['wall_seconds','user_seconds','system_seconds']:
                        require(all(math.isfinite(s[metric]) and s[metric]>=0 for s in ss),'valid stage timings')
                        row[stage+'_'+metric+'_median']=S.median(s[metric] for s in ss)
                directories=[p for p in (folder/'legs').iterdir() if p.name.endswith(case['id']+'-mlf')]
                require(len(directories)==3,'all three retained leg directories')
                inventories=[load(d/'query-cache-inventory.json') for d in directories]
                counts=[sum(k.endswith('.mlfq') for k in inv) for inv in inventories]
                require(all(n==row['fresh'] for n in counts),'one persisted query object per fresh group')
                row['query_files']=counts[0]
                row['query_bytes_median']=S.median(sum(v['bytes'] for k,v in inv.items() if k.endswith('.mlfq')) for inv in inventories)
        row['mlf_over_ghc']=row['mlf_wall_median']/row['ghc_wall_median'];rows.append(row)
    return rows,plan,receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cohorts',nargs='+',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);rows=[];provenance=[]
    for cohort in a.cohorts:
        data,plan,receipt=analyze(cohort);rows.extend(data)
        provenance.append({'cohort':str(cohort.resolve()),'plan_sha256':sha(cohort/'plan.json'),
            'receipt_sha256':sha(cohort/'receipt.json'),'source_commit':plan['source_commit'],
            'host':plan['host'],'compile_runs':len(receipt['runs']),'executable_oracle_runs':sum(len(r['oracle_inputs']) for r in receipt['runs'])})
    report={'scope':'descriptive exploratory medians, ratio of medians; no CIs; cohorts are never pooled',
        'endpoint':'source to native executable; GHC versus GHC-hosted MLF private crate path',
        'native_installed_emlf_measured':False,'provenance':provenance,'rows':rows}
    (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    keys=list(rows[0])
    with (a.output/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    if a.plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        labels={'flat_functions':'Independent functions','dependency_chain':'Annotated chain','inferred_chain':'Inferred chain',
            'recursive_ring':'Mutual recursion','mono_calls':'Monomorphic calls','poly_calls':'Polymorphic calls',
            'tree_chain':'Skewed tree','balanced_tree':'Balanced tree','literal_table':'Literal table','higher_order_chain':'Higher-order chain'}
        fig,(left,right)=plt.subplots(1,2,figsize=(13.6,6.3),gridspec_kw={'width_ratios':[1.35,1]})
        screen=[r for r in rows if r['cohort']=='screen' and r['size']>0]
        order=sorted(labels,key=lambda f:next(r['mlf_over_ghc'] for r in screen if r['family']==f and r['size']==128),reverse=True)
        colors={8:'#94b7c3',32:'#447f98',128:'#183c54'}
        for i,n in enumerate([8,32,128]):
            values=[next(r['mlf_over_ghc'] for r in screen if r['family']==f and r['size']==n) for f in order]
            left.barh([j+(i-1)*.24 for j in range(len(order))],values,height=.22,color=colors[n],label=f'n = {n}')
        left.set_yticks(range(len(order)),[labels[f] for f in order]);left.invert_yaxis();left.axvline(1,color='#b45c40',linestyle='--',linewidth=1)
        left.set_xlabel('MLF / GHC compile wall (ratio of medians)');left.set_title('Initial screen: same source, fresh native outputs');left.legend(frameon=False,loc='lower right')
        extension=[r for r in rows if r['cohort']=='group-extension' and r['size']==512]
        names=['inferred_chain','flat_functions','dependency_chain','local_functions','recursive_ring']
        names_text=['Inferred chain','Top-level functions','Annotated chain','Local functions','Mutual recursion']
        for i,(lane,color) in enumerate([('ghc','#a4b4c0'),('mlf','#245c80')]):
            values=[next(r[lane+'_wall_median'] for r in extension if r['family']==f) for f in names]
            right.barh([j+(i-.5)*.34 for j in range(len(names))],values,height=.31,color=color,label='GHC' if lane=='ghc' else 'MLF crate')
            for j,v in enumerate(values):right.text(v+.08,j+(i-.5)*.34,f'{v:.2f}',va='center',fontsize=8)
        right.set_yticks(range(len(names)),names_text);right.invert_yaxis();right.set_xlim(0,max(r['mlf_wall_median'] for r in extension)*1.15)
        right.set_xlabel('Seconds (three-sample median)');right.set_title('Separate extension cohort: n = 512');right.legend(frameon=False,loc='lower right')
        for ax in [left,right]:
            ax.spines[['top','right']].set_visible(False);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
        fig.suptitle('MLF compiler shape study | fffb66a3 | GHC 9.14.1 -O2 | serial Clang -O2',fontsize=12,y=.985)
        fig.text(.5,.018,'Exploratory samples on one Mac. MLF private crate entry, not the installed native-library driver. Different cohorts are not pooled.',ha='center',fontsize=8)
        fig.tight_layout(rect=[0,.045,1,.96]);fig.savefig(a.output/'compiler-shapes.png',dpi=170);plt.close(fig)
    print(json.dumps({'rows':len(rows),'compile_runs':sum(p['compile_runs'] for p in provenance),
        'oracle_runs':sum(p['executable_oracle_runs'] for p in provenance),'output':str(a.output.resolve())}))


if __name__=='__main__':main()
