#!/usr/bin/env python3
"""Refuse incomplete, malformed or vacuous current control output."""
import json
from pathlib import Path
import unittest

import contracts as C

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE.parent / 'patricia/controls/graph/expectations.json').read_text())


def synthetic_layout():
    lines = []
    rows = []
    for fixture in MANIFEST['authored_matrix_fixtures']:
        for layout in MANIFEST['matrix']['permutations']:
            for coordinate, _, _ in MANIFEST['matrix']['coordinates']:
                serial = len(rows)+1
                label = f'heteroinput/{serial}/{layout}/{coordinate}/{fixture["label"]}'
                row = (serial, fixture['label'], layout, coordinate, 11, -2**60,
                       3, (serial-1) % 3, 0, fixture['admitted'], fixture['success'])
                lines += ['CASE-BEGIN '+label, 'FROZEN-SPEC '+repr(row)]
                if not fixture['success']:
                    lines += ['FROZEN ERROR '+label+': synthetic independent rejection']
                lines += ['CASE-PASS '+label]
                rows.append(row)
    summary = dict(complete=True, cases=216, admitted=156, successes=156, rejections=60,
        root_first=72, root_middle=72, root_last=72, admitted_root_first=52,
        admitted_root_middle=52, admitted_root_last=52, candidate_selected_inputs=False,
        ordinary_timing_samples_added=0)
    lines += ['PASS fixed 216 nonmonotone identity variants with complete Frozen P3 and unchanged transaction oracle',
              json.dumps(summary)]
    return lines


class OutputRefusals(unittest.TestCase):
    def test_transaction_typed_summary(self):
        text = '\n'.join(['PASS synthetic']*9+[json.dumps(C.TRANSACTION)])+'\n'
        self.assertEqual(C.transaction_result(text.encode(), b''), C.TRANSACTION)
        bad = dict(C.TRANSACTION, complete=1)
        with self.assertRaises(ValueError):
            C.transaction_result(text.replace(json.dumps(C.TRANSACTION), json.dumps(bad)).encode(), b'')
        with self.assertRaises(ValueError):
            C.transaction_result(text.encode(), b'warning')
        with self.assertRaises(ValueError):
            C.transaction_result(text.replace('PASS synthetic\n', '', 1).encode(), b'')

    def test_layout_happy(self):
        result = C.heteroinput_result(('\n'.join(synthetic_layout())+'\n').encode(), b'', MANIFEST)
        self.assertEqual(len(result['labels']), 216)
        self.assertEqual(result['summary']['admitted_root_middle'], 52)

    def test_layout_refusals(self):
        original = synthetic_layout()
        mutations = []
        mutations.append(original[3:])  # omitted first complete case
        mutations.append(original[:3]+original)  # duplicate complete case
        bad = original.copy(); bad[0] = original[3]; mutations.append(bad)
        bad = original.copy(); bad[2] = 'CASE-PASS wrong'; mutations.append(bad)
        bad = original.copy(); bad[1] = bad[1].replace(', True, True)', ', False, True)'); mutations.append(bad)
        bad = original.copy(); bad[1] = bad[1].replace(', 3, 0, 0,', ', 3, 3, 0,'); mutations.append(bad)
        bad = original.copy(); j=next(i for i,s in enumerate(bad) if s.startswith('FROZEN ERROR')); del bad[j]; mutations.append(bad)
        bad = original.copy(); bad.insert(-1, 'extra'); mutations.append(bad)
        for field,value in [('complete',1),('root_middle',71),('admitted_root_last',0),('ordinary_timing_samples_added',1)]:
            bad = original.copy(); summary=json.loads(bad[-1]);summary[field]=value;bad[-1]=json.dumps(summary);mutations.append(bad)
        for index, bad in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises((ValueError, IndexError)):
                C.heteroinput_result(('\n'.join(bad)+'\n').encode(), b'', MANIFEST)
        with self.assertRaises(ValueError):
            C.heteroinput_result(('\n'.join(original)+'\n').encode(), b'stderr', MANIFEST)

    def test_public_complete_and_nonvacuous(self):
        summary=dict(complete=True, public_trace_cases=28, validation_cases=12000,
            renamed_cases=400, parsed_expression_cases=8, authored_permission_cases=4,
            a1_private_controls_applicable=False, candidate_output_used_for_expectations=False)
        lines=['PASS finite validation=12000 unification=5616 accepted=1433 unchanged-binders=1392 changed-binders=96',
            'PASS frozen binder-premise outcomes [same-success,same-rejection,changed-success,changed-rejection]=[1361,31,72,24]',
            'PASS frozen dense-rebind permission rejection inventory=synthetic',
            'PASS four authored legal dense permission cases: reuse/fallback x success/exact protected rejection',
            json.dumps(summary)]
        text='\n'.join(lines).encode()
        self.assertEqual(C.public_result(text,b'')['unification_cases'],5616)
        for old,new in [(b'5616',b'5615'),(b'changed-binders=96',b'changed-binders=0'),(b'1361,31,72,24',b'1361,31,72,0')]:
            with self.assertRaises(ValueError):C.public_result(text.replace(old,new),b'')


if __name__ == '__main__':
    unittest.main(verbosity=2)
