#!/usr/bin/env python3
"""Exercise migration, mixed object formats, dependency changes and relocation."""
import argparse
import json
from pathlib import Path
import shutil
from verify import (execute, source_text, frame, sha, read, node, items, text,
                    tree_document, graph, CASES)
from compare_outputs import interface, old_final, new_final


def specification(path, identity, source, cache, builtin, dependencies=()):
    path.write_text(frame(['MLF-CRATE-1', identity, '', 'false',
        frame([frame([source.stem, str(source)])]), frame(list(map(str, dependencies))),
        str(cache), str(builtin / 'unit')]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('baseline', type=Path); p.add_argument('candidate', type=Path)
    p.add_argument('output', type=Path); a = p.parse_args()
    baseline, candidate = a.baseline.resolve(), a.candidate.resolve()
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    builtin = out / 'builtin'; cache = out / 'cache'
    source = out / 'App.hs'; spec = out / 'crate.spec'
    source.write_text(source_text('getName x = addInt x 1\ngreeting x = getName x'))
    specification(spec, 'migration', source, cache, builtin)
    execute(baseline, ['--compile-crate', spec, '-o', out / 'legacy'])
    old = {p: (sha(p.read_bytes()), p.stat().st_mtime_ns)
           for p in cache.iterdir() if p.suffix in ('.mlfq', '.mlfqc')}
    assert old and any(p.suffix == '.mlfq' for p in old)
    execute(candidate, ['--compile-crate', spec, '-o', out / 'migrated'])
    report = json.loads((out / 'migrated.queries').read_text())
    assert report['reused_groups'] == 0
    assert old == {p: (sha(p.read_bytes()), p.stat().st_mtime_ns) for p in old}
    graph(cache)
    print('PASS legacy cache is cold-migrated without changing old files', flush=True)

    fallback = out / 'fallback'; fallback.mkdir()
    fallback_source = fallback / 'App.hs'; fallback_spec = fallback / 'crate.spec'
    fallback_source.write_text(source_text(CASES['recursive-dictionary'][0]))
    specification(fallback_spec, 'fallback-parity', fallback_source, fallback / 'old-cache', builtin)
    execute(baseline, ['--compile-crate', fallback_spec, '-o', fallback / 'old'])
    specification(fallback_spec, 'fallback-parity', fallback_source, fallback / 'new-cache', builtin)
    execute(candidate, ['--compile-crate', fallback_spec, '-o', fallback / 'new'])
    assert interface(fallback / 'old') == interface(fallback / 'new')
    assert old_final(fallback / 'old') == new_final(fallback / 'new')
    graph(fallback / 'new-cache')
    print('PASS recursive dictionary final bodies, contracts and environments match PR 29', flush=True)

    lib = out / 'Lib.hs'; app = out / 'Client.hs'
    library_spec = out / 'library.spec'; app_spec = out / 'app.spec'
    specification(library_spec, 'library', lib, out / 'library-cache', builtin)
    specification(app_spec, 'client', app, out / 'client-cache', builtin, [out / 'library.mlfci'])
    lib.write_text(source_text('getName x = addInt x 1').replace('module App', 'module Lib'))
    app.write_text(source_text('import Lib\ngreeting x = getName x').replace('module App', 'module Client'))
    execute(baseline, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(candidate, ['--compile-crate', app_spec, '-o', out / 'client'])
    execute(candidate, ['--link-crate', out / 'client.mlfci'])
    print('PASS open client links with legacy dependency and builtin', flush=True)
    execute(candidate, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(candidate, ['--compile-crate', app_spec, '-o', out / 'client'])
    before = execute(candidate, ['--link-crate', out / 'client.mlfci']).stdout
    lib.write_text(source_text('getName x = addInt x 2').replace('module App', 'module Lib'))
    execute(candidate, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(candidate, ['--compile-crate', app_spec, '-o', out / 'client'])
    report = json.loads((out / 'client.queries').read_text())
    assert (report['inferred_groups'], report['reused_groups']) == (0, 1)
    assert before != execute(candidate, ['--link-crate', out / 'client.mlfci']).stdout
    lib.write_text(source_text('getName :: Bool -> Bool\ngetName x = x').replace('module App', 'module Lib'))
    execute(candidate, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(candidate, ['--link-crate', out / 'client.mlfci'], success=False)
    execute(candidate, ['--compile-crate', app_spec, '-o', out / 'client'])
    report = json.loads((out / 'client.queries').read_text())
    assert (report['inferred_groups'], report['reused_groups']) == (1, 0)
    expected = execute(candidate, ['--link-crate', out / 'client.mlfci']).stdout
    print('PASS external body reuse, changed implementation linkage, and type invalidation', flush=True)

    for directory in (cache, out / 'library-cache', out / 'client-cache',
                      fallback / 'old-cache', fallback / 'new-cache'):
        shutil.rmtree(directory)
    relocated = out.with_name(out.name + '-relocated')
    out.rename(relocated)
    for path in relocated.rglob('*.mlfci'):
        fields = list(node(read(path, 3), 242, 13))
        rewritten = []
        for dep in items(fields[1]):
            identity, location, digest = node(dep, 3, 3)
            old_path = Path(text(location))
            assert old_path.is_relative_to(out)
            rewritten.append(('node', 3, (identity,
                ('text', str(relocated / old_path.relative_to(out))), digest)))
        fields[1] = ('node', 1, tuple(rewritten))
        path.write_bytes(tree_document([('node', 242, tuple(fields))], schema=3))
    actual = execute(candidate, ['--link-crate', relocated / 'client.mlfci'],
                     env={'MLF_QUERY_SEMANTIC_AUDIT': '1'}).stdout
    assert actual == expected
    (relocated / 'results.json').write_text(json.dumps(dict(complete=True,
        baseline_sha256=sha(baseline.read_bytes()), candidate_sha256=sha(candidate.read_bytes()),
        checks=['legacy-cache', 'recursive-dictionary', 'mixed-objects', 'external-body', 'external-type', 'relocation-without-cache']), indent=2)+'\n')
    print('PASS relocated formal object closure loads with no query cache', flush=True)


if __name__ == '__main__': main()
