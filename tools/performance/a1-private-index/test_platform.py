#!/usr/bin/env python3
"""Cheap transport regressions; no compiler, benchmark, or macOS tool is run.

These mocks check dispatch, units, limits and historical reproduction pins.
They do not qualify a real Mach-O closure, measure peak RSS, run the nine-leg
campaign, or establish that its historical candidate is the current checkout.
"""
from __future__ import annotations

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import resource
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def source_module(path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), value.__dict__)
    return value


HELPER = source_module(HERE / 'helper.py', 'a1_platform_helper')
with mock.patch.dict(sys.modules, {'helper': HELPER}):
    REPRO = source_module(HERE / 'reproduce.py', 'a1_platform_reproduction')
BUILDER = source_module(ROOT / 'tools/shared/build.py', 'a1_platform_builder')


def digest(value):
    return hashlib.sha256(value).hexdigest()


class PinContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.source = root / 'snapshot'
        self.here = root / 'runner/tools/performance/a1-private-index'
        self.here.mkdir(parents=True)
        self.source_file = 'libraries/Fixture.hs'
        self.builder_file = 'tools/shared/build.py'
        for relative, content in [(self.source_file, b'module Fixture where\n'),
                                  (self.builder_file, b'original builder\n')]:
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        adapter = self.here.parents[2] / self.builder_file
        adapter.parent.mkdir(parents=True)
        adapter.write_bytes(b'platform adapter\n')
        self.adapter = adapter.read_bytes()
        pins = {path: HELPER.sha(self.source / path)
                for path in [self.source_file, self.builder_file]}
        self.data = {'implementation_pins': {'base': pins, 'candidate': pins},
                     'implementation_module_counts': {'base': 1, 'candidate': 1}}
        self.manifest = {'modules': [{'path': self.source_file}], 'host_only': []}

    def implementation(self, platform, side='A1'):
        builder = types.SimpleNamespace(load_manifest=lambda: self.manifest)
        with mock.patch.object(REPRO.sys, 'platform', platform), \
             mock.patch.object(REPRO, 'HERE', self.here), \
             mock.patch.object(REPRO, 'module', return_value=builder):
            return REPRO.implementation(self.source, self.data, side)

    def test_linux_accepts_original_builder_on_both_sides(self):
        self.assertEqual(self.implementation('linux', 'P3'), self.implementation('linux', 'A1'))

    def test_linux_never_exempts_builder_pin(self):
        (self.source / self.builder_file).write_bytes(self.adapter)
        for side in ['P3', 'A1']:
            with self.subTest(side=side), self.assertRaisesRegex(RuntimeError, 'implementation pin'):
                self.implementation('linux', side)

    def test_darwin_accepts_only_same_current_adapter_on_both_sides(self):
        (self.source / self.builder_file).write_bytes(self.adapter)
        left, right = self.implementation('darwin', 'P3'), self.implementation('darwin', 'A1')
        self.assertEqual(left, right)
        self.assertEqual(left[str(self.source / self.builder_file)], digest(self.adapter))

    def test_darwin_rejects_a_different_builder(self):
        (self.source / self.builder_file).write_bytes(b'other adapter\n')
        with self.assertRaisesRegex(RuntimeError, 'platform builder patch mismatch'):
            self.implementation('darwin')

    def test_darwin_does_not_exempt_implementation_sources(self):
        (self.source / self.builder_file).write_bytes(self.adapter)
        (self.source / self.source_file).write_bytes(b'changed source\n')
        with self.assertRaisesRegex(RuntimeError, 'implementation pin'):
            self.implementation('darwin')

    def test_unpinned_module_or_host_input_is_rejected(self):
        for field, value in [('modules', [{'path': 'libraries/Unpinned.hs'}]),
                             ('host_only', ['host/Unpinned.hs'])]:
            with self.subTest(field=field):
                prior = self.manifest[field]
                self.manifest[field] = value
                with self.assertRaisesRegex(RuntimeError, 'unpinned registered'):
                    self.implementation('linux')
                self.manifest[field] = prior

    def test_cli_defaults_are_historical_not_head(self):
        # main() really parses its defaults, but no preparation or host probe runs.
        with mock.patch.object(sys, 'argv', ['reproduce.py', '--work-dir', '/unused/a1', '--prepare-only']), \
             mock.patch.object(REPRO, 'host', return_value={}), \
             mock.patch.object(REPRO, 'fixture_contract', return_value=({}, {})), \
             mock.patch.object(REPRO, 'prepare', return_value=Path('/unused/receipt.json')) as prepare, \
             mock.patch.object(REPRO, 'campaign') as campaign:
            REPRO.main()
        args = prepare.call_args.args[0]
        self.assertEqual(args.candidate_ref, '5a89143ecbcaaef152a7e88331583660192e106d')
        self.assertEqual(args.base_ref, '875e483de49655030c4ffba1995b60610a50273a')
        self.assertEqual(args.source_checkout, ROOT)
        campaign.assert_not_called()


