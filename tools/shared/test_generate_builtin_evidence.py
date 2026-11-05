#!/usr/bin/env python3
"""Small synthetic controls; no GHC, native build, or generator is executed.

Build inventories and logs live in memory. Filesystem tests use tiny inputs and
diagnostic outputs (about 40 KiB allocated), never a large literal copy.
Run with unittest under both ordinary Python and python -O.
"""
import contextlib
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

# Source loading also avoids creating pyc in a constrained source workspace.
HELPER = Path(__file__).with_name('generate_builtin_evidence.py').resolve()
g = types.ModuleType('generate_builtin_evidence')
g.__file__ = str(HELPER)
exec(compile(HELPER.read_bytes(), str(HELPER), 'exec'), g.__dict__)
OLD, NEW = '1' * 64, '2' * 64
IDENTITY = 'builtin-source-v1:' + NEW


def digest(data):
    return hashlib.sha256(data).hexdigest()


def literal(identity):
    return ('-- mlf:syntax shared-haskell-v1\nmodule MLF.BuiltinPreludeData (builtin) where\n'
            'builtin = "builtin-source-v1:' + identity + '"\n').encode()


class Pins:
    """Tiny file-hash adapter; production uses the existing canonical verifier."""
    FORMAT = 'builtin-prelude-verification-v1'
    HELPERS = ('tools/shared/builtin_prelude_identity.py', 'tools/shared/verify_builtin_prelude.py')

    def __init__(self, files=None):
        self.files = files

    def bytes(self, path):
        return self.files[str(path)] if self.files is not None else Path(path).read_bytes()

    def sha(self, path):
        return digest(self.bytes(path))

    def identified(self, path):
        path = Path(path)
        return {'path': str(path), 'sha256': self.sha(path)}

    def verify_file(self, item, expected=None):
        g.require(isinstance(item, dict) and isinstance(item.get('path'), str), 'missing file identity')
        path = Path(item['path'])
        g.require(path.is_absolute() and '..' not in path.parts and
                  (expected is None or path == Path(expected)), 'different file path')
        g.require(self.sha(path) == item.get('sha256'), 'input changed: ' + str(path))
        return path

    def verify_inputs(self, inputs):
        for path, sha in inputs.items():
            self.verify_file({'path': path, 'sha256': sha})

    def commands(self, snapshot):
        return [('check-candidate', [snapshot['compiler']['path'], '--verify-builtin-prelude', snapshot['source_identity']]),
                ('fresh-literal', [snapshot['generator']['path'], snapshot['source_identity']])]


