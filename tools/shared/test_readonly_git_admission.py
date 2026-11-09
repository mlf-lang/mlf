"""Revision-02 argv/denial controls only. No real Git or configured hook runs."""
import contextlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('completion_controls_r2', HERE / 'test_completed_result.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
b, p = c.b, c.p


class GitAdmissionControls(unittest.TestCase):
    head = 'a' * 40
    keys = 'core.repositoryformatversion\0core.filemode\0core.bare\0core.logallrefupdates\0core.fsmonitor\0'
    index = '100644 ' + 'b' * 40 + ' 0\tfixture.hs\0'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=HERE.parents[1])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / '.git'
        (self.directory / 'objects/pack').mkdir(parents=True)
        for name, text in [('HEAD', self.head + '\n'), ('config', '# SYNTHETIC CONFIG\n'),
                           ('index', 'SYNTHETIC INDEX; mocked mode listing only')]:
            (self.directory / name).write_text(text)

    def invoke(self, module, *, keys=None, index=None, readonly=True, error=None):
        values = [str(self.root), self.head, '']
        if readonly:
            values = [self.keys if keys is None else keys, self.index if index is None else index, *values]
        env = {'LANG': 'C', 'LD_PRELOAD': '/fixture/not-loaded', 'GIT_CONFIG_COUNT': '1',
               'GIT_CONFIG_KEY_0': 'filter.evil.clean', 'GIT_CONFIG_VALUE_0': '/fixture/not-executed',
               'GIT_DIR': '/wrong', 'GIT_WORK_TREE': '/wrong', 'GIT_INDEX_FILE': '/wrong',
               'GIT_EXTERNAL_DIFF': '/fixture/not-executed', 'GIT_PAGER': '/fixture/not-executed'}
        with mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('real process forbidden')), \
                mock.patch.object(module.subprocess, 'check_output', side_effect=values) as query, \
                mock.patch.object(module, 'sha', return_value='c' * 64):
            context = self.assertRaisesRegex(ValueError, error) if error else contextlib.nullcontext()
            with context:
                if module is b:
                    module.source_checkpoint(self.root, Path('/fixture/git'), env, self.head, True, read_only=readonly)
                else:
                    module.checkpoint(self.root, self.head, '/fixture/git', env, read_only=readonly)
        return query.call_args_list

    def test_both_paths_admit_keys_and_modes_before_status(self):
        for module in (b, p):
            calls = self.invoke(module)
            self.assertEqual(len(calls), 5)
            self.assertIn('config', calls[0].args[0])
            self.assertEqual(calls[0].args[0][-6:], ['config', '--local', '--no-includes', '--name-only', '--null', '--list'])
            self.assertEqual(calls[1].args[0][-3:], ['ls-files', '--stage', '-z'])
            self.assertEqual(calls[-1].args[0][-3:], ['status', '--porcelain', '--untracked-files=normal'])
            for call in calls:
                argv, env = call.args[0], call.kwargs['env']
                self.assertIn('--no-pager', argv)
                self.assertIn('--no-optional-locks', argv)
                self.assertIn('core.fsmonitor=false', argv)
                self.assertIn('core.untrackedCache=false', argv)
                self.assertNotIn('--ignore-submodules', ' '.join(argv))
                self.assertEqual(env['GIT_OPTIONAL_LOCKS'], '0')
                self.assertEqual(env['GIT_NO_LAZY_FETCH'], '1')
                self.assertEqual(env['GIT_CONFIG_NOSYSTEM'], '1')
                self.assertEqual(env['GIT_CONFIG_GLOBAL'], '/dev/null')
                self.assertFalse({'LD_PRELOAD', 'GIT_DIR', 'GIT_INDEX_FILE', 'GIT_PAGER',
                                  'GIT_CONFIG_COUNT', 'GIT_EXTERNAL_DIFF'} & set(env))
                self.assertEqual(call.kwargs['stderr'], subprocess.DEVNULL)
                self.assertEqual(call.kwargs['timeout'], 15)

    def test_external_filter_and_complex_keys_stop_before_index_and_status(self):
        keys = ['filter.fixture.clean', 'filter.fixture.process', 'include.path',
                'includeif.gitdir:/private/url.path', 'extensions.worktreeconfig',
                'extensions.partialclone', 'extensions.objectformat', 'remote.origin.promisor',
                'core.hookspath', 'core.worktree', 'core.sparsecheckout',
                'http.https://fixture-private/.extraheader', 'unknown.private.setting']
        for module in (b, p):
            for key in keys:
                with self.subTest(module=module.__name__, key_kind=key.split('.')[0]):
                    calls = self.invoke(module, keys=self.keys + key + '\0', error='unsupported configuration key')
                    self.assertEqual(len(calls), 1)

    def test_known_remote_branch_and_user_keys_are_argv_fixtures_only(self):
        keys = self.keys + 'remote.origin.url\0remote.origin.fetch\0branch.main.remote\0branch.main.merge\0user.name\0user.email\0'
        for module in (b, p):
            self.assertEqual(len(self.invoke(module, keys=keys)), 5)

    def test_gitlink_and_conflict_stop_before_any_status(self):
        for module in (b, p):
            for index in ['160000 ' + 'd' * 40 + ' 0\tsubmodule\0',
                          '100644 ' + 'd' * 40 + ' 2\tconflict\0',
                          '040000 ' + 'd' * 40 + ' 0\tsparse-directory\0']:
                calls = self.invoke(module, index=index, error='read-only Git')
                self.assertEqual(len(calls), 2)

    def test_config_and_index_framing_fail_closed(self):
        for module in (b, p):
            self.assertEqual(len(self.invoke(module, keys='core.filemode', error='key framing')), 1)
            self.assertEqual(len(self.invoke(module, index=self.index.rstrip('\0'), error='index framing')), 2)

    def test_shared_and_partial_metadata_rejected_without_git(self):
        for name in ('commondir', 'config.worktree', 'objects/info/alternates',
                     'objects/info/http-alternates', 'objects/pack/fixture.promisor'):
            target = self.directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('SYNTHETIC UNSUPPORTED METADATA')
            try:
                for module in (b, p):
                    self.assertEqual(len(self.invoke(module, error='read-only Git')), 0)
            finally:
                target.unlink()

    def test_gitfile_and_metadata_alias_rejected_without_git(self):
        config = self.directory / 'config'
        saved = self.directory / 'saved-config'
        config.rename(saved)
        config.symlink_to(saved)
        for module in (b, p):
            self.assertEqual(len(self.invoke(module, error='metadata must be local regular')), 0)
        config.unlink(); saved.rename(config)
        saved_directory = self.root / 'git-storage'
        self.directory.rename(saved_directory)
        self.directory.write_text('gitdir: ' + str(saved_directory) + '\n')
        for module in (b, p):
            self.assertEqual(len(self.invoke(module, error='gitfiles/worktrees')), 0)

    def test_rejected_key_is_not_echoed(self):
        key = 'filter.private-URL-or-secret.clean'
        with mock.patch.object(subprocess, 'check_output', return_value=key + '\0'):
            for module in (b, p):
                with self.assertRaises(ValueError) as caught:
                    module._readonly_git_context(self.root, Path('/fixture/git'))
                self.assertNotIn(key, str(caught.exception))
                self.assertNotIn('private-URL', str(caught.exception))

    def test_original_default_argv_has_no_new_admission_or_overrides(self):
        for module in (b, p):
            calls = self.invoke(module, readonly=False)
            self.assertEqual(len(calls), 3)
            for call in calls:
                self.assertEqual(call.args[0][:5], ['/fixture/git', '-c', 'core.preloadIndex=false', '-c', 'index.threads=1'])
                self.assertNotIn('--no-pager', call.args[0])
                self.assertNotIn('core.fsmonitor=false', call.args[0])
                self.assertEqual(call.kwargs['env']['LD_PRELOAD'], '/fixture/not-loaded')


