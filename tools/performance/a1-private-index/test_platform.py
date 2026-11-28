#!/usr/bin/env python3
"""Test current toolchain discovery, resource accounting, and POSIX session cleanup."""
from __future__ import annotations

from contextlib import ExitStack
import json
import os
from pathlib import Path
import resource
import select
import signal
import subprocess
import sys
import tempfile
import time
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
BUILDER = source_module(ROOT / 'tools/shared/build.py', 'a1_platform_builder')


class ToolchainDispatch(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
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

    def test_darwin_process_rss_includes_workers_in_separate_groups(self):
        output = '101 41 R+ 12\n102 41 Z+ 3\n103 103 S 9\n104 104 R 6\n105 105 R 5\n'
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.subprocess, 'check_output', return_value=output) as command, \
             mock.patch.object(HELPER.os, 'getsid', side_effect=[41, 44, ProcessLookupError]) as session:
            self.assertEqual(HELPER.process_group(41), [
                {'pid': 101, 'state': 'R+', 'rss': 12 * 1024},
                {'pid': 102, 'state': 'Z+', 'rss': 3 * 1024},
                {'pid': 103, 'state': 'S', 'rss': 9 * 1024}])
        command.assert_called_once_with(['/bin/ps', '-axo', 'pid=,pgid=,state=,rss='], text=True)
        self.assertEqual(session.call_args_list, [mock.call(103), mock.call(104), mock.call(105)])

    def test_unknown_ps_layout_fails_closed(self):
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


