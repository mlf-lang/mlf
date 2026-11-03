#!/usr/bin/env python3
"""Partition elapsed time with exclusive clocks; inspect the real cache after timing."""
from collections import Counter
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]/'shared'))
from artifact_binary_reference import read_document

RUN, OUT = map(Path,sys.argv[1:3])
study = json.loads((RUN/'results.json').read_text())
if not study['complete']:
    raise RuntimeError('incomplete study')
OUT.mkdir(parents=True,exist_ok=True)
samples = study['samples']
warm = [s for s in samples if not s['preflight']]
details = [s for s in warm if s['arm']=='D']
coarse = [s for s in warm if s['arm']=='C']
plain = [s for s in warm if s['arm']=='P']
expected_order=list('PCDDCP') if 'primary_compiler_sha256' in study else list('PCDCDPDPC')
if [s['arm'] for s in warm] != expected_order:
    raise RuntimeError('unexpected sample sequence')

def distribution(ns):
    values = [n/1e9 for n in ns]
    return dict(mean_s=statistics.mean(values),min_s=min(values),max_s=max(values))

def leaf(rows, tag):
    matches=[v for k,v in rows.items() if k.split('/')[-1]==tag]
    if not matches:
        raise RuntimeError('missing span: '+tag)
    return [sum(v[i] for v in matches) for i in range(3)]

def collect(rows, target, mode):
    values=Counter()
    for path,(_,_,exclusive) in rows.items():
        fields=path.split('/')
        if target in fields:
            values[mode(fields[fields.index(target):])]+=exclusive
    if sum(values.values())!=leaf(rows,target)[1]:
        raise RuntimeError('overlapping or missing partition: '+target)
    return values

def hit_category(fields):
    name=fields[-1]
    if name=='file.c-read': return 'C bounded file read'
    if name in ('file.read','file.stat'): return 'file acquisition outside C read'
    if name=='context.sha': return 'context SHA'
    if name.startswith(('wire.','typed.','symbol.')): return 'wire and typed decoding'
    if name.startswith('key.'): return 'key and context proof'
    if name.startswith('xmlf.'): return 'xMLF type checking'
    if name.startswith('checksum.'): return 'object fingerprints'
    if name in ['interface.validate','datatype.validate','syntax.body','syntax.unit','raw.validate']:
        return 'syntax, interface, ownership and layouts'
    if name in ['raw.checkUnit','raw.record','context.load','hit']: return 'other hit work'
    raise RuntimeError('unclassified hit phase: '+name)

END_PHASES={'hit','finish','prelude','final.write','final.report','assembly','frontend.load','frontend.prepare','group.prepare',
            'scratch.force','scratch.write','scratch.sha','compiler.sha','group.record-stat','preparedRaw',
            'final.objectWHNF','final.contractsWHNF'}

def session_category(fields):
    for tag in fields:
        if tag in END_PHASES:
            return tag
    return 'remaining driver work'

def table(counters):
    keys=sorted(set().union(*(r.keys() for r in counters)))
    return dict(sorted(((k,distribution(r[k] for r in counters)) for k in keys),
                       key=lambda row:-row[1]['mean_s']))

def subtree(target,kind):
    return table([collect(s['spans'],target,kind) for s in details])

def cache_shape():
    report=json.loads((RUN/'final.queries').read_text())
    counts=Counter()
    field_sizes=Counter()
    mru=[]
    for group in report['groups']:
        cache=RUN/'cache'
        record=(cache/(group['query_key']+'.mlfq')).read_bytes()
        doc=read_document(record,2)
        def node(index,tag):
            entry=doc.nodes[index]
            if entry.kind!=3 or entry.data[0]!=tag:raise ValueError('unexpected node')
            return entry.data[1]
        def text_id(index):
            entry=doc.nodes[index]
            if entry.kind!=2:raise ValueError('expected symbol')
            return entry.data
        ref,compact,_,_=node(doc.roots[0],301)
        digest=doc.symbols[text_id(ref)]
        ids=[text_id(v) for v in node(compact,1)]
        if len(ids)!=8 or doc.symbols[ids[0]]!='MLF-SOURCE-CRATE-QUERY-7' or doc.symbols[ids[2]]!=study['compiler_sha256']:
            raise ValueError('wrong v7 record or compiler identity')
        counts['records']+=1
        counts['record_bytes']+=len(record)
        counts['record_symbols']+=len(doc.symbols)
        counts['record_symbol_utf8_bytes']+=sum(doc.symbol_sizes)
        counts['distinct_record_symbol_bytes_referenced_by_compact_fields']+=sum(doc.symbol_sizes[i] for i in set(ids))
        for name,i in zip(['format','crate','compiler','members','bindings','prepared','contracts','scopes'],ids):
            field_sizes[name]+=doc.symbol_sizes[i]
        if digest not in mru:
            counts['context_reads']+=1
            counts['context_read_bytes']+=(cache/('context-'+digest+'.mlfqc')).stat().st_size
        mru=[digest]+[k for k in mru if k!=digest][:7]
    for s in details:
        rows=s['spans']
        reads=sum(row[0] for path,row in rows.items() if 'hit' in path.split('/') and path.endswith('/file.c-read'))
        if counts['context_reads']!=leaf(rows,'context.load')[0] or reads!=counts['context_reads']+counts['records']:
            raise RuntimeError('independent context-window replay disagrees with real host reads')
    return dict(counts), dict(field_sizes)

