"""Developer entry point contracts. No compiler or released seed is required."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import dev


class DeveloperCommands(unittest.TestCase):
    def run_cli(self, *args, cwd=None, env=None):
        return subprocess.run(dev.python(dev.ROOT / 'tools/dev.py', *args), cwd=cwd, env=env,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_matrix_and_host_help_from_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            matrix = self.run_cli('bench', 'shapes', 'list', '--family', 'wide_case, state_updates',
                                  '--size', '8,32', cwd=tmp)
            host = self.run_cli('build-host', '--help', cwd=tmp)
        self.assertEqual(matrix.returncode, 0, matrix.stderr)
        self.assertIn('cells:    4, timed compilations: 48', matrix.stdout)
        self.assertEqual(host.returncode, 0, host.stderr)
        self.assertIn('--bootstrap-only', host.stdout)

    def test_native_arguments_use_package_manager_order(self):
        with mock.patch.object(dev, 'launch', side_effect=lambda argv: argv):
            self.assertEqual(dev.main(['build', '--jobs', '4', '--target', 'emlf']),
                             [*dev.manager(), '--locked', '--jobs', '4', 'build', '--target', 'emlf'])
            self.assertEqual(dev.main(['test', '--target', 'unit', '--target', 'packages']),
                             [*dev.manager(), '--timeout', '21600', 'test', '--target', 'unit',
                              '--target', 'packages'])

    @unittest.skipUnless(os.name == 'posix', 'POSIX native launcher')
    def test_native_failure_and_argument_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            probe = Path(tmp) / 'probe manager'
            probe.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 23\n')
            probe.chmod(0o755)
            result = self.run_cli('test', '--target', 'name with space', cwd=tmp,
                                  env={**os.environ, 'MLF_PACKAGE_MANAGER': str(probe)})
        self.assertEqual(result.returncode, 23)
        self.assertEqual(result.stdout.splitlines(), ['--timeout', '21600', 'test', '--target', 'name with space'])

    def test_app_driver_builds_then_runs_in_repo_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            compiler = directory / 'candidate compiler'
            compiler.touch()
            baseline = directory / 'baseline'
            baseline.touch()
            args = ['bench', 'apps', '--candidate', str(compiler), '--baseline', str(baseline),
                    '--output', str(directory / 'out'), '--driver-dir', str(directory / 'driver'),
                    '--clang', sys.executable, '--check-only']
            with mock.patch.dict(os.environ, {'MLF_TEST_SUITE': ''}), mock.patch.object(dev, 'launch') as launch:
                dev.main(args)
                self.assertEqual(launch.call_args.args[0],
                                 dev.python(dev.TEST_RUNNER, 'application-benchmarks', '--', *args[2:]))
            environment = {'MLF_TEST_SUITE': 'application-benchmarks'}
            with mock.patch.dict(os.environ, environment), \
                 mock.patch.object(dev, 'run_build', return_value=0) as build, mock.patch.object(dev, 'launch') as launch:
                dev.main(args)
            command, cwd = build.call_args.args
            self.assertEqual(cwd, dev.ROOT)
            self.assertEqual(command[-3:], ['build', '--target', 'bench'])
            self.assertEqual(command[command.index('--manifest') + 1], 'tools/bench/mlf-package.json')
            self.assertEqual(launch.call_args.args[0][1:4], [compiler.resolve(), baseline.resolve(), directory / 'out'])
            self.assertEqual(launch.call_args.args[0][-1], '--check-only')
            self.assertEqual(Path.cwd(), dev.ROOT)
            with mock.patch.dict(os.environ, environment), \
                 mock.patch.object(dev, 'run_build', return_value=9), mock.patch.object(dev, 'launch') as launch:
                self.assertEqual(dev.main(args), 9)
            launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
