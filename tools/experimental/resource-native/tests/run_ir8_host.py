#!/usr/bin/env python3
"""Run the four script-only IR8 host suites, never discovery or native code.

POSIX, unoptimized CPython 3.12. From any directory:
  python3.12 -B tests/run_ir8_host.py --output /fresh/external/ir8-host-evidence
The output parent must already exist; output must not exist, contain symlinks,
or be within this checkout. All evidence is retained on failure. Exactly four
children on success, sequential, using this interpreter with -B -S and a local
PYTHONPATH. Stage04 generates C TEXT ONLY and stops before compilation.

Limits per child: CPU 180 s, wall including cleanup 240 s, address space 1 GiB,
stdout/stderr 4 MiB each. Aggregate wall 900 s, retained evidence 256 MiB/600
files. Live census guards stop on budget violation, never delete excess evidence
or claim truncated streams passed. Outer containment is still appropriate for
uninterruptible OS faults; inability to reap/clear a process group is failure.
This is an execution entrypoint, not authorization to launch unreviewed sources.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time

HERE = Path(__file__).absolute().parent
ROOT = HERE.parent
CHECKOUT = ROOT.parents[2]
MIB = 1024 * 1024
CPU_SECONDS = 180
WALL_SECONDS = 240
STAGE_SECONDS = 900
MEMORY_BYTES = 1024 * MIB
STREAM_BYTES = 4 * MIB
EVIDENCE_BYTES = 256 * MIB
EVIDENCE_FILES = 600
# Leave room for failure reports after a child is stopped. No evidence is erased.
LIVE_BYTES = EVIDENCE_BYTES - 2 * MIB
LIVE_FILES = EVIDENCE_FILES - 4
SUITES = (
    ('declarations', 'test_ir8_declarations.py', 103, None),
    ('resources', 'test_ir8_resources.py', 170, 'RESOURCE_TEST_EVIDENCE'),
    ('metadata', 'test_ir8_metadata.py', 117, 'METADATA_TEST_EVIDENCE'),
    ('packet', 'test_stage04_packet.py', 85, 'STAGE04_TEST_EVIDENCE'),
)
INTERRUPTED = None
DEADLINE = None


class GateError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise GateError(message)


def exact(actual, expected, message):
    require(type(actual) is type(expected), message + ': value type')
    if type(expected) is dict:
        require(set(actual) == set(expected), message + ': keys')
        for key in expected:
            exact(actual[key], expected[key], message + '.' + str(key))
    elif type(expected) in (list, tuple):
        require(len(actual) == len(expected), message + ': length')
        for left, right in zip(actual, expected):
            exact(left, right, message)
    else:
        require(actual == expected, message)


def stop_requested():
    require(INTERRUPTED is None, 'interrupted by signal %s' % INTERRUPTED)
    require(DEADLINE is None or time.monotonic() < DEADLINE - 5,
            'aggregate wall deadline reached')


def signal_handler(number, _frame):
    global INTERRUPTED
    if INTERRUPTED is None:
        INTERRUPTED = number


def no_symlinks(path):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'absolute normalized path required')
    for part in [*reversed(path.parents), path]:
        st = part.lstat()
        require(not stat.S_ISLNK(st.st_mode), 'symlink forbidden: ' + str(part))
    return path


def identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def read_file(path, limit, collect=False):
    """Bounded regular-file ingress; stat before read, identity checked afterward."""
    path = no_symlinks(Path(path))
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit,
            'nonregular or over-limit file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    digest = hashlib.sha256()
    chunks = []
    count = 0
    try:
        exact(identity(os.fstat(fd)), identity(before), 'file changed before open: ' + str(path))
        while True:
            data = os.read(fd, min(65536, limit + 1 - count))
            if not data:
                break
            count += len(data)
            require(count <= limit, 'file grew beyond bound: ' + str(path))
            digest.update(data)
            if collect:
                chunks.append(data)
        exact(identity(os.fstat(fd)), identity(before), 'file changed during read: ' + str(path))
    finally:
        os.close(fd)
    exact(identity(path.lstat()), identity(before), 'file replaced during read: ' + str(path))
    exact(count, before.st_size, 'file size changed: ' + str(path))
    result = {'bytes': count, 'sha256': digest.hexdigest()}
    return (result, b''.join(chunks)) if collect else result


def pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def reject_constant(value):
    raise GateError('nonfinite JSON value: ' + value)


def json_bytes(data):
    return json.loads(data.decode('utf-8'), object_pairs_hook=pairs_no_duplicates,
                      parse_constant=reject_constant)


def json_file(path, limit=8 * MIB):
    return json_bytes(read_file(path, limit, True)[1])


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode()


def write_new(path, value):
    payload = encoded(value)
    require(len(payload) <= 2 * MIB, 'runner receipt exceeds reserved bound')
    with path.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def append_event(path, event):
    payload = (json.dumps(event, sort_keys=True, separators=(',', ':')) + '\n').encode()
    require(len(payload) <= MIB, 'command journal record too large')
    with path.open('ab') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def census(root, hash_files=False):
    """No links/special files, bounded directory and file membership."""
    entries = {}
    total = directories = 0
    for current, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        names.sort()
        directories += 1
        require(directories <= 2048, 'evidence directory count exceeded')
        for name in dirs:
            st = (Path(current) / name).lstat()
            require(stat.S_ISDIR(st.st_mode), 'non-directory/symlink evidence member')
        for name in names:
            path = Path(current) / name
            st = path.lstat()
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1,
                    'nonregular/link evidence member: ' + str(path))
            require(len(entries) < EVIDENCE_FILES, 'evidence file ceiling exceeded')
            total += st.st_size
            require(total <= EVIDENCE_BYTES, 'evidence byte ceiling exceeded')
            entries[str(path.relative_to(root))] = (read_file(path, EVIDENCE_BYTES)
                                                  if hash_files else {'bytes': st.st_size})
    return {'files': entries, 'file_count': len(entries), 'bytes': total,
            'directories': directories}


def source_inputs():
    paths = {HERE / script for _, script, _, _ in SUITES}
    paths.update(HERE / name for name in (
        'run_ir8_host.py', 'stage04_packet_fixture_driver.py',
        'stage04_packet_oracle.py', 'stage04_packet_native_harness.c',
        'stage04_packet_cases.json'))
    paths.update((HERE / 'fixtures').glob('ir8-*.json'))
    for directory in (ROOT / 'resource_ir_v8', ROOT / 'packet_v8'):
        no_symlinks(directory)
        for path in directory.rglob('*'):
            require(not path.is_symlink(), 'symlink source member')
            if path.is_file():
                require('__pycache__' not in path.parts and path.suffix != '.pyc',
                        'bytecode cache in pinned local package')
                paths.add(path)
    require(len(paths) <= 256, 'source input census exceeded')
    result = {}
    total = 0
    for path in sorted(paths):
        stop_requested()
        entry = read_file(path, 16 * MIB)
        total += entry['bytes']
        require(total <= 64 * MIB, 'source input byte ceiling exceeded')
        result[str(path.relative_to(ROOT))] = entry
    return result


def literal_assignment(path, name):
    tree = ast.parse(read_file(path, MIB, True)[1].decode('utf-8'))
    found = [node.value for node in tree.body if isinstance(node, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
    exact(len(found), 1, 'one literal assignment required: ' + name)
    return ast.literal_eval(found[0])


def fixtures():
    result = {}
    for short in ('resources', 'metadata', 'metadata-boundaries'):
        data = json_file(HERE / 'fixtures' / ('ir8-' + short + '.json'))
        result[short] = data['cases']
        names = [case['name'] for case in data['cases']]
        exact(len(set(names)), len(names), 'duplicate raw fixture name')
        for case in data['cases']:
            payload = case['text'].encode('utf-8')
            exact(len(payload), case['input_bytes'], 'raw byte pin')
            exact(hashlib.sha256(payload).hexdigest(), case['input_sha256'], 'raw hash pin')
    result['mutations'] = literal_assignment(HERE / 'test_ir8_metadata.py', 'MUTATIONS')
    result['packet'] = json_file(HERE / 'stage04_packet_cases.json')
    exact(len(result['resources']), 140, 'resource raw census')
    exact(sum(case['accepted'] is True for case in result['resources']), 26, 'resource positives')
    exact(sum(case['accepted'] is True for case in result['metadata']), 31, 'metadata positives')
    exact(len(result['metadata']), 55, 'metadata raw census')
    exact(len(result['metadata-boundaries']), 3, 'metadata phase census')
    exact(len(result['mutations']), 30, 'metadata mutation census')
    exact(len(result['packet']['native_fixtures']), 12, 'packet native-source census')
    exact(len(result['packet']['native_mutations']), 82, 'packet mutation census')
    return result


def expected_payload_names(cases, positive_suffix, negative_suffix):
    result = set()
    for case in cases:
        suffixes = positive_suffix if case['accepted'] else (negative_suffix,)
        result.update(case['name'] + suffix for suffix in suffixes)
    return result


def pin_records(directory, records, expected_names, field='name'):
    require(type(records) is list, 'file pin list required')
    pinned = {}
    for record in records:
        exact(set(record), {field, 'bytes', 'sha256'}, 'exact file pin keys')
        name = record[field]
        require(type(name) is str and name in expected_names and name not in pinned,
                'unexpected/duplicate file pin: ' + repr(name))
        require(type(record['bytes']) is int and 0 <= record['bytes'] <= EVIDENCE_BYTES,
                'plain bounded byte count required')
        require(type(record['sha256']) is str and re.fullmatch('[0-9a-f]{64}', record['sha256']),
                'valid hash required')
        actual = read_file(directory / name, record['bytes'])
        exact(actual, {key: record[key] for key in ('bytes', 'sha256')}, 'file pin mismatch: ' + name)
        pinned[name] = actual
    exact(set(pinned), expected_names, 'complete payload inventory')
    return pinned


def failure_fields(manifest, count, tests='tests_run'):
    exact(manifest[tests], count, 'manifest test count')
    for key in ('failures', 'errors', 'skipped'):
        exact(manifest[key], 0, 'nonzero or malformed ' + key)


def exact_diagnostics(directory, cases, suffix):
    for case in cases:
        if case['accepted']:
            continue
        diagnostic = json_file(directory / (case['name'] + suffix), MIB)
        for key in ('layer', 'code', 'path'):
            exact(diagnostic[key], case['expected_' + key], 'changed lower diagnostic: ' + case['name'])


def verify_unittest(directory, count):
    stderr = read_file(directory / 'stderr.raw', STREAM_BYTES, True)[1].decode('utf-8')
    summaries = re.findall(r'^Ran ([0-9]+) tests? in ([0-9]+(?:\.[0-9]+)?)s$', stderr, re.M)
    exact(len(summaries), 1, 'one unittest summary required')
    exact(int(summaries[0][0]), count, 'unittest count')
    exact(stderr.rstrip().splitlines()[-1], 'OK', 'unittest did not end with unqualified OK')
    exact(len(re.findall(r'^.* \.\.\. ok$', stderr, re.M)), count, 'each individual unittest must report ok')
    require(not re.search(r'^.* \.\.\. (?:FAIL|ERROR|skipped|expected failure|unexpected success)', stderr, re.M),
            'failure/error/skip in verbose result')


def verify_suite(name, directory, data):
    evidence = directory / 'evidence'
    if name == 'declarations':
        exact(read_file(directory / 'stdout.raw', STREAM_BYTES, True)[1], b'', 'unexpected declaration stdout')
        require(not evidence.exists(), 'declaration suite must not emit case files')
        return {'payload_files': 0, 'payload_bytes': 0}
    if name in ('resources', 'metadata'):
        metadata = name == 'metadata'
        manifest = json_file(evidence / 'MANIFEST.json')
        keys = ({'schema', 'tests_run', 'failures', 'errors', 'skipped', 'files', 'total_bytes',
                 'graph_executed', 'native_executed', 'source_admitted'} if metadata else
                {'schema', 'payload_files', 'payload_bytes', 'fixed_cases', 'tests_run', 'errors',
                 'failures', 'skipped', 'graph_execution'})
        exact(set(manifest), keys, 'exact lower manifest schema')
        exact(manifest['schema'], 'ir8-metadata-case-evidence/1' if metadata else
              'ir8-resource-host-case-evidence/1', 'lower manifest format')
        failure_fields(manifest, 117 if metadata else 170)
        names = expected_payload_names(data[name], ('.metadata.json', '.report.json') if metadata else
                                       ('.derived.json', '.report.json'), '.error.json' if metadata else '.rejection.json')
        if metadata:
            names.update('mutation-' + item[0] + '.json' for item in data['mutations'])
            names.update('phase-' + item['name'] + '.json' for item in data['metadata-boundaries'])
            for key in ('graph_executed', 'native_executed', 'source_admitted'):
                exact(manifest[key], False, 'unexpected execution/admission claim')
        else:
            exact(manifest['fixed_cases'], 140, 'resource fixture census')
            exact(manifest['graph_execution'], False, 'resource graph execution claim')
        pins = pin_records(evidence, manifest['files' if metadata else 'payload_files'], names)
        total = sum(item['bytes'] for item in pins.values())
        exact(manifest['total_bytes' if metadata else 'payload_bytes'], total, 'lower evidence byte sum')
        require(total <= (128 if metadata else 32) * MIB, 'existing suite evidence budget exceeded')
        exact(set(census(evidence)['files']), names | {'MANIFEST.json'}, 'unlisted lower evidence')
        exact_diagnostics(evidence, data[name], '.error.json' if metadata else '.rejection.json')
        stdout = read_file(directory / 'stdout.raw', STREAM_BYTES, True)[1]
        if metadata:
            exact(json_bytes(stdout), {'status': 'passed', 'tests': 117, 'case_files': len(pins),
                  'case_bytes': total, 'graph_executed': False, 'native_executed': False,
                  'source_admitted': False}, 'metadata stdout receipt')
        else:
            expected_resource_stdout = (
                b'B07 budget-only choice trace: row+inner+inventory=3; references=1000; final=65536; no provenance admission claim\n'
                b'B08 budget-only choice trace: required=1004; remaining=1003; no insertion; no provenance admission claim\n'
            )
            exact(stdout, expected_resource_stdout, 'exact resource budget-only stdout')
        return {'payload_files': len(pins) + 1, 'payload_bytes': census(evidence)['bytes'],
                'manifest': read_file(evidence / 'MANIFEST.json', 8 * MIB)}
    return verify_packet(directory, data)


def verify_packet(directory, data):
    evidence = directory / 'evidence'
    host = json_file(evidence / 'HOST_RESULTS.json')
    exact(set(host), {'format', 'tests', 'failures', 'errors', 'skipped', 'records',
                     'native_executed', 'graph_executed', 'source_admitted'}, 'host results schema')
    exact(host['format'], 'ir8-stage04-host-results/1', 'host results format')
    failure_fields(host, 85, 'tests')
    for key in ('native_executed', 'graph_executed', 'source_admitted'):
        exact(host[key], False, 'unexpected packet execution/admission')
    cases = {case['name']: case for case in data['metadata']}
    candidates = data['packet']['native_fixtures']
    native_names = {case['name'] for case in candidates}
    expected_names = {'HOST_RESULTS.json', 'native/MANIFEST.json', 'native/stage04_arithmetic.c'}
    seen = set()
    host_bytes = 0
    require(type(host['records']) is list, 'host record list required')
    exact(len(host['records']), 56, '55 raw outcomes plus one private diagnostic')
    private = [record for record in host['records'] if record.get('name') == 'private-bool-integer']
    exact(private, [{'name': 'private-bool-integer',
                    'classification': 'private-mutation-not-public-capacity',
                    'diagnostic': {'layer': 'packet-mapping', 'code': 'EQUATION',
                                   'path': 'packet.specification',
                                   'message': 'packet value has a different plain type'}}],
          'exact separately retained private bool/integer diagnostic')
    for record in host['records']:
        name = record['name']
        if name == 'private-bool-integer':
            continue
        require(name in cases and name not in seen, 'unknown/duplicate host result')
        seen.add(name)
        case = cases[name]
        if not case['accepted']:
            exact(set(record), {'name', 'status', 'diagnostic'}, 'rejection record keys')
            exact(record['status'], 'expected-lower-rejection', 'lower rejection status')
            for key in ('layer', 'code', 'path'):
                exact(record['diagnostic'][key], case['expected_' + key], 'packet lower diagnostic')
            continue
        exact(set(record), {'name', 'status', 'declared_outcome', 'artifacts', 'raw_sha256',
                           'metadata_sha256', 'supplement_sha256', 'manifest_sha256', 'source_sha256'},
              'accepted host record keys')
        exact(record['status'], 'host-emission-only', 'host result status')
        exact(record['declared_outcome'], 'accepted', 'host declared outcome')
        exact(record['raw_sha256'], case['input_sha256'], 'host raw binding')
        if name in native_names:
            exact(record['artifacts'], [], 'native artifact duplication')
            continue
        names = {'host-only/' + name + '/' + tail for tail in (
            'ir8_packet_generated.h', 'ir8_packet_generated.c', 'host-receipt.json')}
        pins = pin_records(evidence, record['artifacts'], names, 'path')
        expected_names.update(names)
        host_bytes += sum(pin['bytes'] for pin in pins.values())
        receipt = json_file(evidence / ('host-only/' + name + '/host-receipt.json'))
        exact(set(receipt), {'format', 'fixture', 'manifest_json', 'manifest_sha256',
                            'supplement_json', 'supplement_sha256'}, 'host artifact receipt keys')
        exact(receipt['format'], 'ir8-stage04-host-artifact/1', 'host artifact format')
        exact(receipt['fixture'], name, 'host artifact fixture')
        for kind in ('manifest', 'supplement'):
            exact(hashlib.sha256(receipt[kind + '_json'].encode()).hexdigest(),
                  receipt[kind + '_sha256'], 'embedded artifact hash')
            exact(receipt[kind + '_sha256'], record[kind + '_sha256'], 'host artifact hash link')
        exact(pins['host-only/' + name + '/ir8_packet_generated.c']['sha256'],
              record['source_sha256'], 'host source hash link')
    exact(seen, set(cases), 'all raw case outcomes required')
    require(host_bytes <= 128 * MIB, 'host-only artifact budget')
    native = evidence / 'native'
    generation = json_file(native / 'MANIFEST.json')
    exact(set(generation), {'format', 'private_arithmetic', 'fixtures', 'files',
                           'payload_bytes_excluding_manifest', 'status', 'compiler_invoked',
                           'native_invoked'}, 'generation manifest schema')
    exact(generation['format'], 'ir8-stage04-generation/1', 'generation format')
    exact(generation['files'], 50, 'generation file count')
    exact(generation['status'], 'stop-for-generated-source-review', 'generation stop boundary')
    for key in ('compiler_invoked', 'native_invoked'):
        exact(generation[key], False, 'unexpected generated execution')
    exact(len(generation['fixtures']), 12, 'twelve generated fixture records')
    total = mutations = 0
    for candidate, record in zip(candidates, generation['fixtures']):
        exact(set(record), {'fixture', 'order', 'files', 'expected_native_file', 'status',
                           'raw_sha256', 'native_mutations', 'graph_executed', 'source_admitted'},
              'generated fixture schema')
        name = candidate['name']
        for actual, wanted in ((record['fixture'], name), (record['order'], candidate['order']),
                               (record['raw_sha256'], candidate['raw_sha256']),
                               (record['status'], 'generated-uncompiled'),
                               (record['expected_native_file'], 'native.stdout.json')):
            exact(actual, wanted, 'generated fixture binding')
        for key in ('graph_executed', 'source_admitted'):
            exact(record[key], False, 'generated execution/admission claim')
        relative = '%02d' % candidate['order']
        names = {'ir8_packet_generated.h', 'ir8_packet_generated.c', 'stage04_harness.c', 'control.json'}
        pins = pin_records(native / relative, record['files'], names)
        total += sum(pin['bytes'] for pin in pins.values())
        expected_names.update('native/' + relative + '/' + name for name in names)
        control = json_file(native / relative / 'control.json', 16 * MIB)
        exact(control['format'], 'ir8-stage04-fixture-control/1', 'control format')
        exact(control['fixture'], name, 'control fixture')
        exact(control['order'], candidate['order'], 'control order')
        exact(control['raw_json'], cases[name]['text'], 'control exact raw text')
        exact(control['raw_sha256'], candidate['raw_sha256'], 'control raw pin')
        expected_mutations = [item['name'] for item in data['packet']['native_mutations'] if item['fixture'] == name]
        exact([item['name'] for item in control['mutations']], expected_mutations, 'mutation identity/order')
        exact(record['native_mutations'], len(expected_mutations), 'mutation count')
        mutations += record['native_mutations']
        for kind in ('manifest', 'supplement'):
            exact(hashlib.sha256(control[kind + '_json'].encode()).hexdigest(),
                  control[kind + '_sha256'], 'control embedded hash')
        host_record = next(row for row in host['records'] if row['name'] == name)
        exact(pins['ir8_packet_generated.c']['sha256'], host_record['source_sha256'], 'native/host emitted source link')
        for kind in ('manifest', 'supplement'):
            exact(control[kind + '_sha256'], host_record[kind + '_sha256'], 'native/host embedded link')
    exact(mutations, 82, 'finite mutation total')
    arithmetic = generation['private_arithmetic']
    exact(set(arithmetic), {'source', 'bytes', 'sha256', 'expected_native_file'}, 'arithmetic pin schema')
    exact(arithmetic['source'], 'stage04_arithmetic.c', 'arithmetic filename')
    exact(arithmetic['expected_native_file'], 'arithmetic.stdout.json', 'arithmetic output association')
    arithmetic_pins = pin_records(native, [{key: arithmetic[key] for key in ('source', 'bytes', 'sha256')}],
                                 {'stage04_arithmetic.c'}, 'source')
    total += arithmetic_pins['stage04_arithmetic.c']['bytes']
    exact(generation['payload_bytes_excluding_manifest'], total, 'generation payload bytes')
    require(total + read_file(native / 'MANIFEST.json', 8 * MIB)['bytes'] <= 128 * MIB,
            'generation evidence budget')
    exact(set(census(evidence)['files']), expected_names, 'complete packet artifact census')
    exact(len(expected_names), 108, 'packet retained file count')
    exact(json_bytes(read_file(directory / 'stdout.raw', STREAM_BYTES, True)[1]),
          {'status': 'host-only-stop-before-compile', 'tests': 85, 'generated_fixtures': 12,
           'native_executed': False, 'graph_executed': False, 'source_admitted': False}, 'packet stdout receipt')
    return {'payload_files': 108, 'payload_bytes': census(evidence)['bytes'],
            'raw_positives': 31, 'raw_rejections': 24, 'native_source_sets': 12,
            'native_mutation_records': 82, 'host_only_source_sets': 19, 'private_host_records': 1,
            'generation_manifest': read_file(native / 'MANIFEST.json', 8 * MIB),
            'host_results': read_file(evidence / 'HOST_RESULTS.json', 8 * MIB)}


def limit_child():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * MIB, 128 * MIB))


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def kill_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def child_failure(result, where, error):
    """In-memory custody survives failed evidence writes; never masks cleanup."""
    detail = where + ': ' + type(error).__name__ + ': ' + str(error)
    result['status'] = 'failed-or-unknown'
    result['reason'] = result['reason'] or detail
    result['custody_errors'].append(detail)


def run_child(name, script, count, variable, directory, output, result):
    # main has already appended this SAME dict before any launch or file write.
    # Thus a post-Popen exception cannot make an actual/uncertain call disappear.
    started = time.monotonic()
    result['attempt_started_monotonic'] = started
    process = selector = None
    files = {}
    observed = {'stdout': 0, 'stderr': 0}
    kept = {'stdout': 0, 'stderr': 0}
    complete = {'stdout': True, 'stderr': True}
    reason = None
    termination = None
    cleanup = None
    journal_ready = journal_failed = False
    journal = directory / 'COMMAND.jsonl'
    try:
        directory.mkdir()
        with journal.open('xb'):
            pass
        journal_ready = True
        env = {'PATH': os.defpath, 'LANG': 'C', 'LC_ALL': 'C', 'PYTHONPATH': str(ROOT),
               'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1',
               'PYTHONHASHSEED': '0', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'}
        if variable:
            env[variable] = str(directory / 'evidence')
        argv = [sys.executable, '-B', '-S', str(HERE / script)]
        command = {'suite': name, 'argv': argv, 'cwd': str(ROOT), 'env': env,
                   'expected_tests': count, 'expected_return_code': 0,
                   'limits': {'cpu_seconds': CPU_SECONDS, 'wall_seconds': WALL_SECONDS,
                              'address_space_bytes': MEMORY_BYTES, 'stream_bytes_each': STREAM_BYTES}}
        result['command'] = command
        try:
            append_event(journal, {'event': 'launch-intended', 'command': command})
        except BaseException:
            journal_failed = True
            raise
        selector = selectors.DefaultSelector()
        for stream in ('stdout', 'stderr'):
            files[stream] = (directory / (stream + '.raw')).open('xb')
        # Mark the call before entering Popen. If Popen raises, whether it created
        # a child is conservatively UNKNOWN, even for a plausible exec failure.
        result['launch_attempted'] = True
        result['launch_state'] = 'popen-outcome-unknown'
        result['launch_attempt_monotonic'] = time.monotonic()
        process = subprocess.Popen(argv, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True, preexec_fn=limit_child)
        # No fallible journal/stream operation intervenes before this registration.
        result['known_started'] = True
        result['pid'] = process.pid
        result['pgid'] = process.pid
        result['launch_state'] = 'started'
        try:
            append_event(journal, {'event': 'process-started', 'pid': process.pid, 'pgid': process.pid})
        except BaseException:
            journal_failed = True
            raise
        for name_, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name_)
        next_census = 0.0
        while selector.get_map() or process.poll() is None:
            now = time.monotonic()
            if reason is None:
                if INTERRUPTED is not None:
                    reason = 'signal-' + str(INTERRUPTED)
                elif now >= min(started + WALL_SECONDS - 4, DEADLINE - 5):
                    reason = 'wall-limit'
                elif now >= next_census:
                    try:
                        seen = census(output)
                        require(seen['bytes'] <= LIVE_BYTES and seen['file_count'] <= LIVE_FILES,
                                'live evidence reservation exceeded')
                    except Exception as error:
                        reason = 'evidence-limit-or-census: ' + str(error)
                    next_census = now + 0.1
            if process.poll() is not None and group_exists(process.pid) and reason is None:
                reason = 'lingering-process-group'
            if reason is not None and termination is None:
                termination = now
                kill_group(process.pid, signal.SIGTERM)
            if termination is not None and now >= termination + 1:
                kill_group(process.pid, signal.SIGKILL)
            if termination is not None and now >= termination + 3:
                for key in list(selector.get_map().values()):
                    complete[key.data] = False
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                break
            for key, _mask in selector.select(0.05):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    key.fileobj.close()
                    continue
                stream = key.data
                observed[stream] += len(chunk)
                available = STREAM_BYTES - kept[stream]
                part = chunk[:available]
                try:
                    files[stream].write(part)
                    files[stream].flush()
                    kept[stream] += len(part)
                except BaseException:
                    complete[stream] = False
                    raise
                if len(chunk) > available:
                    complete[stream] = False
                    reason = reason or stream + '-limit'
        if process.poll() is None:
            kill_group(process.pid, signal.SIGKILL)
        process.wait(timeout=1)
        result['return_code'] = process.returncode
        if process.returncode != 0:
            reason = reason or 'nonzero-exit'
    except BaseException as error:
        child_failure(result, 'launch-or-capture', error)
    finally:
        # Each cleanup operation is separately guarded: a failed kill, wait,
        # close, flush or fsync must not bypass the remaining cleanup attempts.
        if process is not None:
            try:
                kill_group(process.pid, signal.SIGKILL)
            except BaseException as error:
                child_failure(result, 'process-group-kill', error)
            try:
                process.wait(timeout=1)
                result['return_code'] = process.returncode
            except BaseException as error:
                child_failure(result, 'process-reap', error)
            try:
                cleanup = process.returncode is not None and not group_exists(process.pid)
            except BaseException as error:
                child_failure(result, 'process-group-check', error)
            result['process_group_cleanup_confirmed'] = cleanup
            result['launch_state'] = 'terminated' if process.returncode is not None else 'started-outcome-unknown'
            for name_, stream in (('stdout', process.stdout), ('stderr', process.stderr)):
                if stream is not None and not stream.closed:
                    complete[name_] = False
                    try:
                        stream.close()
                    except BaseException as error:
                        child_failure(result, name_ + '-pipe-close', error)
        else:
            # No returned process handle means no complete capture/cleanup claim.
            complete['stdout'] = complete['stderr'] = False
        if selector is not None:
            try:
                selector.close()
            except BaseException as error:
                child_failure(result, 'selector-close', error)
        for name_, stream in files.items():
            try:
                stream.flush()
            except BaseException as error:
                complete[name_] = False
                child_failure(result, name_ + '-flush', error)
            try:
                os.fsync(stream.fileno())
            except BaseException as error:
                complete[name_] = False
                child_failure(result, name_ + '-fsync', error)
            try:
                stream.close()
            except BaseException as error:
                complete[name_] = False
                child_failure(result, name_ + '-close', error)
        # Terminal state and elapsed time reach the shared record BEFORE hashes
        # or receipt writes. Those later operations are custody, not execution.
        result['elapsed_seconds'] = time.monotonic() - started
        result['process_group_cleanup_confirmed'] = cleanup
        if result['elapsed_seconds'] > WALL_SECONDS:
            reason = reason or 'wall-limit-including-cleanup'
        if cleanup is not True:
            reason = reason or 'cleanup-unconfirmed-or-not-launched'
        if not all(complete.values()):
            reason = reason or 'incomplete-stream'
        result['reason'] = result['reason'] or reason
        result['status'] = 'process-ok' if result['reason'] is None else 'failed-or-unknown'
    for name_ in ('stdout', 'stderr'):
        stream_result = {'observed_bytes': observed[name_], 'complete': complete[name_],
                         'retained_bytes_confirmed_by_write': kept[name_], 'hash_status': 'unavailable'}
        result['streams'][name_] = stream_result
        try:
            stream_result.update(read_file(directory / (name_ + '.raw'), STREAM_BYTES))
            stream_result['hash_status'] = 'checked'
        except BaseException as error:
            stream_result['complete'] = False
            child_failure(result, name_ + '-final-hash', error)
    if journal_ready and not journal_failed:
        try:
            append_event(journal, {'event': 'process-result', 'result': result})
        except BaseException as error:
            journal_failed = True
            child_failure(result, 'process-result-journal', error)
    result['journal_custody'] = 'failed-or-incomplete' if journal_failed or not journal_ready else 'written'
    # Even if the journal is unwritable, the same failed/unknown record remains
    # in main's final summary. No retry or later suite is allowed after failure.
    return result


def main():
    global DEADLINE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', required=True, help='fresh external evidence directory; parent must exist')
    args = parser.parse_args()
    require(os.name == 'posix', 'POSIX process groups and rlimits required')
    require(sys.implementation.name == 'cpython' and sys.version_info[:2] == (3, 12),
            'CPython 3.12 required')
    require(sys.flags.optimize == 0 and __debug__, 'optimized Python disables required assertions')
    started = time.monotonic()
    DEADLINE = started + STAGE_SECONDS
    for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(number, signal_handler)
    output = Path(args.output).absolute()
    require('..' not in output.parts, 'normalized output path required')
    no_symlinks(output.parent)
    no_symlinks(CHECKOUT)
    require(not output.is_relative_to(CHECKOUT), 'output must be outside the source checkout')
    require(not output.exists() and not output.is_symlink(), 'fresh output directory required')
    inputs = source_inputs()
    data = fixtures()
    interpreter = Path(sys.executable).resolve(strict=True)
    interpreter_pin = read_file(interpreter, 128 * MIB)
    # 167 resource files +120 metadata files +108 packet files +12 process files
    # +SOURCE_INPUTS/RUN_PLAN/RUN_RESULT =410 regular files on complete success.
    forecast = 410
    output.mkdir(mode=0o700)
    write_new(output / 'SOURCE_INPUTS.json', {'format': 'ir8-host-source-inputs/1',
              'root': str(ROOT), 'files': inputs, 'interpreter': {'path': str(interpreter), **interpreter_pin}})
    write_new(output / 'RUN_PLAN.json', {'format': 'ir8-host-suite-plan/1', 'scope': 'host-only; generated C text only',
              'suites': [dict(name=n, script=s, tests=t, evidence_variable=v) for n, s, t, v in SUITES],
              'expected_tests': 475, 'expected_success_files': forecast, 'max_child_processes': 4,
              'stage_wall_seconds': STAGE_SECONDS, 'evidence_bytes': EVIDENCE_BYTES,
              'evidence_files': EVIDENCE_FILES, 'source_mutation_permitted': False,
              'compiler_native_model_original_source_execution': False})
    results = []
    failure = None
    try:
        for name, script, count, variable in SUITES:
            stop_requested()
            exact(source_inputs(), inputs, 'local source drift before child')
            exact(read_file(interpreter, 128 * MIB), interpreter_pin, 'interpreter drift')
            directory = output / name
            result = {'suite': name, 'status': 'not-launched', 'reason': None,
                      'launch_attempted': False, 'known_started': False,
                      'launch_state': 'not-attempted', 'pid': None, 'pgid': None,
                      'return_code': None, 'elapsed_seconds': None,
                      'process_group_cleanup_confirmed': None, 'streams': {},
                      'custody_errors': []}
            results.append(result)  # Register BEFORE every fallible launch operation.
            run_child(name, script, count, variable, directory, output, result)
            require(result['status'] == 'process-ok', name + ': ' + str(result['reason']))
            stop_requested()
            verify_unittest(directory, count)
            evidence = verify_suite(name, directory, data)
            exact(source_inputs(), inputs, 'local source drift after child')
            result['status'] = 'verified-host-only'
            result['verified_tests'] = count
            result['evidence'] = evidence
            append_event(directory / 'COMMAND.jsonl', {'event': 'verification-result', 'status': 'verified-host-only',
                         'tests': count, 'evidence': evidence})
        exact(len(results), 4, 'four suite records required')
        exact(sum(item['launch_attempted'] is True for item in results), 4, 'four launch attempts required')
        exact(sum(item['known_started'] is True for item in results), 4, 'four known-started children required')
        exact(sum(item['verified_tests'] for item in results), 475, 'all test counts')
        stop_requested()
    except BaseException as error:
        failure = type(error).__name__ + ': ' + str(error)
        if results:
            child_failure(results[-1], 'suite-or-verification', error)
    source_rechecked = False
    try:
        exact(source_inputs(), inputs, 'final local source drift')
        exact(read_file(interpreter, 128 * MIB), interpreter_pin, 'final interpreter drift')
        source_rechecked = True
    except BaseException as error:
        failure = failure or ('final custody: ' + type(error).__name__ + ': ' + str(error))
    try:
        inventory = census(output, True)
        if failure is None:
            exact(inventory['file_count'] + 1, forecast, 'final expected file census')
    except BaseException as error:
        failure = failure or ('final census: ' + type(error).__name__ + ': ' + str(error))
        inventory = {'files': None, 'file_count': None, 'bytes': None,
                     'error': str(error), 'status': 'unavailable-or-over-limit'}
    elapsed = time.monotonic() - started
    if elapsed > STAGE_SECONDS or INTERRUPTED is not None:
        failure = failure or 'aggregate deadline or signal'
    known_started = sum(item['known_started'] is True for item in results)
    uncertain_launches = sum(item['launch_attempted'] is True and not item['known_started'] for item in results)
    report = {'format': 'ir8-host-suite-result/1', 'status': 'passed-host-only' if failure is None else 'failed-or-unknown',
              'failure': failure, 'elapsed_seconds': elapsed,
              'suite_attempts': len(results),
              'child_launch_attempts': sum(item['launch_attempted'] is True for item in results),
              'children_known_started': known_started, 'children_launch_uncertain': uncertain_launches,
              'children_started': known_started, 'children_started_count_complete': uncertain_launches == 0,
              'children_started_upper_bound': known_started + uncertain_launches,
              'expected_tests': 475, 'verified_tests': sum(x.get('verified_tests', 0) for x in results),
              'source_rechecked': source_rechecked, 'suites': results, 'inventory_excluding_this_report': inventory,
              'compiler_invoked': False, 'native_invoked': False, 'graph_executed': False,
              'model_executed': False, 'source_admitted': False,
              'owned_files_including_this_report': None if inventory['file_count'] is None else inventory['file_count'] + 1,
              'owned_bytes_including_this_report': None}
    if inventory['bytes'] is not None:
        for _ in range(10):
            size = inventory['bytes'] + len(encoded(report))
            if size == report['owned_bytes_including_this_report']:
                break
            report['owned_bytes_including_this_report'] = size
        if size > EVIDENCE_BYTES:
            report['status'] = 'failed-or-unknown'
            report['failure'] = report['failure'] or 'final evidence byte limit'
            report['owned_bytes_including_this_report'] = None
    try:
        write_new(output / 'RUN_RESULT.json', report)
    except BaseException as error:
        # Do not overwrite/retry a partial receipt. Preserve the full in-memory
        # result, including known/uncertain launch counters, on the outer stream.
        report['status'] = 'failed-or-unknown'
        report['failure'] = report['failure'] or 'final receipt write failed'
        report['final_receipt_error'] = type(error).__name__ + ': ' + str(error)
        report['owned_bytes_including_this_report'] = None
        try:
            sys.stderr.write(json.dumps(report, sort_keys=True) + '\n')
            sys.stderr.flush()
        except BaseException:
            pass  # Both evidence routes may be unavailable; never return success.
        return 1
    try:
        print(json.dumps({'status': report['status'], 'verified_tests': report['verified_tests'],
                          'children_started': report['children_started'],
                          'children_launch_uncertain': report['children_launch_uncertain'],
                          'result': str(output / 'RUN_RESULT.json')}, sort_keys=True))
    except BaseException:
        return 1
    return 0 if report['status'] == 'passed-host-only' else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (GateError, OSError, ValueError) as error:
        print('IR8 host runner refused/failed: ' + str(error), file=sys.stderr)
        raise SystemExit(2)
