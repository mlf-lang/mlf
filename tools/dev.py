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


def check_tools():
    scripts = [ROOT / 'tools/developer/test_commands.py', ROOT / 'tools/developer/test_process.py']
    if sys.platform in ('linux', 'darwin'):
        scripts.extend(SHAPES / name for name in (
            'test_contract.py', 'test_sweep.py', 'test_cancellation.py',
            'test_data_shapes.py', 'test_rank_shapes.py',
        ))
    else:
        print('The compiler-shape harness is tested on macOS and Linux.', flush=True)
    for script in scripts:
        # The cancellation tests run their own supervised process groups. Give
        # their supervisors time to finish cleanup before killing the suite.
        status = run_build(python(script), ROOT, cancellation_grace=2)
        if status:
            return status


def main(argv):
    os.chdir(ROOT)
    if argv[:1] == ['build-host']:
        return launch(python(ROOT / 'tools/shared/build.py', *argv[1:]))
    if argv[:2] == ['bench', 'shapes']:
        if argv[2:3] == ['list']:
            return launch(python(SHAPES / 'bench.py', 'list', *argv[3:]))
        return launch(python(SHAPES / 'bench.py', 'sweep', *argv[2:]))

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
    commands.add_parser('check-tools', help='test the developer commands and compiler benchmark harness')
    bench = commands.add_parser('bench', help='compile shapes against GHC or benchmark native applications')
    suites = bench.add_subparsers(dest='suite', required=True)
    suites.add_parser('shapes', help='run the paired compiler sweep, or use shapes list')
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
        return check_tools()
    return applications(args)


if __name__ == '__main__':
    try:
        status = main(sys.argv[1:]) or 0
        sys.exit(status if status >= 0 else 128 - status)
    except KeyboardInterrupt:
        sys.exit(130)
    except OSError as exc:
        sys.exit(str(exc))
