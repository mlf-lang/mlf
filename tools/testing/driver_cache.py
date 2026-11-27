#!/usr/bin/env python3
"""Transfer the native driver cache entries identified by one preparation run."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile


FORMAT = 'mlf-test-driver-cache-v1'
OUTPUTS = {'llvm': 'program.ll', 'object': 'program.o', 'linked': 'program',
           'runtime': 'object.o', 'trace': 'object.o'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'invalid SHA-256')
    return value


def canonical(path):
    path = Path(path).absolute()
    try:
        resolved = path.resolve()
    except RuntimeError as exc:
        raise ValueError(f'symlink loop: {path}') from exc
    require(resolved == path, f'noncanonical or symlinked path: {path}')
    return path


def regular(path):
    path = canonical(path)
    require(path.is_file(), f'missing regular file: {path}')
    return path


def read(path, expected_hash=None):
    raw = regular(path).read_bytes()
    if expected_hash is not None:
        require(hashlib.sha256(raw).hexdigest() == digest(expected_hash), f'JSON digest mismatch: {path}')
    value = json.loads(raw)
    require(isinstance(value, dict), f'expected JSON object: {path}')
    return value


def sha(path):
    with regular(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def copy_entry(source, target, key, stamp_hash, receipt_files=None):
    """Validate the bytes at their destination before publishing the directory."""
    require(source.name == digest(key), 'artifact directory does not match key')
    target.mkdir()
    stamp = target / 'artifact.json'
    shutil.copyfile(regular(source / stamp.name), stamp)
    require(sha(stamp) == digest(stamp_hash), f'artifact stamp digest mismatch: {key}')
    metadata = read(stamp)
    files = metadata['files']
    require(metadata['key'] == key and isinstance(metadata['inputs'], dict), 'invalid artifact identity')
    require(isinstance(files, dict) and len(files) == 1 and set(files) <= set(OUTPUTS.values()),
            'unexpected driver artifact filename')
    require(receipt_files is None or files == receipt_files, 'driver receipt differs from stamp')
    for name, expected in files.items():
        dest = target / name
        shutil.copyfile(regular(source / name), dest)
        require(sha(dest) == digest(expected), f'artifact file digest mismatch: {key}/{name}')
        # Workflow artifact transport flattens executable permissions.
        dest.chmod(0o755 if name == 'program' else 0o644)


def export(report_path, output):
    report = read(report_path)
    require(report.get('complete') is True and report.get('scope') == 'preparation' and
            report.get('group') == 'backend-prepare', 'expected completed backend-prepare preparation')
    build_receipt = report['driver_build']
    build = read(build_receipt['path'], digest(build_receipt['sha256']))
    require(build.get('complete') is True and build.get('implementation') == 'MLF' and
            type(build.get('format')) is int and build['format'] == 1, 'expected completed manager driver build')
    cache = canonical(build['cache_directory'])
    require(set(report['drivers']) == {'RuntimeDriver', 'LLVMDriver'}, 'expected both native drivers')
    entries = {}
    for name, driver in report['drivers'].items():
        stages = driver['artifacts']
        expected = set(OUTPUTS) if name == 'RuntimeDriver' else set(OUTPUTS) - {'trace'}
        frontend = driver.get('frontend')
        require(frontend in ('source', 'crate') and set(stages) == expected,
                f'incomplete driver stages: {name}')
        for stage, row in stages.items():
            key = digest(row['key'])
            kind = {'llvm': f'{frontend} {name} LLVM', 'object': 'LLVM object',
                    'linked': 'test driver native link'}.get(stage, 'test driver C object')
            decision = {'key': key, 'kind': kind, 'cached': row['cached']}
            require(row['kind'] == kind and type(row['cached']) is bool and decision in build['builds'],
                    f'missing matching driver build decision: {name}/{stage}')
            files = row['files']
            require(row['directory'] == str(cache / key) and set(files) == {OUTPUTS[stage]},
                    f'driver artifact path or outputs differ: {name}/{stage}')
            if stage in ('linked', 'llvm'):
                require(files[OUTPUTS[stage]] == driver['sha256' if stage == 'linked' else 'llvm_sha256'],
                        f'driver output digest differs: {name}/{stage}')
            entry = (digest(row['artifact_sha256']), files)
            require(key not in entries or entries[key] == entry, f'conflicting receipts: {key}')
            entries[key] = entry

    output = canonical(output)
    require(not output.exists(), f'choose a fresh snapshot directory: {output}')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent) as tmp:
        staged = Path(tmp) / 'snapshot'
        staged.mkdir()
        for key, (stamp_hash, files) in entries.items():
            copy_entry(cache / key, staged / key, key, stamp_hash, files)
        manifest = {'format': FORMAT, 'artifacts': {k: h for k, (h, _) in entries.items()}}
        (staged / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True) + '\n')
        staged.rename(output)
    return {'exported': len(entries)}


def restore(snapshot, cache):
    cache = canonical(cache)
    cache.mkdir(parents=True, exist_ok=True)
    result = {'imported': [], 'existing': [], 'misses': []}
    errors = (OSError, ValueError, TypeError, KeyError)
    try:
        snapshot = canonical(snapshot)
        manifest = read(snapshot / 'manifest.json')
        entries = manifest['artifacts']
        require(manifest.get('format') == FORMAT and isinstance(entries, dict) and 0 < len(entries) <= 9,
                'invalid driver cache manifest')
    except errors as exc:
        result['misses'].append(f'manifest: {exc}')
        return result
    for key, stamp_hash in entries.items():
        try:
            digest(key)
            digest(stamp_hash)
            destination = cache / key
            if os.path.lexists(destination):
                result['existing'].append(key)
                continue
            with tempfile.TemporaryDirectory(dir=cache) as tmp:
                staged = Path(tmp) / key
                copy_entry(snapshot / key, staged, key, stamp_hash)
                try:
                    staged.rename(destination)
                except OSError as exc:
                    # Another importer published a complete (nonempty) entry first.
                    if exc.errno not in (errno.EEXIST, errno.ENOTEMPTY):
                        raise
                    result['existing'].append(key)
                else:
                    result['imported'].append(key)
        except errors as exc:
            result['misses'].append(f'{key}: {exc}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    save = commands.add_parser('export')
    save.add_argument('--report', type=Path, required=True)
    save.add_argument('--output', type=Path, required=True)
    load = commands.add_parser('import')
    load.add_argument('--snapshot', type=Path, required=True)
    load.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export(args.report, args.output) if args.operation == 'export' else restore(args.snapshot, args.cache)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        sys.exit(str(exc))
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
