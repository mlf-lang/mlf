#!/usr/bin/env python3
"""Verify the two complete source trees using an isolated Git index/object store.

No working-tree changes, commit, compiler, generator, test or benchmark is run.
The supplied repository must already contain the public base commit.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repository', required=True, type=Path)
args = parser.parse_args()
archive = Path(__file__).resolve().parent
manifest = json.loads((archive / 'source-manifest.json').read_text())
repo = args.repository.resolve()
base = manifest['public_base']['commit']
builtin = 'bootstrap/MLF/BuiltinPreludeData.hs'

def command(*argv, env=None, data=None):
    return subprocess.check_output(['git', '-C', str(repo), *argv], env=env, input=data)

objects = Path(command('rev-parse', '--path-format=absolute', '--git-path', 'objects').decode().strip())
assert command('rev-parse', base + '^{tree}').decode().strip() == manifest['public_base']['tree']
with tempfile.TemporaryDirectory(prefix='putvar-source-check-') as directory:
    temporary = Path(directory)
    (temporary / 'objects').mkdir()
    env = dict(os.environ, GIT_INDEX_FILE=str(temporary / 'index'),
               GIT_OBJECT_DIRECTORY=str(temporary / 'objects'),
               GIT_ALTERNATE_OBJECT_DIRECTORIES=str(objects))
    command('read-tree', base, env=env)
    results = {}
    for side, patch in [('A', '01-public-to-F25-Graph.patch'),
                        ('B', '02-F25-to-putVar-Bitstream.patch')]:
        patch_path = archive / 'source' / patch
        command('apply', '--cached', '--check', str(patch_path), env=env)
        command('apply', '--cached', str(patch_path), env=env)
        content = (archive / 'source' / side / builtin).read_bytes()
        record = next(x for x in manifest['changed_paths'] if x['path'] == builtin)['variants'][side]
        assert len(content) == record['bytes']
        assert hashlib.sha256(content).hexdigest() == record['sha256']
        blob = command('hash-object', '-w', '--stdin', env=env, data=content).decode().strip()
        assert blob == record['git_blob']
        command('update-index', '--cacheinfo', '100644,' + blob + ',' + builtin, env=env)
        tree = command('write-tree', env=env).decode().strip()
        assert tree == manifest['variants'][side]['source_tree'], (side, tree)
        files = command('ls-tree', '-r', '--name-only', tree, env=env).splitlines()
        assert len(files) == manifest['tracked_source_file_count_each']
        results[side] = {'tree': tree, 'tracked_files': len(files), 'exact_tree_match': True}
print(json.dumps({'complete': True, 'public_base': base, 'source_trees': results,
                  'working_tree_changed': False, 'compiler_or_generator_run': False}, indent=2))
