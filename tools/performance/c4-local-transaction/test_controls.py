#!/usr/bin/env python3
"""Cheap static and synthetic refusal tests. Never invokes GHC or a target."""
import ast
import copy
import json
from pathlib import Path
import re
import unittest

import contracts as C
import run_controls as R

HERE = Path(__file__).resolve().parent
MANIFEST = json.loads((HERE/'manifest.json').read_text())


def synthetic_layout():
    lines = []
    rows = []
    for fixture in MANIFEST['authored_matrix_fixtures']:
        for layout in MANIFEST['matrix']['permutations']:
            for coordinate, _, _ in MANIFEST['matrix']['coordinates']:
                serial = len(rows)+1
                label = f'heteroinput/{serial}/{layout}/{coordinate}/{fixture["label"]}'
                row = (serial, fixture['label'], layout, coordinate, 11, -10**40,
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


class StaticControls(unittest.TestCase):
    def test_fixed_source_inventory(self):
        for path, digest in MANIFEST['pins'].items():
            self.assertEqual(C.sha_bytes((HERE/path).read_bytes()), digest, path)
        for path, provenance in MANIFEST['origins'].items():
            self.assertEqual(C.sha_bytes((HERE/path).read_bytes()), provenance['sha256'])
            self.assertEqual(provenance['transformation'], 'none; exact recovered v10 source bytes')
        self.assertEqual(len(list((HERE/'controls').glob('*.hs'))), 13)
        self.assertEqual(len(list((HERE/'entrypoints').glob('*.hs'))), 2)

    def test_complete_oracle_inverse(self):
        C.verify_oracles(HERE, MANIFEST, None)
        changed = copy.deepcopy(MANIFEST)
        changed['full_algorithm_modules'][0]['original_sha256'] = '0'*64
        with self.assertRaises(ValueError):
            C.verify_oracles(HERE, changed, None)

    def test_no_borrowed_historical_current_collections(self):
        for name in ['FrozenGraph', 'FrozenSolver', 'FrozenConstraint']:
            text = (HERE/'controls'/f'{name}.hs').read_text()
            self.assertIn('import qualified Bootstrap.Map as M;', text)
            self.assertNotIn('import qualified FrozenMap', text)
        for name in ['SessionGraftFixtures', 'SessionFieldFixtures']:
            self.assertIn('import qualified FrozenGraph as G', (HERE/'controls'/f'{name}.hs').read_text())
        self.assertFalse((HERE/'controls/TransactionControls.hs').exists())

    def test_fixed_matrix_input_metadata(self):
        text = (HERE/'controls/C4Fixtures.hs').read_text()
        parsed = [dict(label=n, admitted=a=='True', success=b=='True') for n,_,a,b in
            re.findall(r'Fixture "([^"]+)"(.*?)\b(True|False)\s+(True|False)\s+(?:Nothing|\(Just)', text, re.S)]
        self.assertEqual(parsed, MANIFEST['authored_matrix_fixtures'])
        self.assertEqual(len(parsed), 18)
        self.assertEqual(sum(f['admitted'] for f in parsed)*12, 156)
        self.assertEqual(sum(f['success'] for f in parsed)*12, 156)
        self.assertEqual(MANIFEST['matrix']['cases'], 216)

    def test_shared_support_and_historical_oracle_pins(self):
        for path, digest in {**MANIFEST['shared_support_pins'], **MANIFEST['historical_a1_pins']}.items():
            self.assertEqual(C.sha_bytes((R.A1/path).read_bytes()), digest, path)

    def test_python_parses(self):
        for path in HERE.glob('*.py'):
            ast.parse(path.read_text(), str(path))


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

    def test_builtin_identity_only(self):
        a=b'RawPrelude "builtin-source-v1:'+b'a'*64+b'" payload'
        b=b'RawPrelude "builtin-source-v1:'+b'b'*64+b'" payload'
        self.assertEqual(C.builtin_payload(a),C.builtin_payload(b))
        self.assertNotEqual(C.builtin_payload(a),C.builtin_payload(b+b' changed'))
        for bad in [b'no identity',a+b]:
            with self.assertRaises(ValueError):C.builtin_payload(bad)

    def test_compile_argv_exact_replacements(self):
        source,producer,folder=Path('/source'),Path('/producer'),Path('/fresh')
        flags=['-O2','-i','-i/source/libraries','-odir','/producer/objects','-hidir','/producer/objects']
        official=dict(ghc={'path':'/ghc'},flags=flags)
        command=['/ghc','--make','-j1',*flags,'-rtsopts=ignoreAll','/source/host/ghc/app/emlf/Main.hs',
                 '/producer/host.o','/producer/supervisor.o','-o','/producer/bin/emlf']
        official['commands']=[dict(log='/producer/link-emlf.log',argv=command,cwd='/source',exit_code=0)]
        actual=R.compile_argv(official,source,producer,folder,folder/'Main.hs',folder/'controls')
        self.assertIn('/source/libraries', ''.join(actual))
        self.assertEqual(actual.count('/fresh/objects'),2)
        self.assertIn('/fresh/Main.hs',actual)
        self.assertEqual(actual[-1],'/fresh/controls')
        self.assertNotIn('/producer/host.o',actual)
        for key,value in [('exit_code',1),('cwd','/different'),('argv',command+['-O0'])]:
            bad=copy.deepcopy(official);bad['commands'][0][key]=value
            with self.assertRaises(ValueError):R.compile_argv(bad,source,producer,folder,folder/'Main.hs',folder/'controls')


if __name__ == '__main__':
    unittest.main(verbosity=2)
