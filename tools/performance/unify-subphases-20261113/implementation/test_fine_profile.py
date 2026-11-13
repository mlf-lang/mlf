"""Synthetic raw-report tests only. No Haskell, subprocess, lock or stage launch."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import fine_profile as F

ROOT = Path('/synthetic-reviewed-mirror')
SPEC = F.load_fine_spec()
IDS = {site['site_id']: 10 + i for i, site in enumerate(SPEC['r16_fine']['sites'])}


def cc(i, label, module='Test', location='Test.hs:1:1', caf=False):
    return dict(id=i, label=label, module=module, src_loc=location, is_caf=caf)


def node(i, alloc=0, ticks=0, children=None):
    return dict(id=i, entries=1, alloc=alloc, ticks=ticks, children=children or [])


def fixture():
    centres = [cc(1, 'MAIN', 'MAIN', '<built-in>'), cc(2, 'SOLVE'),
               cc(3, 'CONSTRAINT_GENERATION'), cc(4, 'ENCODE'), cc(5, 'unlabelled')]
    for site in SPEC['r16_fine']['sites']:
        a, b = site['fine_rhs_span']['start'], site['fine_rhs_span']['end_exclusive']
        location = str(ROOT / site['path']) + ':({},{})-({},{})'.format(*a, *b)
        centres.append(cc(IDS[site['site_id']], site['label'], site['module'], location))
    tree = node(1, 1, 1, [node(2, 2, 1, [
        node(IDS['prepare'], 3, 1),
        node(IDS['steps'], 5, 1, [
            node(IDS['transaction-distinct'], 7, 1, [node(IDS['local-unify'], 11, 1)]),
            node(IDS['transaction-prepared'], 13, 1),
            node(IDS['expansion'], 17, 1),
            node(IDS['finish-audit'], 19, 1),
            node(5, 23, 1)])]),
        node(3, 29, 1, [node(IDS['prepare'], 31, 1)])])
    pending, alloc, ticks = [tree], 0, 0
    while pending:
        item = pending.pop(); alloc += item['alloc']; ticks += item['ticks']; pending.extend(item['children'])
    return dict(program='synthetic-not-an-execution', arguments=[], rts_arguments=['-pj'], end_time='synthetic',
                initial_capabilities=0, total_time=0, total_ticks=ticks, tick_interval=1000,
                total_alloc=alloc, cost_centres=centres, profile=tree)


def matrix(result):
    return {(row['coarse'], row['fine']): row for row in result['matrix']}


def synthetic_unit_evidence():
    # Shape-only data for a unit test, never exported as a real control receipt.
    return dict(toolchain_sha256='a' * 64, installed_rts_definition_sha256='b' * 64,
                control_receipt_sha256='c' * 64, writer_alloc_unit='bytes',
                control_expected_bytes=64, control_observed_raw=64, control_passed=True)


class FineProfileTests(unittest.TestCase):
    def parse(self, data=None):
        return F.partition(json.dumps(fixture() if data is None else data), ROOT)

    def test_disjoint_nearest_fine_conserves_original_coarse_rows(self):
        result, coarse = self.parse(); cells = matrix(result)
        self.assertEqual(cells['SOLVE', 'SOLVER_STEPS']['alloc'], 28)
        self.assertEqual(cells['SOLVE', 'SOLVER_TRANSACTION']['alloc'], 20)
        self.assertEqual(cells['SOLVE', 'SOLVER_LOCAL_UNIFY']['alloc'], 11)
        self.assertEqual(cells['SOLVE', 'UNLABELLED']['alloc'], 2)
        for bucket, expected in coarse['partition'].items():
            for field in ('alloc', 'ticks', 'nodes'):
                self.assertEqual(sum(row[field] for row in result['matrix'] if row['coarse'] == bucket), expected[field])
        self.assertEqual(sum(row['alloc'] for row in result['matrix']), coarse['total_alloc'])
        self.assertGreater(sum(row['inherited_alloc'] for row in coarse['stacks']), coarse['total_alloc'])

    def test_both_transaction_sites_remain_distinct_below_same_label(self):
        result, _ = self.parse()
        rows = {(r['coarse'], r['site']): r['alloc'] for r in result['site_matrix']}
        self.assertEqual(rows['SOLVE', 'transaction-distinct'], 7)
        self.assertEqual(rows['SOLVE', 'transaction-prepared'], 13)

    def test_same_fine_site_can_run_under_generation(self):
        result, _ = self.parse(); cells = matrix(result)
        self.assertEqual(cells['SOLVE', 'SOLVER_PREPARE']['alloc'], 3)
        self.assertEqual(cells['CONSTRAINT_GENERATION', 'SOLVER_PREPARE']['alloc'], 31)

    def test_new_coarse_boundary_resets_ancestor_fine(self):
        data = fixture()
        # The existing unlabelled child of STEPS now introduces ENCODE.
        data['profile']['children'][0]['children'][1]['children'][-1]['id'] = 4
        result, _ = self.parse(data); cells = matrix(result)
        self.assertEqual(cells['ENCODE', 'UNLABELLED']['alloc'], 23)
        self.assertNotIn(('ENCODE', 'SOLVER_STEPS'), cells)

    def test_declared_but_unobserved_is_not_fabricated_as_observed(self):
        data = fixture(); data['profile'] = node(1, data['total_alloc'], data['total_ticks'])
        result, _ = self.parse(data)
        self.assertEqual(result['defined_sites'], sorted(F.EXPECTED))
        self.assertEqual(result['observed_sites'], [])
        self.assertEqual(result['unobserved_sites'], sorted(F.EXPECTED))

    def test_multiple_cost_centre_ids_for_one_reviewed_site_allowed(self):
        data = fixture(); centre = copy.deepcopy(data['cost_centres'][5]); centre['id'] = 101
        data['cost_centres'].append(centre)
        data['profile']['children'][1]['children'][0]['id'] = 101
        self.parse(data)

    def reject(self, mutation):
        data = fixture(); mutation(data)
        with self.assertRaises(ValueError): self.parse(data)

    def test_unknown_fine_label_rejected(self):
        self.reject(lambda d: d['cost_centres'].append(cc(99, 'SOLVER_UNREVIEWED')))

    def test_correct_label_wrong_module_rejected(self):
        self.reject(lambda d: d['cost_centres'][5].update(module='Bootstrap.Fake'))

    def test_correct_label_wrong_source_path_rejected(self):
        self.reject(lambda d: d['cost_centres'][5].update(src_loc='/foreign/Graph/Solver.hs:242:1-5'))

    def test_correct_label_wrong_site_span_rejected(self):
        self.reject(lambda d: d['cost_centres'][5].update(src_loc=str(ROOT / F.EXPECTED['prepare'][2]) + ':1:1-5'))

    def test_fine_caf_rejected(self):
        self.reject(lambda d: d['cost_centres'][5].update(is_caf=True))

    def test_missing_unused_site_declaration_rejected(self):
        data = fixture(); data['profile'] = node(1, data['total_alloc'], data['total_ticks']); data['cost_centres'].pop()
        with self.assertRaisesRegex(ValueError, 'eleven fine sites'): self.parse(data)

    def test_single_line_source_locations_supported(self):
        data = fixture()
        site = next(s for s in SPEC['r16_fine']['sites'] if s['site_id'] == 'steps')
        centre = next(c for c in data['cost_centres'] if c['id'] == IDS['steps'])
        a, b = site['fine_rhs_span']['start'], site['fine_rhs_span']['end_exclusive']
        for suffix in [f'{a[0]}:{a[1]}-{b[1]}', f'{a[0]}:{a[1]}']:
            centre['src_loc'] = str(ROOT / site['path']) + ':' + suffix
            self.parse(data)

    def test_malformed_source_extent_rejected(self):
        path = ROOT / F.EXPECTED['prepare'][2]
        for suffix in ['242:0-5', '242:5-1', '(243,1)-(242,1)', '242', '242:1-2:3']:
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                F.source_extent(str(path) + ':' + suffix, path)

    def test_duplicate_raw_key_rejected_by_original_parser(self):
        raw = json.dumps(fixture()).replace('"total_alloc":', '"total_alloc": 1, "total_alloc":', 1)
        with self.assertRaises(ValueError): F.partition(raw, ROOT)

    def test_wrong_raw_totals_rejected_by_original_parser(self):
        self.reject(lambda d: d.update(total_alloc=d['total_alloc'] + 1))

    def test_qualified_summary_is_exact_reparse_not_trusted_stack_input(self):
        _, coarse = self.parse(); evidence = synthetic_unit_evidence()
        supplied = F.COARSE.qualify_units(coarse, evidence, toolchain_sha256='a' * 64)
        self.assertEqual(F.match_qualified_summary(coarse, supplied, 'a' * 64), evidence)
        for field in ['self_alloc', 'inherited_alloc', 'entries']:
            mutated = copy.deepcopy(supplied); mutated['stacks'][0][field] += 1
            with self.subTest(field=field), self.assertRaises(ValueError):
                F.match_qualified_summary(coarse, mutated, 'a' * 64)

    def test_bool_number_equality_cannot_hide_summary_tampering(self):
        _, coarse = self.parse()
        supplied = copy.deepcopy(F.COARSE.qualify_units(coarse, synthetic_unit_evidence(), toolchain_sha256='a' * 64))
        supplied['stacks'][0]['entries'] = True
        with self.assertRaises(ValueError): F.match_qualified_summary(coarse, supplied, 'a' * 64)

    def test_wrong_toolchain_and_unqualified_summary_rejected(self):
        _, coarse = self.parse()
        with self.assertRaises(ValueError): F.match_qualified_summary(coarse, coarse, 'a' * 64)
        supplied = F.COARSE.qualify_units(coarse, synthetic_unit_evidence(), toolchain_sha256='a' * 64)
        with self.assertRaises(ValueError): F.match_qualified_summary(coarse, supplied, 'd' * 64)

    def test_digest_and_symlink_input_rejected(self):
        with tempfile.TemporaryDirectory(prefix='r16-pure-reader-') as directory:
            path = Path(directory) / 'raw'; path.write_bytes(b'raw')
            self.assertEqual(F.read_verified(path, F.digest(b'raw')), b'raw')
            with self.assertRaises(ValueError): F.read_verified(path, '0' * 64)
            link = Path(directory) / 'link'; link.symlink_to(path)
            with self.assertRaises(ValueError): F.read_verified(link, F.digest(b'raw'))

    def test_output_explicitly_cannot_establish_execution_or_bytes(self):
        result, _ = self.parse()
        self.assertIn('pending', result['unit'])
        for field in ['actual_execution_established_by_this_tool', 'byte_control_reexecuted', 'resume_authorized']:
            self.assertIs(result[field], False)

    def test_nested_local_unify_four_children_are_disjoint_and_roll_up(self):
        data = fixture()
        local = data['profile']['children'][0]['children'][1]['children'][0]['children'][0]
        sites = ['unify-input-validation', 'unify-first-order', 'unify-rebind', 'unify-output-validation']
        amounts = [2, 3, 5, 7]
        local['children'] = [node(IDS[s], amount, 1) for s, amount in zip(sites, amounts)]
        data['total_alloc'] += sum(amounts); data['total_ticks'] += 4
        result, coarse = self.parse(data); cells = matrix(result)
        self.assertEqual(cells['SOLVE', 'SOLVER_LOCAL_UNIFY']['alloc'], 11)
        for site, amount in zip(sites, amounts):
            self.assertEqual(cells['SOLVE', F.EXPECTED[site][0]]['alloc'], amount)
        family = next(r for r in result['local_unify_family_by_coarse'] if r['coarse'] == 'SOLVE')
        self.assertEqual(family, dict(coarse='SOLVE', alloc=28, ticks=5, nodes=5))
        self.assertEqual(sum(r['alloc'] for r in result['matrix']), coarse['total_alloc'])
        self.assertEqual(sum(r['alloc'] for r in result['matrix'] if r['coarse'] == 'SOLVE'),
                         coarse['partition']['SOLVE']['alloc'])

    def test_unify_family_rollup_respects_generation_and_coarse_reset(self):
        data = fixture()
        data['profile']['children'][1]['children'].append(node(IDS['local-unify'], 2, 1, [
            node(IDS['unify-rebind'], 3, 1, [node(4, 5, 1)])]))
        data['total_alloc'] += 10; data['total_ticks'] += 3
        result, _ = self.parse(data)
        family = {r['coarse']: r['alloc'] for r in result['local_unify_family_by_coarse']}
        self.assertEqual(family, {'SOLVE': 11, 'CONSTRAINT_GENERATION': 5})
        self.assertEqual(matrix(result)['ENCODE', 'UNLABELLED']['alloc'], 5)
        self.assertNotIn('ENCODE', family)


if __name__ == '__main__': unittest.main()