class GroupTermination(unittest.TestCase):
    def test_darwin_accepts_eperm_only_for_disappeared_or_zombie_only_group(self):
        for members in ([], [{'pid': 31, 'state': 'Z+'}]):
            with self.subTest(members=members), mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
                 mock.patch.object(HELPER.os, 'getsid', return_value=31), \
                 mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError) as killpg:
                HELPER.kill_group(31, members=lambda group: members)
                killpg.assert_called_once_with(31, signal.SIGKILL)

    def test_darwin_eperm_rechecks_exiting_members(self):
        exiting = [{'pid': 31, 'state': '?E', 'rss': 0}]
        zombie = [{'pid': 31, 'state': 'Z+', 'rss': 0}]
        for final in ([], zombie):
            inventory = mock.Mock(side_effect=[exiting, final])
            with self.subTest(final=final), mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
                 mock.patch.object(HELPER.os, 'getsid', return_value=31), \
                 mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError), \
                 mock.patch.object(HELPER.time, 'sleep'), mock.patch.object(HELPER.os, 'kill') as kill:
                HELPER.kill_group(31, members=inventory)
                self.assertEqual(inventory.call_args_list, [mock.call(31)] * 2)
                kill.assert_not_called()

    def test_persistent_or_unconfirmed_exit_does_not_hide_eperm(self):
        exiting = {'pid': 31, 'state': '?E', 'rss': 0}
        stopped = {'pid': 32, 'state': 'T', 'rss': 0}
        for label, platform, rows in [
                ('persistent', 'darwin', [exiting]), ('mixed', 'darwin', [exiting, stopped]),
                ('unknown', 'darwin', [dict(exiting, state='?')]),
                ('resident', 'darwin', [dict(exiting, rss=4096)]), ('Linux', 'linux', [exiting])]:
            with self.subTest(label=label), mock.patch.object(HELPER.sys, 'platform', platform), \
                 mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError), \
                 mock.patch.object(HELPER.os, 'getpgid', return_value=31), \
                 mock.patch.object(HELPER.os, 'getsid', return_value=31), \
                 mock.patch.object(HELPER.os, 'kill') as kill, mock.patch.object(HELPER.time, 'sleep'):
                inventory = mock.Mock(return_value=rows)
                with self.assertRaises(PermissionError):
                    HELPER.kill_group(31, members=inventory)
                if label == 'persistent':
                    self.assertGreater(inventory.call_count, 1)
                    self.assertLessEqual(inventory.call_count, 6)
                else:
                    inventory.assert_called_once_with(31)
                self.assertEqual(kill.call_count, len(rows))

    def test_exit_recheck_reports_a_stopped_member_or_inspection_error(self):
        exiting = [{'pid': 31, 'state': '?E', 'rss': 0}]
        stopped = [{'pid': 31, 'state': 'T', 'rss': 0}]
        for result, error in [(stopped, PermissionError), (RuntimeError('failed inventory'), RuntimeError)]:
            inventory = mock.Mock(side_effect=[exiting, result])
            with self.subTest(result=result), mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
                 mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError), \
                 mock.patch.object(HELPER.os, 'getsid', return_value=31), \
                 mock.patch.object(HELPER.os, 'kill'), mock.patch.object(HELPER.time, 'sleep'):
                with self.assertRaises(error):
                    HELPER.kill_group(31, members=inventory)

    def test_live_group_denial_is_reported_after_best_effort_cleanup(self):
        rows = [{'pid': 31, 'state': 'S'}, {'pid': 32, 'state': 'R'}, {'pid': 35, 'state': 'Z'}]
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError), \
             mock.patch.object(HELPER.os, 'getsid', side_effect=[31, 31, 40]), \
             mock.patch.object(HELPER.os, 'kill') as kill, self.assertRaises(PermissionError):
            HELPER.kill_group(31, members=lambda group: rows)
        kill.assert_called_once_with(31, signal.SIGKILL)

    def test_unknown_membership_and_linux_zombie_denial_remain_errors(self):
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.os, 'getsid', return_value=31), \
             mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError), self.assertRaisesRegex(RuntimeError, 'cannot inspect'):
            HELPER.kill_group(31, members=mock.Mock(side_effect=RuntimeError('cannot inspect')))
        with mock.patch.object(HELPER.sys, 'platform', 'linux'), \
             mock.patch.object(HELPER.os, 'killpg', side_effect=PermissionError), self.assertRaises(PermissionError):
            HELPER.kill_group(31, members=lambda group: [])

    def test_darwin_sweeps_only_revalidated_members_after_killpg_success_or_esrch(self):
        rows = [{'pid': pid, 'state': state} for pid, state in [(32, 'S'), (33, 'R'), (34, 'S'), (35, 'Z+')]]
        for outcome in (None, ProcessLookupError):
            with self.subTest(killpg=outcome), mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
                 mock.patch.object(HELPER.os, 'killpg', side_effect=outcome) as killpg, \
                 mock.patch.object(HELPER.os, 'getsid', side_effect=[31, 31, 40, ProcessLookupError]) as sid, \
                 mock.patch.object(HELPER.os, 'kill') as kill:
                HELPER.kill_group(31, members=lambda group: rows)
            killpg.assert_called_once_with(31, signal.SIGKILL)
            self.assertEqual(sid.call_args_list, [mock.call(pid) for pid in (31, 32, 33, 34)])
            kill.assert_called_once_with(32, signal.SIGKILL)

    def test_darwin_never_signals_a_reassigned_leader_or_group(self):
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.os, 'getsid', return_value=40), \
             mock.patch.object(HELPER.os, 'killpg') as killpg, mock.patch.object(HELPER.os, 'kill') as kill:
            HELPER.kill_group(31, members=lambda group: [{'pid': 31, 'state': 'S'}])
        killpg.assert_not_called()
        kill.assert_not_called()

    def test_darwin_unverified_leader_remains_an_error_even_without_live_rows(self):
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.os, 'getsid', side_effect=PermissionError('leader identity')), \
             mock.patch.object(HELPER.os, 'killpg') as killpg:
            with self.assertRaisesRegex(PermissionError, 'leader identity'):
                HELPER.kill_group(31, members=lambda group: [])
        killpg.assert_not_called()

    def test_darwin_reports_worker_denial_after_trying_every_enrolled_worker(self):
        rows = [{'pid': pid, 'state': 'S'} for pid in (32, 33, 34)]
        with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
             mock.patch.object(HELPER.os, 'killpg'), \
             mock.patch.object(HELPER.os, 'getsid', side_effect=[31, PermissionError('worker identity'), 31, 31]), \
             mock.patch.object(HELPER.os, 'kill', side_effect=[PermissionError('worker signal'), None]) as kill:
            with self.assertRaisesRegex(PermissionError, 'worker identity'):
                HELPER.kill_group(31, members=lambda group: rows)
        self.assertEqual(kill.call_args_list, [mock.call(pid, signal.SIGKILL) for pid in (33, 34)])

    def test_linux_still_returns_without_inventory_after_killpg_success_or_esrch(self):
        for outcome in (None, ProcessLookupError):
            inventory = mock.Mock()
            with self.subTest(killpg=outcome), mock.patch.object(HELPER.sys, 'platform', 'linux'), \
                 mock.patch.object(HELPER.os, 'killpg', side_effect=outcome) as killpg, \
                 mock.patch.object(HELPER.os, 'getsid') as session, mock.patch.object(HELPER.os, 'kill') as kill:
                HELPER.kill_group(31, members=inventory)
            killpg.assert_called_once_with(31, signal.SIGKILL)
            session.assert_not_called()
            kill.assert_not_called()
            inventory.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'Darwin killpg exit race')
    def test_owned_unreaped_zombie_is_handled_on_darwin(self):
        child = subprocess.Popen(['/usr/bin/true'], start_new_session=True)
        try:
            deadline = time.monotonic() + 2
            while not any(row['state'].startswith('Z') for row in HELPER.process_group(child.pid)):
                self.assertLess(time.monotonic(), deadline, 'child did not become a zombie')
                time.sleep(.005)
            HELPER.kill_group(child.pid)
        finally:
            self.assertEqual(child.wait(timeout=2), 0)


