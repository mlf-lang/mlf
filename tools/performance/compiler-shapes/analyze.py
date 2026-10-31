#!/usr/bin/env python3
"""Offline descriptive analysis. Reject incomplete/duplicate/nonfinite/incompatible cohorts."""
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


def compatibility(plan):
    """Everything that must match before two cohorts may appear in one report."""
    benchmark=plan['benchmark'];toolchain=plan['toolchain']
    builtin={k:v for k,v in toolchain['builtin'].items() if k.endswith(('.mlfci','.mlfco'))}
    return {'endpoint':benchmark['endpoint']['id'],'suite':benchmark['suite'],'suite_version':benchmark['suite_version'],
            'repeats':benchmark['repeats'],'ghc_version':toolchain['ghc']['version'],
            'ghc_path':toolchain['ghc']['path'],'clang_version':toolchain['clang']['version'],
            'producer_receipt_sha256':toolchain['producer']['receipt_sha256'],
            'producer_emlf_sha256':toolchain['producer']['emlf_sha256'],
            'builtin':builtin,'host_platform':plan['host'].get('platform'),'host_machine':plan['host'].get('machine')}


def analyze(folder):
    folder=Path(folder);plan=load(folder/'plan.json');receipt=load(folder/'receipt.json')
    require(plan.get('benchmark',{}).get('schema')==2,
            'cohort predates benchmark schema 2; re-measure it instead of relabelling it')
    require(receipt['complete'] and receipt['all_cases_passed'] and not receipt['failures'],'incomplete/failed cohort; do not silently omit failures')
    require(sha(folder/'plan.json')==receipt['plan_sha256'],'frozen plan digest')
    expected={(r['case'],r['position'],r['lane']) for r in plan['schedule']}
    actual=[(r['case'],r['position'],r['lane']) for r in receipt['runs']]
    require(len(actual)==len(set(actual)) and set(actual)==expected,'exact scheduled runs, no missing or duplicate samples')
    repeats=plan['benchmark']['repeats']
    groups=collections.defaultdict(list);samples=[]
    for order,index in enumerate(plan['schedule']):
        run=next(r for r in receipt['runs'] if (r['case'],r['position'],r['lane'])==(index['case'],index['position'],index['lane']))
        require(run['complete'] and run['output_correct'] and run['command']['complete'],'qualified native run')
        require(run['command']['timed_target_leg'],'qualification data are not performance samples')
        require(run['command'].get('exit_code')==0 and run['command'].get('reason') is None,'clean exit without guard')
        for k in ['wall_seconds','child_user_seconds','child_system_seconds']:
            require(math.isfinite(run['command'][k]) and run['command'][k]>=0,'finite nonnegative timings')
        if run['lane']=='mlf':require(run['fresh']>0 and run['reused']==0,'fresh MLF target')
        groups[run['case'],run['lane']].append(run)
        samples.append({'cohort':plan['benchmark']['cohort'],'order':order,'case':run['case'],'lane':run['lane'],
            'position':run['position'],'wall_seconds':run['command']['wall_seconds'],
            'child_user_seconds':run['command']['child_user_seconds'],
            'child_system_seconds':run['command']['child_system_seconds'],
            'exit_code':run['command'].get('exit_code'),'fresh':run.get('fresh'),'reused':run.get('reused'),
            'output_correct':run['output_correct'],'started_utc':run['command'].get('started_utc'),
            'executable_sha256':run.get('executable_sha256')})
    rows=[]
    for case in plan['cases']:
        require(sha(case['source'])==case['source_sha256'],'unchanged shared source')
        row={'cohort':plan['benchmark']['cohort'],'endpoint':plan['benchmark']['endpoint']['id'],
             'case':case['id'],'family':case['family'],'size':case['size'],
             'source_bytes':case['source_bytes'],'source_sha256':case['source_sha256']}
        for lane in ['ghc','mlf']:
            rs=groups[case['id'],lane];require(len(rs)==repeats,'exactly '+str(repeats)+' samples per compiler')
            times=[r['command']['wall_seconds'] for r in rs]
            row[lane+'_wall_median']=S.median(times);row[lane+'_wall_min']=min(times);row[lane+'_wall_max']=max(times)
            row[lane+'_wall_spread']=(max(times)-min(times))/S.median(times)
            row[lane+'_user_median']=S.median(r['command']['child_user_seconds'] for r in rs)
            row[lane+'_system_median']=S.median(r['command']['child_system_seconds'] for r in rs)
            row[lane+'_samples']=times
            if lane=='mlf':
                row['fresh']=rs[0]['fresh'];row['reused']=0;row['max_group_members']=rs[0]['max_group_members']
                require(all(r['fresh']==row['fresh'] for r in rs),'stable query group count')
                require(sum(r['raw_compared_with_first_mlf_leg'] for r in rs)==repeats-1,'actual raw-byte comparisons on every repetition')
                for stage in ['source-to-checked','checked-to-llvm','llvm-to-executable']:
                    ss=[next(s for s in r['stages']['stages'] if s['name']==stage) for r in rs]
                    for metric in ['wall_seconds','user_seconds','system_seconds']:
                        require(all(math.isfinite(s[metric]) and s[metric]>=0 for s in ss),'valid stage timings')
                        row[stage+'_'+metric+'_median']=S.median(s[metric] for s in ss)
                directories=[p for p in (folder/'legs').iterdir() if p.name.endswith(case['id']+'-mlf')]
                require(len(directories)==repeats,'all retained leg directories')
                inventories=[load(d/'query-cache-inventory.json') for d in directories]
                counts=[sum(k.endswith('.mlfq') for k in inv) for inv in inventories]
                require(all(n==row['fresh'] for n in counts),'one persisted query object per fresh group')
                row['query_files']=counts[0]
                row['query_bytes_median']=S.median(sum(v['bytes'] for k,v in inv.items() if k.endswith('.mlfq')) for inv in inventories)
        row['mlf_over_ghc']=row['mlf_wall_median']/row['ghc_wall_median'];rows.append(row)
    return rows,plan,receipt,samples