class ToolchainDispatch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.libdir = root / 'install/lib'
        self.libdir.mkdir(parents=True)
        self.actual = root / 'install/bin/ghc-9.14.1'
        self.actual.parent.mkdir()
        self.actual.write_bytes(b'\x7fELFfixture')
        self.ghc, self.cc, self.windres, self.library = [root / name for name in ['ghc', 'cc', 'windres', 'libfixture.so']]
        for path in [self.ghc, self.cc, self.windres, self.library]:
            path.write_bytes(b'fixture')
        self.info = ('[("windres command","windres"),'
                     '("LLVM llc command","unused-llvm"),'
                     '("JavaScript linker command","unused-js")]')

    def invoke(self, platform, dynamic_output=None, missing_windres=False):
        calls = []
        def executable(name):
            calls.append(name)
            if missing_windres:
                raise RuntimeError('missing windres fixture')
            self.assertEqual(name, 'windres')
            return self.windres
        output = dynamic_output if dynamic_output is not None else 'libfixture.so => ' + str(self.library) + ' (0x0)\n'
        with mock.patch.object(BUILDER.sys, 'platform', platform), \
             mock.patch.object(BUILDER, 'executable', side_effect=executable), \
             mock.patch.object(BUILDER.subprocess, 'check_output', return_value=''), \
             mock.patch.object(BUILDER.subprocess, 'run', return_value=types.SimpleNamespace(
                 returncode=0, stdout=output, stderr='')) as ldd, \
             mock.patch.object(BUILDER, 'darwin_toolchain_inputs', return_value={'experimental': True}) as darwin:
            result = BUILDER.toolchain_inputs(self.ghc, self.libdir, self.info, self.cc)
        return result, calls, ldd.call_args_list, darwin.call_args_list

    def test_linux_keeps_windres_and_elf_ldd_closure(self):
        result, calls, ldd, darwin = self.invoke('linux')
        self.assertEqual(calls, ['windres'])
        self.assertEqual(ldd, [mock.call(['ldd', str(self.actual)], capture_output=True, text=True)])
        self.assertEqual(darwin, [])
        self.assertEqual(set(result['files']), {str(p) for p in [self.ghc, self.cc, self.actual, self.windres, self.library]})
        self.assertEqual(result['actual_ghc']['sha256'], HELPER.sha(self.actual))

    def test_linux_missing_windres_is_not_silently_skipped(self):
        with self.assertRaisesRegex(RuntimeError, 'missing windres'):
            self.invoke('linux', missing_windres=True)

    def test_linux_missing_dynamic_dependency_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'missing dynamic toolchain dependency'):
            self.invoke('linux', dynamic_output='libfixture.so => not found\n')

    def test_darwin_alone_skips_windres_and_dispatches_collector(self):
        result, calls, ldd, darwin = self.invoke('darwin', missing_windres=True)
        self.assertEqual(result, {'experimental': True})
        self.assertEqual(calls, [])
        self.assertEqual(ldd, [])
        self.assertEqual(darwin, [mock.call({self.ghc, self.cc, self.actual}, self.actual, self.libdir)])

    def test_other_platform_fails_closed(self):
        with self.assertRaisesRegex(RuntimeError, 'Linux toolchains only'):
            self.invoke('unsupported')


