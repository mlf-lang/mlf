#!/usr/bin/env python3
"""Build an executable and print the compiler's native build receipt."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', required=True, type=Path)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('-i', '--include', action='append', default=[], type=Path)
    parser.add_argument('--no-prelude', action='store_true')
    parser.add_argument('-o', '--output', required=True, type=Path)
    parser.add_argument('--build-dir', type=Path, help='fresh directory for IR, objects, logs and receipt')
    parser.add_argument('--timeout', type=float, default=1800, help='maximum build time in seconds')
    args = parser.parse_args()
    command = [args.compiler.resolve(strict=True)]
    if args.no_prelude:
        command.append('--no-prelude')
    for include in args.include:
        command.extend(['-i', include.resolve(strict=True)])
    command.extend([args.source.resolve(strict=True), '-o', args.output.absolute()])
    if args.build_dir:
        command.extend(['--build-dir', args.build_dir.absolute()])

    # Leave dependency reporting and publication to the same compiler invocation
    # that selected and validated the objects. Preserve both of its output streams.
    process = subprocess.Popen(command, start_new_session=True)
    try:
        return process.wait(timeout=args.timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
