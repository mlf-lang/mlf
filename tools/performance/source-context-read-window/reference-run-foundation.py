#!/usr/bin/env python3
"""UNEXECUTED DRAFT: real foundation package, same-binary representation study.

This is an inner study runner, not a resource/lock platform. The unchanged ROOT
guard owns .heavy-phase.lock; the qualified outer launcher owns .reproduction.lock.
The caller must authenticate the fresh current producer/build and run this under
those maintained controls. This file acquires neither lock a second time.

The 448 MiB partition is an admission reservation and before/after-stage sampled
acceptance budget, NOT a demonstrated instantaneous peak. Only the original ROOT
guard samples running processes/output. A separate explicit protocol-acceptance
gate stays false in the authored draft; it must not be silently enabled.
"""
from pathlib import Path
import errno
import argparse
import hashlib
import json
import os
import re
import resource
import stat
import subprocess
import time

ROOT = Path('/workspace/scratch/3f83e2ebe290/full88-work-20261031T0843Z')
PUBLICATION = ROOT / 'preflight/optimization-readonly-20261031/artifact-query-scratch-cleanup-20261101T1422Z/context-read-window-20261102T0406Z'
WORK = PUBLICATION / 'workload-foundation'
MIB = 1024**2
SHA = re.compile(r'[0-9a-f]{64}')
CRATE = 'mlf-foundation/0.3.0/library'
ORDER = ['coldA', 'materializeB', 'warmA1', 'warmB1', 'warmB2', 'warmA2',
         'changeA', 'changeB', 'changedwarmA', 'changedwarmB']
CLI_STAGES = [name for name in ORDER if name != 'materializeB']
ARMS = {name: ('B' if name in ['warmB1', 'warmB2', 'changeB', 'changedwarmB'] else 'A')
        for name in CLI_STAGES}
CHANGED = {'changeA', 'changeB', 'changedwarmA', 'changedwarmB'}
CAPS_MIB = {'cache_A': 128, 'cache_B': 128, 'helper': 32,
            'sources': 1, 'builtin': 2, 'metadata': 13,
            **{'output_' + name: 16 for name in CLI_STAGES}}
ORACLE = ROOT / 'preflight/optimization-readonly-20261031/guest-framework-output256-ci-fix-20261101T0724Z/candidate-run/foundation/artifact/unit.queries'
ORACLE_SHA = 'e329ad83074a301ad803965a035e895c27eeb33b668ba6ba3829ef038063583c'
PROJECTION_SHA = '7d65ce8b9a8718c932a7376583b2ea121a1ccca2133d5ffaa43582cfb2cf7762'
VERSION_RELATIVE = 'libraries/mlf-foundation/Bootstrap/Version.hs'
OLD_VERSION = b'version = "0.3.0"'
NEW_VERSION = b'version = "0.3.1"'


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def read_bounded(path, cap):
    path = Path(path)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
         path.resolve(strict=True) == path and before.st_size <= cap,
         'bounded real single-link file: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(cap + 1)
    after = path.lstat()
    attrs = ['st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns']
    need(len(data) == before.st_size and len(data) <= cap and
         all(getattr(before, key) == getattr(after, key) for key in attrs),
         'stable bounded read: ' + str(path))
    return data


def load_json(path, cap=2*MIB):
    return json.loads(read_bounded(path, cap), object_pairs_hook=unique_pairs)


def write_json_new(path, value, cap=2*MIB):
    data = (json.dumps(value, indent=2, ensure_ascii=False) + '\n').encode('utf-8')
    need(len(data) <= cap, 'bounded new JSON evidence')
    with Path(path).open('xb') as stream:
        stream.write(data)


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def unpack(text):
    values = []
    position = 0
    while position < len(text):
        colon = text.find(':', position)
        need(colon > position, 'scalar framing separator')
        number = text[position:colon]
        need(number.isascii() and number.isdecimal() and str(int(number)) == number,
             'canonical scalar length')
        size = int(number)
        end = colon + 1 + size
        need(end <= len(text), 'bounded scalar field')
        values.append(text[colon+1:end])
        position = end
    need(pack(values) == text, 'full framing roundtrip')
    return values


def direct_equal(left, right):
    """Actual streaming byte comparison, not merely equality of stored hashes."""
    with Path(left).open('rb') as a, Path(right).open('rb') as b:
        while True:
            x, y = a.read(65536), b.read(65536)
            if x != y:
                return False
            if not x:
                return True


