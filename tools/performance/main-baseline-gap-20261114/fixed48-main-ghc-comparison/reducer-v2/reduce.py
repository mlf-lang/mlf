"""Read-only fixed-48 descriptive reducer. JSON to stdout; no runner/target imports."""
import hashlib
import json
import math
from pathlib import Path
import sys
from rts_parser import parse_statistics

ROOT = Path('<EXPERIMENT_ROOT>')
EXPECTED = {
 'cells':'3b5a5d5c486186a50cb45f248e2c9522b2437ae69257025770e02189e94ddaf3',
 'legs':'53dcf311abd779697726d56bfd09a31d77aae0e8c278cd1551cdee280a546be8',
 'parser_source':'b558556b11af12b117444f6476c5e841fa1b4beddc8f7cfe5e13047f2426a84c',
 'sampling_source_manifest':'8d8fb5fdc68f15d404e2e962aab15dd1def5266179a7cd6c207c902d421da099',
 'qualification_review':'9293db948fe9393f28f6153ee514eb16e1c1ee3c8b1ec0fe15ffa9d762232a41'
}
METRICS = ('guard_elapsed_seconds','MUT_cpu_seconds','GC_cpu_seconds','Total_cpu_seconds',
           'allocated_bytes','copied_bytes','maximum_residency_bytes')
LIMITATIONS = [
 'Each endpoint/cell has two observations only. Means, ratios and adjacent gradients are descriptive, not confidence intervals, stable improvements, statistical significance or asymptotic complexity proofs.',
 'M is the MLF frontend checked/published-artifact endpoint; G is GHC typed interfaces only. Same inputs do not make the endpoints identical work or establish GHC parity.',
 'Guard elapsed includes supervision/polling overhead and clock/sampling effects; it is not exact child process wall time. Stage/qualification/cleanup elapsed never enters these metrics.',
 'RTS MUT/GC/Total CPU and elapsed are rounded process totals. Small or zero rounded denominators cannot support reliable ratios. MUT is not attribution to a specific compiler algorithm.',
 'Maximum residency is major-GC sampled live bytes, not peak RSS. Copied bytes are GC copying, not a graph-copy or compiler-constraint counter.',
 'Fresh application/query caches do not imply OS page-cache cold. System caches were not dropped; controls are qualification observations, not added samples.',
 'No input has been rerun, discarded, substituted, baseline-subtracted or timing-corrected. Ratios use the arithmetic mean of the two original observations, with both originals retained.',
 'Runtime graph visits/copies/constraints were not instrumented. Source size is a static normalization variable, not measured compiler work.',
 'This reducer verifies report/worker/child/RTS provenance and numerical reduction, not a replacement for the independent lifecycle/raw-semantic review or final combined review.'
]

def need(v, message):
    if not v: raise ValueError(message)

def number(v):
    need(type(v) in (int,float) and math.isfinite(v) and v>=0,'invalid nonnegative number')
    return v

def checked(pin):
    need(isinstance(pin,dict) and set(pin)=={'path','bytes','sha256'},'full pin required')
    need(type(pin['path']) is str and type(pin['bytes']) is int and pin['bytes']>=0,'pin type')
    p=Path(pin['path']);need(p.is_file() and not p.is_symlink(),'pinned regular file')
    b=p.read_bytes()
    need(len(b)==pin['bytes'] and hashlib.sha256(b).hexdigest()==pin['sha256'],'pin mismatch '+str(p))
    return b

def load(pin): return json.loads(checked(pin))

def ratio(a,b,rounded=False):
    if a is None or b is None: return {'value':None,'reason':'pending observation'}
    number(a);number(b)
    if rounded and (a==0 or b==0): return {'value':None,'reason':'zero rounded RTS time; unresolved ratio'}
    return {'value':a/b if b>0 else None,'reason':None if b>0 else 'zero (possibly rounded) denominator'}

def pair_summary(rows, n, source_bytes):
    if not rows: return {'status':'pending','observations':None,'mean':None,'per_size':None,'per_source_byte':None}
    need(len(rows)==2,'exact two observations per endpoint/cell')
    means={k:sum(r['metrics'][k] for r in rows)/2 for k in METRICS}
    return dict(status=rows[0]['review_status'],observations=rows,mean=means,
                per_size={k:[r['metrics'][k]/n for r in rows] for k in METRICS} if type(n) is int and n>0 else None,
                per_source_byte={k:[r['metrics'][k]/source_bytes for r in rows] for k in METRICS})

