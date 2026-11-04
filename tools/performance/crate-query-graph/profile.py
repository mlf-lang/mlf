#!/usr/bin/env python3
"""Separate instrumented Foundation run; never mix these times into ABBA."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
from verify import graph, unpack

helper = Path(__file__).resolve().parents[1] / 'foundation-query/compare.py'
loader = importlib.util.spec_from_file_location('foundation_protocol', helper)
protocol = importlib.util.module_from_spec(loader); loader.loader.exec_module(protocol)


def inventory(cache):
    return {str(p.relative_to(cache)): (p.stat().st_size, protocol.digest(p), p.stat().st_mtime_ns)
            for p in cache.rglob('*') if p.is_file() and p.name != '.lock'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('binary', type=Path); p.add_argument('foundation', type=Path)
    p.add_argument('builtin', type=Path, help='verified candidate builtin directory from ABBA')
    p.add_argument('output', type=Path); a = p.parse_args()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    binary = a.binary.resolve(strict=True)
    source = out / 'input'; shutil.copytree(a.foundation.resolve() / 'Bootstrap', source / 'Bootstrap')
    modules = [('Bootstrap.' + f.stem, f) for f in sorted((source/'Bootstrap').glob('*.hs'))]
    assert len(modules) == 14
    shutil.copytree(a.builtin, out / 'builtin')
    cache = out / 'cache'; spec = out / 'crate.spec'
    spec.write_text(protocol.crate_spec(modules,'mlf-foundation/0.3.0/library',cache,out/'builtin/unit'))
    version = source / 'Bootstrap/Version.hs'; original = version.read_bytes()
    assert original.count(b'version = "0.3.0"') == 1
    os.environ['MLF_QUERY_PROFILE'] = '1'
    os.environ.pop('MLF_QUERY_SEMANTIC_AUDIT', None); os.environ.pop('MLF_QUERY_FAILPOINT', None)
    result = dict(complete=False, binary_sha256=protocol.digest(binary),
                  sources={n:protocol.digest(f) for n,f in modules}, samples=[])
    def save(): (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    save(); before = {}
    for stage, counts in [('cold',(504,0)),('warm',(0,504)),('edit',(1,503))]:
        if stage == 'edit': version.write_bytes(original.replace(b'version = "0.3.0"',b'version = "0.3.1"'))
        prefix = out / stage
        resources = protocol.compile_crate(binary,spec,prefix)
        report = json.loads(prefix.with_suffix('.queries').read_text())
        assert (report['inferred_groups'],report['reused_groups']) == counts
        after = inventory(cache)
        if stage == 'warm': assert before == after, 'warm cache writes'
        current, nodes = graph(cache)
        payloads = {n['payload'] for n in nodes.values() if n['payload']}
        raw = {n['payload'] for k,n in nodes.items() if unpack(k)[0] == 'InferScc'}
        size = lambda h: (cache/'query-graph-v1/results'/(h+'.mlfqr')).stat().st_size
        reachable = sum(map(size,payloads)) + (cache/'query-graph-v1/CURRENT').stat().st_size + \
            (cache/'query-graph-v1/generations'/(current+'.mlfqg')).stat().st_size
        result['samples'].append(dict(stage=stage, counts=counts, **resources,
            phases=json.loads(prefix.with_suffix('.query-profile').read_text()),
            reachable_cache_bytes=reachable, retained_cache_bytes=sum(v[0] for v in after.values()),
            written_cache_bytes=sum(v[0] for k,v in after.items() if before.get(k)!=v),
            active_raw_encoded_bytes=sum(map(size,raw)),
            interface_bytes=prefix.with_suffix('.mlfci').stat().st_size,
            object_bytes=prefix.with_suffix('.mlfco').stat().st_size,
            graph_nodes=len(nodes), retained_generations=len(list((cache/'query-graph-v1/generations').glob('*')))))
        before=after; save()
    version.write_bytes(original); result['complete']=True; save()
    print(json.dumps(result['samples'],indent=2))


if __name__ == '__main__': main()
