#!/usr/bin/env python3
"""Compare PR 29 closed records with open query records, independently of producers."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.setrecursionlimit(50000)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shared'))
from query_generation import cache_directory
from artifact_binary_reference import read_document, tree_document
from artifact_binary_typed import (value_node as node, text, list_values as items,
                                   unpack, logical_context, validate_type, query_payload_root)


def read(path, schema):
    return read_document(path.read_bytes(), schema)
def sha(data): return hashlib.sha256(data).hexdigest()
def name(value): return text(node(value, 31, 2)[1])
def pair(value): return node(value, 2, 2)
def data_semantics(values): return logical_context(values, 'MLF-SOURCE-CRATE-QUERY-7')

def type_semantics(value, env=None):
    env = {} if env is None else env
    tag, fields = value[1:]
    if tag == 40:
        number = node(fields[0], 30, 1)[0][1]
        assert number in env, ('open exported type', number)
        return ('bound', env[number])
    if tag == 46:
        number = node(fields[0], 30, 1)[0][1]
        return (46, type_semantics(fields[1], env), type_semantics(fields[2], {**env, number: len(env)}))
    if tag in (43, 45): return (tag, *(type_semantics(f, env) for f in fields))
    if tag == 44: return (44, text(fields[0]), tuple(type_semantics(f, env) for f in items(fields[1])))
    return value

def body_semantics(value):
    # XThen is associative. Source finalization only rebalances its tree;
    # preserve every atom, term/type binder, flag, name and literal bit.
    memo = {}
    def walk(v):
        k = id(v)
        if k in memo: return memo[k]
        if v[0] != 'node': result = v
        else:
            children = tuple(walk(f) for f in v[2])
            if v[1] == 58:
                atoms = []
                for child in children:
                    atoms.extend(child[1] if child[0] == 'then-sequence' else (child,))
                result = ('then-sequence', tuple(atoms))
            else: result = ('node', v[1], children)
        memo[k] = result
        return result
    return walk(value)

def old_raw(cache, key):
    document = read(cache / (key + '.mlfq'), 2)
    root = query_payload_root(document)
    value = document.values()[-1]
    if value[1] in (301, 303):
        fields = node(value)
        reference, header, body = text(fields[0]), fields[-2], fields[-1]
        raw = (cache / ('context-' + reference + '.mlfqc')).read_bytes()
        assert sha(raw) == reference
        declarations = items(node(read_document(raw, 1).values()[0], 244, 1)[0])
    elif value[1] in (300, 302):
        fields = node(value)
        header, body = node(fields[-1], 241, 2)
        declarations = items(node(header, 240, 8)[3])
        if body[1] == 84: _, body = node(body, 84, 2)
    else: raise AssertionError(('unknown old raw', value[1]))
    parameters = []
    while body[1] == 71:
        binder, ty, body = node(body, 71, 3)
        parameters.append((name(binder), type_semantics(ty)))
    owned = [(text(n), type_semantics(t)) for n, t in map(pair, items(node(header, 240, 8)[6]))]
    return tuple(parameters), body_semantics(body), tuple(owned), data_semantics(declarations)

def new_raw(cache, key):
    directory = cache_directory(cache) / 'results'
    raw = (directory / (key + '.mlfqr')).read_bytes()
    assert sha(raw) == key
    document = read_document(raw, 6)
    assert tree_document(document.values(), schema=6) == raw
    references, body_record = node(document.values()[0], 425, 2)
    stage, group, receipt, ps, body, owned, uses = node(body_record, 400, 7)
    assert text(stage) == 'raw'
    types, declarations = {}, []
    for k, h in map(pair, items(references)):
        kind, identity = unpack(text(k)); digest = text(h)
        encoded = (directory / (digest + '.mlfqr')).read_bytes()
        assert sha(encoded) == digest
        result = read_document(encoded, 6).values()[0]
        if kind == 'Binding': types[identity] = node(result, 420, 3)[0]
        elif kind == 'Datatype': declarations.append(result)
        else: raise AssertionError(kind)
    parameters = tuple((text(key), type_semantics(types[text(key)])) for binder, key in map(pair, items(ps)))
    bindings = tuple((name(n), type_semantics(t)) for n, t in map(pair, items(owned)))
    return parameters, body_semantics(body), bindings, data_semantics(declarations)

def interface(prefix):
    fields = list(node(read(prefix.with_suffix('.mlfci'), 3).values()[0], 242, 13))
    fields[11] = ('text', 'object-format-specific-checksum')
    return tuple(fields)

def old_final(prefix):
    document = read(prefix.with_suffix('.mlfco'), 4)
    _, _, fragments = node(document.values()[0], 243, 3)
    result = {}
    for value in items(fragments):
        header, body = node(value, 241, 2)
        metadata = node(header, 240, 8)
        declarations = items(metadata[3])
        if body[1] == 84:
            declared, body = node(body, 84, 2)
            assert data_semantics(items(declared)) == data_semantics(declarations)
        params = []
        while body[1] == 71:
            binder, ty, body = node(body, 71, 3)
            params.append((name(binder), type_semantics(ty)))
        exports = tuple((text(n), type_semantics(t)) for n,t in map(pair, items(metadata[6])))
        result[text(metadata[0])] = (tuple(params), body_semantics(body), exports, data_semantics(declarations))
    return result

def new_final(prefix):
    doc = read(prefix.with_suffix('.mlfco'), 7)
    fmt, compiler, association, bs, ds, fs = node(doc.values()[0], 430, 6)
    iface = node(read(prefix.with_suffix('.mlfci'), 3).values()[0], 242, 13)
    assert text(iface[11]) == sha(prefix.with_suffix('.mlfco').read_bytes())
    all_interfaces, seen = [], set()
    def collect(meta):
        identifier = text(meta[0])
        if identifier in seen: return
        seen.add(identifier); all_interfaces.append(meta)
        for dep in items(meta[1]):
            _, path, _ = node(dep, 3, 3)
            location = Path(text(path))
            # compare.py archives each arm after the fixed-path run.
            active_builtin = prefix.parent.parent / 'builtin'
            if not location.exists() and location.is_relative_to(active_builtin):
                location = prefix.parent / 'builtin' / location.relative_to(active_builtin)
            collect(node(read(location, 3).values()[0], 242, 13))
    collect(iface)
    types = {text(n): t for i in all_interfaces for n,t in map(pair,items(i[9]))}
    declarations = {text(node(d)[0]): d for i in all_interfaces for d in items(i[8])}
    result = {}
    for fragment in items(fs):
        group, receipt, refs, ps, body, owned, uses = node(fragment, 401, 7)
        params = tuple((name(n), type_semantics(types[name(n)])) for n in items(ps))
        exports = tuple((name(n), type_semantics(types[name(n)])) for n in items(owned))
        result[text(group)] = (params, body_semantics(body), exports,
                              data_semantics([declarations[text(r)] for r in items(refs)]))
    return result

def compare(baseline, candidate):
    baseline, candidate = baseline.resolve(), candidate.resolve()
    checked = set()
    counts = {'cold': (504,0), 'warm': (0,504), 'edit': (1,503)}
    for stage in counts:
        left, right = baseline / stage, candidate / stage
        assert interface(left) == interface(right), (stage, 'interface semantic content')
        a, b = old_final(left), new_final(right)
        assert a.keys() == b.keys(), (stage, 'final SCC inventory')
        for group in a:
            for i, label in enumerate(('parameters','body','exports','datatypes')):
                assert a[group][i] == b[group][i], (stage, group, 'final '+label)
        reports = [json.loads(p.with_suffix('.queries').read_text()) for p in (left,right)]
        for report in reports:
            assert (report['inferred_groups'],report['reused_groups']) == counts[stage]
        for a,b in zip(reports[0]['groups'],reports[1]['groups']):
            assert a['id'] == b['id'] and a['members'] == b['members']
            keys = a['query_key'],b['query_key']
            if keys in checked: continue
            x,y = old_raw(baseline/'cache',keys[0]),new_raw(candidate/'cache',keys[1])
            for i,label in enumerate(('parameters','body','exports','datatypes')):
                assert x[i] == y[i], (stage,a['members'],'raw '+label)
            checked.add(keys)
    return len(checked)

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('baseline',type=Path);p.add_argument('candidate',type=Path)
    args=p.parse_args();print('PASS',compare(args.baseline,args.candidate),'raw versions and all final interfaces/bodies/environments')
