#!/usr/bin/env python3
"""Fast mismatch controls for prepared-library production evidence."""
import hashlib
import json
import subprocess
from pathlib import Path
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent

def load(name):
    path = HERE / name
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module

V = load('verify_prepared_libraries.py')
B = load('build_prepared.py')

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))

class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = Path(self.tmp.name).resolve()
        self.root = self.job / 'sources'
        self.root.mkdir()
        self.data = self.root / V.DATA
        self.data.parent.mkdir(parents=True)
        self.data.write_bytes(b'generated registry')
        pool_helper = self.root / 'tools/shared/pool_generated_strings.py'
        pool_helper.parent.mkdir(parents=True)
        pool_helper.write_bytes((HERE / 'pool_generated_strings.py').read_bytes())
        dump(self.root / 'shared-sources.json', {'primitive_abi': 'mlf-primitive-108-v5', 'frontend_semantics': 'semantics', 'builtin_interface': 'builtin', 'source_roots': ['libraries']})
        (self.root / 'library.hs').write_bytes(b'raw\r\nsource')
        pins = {}
        for path in sorted(self.root.rglob('*')):
            if path.is_file():
                name = path.relative_to(self.root).as_posix()
                pins[name] = {'path': '/original/' + name, 'snapshot': str(path), 'sha256': V.sha(path), 'bytes': path.stat().st_size, 'mode': path.stat().st_mode & 0o777}
        inventory = [{'module': 'Library', 'path': './lexical//library.hs', 'sha256': V.sha(self.root / 'library.hs')}]
        identity = {'format': 'MLF-PREPARED-LIBRARY-JOB-1', 'roots': ['Library'], 'source_root': './lexical/', 'source_package': 'main', 'mode': 'ImplicitPrelude', 'primitive_abi': 'mlf-primitive-108-v5', 'frontend_semantics': 'semantics', 'library_inventory': inventory,
                    'source_hashes': {n: p['sha256'] for n, p in pins.items() if n != V.DATA}}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        generated = self.job / 'generated/MLF/PreparedLibraryData.hs'
        generated.parent.mkdir(parents=True)
        generated.write_bytes(self.data.read_bytes())
        request = {k: v for k, v in identity.items() if k != 'source_hashes'}
        request.update(input_identity=key, library_identity='mlf:prepared-library:' + key, generated_source=str(generated), output_directory=str(self.job / 'artifacts'), library_inventory=[{**inventory[0], 'buffer_path': str(self.root / 'library.hs')}])
        product = {'generated_source': str(generated), 'generated_sha256': V.sha(generated), 'artifacts': []}
        generator = self.job / 'build/generate-prepared-libraries'
        generator.parent.mkdir()
        generator.write_bytes(b'generator')
        first = {'complete': True, 'immutable_inputs_verified_after': True, 'input_identity': key, 'tools': {}, 'generator': {'path': str(generator), 'sha256': V.sha(generator)}, 'generated_product': product, 'canonical_snapshot_registry': str(self.data), 'commands': [{'label': name, 'exit_code': 0} for name in ['build-generate-prepared-libraries', 'generate']]}
        fresh = self.job / 'regeneration/generate-prepared-libraries'
        fresh.parent.mkdir()
        fresh.write_bytes(b'fresh generator')
        backup = self.job / 'regeneration/first/data'
        backup.parent.mkdir()
        backup.write_bytes(generated.read_bytes())
        second_request = {**request, 'query_directory': str(self.job / 'regeneration/fresh-queries')}
        dump(self.job / 'regeneration/request.json', second_request)
        second = {'complete': True, 'immutable_inputs_verified_after': True, 'input_identity': key, 'commands': [{'label': name, 'exit_code': 0} for name in ['rebuild-host', 'rebuild-supervisor', 'rebuild-generator', 'regenerate']], 'first_outputs': {str(generated): {'path': str(backup), 'sha256': V.sha(generated)}}, 'comparisons': [{'path': str(generated), 'bytes_equal': True, 'first_sha256': V.sha(generated), 'second_sha256': V.sha(generated)}], 'inputs': {**{p['snapshot']: p['sha256'] for p in pins.values()}, str(generator): V.sha(generator)}, 'independent_generator': {'path': str(fresh), 'sha256': V.sha(fresh)}, 'query_directory': second_request['query_directory'], 'request_sha256': V.sha(self.job / 'regeneration/request.json')}
        product.update(format='MLF-PREPARED-LIBRARY-GENERATION-1', input_identity=key,
                       schema='mlf-prepared-libraries/1/semantics/builtin/108', source_package='main',
                       modules=['Library'], source_paths=[inventory[0]['path']], source_sha256=[inventory[0]['sha256']],
                       user_program_cache=False, native_object_reuse=False)
        for prefix in ['builtin', 'library']:
            artifact = {'identity': request['library_identity'] if prefix == 'library' else 'builtin'}
            for field, suffix in [('metadata', '.mlfci'), ('object', '.mlfco')]:
                target = self.job / 'artifacts' / (prefix + suffix)
                target.parent.mkdir(exist_ok=True)
                target.write_bytes((prefix + field).encode())
                artifact[field + '_path'] = str(target)
                artifact[field + '_sha256'] = V.sha(target)
                saved = backup.parent / target.name
                saved.write_bytes(target.read_bytes())
                second['first_outputs'][str(target)] = {'path': str(saved), 'sha256': V.sha(saved)}
                second['comparisons'].append({'path': str(target), 'bytes_equal': True, 'first_sha256': V.sha(target), 'second_sha256': V.sha(target)})
            product['artifacts'].append(artifact)
        ghc, cc = self.job / 'ghc', self.job / 'cc'
        for tool in [ghc, cc]:
            tool.write_bytes(tool.name.encode())
            first['tools'][str(tool)] = V.sha(tool)
            second['inputs'][str(tool)] = V.sha(tool)
        commands = V.producer_commands(self.root, self.job, V.read(self.root / 'shared-sources.json'), str(ghc), str(cc))
        first['commands'] = [{'label': label, 'argv': argv, 'exit_code': 0} for label, argv in commands.items()]
        second['commands'] = [{'label': label, 'argv': argv, 'exit_code': 0} for label, argv in V.regeneration_commands(self.job, commands).items()]
        for name, value in [('source-pins.json', pins), ('owned-source.json', {'format': 1, 'inventory': sorted(pins), 'input_identity': key}), ('identity-input.json', identity), ('request.json', request), ('build/receipt.json', first), ('artifacts/generation.json', product), ('regeneration/receipt.json', second)]:
            dump(self.job / name, value)

    def test_valid_and_authentication(self):
        record = V.verify(self.root)
        V.authenticate(record, self.root)
        with self.assertRaises(ValueError):
            V.authenticate(None, self.root)

    def install_pooled_fixture(self):
        pooler = load('pool_generated_strings.py')
        raw = pooler.PROFILE + pooler.MODULE + '\nlibraries = ["x", "x"];\n}\n'
        pooled, proof = pooler.pool(raw)
        first = V.read(self.job / 'build/receipt.json')
        product = first['generated_product']
        generated = Path(product['generated_source'])
        generated.write_bytes(raw.encode('utf-8'))
        self.data.write_bytes(pooled.encode('utf-8'))
        product['generated_sha256'] = V.sha(generated)
        first['canonical_string_pool'] = proof
        second = V.read(self.job / 'regeneration/receipt.json')
        second['inputs'][str(self.data)] = V.sha(self.data)
        backup = second['first_outputs'][str(generated)]
        Path(backup['path']).write_bytes(generated.read_bytes())
        backup['sha256'] = V.sha(generated)
        for row in second['comparisons']:
            if row['path'] == str(generated):
                row['first_sha256'] = row['second_sha256'] = V.sha(generated)
        for name, record in [('build/receipt.json', first), ('artifacts/generation.json', product),
                             ('regeneration/receipt.json', second)]:
            dump(self.job / name, record)
        return generated, Path(backup['path'])

    def test_pooled_registry_preserves_raw_regeneration_contract(self):
        generated, backup = self.install_pooled_fixture()
        V.verify(self.root)
        self.assertEqual(generated.read_bytes(), backup.read_bytes())
        self.assertNotEqual(generated.read_bytes(), self.data.read_bytes())
        backup.write_bytes(self.data.read_bytes())
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_pooled_registry_and_proof_mutations_rejected(self):
        self.install_pooled_fixture()
        original = self.data.read_bytes()
        self.data.write_bytes(original.replace(b'= "x"', b'= "y"'))
        with self.assertRaises(ValueError):
            V.verify(self.root)
        self.data.write_bytes(original)
        path = self.job / 'build/receipt.json'
        first = V.read(path)
        first['canonical_string_pool']['references'] += 1
        dump(path, first)
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_nongenerated_source_mutation(self):
        (self.root / 'library.hs').write_bytes(b'normalized\nsource')
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_canonical_module_mutation(self):
        self.data.write_bytes(b'other generated registry')
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_extra_source_rejected(self):
        (self.root / 'extra.hs').write_text('extra')
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_modes_preserved(self):
        (self.root / 'library.hs').chmod(0o755)
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_request_and_regeneration_mismatches(self):
        cases = [('request.json', 'roots', ['Other']), ('request.json', 'input_identity', 'bad'), ('regeneration/receipt.json', 'complete', False), ('regeneration/receipt.json', 'comparisons', []), ('identity-input.json', 'source_hashes', {})]
        for filename, field, value in cases:
            with self.subTest(filename=filename, field=field):
                path = self.job / filename
                original = path.read_bytes()
                data = json.loads(original)
                data[field] = value
                dump(path, data)
                with self.assertRaises(ValueError):
                    V.verify(self.root)
                path.write_bytes(original)

    def test_generation_identity_and_source_closure_mismatches(self):
        for field, value in [('input_identity', 'stale'), ('schema', 'wrong'), ('modules', ['Other']),
                             ('source_paths', ['/rebased/library.hs']), ('source_sha256', ['wrong'])]:
            with self.subTest(field=field):
                product_path = self.job / 'artifacts/generation.json'
                first_path = self.job / 'build/receipt.json'
                before_product, before_first = product_path.read_bytes(), first_path.read_bytes()
                product, first = json.loads(before_product), json.loads(before_first)
                product[field] = value
                first['generated_product'] = product
                dump(product_path, product)
                dump(first_path, first)
                with self.assertRaises(ValueError):
                    V.verify(self.root)
                product_path.write_bytes(before_product)
                first_path.write_bytes(before_first)

    def test_producer_source_and_roots_mismatches(self):
        path = self.job / 'build/receipt.json'
        before = path.read_bytes()
        for replacement in ['-i/shadow', '/alternative/Generate.hs']:
            first = json.loads(before)
            command = next(row for row in first['commands'] if row['label'] == 'build-generate-prepared-libraries')
            argv = command['argv']
            index = next(i for i, arg in enumerate(argv) if arg.startswith('-i/')) if replacement.startswith('-i') else next(i for i, arg in enumerate(argv) if arg.endswith('/Generate.hs'))
            argv[index] = replacement
            dump(path, first)
            with self.assertRaises(ValueError):
                V.verify(self.root)
        path.write_bytes(before)

    def test_regeneration_argv_mismatch(self):
        path = self.job / 'regeneration/receipt.json'
        receipt = V.read(path)
        receipt['commands'][-1]['argv'][-1] = '/stale/request.json'
        dump(path, receipt)
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_backup_mutation(self):
        (self.job / 'regeneration/first/data').write_bytes(b'tampered')
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_empty_registry(self):
        self.data.write_bytes((HERE.parents[1] / V.DATA).read_bytes())
        self.assertEqual(V.verify(self.root)['kind'], 'empty')

    def test_empty_marker_cannot_authorize_parser_override(self):
        canonical = (HERE.parents[1] / V.DATA).read_text()
        self.assertIn('libraries = []', canonical)
        self.assertIn('parseLibrary = Parser.parseModule', canonical)
        self.data.write_text(canonical.replace('parseLibrary = Parser.parseModule',
                                               'parseLibrary path text = Right forged'))
        with self.assertRaises(ValueError):
            V.verify(self.root)

    def test_unowned_populated_registry(self):
        (self.job / 'owned-source.json').unlink()
        with self.assertRaises(FileNotFoundError):
            V.verify(self.root)

