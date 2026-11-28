#!/usr/bin/env python3
"""Exercise external dependency invalidation and relocation without caches."""
import argparse
import json
from pathlib import Path
import shutil
from verify import execute, source_text, frame, sha, read, node, items, text, tree_document, require


def specification(path, identity, source, cache, builtin, dependencies=()):
    path.write_text(frame(['MLF-CRATE-1', identity, '', 'false',
        frame([frame([source.stem, str(source)])]), frame(list(map(str, dependencies))),
        str(cache), str(builtin / 'unit')]))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('compiler', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    compiler = args.compiler.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    builtin = out / 'builtin'

    lib = out / 'Lib.hs'; app = out / 'Client.hs'
    library_spec = out / 'library.spec'; app_spec = out / 'app.spec'
    specification(library_spec, 'library', lib, out / 'library-cache', builtin)
    specification(app_spec, 'client', app, out / 'client-cache', builtin, [out / 'library.mlfci'])
    lib.write_text(source_text('getName x = addInt x 1').replace('module App', 'module Lib'))
    app.write_text(source_text('import Lib\ngreeting x = getName x').replace('module App', 'module Client'))
    execute(compiler, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(compiler, ['--compile-crate', app_spec, '-o', out / 'client'])
    before = execute(compiler, ['--link-crate', out / 'client.mlfci']).stdout
    lib.write_text(source_text('getName x = addInt x 2').replace('module App', 'module Lib'))
    execute(compiler, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(compiler, ['--compile-crate', app_spec, '-o', out / 'client'])
    report = json.loads((out / 'client.queries').read_text())
    require((report['inferred_groups'], report['reused_groups']) == (0, 1),
            'implementation edit should reuse the unchanged client contract')
    after = execute(compiler, ['--link-crate', out / 'client.mlfci']).stdout
    require(before != after, 'linking must use the new external implementation')
    lib.write_text(source_text('getName :: Bool -> Bool\ngetName x = x').replace('module App', 'module Lib'))
    execute(compiler, ['--compile-crate', library_spec, '-o', out / 'library'])
    execute(compiler, ['--link-crate', out / 'client.mlfci'], success=False)
    execute(compiler, ['--compile-crate', app_spec, '-o', out / 'client'])
    report = json.loads((out / 'client.queries').read_text())
    require((report['inferred_groups'], report['reused_groups']) == (1, 0),
            'a changed external type must invalidate the client group')
    expected = execute(compiler, ['--link-crate', out / 'client.mlfci']).stdout
    print('PASS external body reuse, changed implementation linkage, and type invalidation', flush=True)

    for directory in (out / 'library-cache', out / 'client-cache'):
        shutil.rmtree(directory)
    relocated = out.with_name(out.name + '-relocated')
    out.rename(relocated)
    for path in relocated.rglob('*.mlfci'):
        fields = list(node(read(path, 3), 242, 13))
        rewritten = []
        for dep in items(fields[1]):
            identity, location, digest = node(dep, 3, 3)
            old_path = Path(text(location))
            require(old_path.is_relative_to(out), 'fixture dependency must be inside the relocated output')
            rewritten.append(('node', 3, (identity,
                ('text', str(relocated / old_path.relative_to(out))), digest)))
        fields[1] = ('node', 1, tuple(rewritten))
        path.write_bytes(tree_document([('node', 242, tuple(fields))], schema=3))
    actual = execute(compiler, ['--link-crate', relocated / 'client.mlfci'],
                     env={'MLF_QUERY_SEMANTIC_AUDIT': '1'}).stdout
    require(actual == expected, 'relocated closure must link the same program')
    result = dict(complete=True, compiler_sha256=sha(compiler.read_bytes()),
                  checks=['external-body', 'external-type', 'relocation-without-cache'])
    (relocated / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS relocated formal object closure loads with no query cache', flush=True)


if __name__ == '__main__': main()