def identity(path, digest=True):
    path = Path(path)
    info = path.lstat()
    directory = stat.S_ISDIR(info.st_mode)
    need(directory or stat.S_ISREG(info.st_mode), 'no link/special node: ' + str(path))
    need(directory or info.st_nlink == 1, 'no hidden hard-link sharing')
    row = {'directory': directory, 'bytes': info.st_size,
           'allocated': info.st_blocks*512, 'device': info.st_dev, 'inode': info.st_ino,
           'mode': info.st_mode, 'links': info.st_nlink,
           'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}
    if digest and not directory:
        row['sha256'] = sha_file(path)
    return row


def budget_snapshot_raw(out):
    """Before/after-stage samples only. This is NOT an in-flight 448 MiB guard."""
    roots = {'cache_A': [out/'cache/A'], 'cache_B': [out/'cache/B'],
             'helper': [WORK/'build', WORK/'home', WORK/'tmp', WORK/'cache'],
             'sources': [out/'source'], 'builtin': [out/'builtin'],
             **{'output_'+name: [out/'outputs'/name] for name in CLI_STAGES}}
    totals = {name: {'logical': 0, 'allocated': 0, 'nodes': 0} for name in CAPS_MIB}
    paths = [WORK, *sorted(WORK.rglob('*'))]
    need(len(paths) <= 8192, 'bounded complete study pathname population')
    for path in paths:
        row = identity(path, digest=False)
        category = 'metadata'
        matches = [name for name, entries in roots.items()
                   if any(path == root or path.is_relative_to(root) for root in entries)]
        need(len(matches) <= 1, 'disjoint budget partition')
        if matches:
            category = matches[0]
        total = totals[category]
        total['logical'] += 0 if row['directory'] else row['bytes']
        total['allocated'] += row['allocated']
        total['nodes'] += 1
    need(sum(CAPS_MIB.values()) == 448, 'complete identity reservation arithmetic')
    for name, values in totals.items():
        need(max(values['logical'], values['allocated']) <= CAPS_MIB[name]*MIB,
             'sampled category budget exceeded (failed evidence retained): ' + name)
    logical = sum(row['logical'] for row in totals.values())
    allocated = sum(row['allocated'] for row in totals.values())
    need(max(logical, allocated) <= 448*MIB, 'sampled complete study budget')
    return {'categories': totals, 'logical': logical, 'allocated': allocated,
            'sampling': 'before/after stage; NOT an instantaneous or continuous subroot bound'}


class GuardReceiptSnapshotRace(RuntimeError):
    def __init__(self, temporary, attempts):
        self.temporary = str(temporary)
        self.attempts = attempts
        super().__init__("guard receipt snapshot race exhausted: attempts=" +
                         str(attempts) + "; path=" + str(temporary))


def snapshot_with_guard_retry(sample, guard_directory):
    """Return one complete sample; retry ONLY the exact active tmp ENOENT.

    Three attempts include the first attempt. A partial account is discarded,
    never returned or carried into the next account. Non-racing initial samples
    need not wait for the parent's first receipt save after Popen.
    """
    guard = Path(guard_directory)
    if not guard.is_absolute() or guard != WORK / 'guard':
        raise RuntimeError('fixed absolute active guard directory required')

    def directory_identity():
        info = guard.lstat()
        if not stat.S_ISDIR(info.st_mode) or guard.resolve(strict=True) != guard:
            raise RuntimeError('guard directory is not a canonical real directory')
        return info.st_dev, info.st_ino

    initial = directory_identity()
    fd = os.open(guard, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = guard / 'bounded-receipt.json.tmp'
    observations = []

    def validate_directory():
        held = os.fstat(fd)
        if (not stat.S_ISDIR(held.st_mode) or
                (held.st_dev, held.st_ino) != initial or
                directory_identity() != initial):
            raise RuntimeError('active guard directory identity changed')

    def observe_renamed_receipt():
        info = os.stat('bounded-receipt.json', dir_fd=fd, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise RuntimeError('guard receipt is not a single-link regular file')
        return {'device': info.st_dev, 'inode': info.st_ino,
                'bytes': info.st_size, 'allocated': info.st_blocks * 512,
                'mode': info.st_mode, 'links': info.st_nlink,
                'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}

    try:
        for attempt in range(1, 4):
            validate_directory()
            try:
                value = sample()
            except FileNotFoundError as error:
                if (error.errno != errno.ENOENT or
                        error.filename != str(temporary) or
                        error.filename2 is not None):
                    raise
                validate_directory()
                # A legitimate rename has produced the final receipt. Missing,
                # directory, symlink or multi-link final entries fail here.
                observations.append(observe_renamed_receipt())
                validate_directory()
                if attempt == 3:
                    raise GuardReceiptSnapshotRace(temporary, attempt) from error
                continue
            validate_directory()
            if type(value) is not dict or 'guard_receipt_resampling' in value:
                raise RuntimeError('unexpected budget sample result schema')
            return {**value, 'guard_receipt_resampling': {
                'attempts': attempt, 'restarts': attempt - 1,
                'temporary_path': str(temporary),
                'observed_final_receipts_after_tmp_enoent': observations,
                'scope': 'complete sampled account; not atomic or hard isolation'}}
        raise AssertionError('unreachable bounded sampling loop')
    finally:
        os.close(fd)


def budget_snapshot(out):
    return snapshot_with_guard_retry(lambda: budget_snapshot_raw(out), WORK / "guard")

def cache_snapshot(directory, active_keys, compiler_sha):
    rows = {}
    paths = [directory, *sorted(directory.rglob('*'))]
    need(len(paths) <= 4096, 'bounded actual cache pathname population')
    for path in paths:
        row = identity(path, digest=False)
        relative = str(path.relative_to(directory))
        need(relative == '.' or '/' not in relative, 'flat private query cache')
        need(row['directory'] == (relative == '.'), 'no unexpected empty cache subdirectory')
        if not row['directory']:
            if relative == '.lock':
                need(row['bytes'] == 0, 'persistent empty cache lock')
                row['sha256'] = sha_bytes(b'')  # Never reopen a lock for accounting.
            else:
                row['sha256'] = sha_bytes(read_bounded(path, 16*MIB))
        rows[relative] = row
    need('.lock' in rows and not rows['.lock']['directory'], 'persistent cache lock exists')
    contexts = {}
    for name, row in rows.items():
        if row['directory'] or not name.endswith('.mlfqc'):
            continue
        match = re.fullmatch(r'context-([0-9a-f]{64})\.mlfqc', name)
        need(match is not None and match[1] == row['sha256'], 'actual CAS context SHA')
        text = read_bounded(directory/name, 16*MIB).decode('utf-8')
        fields = unpack(text)
        need(len(fields) == 2 and fields[0] == 'MLF-SOURCE-QUERY-CONTEXT-1', 'context carrier')
        contexts[name] = fields[1]
    records = {}
    for name, row in rows.items():
        if row['directory'] or name == '.lock' or name in contexts:
            continue
        need(name.endswith('.mlfq') and SHA.fullmatch(name[:-5]) is not None,
             'unexpected cache file, including residual scratch/staging: ' + name)
        fields = unpack(read_bounded(directory/name, 16*MIB).decode('utf-8'))
        reference = None
        if len(fields) == 4 and fields[0] == 'MLF-QUERY-CACHE-1':
            key = fields[1]
        elif len(fields) == 4 and fields[0] == 'MLF-QUERY-CACHE-3':
            need(SHA.fullmatch(fields[1]) is not None, 'safe context reference')
            reference = 'context-' + fields[1] + '.mlfqc'
            need(reference in contexts, 'all referenced context bytes present')
            compact = unpack(fields[2])
            need(len(compact) == 8, 'eight-field source key projection')
            key = pack(compact[:5] + [contexts[reference]] + compact[5:])
        else:
            raise RuntimeError('unexpected source record format: ' + name)
        complete = unpack(key)
        need(len(complete) == 9 and complete[0] == 'MLF-SOURCE-CRATE-QUERY-6', 'complete source key')
        need(complete[1] == CRATE and complete[2] == compiler_sha, 'actual crate/binary key identity')
        need(sha_bytes(key.encode('utf-8')) == name[:-5], 'independent full UTF8 key SHA filename')
        records[name] = {'format': fields[0], 'context': reference,
                         'full_key_utf8_bytes': len(key.encode('utf-8')),
                         'datatype_key_sha256': sha_bytes(complete[5].encode('utf-8'))}
    active = {value+'.mlfq' for value in active_keys.values()}
    need(len(active) == 504 and active.issubset(records), 'all 504 active records persisted')
    references = {records[name]['context'] for name in active if records[name]['context'] is not None}
    reachable = active | references
    return {'all_nodes': rows, 'records': records, 'active_records': sorted(active),
            'referenced_contexts': sorted(references), 'all_context_files': sorted(contexts),
            'retained_orphan_records': sorted(set(records)-active),
            'unreferenced_contexts': sorted(set(contexts)-references),
            'all_file_logical_bytes': sum(row['bytes'] for row in rows.values() if not row['directory']),
            'all_pathname_allocated_bytes': sum(row['allocated'] for row in rows.values()),
            'reachable_logical_bytes': sum(rows[name]['bytes'] for name in reachable),
            'reachable_file_allocated_bytes': sum(rows[name]['allocated'] for name in reachable),
            'atime_excluded': True, 'root_lock_orphans_included_in_complete_directory': True}


def stable_files(before, after, names=None):
    names = names if names is not None else [name for name, row in before['all_nodes'].items()
                                             if not row['directory']]
    for name in names:
        need(before['all_nodes'][name] == after['all_nodes'].get(name),
             'retained file bytes/identity/metadata changed: ' + name)


def context_distribution(groups, snapshot):
    sequence = [snapshot['records'][group['query_key']+'.mlfq']['context'] for group in groups]
    multiplicity = {}
    runs = []
    for reference in sequence:
        if reference is not None:
            multiplicity[reference] = multiplicity.get(reference, 0) + 1
        if runs and runs[-1]['context'] == reference:
            runs[-1]['length'] += 1
        else:
            runs.append({'context': reference, 'length': 1})
    return {'ordered_context_references': sequence, 'multiplicity': multiplicity, 'runs': runs,
            'adjacent_same_nonlegacy_reference_pairs': sum(a is not None and a == b
                                                          for a, b in zip(sequence, sequence[1:])),
            'interpretation': 'Static actual report/record layout, NOT measured memo hits or file reads. None is CACHE1.'}


def projection(groups):
    return [{'id': group['id'], 'members': group['members']} for group in groups]


def projection_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    plan_raw = read_bounded(args.plan.absolute(), 2*MIB)
    need(sha_bytes(plan_raw) == args.plan_sha256, 'exact approved execution-plan hash')
    plan = json.loads(plan_raw, object_pairs_hook=unique_pairs)
    # Reject draft/unknown producer before creating ANY run output.
    need(plan.get('approved_for_execution') is True, 'draft: no execution admission')
    need(plan.get('resource_protocol_accepted') is True, '448 MiB monitoring boundary unresolved')
    need(isinstance(plan.get('producer_state'), dict) and plan['producer_state'],
         'current fresh producer state must be independently authenticated')
    need(plan.get('qualified_outer_launcher') is not None, 'maintained guard/qualified-lock launcher required')
    need(plan['root'] == str(ROOT) and plan['work'] == str(WORK), 'fixed actual work roots')
    need(plan['stage_order'] == ORDER and plan['caps_mib'] == CAPS_MIB, 'frozen stages/complete budget')
    need(plan['resource_limits'] == {'seconds': 1800, 'address_space_mib': 6144,
         'rss_mib': 5120, 'root_output_mib': 8192, 'disk_free_mib': 4096,
         'mem_available_floor_bytes': 3072*MIB}, 'unchanged original resource limits')
    fixture = Path(plan['fixture'])
    source_root = Path(plan['source_root'])
    producer = Path(plan['producer'])
    need(fixture == WORK/'build/foundation-study' and fixture.resolve(strict=True) == fixture,
         'actual qualified wrapper, not an old producer alias')
    need(source_root.is_relative_to(PUBLICATION) and producer.is_relative_to(PUBLICATION),
         'current publication source/producer required, never M as current combined')
    need(source_root.resolve(strict=True) == source_root and producer.resolve(strict=True) == producer,
         'current source/producer real paths')
    receipt_sha = plan['producer_state'].get('receipt_sha256')
    need(isinstance(receipt_sha, str) and SHA.fullmatch(receipt_sha) is not None and
         sha_file(producer/'receipt.json') == receipt_sha, 'real current producer receipt binding')
    need(plan['pinned_inputs'].get(str(producer/'receipt.json')) == receipt_sha and
         str(source_root/'shared-sources.json') in plan['pinned_inputs'],
         'producer receipt and registered source manifest remain pinned throughout')
    expected_environment = {'HOME': str(WORK/'home'), 'TMPDIR': str(WORK/'tmp'),
                            'TMP': str(WORK/'tmp'), 'TEMP': str(WORK/'tmp'),
                            'XDG_CACHE_HOME': str(WORK/'cache'), 'LC_ALL': 'C.UTF-8',
                            'LANG': 'C.UTF-8', 'TZ': 'UTC', 'GHC_ENVIRONMENT': '-',
                            'GHCRTS': '', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONNOUSERSITE': '1'}
    for name, expected in expected_environment.items():
        need(os.environ.get(name) == expected, 'qualified private environment binding: '+name)
    fixture_sha = sha_file(fixture)
    need(SHA.fullmatch(plan['fixture_sha256']) is not None and fixture_sha == plan['fixture_sha256'],
         'approved current wrapper bytes')
    for path, expected in plan['pinned_inputs'].items():
        need(sha_file(Path(path)) == expected, 'pinned input changed: ' + path)
    need(sha_file(Path(__file__).absolute()) == plan['runner_sha256'], 'frozen runner bytes')
    need(sha_file(ORACLE) == ORACLE_SHA, 'independent historical population oracle')
    oracle = load_json(ORACLE, MIB)
    expected_population = projection(oracle['groups'])
    need(len(expected_population) == 504 and sha_bytes(projection_bytes(expected_population)) == PROJECTION_SHA,
         'frozen independent ordered population')
    version_token = '_'.join(str(ord(char)) for char in 'Bootstrap.Version')
    version_groups = [row for row in expected_population if any(version_token in name for name in row['members'])]
    need(len(version_groups) == 1 and len(version_groups[0]['members']) == 1, 'one authored Version group')
    version_id = version_groups[0]['id']
    out = WORK/'run'
    need(not out.exists() and not out.is_symlink(), 'fresh run directory; failed runs are never overwritten')
    out.mkdir()
    for path in [out/'cache', out/'outputs', out/'auxiliary', out/'metadata', out/'source', out/'builtin']:
        path.mkdir()
    record = {'format': 'foundation-504-source-cache-study-v1', 'complete': False,
              'plan_sha256': args.plan_sha256, 'fixture_sha256': fixture_sha,
              'stage_order': ORDER, 'stages': [], 'auxiliary_commands': [],
              'producer_state_from_qualified_launcher': plan['producer_state'],
              'ordinary_cli_implementation': 'runEntry Entry.main, unchanged owner objects',
              'binary_scope': 'study wrapper identity, not the ordinary emlf executable bytes',
              'error': None, 'post_integrity': False, 'interpretation': plan['interpretation']}

    def save_progress():
        data = (json.dumps(record, indent=2) + '\n').encode()
        need(len(data) <= 2*MIB, 'bounded progress receipt')
        (out/'metadata/progress.json').write_bytes(data)

    def pinned_check():
        need(sha_file(fixture) == fixture_sha, 'same binary throughout all stages')
        for path, expected in plan['pinned_inputs'].items():
            need(sha_file(Path(path)) == expected, 'pinned input changed: ' + path)

    source_rows = plan['source_inputs']
    need(len(source_rows) == 14 and len({row['module'] for row in source_rows}) == 14,
         'complete real foundation module inventory')
    original_sources = {}
    for row in source_rows:
        relative = Path(row['relative'])
        need(not relative.is_absolute() and '..' not in relative.parts and
             str(relative).startswith('libraries/mlf-foundation/Bootstrap/'), 'fixed real source location')
        data = read_bounded(source_root/relative, MIB)
        need(len(data) == row['bytes'] and sha_bytes(data) == row['sha256'], 'frozen real source bytes')
        target = out/'source'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        original_sources[row['relative']] = data
    need(sum(map(len, original_sources.values())) == 204977, 'complete real source byte population')
    version_path = out/'source'/VERSION_RELATIVE
    original_version = original_sources[VERSION_RELATIVE]
    need(original_version.count(OLD_VERSION) == 1 and len(OLD_VERSION) == len(NEW_VERSION),
         'single same-length authored mutation')
    changed_version = original_version.replace(OLD_VERSION, NEW_VERSION)
    with (out/'source/Version.hs.original').open('xb') as stream:
        stream.write(original_version)
    source_identities = {relative: identity(out/'source'/relative) for relative in original_sources}

    def check_sources(changed):
        for relative, original in original_sources.items():
            expected = changed_version if changed and relative == VERSION_RELATIVE else original
            need(read_bounded(out/'source'/relative, MIB) == expected, 'exact actual source state')
            if relative != VERSION_RELATIVE:
                need(identity(out/'source'/relative) == source_identities[relative], 'unmodified source identity')
        need(version_path.lstat().st_ino == source_identities[VERSION_RELATIVE]['inode'],
             'same Version source inode/path through in-place edit')

    builtin_prefix = out/'builtin/unit'
    cache = {'A': out/'cache/A', 'B': out/'cache/B'}
    specs = {}
    for arm in ['A', 'B']:
        entries = [pack([row['module'], str(out/'source'/row['relative'])])
                   for row in sorted(source_rows, key=lambda row: row['module'])]
        fields = ['MLF-CRATE-1', CRATE, '', 'false', pack(entries), '', str(cache[arm]), str(builtin_prefix)]
        path = out/'metadata'/('crate-'+arm+'.spec')
        with path.open('x', encoding='utf-8', newline='') as stream:
            stream.write(pack(fields))
        specs[arm] = path
    spec_hashes = {str(path): sha_file(path) for path in specs.values()}
    source_paths = [str(out/'source'/row['relative']) for row in source_rows]
    need(len(set(source_paths)) == 14, 'same unique absolute sources in all nine invocations')
    write_json_new(out/'metadata/source-identity.json', {
        'source_rows': source_rows, 'actual_paths': source_paths, 'initial_identities': source_identities,
        'mutation': {'path': str(version_path), 'before_sha256': sha_bytes(original_version),
                     'after_sha256': sha_bytes(changed_version), 'same_length': True,
                     'only_change': 'version string 0.3.0 -> 0.3.1; no crate identity/path change'},
        'spec_hashes': spec_hashes, 'historical_projection_sha256': PROJECTION_SHA})
    index_path = out/'metadata/cold.index'
    latest = {}
    original_artifacts = None
    changed_artifacts = None
    cold_report = None
    cold_keys = None
    builtin_identity = None

    def run_command(name, arguments, folder, timed, auxiliary=False):
        folder.mkdir(parents=True, exist_ok=False)
        budget_before = budget_snapshot(out)
        pinned_check()
        row = {'name': name, 'argv': [str(fixture), *map(str, arguments)],
               'cwd': str(out), 'timed_endpoint': timed, 'state': 'running',
               'timeout_seconds': plan['timeouts']['cli' if timed else 'auxiliary'],
               'budget_before': budget_before}
        (record['auxiliary_commands'] if auxiliary else record['stages']).append(row)
        save_progress()
        started = time.monotonic()
        usage_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            with (folder/'stdout').open('xb') as stdout, (folder/'stderr').open('xb') as stderr:
                result = subprocess.run(row['argv'], cwd=out, env=os.environ.copy(),
                                        stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                        timeout=row['timeout_seconds'], check=False)
            row['exit_code'] = result.returncode
        finally:
            # Endpoint timer ends at waited direct-child exit, BEFORE hashes,
            # snapshots, materialization, Version evaluation or source audits.
            row['subprocess_wall_seconds'] = time.monotonic()-started
            usage_after = resource.getrusage(resource.RUSAGE_CHILDREN)
            row['waited_child_cpu_seconds'] = {'user': usage_after.ru_utime-usage_before.ru_utime,
                                              'system': usage_after.ru_stime-usage_before.ru_stime}
            row['state'] = 'child-exited-not-qualified'
            for stream in ['stdout', 'stderr']:
                path = folder/stream
                if path.exists():
                    row[stream] = {'path': str(path), **identity(path)}
            save_progress()
        need(row['exit_code'] == 0 and row['stderr']['bytes'] == 0, 'command exit/stderr: '+name)
        row['budget_after'] = budget_snapshot(out)
        pinned_check()
        return row

    def verify_builtin_unchanged():
        if builtin_identity is not None:
            for path, before in builtin_identity.items():
                need(identity(Path(path)) == before, 'fixed builtin input bytes/stat changed')

    def check_query(stage):
        arm, changed = ARMS[stage], stage in CHANGED
        check_sources(changed)
        need(all(sha_file(Path(path)) == digest for path, digest in spec_hashes.items()), 'immutable source specs')
        verify_builtin_unchanged()
        prefix = out/'outputs'/stage/'unit'
        row = run_command(stage, ['--compile-crate', specs[arm], '-o', prefix], prefix.parent, True)
        report = load_json(Path(str(prefix)+'.queries'), 2*MIB)
        need(report['format'] == 1 and report['crate'] == CRATE, 'actual official QueryReport')
        groups = report['groups']
        need(projection(groups) == expected_population, 'independent ordered 504-group population')
        need(all(type(group['cached']) is bool for group in groups), 'actual Boolean cache flags')
        keys = {group['id']: group['query_key'] for group in groups}
        need(len(keys) == 504 and len(set(keys.values())) == 504 and
             all(SHA.fullmatch(value) is not None for value in keys.values()), '504 unique actual query keys')
        inferred = sum(not group['cached'] for group in groups)
        reused = sum(group['cached'] for group in groups)
        expected_counts = (504, 0) if stage == 'coldA' else (1, 503) if stage in ['changeA', 'changeB'] else (0, 504)
        need((report['inferred_groups'], report['reused_groups']) == (inferred, reused) == expected_counts,
             'predeclared real-source cache counts: '+stage)
        if stage in ['changeA', 'changeB']:
            need([group['id'] for group in groups if not group['cached']] == [version_id],
                 'only Version group is freshly inferred')
        artifacts = {suffix: {'path': str(prefix)+suffix, **identity(Path(str(prefix)+suffix))}
                     for suffix in ['.mlfci', '.mlfco', '.queries']}
        snapshot = cache_snapshot(cache[arm], keys, fixture_sha)
        distribution = context_distribution(groups, snapshot)
        snapshot_path = out/'metadata'/(stage+'.snapshot.json')
        write_json_new(snapshot_path, {'cache': snapshot, 'context_distribution': distribution}, 2*MIB)
        row.update({'report': artifacts['.queries'], 'artifacts': artifacts,
                    'snapshot_path': str(snapshot_path), 'snapshot_sha256': sha_file(snapshot_path),
                    'counts': {'inferred': inferred, 'reused': reused}})
        if stage == 'coldA':
            packed_index = pack(['MLF-FOUNDATION-STUDY-INDEX-1',
                                 pack([pack([group['id'], pack(group['members']), group['query_key']])
                                       for group in groups])])
            with index_path.open('x', encoding='utf-8', newline='') as stream:
                stream.write(packed_index)
        audit_evidence = out/'metadata'/(stage+'.version')
        audit = run_command('version-'+stage,
                            ['--study-version', prefix, index_path, 'changed' if changed else 'original', audit_evidence],
                            out/'auxiliary'/('version-'+stage), False, True)
        expected_version = '0.3.1' if changed else '0.3.0'
        need(unpack(read_bounded(audit_evidence, 4096).decode('utf-8')) ==
             ['MLF-FOUNDATION-VERSION-1', '504', expected_version], 'independent final Version oracle')
        audit['state'] = 'passed'
        row['version_evidence'] = {'path': str(audit_evidence), **identity(audit_evidence)}
        check_sources(changed)
        verify_builtin_unchanged()
        return row, report, keys, snapshot, artifacts

    error = None
    try:
        save_progress()
        setup = run_command('prepare-builtin', ['--study-builtin', builtin_prefix],
                            out/'auxiliary/prepare-builtin', False, True)
        builtin_identity = {str(builtin_prefix)+suffix: identity(Path(str(builtin_prefix)+suffix))
                            for suffix in ['.mlfci', '.mlfco', '.lock']}
        setup['prepared_inputs'] = builtin_identity
        setup['state'] = 'passed'
        for stage in ORDER:
            if stage == 'materializeB':
                evidence = out/'metadata/materializeB.conversion'
                row = run_command(stage,
                    ['--study-materialize', cache['A'], cache['B'], index_path,
                     out/'outputs/coldA/unit', evidence], out/'auxiliary/materializeB', False)
                after_a = cache_snapshot(cache['A'], cold_keys, fixture_sha)
                need(after_a == latest['A']['snapshot'], 'materializer did not mutate source A')
                b = cache_snapshot(cache['B'], cold_keys, fixture_sha)
                need(len(b['records']) == 504 and not b['all_context_files'] and not b['retained_orphan_records'] and
                     all(item['format'] == 'MLF-QUERY-CACHE-1' for item in b['records'].values()),
                     'actual complete self-contained legacy B')
                converted = unpack(read_bounded(evidence, 2*MIB).decode('utf-8'))
                need(len(converted) == 2 and converted[0] == 'MLF-FOUNDATION-CONVERSION-1', 'conversion evidence format')
                conversion_rows = [unpack(value) for value in unpack(converted[1])]
                need(len(conversion_rows) == 504, 'all real raw records converted')
                for item, group in zip(conversion_rows, cold_report['groups']):
                    need(len(item) == 6 and item[:3] == [group['id'], pack(group['members']), group['query_key']],
                         'conversion exact actual ordered source index')
                    name = group['query_key']+'.mlfq'
                    need(item[3] == after_a['records'][name]['format'] and
                         int(item[4]) == after_a['all_nodes'][name]['bytes'] and
                         int(item[5]) == b['all_nodes'][name]['bytes'], 'actual persisted conversion sizes/formats')
                path = out/'metadata/materializeB.snapshot.json'
                write_json_new(path, {'cache': b}, 2*MIB)
                row.update({'snapshot_path': str(path), 'snapshot_sha256': sha_file(path),
                            'conversion': {'path': str(evidence), **identity(evidence)},
                            'semantic_scope': 'wire admission/raw roundtrip only; real against-source admission is warmB1'})
                latest['B'] = {'snapshot': b, 'keys': cold_keys}
            else:
                if stage == 'changeA':
                    check_sources(False)
                    # Same path and inode, same byte length, only one literal.
                    with version_path.open('r+b') as stream:
                        stream.write(changed_version)
                        stream.truncate()
                    check_sources(True)
                row, report, keys, snapshot, artifacts = check_query(stage)
                arm = ARMS[stage]
                if stage == 'coldA':
                    need(not snapshot['retained_orphan_records'], 'cold A no preexisting query objects')
                    need(any(item['format'] == 'MLF-QUERY-CACHE-3' for item in snapshot['records'].values()),
                         'real workload actually exercises compact source records')
                    need(snapshot['records'][keys[version_id]+'.mlfq']['format'] == 'MLF-QUERY-CACHE-3',
                         'the frozen Version source group exercises the compact source writer')
                    cold_report, cold_keys, original_artifacts = report, keys, artifacts
                else:
                    need(report['semantic_fingerprint'] == cold_report['semantic_fingerprint'] and
                         [group['semantic_fingerprint'] for group in report['groups']] ==
                         [group['semantic_fingerprint'] for group in cold_report['groups']],
                         'same ABI/type fingerprints, not a global body fingerprint')
                    if stage in CHANGED:
                        need([identity for identity in cold_keys if keys[identity] != cold_keys[identity]] == [version_id],
                             'exactly one changed full semantic key')
                        old_name, new_name = cold_keys[version_id]+'.mlfq', keys[version_id]+'.mlfq'
                        need(snapshot['records'][new_name]['datatype_key_sha256'] ==
                             snapshot['records'][old_name]['datatype_key_sha256'], 'Version change leaves datatype key context equal')
                        need(snapshot['records'][new_name]['format'] == 'MLF-QUERY-CACHE-3',
                             'changed Version is written by the actual new source writer')
                        need(snapshot['retained_orphan_records'] == [old_name] and len(snapshot['records']) == 505,
                             'one retained old Version record, no hidden cleanup')
                        if arm == 'B':
                            active_formats = [snapshot['records'][name]['format'] for name in snapshot['active_records']]
                            need(active_formats.count('MLF-QUERY-CACHE-1') == 503 and
                                 active_formats.count('MLF-QUERY-CACHE-3') == 1 and
                                 len(snapshot['all_context_files']) == 1,
                                 'legacy arm is explicitly 503 old + one new active record with its context')
                    else:
                        need(keys == cold_keys and not snapshot['retained_orphan_records'], 'all original warm keys/hits')
                    stable_files(latest[arm]['snapshot'], snapshot)
                    if stage in ['changeA', 'changeB']:
                        names = [key+'.mlfq' for identity, key in cold_keys.items() if identity != version_id]
                        need(len(names) == 503, '503 unchanged record identity inventory')
                        stable_files(latest[arm]['snapshot'], snapshot, names)
                    expected_artifacts = changed_artifacts if stage in CHANGED and changed_artifacts else original_artifacts
                    if stage == 'changeA':
                        need(not direct_equal(artifacts['.mlfco']['path'], original_artifacts['.mlfco']['path']),
                             'actual final body changed, not merely a cache flag')
                        changed_artifacts = artifacts
                    else:
                        for suffix in ['.mlfci', '.mlfco']:
                            need(direct_equal(artifacts[suffix]['path'], expected_artifacts[suffix]['path']),
                                 'full direct final artifact bytes: '+stage+suffix)
                        row['direct_final_bytes_equal'] = True
                latest[arm] = {'snapshot': snapshot, 'keys': keys}
            row['state'] = 'passed'
            row['poststage_budget'] = budget_snapshot(out)
            save_progress()
        need([row['name'] for row in record['stages']] == ORDER and len(record['stages']) == 10,
             'exact frozen ten study stages, auxiliary work not counted as samples')
        need(len(record['auxiliary_commands']) == 10, 'one untimed builtin + nine untimed Version/final audits')
        check_sources(True)
        verify_builtin_unchanged()
        pinned_check()
        record['post_integrity'] = True
        # This sample precedes the last progress/possible entry-failure writes.
        # The qualified outer launcher owns the post-receipt ROOT/W terminal audit.
        record['final_budget_before_terminal_receipts'] = budget_snapshot(out)
        record['complete'] = True
    except BaseException as exc:
        error = type(exc).__name__+': '+str(exc)
        record['complete'] = False
        record['error'] = error
        # Do not remove partial cache/output/scratch/failed evidence here.
    finally:
        save_progress()
    need(error is None and record['complete'], error or 'study incomplete')
    print(json.dumps({'complete': True, 'groups': 504, 'study_stages': 10,
                      'real_cli_executions': 9, 'untimed_auxiliary_commands': 10}))


if __name__ == '__main__':
    try:
        main()
    except BaseException as exc:
        # Cover setup/admission-to-copy failures before the main progress loop.
        # Never create a run identity for a rejected draft, and never overwrite
        # an earlier failure or any raw/final capture.
        out = WORK/'run'
        failure_path = out/'entry-failure.json'
        if out.is_dir() and not out.is_symlink() and not failure_path.exists():
            try:
                write_json_new(failure_path, {'complete': False,
                    'error': type(exc).__name__+': '+str(exc),
                    'scope': 'inner runner; outer maintained guard owns process cleanup'}, 65536)
            except BaseException:
                pass
        raise