class SnapshotTests(unittest.TestCase):
    def test_complete_inventory_preserves_bytes_and_modes(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            source, job = base / 'repo', base / 'job'
            source.mkdir()
            subprocess.run(['git', 'init', '-q', str(source)], check=True)
            (source / '.gitignore').write_text('.mlf-build/\n')
            (source / 'tracked').write_bytes(b'raw\r\nbytes')
            subprocess.run(['git', '-C', str(source), 'add', '.'], check=True)
            (source / 'untracked-tool').write_text('#!/bin/sh\n')
            (source / 'untracked-tool').chmod(0o755)
            (source / '.mlf-build').mkdir()
            (source / '.mlf-build/noise').write_text('ignored')
            names = B.inventory(source)
            self.assertEqual(names, ['.gitignore', 'tracked', 'untracked-tool'])
            job.mkdir()
            for name, value in [('source-pins.json', {}), ('identity-input.json', {}), ('request.json', {}), ('receipt.json', {})]:
                dump(job / name, value)
            B.complete_snapshot(source, job, names)
            self.assertEqual((job / 'sources/tracked').read_bytes(), b'raw\r\nbytes')
            self.assertEqual((job / 'sources/untracked-tool').stat().st_mode & 0o777, 0o755)
            self.assertEqual(set(json.loads((job / 'source-pins.json').read_text())), set(names))

if __name__ == '__main__':
    unittest.main()
