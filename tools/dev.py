#!/usr/bin/env python3
"""Build, test, and benchmark this checkout with the project's existing tools."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from developer.process import run_build


ROOT = Path(__file__).resolve().parents[1]
SHAPES = ROOT / 'tools/performance/compiler-shapes'
NATIVE_COMPARISON = ROOT / 'tools/performance/llvm-memory/compare_native.py'
TEST_RUNNER = ROOT / 'tools/testing/run.py'


def launch(argv):
    """Replace the launcher on POSIX so the selected tool receives signals directly."""
    command = list(map(str, argv))
    if os.name == 'nt':
        return subprocess.call(command)
    os.execv(command[0], command)


def manager():
    if os.name == 'nt':
        return [os.environ.get('MLF_PACKAGE_MANAGER')
                or ROOT / '.mlf-build/windows-package-tools/bin/mlfpkg.exe']
    return [ROOT / 'mlfpkg']


def python(script, *args):
    return [sys.executable, '-B', script, *args]


def package(args):
    options = ['--locked'] if args.action == 'build' else []
    if args.jobs is not None:
        options += ['--jobs', str(args.jobs)]
    if args.timeout is not None:
        options += ['--timeout', str(args.timeout)]
    if args.build_dir:
        options += ['--build-dir', args.build_dir]
    targets = [arg for name in args.target for arg in ('--target', name)]
    return launch([*manager(), *options, args.action, *targets])


def applications(args):
    clang = shutil.which(args.clang)
    if not clang:
        raise SystemExit(f'Clang executable not found: {args.clang}')
    candidate = args.candidate.resolve(strict=True)
    baseline = args.baseline.resolve(strict=True)
    if args.check_only and args.workload:
        raise SystemExit('--check-only runs all application workloads')
    # mlfpkg run changes to the manifest directory. The native benchmark reads
    # benchmarks/manifest.json and its pinned workload sources from the repo root.
    build = [*manager(), '--manifest', 'tools/bench/mlf-package.json', '--compiler', candidate,
             '--clang', clang, '--runtime', ROOT / 'runtime/mlf_runtime.c', '--build-dir', args.driver_dir,
             '--timeout', '21600', 'build', '--target', 'bench']
    status = run_build(build, ROOT)
    if status:
        return status
    driver = args.driver_dir.resolve() / 'bin' / ('bench.exe' if os.name == 'nt' else 'bench')
    options = ['--check-only'] if args.check_only else [args.compile_limit, args.runtime_limit, *args.workload]
    return launch([driver, candidate, baseline, args.output, str(args.samples), clang, *options])


def check_tools(args):
    suites = ['release-developer-commands', 'release-developer-process']
    if sys.platform in ('linux', 'darwin'):
        suites.extend(('compiler-shapes-contract', 'compiler-shapes-sweep',
                       'compiler-shapes-cancellation', 'compiler-shapes-data-shapes',
                       'compiler-shapes-rank-shapes', 'compiler-shapes-fit-growth'))
    elif not args.suite:
        print('The compiler-shape harness is tested on macOS and Linux.', flush=True)
    if args.suite:
        if args.suite not in suites:
            raise SystemExit(f'Unknown check-tools suite for this host: {args.suite}')
        suites = [args.suite]
    elif args.exact:
        raise SystemExit('--exact requires --suite')
    options = ['--list'] if args.list else []
    if args.exact:
        options.extend(('--exact', args.exact))
    for suite in suites:
        # The cancellation tests run their own supervised process groups. Give
        # their supervisors time to finish cleanup before killing the suite.
        status = run_build(python(ROOT / 'tools/testing/run.py', '--inherit-process-group', suite, *options),
                           ROOT, cancellation_grace=2)
        if status:
            return status


def main(argv):
    os.chdir(ROOT)
    if argv[:1] == ['build-host']:
        return launch(python(ROOT / 'tools/shared/build.py', *argv[1:]))
    if argv[:2] == ['bench', 'compiler']:
        if any(flag in argv[2:] for flag in ('-h', '--help')):
            return launch(python(NATIVE_COMPARISON, *argv[2:]))
        return launch(python(TEST_RUNNER, 'full-compiler-native-comparison', '--', *argv[2:]))
    if argv[:2] == ['bench', 'shapes']:
        if len(argv) > 2 and argv[2] in ('list', 'growth'):
            return launch(python(SHAPES / 'bench.py', *argv[2:]))
        if any(flag in argv[2:] for flag in ('-h', '--help')):
            return launch(python(SHAPES / 'bench.py', 'sweep', *argv[2:]))
        return launch(python(TEST_RUNNER, 'compiler-shapes', '--', 'sweep', *argv[2:]))
    if argv[:3] == ['bench', 'apps', '--framework-list']:
        return launch(python(ROOT / 'tools/bench/framework_inventory.py', *argv[3:]))

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    for name, help_text in [('build', 'build the locked package'), ('test', 'run native package tests')]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument('--target', action='append', default=[], help='package target (repeatable)')
        command.add_argument('--jobs', type=int, help='maximum concurrent build actions')
        command.add_argument('--build-dir', type=Path, help='package output/cache directory')
        command.add_argument('--timeout', type=int, default=21600 if name == 'test' else None,
                             help='timeout per build action, in seconds')
    commands.add_parser('build-host', help='GHC-hosted build (see build-host --help)')
    tools = commands.add_parser('check-tools', help='test developer commands and benchmark support')
    tools.add_argument('--suite', help='select a registered developer or shape suite')
    tools.add_argument('--list', action='store_true', help='list selected case IDs')
    tools.add_argument('--exact', help='select one case in the chosen suite')
    bench = commands.add_parser('bench', help='compare compiler builds or benchmark native applications')
    suites = bench.add_subparsers(dest='suite', required=True)
    suites.add_parser('compiler', help='compare fresh full compiler builds by GHC and GHC-hosted MLF')
    suites.add_parser('shapes', help='run the paired compiler sweep, or use shapes list or growth')
    apps = suites.add_parser('apps', help='run the native candidate / baseline / C comparison')
    apps.add_argument('--candidate', type=Path, default=ROOT / '.mlf-build/bin/emlf',
                      help='candidate compiler (default: .mlf-build/bin/emlf)')
    apps.add_argument('--baseline', required=True, type=Path, help='comparison compiler')
    apps.add_argument('--output', type=Path, required=True, help='fresh native benchmark output directory')
    apps.add_argument('--driver-dir', type=Path, default=ROOT / '.mlf-build/native-bench-driver')
    apps.add_argument('--clang', default=os.environ.get('CLANG') or 'clang')
    apps.add_argument('--samples', type=int, default=3, help='odd sample count, at least three')
    apps.add_argument('--compile-limit', default='3', help='native compilation ratio limit')
    apps.add_argument('--runtime-limit', default='2', help='native runtime ratio limit')
    apps.add_argument('--workload', action='append', default=[], help='select workloads (repeatable)')
    apps.add_argument('--check-only', action='store_true', help='run the native correctness checks')
    args = parser.parse_args(argv)
    if args.action in ('build', 'test'):
        return package(args)
    if args.action == 'check-tools':
        return check_tools(args)
    if os.environ.get('MLF_TEST_SUITE') == 'application-benchmarks':
        return applications(args)
    return launch(python(TEST_RUNNER, 'application-benchmarks', '--', *argv[2:]))


if __name__ == '__main__':
    try:
        status = main(sys.argv[1:]) or 0
        sys.exit(status if status >= 0 else 128 - status)
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(str(exc))
