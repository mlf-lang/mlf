"""Host controls for the narrow, explicit application-copy API."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path[:0] = [str(Path(__file__).resolve().parent), str(Path(__file__).resolve().parents[1])]
import test_branch_owner_reuse as r
from resource_ir_v8 import application_copy_elision as opt
from resource_ir_v8.program_schema import ResourceError


def fixture(groups=False, pending=False):
    argument = r.add(r.lit(20), r.lit(22)) if pending else r.lit(42)
    raw = r.let(1, r.lam(2, r.INT, r.var(2)),
        r.let(3, r.lam(4, r.INT, r.app(r.var(1), r.var(4))), r.app(r.var(3), argument)))
    return r.planner.plan_fragment(raw, data_groups=groups)['program']


def body(program):
    return next(f['body'] for f in program['functions'].values()
                if [i['op'] for i in f['body'][:5]] ==
                   ['retain', 'retain', 'application', 'drop', 'drop'])


def window(program):
    derived = json.loads(r.check_resources(program).derived_json)
    for index, row in enumerate(derived['instructions']):
        rows = derived['instructions'][index:index + 5]
        if len(rows) == 5 and [x['op'] for x in rows] == ['retain', 'retain', 'application', 'drop', 'drop']:
            return rows, derived['types']
    raise AssertionError('missing fixture window')


class ApplicationCopyTests(unittest.TestCase):
    def test_finite_literal_and_pending_both_placements(self):
        for groups in (False, True):
            for pending in (False, True):
                with self.subTest(groups=groups, pending=pending):
                    p = fixture(groups, pending); saved = copy.deepcopy(p)
                    expected = copy.deepcopy(p); b = body(expected)
                    b[2]['function'], b[2]['argument'] = b[0]['value'], b[1]['value']
                    b[:5] = [b[2]]
                    result = opt.elide_application_input_copies(p)
                    self.assertEqual(result.eliminated_applications, 1)
                    self.assertEqual(result.data(), expected)
                    self.assertEqual(p, saved)
                    checked = r.check_resources(expected)
                    self.assertEqual(result.sha256, checked.sha256)
                    self.assertEqual(r.check_metadata(expected).ir_sha256, checked.sha256)
                    self.assertEqual(json.loads(r.emit_runtime(expected).canonical_ir_json), expected)
                    w = json.loads(result.witness_json)
                    self.assertEqual((w['removed_instructions'], w['rewritten_operands']), (4, 2))
                    self.assertFalse(w['source_admitted']); self.assertFalse(w['native_executed'])

    def test_structural_types_not_type_names(self):
        p = fixture()
        rename = {name: 'Renamed' + name for name in p['types']}
        def rewrite(x):
            if isinstance(x, dict): return {rename.get(k, k): rewrite(v) for k, v in x.items()}
            if isinstance(x, list): return [rewrite(v) for v in x]
            if isinstance(x, str): return rename.get(x, '^' + rename[x[1:]] if x.startswith('^') and x[1:] in rename else x)
            return x
        self.assertEqual(opt.elide_application_input_copies(rewrite(p)).eliminated_applications, 1)

    def test_nonadjacent_or_reordered_is_unchanged(self):
        for kind in ('scalar', 'force', 'borrow', 'early-source-drop', 'reverse-drops'):
            p = fixture(); b = body(p)
            if kind == 'scalar':
                b[2:2] = [{'op': 'scalar', 'out': 'extra', 'in': '$home', 'kind': 'i64', 'value': 0},
                          {'op': 'drop', 'value': 'extra'}]
            elif kind == 'force':
                b[2:2] = [{'op': 'retain', 'out': 'force_input', 'value': b[1]['value']},
                          {'op': 'force', 'out': 'extra', 'value': 'force_input'},
                          {'op': 'drop', 'value': 'extra'}]
            elif kind == 'borrow':
                b[2:2] = [{'op': 'borrow', 'out': 'extra', 'value': b[1]['out']}, {'op': 'end_borrow', 'value': 'extra'}]
            elif kind == 'early-source-drop':
                b.insert(2, b.pop(5))
            else:
                b[3], b[4] = b[4], b[3]
            with self.subTest(kind=kind):
                self.assertEqual(opt.elide_application_input_copies(p).data(), p)

    def test_decision_refuses_scope_ticket_loan_scheme_and_wrong_type(self):
        rows, types = window(fixture())
        for field, value in [('ticket', True), ('anchor', {'capability': 999}),
                             ('mode', 'loan'), ('view', 'SCHEME'), ('scheme', 0)]:
            bad = copy.deepcopy(rows); bad[0]['inputs'][0][field] = value
            self.assertFalse(opt._eligible(bad, types), field)
        for i in range(5):
            bad = copy.deepcopy(rows); bad[i]['type_scope'] = 'S0'
            self.assertFalse(opt._eligible(bad, types))
        for field, value in [('protocol', 'once'), ('result', 999), ('result_identity', 'argument')]:
            bad = copy.deepcopy(types); bad[rows[0]['inputs'][0]['type']][field] = value
            self.assertFalse(opt._eligible(rows, bad), field)
        bad = copy.deepcopy(types); bad[rows[1]['inputs'][0]['type']]['atom'] = '#bool'
        self.assertFalse(opt._eligible(rows, bad))
        for op in ('application_borrow', 'unknown'):
            bad = copy.deepcopy(rows); bad[2]['op'] = op
            self.assertFalse(opt._eligible(bad, types))
        bad = copy.deepcopy(rows); bad[2]['inputs'][0]['capability'] = bad[0]['outputs'][0]['capability']
        self.assertFalse(opt._eligible(bad, types))
        bad = copy.deepcopy(rows); bad[2]['inputs'][1]['capability'] = bad[0]['inputs'][0]['capability']
        self.assertFalse(opt._eligible(bad, types))

    def test_invalid_input_is_rejected_before_rewrite(self):
        for kind in ('wrong-role', 'missing-copy', 'unknown-op'):
            p = fixture(); b = body(p)
            if kind == 'wrong-role': b[2]['function'], b[2]['argument'] = b[2]['argument'], b[2]['function']
            elif kind == 'missing-copy': b[3]['value'] = 'missing'
            else: b[0]['op'] = 'foreign_retain'
            for fn in (r.check_resources, opt.elide_application_input_copies):
                try: fn(p)
                except ResourceError: pass
                else: self.fail(kind + ': invalid raw input accepted')

    def test_fresh_checks_noop_isolation_and_determinism(self):
        p = fixture(); result = opt.elide_application_input_copies(p)
        with patch.object(opt, 'check_resources', wraps=r.check_resources) as check:
            again = opt.elide_application_input_copies(result.data())
            self.assertEqual(check.call_count, 2)
        self.assertEqual(again.eliminated_applications, 0)
        self.assertEqual(again.sha256, result.sha256)
        returned = result.data(); returned['entry'].clear()
        self.assertNotEqual(returned, result.data())
        self.assertEqual(result.witness_json, opt.elide_application_input_copies(p).witness_json)


if __name__ == '__main__':
    unittest.main()