hit_ns=[leaf(s['spans'],'hit')[1] for s in details]
coarse_ns=[s['coarse']['read+decode_ns'] for s in coarse]
wall={arm:distribution(s['wall_ns'] for s in warm if s['arm']==arm) for arm in ['P','C','D']}
delta=lambda x,y:100*(x/y-1)
perturbation={
    'detail_vs_plain_wall_pct':delta(wall['D']['mean_s'],wall['P']['mean_s']),
    'detail_vs_coarse_wall_pct':delta(wall['D']['mean_s'],wall['C']['mean_s']),
    'detail_vs_coarse_hit_pct':delta(statistics.mean(hit_ns),statistics.mean(coarse_ns))}
def inclusive(scope, label):
    times=[]
    counts=[]
    for sample in details:
        values=[row for path,row in sample['spans'].items()
                if scope in path.split('/') and path.split('/')[-1]==label]
        if not values:
            raise RuntimeError('missing scoped span: '+scope+'/'+label)
        times.append(sum(row[1] for row in values))
        counts.append(sum(row[0] for row in values))
    return dict(calls=counts,**distribution(times))

shape,fields=cache_shape()
session_parts=[]
for s in details:
    parts=collect(s['spans'],'session',session_category)
    parts['outside session (process)']=s['wall_ns']-leaf(s['spans'],'session')[1]
    if sum(parts.values())!=s['wall_ns']:raise RuntimeError('process partition mismatch')
    session_parts.append(parts)
summary={k:v for k,v in study.items() if k!='samples'}
summary.update(
    elapsed_ns_samples=[{k:v for k,v in s.items() if k!='spans'} for s in samples],
    wall_by_arm=wall, coarse_hit=distribution(coarse_ns), detail_hit=distribution(hit_ns),
    perturbation_pct=perturbation, material_perturbation=any(abs(v)>10 for v in perturbation.values()),
    end_to_end=table(session_parts),hit_categories=subtree('hit',hit_category),
    hit_detail=subtree('hit',lambda p:p[-1]),finish_detail=subtree('finish',lambda p:p[-1]),
    output_detail=subtree('final.write',lambda p:p[-1]),assembly_detail=subtree('assembly',lambda p:p[-1]),
    prelude_detail=subtree('prelude',lambda p:p[-1]),
    inclusive_spans={scope+'/'+label:inclusive(scope,label) for scope,label in
                     [('hit','wire.symbols'),('hit','key.equal'),('prelude','prelude.ensure'),
                      ('finish','finish.admit'),('finish','finish.planGraph'),
                      ('final.write','artifact.object-v1'),('final.write','artifact.interface')]},
    cache_shape=shape,compact_key_utf8_bytes_by_field=fields)
if 'primary_compiler_sha256' in study:
    symbol_parts=[]
    for sample in details:
        parts=collect(sample['spans'],'hit',lambda p:p[-1] if 'wire.symbols' in p else 'outside symbol reader')
        del parts['outside symbol reader']
        symbol_parts.append(parts)
    summary['symbols_within_hits']=table(symbol_parts)
    for tag in ['builtin.construct','builtin.compile','builtin.solve','builtin.split']:
        summary['inclusive_spans']['prelude/'+tag]=inclusive('prelude',tag)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
# One row per measured stack, including preflight. Never fold inclusive parent
# and child times together. This TSV preserves integer nanoseconds and counts.
with (OUT/'spans.tsv').open('w') as f:
    f.write('sample\tpreflight\tstack\tcalls\tinclusive_ns\texclusive_ns\n')
    for i,s in enumerate(samples):
        for path,values in s.get('spans',{}).items():
            f.write('\t'.join(map(str,[i,int(s['preflight']),path,*values]))+'\n')
