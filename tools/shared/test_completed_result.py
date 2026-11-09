"""Synthetic file controls only; no GHC/native/Git execution or qualification."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


HERE = Path(__file__).resolve().parent
b = load('completion_driver', HERE / 'bootstrap_ghc_native.py')
p = load('completion_prerequisites', HERE / 'collect_ghc_native_prerequisites.py')
fixture = load('completion_fixture', HERE / 'completion_fixture.py')
fixture.b = b


class CompletedControls(unittest.TestCase):
    def file(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def setUp(self):
        # Keep all scratch artifacts inside the bounded proposal directory.
        self.temp = tempfile.TemporaryDirectory(dir=HERE.parents[1])
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'
        self.out = self.base / 'native'
        self.producer = self.base / 'producer'
        self.file(self.source / 'runtime/mlf_build_runner.c', 'SYNTHETIC runner source')
        self.file(self.source / 'bootstrap/MLF/PreparedNativeData.hs',
                  (HERE / 'fixtures/canonical-disabled-native.hs').read_text())
        self.file(self.producer / 'receipt.json', {'optimization': '2', 'fixture_only': True})
        self.a = fixture.StageFixture(self.source, self.out, 'A', self.producer)
        self.z = fixture.StageFixture(self.source, self.out, 'B', self.producer)
        self.stages = {'A': self.a.verify(), 'B': self.z.verify()}
        self.comparisons = b.compare_stages(self.stages['A'], self.stages['B'])
        self.plans = self.base / 'prerequisites/plans'
        self.gate = self.file(self.plans.parent / 'gate.json', {'fixture_only': True})
        self.file(self.plans / 'receipt.json', {'fixture_only': True})
        self.file(self.plans / 'root-plan.json', {'packages': self.a.packages, 'crates': self.a.crates})
        self.clang = self.a.clang
        self.pkg = self.clang
        self.gc = self.base / 'gc'
        self.file(self.gc / 'lib/libgc.a', 'SYNTHETIC GC archive')
        self.file(self.gc / 'include/gc.h', 'SYNTHETIC GC header')
        self.nice = self.file(self.base / 'tools/nice', 'SYNTHETIC nice')
        self.python = self.file(self.base / 'tools/python', 'SYNTHETIC Python')
        self.ldd = self.file(self.base / 'tools/ldd', 'SYNTHETIC ldd')
        self.ld = self.file(self.base / 'tools/ld', 'SYNTHETIC ld')
        self.file(self.base / 'gmp/libgmp.so', 'SYNTHETIC GMP')
        self.helper = self.out / 'tools/mlf-build-runner'
        self.auth = {}
        for name in b.PRODUCER_AUTH_HELPERS:
            path = self.file(self.source / 'tools/shared' / name, 'SYNTHETIC authentication fixture')
            self.auth[str(path)] = b.sha(path)
        self.heads = {'source': 'a' * 40, 'driver': 'b' * 40}
        self.fixed_git = Path('/usr/bin/git').resolve(strict=True)
        self.fixed_git_digest = b.sha(self.fixed_git)
        self.file(self.gate, {'fixture_only': True, 'binding': {'git':
            {'path': str(self.fixed_git), 'sha256': self.fixed_git_digest}}})
        self.identities = {name: {'head': head, 'expected': head, 'dirty': False,
                                 'git': str(self.fixed_git), 'git_sha256': self.fixed_git_digest}
                           for name, head in self.heads.items()}
        self.kwargs = dict(source_root=self.source, checkpoint=self.heads['source'],
            driver_checkpoint=self.heads['driver'], producer_receipt=self.producer / 'receipt.json',
            producer_sha256=b.sha(self.producer / 'receipt.json'), frontend_receipt=self.gate,
            frontend_sha256=b.sha(self.gate), plans_dir=self.plans, plans_sha256=b.sha(self.plans / 'receipt.json'))
        self.contract = {'source_root': str(self.source), 'driver_root': str(b.ROOT),
            'checkpoints': self.identities, 'producer_receipt': str(self.kwargs['producer_receipt']),
            'producer_sha256': self.kwargs['producer_sha256'], 'frontend_receipt': str(self.gate),
            'frontend_sha256': self.kwargs['frontend_sha256'], 'plans_dir': str(self.plans),
            'plans_sha256': self.kwargs['plans_sha256'], 'producer_authentication_inputs': self.auth,
            'clang': str(self.clang), 'pkg_config': str(self.pkg), 'nice': str(self.nice),
            'python': str(self.python), 'gc_prefix': str(self.gc), 'loader_dirs': [],
            'loader_inventory': {'files': {}, 'bindings': {}}, 'action_seconds': 60}
        self.environment = b.isolated_environment(self.out, self.clang, self.pkg, self.gc, [])
        commands = [(f'native-loader-{i}', [self.ldd, tool], '')
                    for i, tool in enumerate((self.clang, self.pkg, self.python))]
        commands += [('gmp-flags', [self.pkg, '--cflags', '--libs', 'gmp'], '-lgmp\n'),
            ('gmp-libdir', [self.pkg, '--variable=libdir', 'gmp'], str(self.base / 'gmp') + '\n'),
            ('clang-link-selection', [self.clang, '-###', '-O2', self.source / 'runtime/mlf_build_runner.c',
                self.gc / 'lib/libgc.a', '-lgmp', '-lm', '-lpthread', '-ldl', '-o',
                self.out / 'tools/not-built-link-probe'], '"' + str(self.ld) + '"\n'),
            ('selected-tool-loader-0', [self.ldd, self.ld], '')]
        for name, source, flags in [('runner', self.source / 'runtime/mlf_build_runner.c', []),
                ('runtime', self.source / 'runtime/mlf_runtime.c', ['-I' + str(self.gc / 'include')])]:
            dep = self.file(self.out / 'tools' / (name + '.d'), 'probe: ' + str(source) + '\n')
            commands.append((name + '-dependencies', [self.clang, '-M', '-std=c11', *flags, '-MF', dep, source], ''))
        commands += [('build-runner', [self.clang, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
            self.source / 'runtime/mlf_build_runner.c', '-o', self.helper], ''),
            ('runner-protocol', [self.helper, '--protocol-version'], '1\n')]
        planned = []
        for name, pair in [('A', self.producer / 'bin'), ('B', self.out / 'stage-A/bin')]:
            argv = b.stage_command(self.source, pair, self.out / ('stage-' + name),
                self.out / ('cache-' + name), self.clang, self.gc, 60, self.pkg)
            planned.append(argv)
            commands.append(('stage-' + name, argv, 'SYNTHETIC stage log'))
            commands += [(name + '-' + tool + '-identity',
                [self.out / ('stage-' + name) / 'bin' / tool, '--implementation-identity'],
                'MLF/shared-haskell-v1 native-MLF\n') for tool in b.TARGETS]
        rows = []
        for label, argv, log in commands:
            argv = list(map(str, argv))
            stage_env = ({'MLF_BUILD_RUNNER': str(self.helper)} if label.startswith(('stage-A', 'A-')) else
                         {'MLF_BUILD_RUNNER': str(self.out / 'stage-A/bin/mlf-build-runner')}
                         if label.startswith(('stage-B', 'B-')) else {})
            directory = self.out / 'commands' / label
            self.file(directory / 'build.log', log)
            bounded = self.file(directory / 'bounded-receipt.json', {'complete': True, 'exit_code': 0,
                'final_owned_descendants': [], 'reason': None, 'command': [str(self.nice), '-n', '19', *argv]})
            rows.append({'label': label, 'argv': argv, 'exit_code': 0, 'bounded_receipt': str(bounded),
                'bounded_sha256': b.sha(bounded), 'log_sha256': b.sha(directory / 'build.log'),
                'driver_teardown': {'drained': True, 'remaining': []}, 'stage_environment': stage_env,
                'environment': {**self.environment, **stage_env}})
        inputs = {str(path): b.sha(path) for path in self.base.rglob('*') if path.is_file()}
        for path in (Path(b.__file__), b.ROOT / 'tools/shared/test_direct.py',
                     b.ROOT / 'tools/shared/resource_watchdog.py', b.ROOT / 'tools/shared/collect_ghc_native_prerequisites.py'):
            inputs[str(path)] = b.sha(path)
        inputs[str(self.fixed_git)] = self.fixed_git_digest
        # Real production inputs do not contain these success/pointer files.
        self.receipt = {'format': 2, 'route': b.ROUTE, 'output': str(self.out), 'mode': 'execute',
            'phase': 'fixed-point-complete', 'status': 'passed', 'complete': True, 'fixed_point_qualified': True,
            'boundary_complete': True, 'stage_complete': {'runner': True, 'A': True, 'B': True},
            'stages': self.stages, 'comparisons': self.comparisons, 'contract': self.contract,
            'checkpoints': self.identities, 'inputs': inputs, 'path_bindings': {str(self.clang): str(self.clang)},
            'producer_receipt_sha256': self.kwargs['producer_sha256'],
            'frontend_receipt_sha256': self.kwargs['frontend_sha256'], 'plans_receipt_sha256': self.kwargs['plans_sha256'],
            'environment': self.environment, 'runner': {'path': str(self.helper), 'sha256': b.sha(self.helper)},
            'commands': rows, 'native_gmp_flags': ['-lgmp'], 'clang_selected_tools': [str(self.ld)],
            'planned_stage_commands': planned}
        inventory = b.output_tree(self.out, hashes=True)
        inventory = {k: v for k, v in inventory.items() if not k.startswith(('stage-B', 'cache-B', 'commands/stage-B', 'commands/B-'))}
        self.receipt['output_inventory'] = inventory
        self.history = copy.deepcopy(self.receipt)
        self.history.update(phase='native-A-complete', status='paused', complete=False, fixed_point_qualified=False,
                            stage_complete={'runner': True, 'A': True, 'B': False}, stages={'A': self.stages['A']})
        self.history['commands'] = copy.deepcopy(rows[:next(n for n, r in enumerate(rows) if r['label'] == 'stage-B')])
        history = self.file(self.out / 'checkpoints/native-A-complete.json', self.history)
        self.receipt['boundary_checkpoint'] = {'path': str(history), 'sha256': b.sha(history)}
        for tool, pointer in [('emlf', 'compiler.path'), ('mlfpkg', 'manager.path')]:
            self.file(self.out / pointer, str(self.out / 'stage-B/bin' / tool) + '\n')
        self.seal()

    def seal(self):
        self.path = self.file(self.out / 'receipt.json', self.receipt)
        self.digest = b.sha(self.path)

    def invoke(self, producer_effect=None):
        def checkpoint(root, git, env, expected, executing, *, read_only=False):
            self.assertTrue(read_only)
            self.assertTrue(executing)
            result = self.identities['source' if root == self.source else 'driver']
            if expected != result['head']:
                raise ValueError('fixture exact checkpoint mismatch')
            return result
        with contextlib.ExitStack() as stack:
            for name in ('Popen', 'run', 'check_output', 'check_call', 'call'):
                stack.enter_context(mock.patch.object(subprocess, name, side_effect=AssertionError('subprocess forbidden in fixture')))
            stack.enter_context(mock.patch.object(b, 'source_checkpoint', side_effect=checkpoint))
            producer = stack.enter_context(mock.patch.object(b, 'authenticate_producer',
                side_effect=producer_effect, return_value={'optimization': '2'}))
            prereq = stack.enter_context(mock.patch.object(b, 'verify_prerequisites', return_value={
                'inputs': {str(self.plans / 'receipt.json'): b.sha(self.plans / 'receipt.json')}}))
            stage = stack.enter_context(mock.patch.object(b, 'verify_stage', wraps=b.verify_stage))
            old_open = Path.open
            def readonly_open(path, mode='r', *args, **kwargs):
                if any(flag in mode for flag in 'wax+'):
                    raise AssertionError('verification attempted a write')
                return old_open(path, mode, *args, **kwargs)
            stack.enter_context(mock.patch.object(Path, 'open', readonly_open))
            for name in ('mkdir', 'unlink', 'rename', 'replace'):
                stack.enter_context(mock.patch.object(Path, name, side_effect=AssertionError('verification filesystem mutation')))
            result = b.authenticate_completed(self.path, self.digest, **self.kwargs)
            self.assertEqual(stage.call_count, 2)
            self.assertEqual(producer.call_count, 1)
            self.assertTrue(prereq.call_args.kwargs['read_only'])
            self.assertEqual(prereq.call_args.kwargs['source_checkpoint'], self.heads['source'])
            self.assertEqual(prereq.call_args.kwargs['driver_checkpoint'], self.heads['driver'])
            return result

    def test_synthetic_two_stage_authentication_is_readonly(self):
        before = b.output_tree(self.out, hashes=True)
        self.assertEqual(self.invoke()['comparisons'], self.comparisons)
        self.assertEqual(b.output_tree(self.out, hashes=True), before)

    def test_wrong_status_phase_route_and_incomplete_a_rejected(self):
        for field, value in [('route', 'other'), ('status', 'paused'), ('phase', 'native-A-complete'),
                             ('complete', False), ('fixed_point_qualified', False)]:
            old = self.receipt[field]
            self.receipt[field] = value; self.seal()
            with self.subTest(field=field), self.assertRaises(ValueError): self.invoke()
            self.receipt[field] = old

    def test_each_raw_digest_mismatch_rejected(self):
        for tool in b.TARGETS:
            for kind in ('llvm_sha256', 'object_sha256', 'binary_sha256'):
                old = self.receipt['comparisons'][tool][kind]
                self.receipt['comparisons'][tool][kind] = 'f' * 64; self.seal()
                with self.subTest(tool=tool, kind=kind), self.assertRaises(ValueError): self.invoke()
                self.receipt['comparisons'][tool][kind] = old

    def test_native_input_signature_tampering_rejected(self):
        self.receipt['stages']['B']['native_input_signature']['machine'] = 'other'; self.seal()
        with self.assertRaises(ValueError): self.invoke()

    def test_missing_published_output_rejected(self):
        (self.out / 'stage-B/bin/emlf').unlink()
        with self.assertRaises((ValueError, FileNotFoundError)): self.invoke()

    def test_omitted_stage_b_rejected(self):
        self.receipt['stages'].pop('B'); self.seal()
        with self.assertRaises(ValueError): self.invoke()

    def test_wrong_pointer_rejected(self):
        (self.out / 'compiler.path').write_text(str(self.producer / 'bin/emlf') + '\n')
        with self.assertRaisesRegex(ValueError, 'publication pointer'): self.invoke()

    def test_source_driver_or_producer_identity_drift_rejected(self):
        for key in ('checkpoint', 'driver_checkpoint', 'producer_sha256', 'frontend_sha256', 'plans_sha256'):
            old = self.kwargs[key]; self.kwargs[key] = ('e' * len(old))
            with self.subTest(key=key), self.assertRaises(ValueError): self.invoke()
            self.kwargs[key] = old

    def test_forged_successful_stage_command_is_not_sufficient(self):
        row = next(r for r in self.receipt['commands'] if r['label'] == 'stage-B')
        row['argv'] = [str(self.producer / 'bin/mlfpkg'), '--version']
        bounded = Path(row['bounded_receipt']); data = b.read(bounded)
        data['command'] = [str(self.nice), '-n', '19', *row['argv']]
        self.file(bounded, data); row['bounded_sha256'] = b.sha(bounded)
        self.receipt['inputs'][str(bounded)] = b.sha(bounded); self.seal()
        with self.assertRaisesRegex(ValueError, 'command argv differs'): self.invoke()

    def test_protocol_or_identity_wrong_even_when_hashes_rebound(self):
        label = 'B-emlf-identity'
        path = self.out / 'commands' / label / 'build.log'
        self.file(path, 'MLF/shared-haskell-v1 GHC\n')
        row = next(r for r in self.receipt['commands'] if r['label'] == label)
        row['log_sha256'] = self.receipt['inputs'][str(path)] = b.sha(path); self.seal()
        with self.assertRaisesRegex(ValueError, 'native identity evidence'): self.invoke()

    def test_unbound_b_miscellaneous_file_is_not_claimed_sealed(self):
        self.file(self.out / 'unbound-B-notes.txt', 'Unsealed miscellaneous evidence')
        self.assertEqual(self.invoke()['comparisons'], self.comparisons)

    def test_wrong_historical_boundary_rejected(self):
        self.history['phase'] = 'fixed-point-complete'
        path = self.file(self.out / 'checkpoints/native-A-complete.json', self.history)
        self.receipt['boundary_checkpoint']['sha256'] = b.sha(path); self.seal()
        with self.assertRaisesRegex(ValueError, 'historical A boundary'): self.invoke()

    def test_enabled_native_registry_rejected_before_authentication(self):
        self.file(self.source / 'bootstrap/MLF/PreparedNativeData.hs', 'enabled fixture registry')
        with self.assertRaisesRegex(ValueError, 'does not support an enabled native registry'):
            self.invoke()

    def test_no_pycache_before_source_helper_loading(self):
        module = self.file(self.base / 'import_fixture.py', 'VALUE = 1\n')
        def import_source(*args):
            self.assertTrue(sys.dont_write_bytecode)
            self.assertEqual(load('readonly_import_fixture', module).VALUE, 1)
            return {'optimization': '2'}
        with mock.patch.object(sys, 'dont_write_bytecode', False):
            self.invoke(producer_effect=import_source)
            self.assertFalse(sys.dont_write_bytecode)
        self.assertFalse((self.base / '__pycache__').exists())

    def test_source_git_index_receipts_and_pointers_unchanged(self):
        self.file(self.source / '.git/index', 'SYNTHETIC git index')
        before = {str(p): b.sha(p) for p in self.base.rglob('*') if p.is_file()}
        self.invoke()
        after = {str(p): b.sha(p) for p in self.base.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_missing_output_not_created(self):
        missing = self.base / 'absent/receipt.json'
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('no process')):
            with self.assertRaises((ValueError, FileNotFoundError)):
                b.authenticate_completed(missing, 'a' * 64, **self.kwargs)
        self.assertFalse(missing.parent.exists())

    def test_active_lock_rejected_without_changes(self):
        self.file(self.out / 'driver.lock', 'fixture active')
        with self.assertRaisesRegex(ValueError, 'active or has unfinished'): self.invoke()


class CheckpointReadOnlyControls(unittest.TestCase):
    def test_verification_cli_cannot_combine_with_execute_or_create_outputs(self):
        with mock.patch.object(b, 'authenticate_completed', side_effect=AssertionError('must reject arguments first')):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                b.completed_main(['--verify-complete', '--execute'])




if __name__ == '__main__':
    unittest.main()