def markdown(report,rows,samples):
    benchmark=report['cohorts'][0]['benchmark']
    lines=['# Compiler shape benchmark summary','',
        'Suite `'+benchmark['suite']+'` version '+str(benchmark['suite_version'])+', cohort '
        +', '.join('`'+c['benchmark']['cohort']+'`' for c in report['cohorts'])+'.','',
        'Endpoint profile: `'+report['endpoint']+'` ('+benchmark['endpoint']['status']+'). '
        +benchmark['endpoint']['summary'],'',
        'Measured source:']
    for cohort in report['cohorts']:
        source=cohort['plan']['source']
        lines.append('- `'+source['commit']+'` on `'+source['branch']+'`, dirty: '
                     +('yes (patch sha256 `'+source['patch_sha256']+'`)' if source['dirty'] else 'no')
                     +', cohort `'+cohort['benchmark']['cohort']+'`')
    lines+=['',
        'Toolchain: GHC '+report['compatibility']['ghc_version']+', Clang '
        +str(report['compatibility']['clang_version'])+', producer receipt `'
        +report['compatibility']['producer_receipt_sha256']+'`.','',
        'Cells: '+str(len(rows))+', timed compilations: '+str(len(samples))+', repetitions per compiler per cell: '
        +str(report['compatibility']['repeats'])+'. Wall in seconds; ratio is MLF median / GHC median.','',
        '| Family | n | GHC median | MLF median | ratio | fresh groups | GHC spread | MLF spread |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for row in sorted(rows,key=lambda r:(r['family']!='baseline',r['family'],r['size'])):
        lines.append('| `'+row['family']+'` | '+str(row['size'])+' | {:.3f} | {:.3f} | {:.2f} | '.format(
            row['ghc_wall_median'],row['mlf_wall_median'],row['mlf_over_ghc'])
            +str(row.get('fresh','-'))+' | {:.1%} | {:.1%} |'.format(row['ghc_wall_spread'],row['mlf_wall_spread']))
    shaped=[r for r in rows if r['family']!='baseline']
    slower=[r for r in shaped if r['mlf_over_ghc']>1];faster=[r for r in shaped if r['mlf_over_ghc']<=1]
    lines+=['','Cells where MLF is slower: '+str(len(slower))+' of '+str(len(shaped))+'. '
            'Cells where MLF is not slower: '+str(len(faster))+
            (' ('+', '.join('`'+r['family']+'` n='+str(r['size']) for r in faster)+')' if faster else '')+'.']
    if report['duplicate_cells_across_cohorts']:
        lines+=['','Cells present in more than one cohort (listed, never combined): '
                +', '.join('`'+c['family']+'-'+str(c['size'])+'`' for c in report['duplicate_cells_across_cohorts'])+'.']
    lines+=['','## Reading this table','']
    lines+=['- '+limit for limit in report['claim_limits']]
    lines+=['- Spread is (max - min) / median over the recorded repetitions; it is a description of this window, not an error bar.',
            '- A ratio above 1.00 means MLF took longer for that cell in this cohort. It is not a universal speed claim.',
            '- Cohorts are separate windows and are never pooled into one median.','']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('cohorts',nargs='+',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--plot',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);rows=[];samples=[];cohorts=[];labels=set()
    for cohort in a.cohorts:
        data,plan,receipt,points=analyze(cohort);rows.extend(data);samples.extend(points)
        label=plan['benchmark']['cohort']
        require(label not in labels,'duplicate cohort label: '+label);labels.add(label)
        cohorts.append({'benchmark':plan['benchmark'],'plan':plan,'receipt_sha256':sha(cohort/'receipt.json'),
            'plan_sha256':sha(cohort/'plan.json'),'compile_runs':len(receipt['runs']),
            'executable_oracle_runs':sum(len(r['oracle_inputs']) for r in receipt['runs']),
            'cell_count':len(plan['cases']),'host':plan['host'],'compatibility':compatibility(plan),
            'source':plan['source']})
    reference=cohorts[0]['compatibility']
    for cohort in cohorts[1:]:
        difference=sorted(k for k in reference if cohort['compatibility'][k]!=reference[k])
        require(not difference,'incompatible cohorts differ in: '+', '.join(difference))
    seen=collections.Counter((r['family'],r['size']) for r in rows)
    report={'scope':'descriptive measured medians, ratio of medians; no confidence intervals; cohorts are never pooled',
        'endpoint':reference['endpoint'],
        'endpoint_summary':cohorts[0]['benchmark']['endpoint'],
        'native_installed_emlf_measured':False,
        'compatibility':reference,'claim_limits':cohorts[0]['benchmark']['claim_limits'],
        'cohorts':cohorts,
        'duplicate_cells_across_cohorts':[{'family':f,'size':s} for (f,s),n in sorted(seen.items()) if n>1],
        'counts':{'cells':len(rows),'samples':len(samples),'cohorts':len(cohorts),
                  'executable_oracle_runs':sum(c['executable_oracle_runs'] for c in cohorts)},
        'rows':rows}
    (a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    with (a.output/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (a.output/'samples.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(samples[0]));w.writeheader();w.writerows(samples)
    (a.output/'summary.md').write_text(markdown(report,rows,samples)+'\n')
    if a.plot:
        labels_in_report={c['benchmark']['cohort'] for c in cohorts}
        if not {'screen','group-extension'}<=labels_in_report:
            print('plot skipped: needs the original cohort names screen and group-extension',flush=True)
        else:
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
            fig.suptitle('MLF compiler shape study | GHC 9.14.1 -O2 | serial Clang -O2',fontsize=12,y=.985)
            fig.text(.5,.018,'Exploratory samples on one Mac. MLF private crate entry, not the installed native-library driver. Different cohorts are not pooled.',ha='center',fontsize=8)
            fig.tight_layout(rect=[0,.045,1,.96]);fig.savefig(a.output/'compiler-shapes.png',dpi=170);plt.close(fig)
    print(json.dumps({'rows':len(rows),'samples':len(samples),'cohorts':[c['benchmark']['cohort'] for c in cohorts],
        'compile_runs':sum(c['compile_runs'] for c in cohorts),
        'oracle_runs':sum(c['executable_oracle_runs'] for c in cohorts),'output':str(a.output.resolve())}))


if __name__=='__main__':main()
