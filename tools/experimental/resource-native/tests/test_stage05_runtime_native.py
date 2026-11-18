#!/usr/bin/env python3
"""Portable, opt-in native IR8 smoke tests. Run this script explicitly.

Fresh raw inputs come only from repository fixtures, are admitted by the public
loads_runtime API, and produce the real C bodies compiled here. Requires POSIX,
Python 3.12+, and a C11 compiler. No default/v7 execution path changes.

Default: 16 tests. --stress adds six one/100-entry checks. --sanitize enables
ASan+UBSan and omits the address-space rlimit required by ASan's virtual shadow
reservation. Under ptrace, use ASAN_OPTIONS=detect_leaks=0:abort_on_error=1 because
LSan is unsupported there. Requested-allocation ledgers are not a leak detector.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import resource
import shlex
import shutil
import tempfile
import signal
import subprocess
import sys
import time
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CASES = {
    'P01': (None, {}),
    'P09': ({'kind': 'i64', 'value': 42}, {'apply': 1, 'apply_arg': 1, 'foreign': 1}),
    'P12': ({'kind': 'i64', 'value': 42}, {'id': 1}),
    'D1': ({'kind': 'i64', 'value': 42}, {'id': 3}),
    'D2': ({'kind': 'bool', 'value': True}, {'id': 3}),
    'D3': ({'kind': 'i64', 'value': 42}, {'outer': 1, 'id': 3, 'coerce': 3}),
    'D4': ({'kind': 'bool', 'value': True}, {'outer': 1, 'id': 3, 'coerce': 3}),
    'D5': ({'kind': 'bool', 'value': True}, {'constant': 2, 'return_x': 4}),
    'D6': ({'kind': 'i64', 'value': 43}, {'id': 2}),
    'D7': ({'kind': 'i64', 'value': 42}, {'id': 2, 'some': 1}),
    'D8': (None, {'constant': 2, 'return_x': 2, 'cycle': 1}),
}
# Exact raw entry instruction index -> original entry scalar variable.
# These are semantic expectations, not emitter-derived metadata: both closed
# views must return the originally allocated scalar, including memo revisits.
FORCE_SCALARS = {
    'D1': {11: 'i', 13: 'b', 15: 'i', 26: 'i'},
    'D2': {11: 'b', 13: 'i', 15: 'b', 26: 'b'},
    'D3': {11: 'i', 13: 'b', 15: 'i', 26: 'i'},
    'D4': {11: 'b', 13: 'i', 15: 'b', 26: 'b'},
    'D5': {14: 'i', 17: 'b', 20: 'i', 23: 'b'},
    'D6': {15: 'i', 17: 'j'},
    'D7': {11: 'payload', 18: 'payload'},
    # The ignored Force returns42. The final demanded knot never returns.
    'D8': {15: 'i'},
}
MAX_STREAM = 16 * 1024 * 1024
RESULTS = []
COMMANDS = []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_process(argv, directory, *, compile=False, sanitize=False):
    """One ordinary bounded subprocess, retaining both streams and cleanup."""
    directory.mkdir()
    row = {'argv': [str(x) for x in argv], 'cwd': str(directory),
           'status': 'starting', 'returncode': None, 'cleanup_errors': []}
    COMMANDS.append(row)
    process = None
    original_error = None
    started = time.monotonic()
    env = os.environ.copy()
    env.update({'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC'})
    if sanitize:
        env.setdefault('ASAN_OPTIONS', 'abort_on_error=1')
        env.setdefault('UBSAN_OPTIONS', 'halt_on_error=1:print_stacktrace=1')
    row['sanitizer_options'] = {k: env[k] for k in ('ASAN_OPTIONS', 'UBSAN_OPTIONS') if k in env}
    def limits():
        resource.setrlimit(resource.RLIMIT_CPU, (30, 30) if compile else (10, 10))
        if compile or not sanitize:
            memory = (1024 if compile else 512) * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_STREAM, MAX_STREAM))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        with (directory / 'stdout.raw').open('xb') as out, (directory / 'stderr.raw').open('xb') as err:
            process = subprocess.Popen(row['argv'], stdout=out, stderr=err,
                cwd=directory, start_new_session=True, preexec_fn=limits, env=env)
            row['pid'] = process.pid
            row['returncode'] = process.wait(timeout=60 if compile else 20)
        for name in ('stdout.raw', 'stderr.raw'):
            if (directory / name).stat().st_size >= MAX_STREAM:
                raise RuntimeError(f'{name} reached the output limit')
        row['status'] = 'completed'
    except BaseException as exc:
        original_error = exc
        row['status'] = 'failed'
        row['error'] = repr(exc)
    finally:
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as exc:
                row['cleanup_errors'].append(repr(exc))
            try:
                process.wait(timeout=5)
            except BaseException as exc:
                row['cleanup_errors'].append(repr(exc))
        if process is not None:
            row['returncode'] = process.returncode
        row['elapsed_seconds'] = time.monotonic() - started
        if row['cleanup_errors']:
            row['status'] = 'failed'
        (directory / 'command.json').write_text(json.dumps(row, indent=2, sort_keys=True) + '\n')
    if original_error is not None:
        raise original_error
    if row['cleanup_errors']:
        raise RuntimeError(f'Child cleanup failed: {row["cleanup_errors"]}')
    return row


def load_raws(selected):
    data = json.loads((HERE / 'stage05_runtime_cases.json').read_text())
    fixture = json.loads((ROOT / data['source_fixture_file']['path']).read_text())
    raws = {}
    for case_id in selected:
        choices = [c for c in data['cases'] if c['id'] == case_id]
        if len(choices) != 1:
            raise ValueError(f'Expected one repository case for {case_id}')
        case = choices[0]
        if case['storage'] == 'embedded-exact-raw-text':
            text = case['text']
        elif case['storage'] == 'repository-json-extraction':
            if case['source_file'] != data['source_fixture_file']['path']:
                raise ValueError('Unexpected raw fixture source')
            text = fixture
            for segment in case['source_json_pointer'].split('/')[1:]:
                segment = segment.replace('~1', '/').replace('~0', '~')
                text = text[int(segment)] if isinstance(text, list) else text[segment]
        else:
            raise ValueError(f'Unknown raw storage: {case["storage"]}')
        encoded = text.encode('utf-8')
        if len(encoded) != case['raw_utf8_bytes'] or hashlib.sha256(encoded).hexdigest() != case['raw_sha256']:
            raise ValueError(f'Raw fixture identity changed: {case_id}')
        raws[case_id] = text
    return raws


def build_programs(output, raw_texts, cc, sanitize, optimization):
    # Public production ingress only. Do not import evidence-producing tests.
    sys.path.insert(0, str(ROOT))
    from resource_ir_v8.runtime_emit import loads_runtime
    build = output / 'build'
    build.mkdir()
    logs = output / 'compilation'
    logs.mkdir()
    flags = ['-std=c11', '-' + optimization, '-g', '-Wall', '-Wextra', '-Werror', '-pedantic']
    if sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer']
    includes = ['-I' + str(ROOT / 'packet_v8'), '-I' + str(ROOT / 'runtime_v8')]
    common = [ROOT / 'packet_v8/ir8_packet.c'] + [ROOT / ('runtime_v8/' + n) for n in (
        'rir8_binding.c', 'rir8_guard.c', 'rir8_memory.c', 'rir8_runtime.c',
        'rir8_force.c', 'rir8_session.c')]
    objects = []
    def compile_one(argv, name):
        row = run_process(argv, logs / name, compile=True, sanitize=sanitize)
        if row['returncode'] != 0:
            raise RuntimeError(f'Compiler failed ({row["returncode"]}); see {logs / name / "stderr.raw"}')
    for source in common:
        obj = build / (source.stem + '.o')
        compile_one([*cc, *flags, *includes, '-c', str(source), '-o', str(obj)], source.stem)
        objects.append(str(obj))
    for case_id, text in raw_texts.items():
        directory = build / case_id
        directory.mkdir()
        (directory / 'raw.json').write_bytes(text.encode('utf-8'))
        emission = loads_runtime(text)
        for filename, content in (
            ('ir8_packet_generated.h', emission.packet_header),
            ('ir8_packet_generated.c', emission.packet_source),
            ('ir8_runtime_generated.h', emission.runtime_header),
            ('ir8_runtime_generated.c', emission.runtime_source),
            ('runtime_manifest.json', emission.manifest_json),
            ('metadata.json', emission.metadata_json)):
            (directory / filename).write_bytes(content.encode('utf-8'))
        compile_one([*cc, *flags, *includes, '-I' + str(directory), *objects,
                     str(directory / 'ir8_packet_generated.c'),
                     str(directory / 'ir8_runtime_generated.c'),
                     str(HERE / 'stage05_runtime_driver.c'), '-o', str(directory / 'smoke')], case_id)
    return build


class RuntimeSmoke(unittest.TestCase):
    def run_case(self, case_id, repetitions, stress=False):
        binary = self.build_root / case_id / 'smoke'
        self.assertTrue(binary.is_file(), f'Build missing: {binary}')
        name = f'{case_id}-{"stress-" if stress else ""}repeat{repetitions}'
        case_dir = self.output / name
        row = {'case': case_id, 'repetitions': repetitions, 'stress': stress,
               'binary_sha256': digest(binary), 'status': 'running'}
        RESULTS.append(row)
        try:
            command = run_process([binary, str(repetitions)], case_dir, sanitize=self.sanitize)
            row['command'] = command
            stderr = (case_dir / 'stderr.raw').read_bytes()
            self.assertEqual(stderr, b'', stderr[:2000])
            document = json.loads((case_dir / 'stdout.raw').read_text())
            row['observed'] = {k: document['evaluation'][k] for k in
                               ('fault', 'location', 'result', 'metrics', 'memory', 'memory_categories',
                                'events_emitted', 'events_omitted')}
            row['destruction'] = document['destruction']
            self.check_report(case_id, repetitions, command['returncode'], document)
            row['status'] = 'passed'
        except BaseException as exc:
            row['status'] = 'failed'
            row['error'] = repr(exc)
            raise
        finally:
            if case_dir.is_dir():
                (case_dir / 'result.json').write_text(json.dumps(row, indent=2, sort_keys=True) + '\n')

    def check_report(self, case_id, repetitions, returncode, document):
        self.assertEqual(document['schema'], 'resource-ir-v8-terminal-run/1')
        r, destruction = document['evaluation'], document['destruction']
        self.assertEqual(r['schema'], 'resource-ir-v8-run/1')
        fault = case_id == 'D8'
        self.assertEqual(returncode, 2 if fault else 0, r['location'])
        self.assertEqual(r['fault'], 7 if fault else 0, r['location'])
        self.assertEqual(r['state'], 1 if fault else 0)
        self.assertEqual(r['events_omitted'], 0)
        self.assertEqual(r['events_emitted'], len(r['events']))
        self.assertEqual(r['graph_executed'], 1)
        self.assertEqual(r['result'], CASES[case_id][0])
        self.assertEqual(r['metrics']['entries_completed'], 0 if fault else repetitions)
        names = Counter(e['context']['name'] for e in r['events']
                        if e['event'] == 'frame_enter' and e['context']['kind'] != 'entry')
        self.assertEqual(dict(names), {name: n * repetitions for name, n in CASES[case_id][1].items()})
        thunk_calls = sum(n for name, n in CASES[case_id][1].items() if name in self.raws[case_id]['codes'])
        self.assertEqual(r['metrics']['callback_calls'], thunk_calls * repetitions)
        ordinary = sum(CASES[case_id][1].values()) - thunk_calls
        self.assertEqual(r['metrics']['ordinary_calls'], ordinary * repetitions)
        self.assertGreater(r['guard_work_total'], 0)
        self.assertLessEqual(r['guard_work_used'], r['guard_work_limit'])
        cats = r['memory_categories']
        self.assertEqual(len(cats), 7)
        for key in ('allocated_bytes', 'freed_bytes', 'live_bytes', 'allocations', 'frees', 'live_blocks'):
            self.assertEqual(r['memory'][key], sum(c[key] for c in cats.values()), key)
        for c in [r['memory'], *cats.values()]:
            self.assertEqual(c['allocated_bytes'] - c['freed_bytes'], c['live_bytes'])
            self.assertEqual(c['allocations'] - c['frees'], c['live_blocks'])
            self.assertGreaterEqual(c['peak_bytes'], c['live_bytes'])
            self.assertGreaterEqual(c['peak_blocks'], c['live_blocks'])
        if fault:
            self.assertEqual(r['location']['guard_index'], 25)
            self.assertGreater(r['memory']['live_blocks'], 0)
            self.assertEqual(destruction['status'], 1)
            self.assertFalse(destruction['totals_overflow'])
            self.assertEqual(destruction['retired_blocks'], r['memory']['live_blocks'])
            self.assertEqual(destruction['retired_bytes'], r['memory']['live_bytes'])
            for name, c in cats.items():
                self.assertEqual(destruction['categories'][name], {'blocks': c['live_blocks'], 'bytes': c['live_bytes']})
        else:
            for c in [r['memory'], *cats.values()]:
                self.assertEqual(c['live_blocks'], 0)
                self.assertEqual(c['live_bytes'], 0)
            self.assertEqual(r['metrics']['owner_handle_acquisitions'], r['metrics']['owner_handle_releases'])
            self.assertEqual(r['metrics']['loan_handle_acquisitions'], r['metrics']['loan_handle_releases'])
            self.assertEqual(r['metrics']['groups_allocated'], r['metrics']['groups_closed'])
            self.assertEqual(r['metrics']['nodes_allocated'], r['metrics']['nodes_freed'])
            self.assertEqual(destruction['status'], 2)
            self.assertEqual(destruction['retired_blocks'], 0)
        if repetitions > 1:
            baseline = next(x['observed'] for x in RESULTS if x['case'] == case_id and x['repetitions'] == 1 and x['status'] == 'passed')
            for key in ('peak_bytes', 'peak_blocks'):
                self.assertEqual(r['memory'][key], baseline['memory'][key])
            for name, category in cats.items():
                factor = 1 if name == 'context' else repetitions
                for key in ('allocated_bytes', 'freed_bytes', 'allocations', 'frees'):
                    self.assertEqual(category[key], baseline['memory_categories'][name][key] * factor, (name, key))
        if case_id in ('D1', 'D2', 'D3', 'D4'):
            self.assertGreaterEqual(r['metrics']['memo_fast_paths'], repetitions)
        self.check_force_identity(case_id, repetitions, r['events'])

    def check_force_identity(self, case_id, repetitions, events):
        raw = self.raws[case_id]
        entries = [e['frame'] for e in events if e['event'] == 'frame_enter' and e['context']['kind'] == 'entry']
        self.assertEqual(len(entries), repetitions)
        for frame in entries:
            entry_start = next(i for i, e in enumerate(events) if e['event'] == 'frame_enter' and e['frame'] == frame)
            allocations = {e['out']: e['node'] for e in events
                           if e['event'] == 'allocate' and e['frame'] == frame}
            forces = [e for e in events if e['event'] == 'ir_force_result' and e['frame'] == frame]
            expected_outs = [i['out'] for i in raw['entry'] if i['op'] == 'force']
            if case_id == 'D8':
                expected_outs = expected_outs[:-1]
            self.assertEqual([e['out'] for e in forces], expected_outs)
            for index, scalar in FORCE_SCALARS.get(case_id, {}).items():
                instruction = raw['entry'][index]
                self.assertEqual(instruction['op'], 'force')
                actual = next(e for e in forces if e['out'] == instruction['out'])
                self.assertEqual(actual['result'], allocations[scalar])
            if case_id in ('D1', 'D2', 'D3', 'D4'):
                counts = [sum(e['event'] == 'frame_enter' and e['context']['kind'] != 'entry'
                              for e in events[entry_start:events.index(force)]) for force in forces]
                self.assertEqual(counts, [1, 2, 2, 3] if case_id in ('D1', 'D2') else [3, 5, 5, 7])
            if case_id == 'D5':
                creator = [e for e in events[entry_start:events.index(forces[2])]
                           if e['event'] == 'frame_enter' and e['context'].get('name') == 'constant']
                self.assertEqual(len(creator), 2)
                returned = [e for e in events[entry_start:events.index(forces[2])]
                            if e['event'] == 'invoke_raw_return' and e['closure'] in {f['context']['node'] for f in creator}]
                self.assertEqual(len(returned), 2)
                first_use = next(e for e in events[entry_start:] if e['event'] == 'frame_enter' and e['context'].get('name') == 'return_x')
                self.assertLess(events.index(returned[-1]), events.index(first_use))
            if case_id == 'D8':
                prefix = next(e for e in forces if e['out'] == raw['entry'][15]['out'])
                cycle = next(e for e in events if e['event'] == 'frame_enter' and e['context'].get('name') == 'cycle')
                self.assertLess(events.index(prefix), events.index(cycle))
                self.assertFalse(any(e['event'] == 'memo_publish' for e in events[events.index(forces[-1]) + 1:]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New external directory; otherwise retain a fresh temporary directory')
    parser.add_argument('--cases', nargs='+', choices=CASES, default=list(CASES))
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'), help='Compiler command, defaults to CC or cc')
    parser.add_argument('--stress', action='store_true', help='Add six one/100-entry D1/D3/D5 checks')
    parser.add_argument('--sanitize', action='store_true', help='ASan+UBSan; honors ASAN_OPTIONS/UBSAN_OPTIONS; no native address-space rlimit')
    parser.add_argument('--optimization', choices=('O0', 'O2'), default='O0')
    args = parser.parse_args()
    if os.name != 'posix':
        parser.error('This native test runner requires POSIX process groups and resource limits')
    if sys.flags.optimize:
        parser.error('Run unoptimized Python: lower checker assertions are required')
    cc = shlex.split(args.cc)
    if not cc or shutil.which(cc[0]) is None:
        parser.error('No C compiler found; set CC or --cc')
    cc[0] = shutil.which(cc[0])
    if args.output:
        output = args.output.resolve()
        if output == ROOT or ROOT in output.parents:
            parser.error('--output must be outside the resource-native source tree')
        output.mkdir(parents=False, exist_ok=False)
    else:
        output = Path(tempfile.mkdtemp(prefix='ir8-runtime-native-'))
    print(f'Native test artifacts: {output}', file=sys.stderr)
    summary = {'status': 'building', 'compiler': cc, 'sanitize': args.sanitize,
               'optimization': args.optimization, 'cases': RESULTS, 'commands': COMMANDS,
               'not_covered': ['neutral memo Access', 'lexical Env observation', 'all 27 guards',
                               'general GC replacement', 'performance', 'source/model/original parity']}
    try:
        raw_texts = load_raws(args.cases)
        RuntimeSmoke.raws = {key: json.loads(text) for key, text in raw_texts.items()}
        RuntimeSmoke.build_root = build_programs(output, raw_texts, cc, args.sanitize, args.optimization)
        RuntimeSmoke.output = output / 'runs'
        RuntimeSmoke.output.mkdir()
        RuntimeSmoke.sanitize = args.sanitize
        for case_id in args.cases:
            variants = [(1, False)]
            if case_id in ('D1', 'D2', 'D3', 'D4', 'D5'):
                variants.append((3, False))
            if args.stress and case_id in ('D1', 'D3', 'D5'):
                variants += [(1, True), (100, True)]
            for repeat, stress in variants:
                def test(self, case_id=case_id, repeat=repeat, stress=stress):
                    self.run_case(case_id, repeat, stress)
                setattr(RuntimeSmoke, f'test_{case_id}_{"stress_" if stress else ""}repeat{repeat}', test)
        result = unittest.TextTestRunner(verbosity=2, failfast=True).run(unittest.defaultTestLoader.loadTestsFromTestCase(RuntimeSmoke))
        summary.update(status='passed' if result.wasSuccessful() else 'failed', tests_run=result.testsRun,
                       failures=len(result.failures), errors=len(result.errors))
        return 0 if result.wasSuccessful() else 1
    except BaseException as exc:
        summary.update(status='failed', error=repr(exc))
        raise
    finally:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    sys.exit(main())