class MemoryBuild:
    """Exercise production authentication without allocating source/log files."""
    def __init__(self):
        self.root = Path('/__builtin_fixture__/source')
        self.build = self.root / '.mlf-build/test'
        self.path = self.build / 'receipt.json'
        self.files = {}
        self.v = Pins(self.files)
        def add(path, data=None):
            self.files[str(path)] = data if data is not None else str(path).encode()
            return self.v.identified(path)
        self.add = add
        self.manifest = {'source_syntax': 'shared-haskell-v1', 'primitive_abi': 'abi',
            'frontend_semantics': 'frontend', 'builtin_interface': 'builtin',
            'source_roots': ['bootstrap', 'host/ghc'],
            'modules': [{'module': 'MLF.Entry.BuiltinPrelude', 'path': 'bootstrap/MLF/Entry/BuiltinPrelude.hs'},
                        {'module': 'MLF.BuiltinPreludeData', 'path': 'bootstrap/MLF/BuiltinPreludeData.hs'}],
            'executables': [{'name': name, 'wrapper': 'host/ghc/app/' + name + '/Main.hs'}
                            for name in ['emlf', 'builtin-prelude']]}
        config = ['cabal.project', 'mlf-shared.cabal', 'shared-sources.json', 'mlf-package.json']
        self.v.configuration_paths = lambda root: [root / p for p in config]
        host = [*g.HOST_MODULES.values(), 'host/ghc/cbits/host.c',
                'runtime/mlf_process_supervisor.c', 'runtime/host.h',
                *[row['wrapper'] for row in self.manifest['executables']]]
        for p in config + host + list(self.v.HELPERS) + [row['path'] for row in self.manifest['modules']]:
            add(self.root / p)
        add(self.root / 'shared-sources.json', json.dumps(self.manifest).encode())
        self.receipt = r = {'format': 1, 'complete': False, 'typecheck_only': False, 'producer_host': 'GHC',
            'implementation_language': 'MLF/shared-haskell-v1', 'builtin_verification': None, 'optimization': '0',
            'build_driver': add(self.root / 'tools/shared/build.py'),
            'orchestrator': {**add(Path(sys.executable)), 'version': sys.version},
            'cabal_manifest': self.v.identified(self.root / 'mlf-shared.cabal'),
            'manifest_sha256': self.v.sha(self.root / 'shared-sources.json'),
            'shared_inputs': {row['module']: {**row, **self.v.identified(self.root / row['path'])} for row in self.manifest['modules']},
            'resolved_modules': {row['module']: self.v.identified(self.root / row['path']) for row in self.manifest['modules']},
            'resolved_host_modules': {name: self.v.identified(self.root / p) for name, p in g.HOST_MODULES.items()},
            'configuration_inputs': {p: self.v.identified(self.root / p) for p in config},
            'host_inputs': {p: self.v.identified(self.root / p) for p in host},
            'builtin_verification_helpers': {p: self.v.identified(self.root / p) for p in self.v.HELPERS},
            'prepared_verification_helper': add(self.root / 'tools/shared/verify_prepared_libraries.py'),
            'prepared_verification': {'kind': 'empty'},
            'ghc': {**add(Path('/__builtin_fixture__/launcher/ghc')), 'version': '9.14.1'},
            'cc': add(Path('/__builtin_fixture__/tools/cc')),
            'ghc_settings': add(Path('/__builtin_fixture__/ghc/lib/settings')),
            'outputs': {row['name']: add(self.build / 'bin' / row['name']) for row in self.manifest['executables']},
            'commands': [], 'inferred_shared_interfaces': {'synthetic': 'interfaces'}}
        for key in ('source_syntax', 'primitive_abi', 'builtin_interface', 'frontend_semantics'):
            r[key] = self.manifest[key]
        actual = add(Path('/__builtin_fixture__/ghc/bin/ghc-9.14.1'))
        r['toolchain'] = {'actual_ghc': actual, 'files': {p['path']: p['sha256'] for p in [actual, r['ghc'], r['cc']]}}
        dep = add(Path('/__builtin_fixture__/packages/base.hi'))
        self.dependencies = {'packages': ['base'], 'files': {dep['path']: dep['sha256']}}
        r['installed_dependencies'] = copy.deepcopy(self.dependencies)
        for filename, key in [('packages.txt', 'package_database_sha256'), ('ghc-info.txt', 'ghc_info_sha256')]:
            r[key] = add(self.build / filename)['sha256']
        self.builder = types.SimpleNamespace(ROOT=self.root, GHC_VERSION='9.14.1',
            DEMAND_FLAGS=['-fpedantic-bottoms', '-fno-state-hack'], PACKAGES=['base'],
            EXHAUSTIVENESS_FLAGS=['-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns'],
            LINK_FLAGS=['-rtsopts=ignoreAll'], load_manifest=lambda: self.manifest,
            audit_inferred_interfaces=lambda log, inputs: {'synthetic': 'interfaces'},
            package_inputs=lambda dump, names: self.dependencies)
        r['flags'] = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
            '-no-user-package-db', '-hide-all-packages', '-O0', *self.builder.DEMAND_FLAGS, '-i',
            *['-i' + str(self.root / p) for p in self.manifest['source_roots']], '-odir', str(self.build / 'objects'),
            '-hidir', str(self.build / 'objects'), '-package', 'base']
        compiled = {**r['resolved_modules'], **r['resolved_host_modules']}
        for label, argv in g.build_commands(self.builder, self.root, self.build, self.manifest, r):
            data = b'ok\n'
            if label == 'shared-compile':
                data = ''.join('Compiling ' + name + ' ( ' + row['path'] + ', object )\n'
                               for name, row in compiled.items()).encode()
            if label == 'implementation-identity':
                data = b'MLF/shared-haskell-v1 GHC\n'
            log = self.build / (label + '.log')
            r['commands'].append({'argv': argv, 'cwd': str(self.root), 'exit_code': 0,
                                  'log': str(log), 'log_sha256': add(log, data)['sha256']})
        self.snapshot = {'source_root': str(self.root), 'source_identity': IDENTITY,
                         'compiler': r['outputs']['emlf'], 'generator': r['outputs']['builtin-prelude'],
                         'inputs': {str(self.root / p): self.v.sha(self.root / p) for p in self.v.HELPERS}}
        self.failed_path = self.build / 'builtin-verification/receipt.json'
        stdout = add(self.failed_path.parent / 'check-candidate.stdout', b'')
        stderr = add(self.failed_path.parent / 'check-candidate.stderr', g.STALE)
        self.failed = {'format': self.v.FORMAT, 'complete': False, 'immutable_inputs_verified_after': True,
            'source_files_rewritten': False, 'toolchain_qualification': False, **self.snapshot,
            'error': 'ValueError: builtin verification command failed: check-candidate',
            'commands': [{'label': 'check-candidate', 'argv': self.v.commands(self.snapshot)[0][1],
                          'cwd': str(self.root), 'exit_code': 1, 'timeout_seconds': 1800,
                          'input_pins_verified_before': True, 'input_pins_verified_after': True,
                          'stdout': stdout, 'stderr': stderr}]}

    @contextlib.contextmanager
    def mounted(self):
        self.add(self.path, json.dumps(self.receipt).encode())
        self.add(self.failed_path, json.dumps(self.failed).encode())
        def read(path, *args, **kwargs):
            return self.files[str(path)].decode()
        def glob(path, pattern):
            return sorted(Path(p) for p in self.files if Path(p).parent == path and Path(p).match(pattern))
        def rglob(path, pattern):
            return sorted(Path(p) for p in self.files if Path(p).is_relative_to(path) and Path(p).match(pattern))
        def loaded(path):
            if path.name == 'build.py':
                return self.builder
            return types.SimpleNamespace(authenticate=lambda record, root: None)
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.object(Path, 'read_text', read))
            stack.enter_context(mock.patch.object(Path, 'read_bytes', lambda p: self.files[str(p)]))
            stack.enter_context(mock.patch.object(Path, 'stat', lambda p, **kw: types.SimpleNamespace(st_size=len(self.files[str(p)]))))
            stack.enter_context(mock.patch.object(Path, 'resolve', lambda p, **kw: p))
            stack.enter_context(mock.patch.object(Path, 'exists', lambda p: str(p) in self.files))
            stack.enter_context(mock.patch.object(Path, 'rglob', rglob))
            stack.enter_context(mock.patch.object(Path, 'glob', glob))
            stack.enter_context(mock.patch.object(g, 'load_source', side_effect=loaded))
            yield

    def authenticate(self):
        with self.mounted():
            return g.authenticate_build(self.v, self.root, self.path, self.snapshot)

    def authenticate_failure(self):
        with self.mounted():
            return g.authenticate_failure(self.v, self.snapshot, self.failed_path)


