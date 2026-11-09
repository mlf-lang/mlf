#!/usr/bin/env python3
"""Fixed ten-process synthetic source-query format study, NOT a benchmark claim.

Only run a separately authenticated freshly built fixture under the approved
outer guard. Never compile, install, rerun a target, reduce 64, or drop OS caches.
The same fixture/compiler identity is used for both representations. Legacy
records are materialized from new cold raw objects, not compiled by an old tool.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import resource
import stat
import subprocess
import time

NAMES = [f'v{i:03}' for i in range(64)]
SHA = re.compile('[0-9a-f]{64}')
CACHE_CAP = 24 * 1024**2
ORDER = ['coldA', 'materializeB', 'warmA1', 'warmB1', 'warmB2', 'warmA2',
         'changeA', 'changeB', 'changedwarmA', 'changedwarmB']


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            digest.update(block)
    return digest.hexdigest()


def unpack(text):
    result = []
    while text:
        count, separator, rest = text.partition(':')
        require(separator and count.isascii() and count.isdecimal(), 'scalar framing')
        size = int(count)
        require(str(size) == count and size <= len(rest), 'canonical scalar count')
        result.append(rest[:size])
        text = rest[size:]
    return result


def pack(values):
    return ''.join(str(len(value)) + ':' + value for value in values)


def bounded_bytes(path, maximum):
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= maximum,
            'bounded regular input: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(maximum + 1)
    require(len(data) == s.st_size and len(data) <= maximum, 'bounded stable read')
    return data


def cache_snapshot(root, active_keys):
    """All physical nodes + separately computed active reachability; no cleanup."""
    rows, logical, allocated = {}, 0, 0
    paths = [root, *sorted(root.rglob('*'))]
    require(len(paths) <= 512, 'fixed-workload private cache path cap')
    for path in paths:
        s = path.lstat()
        is_file, is_dir = stat.S_ISREG(s.st_mode), stat.S_ISDIR(s.st_mode)
        require(is_file or is_dir, 'no cache symlink or special node')
        require(not is_file or s.st_nlink == 1, 'no hidden hard-link sharing')
        allocated += s.st_blocks * 512
        logical += s.st_size if is_file else 0
        row = {'directory': is_dir, 'bytes': s.st_size, 'allocated': s.st_blocks * 512,
               'device': s.st_dev, 'inode': s.st_ino, 'mode': s.st_mode,
               'links': s.st_nlink, 'mtime_ns': s.st_mtime_ns, 'ctime_ns': s.st_ctime_ns}
        rows[str(path.relative_to(root))] = row
    require(logical <= CACHE_CAP and allocated <= CACHE_CAP, 'per-cache terminal budget')
    context_bodies = {}
    records = {}
    for relative, row in rows.items():
        if row['directory']:
            continue
        require('/' not in relative, 'no nested cache payload expected')
        if relative == '.lock':
            require(row['bytes'] == 0, 'zero-byte lock')
            row['sha256'] = sha_bytes(b'')  # Metadata only; never reopen .lock.
        else:
            data = bounded_bytes(root / relative, 8 * 1024**2)
            row['sha256'] = sha_bytes(data)
            if relative.endswith('.mlfqc'):
                match = re.fullmatch(r'context-([0-9a-f]{64})\.mlfqc', relative)
                require(match is not None and match[1] == row['sha256'], 'actual context SHA filename')
                decoded = data.decode('utf-8')
                carrier = unpack(decoded)
                require(len(carrier) == 2 and carrier[0] == 'MLF-SOURCE-QUERY-CONTEXT-1'
                        and pack(carrier) == decoded, 'canonical context carrier')
                context_bodies[relative] = carrier[1]
            elif relative.endswith('.mlfq'):
                require(SHA.fullmatch(relative[:-5]), 'query SHA filename')
            else:
                raise ValueError('unexpected physical cache file (including scratch/staging): ' + relative)
    active_paths = {key + '.mlfq' for key in active_keys.values()}
    require(len(active_paths) == 64, 'exact 64 active query paths')
    referenced = set()
    for relative, row in rows.items():
        if row['directory'] or not relative.endswith('.mlfq'):
            continue
        data = bounded_bytes(root / relative, 8 * 1024**2)
        text = data.decode('utf-8')
        fields = unpack(text)
        require(fields and pack(fields) == text, 'canonical query carrier')
        reference = None
        if fields[0] == 'MLF-QUERY-CACHE-1':
            require(len(fields) == 4, 'self-contained legacy record shape')
            full_key = fields[1]
        elif fields[0] == 'MLF-QUERY-CACHE-3':
            require(len(fields) == 4 and SHA.fullmatch(fields[1]), 'compact query reference')
            reference = 'context-' + fields[1] + '.mlfqc'
            require(reference in context_bodies, 'physical referenced context exists')
            compact = unpack(fields[2])
            require(len(compact) == 8 and pack(compact) == fields[2], 'canonical eight-field projection')
            full_key = pack(compact[:5] + [context_bodies[reference]] + compact[5:])
        else:
            raise ValueError('unexpected format in fixed experiment')
        key_fields = unpack(full_key)
        require(len(key_fields) == 9 and key_fields[0] == 'MLF-SOURCE-CRATE-QUERY-6'
                and pack(key_fields) == full_key, 'complete canonical nine-field key')
        encoded_key = full_key.encode('utf-8')
        require(sha_bytes(encoded_key) == relative[:-5], 'independent full-key UTF8 SHA equals filename')
        records[relative] = {'format': fields[0], 'context': reference,
                             'full_key_utf8_bytes': len(encoded_key), 'full_key_sha256': relative[:-5]}
        if relative in active_paths and reference:
            referenced.add(reference)
    require(active_paths.issubset(records), 'all active queries persisted')
    reachable = active_paths | referenced
    return {'all_nodes': rows, 'all_file_logical_bytes': logical,
            'all_pathname_conservative_allocated_bytes': allocated,
            'records': records, 'all_context_files': sorted(context_bodies),
            'active_records': sorted(active_paths), 'referenced_contexts': sorted(referenced),
            'retained_orphan_records': sorted(set(records) - active_paths),
            'unreferenced_contexts': sorted(set(context_bodies) - referenced),
            'reachable_logical_bytes': sum(rows[name]['bytes'] for name in reachable),
            'reachable_file_allocated_bytes': sum(rows[name]['allocated'] for name in reachable),
            'directory_root_and_lock_included_in_physical_not_payload_reachability': True,
            'atime_not_compared_because_reading_can_update_it': True}


def stable_files(before, after, names):
    for name in names:
        require(before['all_nodes'][name] == after['all_nodes'][name], 'file content/metadata changed: ' + name)


def publication_delta(before, after):
    old = {n: r for n, r in before['all_nodes'].items() if not r['directory']}
    new = {n: r for n, r in after['all_nodes'].items() if not r['directory']}
    created, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = sorted(n for n in set(old) & set(new) if old[n] != new[n])
    return {'created_files': created, 'removed_files': removed, 'changed_existing_files': changed,
            'observed_created_or_rewritten_file_bytes': sum(new[n]['bytes'] for n in created + changed),
            'logical_delta': after['all_file_logical_bytes'] - before['all_file_logical_bytes'],
            'physical_allocated_delta': after['all_pathname_conservative_allocated_bytes'] - before['all_pathname_conservative_allocated_bytes'],
            'not_cumulative_IO_or_transient_staging_write_bytes': True}


def shape(snapshot, legacy, compact, contexts, orphans):
    formats = [snapshot['records'][name]['format'] for name in snapshot['active_records']]
    require(formats.count('MLF-QUERY-CACHE-1') == legacy and formats.count('MLF-QUERY-CACHE-3') == compact,
            'exact active format population')
    require(len(snapshot['all_context_files']) == contexts and not snapshot['unreferenced_contexts'], 'exact physical context population')
    require(len(snapshot['records']) == 64 + orphans and len(snapshot['retained_orphan_records']) == orphans,
            'exact retained orphan population')
    require(len(snapshot['all_nodes']) == 1 + (64 + orphans) + contexts + 1,
            'complete cache tree has only root, exact records/contexts, and persistent lock')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    fixture, out = args.fixture.absolute(), args.output.absolute()
    require(fixture.resolve(strict=True) == fixture and stat.S_ISREG(fixture.lstat().st_mode), 'qualified real fixture path')
    require(not out.exists() and out.parent.resolve(strict=True) == out.parent, 'fresh real output')
    require(not fixture.is_relative_to(out), 'fixture outside fresh evidence tree')
    out.mkdir()
    (out / 'A').mkdir()
    (out / 'B').mkdir()
    cache = {'A': out / 'A/cache', 'B': out / 'B/cache'}
    record = {'format': 1, 'complete': False, 'fixture': str(fixture), 'fixture_sha256': sha_file(fixture),
              'stage_order': ORDER, 'commands': [], 'stages': {},
              'workload': {'groups': 64, 'names': NAMES, 'values': '1000+i', 'only_change': 'v000 -> 2000'},
              'limits': {'each_target_seconds': 180, 'combined_cache_logical_and_allocated_bytes': CACHE_CAP,
                         'cache_cap_is_poststage_not_continuous_peak': True,
                         'outer_guard_and_authenticated_build_required': True},
              'interpretation': [
                  'Synthetic controlled Query source groups, not 12-real-sample expansion or a whole-project workload.',
                  'Legacy baseline materialized by this same new compiler from actual cold raw objects; no old-compiler cold timing.',
                  'One fixed ABBA warm sequence; OS caches not cleared; no statistical speedup claim.',
                  'Subprocess wall includes plan construction, real driver, equal 64-value checked interpretation, and necessary final/report output.',
                  'Q CPU picoseconds bracket the IO action and Either discrimination, not wall time or full forcing of lazy terms; excludes helper child CPU.',
                  'Full cache snapshots, UTF8 key hashing and physical accounting happen after subprocess timing.',
                  'One change on legacy arm naturally writes CACHE3, with 63 active CACHE1 and one retained old orphan; not pure legacy rewriting.',
                  'Physical terminal files do not measure transient allocation peaks or cumulative write syscalls; outer guard accounts whole identity.',
                  'Failure stops all later stages; no automatic retries, smaller population, or deletion of failed evidence.']}
    current_row = None

    def save():
        data = (json.dumps(record, indent=2) + '\n').encode()
        require(len(data) <= 2 * 1024**2, 'bounded report metadata')
        (out / 'receipt.json').write_bytes(data)

    def run(name, arguments):
        nonlocal current_row
        require(name == ORDER[len(record['commands'])], 'frozen ten-stage order')
        row = {'name': name, 'argv': [str(fixture), *map(str, arguments)], 'timeout_seconds': 180, 'state': 'running'}
        current_row = row
        record['commands'].append(row)
        save()
        failure = None
        cpu_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.monotonic()
        try:
            with (out / (name + '.stdout')).open('xb') as stdout, (out / (name + '.stderr')).open('xb') as stderr:
                result = subprocess.run(row['argv'], cwd=out, env=os.environ.copy(), stdout=stdout, stderr=stderr, timeout=180)
            row['exit_code'] = result.returncode
        except BaseException as error:
            failure = error
            row['error'] = type(error).__name__ + ': ' + str(error)
            row['timed_out'] = isinstance(error, subprocess.TimeoutExpired)
        finally:
            # Stop the target timer before capture hashing or snapshot work.
            row['subprocess_wall_seconds'] = time.monotonic() - started
            cpu_after = resource.getrusage(resource.RUSAGE_CHILDREN)
            row['waited_child_cpu_seconds'] = {'user': cpu_after.ru_utime - cpu_before.ru_utime,
                                              'system': cpu_after.ru_stime - cpu_before.ru_stime}
            row['state'] = 'target-exited-not-qualified'
            for suffix in ('stdout', 'stderr'):
                path = out / (name + '.' + suffix)
                if path.exists():
                    row[suffix] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha_file(path)}
            save()
        if failure is not None:
            raise failure
        require(row['exit_code'] == 0 and row['stderr']['bytes'] == 0, 'target exit/stderr: ' + name)
        require(row['stdout']['bytes'] <= 65536, 'bounded target report; full rejected capture preserved')
        return bounded_bytes(out / (name + '.stdout'), 65536), row

    def parse_query(name, arm, changed):
        prefix = out / name
        raw, row = run(name, ['query64', cache[arm], prefix, 'changed' if changed else 'original'])
        post_started = time.monotonic()
        report = json.loads(raw)
        require(report.get('format') == 1 and report.get('crate') == 'query-context-64', 'actual QueryReport')
        groups = report.get('groups', [])
        require(len(groups) == 64 and all(len(group.get('members', [])) == 1 for group in groups), '64 singleton groups')
        keys = {group['members'][0]: group['query_key'] for group in groups}
        require(sorted(keys) == NAMES and len(set(keys.values())) == 64 and all(SHA.fullmatch(key) for key in keys.values()),
                'exact unique members and keys')
        require(len({group['id'] for group in groups}) == 64, 'unique group identities')
        inferred = sum(not group['cached'] for group in groups)
        reused = sum(group['cached'] for group in groups)
        require(report['inferred_groups'] == inferred and report['reused_groups'] == reused and inferred + reused == 64,
                'full per-group cache flags match counts')
        values_raw = bounded_bytes(Path(str(prefix) + '.values'), 65536)
        values = [unpack(row) for row in unpack(values_raw.decode('utf-8'))]
        require(len(values) == 64 and all(len(row) == 2 for row in values), '64 evaluated values')
        observed = dict(values)
        expected = {f'v{i:03}': str(2000 if changed and i == 0 else 1000 + i) for i in range(64)}
        require(observed == expected, 'independently checked/runtime-evaluated integer semantics')
        index_raw = bounded_bytes(Path(str(prefix) + '.index'), 65536)
        index = unpack(index_raw.decode('utf-8'))
        require(len(index) == 2 and index[0] == 'MLF-CONTEXT-64-INDEX-1', 'actual materialization index')
        index_rows = [unpack(text) for text in unpack(index[1])]
        require(index_rows == [[group['id'], group['members'][0], group['query_key']] for group in groups], 'index exactly actual report')
        cpu_text = bounded_bytes(Path(str(prefix) + '.q-cpu-picoseconds'), 128).decode('ascii').strip()
        require(cpu_text.isdecimal(), 'nonnegative Q-call CPU sample')
        final_bytes = bounded_bytes(Path(str(prefix) + '.objects'), 8 * 1024**2)
        require(len(unpack(final_bytes.decode('utf-8'))) == 64, '64 serialized final artifacts')
        snapshot = cache_snapshot(cache[arm], keys)
        evidence = {'arm': arm, 'changed': changed, 'query_report': report, 'keys': keys,
                    'final_artifact': {'path': str(prefix) + '.objects', 'bytes': len(final_bytes), 'sha256': sha_bytes(final_bytes)},
                    'runtime_values': observed, 'q_action_cpu_picoseconds': int(cpu_text),
                    'index_sha256': sha_bytes(index_raw), 'values_sha256': sha_bytes(values_raw), 'cache': snapshot}
        row['postprocess_snapshot_hash_seconds'] = time.monotonic() - post_started
        record['stages'][name] = evidence
        return evidence, row

    def finish(row):
        row['state'] = 'passed'
        save()

    def check_budget(snapshots):
        logical = sum(s['all_file_logical_bytes'] for s in snapshots.values())
        allocated = sum(s['all_pathname_conservative_allocated_bytes'] for s in snapshots.values())
        require(logical <= CACHE_CAP and allocated <= CACHE_CAP, 'combined complete cache terminal budget')
        record['last_complete_cache_totals'] = {'logical': logical, 'allocated': allocated,
                                               'scope': 'both complete cache directories; all records, contexts, locks, directories and orphan records'}

    save()
    try:
        cold, row = parse_query('coldA', 'A', False)
        require((cold['query_report']['inferred_groups'], cold['query_report']['reused_groups']) == (64, 0), 'actual compact cold')
        shape(cold['cache'], 0, 64, 1, 0)
        snapshots = {'A': cold['cache']}
        check_budget(snapshots)
        finish(row)
        raw, row = run('materializeB', ['materialize64', cache['A'], cache['B'], out / 'coldA.index', out / 'materializeB'])
        post_started = time.monotonic()
        require(raw == b'PASS materialized 64 self-contained legacy records\n', 'materializer terminal marker')
        source_after = cache_snapshot(cache['A'], cold['keys'])
        require(source_after == cold['cache'], 'source compact cache bytes and identity stats unchanged by materialization')
        legacy = cache_snapshot(cache['B'], cold['keys'])
        shape(legacy, 64, 0, 0, 0)
        conversion = unpack(bounded_bytes(out / 'materializeB.conversion', 65536).decode('utf-8'))
        require(len(conversion) == 2 and conversion[0] == 'MLF-CONTEXT-64-CONVERSION-1', 'conversion evidence')
        converted = [unpack(text) for text in unpack(conversion[1])]
        require(len(converted) == 64 and all(len(value) == 5 for value in converted), '64 conversion rows')
        require([(v[0], v[1], v[2]) for v in converted] ==
                [(g['id'], g['members'][0], g['query_key']) for g in cold['query_report']['groups']], 'conversion exactly cold inventory')
        for value in converted:
            filename = value[2] + '.mlfq'
            require(int(value[3]) == cold['cache']['all_nodes'][filename]['bytes'] and
                    int(value[4]) == legacy['all_nodes'][filename]['bytes'], 'persisted UTF8 conversion sizes')
        row['postprocess_snapshot_hash_seconds'] = time.monotonic() - post_started
        snapshots['B'] = legacy
        record['stages']['materializeB'] = {'cache_A_unchanged': source_after, 'cache_B': legacy,
                                           'conversion_rows': converted, 'semantic_scope': 'actual Q/U decoding, old encoding, write and old readback; actual production warm admission follows'}
        check_budget(snapshots)
        finish(row)
        latest = {'A': cold, 'B': {'cache': legacy, 'keys': cold['keys'], 'final_artifact': cold['final_artifact']}}
        for name, arm in [('warmA1', 'A'), ('warmB1', 'B'), ('warmB2', 'B'), ('warmA2', 'A')]:
            value, row = parse_query(name, arm, False)
            require((value['query_report']['inferred_groups'], value['query_report']['reused_groups']) == (0, 64), 'actual warm hits all groups')
            require(value['keys'] == cold['keys'] and value['final_artifact']['sha256'] == cold['final_artifact']['sha256'], 'warm complete key and final equality')
            shape(value['cache'], 64 if arm == 'B' else 0, 0 if arm == 'B' else 64, 0 if arm == 'B' else 1, 0)
            stable_files(latest[arm]['cache'], value['cache'], [n for n, r in latest[arm]['cache']['all_nodes'].items() if not r['directory']])
            latest[arm], snapshots[arm] = value, value['cache']
            check_budget(snapshots)
            finish(row)
        changed = {}
        for name, arm in [('changeA', 'A'), ('changeB', 'B')]:
            before = latest[arm]
            value, row = parse_query(name, arm, True)
            require((value['query_report']['inferred_groups'], value['query_report']['reused_groups']) == (1, 63), 'one actual changed group')
            require(value['final_artifact']['sha256'] != cold['final_artifact']['sha256'], 'change is not a no-op')
            require([n for n in NAMES if value['keys'][n] != cold['keys'][n]] == ['v000'], 'only v000 full key changes')
            shape(value['cache'], 63 if arm == 'B' else 0, 1 if arm == 'B' else 64, 1, 1)
            require(value['cache']['retained_orphan_records'] == [cold['keys']['v000'] + '.mlfq'], 'old v000 retained as orphan')
            stable_files(before['cache'], value['cache'], [n for n, r in before['cache']['all_nodes'].items() if not r['directory']])
            value['one_change_publication_delta'] = publication_delta(before['cache'], value['cache'])
            changed[arm], latest[arm], snapshots[arm] = value, value, value['cache']
            check_budget(snapshots)
            finish(row)
        require(changed['A']['keys'] == changed['B']['keys'] and
                changed['A']['final_artifact']['sha256'] == changed['B']['final_artifact']['sha256'], 'changed arms exact keys and final equality')
        for name, arm in [('changedwarmA', 'A'), ('changedwarmB', 'B')]:
            value, row = parse_query(name, arm, True)
            require((value['query_report']['inferred_groups'], value['query_report']['reused_groups']) == (0, 64), 'changed warm all hits')
            require(value['keys'] == changed[arm]['keys'] and value['final_artifact']['sha256'] == changed[arm]['final_artifact']['sha256'], 'changed warm exact final and keys')
            shape(value['cache'], 63 if arm == 'B' else 0, 1 if arm == 'B' else 64, 1, 1)
            stable_files(latest[arm]['cache'], value['cache'], [n for n, r in latest[arm]['cache']['all_nodes'].items() if not r['directory']])
            latest[arm], snapshots[arm] = value, value['cache']
            check_budget(snapshots)
            finish(row)
        require(len(record['commands']) == 10 and [row['name'] for row in record['commands']] == ORDER, 'frozen ten-stage population')
        require(sha_file(fixture) == record['fixture_sha256'], 'fixture identity unchanged')
        record['space_comparison'] = {
            'scope': 'complete cache directories; legacy materialization is not an old-compiler cold build',
            'cold_compact_logical': cold['cache']['all_file_logical_bytes'],
            'materialized_legacy_logical': legacy['all_file_logical_bytes'],
            'cold_compact_allocated': cold['cache']['all_pathname_conservative_allocated_bytes'],
            'materialized_legacy_allocated': legacy['all_pathname_conservative_allocated_bytes'],
            'logical_bytes_avoided': legacy['all_file_logical_bytes'] - cold['cache']['all_file_logical_bytes'],
            'physical_allocated_bytes_avoided': legacy['all_pathname_conservative_allocated_bytes'] - cold['cache']['all_pathname_conservative_allocated_bytes'],
            'final_mixed_B_and_compact_A_keep_all_orphans': True}
        record['complete'] = True
        save()
        print(json.dumps({'complete': True, 'groups': 64, 'commands': 10, 'order': ORDER}))
    except BaseException as error:
        record.update(complete=False, error=type(error).__name__ + ': ' + str(error))
        if current_row is not None:
            current_row['state'] = 'failed'
        save()
        raise


if __name__ == '__main__':
    main()
