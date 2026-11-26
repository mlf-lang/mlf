#!/usr/bin/env python3
"""Round-trip the preparation receipt, directory layout and downloaded file modes."""
import concurrent.futures
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import driver_cache as cache


def write(path, value):
    path.write_text(json.dumps(value) + '\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DriverCacheTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.source = self.root / 'build-cache'
        self.snapshot = self.root / 'snapshot'
        self.dest = self.root / 'restored-cache'
        self.report = self.root / 'verification.json'
        self.build_report = self.root / 'build-report.json'
        self.source.mkdir()
        builds = []
        drivers = {}
        for name in ('RuntimeDriver', 'LLVMDriver'):
            stages = {}
            products = {'llvm': (f'source {name} LLVM', 'program.ll'), 'object': ('LLVM object', 'program.o'),
                        'linked': ('test driver native link', 'program'), 'runtime': ('test driver C object', 'object.o')}
            if name == 'RuntimeDriver':
                products['trace'] = ('test driver C object', 'object.o')
            for stage, (kind, filename) in products.items():
                label = 'shared-runtime' if stage == 'runtime' else name + '-' + stage
                key = hashlib.sha256(label.encode()).hexdigest()
                directory = self.source / key
                directory.mkdir(exist_ok=True)
                product = directory / filename
                product.write_bytes(b'#!/bin/sh\necho driver-ok\n' if stage == 'linked' else label.encode())
                if stage == 'linked':
                    product.chmod(0o755)
                files = {filename: hashlib.sha256(product.read_bytes()).hexdigest()}
                stamp_hash = write(directory / 'artifact.json', {'key': key, 'inputs': {'label': label}, 'files': files})
                (directory / 'unrelated-file').write_text('exclude me')
                row = {'key': key, 'kind': kind, 'cached': any(b['key'] == key for b in builds)}
                builds.append(row)
                stages[stage] = dict(row, directory=str(directory), files=files, artifact_sha256=stamp_hash)
            drivers[name] = {'frontend': 'source', 'artifacts': stages, 'sha256': stages['linked']['files']['program'],
                             'llvm_sha256': stages['llvm']['files']['program.ll']}
        build = {'implementation': 'MLF', 'complete': True, 'format': 1,
                 'cache_directory': str(self.source), 'builds': builds}
        self.prepared = {'complete': True, 'group': 'backend-prepare', 'scope': 'preparation', 'drivers': drivers,
                         'driver_build': {'path': str(self.build_report), 'sha256': write(self.build_report, build)}}
        write(self.report, self.prepared)
        self.linked = drivers['RuntimeDriver']['artifacts']['linked']['key']

    def cli(self, *args):
        result = subprocess.run([sys.executable, '-B', cache.__file__, *args], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_round_trip_shared_stage_and_executable_after_download(self):
        self.assertEqual(self.cli('export', '--report', self.report, '--output', self.snapshot), {'exported': 8})
        (self.snapshot / self.linked / 'program').chmod(0o644)
        result = self.cli('import', '--snapshot', self.snapshot, '--cache', self.dest)
        self.assertEqual(result['misses'], [])
        self.assertEqual(set(result['imported']), {p.name for p in self.source.iterdir()})
        for key in result['imported']:
            before, after = self.source / key, self.dest / key
            self.assertEqual({p.name for p in after.iterdir()}, {p.name for p in before.iterdir()} - {'unrelated-file'})
            for p in after.iterdir():
                self.assertEqual(p.read_bytes(), (before / p.name).read_bytes())
        if os.name == 'posix':
            self.assertEqual(subprocess.check_output([self.dest / self.linked / 'program']), b'driver-ok\n')

    def test_concurrent_and_repeated_imports_preserve_existing_entries(self):
        cache.export(self.report, self.snapshot)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda _: cache.restore(self.snapshot, self.dest), range(2)))
        self.assertEqual(sum(len(r['imported']) for r in results), 8)
        self.assertFalse(any(r['misses'] for r in results))
        binary = self.dest / self.linked / 'program'
        binary.write_text('existing entry for the builder to validate')
        again = cache.restore(self.snapshot, self.dest)
        self.assertEqual(len(again['existing']), 8)
        self.assertEqual(binary.read_text(), 'existing entry for the builder to validate')

    def test_damaged_entries_and_unavailable_snapshot_fall_back(self):
        self.assertTrue(cache.restore(self.snapshot, self.dest)['misses'])
        cache.export(self.report, self.snapshot)
        (self.snapshot / self.linked / 'program').write_bytes(b'corrupt')
        stamp_key = self.prepared['drivers']['LLVMDriver']['artifacts']['llvm']['key']
        (self.snapshot / stamp_key / 'artifact.json').write_text('{}')
        result = cache.restore(self.snapshot, self.dest)
        self.assertEqual(len(result['imported']), 6)
        self.assertEqual(len(result['misses']), 2)
        self.assertFalse((self.dest / self.linked).exists())
        self.assertFalse((self.dest / stamp_key).exists())

    def test_untrusted_names_and_links_do_not_escape_cache(self):
        cache.export(self.report, self.snapshot)
        manifest_path = self.snapshot / 'manifest.json'
        manifest = cache.read(manifest_path)
        key = self.linked
        witness = self.root / 'outside'
        witness.write_bytes(b'untouched')
        stamp = self.snapshot / key / 'artifact.json'
        saved = cache.read(stamp)
        saved['files'] = {'../../outside': hashlib.sha256(witness.read_bytes()).hexdigest()}
        manifest['artifacts'][key] = write(stamp, saved)
        manifest['artifacts']['../outside'] = 'a' * 64
        write(manifest_path, manifest)
        result = cache.restore(self.snapshot, self.dest)
        self.assertEqual(len(result['misses']), 2)
        self.assertFalse((self.dest / key).exists())
        self.assertEqual(witness.read_bytes(), b'untouched')

    @unittest.skipUnless(os.name == 'posix', 'symlink test needs unprivileged symlinks')
    def test_symlinked_file_and_directory_are_misses(self):
        cache.export(self.report, self.snapshot)
        before = self.source / self.linked
        after = self.snapshot / self.linked
        (after / 'program').unlink()
        (after / 'program').symlink_to(before / 'program')
        other = self.prepared['drivers']['LLVMDriver']['artifacts']['llvm']['key']
        (self.snapshot / other).rename(self.root / 'external-key')
        (self.snapshot / other).symlink_to(self.root / 'external-key', target_is_directory=True)
        result = cache.restore(self.snapshot, self.dest)
        self.assertEqual(len(result['misses']), 2)
        self.assertFalse((self.dest / self.linked).exists())
        self.assertFalse((self.dest / other).exists())

    def test_only_complete_preparation_can_export(self):
        for fields in ({'complete': False}, {'scope': 'full'}, {'group': 'backend-native'}):
            with self.subTest(fields=fields):
                write(self.report, {**self.prepared, **fields})
                with self.assertRaisesRegex(ValueError, 'completed backend-prepare preparation'):
                    cache.export(self.report, self.snapshot)
                self.assertFalse(self.snapshot.exists())
        build = cache.read(self.build_report)
        build['complete'] = False
        incomplete_hash = write(self.build_report, build)
        for expected_hash, message in ((self.prepared['driver_build']['sha256'], 'digest mismatch'),
                                       (incomplete_hash, 'completed manager driver build')):
            value = {**self.prepared, 'driver_build': {'path': str(self.build_report), 'sha256': expected_hash}}
            write(self.report, value)
            with self.assertRaisesRegex(ValueError, message):
                cache.export(self.report, self.snapshot)
            self.assertFalse(self.snapshot.exists())

    def test_mismatched_artifact_identity_or_bytes_cannot_publish(self):
        for field, change in [('directory', str(self.source)), ('key', '../escape'),
                              ('artifact_sha256', 'f' * 64), ('cached', True), ('files', {'unexpected': '0'*64})]:
            with self.subTest(field=field):
                value = copy.deepcopy(self.prepared)
                value['drivers']['RuntimeDriver']['artifacts']['linked'][field] = change
                write(self.report, value)
                with self.assertRaises(ValueError):
                    cache.export(self.report, self.snapshot)
                self.assertFalse(self.snapshot.exists())
        write(self.report, self.prepared)
        (self.source / self.linked / 'program').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'artifact file digest mismatch'):
            cache.export(self.report, self.snapshot)
        self.assertFalse(self.snapshot.exists())


if __name__ == '__main__':
    unittest.main()