class BuildAuthenticationTests(unittest.TestCase):
    def test_accepts_incomplete_runtime_without_unsaved_identity(self):
        f = MemoryBuild()
        ref, opt, pins = f.authenticate()
        self.assertEqual(opt, '0')
        self.assertEqual(ref['path'], str(f.path))
        self.assertIn(str(f.build / 'implementation-identity.log'), pins)
        self.assertNotIn('implementation_identity', f.receipt)
        self.assertFalse(f.receipt['complete'])

    def test_rejects_receipt_contract_changes(self):
        changes = [('complete', True), ('typecheck_only', True), ('producer_host', 'other'),
                   ('builtin_verification', {}), ('optimization', '1'), ('implementation_identity', 'wrong'),
                   ('frontend_semantics', 'changed'), ('manifest_sha256', '0' * 64),
                   ('prepared_verification', {'kind': 'prepared'})]
        for key, value in changes:
            with self.subTest(key=key):
                f = MemoryBuild()
                f.receipt[key] = value
                with self.assertRaises(ValueError):
                    f.authenticate()

    def test_rejects_all_relevant_pin_mutations(self):
        for kind in ['build_driver', 'compiler', 'generator', 'host', 'shared', 'helper',
                     'settings', 'toolchain', 'dependency', 'compile_log', 'identity_log', 'configuration']:
            with self.subTest(kind=kind):
                f = MemoryBuild()
                r = f.receipt
                paths = {'build_driver': r['build_driver']['path'], 'compiler': r['outputs']['emlf']['path'],
                    'generator': r['outputs']['builtin-prelude']['path'], 'host': next(iter(r['host_inputs'].values()))['path'],
                    'shared': next(iter(r['shared_inputs'].values()))['path'], 'helper': next(iter(r['builtin_verification_helpers'].values()))['path'],
                    'settings': r['ghc_settings']['path'], 'toolchain': r['toolchain']['actual_ghc']['path'],
                    'dependency': next(iter(r['installed_dependencies']['files'])),
                    'compile_log': str(f.build / 'shared-compile.log'), 'identity_log': str(f.build / 'implementation-identity.log'),
                    'configuration': str(f.root / 'cabal.project')}
                f.files[paths[kind]] += b'changed'
                with self.assertRaises(ValueError):
                    f.authenticate()

    def test_rejects_command_and_inventory_changes(self):
        for mode in ['argv', 'cwd', 'exit', 'log_path', 'missing_command', 'extra_output', 'source_path',
                     'missing_resolved', 'missing_dependency', 'compile_omission', 'wrong_banner', 'producer_path', 'ghc_path']:
            with self.subTest(mode=mode):
                f = MemoryBuild()
                r = f.receipt
                if mode == 'argv':
                    r['commands'][0]['argv'][0] = '/untrusted/ghc'
                elif mode == 'cwd':
                    r['commands'][0]['cwd'] = '/untrusted'
                elif mode == 'exit':
                    r['commands'][0]['exit_code'] = 1
                elif mode == 'log_path':
                    r['commands'][0]['log'] = str(f.build / '../shared-compile.log')
                elif mode == 'missing_command':
                    r['commands'].pop()
                elif mode == 'extra_output':
                    r['outputs']['other'] = r['outputs']['emlf']
                elif mode == 'source_path':
                    next(iter(r['shared_inputs'].values()))['path'] = '/outside/source.hs'
                elif mode == 'missing_resolved':
                    r['resolved_modules'].pop(next(iter(r['resolved_modules'])))
                elif mode == 'missing_dependency':
                    r['installed_dependencies']['files'].clear()
                elif mode == 'ghc_path':
                    r['toolchain']['actual_ghc'] = f.add(Path('/elsewhere/ghc-9.14.1'))
                elif mode in ['compile_omission', 'wrong_banner']:
                    row = r['commands'][0 if mode == 'compile_omission' else -1]
                    f.files[row['log']] = b'not provenance\n'
                    row['log_sha256'] = f.v.sha(row['log'])
                else:
                    f.snapshot['generator'] = r['outputs']['emlf']
                with self.assertRaises(ValueError):
                    f.authenticate()