def read_block(desc, expected, source_manifest, qualification):
    block=desc['block'];need(type(block) is int and block in (1,2),'block identity')
    if desc['worker'] is None:
        need(desc['actual_review'] is None,'review without worker')
        return [],{'block':block,'status':'pending','worker':None,'actual_review':None}
    need(desc['worker']['path']==str(ROOT/'main-gap-setup-run04'/('sampling-%02d'%block)/'sampling-receipt.json'),'worker scope path')
    w=load(desc['worker'])
    need(w['schema']=='main-gap-sampling-worker-v1' and w['complete'] is True and w['block']==block,'worker success/block')
    need(w['combined_qualification_review']==qualification and w['sampling_oracles_rebased'] is False,'qualification/oracle identity')
    need(w['counts']=={'measured_leg':24,'runtime':8} and len(w['commands'])==32 and len(w['samples'])==24 and len(w['statistics'])==24,'fixed stage counts')
    status='actual_review_pending'
    if desc['actual_review'] is not None:
        need(desc['actual_review']['path']==str(ROOT/('main-gap-sampling-%02d-actual-review'%block)/'report.json'),'review path')
        r=load(desc['actual_review'])
        need(r['schema']=='main-gap-sampling-actual-review-v1' and r['complete'] is True and r['actual_sampling_stage_passed'] is True and r['cleanup_lease_locks'] is True and r['blockers']==[],'actual review not passed')
        need(r['block']==block and r['phase']=='SAMPLE'+str(block),'actual review phase')
        need(r['actual_pins']['worker']==desc['worker'] and r['combined_qualification_review']==qualification and r['source_package_manifest']==source_manifest,'review provenance')
        # Stage elapsed is deliberately not read into the result metrics.
        status='independent_stage_review_passed'
    cmds=w['commands'];need([x['kind'] for x in cmds]==['runtime']*4+['measured_leg']*24+['runtime']*4,'command spine')
    rows=[]
    for i,(s,e,c) in enumerate(zip(w['samples'],expected,cmds[4:28])):
        need((s['leg_id'],s['leg_ordinal'],s['cell'],s['lane'])==(e['id'],e['ordinal'],e['cell'],e['lane']),'fixed leg order/identity')
        need(c['label']=='leg-'+e['id'] and c['receipt']==s['actual_guard'],'sample/command pin')
        g=load(c['receipt']);need(g==c['guard'] and g['complete'] is True and g['exit_code']==0 and g['cleanup'] is True,'child guard result')
        need(g['elapsed_seconds']==s['guard_elapsed_seconds'],'guard elapsed differs')
        rt=s['RTS'];need(rt==w['statistics'][i] and rt['sampling_leg']==e['id'] and rt['command']==c['label'] and rt['qualification_only'] is False,'RTS role/order')
        need(rt['raw'] in g['archived'].values(),'RTS not child archived output')
        parsed=parse_statistics(checked(rt['raw']));need(parsed==rt['parsed'],'RTS raw/parsed mismatch')
        m={'guard_elapsed_seconds':number(g['elapsed_seconds'])}
        for k in ('MUT','GC','Total'):m[k+'_cpu_seconds']=number(parsed['times'][k]['cpu_seconds'])
        for k in ('allocated_bytes','copied_bytes','maximum_residency_bytes'):
            need(type(parsed[k]) is int,'byte metric integer');m[k]=number(parsed[k])
        need(s['exact_process_wall_ns'] is None and s['child_user_cpu'] is None and s['child_system_cpu'] is None and s['runtime_graph_visit_copy_constraint_counters'] is None,'unmeasured fields must remain unknown')
        rows.append(dict(leg_id=e['id'],ordinal=e['ordinal'],cell=e['cell'],lane=e['lane'],block=block,
                         review_status=status,metrics=m,rts_times=parsed['times'],
                         gc_cpu_fraction_from_rounded_times=ratio(m['GC_cpu_seconds'],m['Total_cpu_seconds'],rounded=True),
                         major_gc_residency_samples=parsed['major_gc_residency_samples'],guard=c['receipt'],RTS=rt['raw']))
    return rows,dict(block=block,status=status,worker=desc['worker'],actual_review=desc['actual_review'])

