#!/usr/bin/env python3
"""Describe the fixed eight-cell discovery window; no inferential statistics."""
from pathlib import Path
import argparse
import json,statistics,math,hashlib
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--workdir',type=Path,required=True)
p.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
a=p.parse_args();w=a.workdir.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
def require(ok):
 if not ok:raise ValueError('Incomplete or invalid fixed discovery cohort')
load=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
r=load(w/'curve/receipt.json');g=load(w/'ghc-reference/receipt.json')
require(r['complete'] and g['complete'] and len(r['runs'])==32 and len(g['runs'])==16)
rows=[]
for family in ['dependency_chain','inferred_chain']:
 for n in [32,128,512,2048]:
  case=f'{family}-{n}';sides={}
  for side in ['A','B']:
   legs=[x for x in r['runs'] if x['case']==case and x['side']==side]
   require(len(legs)==2 and all(x['complete'] and x['raw_bytes_equal'] and x['reused']==0 for x in legs))
   whole=[x['command']['wall_seconds'] for x in legs];require(all(math.isfinite(x) and x>0 for x in whole))
   stage={name:[next(s['wall_seconds'] for s in x['stages']['stages'] if s['name']==name) for x in legs] for name in ['source-to-checked','checked-to-llvm','llvm-to-executable']}
   sides[side]={'whole_seconds':whole,'whole_median':statistics.median(whole),'stages_seconds':stage,'stage_medians':{k:statistics.median(v) for k,v in stage.items()},'fresh':legs[0]['fresh']}
  gh=[x['command']['wall_seconds'] for x in g['runs'] if x['case']==case];require(len(gh)==2 and all(math.isfinite(x) and x>0 for x in gh))
  gm=statistics.median(gh)
  gain=1-math.exp(statistics.mean(map(math.log,sides['B']['whole_seconds']))-statistics.mean(map(math.log,sides['A']['whole_seconds'])))
  rows.append({'case':case,'family':family,'size':n,'sides':sides,'ghc_seconds':gh,'ghc_median':gm,'descriptive_geometric_time_reduction':gain,'candidate_over_ghc':sides['B']['whole_median']/gm})
summary={'complete':True,'baseline_ref':'48275901cd7b760cc8dd000ed54898a23a494a87','scope':'Fixed exploratory growth curve; one ABBA/BAAB block per cell; 2 samples per implementation; same-session separate GHC reference pass; no CI or asymptotic order claim.','endpoint':'crate-bootstrap-v1; fresh source to native executable, GHC 9.14.1 O2 hosted MLF; serial ordinary Clang O2; fixed primitive/runtime/builtin dependencies reused','raw_directory':str(w),'receipts':{name:{'path':str(w/name),'sha256':sha(w/name)} for name in ['curve/plan.json','curve/receipt.json','ghc-reference/receipt.json','controls/receipt.json','producer/receipt.json','builtin-refresh/receipt.json']},'rows':rows,'growth':{}}
large=[x for x in rows if x['size']==2048]
summary['screen_advancement']={'large_gain_and_frontend':all(x['descriptive_geometric_time_reduction']>=.05 and x['sides']['B']['stage_medians']['source-to-checked']<x['sides']['A']['stage_medians']['source-to-checked'] for x in large),'regression_cells_over_5pct':[x['case'] for x in rows if x['sides']['B']['whole_median']>1.05*x['sides']['A']['whole_median']]}
summary['screen_advancement']['regression_512_over_3pct']=[x['case'] for x in rows if x['size']==512 and x['sides']['B']['whole_median']>1.03*x['sides']['A']['whole_median']]
summary['decision']='Not advanced: the fixed discovery window did not meet its predeclared gain criterion; no confirmation, commit, or push.'
summary['mechanism_diagnostics']={}
for name in ['demand-mechanism-results/receipt.json','lowered-shape-mechanism-results/receipt.json']:
 f=w/name
 if f.exists():
  d=load(f);require(d['complete']);summary['mechanism_diagnostics'][name]={'path':str(f),'sha256':sha(f),'performance_sample':False}
summary['additional_qualification']={}
for name in ['validation/receipt.json','builtin/receipt.json','lock-validation.json']:
 f=w/name
 if f.exists():
  d=load(f);require(d['complete']);summary['additional_qualification'][name]={'complete':True,'sha256':sha(f),'path':str(f)}
for family in ['dependency_chain','inferred_chain']:
 small=next(x for x in rows if x['family']==family and x['size']==512);large=next(x for x in rows if x['family']==family and x['size']==2048)
 slope={side:(large['sides'][side]['whole_median']-small['sides'][side]['whole_median'])/1536 for side in ['A','B']}
 front={side:(large['sides'][side]['stage_medians']['source-to-checked']-small['sides'][side]['stage_medians']['source-to-checked'])/1536 for side in ['A','B']}
 summary['growth'][family]={'interval':[512,2048],'whole_increment_seconds_per_function':slope,'whole_increment_reduction':1-slope['B']/slope['A'],'frontend_increment_seconds_per_function':front,'frontend_increment_reduction':1-front['B']/front['A']}
(out/'results-20261101.json').write_text(json.dumps(summary,indent=2)+'\n')
for x in rows:
 a,b=x['sides']['A'],x['sides']['B']
 print(x['case'],f"GHC {x['ghc_median']:.4f}; A {a['whole_median']:.4f}; B {b['whole_median']:.4f}; gain {100*x['descriptive_geometric_time_reduction']:.2f}%; front {a['stage_medians']['source-to-checked']:.4f}->{b['stage_medians']['source-to-checked']:.4f}")
print('growth',json.dumps(summary['growth'],indent=2))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(3,2,figsize=(11,10),constrained_layout=True)
colors={'A':'#8a6e65','B':'#087f8c','GHC':'#7b43ad'}
for j,family in enumerate(['dependency_chain','inferred_chain']):
 data=[x for x in rows if x['family']==family];xs=[x['size'] for x in data]
 for i,stage in enumerate(['whole','source-to-checked','checked-to-llvm']):
  ax=axes[i,j]
  for side,label in [('A','Before (48275901)'),('B','Owned reservation')]:
   ys=[x['sides'][side]['whole_median'] if stage=='whole' else x['sides'][side]['stage_medians'][stage] for x in data]
   ax.plot(xs,ys,'o-',color=colors[side],label=label)
   for x in data:
    values=x['sides'][side]['whole_seconds'] if stage=='whole' else x['sides'][side]['stages_seconds'][stage]
    ax.scatter([x['size']]*2,values,color=colors[side],s=15,alpha=.45)
  if stage=='whole':ax.plot(xs,[x['ghc_median'] for x in data],'s--',color=colors['GHC'],label='GHC (separate pass)')
  ax.set_title(('Annotated' if j==0 else 'Inferred')+' chain: '+(['source to executable','source to checked','checked to LLVM'][i]))
  ax.set_xlabel('Number of generated functions');ax.set_ylabel('Seconds');ax.set_xticks(xs);ax.tick_params(axis='x',labelrotation=45,labelsize=9);ax.grid(alpha=.2);ax.set_ylim(bottom=0);ax.legend(fontsize=8)
fig.suptitle('Dependency-chain compilation growth — exploratory, 2 samples per point\nFixed binaries and inputs; no confidence interval or asymptotic-order claim',fontsize=12)
fig.savefig(out/'growth-20261101.png',dpi=180)
fig.savefig(out/'growth-20261101.svg')

# Normalize generated SVG line endings without changing geometry.
svg_path = out / 'growth-20261101.svg'
svg_path.write_text('\n'.join(line.rstrip() for line in svg_path.read_text().splitlines()) + '\n')