class FailureAuthenticationTests(unittest.TestCase):
    def test_accepts_exact_original_failure(self):
        f = MemoryBuild()
        record = f.authenticate_failure()
        self.assertEqual(record['stderr']['sha256'], digest(g.STALE))

    def test_rejects_other_failures_and_mutations(self):
        for mode in ['complete', 'input_error', 'input_check', 'source_identity', 'argv', 'cwd', 'exit',
                     'second_command', 'before', 'after', 'timeout', 'error', 'stderr_pin', 'stderr_text', 'stdout_text', 'source_pin']:
            with self.subTest(mode=mode):
                f = MemoryBuild()
                r, row = f.failed, f.failed['commands'][0]
                if mode == 'complete': r['complete'] = True
                elif mode == 'input_error': r['input_error'] = 'mutation'
                elif mode == 'input_check': r['immutable_inputs_verified_after'] = False
                elif mode == 'source_identity': r['source_identity'] = 'old'
                elif mode == 'argv': row['argv'][0] = '/untrusted/producer'
                elif mode == 'cwd': row['cwd'] = '/untrusted'
                elif mode == 'exit': row['exit_code'] = 2
                elif mode == 'second_command': r['commands'].append(copy.deepcopy(row))
                elif mode == 'before': row['input_pins_verified_before'] = False
                elif mode == 'after': row['input_pins_verified_after'] = False
                elif mode == 'timeout': row['timeout_seconds'] = float('inf')
                elif mode == 'error': r['error'] = 'some other failure'
                elif mode == 'source_pin': f.files[next(iter(f.snapshot['inputs']))] += b'changed'
                else:
                    key = 'stdout' if mode == 'stdout_text' else 'stderr'
                    f.files[row[key]['path']] = b'wrong output\n'
                    if mode != 'stderr_pin': row[key]['sha256'] = f.v.sha(row[key]['path'])
                with self.assertRaises(ValueError):
                    f.authenticate_failure()


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.build = self.root / '.mlf-build/shared-ghc'
        self.build.mkdir(parents=True)
        self.guard = self.root / '.mlf-build/builtin-generation-guard'
        self.guard.mkdir()
        self.source = self.root / 'literal.hs'
        self.source.write_bytes(literal(OLD))
        self.original = self.build / 'receipt.json'
        self.original.write_bytes(b'{"complete":false}\n')
        self.v = Pins()
        self.evidence = {'snapshot': {'canonical': self.v.identified(self.source), 'source_identity': IDENTITY},
            'original_build_receipt': self.v.identified(self.original), 'original_failure': {'error': 'original error'},
            'optimization': '0', 'inputs': {str(p): self.v.sha(p) for p in [self.source, self.original]}}
        self.output = self.guard / 'results'

    def runner(self, stdout=None, stderr=b'', code=0, mutate=None, error=None):
        def run(v, argv, root, output, timeout, entry):
            self.assertEqual(argv, [str(self.build / 'bin/builtin-prelude'), IDENTITY])
            self.assertEqual(root, self.root)
            self.assertEqual(timeout, 600)
            entry['exit_code'] = code
            for label, data in [('stdout', literal(NEW) if stdout is None else stdout), ('stderr', stderr)]:
                p = output / ('fresh-literal.' + label)
                p.write_bytes(data)
                entry[label] = {**v.identified(p), 'bytes': len(data)}
            if mutate:
                mutate()
            if error:
                raise error
        return run

    def generate(self, runner=None, authentication=None):
        with mock.patch.object(g, 'authenticate', side_effect=authentication or (lambda *args: (self.v, self.evidence))), \
                mock.patch.object(g, 'run_generator', side_effect=runner or self.runner()):
            return g.generate(self.root, self.original, self.output)

    def test_actual_bytes_required_for_identity_delta(self):
        original_bytes = self.original.read_bytes()
        path = self.generate()
        receipt = json.loads(path.read_text())
        self.assertTrue(receipt['complete'])
        self.assertTrue(receipt['generation_only'])
        self.assertFalse(receipt['toolchain_qualification'])
        self.assertFalse(receipt['source_files_rewritten'])
        self.assertFalse(receipt['original_build_complete'])
        self.assertFalse(receipt['candidate_verified'])
        self.assertFalse(receipt['producer_build_complete'])
        self.assertTrue(receipt['comparison']['identity_only'])
        self.assertEqual(receipt['comparison']['new_identity'], NEW)
        self.assertEqual(self.original.read_bytes(), original_bytes)
        self.assertEqual(self.source.read_bytes(), literal(OLD))
        self.assertEqual((self.output / 'fresh-literal.stdout').read_bytes(), literal(NEW))

    def test_other_actual_difference_is_not_identity_only(self):
        self.generate(self.runner(stdout=literal(NEW) + b'-- changed\n'))
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertTrue(receipt['complete'])
        self.assertFalse(receipt['comparison']['identity_only'])
        self.assertNotIn('offset', receipt['comparison'])

    def test_failed_runs_preserve_partial_evidence(self):
        cases = [('nonzero', self.runner(code=1)), ('stderr', self.runner(stderr=b'error\n')),
                 ('empty', self.runner(stdout=b'')), ('invalid', self.runner(stdout=b'not a literal')),
                 ('timeout', self.runner(stdout=b'partial', code=-9, error=subprocess.TimeoutExpired(['generator'], 600)))]
        for name, runner in cases:
            with self.subTest(name=name):
                with self.assertRaises((ValueError, subprocess.TimeoutExpired)):
                    self.generate(runner)
                receipt = json.loads((self.output / 'receipt.json').read_text())
                self.assertFalse(receipt['complete'])
                self.assertIn('error', receipt)
                self.assertEqual(receipt['original_failure']['error'], 'original error')
                self.assertTrue((self.output / 'fresh-literal.stdout').is_file())
                self.assertEqual(self.original.read_bytes(), b'{"complete":false}\n')
                # Keep peak allocation constant across subtests.
                for p in self.output.iterdir(): p.unlink()
                self.output.rmdir()

    def test_input_mutation_fails_final_immutable_check(self):
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.generate(self.runner(mutate=lambda: self.source.write_bytes(b'changed')))
        receipt = json.loads((self.output / 'receipt.json').read_text())
        self.assertFalse(receipt['complete'])
        self.assertFalse(receipt['immutable_inputs_verified_after'])
        self.assertIn('input_error', receipt)

    def test_inventory_change_fails(self):
        after = copy.deepcopy(self.evidence)
        after['optimization'] = '2'
        with self.assertRaisesRegex(ValueError, 'inventory changed'):
            self.generate(authentication=mock.Mock(side_effect=[(self.v, self.evidence), (self.v, after)]))
        self.assertFalse(json.loads((self.output / 'receipt.json').read_text())['complete'])

    def test_rejects_existing_canonical_output_without_overwriting(self):
        self.output.mkdir()
        sentinel = self.output / 'receipt.json'
        sentinel.write_bytes(b'old evidence')
        with mock.patch.object(g, 'authenticate') as authenticate:
            with self.assertRaises(FileExistsError):
                g.generate(self.root, self.original, self.output)
            authenticate.assert_not_called()
        self.assertEqual(sentinel.read_bytes(), b'old evidence')

    def test_rejects_canonical_output_symlink(self):
        self.output.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            g.generate(self.root, self.original, self.output)
        self.assertEqual(self.source.read_bytes(), literal(OLD))

    def test_rejects_noncanonical_build_receipt(self):
        for wrong in [self.source, self.original.parent.parent / 'receipt.json']:
            with self.subTest(path=wrong), mock.patch.object(g, 'canonical', side_effect=lambda p, **kw: Path(p)):
                with self.assertRaisesRegex(ValueError, 'canonical CI shared-ghc'):
                    g.authenticate(self.root, wrong)
                with self.assertRaisesRegex(ValueError, 'canonical CI shared-ghc'):
                    g.generate(self.root, wrong, self.output)

    def test_rejects_output_outside_exact_diagnostic_directory(self):
        for output in [self.build / 'results', self.guard / 'other', self.root.parent / 'outside-results']:
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'separate canonical CI'):
                g.generate(self.root, self.original, output)

    def test_rejects_unbounded_timeout_before_output(self):
        for timeout in [0, -1, 1801, float('inf'), float('nan'), True]:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                g.generate(self.root, self.original, self.output, timeout)
        self.assertFalse(self.output.exists())

    def test_identity_delta_requires_unique_old_identity(self):
        self.assertFalse(g.identity_delta(literal(OLD) * 2, literal(NEW) * 2, IDENTITY)['identity_only'])
        self.assertFalse(g.identity_delta(literal(OLD), literal(NEW) + b'!', IDENTITY)['identity_only'])


