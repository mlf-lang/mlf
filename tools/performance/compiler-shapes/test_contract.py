#!/usr/bin/env python3
"""Contract tests for the compiler shape benchmark. No compiler is required.

These tests use synthetic receipts to prove that the analyzer refuses missing,
duplicate, non-finite, failed, qualified-only and incompatible data, and that the
frozen schedule stays balanced.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze  # noqa: E402
import bench  # noqa: E402
import run as runner  # noqa: E402

STAGES = ['source-to-checked', 'checked-to-llvm', 'llvm-to-executable']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_cohort(root, label='screen', family='flat_functions', size=8, repeats=3,
                 mlf_seconds=(2.0, 2.2, 2.4), ghc_seconds=(1.0, 1.0, 1.1),
                 endpoint='crate-bootstrap-v1', host='test-host'):
    folder = Path(root) / label
    folder.mkdir(parents=True)
    source = folder / 'source'
    source.mkdir()
    program = source / 'Main.hs'
    program.write_text('entry x = x\n')
    case = {'id': family + '-' + str(size), 'family': family, 'size': size,
            'source': str(program.resolve()), 'source_sha256': digest(program),
            'source_bytes': program.stat().st_size, 'inputs': [-1, 0, 7],
            'expected_stdout': ['-1\n', '0\n', '7\n']}
    schedule = []
    for index in range(repeats):
        for lane in ['ghc', 'mlf']:
            schedule.append({'case': case['id'], 'position': index * 2 + (lane == 'mlf'), 'lane': lane})
    plan = {'benchmark': {'schema': 2, 'suite': 'compiler-shapes', 'suite_version': 2,
                          'cohort': label, 'endpoint': {'id': endpoint, 'status': 'measured',
                          'summary': 'synthetic endpoint'}, 'repeats': repeats,
                          'families': [family], 'sizes': [size], 'cells': 1,
                          'timed_compilations': len(schedule), 'claim_limits': ['synthetic']},
            'source': {'commit': '0' * 40, 'branch': 'test', 'dirty': False,
                       'patch_sha256': hashlib.sha256(b'').hexdigest()},
            'toolchain': {'ghc': {'path': '/ghc', 'version': '9.14.1'},
                          'clang': {'path': '/clang', 'version': 'clang test'},
                          'producer': {'path': '/producer', 'receipt_sha256': 'a' * 64, 'emlf_sha256': 'b' * 64},
                          'builtin': {'/builtin.mlfci': 'c' * 64, '/builtin.mlfco': 'd' * 64}},
            'host': {'platform': host, 'machine': 'test-mcu'}, 'cases': [case], 'schedule': schedule}
    (folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
    runs = []
    for item in schedule:
        times = mlf_seconds if item['lane'] == 'mlf' else ghc_seconds
        wall = times[item['position'] // 2 if item['position'] // 2 < len(times) else 0]
        stages = [{'name': name, 'wall_seconds': wall / 3, 'user_seconds': wall / 4,
                   'system_seconds': wall / 20} for name in STAGES] if item['lane'] == 'mlf' else []
        runs.append({'case': case['id'], 'position': item['position'], 'lane': item['lane'], 'complete': True,
                     'output_correct': True, 'fresh': 1 if item['lane'] == 'mlf' else None,
                     'reused': 0 if item['lane'] == 'mlf' else None, 'max_group_members': 1,
                     'raw_compared_with_first_mlf_leg': item['lane'] == 'mlf' and item['position'] > 1,
                     'executable_sha256': 'e' * 64, 'oracle_inputs': [-1, 0, 7],
                     'stages': {'complete': True, 'stages': stages},
                     'command': {'complete': True, 'timed_target_leg': True, 'exit_code': 0, 'reason': None,
                                 'wall_seconds': wall, 'child_user_seconds': wall / 4,
                                 'child_system_seconds': wall / 20, 'started_utc': '2026-10-31T00:00:00Z'}})
    receipt = {'complete': True, 'all_cases_passed': True, 'failures': [],
               'plan_sha256': digest(folder / 'plan.json'), 'runs': runs}
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    for index, item in enumerate(schedule):
        if item['lane'] == 'mlf':
            leg = folder / 'legs' / ('%03d-' % index + case['id'] + '-mlf')
            leg.mkdir(parents=True)
            (leg / 'query-cache-inventory.json').write_text(json.dumps({'q.mlfq': {'bytes': 10, 'sha256': 'f' * 64}}))
    return folder


def edit(folder, mutate):
    path = Path(folder) / 'receipt.json'
    receipt = json.loads(path.read_text())
    mutate(receipt)
    path.write_text(json.dumps(receipt, indent=2) + '\n')


class ScheduleTests(unittest.TestCase):
    def test_balanced_pairs(self):
        self.assertEqual(runner.lanes_for(0, 3), ['ghc', 'mlf', 'mlf', 'ghc', 'ghc', 'mlf'])
        self.assertEqual(runner.lanes_for(1, 3), ['mlf', 'ghc', 'ghc', 'mlf', 'mlf', 'ghc'])
        starts = [runner.lanes_for(index, 3)[0] for index in range(6)]
        self.assertEqual(starts.count('ghc'), starts.count('mlf'))

    def test_default_matrix_shape(self):
        matrix, families, sizes, baseline = bench.resolve('default', None, None)
        self.assertEqual(len(families), 10)
        self.assertEqual(sizes, [8, 32, 128])
        self.assertTrue(baseline)
        self.assertEqual(bench.compile_count(len(families) * len(sizes) + 1, matrix['repeats']), 186)

    def test_local_functions_is_opt_in(self):
        _, families, _, _ = bench.resolve('default', None, None)
        self.assertNotIn('local_functions', families)
        _, chosen, _, _ = bench.resolve('default', ['local_functions'], [512])
        self.assertEqual(chosen, ['local_functions'])

    def test_installed_endpoint_is_separate_from_crate_runner(self):
        self.assertIn('emlf-source-v1', bench.registry()['paired_endpoints'])
        with self.assertRaises(SystemExit):
            bench.measured_endpoint('emlf-source-v1')


class AnalyzerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_accepts_complete_cohort(self):
        folder = write_cohort(self.root)
        rows, plan, receipt, samples = analyze.analyze(folder)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(samples), 6)
        self.assertEqual(rows[0]['mlf_over_ghc'], 2.2 / 1.0)
        self.assertEqual(rows[0]['fresh'], 1)

    def test_rejects_missing_sample(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'].pop())
        with self.assertRaisesRegex(ValueError, 'missing or duplicate'):
            analyze.analyze(folder)

    def test_rejects_duplicate_sample(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'].append(dict(r['runs'][0])))
        with self.assertRaisesRegex(ValueError, 'missing or duplicate'):
            analyze.analyze(folder)

    def test_rejects_nonfinite_timing(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'][0]['command'].update(wall_seconds=float('inf')))
        with self.assertRaisesRegex(ValueError, 'finite nonnegative'):
            analyze.analyze(folder)

    def test_rejects_reused_groups(self):
        folder = write_cohort(self.root)
        def mutate(receipt):
            for run in receipt['runs']:
                if run['lane'] == 'mlf':
                    run['reused'] = 1
                    break
        edit(folder, mutate)
        with self.assertRaisesRegex(ValueError, 'fresh MLF target'):
            analyze.analyze(folder)

    def test_rejects_failed_cohort(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r.update(all_cases_passed=False, failures=[{'case': 'x'}]))
        with self.assertRaisesRegex(ValueError, 'do not silently omit failures'):
            analyze.analyze(folder)

    def test_rejects_qualification_samples(self):
        folder = write_cohort(self.root)
        edit(folder, lambda r: r['runs'][0]['command'].update(timed_target_leg=False))
        with self.assertRaisesRegex(ValueError, 'not performance samples'):
            analyze.analyze(folder)

    def test_rejects_plan_digest_mismatch(self):
        folder = write_cohort(self.root)
        (folder / 'plan.json').write_text((folder / 'plan.json').read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'frozen plan digest'):
            analyze.analyze(folder)

    def test_rejects_changed_source(self):
        folder = write_cohort(self.root)
        (folder / 'source' / 'Main.hs').write_text('entry x = x + 1\n')
        with self.assertRaisesRegex(ValueError, 'unchanged shared source'):
            analyze.analyze(folder)

    def test_rejects_pre_schema_cohort(self):
        folder = write_cohort(self.root)
        plan = json.loads((folder / 'plan.json').read_text())
        del plan['benchmark']
        (folder / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        receipt = json.loads((folder / 'receipt.json').read_text())
        receipt['plan_sha256'] = digest(folder / 'plan.json')
        (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        with self.assertRaisesRegex(ValueError, 'predates benchmark schema 2'):
            analyze.analyze(folder)

    def test_cli_writes_all_outputs(self):
        folder = write_cohort(self.root)
        output = self.root / 'results'
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'), str(folder),
                                  '--output', str(output)], capture_output=True, text=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        for name in ['summary.json', 'summary.csv', 'samples.csv', 'summary.md']:
            self.assertTrue((output / name).is_file(), name)
        self.assertIn('MLF median', (output / 'summary.md').read_text())

    def test_cli_rejects_incompatible_cohorts(self):
        write_cohort(self.root, label='screen')
        write_cohort(self.root, label='other', endpoint='emlf-source-v1')
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'),
                                  str(self.root / 'screen'), str(self.root / 'other'),
                                  '--output', str(self.root / 'results')], capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('incompatible cohorts differ in', process.stderr + process.stdout)

    def test_cli_rejects_duplicate_cohort_labels(self):
        write_cohort(self.root, label='screen')
        copy = write_cohort(self.root, label='screen-copy')
        plan = json.loads((copy / 'plan.json').read_text())
        plan['benchmark']['cohort'] = 'screen'
        (copy / 'plan.json').write_text(json.dumps(plan, indent=2) + '\n')
        receipt = json.loads((copy / 'receipt.json').read_text())
        receipt['plan_sha256'] = digest(copy / 'plan.json')
        (copy / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        process = subprocess.run([sys.executable, '-B', str(HERE / 'analyze.py'),
                                  str(self.root / 'screen'), str(copy),
                                  '--output', str(self.root / 'results')], capture_output=True, text=True)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn('duplicate cohort label', process.stderr + process.stdout)



# Graph fixtures are independently encoded by the frozen wire-format reference,
# not a compiler run and never a substitute for retained measurement evidence.
def graph_fixture(groups=1, mutate_nodes=None, version=1, mutate_index=None):
    import base64
    import query_cache as Q
    from artifact_binary_reference import tree_document
    def s(value): return ('text', value)
    def n(tag, *children): return ('node', tag, tuple(children))
    def l(*children): return n(1, *children)
    raw_hash = hashlib.sha256(b'fixture raw payload').hexdigest()
    binding_hash = hashlib.sha256(b'fixture shared binding').hexdigest()
    binding = Q.pack(['Binding', 'imported'])
    nodes = [
        {'key': Q.pack(['Input', binding]), 'hash': binding_hash, 'reads': [], 'payload': None},
        {'key': binding, 'hash': binding_hash,
         'reads': [(Q.pack(['Input', binding]), binding_hash)], 'payload': binding_hash},
        {'key': Q.pack(['Binding', 'alias']), 'hash': binding_hash,
         'reads': [(binding, binding_hash)], 'payload': binding_hash},
    ]
    crate = 'compiler-shapes/flat_functions-8'
    report = {'format': 1, 'crate': crate, 'inferred_groups': groups,
              'reused_groups': 0, 'groups': []}
    for i in range(groups):
        members = ['f' + str(i)]
        key = Q.pack(['InferScc', Q.pack(members)])
        nodes.append({'key': key, 'hash': raw_hash,
                      'reads': [(binding, binding_hash)], 'payload': raw_hash})
        identity = 'Query_' + ''.join(str(ord(c)) + '_' for c in crate) + 'z_' + ''.join(
            str(ord(c)) + '_' for c in members[0])
        report['groups'].append({'id': identity, 'members': members,
                                'cached': False, 'query_key': raw_hash})
    if mutate_nodes:
        mutate_nodes(nodes)
    configuration = Q.pack([crate, 'b' * 64, 'fixture source format', 'open-fragment-checker-1', 'source'])
    if version == 1:
        value = n(411, s('MLF-CRATE-QUERY-GRAPH-1'), s(configuration),
        l(*(n(410, s(x['key']), s(x['hash']),
               l(*(n(2, s(k), s(h)) for k, h in x['reads'])),
               n(4) if x['payload'] is None else n(5, s(x['payload']))) for x in nodes)))
    else:
        strings = sorted({value for x in nodes
                          for value in [x['key'], x['hash'],
                                        *(v for edge in x['reads'] for v in edge),
                                        *([] if x['payload'] is None else [x['payload']])]})
        ids = {value: i for i, value in enumerate(strings)}
        def ref(value): return ('int', ids[value])
        value = n(412, s('MLF-CRATE-QUERY-GRAPH-2'), s(configuration),
                  l(*(s(value) for value in strings)),
                  l(*(n(413, ref(x['key']), ref(x['hash']),
                         l(*(n(2, ref(k), ref(h)) for k, h in x['reads'])),
                         n(4) if x['payload'] is None else n(5, ref(x['payload'])))
                      for x in sorted(nodes, key=lambda x: x['key']))))
    if mutate_index:
        value = mutate_index(value)
    index = tree_document([value], 6)
    generation = hashlib.sha256(index).hexdigest()
    current = tree_document([s(generation)], 6)
    files = {Q.GRAPH + 'CURRENT': current, Q.GRAPH + 'generations/' + generation + '.mlfqg': index}
    inventory = {p: {'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()} for p, b in files.items()}
    for h in [binding_hash, raw_hash]:
        inventory[Q.GRAPH + 'results/' + h + '.mlfqr'] = {'bytes': 40, 'sha256': h}
    evidence = {'format': 1, 'query_report_json': json.dumps(report),
                'files_base64': {p: base64.b64encode(b).decode('ascii') for p, b in files.items()}}
    return inventory, evidence


def change_report(evidence, mutate):
    report = json.loads(evidence['query_report_json'])
    mutate(report)
    evidence['query_report_json'] = json.dumps(report)


class GraphCacheTests(unittest.TestCase):
    version = 1

    def fixture(self, **kwargs):
        return graph_fixture(version=self.version, **kwargs)

    def index_error(self, legacy, indexed):
        return legacy if self.version == 1 else indexed

    def check(self, inventory, evidence, groups=1):
        return analyze.Q.check_graph(inventory, evidence, groups, 1,
                                     'compiler-shapes/flat_functions-8', 'b' * 64)

    def test_accepts_extra_nodes_and_content_deduplication(self):
        inventory, evidence = self.fixture(groups=3)
        result = self.check(inventory, evidence, groups=3)
        self.assertEqual(len(result['groups']), 3)
        self.assertEqual(result['files'], 4)  # CURRENT, index, two unique payloads
        self.assertEqual(result['bytes'], sum(v['bytes'] for v in inventory.values()))

    def test_rejects_missing_evidence(self):
        inventory, _ = self.fixture()
        with self.assertRaisesRegex(ValueError, 're-measure'):
            self.check(inventory, None)

    def test_rejects_missing_payload(self):
        inventory, evidence = self.fixture()
        del inventory[next(p for p in inventory if p.endswith('.mlfqr'))]
        with self.assertRaisesRegex(ValueError, 'missing retained payload'):
            self.check(inventory, evidence)

    def test_rejects_bad_content_address(self):
        inventory, evidence = self.fixture()
        inventory[next(p for p in inventory if p.endswith('.mlfqr'))]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'content-addressed query graph SHA'):
            self.check(inventory, evidence)

    def test_rejects_nonfinite_fractional_or_boolean_sizes(self):
        for size in [float('inf'), float('nan'), 1.5, True, -1]:
            inventory, evidence = self.fixture()
            inventory[next(iter(inventory))]['bytes'] = size
            with self.subTest(size=size), self.assertRaisesRegex(ValueError, 'finite integral'):
                self.check(inventory, evidence)

    def test_rejects_tampered_retained_bytes(self):
        inventory, evidence = self.fixture()
        evidence['files_base64'][analyze.Q.GRAPH + 'CURRENT'] = 'AAAA'
        with self.assertRaisesRegex(ValueError, 'retained query graph bytes'):
            self.check(inventory, evidence)

    def test_rejects_current_selecting_other_generation(self):
        import base64
        from artifact_binary_reference import tree_document
        inventory, evidence = self.fixture()
        current = analyze.Q.GRAPH + 'CURRENT'
        wrong = tree_document([('text', '0' * 64)], 6)
        evidence['files_base64'][current] = base64.b64encode(wrong).decode('ascii')
        inventory[current] = {'bytes': len(wrong), 'sha256': hashlib.sha256(wrong).hexdigest()}
        with self.assertRaisesRegex(ValueError, 'CURRENT selects'):
            self.check(inventory, evidence)

    def test_rejects_duplicate_node_keys(self):
        inventory, evidence = self.fixture(mutate_nodes=lambda ns: ns.append(dict(ns[0])))
        with self.assertRaisesRegex(ValueError, self.index_error('unique query graph keys', 'row canonicality')):
            self.check(inventory, evidence)

    def test_rejects_missing_or_stale_dependency(self):
        for missing in [True, False]:
            def mutate(ns):
                ns[-1]['reads'] = [('absent' if missing else ns[0]['key'], '0' * 64)]
            inventory, evidence = self.fixture(mutate_nodes=mutate)
            with self.subTest(missing=missing), self.assertRaisesRegex(ValueError, self.index_error('missing/stale', 'missing dependency|stale dependency')):
                self.check(inventory, evidence)

    def test_rejects_graph_cycle(self):
        def mutate(ns):
            ns[0]['reads'] = [(ns[1]['key'], ns[1]['hash'])]
        inventory, evidence = self.fixture(mutate_nodes=mutate)
        with self.assertRaisesRegex(ValueError, self.index_error('cyclic/deep', 'cycle')):
            self.check(inventory, evidence)

    def test_rejects_wrong_infer_identity_or_hash(self):
        for field, value in [('members', ['other']), ('query_key', '0' * 64)]:
            inventory, evidence = self.fixture()
            change_report(evidence, lambda q: q['groups'][0].__setitem__(field, value))
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'exact InferScc|group id matches'):
                self.check(inventory, evidence)

    def test_rejects_wrong_report_crate_format_or_group_id(self):
        for mutate in [
            lambda q: q.update(crate='other'),
            lambda q: q.update(format=True),
            lambda q: q['groups'][0].update(id='unrelated'),
        ]:
            inventory, evidence = self.fixture()
            change_report(evidence, mutate)
            with self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_wrong_measured_crate_or_compiler(self):
        for crate, compiler in [('other', 'b' * 64), ('compiler-shapes/flat_functions-8', 'c' * 64)]:
            inventory, evidence = self.fixture()
            with self.assertRaisesRegex(ValueError, 'crate/compiler configuration'):
                analyze.Q.check_graph(inventory, evidence, 1, 1, crate, compiler)

    def test_rejects_missing_or_duplicate_report_groups(self):
        for mode in ['missing', 'duplicate', 'overlapping', 'extra-graph']:
            inventory, evidence = self.fixture(groups=2)
            report = json.loads(evidence['query_report_json'])
            groups = report['groups']
            if mode == 'missing':
                groups.pop()
            elif mode == 'duplicate':
                groups[1]['id'] = groups[0]['id']
            elif mode == 'overlapping':
                groups[1]['members'] = groups[0]['members']
            else:
                groups.pop()
                report['inferred_groups'] = 1
            evidence['query_report_json'] = json.dumps(report)
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.check(inventory, evidence, groups=1 if mode == 'extra-graph' else 2)

    def test_rejects_warm_report_and_false_counts(self):
        for mutate in [
            lambda q: q.update(reused_groups=1),
            lambda q: q.update(inferred_groups=2),
            lambda q: q.update(inferred_groups=True),
            lambda q: q['groups'][0].update(cached=True),
        ]:
            inventory, evidence = self.fixture()
            change_report(evidence, mutate)
            with self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_rejects_duplicate_report_json_keys(self):
        inventory, evidence = self.fixture()
        evidence['query_report_json'] = '{"inferred_groups":1,' + evidence['query_report_json'][1:]
        with self.assertRaisesRegex(ValueError, 'duplicate query report JSON key'):
            self.check(inventory, evidence)

    def test_rejects_payload_hash_different_from_node_hash(self):
        def mutate(nodes):
            nodes[-1]['payload'] = nodes[1]['hash']
        inventory, evidence = self.fixture(mutate_nodes=mutate)
        with self.assertRaisesRegex(ValueError, 'payload matches result hash'):
            self.check(inventory, evidence)

    def test_rejects_extra_generation(self):
        inventory, evidence = self.fixture()
        inventory[analyze.Q.GRAPH + 'generations/' + '0' * 64 + '.mlfqg'] = {
            'bytes': 1, 'sha256': '0' * 64}
        with self.assertRaisesRegex(ValueError, 'one committed graph generation'):
            self.check(inventory, evidence)

    def test_rejects_mixed_storage_and_unpublished_staging(self):
        for extra in ['legacy.mlfq', analyze.Q.GRAPH + 'staging/incomplete']:
            inventory, evidence = self.fixture()
            inventory[extra] = {'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.check(inventory, evidence)

    def test_snapshot_retains_exact_actual_inputs(self):
        import base64
        import query_cache as Q
        inventory, evidence = self.fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            query = root / 'queries'
            for name, value in evidence['files_base64'].items():
                path = query / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(base64.b64decode(value))
            report = root / 'unit.queries'
            report.write_text(evidence['query_report_json'])
            destination = root / 'query-graph-evidence.json'
            Q.snapshot(query, report, destination)
            self.assertEqual(json.loads(destination.read_text()), evidence)


class GraphAnalyzerTests(unittest.TestCase):
    version = 1

    def fixture(self, **kwargs):
        return graph_fixture(version=self.version, **kwargs)

    def test_graph_cohort_and_existing_raw_reuse_guards(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            inventory, evidence = self.fixture()
            legs = sorted((folder / 'legs').iterdir())
            for leg in legs:
                (leg / 'query-cache-inventory.json').write_text(json.dumps(inventory))
                (leg / 'query-graph-evidence.json').write_text(json.dumps(evidence))
            rows, _, _, samples = analyze.analyze(folder)
            self.assertEqual(rows[0]['query_storage'], 'query-graph-v1')
            self.assertEqual(rows[0]['fresh'], 1)
            self.assertEqual(rows[0]['query_files'], 4)
            self.assertEqual(len(samples), 6)
            edit(folder, lambda r: r['runs'][-1].update(raw_compared_with_first_mlf_leg=False))
            with self.assertRaisesRegex(ValueError, 'actual raw-byte comparisons'):
                analyze.analyze(folder)

    def test_rejects_inventory_drift_with_same_file_count(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = write_cohort(directory)
            inventory, evidence = self.fixture()
            legs = sorted((folder / 'legs').iterdir())
            for i, leg in enumerate(legs):
                if i == 2:
                    inventory[next(p for p in inventory if p.endswith('.mlfqr'))]['bytes'] += 1
                (leg / 'query-cache-inventory.json').write_text(json.dumps(inventory))
                (leg / 'query-graph-evidence.json').write_text(json.dumps(evidence))
            with self.assertRaisesRegex(ValueError, 'stable graph inventory'):
                analyze.analyze(folder)

class IndexedGraphCacheTests(GraphCacheTests):
    version = 2

    def test_v1_and_v2_preserve_groups_and_payload_deduplication(self):
        first = self.check(*graph_fixture(groups=3), groups=3)
        second = self.check(*self.fixture(groups=3), groups=3)
        self.assertEqual(first['groups'], second['groups'])
        self.assertEqual(first['files'], second['files'])

    def test_accepts_ordered_duplicate_reads(self):
        def mutate(nodes):
            nodes[-1]['reads'] = [(nodes[1]['key'], nodes[1]['hash']),
                                 (nodes[2]['key'], nodes[2]['hash']),
                                 (nodes[1]['key'], nodes[1]['hash'])]
        inventory, evidence = self.fixture(mutate_nodes=mutate)
        self.check(inventory, evidence)
        import base64
        raw = base64.b64decode(next(value for path, value in evidence['files_base64'].items()
                                   if path.endswith('.mlfqg')))
        configuration = analyze.Q.document(raw)[2][1][1]
        nodes, _ = analyze.Q.read_index(raw, configuration)
        key = analyze.Q.pack(['InferScc', analyze.Q.pack(['f0'])])
        reads = nodes[key][1]
        self.assertEqual(len(reads), 3)
        self.assertEqual(reads[0], reads[2])
        self.assertNotEqual(reads[0], reads[1])

    @staticmethod
    def with_child(value, position, child):
        children = list(value[2])
        children[position] = child
        return (value[0], value[1], tuple(children))

    def test_rejects_index_tag_marker_and_arity(self):
        mutations = [
            lambda v: ('node', 999, v[2]),
            lambda v: self.with_child(v, 0, ('text', 'MLF-CRATE-QUERY-GRAPH-1')),
            lambda v: ('node', 412, v[2][:-1]),
            lambda v: self.with_child(v, 1, ('text', '')),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                self.check(*self.fixture(mutate_index=mutate))

    def test_rejects_noncanonical_dictionary(self):
        for mode in ('unordered', 'duplicate', 'unused'):
            def mutate(value):
                dictionary = list(value[2][2][2])
                if mode == 'unordered':
                    dictionary[0], dictionary[1] = dictionary[1], dictionary[0]
                elif mode == 'duplicate':
                    dictionary[1] = dictionary[0]
                else:
                    dictionary.append(('text', 'zz-unused'))
                return self.with_child(value, 2, ('node', 1, tuple(dictionary)))
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, 'dictionary canonicality|unused dictionary'):
                self.check(*self.fixture(mutate_index=mutate))

    def test_rejects_invalid_ids_and_unordered_rows(self):
        for mode in ('negative', 'out-of-range', 'wrong-type', 'unordered'):
            def mutate(value):
                rows = list(value[2][3][2])
                if mode == 'unordered':
                    rows.reverse()
                else:
                    wrong = {'negative': ('int', -1),
                             'out-of-range': ('int', len(value[2][2][2])),
                             'wrong-type': ('text', '0')}[mode]
                    rows[0] = self.with_child(rows[0], 1, wrong)
                return self.with_child(value, 3, ('node', 1, tuple(rows)))
            with self.subTest(mode=mode), self.assertRaisesRegex(
                    ValueError, 'ID range|int|row canonicality'):
                self.check(*self.fixture(mutate_index=mutate))

    def depth_fixture(self, count):
        def mutate(nodes):
            digest = nodes[0]['hash']
            for i in range(count):
                nodes.append({'key': 'Depth/%04d' % i, 'hash': digest, 'payload': None,
                              'reads': [] if i == 0 else [('Depth/%04d' % (i - 1), digest)]})
        return self.fixture(mutate_nodes=mutate)

    def test_accepts_dependency_first_4096_node_path(self):
        self.check(*self.depth_fixture(4096))

    def test_rejects_dependency_first_4097_node_path(self):
        with self.assertRaisesRegex(ValueError, 'depth'):
            self.check(*self.depth_fixture(4097))


class IndexedGraphAnalyzerTests(GraphAnalyzerTests):
    version = 2


class GraphReaderPinTests(unittest.TestCase):
    def test_runner_pins_index_reference(self):
        import ast
        source = (HERE / 'run.py').read_text()
        tree = ast.parse(source)
        inputs = next(node for node in ast.walk(tree)
                      if isinstance(node, ast.Assign) and
                      any(isinstance(target, ast.Name) and target.id == 'inputs'
                          for target in node.targets))
        self.assertIn('test_query_index.py',
                      [node.value for node in ast.walk(inputs)
                       if isinstance(node, ast.Constant)])


if __name__ == '__main__':
    unittest.main()
