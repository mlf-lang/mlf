#!/usr/bin/env python3
"""Black-box query-graph acceptance, with an independent wire/closure reader."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/shared'))
from artifact_binary_reference import read_document, tree_document
from artifact_binary_typed import value_node as node, text, list_values as items, unpack


def sha(data): return hashlib.sha256(data).hexdigest()
def frame(values): return ''.join(f'{len(v)}:{v}' for v in values)
def spec(source, cache, builtin, identity='query-acceptance'):
    return frame(['MLF-CRATE-1', identity, '', 'false',
                  frame([frame(['App', str(source)])]), '', str(cache), str(builtin / 'unit')])
def read(path, schema): return read_document(path.read_bytes(), schema).values()[0]
def pair(value): return node(value, 2, 2)

def graph(cache):
    directory = cache / 'query-graph-v1'
    current = text(read(directory / 'CURRENT', 6))
    raw = (directory / 'generations' / (current + '.mlfqg')).read_bytes()
    assert sha(raw) == current
    fmt, config, entries = node(read_document(raw, 6).values()[0], 411, 3)
    assert text(fmt) == 'MLF-CRATE-QUERY-GRAPH-1'
    result = {}
    for value in items(entries):
        k, h, edges, location = node(value, 410, 4)
        k, h = text(k), text(h)
        assert k not in result
        dependencies = [(text(a), text(b)) for a, b in map(pair, items(edges))]
        loc = node(location)
        payload = text(loc[0]) if loc else None
        result[k] = {'sha': h, 'reads': dependencies, 'payload': payload}
        if payload:
            raw = (directory / 'results' / (payload + '.mlfqr')).read_bytes()
            assert sha(raw) == payload == h
            assert tree_document(read_document(raw, 6).values(), schema=6) == raw
    for entry in result.values():
        for key, expected in entry['reads']:
            assert key in result and result[key]['sha'] == expected
    visiting, done = set(), set()
    def visit(key):
        if key in done: return
        assert key not in visiting, 'query cycle'
        visiting.add(key)
        for child, _ in result[key]['reads']: visit(child)
        visiting.remove(key); done.add(key)
    for key in result: visit(key)
    return current, result


def execute(binary, argv, *, env=None, success=True):
    variables = dict(os.environ, GHCRTS='', GHC_ENVIRONMENT='-', LANG='C.UTF-8', LC_ALL='C.UTF-8', TZ='UTC')
    variables.update(env or {})
    result = subprocess.run([str(binary), *map(str, argv)], env=variables,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    if success:
        assert result.returncode == 0 and not result.stderr, (argv, result.returncode, result.stderr.decode(errors='replace'))
    else:
        assert result.returncode != 0, ('expected failure', argv, result.stdout)
    return result

HEADER = '-- mlf:syntax shared-haskell-v1\n{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, OverloadedStrings #-}\nmodule App where {\nimport MLF.Primitive;\n'
def source_text(body):
    return HEADER + ';\n'.join(line for line in body.strip().splitlines() if line.strip()) + '\n}\n'
CASES = {
    'body': ['getName x = addInt x 1\ngreeting x = getName x\nuntouched x = x\n',
             'getName x = addInt x 2\ngreeting x = getName x\nuntouched x = x\n'],
    'type': ['getName :: Int -> Int\ngetName x = x\ngreeting x = getName x\nuntouched x = x\n',
             'getName :: Bool -> Bool\ngetName x = x\ngreeting x = getName x\nuntouched x = x\n'],
    'protection': ['getName :: forall a. a -> a\ngetName x = x\ngreeting x = getName x\nuntouched x = x\n',
                   'getName x = x\ngreeting x = getName x\nuntouched x = x\n'],
    'datatype': ['data User = User Int\nvalue = User 3\ngetName (User x) = x\ngreeting = getName value\nuntouched x = x\n',
                 'data User = User Bool\nvalue = User True\ngetName (User x) = x\ngreeting = getName value\nuntouched x = x\n'],
    'constructor-owner': ['data A = Mark\ndata B = Keep\nvalue = Mark\nuntouched x = x\n',
                          'data A = Keep\ndata B = Mark\nvalue = Mark\nuntouched x = x\n'],
    'scc': ['f x = g x\ng x = f x\nuntouched x = x\n',
            'f x = g x\ng x = x\nuntouched x = x\n',
            'f x = g x\ng x = f x\nuntouched x = x\n'],
    'scope': ['class Tag a where { tag :: a -> Int }\nf = tag True\nuntouched x = x\n',
              'class Tag a where { tag :: a -> Int }\ninstance Tag Bool where { tag x = 7 }\nf = tag True\nuntouched x = x\n',
              'class Tag a where { tag :: a -> Int }\nf = tag True\nuntouched x = x\n'],
    'scope-order': ['class Tag a where { tag :: a -> Int }\ninstance Tag Int where { tag x = x }\ninstance Tag Bool where { tag x = 7 }\nf = tag True\n',
                    'class Tag a where { tag :: a -> Int }\ninstance Tag Bool where { tag x = 7 }\ninstance Tag Int where { tag x = x }\nf = tag True\n'],
    'recursive-dictionary': ['class Tag a where { tag :: a -> Int }\ninstance Tag Int where { tag x = getName x }\ngetName :: Int -> Int\ngetName x = tag x\nuntouched x = x\n',
                         'class Tag a where { tag :: a -> Int }\ninstance Tag Int where { tag x = addInt (getName x) 1 }\ngetName :: Int -> Int\ngetName x = tag x\nuntouched x = x\n'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--case', choices=list(CASES), help='run a single named control')
    parser.add_argument('--resume', action='store_true', help='retain completed cases for the same binary and rerun incomplete cases in fresh directories')
    args = parser.parse_args()
    binary, output = args.binary.resolve(strict=True), args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.resume)
    builtin = output / 'builtin'
    record = json.loads((output / 'results.json').read_text()) if args.resume else {
        'binary_sha256': sha(binary.read_bytes()), 'cases': [], 'complete': False}
    assert not record['complete'] and record['binary_sha256'] == sha(binary.read_bytes())
    if args.resume:
        record.setdefault('resumptions', []).append(dict(script_sha256=sha(Path(__file__).read_bytes()),
            completed_cases=list(record.get('recovery', []))))
    def save(): (output / 'results.json').write_text(json.dumps(record, indent=2) + '\n')
    save()
    for name, versions in CASES.items():
        if args.smoke and name != 'body': continue
        if args.case and name != args.case: continue
        if args.resume and name in record.get('recovery', []): continue
        folder = output / name
        if folder.exists():
            assert args.resume
            previous = output / ('failed-' + name + '-' + str(len(list(output.glob('failed-' + name + '-*')))))
            folder.rename(previous)
            (previous / 'attempt-results.json').write_text(json.dumps(record,indent=2)+'\n')
            record['cases'] = [row for row in record['cases'] if row['case'] != name]
        folder.mkdir()
        source = folder / 'App.hs'; cache = folder / 'cache'; specfile = folder / 'crate.spec'
        specfile.write_text(spec(source, cache, builtin))
        def compile(label, *, options=(), env=None, success=True):
            prefix = folder / label
            result = execute(binary, [*options, '--compile-crate', specfile, '-o', prefix], env=env, success=success)
            prefix.with_suffix('.stdout').write_bytes(result.stdout)
            prefix.with_suffix('.stderr').write_bytes(result.stderr)
            return prefix
        def outputs(prefix): return tuple(prefix.with_suffix(ext).read_bytes() for ext in ('.mlfci', '.mlfco'))
        for version, body in enumerate(versions):
            source.write_text(source_text(body))
            inc = compile(f'{version}-incremental')
            report = json.loads(inc.with_suffix('.queries').read_text())
            current, nodes = graph(cache)
            if name == 'recursive-dictionary':
                idx = cache / 'query-graph-v1/generations' / (current + '.mlfqg')
                configuration = text(node(read(idx, 6), 411, 3)[1])
                assert unpack(configuration)[-1] == 'source', 'pure dictionary recursion should retain the source plan'
            before = {str(p.relative_to(cache)): (sha(p.read_bytes()), p.stat().st_mtime_ns)
                      for p in cache.rglob('*') if p.is_file() and p.name != '.lock'}
            warm = compile(f'{version}-warm')
            warm_report = json.loads(warm.with_suffix('.queries').read_text())
            assert warm_report['inferred_groups'] == 0
            assert warm_report['reused_groups'] == len(warm_report['groups'])
            assert outputs(inc) == outputs(warm), (name, version, 'warm output')
            after = {str(p.relative_to(cache)): (sha(p.read_bytes()), p.stat().st_mtime_ns)
                     for p in cache.rglob('*') if p.is_file() and p.name != '.lock'}
            assert before == after, (name, version, 'unchanged generation was rewritten')
            strict = compile(f'{version}-ich', options=['-Zincremental-verify-ich'])
            audit = compile(f'{version}-audit', env={'MLF_QUERY_SEMANTIC_AUDIT': '1'})
            assert outputs(inc) == outputs(strict) == outputs(audit)
            assert json.loads(audit.with_suffix('.queries').read_text())['inferred_groups'] == 0
            cache.rename(folder / f'{version}-retained-cache')
            clean = compile(f'{version}-clean')
            assert outputs(inc) == outputs(clean), (name, version, 'clean output')
            clean_report = json.loads(clean.with_suffix('.queries').read_text())
            assert clean_report['reused_groups'] == 0
            for left, right in zip(report['groups'], clean_report['groups']):
                assert left['query_key'] == right['query_key'], (name, version, 'raw result differs')
            # No query cache can be consulted by a formal-object load/link.
            cache.rename(folder / f'{version}-clean-cache')
            linked = execute(binary, ['--link-crate', inc.with_suffix('.mlfci')])
            assert linked.stdout, 'empty linked program'
            audited_link = execute(binary, ['--link-crate', inc.with_suffix('.mlfci')], env={'MLF_QUERY_SEMANTIC_AUDIT': '1'})
            assert linked.stdout == audited_link.stdout
            shutil.rmtree(folder / f'{version}-clean-cache')
            (folder / f'{version}-retained-cache').rename(cache)
            row = dict(case=name, version=version, inferred=report['inferred_groups'], reused=report['reused_groups'],
                       nodes=len(nodes), kinds=sorted({unpack(k)[0] for k in nodes}), generation=current,
                       artifact_sha256=[sha(x) for x in outputs(inc)])
            record['cases'].append(row); save(); print('PASS', name, version, row['inferred'], row['reused'], flush=True)
            if name == 'body' and version == 1:
                assert report['inferred_groups'] == 1, 'body edit should reuse same-contract callers'
        # A corrupt/missing result is repaired; final output remains exact.
        current, nodes = graph(cache)
        payload = next(n['payload'] for k, n in nodes.items() if unpack(k)[0] == 'InferScc')
        damaged = cache / 'query-graph-v1/results' / (payload + '.mlfqr')
        damaged.write_bytes(b'corrupt checked record')
        repaired = compile('repaired')
        assert json.loads(repaired.with_suffix('.queries').read_text())['inferred_groups'] == 1
        assert outputs(repaired) == outputs(inc)
        graph(cache)
        damaged.unlink()
        missing = compile('missing')
        assert json.loads(missing.with_suffix('.queries').read_text())['inferred_groups'] == 1
        assert outputs(missing) == outputs(inc)
        graph(cache)
        # Failed source/output/publication cannot advance the generation pointer.
        pointer = cache / 'query-graph-v1/CURRENT'; old = pointer.read_bytes()
        source.write_text(source_text(versions[-1] + '\ninvalid = missingDefinition\n'))
        compile('source-failure', success=False)
        assert pointer.read_bytes() == old
        # Enough distinct new results to cross the bounded rename batch. A
        # partly moved publication must leave the old graph fully readable.
        added = ''.join(f'\nnewValue{i} x = addInt x {i}\n' for i in range(96)) if name == 'body' else '\nnewValue x = x\n'
        source.write_text(source_text(versions[-1] + added))
        (folder / 'output-failure.mlfco').mkdir()
        compile('output-failure', success=False)
        assert 'directory' in (folder / 'output-failure.stderr').read_text(), 'failure did not reach formal output'
        assert pointer.read_bytes() == old
        staged_before_move = None
        for point in ('before-results', 'after-result-staging', 'after-result-batch', 'before-index', 'before-current'):
            compile('failed-' + point, env={'MLF_QUERY_FAILPOINT': point}, success=False)
            assert 'query publication interrupted' in (folder / ('failed-' + point + '.stderr')).read_text(), 'failure did not reach publication'
            assert pointer.read_bytes() == old
            graph(cache)
            staged = set((cache / 'query-graph-v1/staging').glob('*.mlfqr'))
            if point == 'after-result-staging':
                assert staged, 'failpoint did not reach staged results'
                staged_before_move = staged
            if point == 'after-result-batch' and name == 'body':
                assert staged < staged_before_move and staged, 'expected a partially moved multi-batch publication'
                record['partial_batch_preserves_previous_generation'] = True
        source.write_text(source_text(versions[-1]))
        resumed = compile('resumed')
        assert json.loads(resumed.with_suffix('.queries').read_text())['inferred_groups'] == 0
        assert outputs(resumed) == outputs(inc)
        objectfile = resumed.with_suffix('.mlfco'); saved = objectfile.read_bytes()
        objectfile.write_bytes(saved[:-1] + bytes([saved[-1] ^ 1]))
        execute(binary, ['--link-crate', resumed.with_suffix('.mlfci')], success=False)
        objectfile.write_bytes(saved)
        # Broken, checksum-correct references reject the whole generation.
        valid_generation, valid_nodes = graph(cache)
        index = cache / 'query-graph-v1/generations' / (valid_generation + '.mlfqg')
        fmt, config, values = node(read(index, 6), 411, 3)
        damaged_entries = []
        changed = False
        for value in items(values):
            k, h, reads, location = node(value, 410, 4)
            if not changed and items(reads):
                edges = list(items(reads))
                _, expected = pair(edges[0])
                edges[0] = ('node', 2, (('text', frame(['Binding','absent-definition'])), expected))
                value = ('node', 410, (k,h,('node',1,tuple(edges)),location))
                changed = True
            damaged_entries.append(value)
        assert changed
        bad_bytes = tree_document([('node',411,(fmt,config,('node',1,tuple(damaged_entries))))], schema=6)
        bad_hash = sha(bad_bytes)
        (index.parent / (bad_hash + '.mlfqg')).write_bytes(bad_bytes)
        pointer.write_bytes(tree_document([('text',bad_hash)],schema=6))
        rebuilt = compile('dangling-generation')
        assert json.loads(rebuilt.with_suffix('.queries').read_text())['reused_groups'] == 0
        assert outputs(rebuilt) == outputs(inc)
        graph(cache)
        if name == 'body':
            # Deliberately forge a *trusted* receipt with a valid byte SHA and
            # graph closure. This is an audit-policy test, not corruption: the
            # normal reader/ICH must not silently become a second typechecker.
            generation, nodes = graph(cache)
            index = cache / 'query-graph-v1/generations' / (generation + '.mlfqg')
            fmt, config, values = node(read(index, 6), 411, 3)
            def replace_literal(value, changed):
                if value[0] != 'node': return value
                if value[1] == 77 and not changed[0]:
                    changed[0] = True
                    return ('node',79,(('node',7,()),))
                return ('node',value[1],tuple(replace_literal(v,changed) for v in value[2]))
            for key, entry in nodes.items():
                if unpack(key)[0] != 'InferScc': continue
                path = cache / 'query-graph-v1/results' / (entry['payload']+'.mlfqr')
                changed = [False]
                forged = replace_literal(read(path, 6), changed)
                if changed[0]: break
            assert changed[0]
            raw = tree_document([forged],schema=6); forged_hash = sha(raw)
            (path.parent/(forged_hash+'.mlfqr')).write_bytes(raw)
            new_entries = []
            for value in items(values):
                k,h,edges,location = node(value,410,4)
                new_edges = tuple(('node',2,(dep,('text',forged_hash) if text(dep)==key else digest))
                                  for dep,digest in map(pair,items(edges)))
                if text(k)==key:
                    h=('text',forged_hash); location=('node',5,(('text',forged_hash),))
                new_entries.append(('node',410,(k,h,('node',1,new_edges),location)))
            encoded = tree_document([('node',411,(fmt,config,('node',1,tuple(new_entries))))],schema=6)
            forged_generation = sha(encoded)
            (index.parent/(forged_generation+'.mlfqg')).write_bytes(encoded)
            pointer.write_bytes(tree_document([('text',forged_generation)],schema=6))
            graph(cache)
            trusted = compile('trusted-receipt', options=['-Zincremental-verify-ich'])
            assert json.loads(trusted.with_suffix('.queries').read_text())['inferred_groups'] == 0
            execute(binary, ['--link-crate',trusted.with_suffix('.mlfci')], success=False)
            audited = compile('semantic-audit-repair', env={'MLF_QUERY_SEMANTIC_AUDIT':'1'})
            assert json.loads(audited.with_suffix('.queries').read_text())['inferred_groups'] == 1
            assert outputs(audited) == outputs(inc)
            record['receipt_ich_semantic_audit_separated'] = True
        # Shared small results are reconstructed from current checked metadata;
        # stable evidence can be recomputed without invalidating raw inference.
        _, nodes = graph(cache)
        damaged_kinds = []
        for kind in ('Binding', 'Datatype', 'Evidence'):
            matches = [n['payload'] for k,n in nodes.items() if unpack(k)[0] == kind and n['payload']]
            if not matches: continue
            (cache / 'query-graph-v1/results' / (matches[0] + '.mlfqr')).unlink()
            repaired = compile('repair-shared-' + kind)
            assert outputs(repaired) == outputs(inc)
            assert json.loads(repaired.with_suffix('.queries').read_text())['inferred_groups'] == 0
            graph(cache); damaged_kinds.append(kind)
        record.setdefault('shared_repair', {})[name] = damaged_kinds
        if name == 'body':
            cache.rename(folder / 'before-concurrent-writers')
            with ThreadPoolExecutor(max_workers=2) as pool:
                writes = list(pool.map(compile, ['writer-a', 'writer-b']))
            reports = [json.loads(p.with_suffix('.queries').read_text()) for p in writes]
            assert sorted((r['inferred_groups'],r['reused_groups']) for r in reports) == [(0,3),(3,0)]
            assert all(outputs(p) == outputs(inc) for p in writes)
            graph(cache); record['serialized_writers'] = True
        record.setdefault('recovery', []).append(name); save()
    selected = [name for name in CASES if (not args.smoke or name=='body') and (not args.case or name==args.case)]
    assert set(selected).issubset(record['recovery'])
    record['selected_cases'] = selected
    record['complete'] = True; save()
    print('PASS query graph acceptance', flush=True)

if __name__ == '__main__': main()