class PipeTests(unittest.TestCase):
    def exercise(self, chunks, timeout=False):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        output = Path(temp.name)
        pipes = [mock.Mock(), mock.Mock()]
        for i, pipe in enumerate(pipes): pipe.fileno.return_value = i
        process = mock.Mock(stdout=pipes[0], stderr=pipes[1], returncode=0)
        process.wait.return_value = 0
        v, entry = Pins(), {}
        v.stop = mock.Mock(side_effect=lambda p: setattr(p, 'returncode', -9))
        class Selector:
            def __init__(self): self.keys = {}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def register(self, pipe, events, data): self.keys[pipe] = types.SimpleNamespace(fileobj=pipe, data=data)
            def unregister(self, pipe): self.keys.pop(pipe)
            def get_map(self): return self.keys
            def select(self, delay): return [(key, 1) for key in list(self.keys.values())]
        with mock.patch.object(g.subprocess, 'Popen', return_value=process) as launch, \
                mock.patch.object(g.selectors, 'DefaultSelector', Selector), \
                mock.patch.object(g.os, 'read', side_effect=lambda fd, n: chunks[fd].pop(0)), \
                mock.patch.object(g.time, 'monotonic', side_effect=[0, 2] if timeout else lambda: 0), \
                mock.patch.object(g, 'MAX_LITERAL', 8), mock.patch.object(g, 'MAX_STDERR', 4):
            try:
                g.run_generator(v, ['/canonical/generator', IDENTITY], output, output, 1, entry)
            except BaseException as error:
                return error, entry, v.stop, output
        self.assertEqual(launch.call_args.args[0], ['/canonical/generator', IDENTITY])
        self.assertEqual(launch.call_args.kwargs['env']['GHC_ENVIRONMENT'], '-')
        return None, entry, v.stop, output

    def test_pipe_success_and_byte_accounting(self):
        error, entry, stop, output = self.exercise([[b'literal', b''], [b'']])
        self.assertIsNone(error)
        self.assertEqual(entry['stdout']['bytes'], 7)
        self.assertEqual(entry['stderr']['bytes'], 0)
        stop.assert_not_called()

    def test_pipe_output_limit_stops_producer_and_retains_bounded_bytes(self):
        error, entry, stop, output = self.exercise([[b'0123456789', b''], [b'']])
        self.assertIsInstance(error, ValueError)
        self.assertEqual(entry['stdout']['bytes'], 8)
        self.assertEqual((output / 'fresh-literal.stdout').read_bytes(), b'01234567')
        stop.assert_called_once()

    def test_pipe_timeout_stops_producer_and_preserves_files(self):
        error, entry, stop, output = self.exercise([[b''], [b'']], timeout=True)
        self.assertIsInstance(error, subprocess.TimeoutExpired)
        self.assertEqual(entry['exit_code'], -9)
        self.assertEqual(entry['stdout']['bytes'], 0)
        stop.assert_called_once()


if __name__ == '__main__':
    unittest.main()
