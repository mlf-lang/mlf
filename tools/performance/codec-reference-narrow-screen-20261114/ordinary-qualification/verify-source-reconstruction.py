#!/usr/bin/env python3
"""Statically reconstruct both exact source trees from public archived bytes.

Uses a temporary Git index and object store. Does not alter either input
repository's work tree/index, create commits, compile, generate or benchmark.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repository', required=True, type=Path,
                    help='Git repository containing the public base commit')
parser.add_argument('--prior-archive', type=Path,
                    help='prior putVar ordinary archive; defaults to sibling archive in this checkout')
args = parser.parse_args()
archive = Path(__file__).resolve().parent
prior = (args.prior_archive or (archive.parent.parent / 'codec-putvar-byte-screen-20261114/ordinary-qualification')).resolve()
repo = args.repository.resolve()
manifest = json.loads((archive / 'source-manifest.json').read_text())
builtin = 'bootstrap/MLF/BuiltinPreludeData.hs'
base = manifest['public_base']['commit']

def command(*argv, env=None, data=None):
    return subprocess.check_output(['git', '-C', str(repo), *argv], env=env, input=data)

def verified_bytes(path, record):
    data = path.read_bytes()
    assert len(data) == record['bytes'], str(path)
    assert hashlib.sha256(data).hexdigest() == record['sha256'], str(path)
    assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == record['git_blob'], str(path)
    return data

for record in manifest['reused_public_files']:
    verified_bytes(prior / record['prior_archive_file'], record)
for name, record in manifest['new_files'].items():
    verified_bytes(archive / name, record)
objects = Path(command('rev-parse', '--path-format=absolute', '--git-path', 'objects').decode().strip())
assert command('rev-parse', base + '^{tree}').decode().strip() == manifest['public_base']['tree']
with tempfile.TemporaryDirectory(prefix='reference-source-check-') as directory:
    temporary = Path(directory)
    (temporary / 'objects').mkdir()
    env = dict(os.environ, GIT_INDEX_FILE=str(temporary / 'index'),
               GIT_OBJECT_DIRECTORY=str(temporary / 'objects'),
               GIT_ALTERNATE_OBJECT_DIRECTORIES=str(objects))
    command('read-tree', base, env=env)

    def apply_patch(path):
        command('apply', '--cached', '--check', str(path), env=env)
        command('apply', '--cached', str(path), env=env)

    def install_builtin(path, side):
        record = next(x for x in manifest['exact_A_to_B_production_changes'] if x['path'] == builtin)['variants'][side]
        data = verified_bytes(path, record)
        blob = command('hash-object', '-w', '--stdin', env=env, data=data).decode().strip()
        assert blob == record['git_blob']
        command('update-index', '--cacheinfo', record['mode'] + ',' + blob + ',' + builtin, env=env)

    def verify_tree(side):
        tree = command('write-tree', env=env).decode().strip()
        assert tree == manifest['variants'][side]['source_tree'], (side, tree)
        count = len(command('ls-tree', '-r', '--name-only', tree, env=env).splitlines())
        assert count == manifest['tracked_source_file_count_each']
        return {'tree': tree, 'tracked_files': count, 'exact_tree_match': True}

    apply_patch(prior / 'source/01-public-to-F25-Graph.patch')
    apply_patch(prior / 'source/02-F25-to-putVar-Bitstream.patch')
    install_builtin(prior / 'source/B' / builtin, 'A')
    results = {'A': verify_tree('A')}
    apply_patch(archive / 'source/03-putVar-to-putReferences-Bitstream.patch')
    install_builtin(archive / 'source/B' / builtin, 'B')
    results['B'] = verify_tree('B')
print(json.dumps({'complete': True, 'public_base': base, 'source_trees': results,
                  'reused_public_files_verified': len(manifest['reused_public_files']),
                  'working_tree_changed': False, 'compiler_or_generator_run': False,
                  'benchmark_or_test_run': False, 'external_writes': 0}, indent=2))
