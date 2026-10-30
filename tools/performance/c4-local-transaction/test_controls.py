#!/usr/bin/env python3
"""Cheap static and synthetic refusal tests. Never invokes GHC or a target."""
import ast
import copy
import json
import hashlib
import os
from pathlib import Path
import re
import tempfile
import unittest

import contracts as C
import run_controls as R
import qualify_fixed14 as Q

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


class Fixed14CacheContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='c4-fixed14-pure-')
        self.root = Path(self.temporary.name)
        self.cache = self.root/'queries'
        self.cache.mkdir()
        keys = [hashlib.sha256(('independent synthetic key '+str(i)).encode()).hexdigest() for i in range(544)]
        self.report = dict(inferred_groups=544,reused_groups=0,
            groups=[dict(query_key=key,cached=False) for key in keys])
        for key in keys:
            (self.cache/(key+'.mlfq')).write_bytes(b'synthetic cache fixture; not a real compiler output')
        self.scratch = b'independent synthetic key 543'
        (self.cache/'query-key.new').write_bytes(self.scratch)
        (self.cache/'.lock').write_bytes(b'')

    def tearDown(self):
        self.temporary.cleanup()

    def check(self, report=None, directory=None):
        return Q.query_cache_inventory(directory or self.cache,report or self.report)

    def test_exact_source_defined_success(self):
        result=self.check()
        self.assertEqual(result['query_files'],544)
        self.assertEqual(result['total_regular_files'],546)
        self.assertEqual(result['scratch_key_sha256'],self.report['groups'][-1]['query_key'])

    def test_report_mutations_refused(self):
        for field,value in [('inferred_groups',543),('inferred_groups',True),('reused_groups',1),('reused_groups',False)]:
            bad=copy.deepcopy(self.report);bad[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(RuntimeError):self.check(bad)
        mutations=[]
        bad=copy.deepcopy(self.report);bad['groups'].pop();mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'].append(bad['groups'][-1]);mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'][0]['cached']=True;mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'][0]['cached']=0;mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'][0]['query_key']=bad['groups'][1]['query_key'];mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'][0]['query_key']=bad['groups'][0]['query_key'].upper();mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'][0]['query_key']='../escape';mutations.append(bad)
        bad=copy.deepcopy(self.report);bad['groups'].reverse();mutations.append(bad)
        for i,bad in enumerate(mutations):
            with self.subTest(mutation=i),self.assertRaises(RuntimeError):self.check(bad)

    def test_missing_extra_and_wrong_names_refused(self):
        first=self.cache/(self.report['groups'][0]['query_key']+'.mlfq')
        original=first.read_bytes()
        for path in [first,self.cache/'.lock',self.cache/'query-key.new']:
            data=path.read_bytes();path.unlink()
            try:
                with self.subTest(missing=path.name),self.assertRaises(RuntimeError):self.check()
            finally:path.write_bytes(data)
        for name in ['unexpected',first.name+'.new','f'*64+'.mlfq']:
            extra=self.cache/name;extra.write_bytes(b'extra')
            try:
                with self.subTest(extra=name),self.assertRaises(RuntimeError):self.check()
            finally:extra.unlink()
        first.unlink();wrong=self.cache/('e'*64+'.mlfq');wrong.write_bytes(original)
        with self.assertRaises(RuntimeError):self.check()

    def test_sidecar_content_refusals(self):
        for path,data in [(self.cache/'.lock',b'not empty'),(self.cache/'query-key.new',b''),
                          (self.cache/'query-key.new',b'independent synthetic key 0')]:
            old=path.read_bytes();path.write_bytes(data)
            try:
                with self.subTest(file=path.name,value=data),self.assertRaises(RuntimeError):self.check()
            finally:path.write_bytes(old)

    def test_nonregular_and_symlink_refusals(self):
        first=self.cache/(self.report['groups'][0]['query_key']+'.mlfq')
        for path in [first,self.cache/'.lock',self.cache/'query-key.new']:
            data=path.read_bytes();path.unlink()
            for kind in ['directory','symlink','dangling','fifo']:
                if kind=='directory':path.mkdir()
                elif kind=='fifo':os.mkfifo(path)
                else:path.symlink_to(self.root/('absent' if kind=='dangling' else 'regular'))
                (self.root/'regular').write_bytes(data)
                try:
                    with self.subTest(file=path.name,kind=kind),self.assertRaises(RuntimeError):self.check()
                finally:
                    if kind=='directory':path.rmdir()
                    else:path.unlink()
            path.write_bytes(data)
        link=self.root/'alias';link.symlink_to(self.cache,target_is_directory=True)
        with self.assertRaises(RuntimeError):self.check(directory=link)


class Fixed14PartialReceipt(unittest.TestCase):
    def test_native_success_saved_before_postcheck_failure(self):
        record=dict(commands=[],target_steps=[])
        step=dict(side='base');record['target_steps'].append(step)
        snapshots=[]
        def save():snapshots.append(copy.deepcopy(record))
        class Fake:
            def run(self,*args):return dict(complete=True,exit_code=0,argv=['synthetic-only'])
        Q.run_observed(Fake(),record,step,[],Path('/unused'),Path('/unused'),save)
        with self.assertRaisesRegex(RuntimeError,'synthetic postcheck'):
            raise RuntimeError('synthetic postcheck')
        self.assertTrue(snapshots[-1]['target_steps'][0]['native_completed'])
        self.assertFalse(snapshots[-1]['target_steps'][0]['postchecks_complete'])
        self.assertEqual(snapshots[-1]['target_steps'][0]['phase'],'postchecks-pending')
        self.assertEqual(len(snapshots[-1]['commands']),1)
        self.assertEqual(snapshots[0]['target_steps'][0]['phase'],'native-launch-requested')

    def test_failed_native_receipt_preserved(self):
        with tempfile.TemporaryDirectory(prefix='c4-partial-pure-') as name:
            out=Path(name);record=dict(commands=[],target_steps=[]);step=dict(side='candidate')
            record['target_steps'].append(step);snapshots=[]
            class Fake:
                def run(self,*args):
                    (out/'command.json').write_text(json.dumps(dict(complete=False,exit_code=7)))
                    raise RuntimeError('synthetic native failure')
            with self.assertRaisesRegex(RuntimeError,'synthetic native failure'):
                Q.run_observed(Fake(),record,step,[],out,out,lambda:snapshots.append(copy.deepcopy(record)))
            self.assertEqual(snapshots[-1]['target_steps'][0]['phase'],'native-failed-or-interrupted')
            self.assertEqual(snapshots[-1]['commands'][0]['exit_code'],7)
            self.assertFalse(snapshots[-1]['target_steps'][0]['native_completed'])

    def test_truthy_or_guarded_completion_refused(self):
        for complete,code in [(1,0),(False,0),(True,False),(True,1)]:
            record=dict(commands=[],target_steps=[]);step={};record['target_steps'].append(step)
            class Fake:
                def run(self,*args):return dict(complete=complete,exit_code=code)
            with self.subTest(complete=complete,code=code),self.assertRaises(RuntimeError):
                Q.run_observed(Fake(),record,step,[],Path('/unused'),Path('/unused'),lambda:None)
            self.assertFalse(step['native_completed'])
            self.assertFalse(step['postchecks_complete'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
