"""Host-only exact ownership forwarding controls. No source/native admission."""
import copy
import dataclasses
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resource_ir_v8.checker import check_resources
from resource_ir_v8.forwarding import forward_owned
from resource_ir_v8.program_schema import ResourceError

CASES = json.loads((Path(__file__).with_name('fixtures') / 'ir8-resources.json').read_text())['cases']
BY_NAME = {row['name']: row for row in CASES}


def fixture(name='concrete_scalar'):
    return json.loads(BY_NAME[name]['text'])


def pair(source, target):
    return [{'op': 'retain', 'out': target, 'value': source},
            {'op': 'drop', 'value': source}]


def scalar_pair():
    p = fixture()
    p['entry'][2:2] = pair('answer', 'copy')
    p['entry'][-1]['value'] = 'copy'
    return p


def outcome(function, p):
    # ResourceError deliberately disallows __traceback__ reassignment. Catch it
    # here rather than let unittest/contextlib mutate the immutable exception.
    try:
        return 'accepted', function(p)
    except ResourceError as exc:
        return 'refused', (exc.layer, exc.code, exc.path)


def body(p, root, name):
    return p['entry'] if root == 'entry' else p['functions' if root == 'function' else 'codes'][name]['body']


def read_instruction(p, path):
    value = body(p, path['root'], path['name'])
    for segment in path['segments']:
        value = value[segment]
    return value


def inject_copy(p, definition, derived):
    """Independent test mutation: insert a redundant pair after one definition."""
    p = copy.deepcopy(p)
    source_row = read_instruction(p, definition['path'])
    source = source_row['out']
    new_name = '__forward_test_owner__'
    cap = definition['outputs'][0]['capability']
    for row in derived['instructions']:
        op = read_instruction(p, row['path'])
        for fact in row['inputs']:
            if fact['capability'] != cap:
                continue
            target = op
            for segment in fact['role'][:-1]:
                target = target[segment]
            target[fact['role'][-1]] = new_name
    path = definition['path']
    sequence = body(p, path['root'], path['name'])
    sequence[path['segments'][0] + 1:path['segments'][0] + 1] = pair(source, new_name)
    return p