class PreparationTransport(unittest.TestCase):
    def preparation(self, platform):
        """Run prepare's orchestration, with all compiler/host work replaced."""
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            repo, work = root / 'repo', root / 'work'
            repo.mkdir()
            here = root / 'runner/tools/performance/a1-private-index'
            here.mkdir(parents=True)
            adapter = here.parents[2] / 'tools/shared/build.py'
            adapter.parent.mkdir(parents=True)
            adapter.write_bytes(b'platform-only builder fixture\n')
            (here / 'run_controls.py').write_bytes(b'unchanged literal controls runner fixture\n')
            ghc, cc = root / 'ghc-fixture', root / 'cc-fixture'
            ghc.write_bytes(b'not executed')
            cc.write_bytes(b'not executed')
            original = b'original fixed builder fixture\n'
            source_bytes = {'tools/shared/build.py': original,
                            'libraries/Fixture.hs': b'module Fixture where\n',
                            'tools/performance/a1-private-index/run_controls.py': (here / 'run_controls.py').read_bytes()}
            pins = {path: digest(value) for path, value in source_bytes.items()}
            data = {'implementation_pins': {'base': pins, 'candidate': pins},
                    'implementation_module_counts': {'base': 1, 'candidate': 1}}
            args = types.SimpleNamespace(work_dir=work, source_checkout=repo, ghc=ghc, cc=cc,
                                         base_ref='a' * 40, candidate_ref='b' * 40, rss_mib=5120,
                                         address_space_mib=6144, host_available_mib=3072,
                                         disk_free_mib=4096, max_work_gib=16, command_timeout=21600)
            builds = []
            def snapshot(repository, ref, destination, runner, output):
                for relative, content in source_bytes.items():
                    path = destination / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                return ref
            def receipt(folder):
                folder.mkdir(parents=True)
                (folder / 'receipt.json').write_text('{}\n')
            class Runner:
                def __init__(self, *unused):
                    pass
                def run(self, argv, cwd, output):
                    if '--build-dir' in argv:
                        producer = Path(argv[argv.index('--build-dir') + 1])
                        builds.append((producer.name, (Path(cwd) / 'tools/shared/build.py').read_bytes()))
                        receipt(producer)
                    else:
                        receipt(Path(argv[argv.index('--output') + 1]))
                    return {'complete': True}
            def dependencies(*unused):
                receipt(work / 'dependencies')
                return {'builtin_prefix': str(work / 'builtin'), 'artifacts': {}}
            identity = {key: 'same installed fixture' for key in
                        ['ghc', 'cc', 'ghc_settings', 'toolchain', 'installed_dependencies']}
            stack.enter_context(mock.patch.object(REPRO.sys, 'platform', platform))
            stack.enter_context(mock.patch.object(REPRO, 'HERE', here))
            # Do not print a mocked preparation as if it were real evidence.
            stack.enter_context(mock.patch.object(REPRO, 'print', create=True))
            stack.enter_context(mock.patch.object(REPRO, 'host', return_value={'mocked': True}))
            stack.enter_context(mock.patch.object(REPRO, 'Runner', Runner))
            stack.enter_context(mock.patch.object(REPRO.subprocess, 'check_output', return_value='9.14.1\n'))
            stack.enter_context(mock.patch.object(REPRO, 'git_snapshot', side_effect=snapshot))
            stack.enter_context(mock.patch.object(REPRO, 'module', return_value=types.SimpleNamespace(
                load_manifest=lambda: {'modules': [{'path': 'libraries/Fixture.hs'}], 'host_only': []})))
            stack.enter_context(mock.patch.object(REPRO, 'authenticate', return_value=identity))
            stack.enter_context(mock.patch.object(REPRO, 'prepare_dependencies', side_effect=dependencies))
            stack.enter_context(mock.patch.object(REPRO, 'validate_dependencies', side_effect=lambda *unused: receipt(work / 'dependency-validation')))
            stack.enter_context(mock.patch.object(REPRO, 'prepare_ghc', side_effect=lambda *unused: receipt(work / 'ghc-dependencies')))
            controls = stack.enter_context(mock.patch.object(REPRO, 'verify_controls'))
            result = REPRO.prepare(args, data, {})
            record = json.loads(result.read_text())
            controls.assert_called_once_with(work / 'focused-controls/receipt.json')
            return record, builds, digest(original), digest(adapter.read_bytes())

    def test_darwin_prepare_records_same_overlay_for_both_real_loop_iterations(self):
        record, builds, original, adapted = self.preparation('darwin')
        self.assertTrue(record['complete'])
        self.assertEqual([side for side, _ in builds], ['P3', 'A1'])
        self.assertEqual({digest(value) for _, value in builds}, {adapted})
        self.assertEqual(set(record['platform_patches']), {'P3', 'A1'})
        for row in record['platform_patches'].values():
            self.assertEqual(row['original_sha256'], original)
            self.assertEqual(row['adapted_sha256'], adapted)
        self.assertFalse(record['native_bootstrap'])
        self.assertFalse(record['local_full_qualification'])

    def test_linux_prepare_keeps_both_fixed_builders_unmodified(self):
        record, builds, original, _ = self.preparation('linux')
        self.assertTrue(record['complete'])
        self.assertEqual([side for side, _ in builds], ['P3', 'A1'])
        self.assertEqual({digest(value) for _, value in builds}, {original})
        self.assertNotIn('platform_patches', record)


