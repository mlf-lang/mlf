"""Independent small final-summary arithmetic check; no reducer or target execution."""
from pathlib import Path
import ast,csv,hashlib,json,math
D=Path(__file__).parent;R=D.parent;F=R/'main-gap-sampling-summary-final';V1=R/'main-gap-sampling-summary-v1-source';V2=R/'main-gap-sampling-summary-v2-source';A=R/'main-gap-sampling-02-actual-review'
PINS={};CHECKS=[]
def need(v,m):
 if not v:raise AssertionError(m)
def pin(p):
 p=Path(p);need(p.is_file()and not p.is_symlink(),'regular');b=p.read_bytes();v={'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};PINS[str(p)]=v;return v
def full(v):need(pin(v['path'])==v,'pin exact');return Path(v['path'])
def load(p):return json.loads(Path(p).read_bytes())
def fixed(p,h):need(pin(p)['sha256']==h,'fixed hash '+str(p));return load(p)
def manifest(p,h):
 m=fixed(p,h)
 for v in m['files']:full(v)
 need({str(x)for x in p.parent.iterdir()}=={str(p)}|{v['path']for v in m['files']},'manifest exact membership')
 return m
def save(n,v):
 with(D/n).open('x')as f:json.dump(v,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def yes(m):CHECKS.append(m)
manifest(F/'MANIFEST.json','66b31ad252834302fba43442c8ff00b81f3a757267940f83c10ef1da3e88af2a')
r=fixed(F/'report.json','22206fa0769fc821baffad0a64f7cbf0f6cd4edc218f63a0dd0abca5468e2a79');need(pin(F/'SUMMARY.md')['sha256']=='f870587ac6a4b883f1a8cf9299c8783675d503c1931bbe19f5e52f64c8c5898c','summary text')
manifest(V2/'MANIFEST.json','28ac7cd3a67df5d3bcef01b42d6b277e1386ca21d8ef01342bf26241834d840d')
manifest(V1/'MANIFEST.json','9a7e7092ff212693509f5edafc721bdd4ee3c904f0eec489f88d23d0d1f9f6f9')
one=(V1/'reduce.py').read_bytes();two=(V2/'reduce.py').read_bytes();old=b' if n>0 else None,';new=b' if type(n) is int and n>0 else None,'
need(one.count(old)==1 and two==one.replace(old,new,1),'exact onepredicate byte delta')
need((V1/'rts_parser.py').read_bytes()==(V2/'rts_parser.py').read_bytes(),'parser exact unchanged')
node=next(x for x in ast.parse(two).body if isinstance(x,ast.FunctionDef)and x.name=='pair_summary')
conditions=[x.test for x in ast.walk(node)if isinstance(x,ast.IfExp)]
need(len(conditions)==1 and ast.dump(conditions[0],include_attributes=False)==ast.dump(ast.parse('type(n) is int and n>0',mode='eval').body,include_attributes=False),'exact positive integer predicate AST')
for n in [None,0,-1,True,False,1.0,'16']:
 need(not(type(n)is int and n>0),'excluded no normalization')
for n in [1,16,256]:need(type(n)is int and n>0,'valid positive size')
yes('frozen final/reducer manifests and exact onepredicate None/nonpositive/noninteger fix; reducer not run')
combined=fixed(A/'combined-final.json','33829f5e71c9a1ed5cc530566450ef06d473dba8de4b5abbc6c554657983c408')
need(r['actual_combined_review']==pin(A/'combined-final.json') and r['actual_combined_sampling_passed']is True and r['complete']is True and r['blockers']==[],'wrapper authoritative actual status')
need(combined['combined_48leg_sampling_passed']is True and combined['cleanup_lease_locks']is True and combined['blockers']==[],'actual combined qualified')
source=load(full(combined['samples']));need(len(source)==48,'actual original48 sample rows')
results=load(F/'results.json');spec=load(F/'actual-input.json');need(results['input_contract']==spec and r['input']==pin(F/'actual-input.json'),'actual reduction inputs')
for v in [spec['cells'],spec['legs'],spec['parser_source'],spec['qualification_review'],spec['sampling_source_manifest']]:full(v)
cells=load(spec['cells']['path'])['cells'];legs=load(spec['legs']['path'])['rows'];need(len(cells)==12 and len(legs)==48,'fixed static ledger')
for i,b in enumerate(spec['blocks'],1):
 review=load(full(b['actual_review']));need(b['block']==i and b['actual_review']==r['actual_stage_reviews'][i-1] and review['actual_pins']['worker']==b['worker'],'actual report input association')
need(results['observations_present']==48 and results['complete_48_observations']is True and results['all_48_independently_stage_reviewed']is True,'full no pending observation')
metrics=('guard_elapsed_seconds','MUT_cpu_seconds','GC_cpu_seconds','Total_cpu_seconds','allocated_bytes','copied_bytes','maximum_residency_bytes')
def ratio(a,b,rounded=False):
 need(all(type(x)in(int,float)and math.isfinite(x)and x>=0 for x in [a,b]),'finite nonnegative')
 if rounded and(a==0 or b==0):return {'value':None,'reason':'zero rounded RTS time; unresolved ratio'}
 return {'value':a/b if b>0 else None,'reason':None if b>0 else 'zero (possibly rounded) denominator'}
observations=[]
for actual,leg in zip(source,legs):
 parsed=actual['RTS']['parsed'];m={'guard_elapsed_seconds':actual['guard_elapsed_seconds'],**{k+'_cpu_seconds':parsed['times'][k]['cpu_seconds']for k in ['MUT','GC','Total']},**{k:parsed[k]for k in ['allocated_bytes','copied_bytes','maximum_residency_bytes']}}
 need((actual['leg_ordinal'],actual['leg_id'],actual['cell'],actual['lane'])==(leg['ordinal'],leg['id'],leg['cell'],leg['lane']),'original order no picked row')
 expected={'leg_id':actual['leg_id'],'ordinal':actual['leg_ordinal'],'cell':actual['cell'],'lane':actual['lane'],'block':1 if actual['leg_ordinal']<=24 else 2,'review_status':'independent_stage_review_passed','metrics':m,'rts_times':parsed['times'],'gc_cpu_fraction_from_rounded_times':ratio(m['GC_cpu_seconds'],m['Total_cpu_seconds'],True),'major_gc_residency_samples':parsed['major_gc_residency_samples'],'guard':actual['guard'],'RTS':actual['RTS']['raw']}
 observations.append(expected)
need(results['raw_observations']==observations,'exact all48 fields metrics RTTtimes pins and order')
with(F/'all48-observations.csv').open()as f:csvrows=list(csv.DictReader(f))
need(len(csvrows)==48,'CSV48')
for x,y in zip(csvrows,observations):
 need({k:x[k]for k in ['leg_id','cell','lane']}=={k:y[k]for k in ['leg_id','cell','lane']} and int(x['ordinal'])==y['ordinal'] and int(x['block'])==y['block'],'CSV identity')
 for k in metrics:need(float(x[k])==y['metrics'][k],'CSV metric')
 for k in ['RTS','guard']:need(x[k+'_path']==y[k]['path']and x[k+'_sha256']==y[k]['sha256'],'CSV evidence pins')
yes('all48 reducer rows and public CSV exactly match already-reviewed observations, evidence pins and every metric')
out=[]
for c in cells:
 need(type(c['source_bytes'])is int and c['source_bytes']>0,'sourcebyte positive')
 by={}
 for lane in ['M','G']:
  rows=[x for x in observations if x['cell']==c['id']and x['lane']==lane];need(len(rows)==2,'two observations')
  by[lane]={'status':'independent_stage_review_passed','observations':rows,'mean':{k:sum(x['metrics'][k]for x in rows)/2 for k in metrics},'per_size':{k:[x['metrics'][k]/c['size']for x in rows]for k in metrics}if type(c['size'])is int and c['size']>0 else None,'per_source_byte':{k:[x['metrics'][k]/c['source_bytes']for x in rows]for k in metrics}}
 out.append({'cell':c['id'],'family':c['family'],'size':c['size'],'source_bytes':c['source_bytes'],'M':by['M'],'G':by['G'],'M_over_G_two_observation_mean':{k:ratio(by['M']['mean'][k],by['G']['mean'][k],k.endswith('_cpu_seconds'))for k in metrics}})
need(results['cells']==out,'all means ratios normalizations exact')
adj=[]
for fam in ['flat_functions','higher_order_chain']:
 group=[x for x in out if x['family']==fam];need([x['size']for x in group]==[16,32,64,128,256],'five fixed sizes')
 for a,b in zip(group,group[1:]):
  for lane in ['M','G']:adj.append({'family':fam,'lane':lane,'from_size':a['size'],'to_size':b['size'],'input_multiplier':2,'mean_metric_multiplier':{k:ratio(b[lane]['mean'][k],a[lane]['mean'][k],k.endswith('_cpu_seconds'))for k in metrics},'not_asymptotic_proof':True})
need(results['adjacent_size_gradients']==adj,'all16 adjacent gradients exact')
yes('all12 per-endpoint means,7 mean ratios,per-size/per-source-byte values,and16 adjacent gradient rows independently recomputed')
findings=load(F/'findings.json');f=next(x for x in out if x['cell']=='foundation14');fm=f['M']['mean'];fg=f['G']['mean']
need(findings['foundation']=={'M_GC_share_of_Total_rounded_CPU':fm['GC_cpu_seconds']/fm['Total_cpu_seconds'],'M_mutator_share_of_Total_rounded_CPU':fm['MUT_cpu_seconds']/fm['Total_cpu_seconds'],'M_over_G_mean_ratios':f['M_over_G_two_observation_mean'],'original_observations':{lane:[x['metrics']for x in f[lane]['observations']]for lane in ['M','G']},'two_observation_means':{'M':fm,'G':fg}},'allFoundation findings exact')
for fam in ['flat_functions','higher_order_chain']:
 group=[x for x in out if x['family']==fam];first,last=group[0],group[-1]
 expected={'sizes':[16,32,64,128,256],'M_adjacent_GC_CPU_multipliers':[x['mean_metric_multiplier']['GC_cpu_seconds']['value']for x in adj if x['family']==fam and x['lane']=='M'],'M_adjacent_Total_CPU_multipliers':[x['mean_metric_multiplier']['Total_cpu_seconds']['value']for x in adj if x['family']==fam and x['lane']=='M'],'mean_Total_CPU_seconds':{lane:[x[lane]['mean']['Total_cpu_seconds']for x in group]for lane in ['M','G']},'n16_to_n256_allocation_multiple':{lane:last[lane]['mean']['allocated_bytes']/first[lane]['mean']['allocated_bytes']for lane in ['M','G']},'n16_to_n256_total_CPU_multiple':{lane:last[lane]['mean']['Total_cpu_seconds']/first[lane]['mean']['Total_cpu_seconds']for lane in ['M','G']}}
 need(findings['growth'][fam]==expected,'growth findings exact')
need(all(x['mean_metric_multiplier']['Total_cpu_seconds']['value']<=2 for x in adj),'descriptive observed adjacent TotalCPU growth no greater than2')
need(next(x for x in out if x['cell']=='baseline-0')['M']['per_size']is None and f['M']['per_size']is None,'excluded baselinezero/FoundationNone')
summary=(F/'SUMMARY.md').read_text()
for phrase in ['38.25×','70.51×','12.55×','30.61×','118.48×','37.22×','2.43×','20.8465s','82.0%','18.0%','5.21×','6.10×','2.05×','2.39×','1.22、1.36、1.84、1.71','1.17、1.01、1.24、1.40']:need(phrase in summary,'correct displayed numeric summary')
need(r['claims']=={'CPU_algorithm_attribution':False,'asymptotic_complexity_proved':False,'equivalent_GHC_endpoint':False,'production_promotion':False,'stable_speedup':False,'statistical_significance':False},'no stronger claims')
need(findings['limitations']==results['limitations'] and len(results['limitations'])==9,'all interpretation caveats retained')
need(results['final_combined_review']=='pending; this reducer does not issue a qualification or execution gate' and 'Final combined review remains pending.'in(F/'results.md').read_text(),'generic placeholder explicitly identified')
need('本目录`report.json`单独绑定' in summary and '作为当前资格状态' in summary,'summary makes wrapper authoritative')
yes('Foundation shares and ratios plus complete ladder findings and displayed rounding correct; honest endpoint/two-observation/complexity boundaries')
report={'schema':'main-gap-sampling-summary-independent-review-v1','complete':True,'summary_review_passed':True,'blockers':[],'scope':'Read-only numerical/presentation cross-check, not a new actual-execution or full source gate. No prior targets or48-leg lifecycle repeated.','summary_report':pin(F/'report.json'),'summary_manifest':pin(F/'MANIFEST.json'),'summary_markdown':pin(F/'SUMMARY.md'),'reducer_v2_manifest':pin(V2/'MANIFEST.json'),'actual_combined_review':pin(A/'combined-final.json'),'reviewed_combined_sample_inventory':combined['samples'],'observation_count':48,'cell_count':12,'exact_all48_observations':True,'exact_all_means_normalizations_and_ratios':True,'exact_all16_gradient_rows':True,'exact_foundation_and_ladder_findings':True,'None_nonpositive_noninteger_size_no_normalization':True,'source_delta_only_positive_integer_size_predicate':True,'source_or_target_execution':False,'new_samples':0,'checks':CHECKS,'key_observations':{'Foundation_M_Total_CPU_mean':fm['Total_cpu_seconds'],'Foundation_G_Total_CPU_mean':fg['Total_cpu_seconds'],'Foundation_M_over_G_Total_CPU_mean_ratio':fm['Total_cpu_seconds']/fg['Total_cpu_seconds'],'Foundation_M_MUT_share':fm['MUT_cpu_seconds']/fm['Total_cpu_seconds'],'Foundation_M_GC_share':fm['GC_cpu_seconds']/fm['Total_cpu_seconds'],'ratios_are_different_endpoints_not_equivalent_work':True},'interpretation':{'two_observations_per_endpoint_cell':True,'stable_speedup_or_significance_claimed':False,'GHC_parity_claimed':False,'asymptotic_complexity_proved':False,'lifecycle_durations_used_as_metrics':False,'MUT_algorithm_attribution_claimed':False,'baseline_subtraction_or_first_sample_discarded':False},'presentation_note':{'blocking':False,'generic_results_pending_is_not_current_status':True,'current_status_source':pin(F/'report.json'),'minimal_public_recommendation':'Use SUMMARY.md/report.json as the public landing entry. If linking or displaying results.md/results.json directly, prepend an external caption: “The fixed48 observations passed independent combined review 33829f5e…; the reducer’s pending placeholder is a retained template, not current review status.” Keep original frozen files unchanged.','another_measurement_or_sourcegate_needed':False},'review_program':pin(__file__)}
save('report.json',report);save('verified-inputs.json',sorted(PINS.values(),key=lambda x:x['path']))
with(D/'NOTE.md').open('x')as f:f.write('# Summary verification\n\nPASS. All48 observations, complete means/normalizations/ratios,16 gradient rows and Foundation/ladder findings exactly match the already-reviewed data. No reducer, helper, target or raw-lifecycle rerun.\n\nPublic presentation: land on SUMMARY.md/report.json. When exposing the generic results files directly, add a caption pointing to the actual combined PASS and explaining that their retained pending template is not current status. This is nonblocking and does not require changing frozen evidence. Preserve typed-only versus frontend and two-observation limitations; no stable speedup or complexity proof.\n')
files=[pin(p)for p in sorted(D.iterdir())];save('MANIFEST.json',{'schema':'independent-summary-review-manifest-v1','complete':True,'files':files})
for v in files:need(pin(v['path'])==v,'final exact readback')
print(json.dumps({'report':pin(D/'report.json'),'manifest':pin(D/'MANIFEST.json'),'members':len(files),'complete':True,'stopped_writing':True}))
