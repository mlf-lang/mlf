"""Pure semantic-stage parsers; no IO, targets, workload synthesis or guessed counts."""
import json,re

def need(ok,message):
    if not ok:raise ValueError(message)

def json_object(raw):
    def unique(pairs):
        out={}
        for key,value in pairs:
            need(key not in out,'duplicate JSON key');out[key]=value
        return out
    need(type(raw) is bytes and len(raw)<=268435456,'bounded exact JSON bytes')
    return json.loads(raw.decode('utf8'),object_pairs_hook=unique)

def fresh_queries(raw,crate):
    q=json_object(raw)
    need(type(q) is dict and set(q)=={'format','crate','semantic_fingerprint','inferred_groups','reused_groups','groups'},'complete main query JSON grammar')
    need(type(q['format']) is int and q['format']==1 and q['crate']==crate,'format/crate')
    need(type(q['inferred_groups']) is int and type(q['reused_groups']) is int and q['reused_groups']==0,'integer fresh counts, zero reuse')
    groups=q['groups'];need(type(groups) is list and 0<len(groups)==q['inferred_groups'],'complete actual fresh group list')
    need(type(q['semantic_fingerprint']) is str and q['semantic_fingerprint'],'semantic fingerprint required')
    ids=[]
    for g in groups:
        need(type(g) is dict and set(g)=={'id','members','cached','semantic_fingerprint','query_key'},'complete ordered group fields')
        need(type(g['id']) is str and g['id'] and g['cached'] is False,'nonempty fresh group identity')
        need(type(g['members']) is list and g['members'] and all(type(m) is str and m for m in g['members']),'actual ordered member strings')
        need(type(g['semantic_fingerprint']) is str and g['semantic_fingerprint'],'group fingerprint')
        need(type(g['query_key']) is str and re.fullmatch('[0-9a-f]{64}',g['query_key']),'actual query content key')
        ids.append(g['id'])
    need(len(set(ids))==len(ids),'duplicate query group ID')
    return q

def ghc_compiling(stdout,stderr,expected):
    need(type(stdout) is bytes and type(stderr) is bytes and type(expected) is dict and expected,'complete GHC logs and declared input modules')
    events=[]
    pattern=r'^\s*\[\s*([0-9]+)\s+of\s+([0-9]+)\]\s+Compiling\s+([A-Z][A-Za-z0-9_\x27.]*)\s+\(\s*([^,\n]+),[^\n]*\)\s*$'
    for line in (stdout.decode('utf8')+'\n'+stderr.decode('utf8')).splitlines():
        if re.search(r'\bCompiling\s+',line):
            m=re.fullmatch(pattern,line);need(m is not None,'unparsed GHC Compiling event')
            index,total,name,path=m.groups();path=path.strip()
            need(path.startswith('/') and '/..' not in path,'exact absolute source event path')
            events.append({'index':int(index),'total':int(total),'module':name,'source':path})
    need(len(events)==len(expected) and len({e['module'] for e in events})==len(events),'exact fresh home compilation count; no hidden/repeated dependencies')
    need({e['module']:e['source'] for e in events}==expected,'exact declared source/module mapping')
    need({e['index'] for e in events}==set(range(1,len(expected)+1)) and all(e['total']==len(expected) for e in events),'complete single GHC compilation group')
    return events

def resolved_commands(plan,setup_work,setup_worker):
    token='<INDEPENDENTLY_ACCEPTED_SETUP_WORK>'
    need(type(setup_work) is str and setup_work.startswith('/') and '<' not in setup_work,'actual accepted setup path required')
    def value(v):
        if type(v) is str:
            if v.startswith('<accepted_setup.runtime_after.'):
                need(v.endswith('>'),'runtime placeholder grammar')
                parts=v[1:-1].split('.')[1:];x=setup_worker
                for p in parts:x=x[p]
                need(type(x) is str and x.startswith('/'),'actual serialized runtime path required');return x
            v=v.replace(token,setup_work)
            need('<' not in v and 'PENDING_' not in v,'unresolved command placeholder');return v
        if type(v) is list:return [value(x) for x in v]
        if type(v) is dict:return {k:value(x) for k,x in v.items()}
        return v
    rows=[]
    # Only execution-relevant fields are resolved; descriptive unknown-oracle labels remain unknown.
    keys={'argv_template','crate_spec_fields_template','report_sink','expected_home_modules'}
    for row in plan['rows']:
        out=dict(row)
        for key in keys:
            if key in out:out[key]=value(out[key])
        rows.append(out)
    need(len(rows)==91 and [r['ordinal'] for r in rows]==list(range(1,92)),'fixed 91 ledger')
    need(len({r['label'] for r in rows})==91,'unique command labels')
    return rows