@unittest.skipUnless(sys.platform in ('linux', 'darwin') and Path('/bin/ps').is_file(),
                     'requires POSIX sessions and ps')
class EnrolledSessionTermination(unittest.TestCase):
    SCRIPT = '''import os, sys, time
r, w = os.pipe()
worker = os.fork()
if worker == 0:
    os.close(r)
    os.setpgid(0, 0)
    os.write(w, b'R')
    os.close(w)
    time.sleep(15)
    os._exit(0)
os.close(w)
if os.read(r, 1) != b'R':
    raise RuntimeError('worker startup failed')
os.close(r)
print(worker, flush=True)
if sys.argv[1] == 'False':
    os.waitpid(worker, 0)
'''

    def run_session(self, exit_early):
        # Use real processes, process groups, ps, and signals. Exercise the
        # Darwin cleanup branch on Linux too without claiming a real Mac run.
        linux = sys.platform == 'linux'
        if linux:
            import ctypes
            prctl = ctypes.CDLL(None).prctl
            previous = ctypes.c_int()
            self.assertEqual(prctl(37, ctypes.byref(previous), 0, 0, 0), 0)  # PR_GET_CHILD_SUBREAPER
            self.assertEqual(prctl(36, 1, 0, 0, 0), 0)  # PR_SET_CHILD_SUBREAPER
            self.addCleanup(prctl, 36, previous.value, 0, 0, 0)
        def stop(child):
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)

        def reap(pid):
            deadline = time.monotonic() + 3
            while True:
                reaped, status = os.waitpid(pid, os.WNOHANG)
                if reaped:
                    return os.waitstatus_to_exitcode(status)
                self.assertLess(time.monotonic(), deadline, 'session worker did not exit')
                time.sleep(0.01)

        unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(15)'], start_new_session=True)
        self.addCleanup(stop, unrelated)
        leader = subprocess.Popen([sys.executable, '-c', self.SCRIPT, str(exit_early)],
                                  start_new_session=True, stdout=subprocess.PIPE, text=True)
        self.addCleanup(stop, leader)
        with leader.stdout as ready:
            self.assertTrue(select.select([ready], [], [], 4)[0], 'session fixture did not become ready')
            worker = int(ready.readline())
        try:
            self.assertEqual(os.getpgid(worker), worker)
            self.assertEqual(os.getsid(worker), leader.pid)
            self.assertNotEqual(os.getsid(unrelated.pid), leader.pid)
            if exit_early:
                self.assertEqual(leader.wait(timeout=3), 0)
                with self.assertRaises(ProcessLookupError):
                    os.killpg(leader.pid, 0)
            with mock.patch.object(HELPER.sys, 'platform', 'darwin'), \
                 mock.patch.object(HELPER.os, 'killpg', wraps=os.killpg) as killpg, \
                 mock.patch.object(HELPER.os, 'kill', wraps=os.kill) as kill:
                HELPER.kill_group(leader.pid)
            self.assertEqual(killpg.call_args_list, [] if exit_early else [mock.call(leader.pid, signal.SIGKILL)])
            self.assertIn(mock.call(worker, signal.SIGKILL), kill.call_args_list)
            self.assertFalse(any(call.args[0] == unrelated.pid for call in kill.call_args_list))
            self.assertIsNone(unrelated.poll())
            self.assertEqual(leader.wait(timeout=3), 0 if exit_early else -signal.SIGKILL)
            if linux:
                status = reap(worker)
                worker = None
                self.assertEqual(status, -signal.SIGKILL)
            else:
                deadline = time.monotonic() + 3
                while HELPER.live_group_members(leader.pid, HELPER.process_group):
                    self.assertLess(time.monotonic(), deadline, 'session worker did not exit')
                    time.sleep(0.01)
        finally:
            stop(leader)
            if worker is not None:
                try:
                    if os.getsid(worker) == leader.pid:
                        os.kill(worker, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                if linux:
                    reap(worker)

    def test_split_worker_does_not_survive_successful_original_group_signal(self):
        self.run_session(exit_early=False)

    def test_split_worker_does_not_survive_vanished_original_group(self):
        self.run_session(exit_early=True)


class RunnerAccounting(unittest.TestCase):
    def run_mock(self, platform, terminal=None, sampled_overflow=False, wait_status=0,
                 group_replies=None, kill_error=None, kill_member=None, refuse_wait=False):
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
                if refuse_wait:
                    assert timeout is not None and timeout <= 5, 'cleanup wait must be bounded'
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
                assert not refuse_wait, 'cannot join an unreaped child'
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
                process_groups.side_effect = [[{'pid': 321, 'state': 'R', 'rss': 5121}], [], []]
            elif terminal:
                process_groups.side_effect = [terminal, [], []]
            if group_replies is not None:
                process_groups.side_effect = group_replies
            stack.enter_context(mock.patch.object(HELPER.threading, 'Event', Event))
            stack.enter_context(mock.patch.object(HELPER.threading, 'Thread', Thread))
            stack.enter_context(mock.patch.object(HELPER.subprocess, 'Popen', side_effect=popen))
            stack.enter_context(mock.patch.object(HELPER.os, 'wait4', return_value=(321, wait_status, usage)))
            setrlimit = stack.enter_context(mock.patch.object(HELPER.resource, 'setrlimit'))
            stack.enter_context(mock.patch.object(HELPER.os, 'getsid', return_value=321))
            stack.enter_context(mock.patch.object(HELPER.os, 'kill', new=kill_member or mock.Mock()))
            killpg = stack.enter_context(mock.patch.object(HELPER.os, 'killpg'))
            killpg.side_effect = kill_error
            failure = None
            try:
                HELPER.Runner(root, limits).run(['mock-compiler'], root, root / 'command', timed=True)
            except (RuntimeError, OSError) as error:
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

    def test_darwin_rechecks_survivors_after_individual_kill_and_fails_closed(self):
        live = [{'pid': 322, 'state': 'R', 'rss': 8}]
        for remains, denial in [([], None), (live, None), (live, PermissionError('worker signal denied'))]:
            with self.subTest(remains=remains, denial=denial), \
                 mock.patch.object(HELPER.time, 'monotonic', side_effect=[0, 1, 2, 7]), \
                 mock.patch.object(HELPER.time, 'sleep'):
                kill = mock.Mock(side_effect=denial)
                receipt, _, _, failure = self.run_mock('darwin', group_replies=[live, live, remains],
                                                       kill_member=kill)
            kill.assert_called_once_with(322, signal.SIGKILL)
            self.assertFalse(receipt['complete'])
            self.assertTrue(receipt['child_reaped'])
            self.assertEqual(receipt['exit_code'], 0)
            self.assertEqual(receipt['terminal_live_descendants'], live)
            self.assertEqual(receipt['remaining_live_after_cleanup'], remains)
            self.assertEqual(receipt['reason'], 'live descendants after leader completion')
            if remains:
                self.assertIn('live group members remain', ' '.join(receipt['supervision_errors']))
            else:
                self.assertNotIn('supervision_errors', receipt)
            if denial:
                self.assertIs(failure, denial)
            else:
                self.assertIsInstance(failure, RuntimeError)

    def test_sampled_overflow_kills_but_does_not_claim_hard_address_cap(self):
        receipt, limits, kills, failure = self.run_mock('darwin', sampled_overflow=True, wait_status=9)
        self.assertIsNotNone(failure)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['reason'], 'process-tree RSS limit')
        self.assertEqual(receipt['sampled_process_tree_peak_rss_bytes'], 5121)
        self.assertEqual(limits, [])
        self.assertEqual(kills, [mock.call(321, signal.SIGKILL)])

    def test_terminal_zombie_race_keeps_wait4_result_and_original_guard(self):
        busy = [{'pid': 321, 'state': 'R', 'rss': 5121}]
        zombie = [{'pid': 321, 'state': 'Z+', 'rss': 0}]
        receipt, _, _, failure = self.run_mock('darwin', sampled_overflow=True, wait_status=9,
            group_replies=[busy, zombie, []], kill_error=PermissionError('gone'))
        self.assertIsNotNone(failure)
        self.assertTrue(receipt['child_reaped'])
        self.assertEqual(receipt['exit_code'], -9)
        self.assertEqual(receipt['reason'], 'process-tree RSS limit')
        self.assertEqual(receipt['terminal_live_descendants'], [])
        self.assertNotIn('supervision_errors', receipt)

    def test_successful_darwin_leader_with_exiting_descendant(self):
        exiting = [{'pid': 322, 'state': '?NEs+', 'rss': 0}]
        with mock.patch.object(HELPER.time, 'sleep'):
            receipt, _, kills, failure = self.run_mock('darwin', group_replies=[exiting, []])
        self.assertIsNone(failure)
        self.assertTrue(receipt['complete'])
        self.assertEqual(receipt['terminal_live_descendants'], [])
        self.assertEqual(kills, [])

    def test_guarded_darwin_exiting_descendant_vanishes_after_wait4(self):
        busy = [{'pid': 321, 'state': 'R', 'rss': 5121}]
        exiting = [{'pid': 322, 'state': '?E', 'rss': 0}]
        with mock.patch.object(HELPER.time, 'sleep'):
            receipt, _, kills, failure = self.run_mock('darwin', sampled_overflow=True, wait_status=9,
                group_replies=[busy, exiting, exiting, [], []])
        self.assertIsInstance(failure, RuntimeError)
        self.assertEqual(kills, [mock.call(321, signal.SIGKILL)])
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['reason'], 'process-tree RSS limit')
        self.assertEqual(receipt['sampled_process_tree_peak_rss_bytes'], 5121)
        self.assertTrue(receipt['child_reaped'])
        self.assertEqual(receipt['exit_code'], -9)
        self.assertEqual(receipt['terminal_live_descendants'], [])
        self.assertNotIn('supervision_errors', receipt)

    def test_terminal_inspection_error_keeps_wait4_and_guard(self):
        busy = [{'pid': 321, 'state': 'R', 'rss': 5121}]
        receipt, _, _, failure = self.run_mock('darwin', sampled_overflow=True, wait_status=9,
            group_replies=[busy, [], PermissionError('cannot inspect'), []])
        self.assertIsInstance(failure, PermissionError)
        self.assertFalse(receipt['complete'])
        self.assertTrue(receipt['child_reaped'])
        self.assertEqual(receipt['exit_code'], -9)
        self.assertEqual(receipt['reason'], 'process-tree RSS limit')
        self.assertIn('cannot inspect', receipt['supervision_errors'][0])

    def test_no_unbounded_wait_when_child_cannot_be_reaped(self):
        busy = [{'pid': 321, 'state': 'R', 'rss': 5121}]
        receipt, _, _, failure = self.run_mock('darwin', sampled_overflow=True, refuse_wait=True,
                                               group_replies=[busy, [], []])
        self.assertIsInstance(failure, RuntimeError)
        self.assertFalse(receipt['complete'])
        self.assertFalse(receipt['child_reaped'])
        self.assertNotIn('exit_code', receipt)
        self.assertEqual(receipt['process_group'], 321)
        self.assertEqual(receipt['reason'], 'process-tree RSS limit')
        self.assertIn('did not exit', receipt['supervision_errors'][0])

    def test_nonzero_child_is_not_a_success(self):
        receipt, _, _, failure = self.run_mock('linux', wait_status=3 << 8)
        self.assertIsNotNone(failure)
        self.assertFalse(receipt['complete'])
        self.assertEqual(receipt['exit_code'], 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
