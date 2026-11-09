#!/usr/bin/env python3
"""Independently reconstruct key bytes and compare complete raw binary fragments."""
import hashlib
import json
import sys
from pathlib import Path

if not __debug__:
    raise RuntimeError('study verification requires a normal Python invocation')

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'shared'))
import run_context_controls as wire
reference, typed, _ = wire.binary_helpers()
out = Path(sys.argv[1])
summary = json.loads((out/'results.json').read_text())
compiler = summary['binary_sha256']
arms = [out/(str(i)+'-'+name) for i,name in enumerate(summary['order'])]
old = arms[0]
new = next((arm for arm in arms if arm.name.endswith('-New')), None)
builtin = typed.logical_context([], 'MLF-SOURCE-CRATE-QUERY-6')
assert len(builtin.encode()) == 119056
assert hashlib.sha256(builtin.encode()).hexdigest() == 'f2439576cdad3064e339927cdc541b9a6ee61b1f261955566185e4a8c9fd4d69'

def read(arm, key, contexts, fmt):
    cache = arm/'cache'
    graph = reference.read_document((cache/(key+'.mlfq')).read_bytes(),2)
    ref, ck, header, body = wire.graph_node(graph, graph.roots[0], 301, 4)
    digest = wire.graph_text(graph, ref)
    if digest not in contexts:
        blob = (cache/('context-'+digest+'.mlfqc')).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == digest
        context = typed.inspect_artifact(blob,1)
        ds = typed.list_values(typed.value_node(context.values()[0],244,1)[0])
        contexts[digest] = blob,typed.logical_context(ds,fmt)
    blob, context = contexts[digest]
    fields = [wire.graph_text(graph,i) for i in wire.graph_node(graph,ck,1)]
    assert len(fields)==8 and fields[0]==fmt and fields[2]==compiler
    full = wire.pack(fields[:5]+[context]+fields[5:]).encode()
    assert hashlib.sha256(full).hexdigest()==key
    return len(full), fields[1:], blob, context, graph, header, body

# Direct file equality, including inactive records retained after the edit.
# The per-stage snapshots in the runner additionally cover the pre-edit state.
for arm in arms:
    peer = new if 'New' in arm.name else old
    names = sorted(f.name for f in (peer/'cache').iterdir())
    assert names == sorted(f.name for f in (arm/'cache').iterdir())
    for f in names:
        assert (arm/'cache'/f).read_bytes() == (peer/'cache'/f).read_bytes()
    for stage in ['cold','warm','edit']:
        assert (arm/(stage+'.queries')).read_bytes() == (peer/(stage+'.queries')).read_bytes()
        for ext in ['.mlfci','.mlfco']:
            assert (arm/(stage+ext)).read_bytes() == (old/(stage+ext)).read_bytes()

rows = {}
for stage in ['cold','edit']:
    groups = lambda arm: json.loads((arm/(stage+'.queries')).read_text())['groups']
    cache_old,cache_new = {},{}
    size_old,size_new = 0,0
    items = groups(old)
    other = groups(new) if new else items
    assert len(items)==len(other)==504
    for a,b in zip(items,other):
        assert a['id']==b['id'] and a['members']==b['members']
        x = read(old,a['query_key'],cache_old,'MLF-SOURCE-CRATE-QUERY-6')
        size_old += x[0]
        if new:
            y = read(new,b['query_key'],cache_new,'MLF-SOURCE-CRATE-QUERY-7')
            size_new += y[0]
            assert x[1:3]==y[1:3] and x[3]==builtin+y[3]
            for i,label in [(5,'raw header'),(6,'raw body')]:
                wire.require_graph_equal(x[4],x[i],y[4],y[i],label)
    rows[stage] = dict(groups=len(items), v6_key_bytes=size_old,
                       v7_key_bytes=size_new if new else None, matched_raw_fragments=len(items) if new else None)
print(json.dumps(rows,indent=2))