def reduce_inputs(spec):
    need(spec['schema']=='sampling-summary-input-v1','input schema')
    need(all(spec[k]['sha256']==sha for k,sha in EXPECTED.items()),'frozen input identity')
    # The copied parser must be byte-identical to the pinned, previously reviewed pure parser.
    need(checked(spec['parser_source'])==Path(__file__).with_name('rts_parser.py').read_bytes(),'parser copy identity')
    checked(spec['sampling_source_manifest']);q=load(spec['qualification_review'])
    need(q['combined_12cell_qualification_passed'] is True and q['blockers']==[],'combined semantic qualification')
    cells=load(spec['cells'])['cells'];legs=load(spec['legs'])['rows']
    need(len(cells)==12 and len(legs)==48 and [r['ordinal'] for r in legs]==list(range(1,49)),'fixed inventory')
    need([b['block'] for b in spec['blocks']]==[1,2],'blocks exactly 1,2')
    for i,c in enumerate(cells):
        es=legs[i*4:(i+1)*4]
        need([e['cell'] for e in es]==[c['id']]*4 and [e['lane'] for e in es]==['M','G','G','M'],'fixed MGGM')
        need(type(c['source_bytes']) is int and c['source_bytes']>0,'source byte denominator')
    allrows=[];states=[]
    for d in spec['blocks']:
        rows,state=read_block(d,legs[(d['block']-1)*24:d['block']*24],spec['sampling_source_manifest'],spec['qualification_review'])
        allrows+=rows;states.append(state)
    need(not allrows or [r['ordinal'] for r in allrows]==list(range(1,len(allrows)+1)),'no skipped/picked blocks')
    out=[]
    for c in cells:
        by={lane:pair_summary([r for r in allrows if r['cell']==c['id'] and r['lane']==lane],c['size'],c['source_bytes']) for lane in ('M','G')}
        compare={k:ratio(by['M']['mean'][k] if by['M']['mean'] else None,by['G']['mean'][k] if by['G']['mean'] else None,rounded=k.endswith('_cpu_seconds')) for k in METRICS}
        out.append(dict(cell=c['id'],family=c['family'],size=c['size'],source_bytes=c['source_bytes'],M=by['M'],G=by['G'],M_over_G_two_observation_mean=compare))
    adjacent=[]
    for family in ('flat_functions','higher_order_chain'):
        group=[x for x in out if x['family']==family]
        need([x['size'] for x in group]==[16,32,64,128,256],'fixed size ladder')
        for a,b in zip(group,group[1:]):
            for lane in ('M','G'):
                ratios={k:ratio(b[lane]['mean'][k] if b[lane]['mean'] else None,a[lane]['mean'][k] if a[lane]['mean'] else None,rounded=k.endswith('_cpu_seconds')) for k in METRICS}
                adjacent.append(dict(family=family,lane=lane,from_size=a['size'],to_size=b['size'],input_multiplier=2,
                                     mean_metric_multiplier=ratios,not_asymptotic_proof=True))
    return dict(schema='main-gap-descriptive-sampling-summary-v1',input_contract=spec,blocks=states,
                observations_present=len(allrows),complete_48_observations=len(allrows)==48,
                all_48_independently_stage_reviewed=len(allrows)==48 and all(s['status']=='independent_stage_review_passed' for s in states),
                final_combined_review='pending; this reducer does not issue a qualification or execution gate',
                raw_observations=allrows,cells=out,adjacent_size_gradients=adjacent,limitations=LIMITATIONS)

def markdown(result):
    lines=['# Main compiler gap: descriptive observations','',
           f"Data present: {result['observations_present']}/48. Final combined review remains pending.",'',
           'Each lane lists its two raw observations in execution order. Units: seconds for guard/CPU, bytes for allocation/copy/residency. No stage elapsed is included.','']
    for c in result['cells']:
        lines += ['## '+c['cell'],f"Static size={c['size']}; source bytes={c['source_bytes']}.",'',
                  '| Lane / review | guard elapsed | MUT CPU | GC CPU | Total CPU | allocated B | GC copied B | max residency B |',
                  '|---|---|---|---|---|---|---|---|']
        for lane in ('M','G'):
            p=c[lane];vals=['pending']*7 if p['observations'] is None else [', '.join(str(r['metrics'][k]) for r in p['observations']) for k in METRICS]
            lines+=['| '+lane+' / '+p['status']+' | '+' | '.join(vals)+' |']
        lines+=['']
    def display(v): return 'pending/unresolved' if v is None else format(v,'.6g')
    lines+=['## Adjacent input doubling (ratios of two-observation means)','',
            '| Family / lane | n → 2n | guard | MUT CPU | GC CPU | Total CPU | allocation |',
            '|---|---|---|---|---|---|---|']
    for a in result['adjacent_size_gradients']:
        keys=('guard_elapsed_seconds','MUT_cpu_seconds','GC_cpu_seconds','Total_cpu_seconds','allocated_bytes')
        lines+=['| '+a['family']+' / '+a['lane']+' | '+str(a['from_size'])+' → '+str(a['to_size'])+' | '+' | '.join(display(a['mean_metric_multiplier'][k]['value']) for k in keys)+' |']
    lines+=['','## Per generated size unit (two original values)','',
            '| Cell / lane | MUT CPU s/n | Total CPU s/n | allocation B/n |',
            '|---|---|---|---|']
    for c in result['cells']:
        if c['family'] not in ('flat_functions','higher_order_chain'): continue
        for lane in ('M','G'):
            normalized=c[lane]['per_size']
            values=['pending']*3 if normalized is None else [', '.join(display(v) for v in normalized[k]) for k in ('MUT_cpu_seconds','Total_cpu_seconds','allocated_bytes')]
            lines+=['| '+c['cell']+' / '+lane+' | '+' | '.join(values)+' |']
    lines+=['','Displayed arithmetic precision does not improve the resolution of the source clocks or rounded RTS totals. Baseline n=0 is not divided; Foundation is not a point on either shape ladder.','']
    lines+=['## Interpretation boundaries','']+['- '+s for s in LIMITATIONS]
    lines+=['','Full JSON also retains raw pins, rounded RTS elapsed fields, M/G ratios, per-size/per-source-byte values and every adjacent doubling. Missing values are null, never zero.','']
    return '\n'.join(lines)

if __name__=='__main__':
    need(len(sys.argv) in (2,3),'usage: python3 -B reduce.py INPUT.json [--markdown]')
    result=reduce_inputs(json.loads(Path(sys.argv[1]).read_bytes()))
    if len(sys.argv)==3:
        need(sys.argv[2]=='--markdown','unknown option');print(markdown(result))
    else: print(json.dumps(result,indent=2,sort_keys=True,allow_nan=False))