class MemoryAndProcessUnits(unittest.TestCase):
    def test_linux_memavailable_is_kib_and_never_calls_vm_stat(self):
        with mock.patch.object(HELPER.sys, 'platform', 'linux'), \
             mock.patch.object(HELPER.Path, 'read_text', return_value='MemFree: 1 kB\nMemAvailable: 42 kB\n'), \
             mock.patch.object(HELPER.subprocess, 'check_output') as command:
            self.assertEqual(HELPER.memory_available(), 42 * 1024)
        command.assert_not_called()

    def test_darwin_uses_reported_page_size_and_only_estimate_fields(self):
        output = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
                  'Pages free: 2.\nPages inactive: 3.\nPages speculative: 5.\nPages active: 99.\n')
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.subprocess, 'check_output', return_value=output) as command:
            self.assertEqual(HELPER.memory_available(), 10 * 16384)
        command.assert_called_once_with(['/usr/bin/vm_stat'], text=True)

    def test_darwin_missing_estimate_field_is_rejected(self):
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.subprocess, 'check_output', return_value='page size of 4096 bytes\nPages free: 1.\n'):
            with self.assertRaisesRegex(RuntimeError, 'vm_stat memory fields missing'):
                HELPER.memory_available()

    def test_darwin_process_rss_is_kib_and_group_filter_is_explicit(self):
        output = '101 1 41 0 R+ 12\n102 101 41 0 Z+ 3\n103 1 42 0 S 9\n'
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.subprocess, 'check_output', return_value=output) as command:
            self.assertEqual(HELPER.process_group(41), [
                {'pid': 101, 'state': 'R+', 'rss': 12 * 1024},
                {'pid': 102, 'state': 'Z+', 'rss': 3 * 1024}])
        command.assert_called_once_with(['/bin/ps', '-axo', 'pid=,ppid=,pgid=,sess=,state=,rss='], text=True)

    def test_unknown_ps_layout_or_nondecimal_session_fails_closed(self):
        # sess is not promised to be a Linux numeric SID on all Darwin releases.
        for output in ['1 2 3\n', '1 2 3 0x123 S 9\n']:
            with self.subTest(output=output), mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
                 mock.patch.object(HELPER.subprocess, 'check_output', return_value=output):
                with self.assertRaises((RuntimeError, ValueError)):
                    HELPER.process_group(3)

    def test_linux_process_rss_uses_page_size(self):
        def entry(pid, group, session, rss):
            fields = ['0'] * 22
            fields[0], fields[2], fields[3], fields[21] = 'S', str(group), str(session), str(rss)
            value = mock.MagicMock()
            value.name = str(pid)
            value.__truediv__.return_value.read_text.return_value = str(pid) + ' (fixture) ' + ' '.join(fields)
            return value
        proc = mock.Mock()
        proc.iterdir.return_value = [entry(101, 41, 0, 2), entry(102, 0, 41, 3), entry(103, 9, 9, 7)]
        with mock.patch.object(HELPER.sys, 'platform', 'linux'), \
             mock.patch.object(HELPER, 'Path', return_value=proc), \
             mock.patch.object(HELPER.os, 'sysconf', return_value=4096):
            self.assertEqual(HELPER.process_group(41), [
                {'pid': 101, 'state': 'S', 'rss': 2 * 4096},
                {'pid': 102, 'state': 'S', 'rss': 3 * 4096}])


