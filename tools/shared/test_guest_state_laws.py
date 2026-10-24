#!/usr/bin/env python3
"""Run maintained Graph/Oracle laws through actual imports on authenticated O2 MLF.

Four sequential stages normally total about 90 seconds; the safety watchdog is
90 seconds PER STAGE, not a 90-second campaign claim. No compiler-within-compiler,
LLVM emission, copied state implementation, or full native/unit qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from test_direct import authenticate_build

ROOT = Path(__file__).resolve().parents[2]
WATCHDOG = ROOT/'tools/shared/resource_watchdog.py'
FLAGS = ('MLF_GRAPH_BUILD_NEGATIVE', 'MLF_ORACLE_TRAVERSAL_NEGATIVE')
CASES = (
    ('graph-build', 'GraphBuildLaws.emlf', FLAGS[0],
     ('libraries/mlf-foundation', 'libraries/mlf-language-core', 'libraries/mlf-inference', 'tests'),
     b'PASS graph build standard classes (14 checks)\n', b'FAIL graph build: pure/oracle\n'),
    ('oracle-traversal', 'OracleTraversalLaws.emlf', FLAGS[1],
     ('libraries/mlf-foundation', 'tests'),
     b'PASS oracle traversal (4 checks)\n', b'FAIL oracle traversal: fresh order/oracle\n'))
LIMITS = {'wall_seconds': 90, 'address_space_per_process': 3*1024**3,
          'process_tree_rss_bytes': 1536*1024**2, 'host_available_floor': 3*1024**3,
          'disk_free_floor': 3*1024**3, 'max_output_bytes': 100*1024**2}

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def capture_inputs(root, fixed):
    # Follow aliases inside the repository, but never silently skip their source
    # contents. Record each lexical link before deduplicating resolved dirs, so
    # retargets/new aliases and cycles cannot hide behind the visited set.
    root = root.resolve(strict=True)
    entries, hashes, visited = {}, {}, set()
    def remember_file(path, source=False):
        path = Path(path).absolute()
        resolved = path.resolve(strict=True)
        require(resolved.is_file(), 'input is not a file: '+str(path))
        require(not source or resolved.is_relative_to(root), 'source escapes repository')
        if resolved not in hashes:
            hashes[resolved] = digest(resolved)
        entries[str(resolved)] = {'kind': 'file', 'sha256': hashes[resolved], 'resolved': str(resolved)}
        if path.is_symlink():
            entries[str(path)] = {'kind': 'file-symlink', 'target': os.readlink(path), 'resolved': str(resolved)}
    def directory_link(path):
        resolved = path.resolve(strict=True)
        require(resolved.is_relative_to(root) and resolved.is_dir(), 'source directory escapes repository')
        entries[str(path.absolute())] = {'kind': 'directory-symlink', 'target': os.readlink(path),
                                        'resolved': str(resolved)}
    def walk_error(error):
        raise error
    for path in fixed:
        remember_file(path)
    for relative in ['libraries', 'tests', 'tools/shared/fixtures']:
        directory = root/relative
        require(directory.is_dir() and directory.resolve(strict=True).is_relative_to(root),
                'missing or escaping source root: '+relative)
        if directory.is_symlink():
            directory_link(directory)
        for current, directories, files in os.walk(directory, followlinks=True, onerror=walk_error):
            current = Path(current)
            resolved = current.resolve(strict=True)
            require(resolved.is_relative_to(root), 'source directory escapes repository')
            if current.is_symlink():
                directory_link(current)
            if resolved in visited:
                directories[:] = []
                continue
            visited.add(resolved)
            pending = []
            for name in sorted(directories):
                child = current/name
                if child.is_symlink():
                    directory_link(child)  # Validate before os.walk opens the target.
                if child.resolve(strict=True) not in visited:
                    pending.append(name)
            directories[:] = pending
            for name in sorted(files):
                path = current/name
                if path.suffix in {'.hs', '.emlf'}:
                    remember_file(path, source=True)
                elif path.is_symlink():
                    # Broken directory links may appear in os.walk's files list.
                    resolved = path.resolve(strict=True)
                    require(resolved.is_relative_to(root) and resolved.is_file(),
                            'broken, escaping, or changing non-source alias')
                    entries[str(path.absolute())] = {'kind': 'non-source-symlink',
                        'target': os.readlink(path), 'resolved': str(resolved)}
    return dict(sorted(entries.items()))

def unchanged(before, after):
    require(before == after, 'source/tool/input inventory changed during campaign')

def verify_observation(resource, status, log, expected):
    require(set(LIMITS) <= set(resource.get('limits', {})) and resource['limits'] == LIMITS,
            'resource contract changed')
    require('reason' in resource and resource['reason'] is None, 'resource failure is not a law result')
    require(type(resource.get('exit_code')) is int and resource['exit_code'] == status,
            'unexpected child status')
    require(resource.get('complete') is (status == 0), 'inconsistent completion status')
    require(resource.get('elapsed_seconds', 91) < 90 and
            resource.get('peak_group_rss', LIMITS['process_tree_rss_bytes']+1) <= LIMITS['process_tree_rss_bytes'],
            'resource measurement exceeds bounds')
    samples = resource.get('samples', [])
    require(bool(samples), 'missing resource samples')
    for sample in samples:
        require(sample.get('host_available', 0) >= LIMITS['host_available_floor'] and
                sample.get('disk_free', 0) >= LIMITS['disk_free_floor'] and
                sample.get('group_rss', LIMITS['process_tree_rss_bytes']+1) <= LIMITS['process_tree_rss_bytes'] and
                sample.get('output_bytes', LIMITS['max_output_bytes']+1) <= LIMITS['max_output_bytes'],
                'resource sample exceeds bounds')
    require(log == expected, 'law output differs from exact oracle')
    if status == 1:
        require(b'PASS' not in log and log.startswith(b'FAIL '), 'invalid negative control output')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    receipt = args.build_receipt.resolve(strict=True)
    producer_dir = receipt.parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    record = {'complete': False, 'kind': 'actual-import-guest-state-laws', 'commands': [],
              'full_native_unit': False, 'native_or_llvm_output': False,
              'per_stage_limits': LIMITS, 'expected_campaign_seconds_approximate': 90.5}
    def save():
        temporary = output/'receipt.json.tmp'
        temporary.write_text(json.dumps(record, indent=2)+'\n')
        temporary.replace(output/'receipt.json')
    def authenticate():
        producer = authenticate_build(receipt, producer_dir/'bin')
        require(producer['optimization'] == '2', 'state-law gate requires authenticated O2 producer')
        for name, expected in producer['object_inputs'].items():
            path = (producer_dir/name).resolve(strict=True)
            require(path.is_relative_to(producer_dir) and digest(path) == expected,
                    'producer object changed: '+name)
        return producer
    try:
        producer = authenticate()
        compiler = producer_dir/'bin/emlf'
        fixed = [Path(__file__), WATCHDOG, ROOT/'tools/shared/test_direct.py', ROOT/'tools/shared/build.py',
                 receipt, compiler, ROOT/'tests/Tests/Graph.emlf', ROOT/'tests/Tests/Oracle.emlf',
                 *[ROOT/'tools/shared/fixtures'/case[1] for case in CASES]]
        before = capture_inputs(ROOT, fixed)
        record.update(inputs=before, producer_receipt_sha256=digest(receipt),
                      producer_objects=producer['object_inputs'])
        save()
        results = {}
        for label, fixture, flag, roots, positive, negative in CASES:
            for failure in [False, True]:
                unchanged(before, capture_inputs(ROOT, fixed))
                stage = label+('-negative' if failure else '-positive')
                directory = output/stage
                directory.mkdir()
                command = [str(compiler)]
                for root in roots:
                    command.extend(['-i', str(ROOT/root)])
                command.extend(['--run', str(ROOT/'tools/shared/fixtures'/fixture)])
                flags = {name: '0' for name in FLAGS}
                flags[flag] = '1' if failure else '0'
                environment = dict(os.environ, **flags)
                row = {'label': stage, 'command': command, 'environment_overrides': flags,
                       'expected_exit': 1 if failure else 0, 'complete': False}
                record['commands'].append(row)
                save()
                supervised = [sys.executable, str(WATCHDOG), '--seconds', '90', '--address-space-mib', '3072',
                              '--rss-mib', '1536', '--disk-free-mib', '3072', '--max-output-mib', '100',
                              str(directory), 'nice', '-n', '19', 'ionice', '-c', '3', *command]
                result = subprocess.run(supervised, cwd=ROOT, env=environment, capture_output=True)
                (directory/'supervisor.stdout').write_bytes(result.stdout)
                (directory/'supervisor.stderr').write_bytes(result.stderr)
                resource_path = directory/'bounded-receipt.json'
                log_path = directory/'build.log'
                resource = json.loads(resource_path.read_text())
                expected_status = 1 if failure else 0
                verify_observation(resource, expected_status, log_path.read_bytes(), negative if failure else positive)
                require(result.returncode == expected_status, 'watchdog process status mismatch')
                unchanged(before, capture_inputs(ROOT, fixed))
                results[str(resource_path)] = digest(resource_path)
                results[str(log_path)] = digest(log_path)
                row.update(complete=True, expected_negative_control=failure,
                           elapsed_seconds=resource['elapsed_seconds'],
                           resource_receipt_sha256=digest(resource_path), log_sha256=digest(log_path))
                save()
        authenticate()
        unchanged(before, capture_inputs(ROOT, fixed))
        require(all(digest(path) == expected for path, expected in results.items()), 'recorded result changed')
        record.update(complete=True, inputs_unchanged=True, producer_and_objects_reauthenticated=True,
                      result_files=results, observed_campaign_seconds=sum(row['elapsed_seconds'] for row in record['commands']))
        save()
        print(json.dumps({'complete': True, 'stages': 4, 'positive_law_checks': 18,
                          'negative_controls': 2, 'full_native_unit': False}))
    except BaseException as error:
        record['error'] = type(error).__name__+': '+str(error)
        save()
        raise

if __name__ == '__main__':
    main()