class ForwardingTests(unittest.TestCase):
    def test_scalar_pair_is_exact_original(self):
        r = forward_owned(scalar_pair())
        self.assertEqual(r.data(), fixture())
        self.assertEqual(r.eliminated_pairs, 1)
        self.assertEqual(r.sha256, hashlib.sha256(r.canonical_json.encode()).hexdigest())
        self.assertEqual(r.derived_sha256, check_resources(r.data()).derived_sha256)
        w = json.loads(r.witness_json)
        self.assertFalse(w['source_admitted'])
        self.assertFalse(w['native_executed'])
        self.assertEqual(w['eliminated_pairs'][0]['source_name'], 'answer')

    def test_concrete_parameter_identity(self):
        r = forward_owned(fixture('closed_identity_retained_parameter'))
        self.assertEqual(r.data(), fixture('explicit_closed_identity'))
        self.assertEqual(r.eliminated_pairs, 1)

    def test_alias_chain(self):
        p = fixture()
        previous = 'answer'
        sequence = []
        for index in range(128):
            target = 'a' + str(index)
            sequence += pair(previous, target)
            previous = target
        p['entry'][2:2] = sequence
        p['entry'][-1]['value'] = previous
        r = forward_owned(p)
        self.assertEqual(r.eliminated_pairs, 128)
        self.assertEqual(r.data(), fixture())

    def test_nonadjacent_pair_is_untouched(self):
        p = scalar_pair()
        p['entry'].insert(3, {'op': 'scalar', 'out': 'other', 'in': 'home', 'kind': 'i64', 'value': 1})
        p['entry'].insert(-1, {'op': 'drop', 'value': 'other'})
        self.assertEqual(forward_owned(p).data(), p)

    def test_releasing_copy_is_not_forwarding(self):
        p = scalar_pair()
        p['entry'][3]['value'] = 'copy'
        p['entry'][-1]['value'] = 'answer'
        self.assertEqual(forward_owned(p).data(), p)

    def test_after_forwarding_new_loan_keeps_exact_anchor(self):
        p = scalar_pair()
        p['entry'][4:4] = [
            {'op': 'borrow', 'out': 'loan', 'value': 'copy'},
            {'op': 'retain', 'out': 'independent', 'value': 'loan'},
            {'op': 'end_borrow', 'value': 'loan'},
            {'op': 'drop', 'value': 'independent'}]
        r = forward_owned(p)
        self.assertEqual(r.eliminated_pairs, 1)
        self.assertEqual(r.data()['entry'][2]['value'], 'answer')
        d = json.loads(check_resources(r.data()).derived_json)
        borrow = next(i for i in d['instructions'] if i['op'] == 'borrow')
        self.assertEqual(borrow['outputs'][0]['anchor']['capability'], borrow['inputs'][0]['capability'])

    def test_live_loan_cannot_be_hidden_by_removing_pair(self):
        p = scalar_pair()
        p['entry'].insert(2, {'op': 'borrow', 'out': 'loan', 'value': 'answer'})
        p['entry'].insert(-1, {'op': 'end_borrow', 'value': 'loan'})
        state, diagnostic = outcome(forward_owned, p)
        self.assertEqual(state, 'refused')
        self.assertEqual(diagnostic[1], 'LIVE_LOAN')

    def test_scheme_pair_is_not_removed(self):
        p = fixture('ready_shared_identity_two_views')
        p['entry'][2:2] = pair('shared', 'saved_scheme')
        for op in p['entry'][4:]:
            if op.get('value') == 'shared':
                op['value'] = 'saved_scheme'
        self.assertEqual(forward_owned(p).data(), p)

    def test_generic_and_nested_bodies_are_unchanged(self):
        p = fixture('ready_shared_identity_two_views')
        p['functions']['id']['body'] = pair('x', 'copy') + [{'op': 'return', 'value': 'copy'}]
        p['entry'][1]['body'][1:1] = pair('f', 'nested_copy')
        p['entry'][1]['body'][-1]['value'] = 'nested_copy'
        self.assertEqual(forward_owned(p).data(), p)

    def test_names_do_not_rewrite_an_unrelated_callback(self):
        p = scalar_pair()
        p['codes']['copy'] = {'result': '#i64', 'captures': {'copy': {'layout': '#i64', 'relation': 'down'}},
            'type_scope': None, 'body': [{'op': 'return', 'value': 'copy'}]}
        p['entry'][4:4] = [{'op': 'thunk', 'out': 'pending', 'in': 'home',
                           'code': 'copy', 'captures': {'copy': 'copy'}},
                          {'op': 'drop', 'value': 'copy'}]
        p['entry'][-1:-1] = [{'op': 'force', 'out': 'ready', 'value': 'pending'}]
        p['entry'][-1]['value'] = 'ready'
        r = forward_owned(p).data()
        thunk = next(i for i in r['entry'] if i['op'] == 'thunk')
        self.assertEqual(thunk['code'], 'copy')
        self.assertEqual(thunk['captures'], {'copy': 'answer'})
        self.assertEqual(r['codes'], p['codes'])

    def test_input_snapshot_and_output_copy_are_isolated(self):
        p = scalar_pair()
        saved = copy.deepcopy(p)
        r = forward_owned(p)
        self.assertEqual(p, saved)
        p['entry'].clear()
        returned = r.data()
        returned['entry'].clear()
        self.assertEqual(r.data(), fixture())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            r.sha256 = 'forged'

    def test_both_checks_are_fresh_even_for_noop(self):
        with patch('resource_ir_v8.forwarding.check_resources', wraps=check_resources) as call:
            r = forward_owned(fixture())
        self.assertEqual(call.call_count, 2)
        self.assertEqual(r.sha256, r.original_sha256)

    def test_deterministic_result(self):
        self.assertEqual(forward_owned(scalar_pair()).witness_json,
                         forward_owned(scalar_pair()).witness_json)

    def test_unknown_instruction_is_not_optimized_away(self):
        p = scalar_pair()
        p['entry'][2]['op'] = 'foreign_retain'
        self.assertEqual(outcome(forward_owned, p)[0], 'refused')

    def test_existing_corpus_preserves_all_140_decisions(self):
        for case in CASES:
            with self.subTest(case=case['name']):
                p = json.loads(case['text'])
                if case['accepted']:
                    r = forward_owned(p)
                    check_resources(r.data())
                else:
                    expected = outcome(check_resources, p)
                    actual = outcome(forward_owned, p)
                    self.assertEqual(expected[0], 'refused')
                    self.assertEqual(actual, expected)

    def test_copy_injection_across_all_concrete_corpus_sites(self):
        tested = 0
        for case in CASES:
            if not case['accepted']:
                continue
            p = json.loads(case['text'])
            derived = json.loads(check_resources(p).derived_json)
            expected = forward_owned(p).canonical_json
            for row in derived['instructions']:
                # instantiate moves a Scheme capability and changes its name;
                # it is not a fresh owner definition for this injection helper.
                if (row['op'] == 'instantiate' or len(row['path']['segments']) != 1
                        or row['type_scope'] is not None or len(row['outputs']) != 1):
                    continue
                fact = row['outputs'][0]
                if (fact['role'] != ['out'] or fact['kind'] != 'value' or fact['mode'] != 'own'
                        or fact['ticket'] or fact['view'] != 'MONO'):
                    continue
                with self.subTest(case=case['name'], path=row['path']):
                    mutant = inject_copy(p, row, derived)
                    # Once owners cannot be copied. This is deliberately a
                    # before-transform error, never a special optimizer permit.
                    status, result = outcome(check_resources, mutant)
                    if status == 'refused':
                        self.assertEqual(result[1], 'ONCE_DUP')
                        continue
                    result = forward_owned(mutant)
                    # An inserted pair can separate a pre-existing pair. This
                    # bounded pass makes one sweep, not a fixed-point promise.
                    self.assertEqual(forward_owned(result.data()).canonical_json, expected)
                    tested += 1
        self.assertGreaterEqual(tested, 70)


if __name__ == '__main__':
    unittest.main()