class RunnerAccounting(unittest.TestCase):
    def run_mock(self, platform, terminal=None, sampled_overflow=False, wait_status=0):
        """Exercise the actual Runner without launching a child or setting limits."""
        pending = []
        class Event:
            ready = False
            waits = 0
            def set(self):
                self.ready = True
            def wait(self, timeout=None):
                if self.ready:
                    return True
                if self.waits == 0:
                    self.waits += 1
                    return False
                pending[0]()
                return self.ready
        class Thread:
            def __init__(self, target, daemon):
                self.target = target
            def start(self):
                if sampled_overflow:
                    pending.append(self.target)
                else:
                    self.target()
            def join(self):
                pass
        def popen(argv, **kwargs):
            kwargs['preexec_fn']()
            self.assertTrue(kwargs['start_new_session'])
            return types.SimpleNamespace(pid=321, returncode=None)
        usage = types.SimpleNamespace(ru_utime=1.25, ru_stime=0.5, ru_maxrss=19,
                                      ru_nvcsw=2, ru_nivcsw=3)
        limits = {'address_space_per_process_bytes': 64 * 1024**2,
                  'host_available_floor_bytes': 1, 'disk_free_floor_bytes': 1,
                  'process_tree_rss_bytes': 5120, 'max_work_bytes': 1024**2, 'wall_seconds': 30}
        rows = terminal if terminal is not None else []
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            stack.enter_context(mock.patch.object(HELPER.sys, 'platform', platform))
            stack.enter_context(mock.patch.object(HELPER, 'memory_available', return_value=1024**3))
            process_groups = stack.enter_context(mock.patch.object(HELPER, 'process_group', return_value=rows))
            if sampled_overflow:
                process_groups.side_effect = [[{'pid': 321, 'state': 'R', 'rss': 5121}], []]
            stack.enter_context(mock.patch.object(HELPER.threading, 'Event', Event))
            stack.enter_context(mock.patch.object(HELPER.threading, 'Thread', Thread))
            stack.enter_context(mock.patch.object(HELPER.subprocess, 'Popen', side_effect=popen))
            stack.enter_context(mock.patch.object(HELPER.os, 'wait4', return_value=(321, wait_status, usage)))
            setrlimit = stack.enter_context(mock.patch.object(HELPER.resource, 'setrlimit'))
            killpg = stack.enter_context(mock.patch.object(HELPER.os, 'killpg'))
            failure = None
            try:
                HELPER.Runner(root, limits).run(['mock-compiler'], root, root / 'command', timed=True)
            except RuntimeError as error:
                failure = error
            receipt = json.loads((root / 'command/command.json').read_text())
            return receipt, setrlimit.call_args_list, killpg.call_args_list, failure

    def test_linux_address_limit_and_ru_maxrss_units(self):
        receipt, limits, kills, failure = self.run_mock('linux')
        self.assertIsNone(failure)
        self.assertTrue(receipt['complete'])
        self.assertEqual(limits, [mock.call(resource.RLIMIT_AS, (64 * 1024**2, 64 * 1024**2))])
        self.assertEqual(receipt['max_individual_child_rss_bytes'], 19 * 1024)
        self.assertEqual(receipt['child_user_seconds'], 1.25)
        self.assertEqual(receipt['child_system_seconds'], 0.5)
        self.assertNotIn('resource_qualification', receipt)
        self.assertEqual(kills, [])

    def test_darwin_has_no_address_limit_and_ru_maxrss_is_bytes(self):
        receipt, limits, kills, failure = self.run_mock('darwin')
        self.assertIsNone(failure)
        self.assertTrue(receipt['complete'])
        self.assertEqual(limits, [])
        self.assertEqual(receipt['max_individual_child_rss_bytes'], 19)
        self.assertIn('not enforced', receipt['resource_qualification']['address_space_limit'])
        self.assertIn('short peaks may be missed', receipt['resource_qualification']['process_group_rss'])
        self.assertEqual(kills, [])

    def test_zombie_suffix_is_not_a_live_descendant(self):
        receipt, _, kills, failure = self.run_mock('darwin', [{'pid': 322, 'state': 'Z+', 'rss': 0}])
        self.assertIsNone(failure)
        self.assertTrue(receipt['complete'])
        self.assertEqual(receipt['terminal_live_descendants'], [])
        self.assertEqual(kills, [])

    def test_live_descendant_makes_successful_leader_incomplete(self):
        receipt, _, kills, failure = self.run_mock('darwin', [{'pid': 322, 'state': 'S', 'rss': 1}])
        self.assertIsNotNone(failure)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['reason'], 'live descendants after leader completion')
        self.assertEqual(kills, [mock.call(321, signal.SIGKILL)])

    def test_sampled_overflow_kills_but_does_not_claim_hard_address_cap(self):
        receipt, limits, kills, failure = self.run_mock('darwin', sampled_overflow=True, wait_status=9)
        self.assertIsNotNone(failure)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['reason'], 'process-tree RSS limit')
        self.assertEqual(receipt['sampled_process_tree_peak_rss_bytes'], 5121)
        self.assertEqual(limits, [])
        self.assertEqual(kills, [mock.call(321, signal.SIGKILL)])

    def test_nonzero_child_is_not_a_success(self):
        receipt, _, _, failure = self.run_mock('linux', wait_status=3 << 8)
        self.assertIsNotNone(failure)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['exit_code'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
