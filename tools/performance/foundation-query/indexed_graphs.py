#!/usr/bin/env python3
"""Measure three installed compilers on the same Foundation query graph."""
import argparse
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys

from compare import compile_crate, crate_spec, digest

# Independent wire reader used by the compiler-shapes acceptance checks.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'compiler-shapes'))
import query_cache as wire

EXPECTED = {'cold': (504, 0), 'empty': (504, 0), 'warm': (0, 504), 'edit': (1, 503)}
ARMS = ('29', '43', 'optimized')


def graph_identity(cache, compiler):
    directory = cache / 'query-graph-v1'
    address = wire.text(wire.document((directory / 'CURRENT').read_bytes()))
    generation = directory / 'generations' / (address + '.mlfqg')
    assert digest(generation) == address
    version, configuration, rows = wire.node(wire.document(generation.read_bytes()), 411, 3)
    config = wire.unpack(wire.text(configuration))
    assert config[1] == compiler
    payloads = []
    for path in sorted((directory / 'results').glob('*.mlfqr')):
        assert digest(path) == path.stem
        payloads.append(path.stem)
    logical = [wire.text(version), config[:1] + config[2:], rows, payloads]
    return wire.digest(json.dumps(logical, separators=(',', ':')).encode())


def schedule(warm_rounds, cold_rounds, profile_rounds):
    # Each block of three puts every compiler in every position. Six also
    # balance which side of each pair goes first.
    rotations = [ARMS[i:] + ARMS[:i] for i in range(3)]
    orders = rotations + [r[::-1] for r in rotations]
    for mode, states, rounds in [('plain', ['warm', 'edit'], warm_rounds),
                                 ('plain', ['cold', 'empty'], cold_rounds),
                                 ('profile', ['warm', 'edit'], profile_rounds)]:
        for r in range(rounds):
            for state in states[::1 if r % 2 == 0 else -1]:
                order = orders[(r + (3 if state == states[1] else 0)) % 6]
                for arm in order:
                    yield dict(mode=mode, state=state, round=r + 1, arm=arm)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('before', 'original', 'optimized', 'foundation', 'output'):
        parser.add_argument(arg, type=Path)
    parser.add_argument('--warm-rounds', type=int, default=12)
    parser.add_argument('--cold-rounds', type=int, default=3)
    parser.add_argument('--profile-rounds', type=int, default=3)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    binaries = dict(zip(ARMS, (p.resolve(strict=True) for p in
                               (args.before, args.original, args.optimized)), strict=True))
    sources = output / 'input' / 'Bootstrap'
    shutil.copytree(args.foundation.resolve() / 'Bootstrap', sources)
    modules = [('Bootstrap.' + p.stem, p) for p in sorted(sources.glob('*.hs'))]
    assert len(modules) == 14
    version = sources / 'Version.hs'
    original = version.read_bytes()
    assert original.count(b'version = "0.3.0"') == 1
    edited = original.replace(b'version = "0.3.0"', b'version = "0.3.1"')
    cache, builtin = output / 'cache', output / 'builtin'
    spec = output / 'foundation.spec'
    spec.write_text(crate_spec(modules, 'mlf-foundation/0.3.0/library', cache, builtin / 'unit'))
    hashes = {arm: digest(path) for arm, path in binaries.items()}
    trials = list(schedule(args.warm_rounds, args.cold_rounds, args.profile_rounds))
    plan = dict(binaries={k: {'path': str(p), 'sha256': hashes[k], 'host':
                subprocess.check_output([p, '--implementation-identity'], text=True).strip()}
                for k,p in binaries.items()}, source={p.name: digest(p) for _,p in modules},
                platform=platform.platform(), trials=trials)
    (output / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    record = dict(complete=False, seeds={}, samples=[])
    references, graph_references, graphs = {}, {}, {}
    os.environ.pop('MLF_QUERY_FAILPOINT', None)
    os.environ.pop('MLF_QUERY_SEMANTIC_AUDIT', None)
    os.environ.pop('MLF_QUERY_PROFILE', None)

    def measure(arm, state, prefix, profile=False):
        if profile:
            os.environ['MLF_QUERY_PROFILE'] = '1'
        try:
            stats = compile_crate(binaries[arm], spec, prefix)
        finally:
            os.environ.pop('MLF_QUERY_PROFILE', None)
        report = json.loads(prefix.with_suffix('.queries').read_bytes())
        counts = (report['inferred_groups'], report['reused_groups'])
        assert counts == EXPECTED[state], (prefix, counts)
        stats['counts'] = counts
        products = {ext: digest(prefix.with_suffix(ext)) for ext in ('.mlfci', '.mlfco', '.queries')}
        family = '29' if arm == '29' else '43'
        key = (family, 'cold' if state == 'empty' else state)
        assert references.setdefault(key, products) == products, (prefix, products)
        stats['products'] = products
        if (arm, state) not in graphs:
            graph = graph_identity(cache, hashes[arm])
            assert graph_references.setdefault(key, graph) == graph, prefix
            graphs[arm, state] = graph
        stats['logical_graph'] = graphs[arm, state]
        if profile:
            stats['profile'] = json.loads(prefix.with_suffix('.query-profile').read_bytes())
        return stats

    def save():
        temporary = output / 'results.tmp'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'results.json')

    try:
        for arm in ARMS:
            seed = output / ('seed-' + arm)
            seed.mkdir()
            record['seeds'][arm] = measure(arm, 'cold', seed / 'unit')
            cache.rename(seed / 'cache')
            builtin.rename(seed / 'builtin')
        save()
        for i, trial in enumerate(trials):
            arm, state = trial['arm'], trial['state']
            seed = output / ('seed-' + arm)
            if state in ('warm', 'edit'):
                shutil.copytree(seed / 'cache', cache)
            if state != 'empty':
                shutil.copytree(seed / 'builtin', builtin)
            version.write_bytes(edited if state == 'edit' else original)
            leg = output / 'legs' / str(i)
            leg.mkdir(parents=True)
            stats = measure(arm, state, leg / 'unit', trial['mode'] == 'profile')
            record['samples'].append({**trial, **stats})
            save()
            shutil.rmtree(cache)
            shutil.rmtree(builtin)
        record['complete'] = True
        save()
    finally:
        version.write_bytes(original)


if __name__ == '__main__':
    main()