class GitPinBeforeExecutionControls(unittest.TestCase):
    def setUp(self):
        self.fixture = c.CompletedControls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def reject_before_git(self):
        f = self.fixture
        with mock.patch.object(b, 'source_checkpoint', side_effect=AssertionError('checkpoint ran before pin')) as checkpoint, \
                mock.patch.object(subprocess, 'Popen', side_effect=AssertionError('real process forbidden')), \
                mock.patch.object(subprocess, 'check_output', side_effect=AssertionError('real Git forbidden')):
            with self.assertRaisesRegex(ValueError, 'original Git'):
                b.authenticate_completed(f.path, f.digest, **f.kwargs)
            self.assertEqual(checkpoint.call_count, 0)

    def test_changed_fixed_git_bytes_are_rejected_first(self):
        f = self.fixture; real_sha = b.sha
        with mock.patch.object(b, 'sha', side_effect=lambda path: 'f' * 64 if Path(path) == f.fixed_git else real_sha(path)):
            self.reject_before_git()

    def test_source_driver_must_share_original_git_pin(self):
        self.fixture.receipt['checkpoints']['driver']['git_sha256'] = 'e' * 64
        self.fixture.seal()
        self.reject_before_git()

    def test_fixed_path_cannot_be_replaced_by_receipt_tool(self):
        self.fixture.receipt['checkpoints']['source']['git'] = '/fixture/substitute-git'
        self.fixture.seal()
        self.reject_before_git()

    def test_missing_original_input_pin_does_not_run_git(self):
        del self.fixture.receipt['inputs'][str(self.fixture.fixed_git)]
        self.fixture.seal()
        self.reject_before_git()


if __name__ == '__main__':
    unittest.main()
