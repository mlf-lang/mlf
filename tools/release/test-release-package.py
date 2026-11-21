#!/usr/bin/env python3
"""Report a release manifest's actual package-manager test rows without publishing."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'testing'))
import events

PREFIX = 'release/package-target/'


def file_identity(path):
    if not path.is_file():
        return None
    status = path.stat()
    return status.st_ino, status.st_mtime_ns, status.st_size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('MLF_COMPILER'))
    parser.add_argument('--manager', default=os.environ.get('MLF_PACKAGE_MANAGER'))
    parser.add_argument('--build-dir', type=Path, default=Path('.mlf-build/package-export'))
    parser.add_argument('--framework-list', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    manifest = args.manifest.resolve(strict=True)
    tests = json.loads(manifest.read_text(encoding='utf-8')).get('tests', {})
    if not isinstance(tests, dict) or not tests or not all(
        isinstance(name, str) and re.fullmatch(r'[a-z][a-z0-9-]*', name) for name in tests
    ):
        parser.error('specify a manifest with package test targets')
    exact = os.environ.get('MLF_TEST_EXACT')
    if exact:
        name = exact.removeprefix(PREFIX)
        if name not in tests or PREFIX + name != exact:
            parser.error('unknown package test target: ' + exact)
        tests = {name: tests[name]}
    ids = [PREFIX + name for name in tests]
    if args.framework_list:
        print(json.dumps(ids))
        return 0
    if not args.manager or not args.compiler:
        parser.error('provide a native package manager and compiler')
    events.plan(ids)

    build_dir = args.build_dir.resolve()
    receipt = build_dir / 'build-report.json'
    previous = file_identity(receipt)
    command = [
        args.manager, '--manifest', str(manifest), '--compiler', args.compiler,
        '--build-dir', str(build_dir), '--locked', 'test',
    ]
    if exact:
        command.extend(('--target', name))
    outcome = subprocess.run(command, check=False)
    current = file_identity(receipt)
    if current is None or current == previous:
        print('package test adapter: no fresh build receipt', file=sys.stderr)
        return outcome.returncode or 1

    raw = receipt.read_bytes()
    event_path = os.environ.get('MLF_TEST_EVENTS')
    retained = Path(event_path).with_suffix('.package-manager.json') if event_path else receipt
    if retained != receipt:
        # A following release export can overwrite build-report.json in this build directory.
        retained.write_bytes(raw)
    evidence = json.loads(raw)
    if evidence.get('format') != 1 or evidence.get('implementation') != 'MLF':
        raise ValueError('invalid package-manager build receipt')
    rows = evidence.get('tests')
    if not isinstance(rows, list):
        raise ValueError('invalid package-manager test rows')
    for row in rows:
        if row['name'] not in tests or row.get('passed') is not True:
            raise ValueError('unexpected package-manager test row')
        events.result(PREFIX + row['name'], 'pass', detail=row, receipt=str(retained))
    if outcome.returncode:
        return outcome.returncode
    return 0 if evidence.get('complete') is True and len(rows) == len(ids) else 1


if __name__ == '__main__':
    try:
        status = main() or 0
        sys.exit(status if status >= 0 else 128 - status)
    except (OSError, ValueError, KeyError, TypeError) as error:
        sys.exit(str(error))
