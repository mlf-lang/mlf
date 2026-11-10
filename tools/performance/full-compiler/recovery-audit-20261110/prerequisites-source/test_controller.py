#!/usr/bin/env python3
"""Static and read-only contract tests. No compiler/target process is started."""
from pathlib import Path
import copy
import importlib.util
import json
import os
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('prerequisites',HERE/'controller.py')
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
spec = importlib.util.spec_from_file_location('prerequisite_launcher',HERE/'run-phase.py')
L = importlib.util.module_from_spec(spec); spec.loader.exec_module(L)


class Contracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = C.load(C.PLANNER.parent/'producer-plan.json')
        cls.auth = C.load(C.UPSTREAM_PATHS['producer_receipt'])
        cls.admission = dict(python='/usr/bin/python3',runtime_library_dir=str(C.TOOLCHAIN/'debian/usr/lib/x86_64-linux-gnu'),
                            upstream={k:dict(path=str(p),sha256=C.sha(p)) for k,p in C.UPSTREAM_PATHS.items()})

    def test_exact_source_helpers(self):
        C.check_pins(C.FIXED)

    def test_all_splits_exact_reference_commit(self):
        # Existing source-only references were copied from this exact Git commit.
        import subprocess
        for basename in ['common.py','prepare.py','worker.py','run.py']:
            data = subprocess.check_output(['git','-C',str(C.SOURCE),'show',
                'e0fa831b3d4cbd395f4d381dbebcb216ebc58365:tools/performance/fresh-split/'+basename])
            self.assertEqual(data,(C.REFERENCE/('split-'+basename)).read_bytes())

    def test_pack_roundtrip(self):
        for values in [[],[''],['alpha','','false','雪:λ'],C.builtin_recipe()['fields']]:
            self.assertEqual(C.unpack(C.pack(values)),values)

    def test_bad_pack_rejected(self):
        for raw in ['01:a','-1:a','2:a','1','x:a','1:a:']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):
                C.unpack(raw)

    def test_all_recipes_inverse_and_order(self):
        built = {}
        for name in C.ORDER:
            part = next(p for p in self.plan['slices'] if p['name'] == name)
            row = self.plan['spec_recipes'][name]
            C.validate_recipe(row,part,built)
            built[name] = row
        C.validate_recipe(C.builtin_recipe(),None,{})
        self.assertEqual(list(built),C.ORDER)

    def test_missing_or_reordered_dependency_rejected(self):
        part = next(p for p in self.plan['slices'] if p['name'] == 'mlf-frontend')
        recipe = self.plan['spec_recipes']['mlf-frontend']
        with self.assertRaises(ValueError):
            C.validate_recipe(recipe,part,{})
        changed = copy.deepcopy(part); changed['dependencies'].reverse()
        built = {n:self.plan['spec_recipes'][n] for n in C.ORDER[:2]}
        with self.assertRaises(ValueError):
            C.validate_recipe(recipe,changed,built)

    def test_recipe_tamper_rejected(self):
        part = self.plan['slices'][0]
        for index in range(8):
            row = copy.deepcopy(self.plan['spec_recipes'][part['name']]); row['fields'][index] += 'x'; row['packed'] = C.pack(row['fields'])
            with self.subTest(index=index),self.assertRaises(ValueError):
                C.validate_recipe(row,part,{})

    def test_exact_query_counts(self):
        for count in [1,475,74,763,173]:
            report = dict(format=1,crate='x',inferred_groups=count,reused_groups=0,
                          groups=[dict(id=str(n),cached=False) for n in range(count)])
            C.fresh(report,'x',count)
            for key,value in [('format',True),('crate','wrong'),('reused_groups',1),('inferred_groups',count+1)]:
                changed = copy.deepcopy(report);changed[key] = value
                with self.assertRaises(ValueError):
                    C.fresh(changed,'x',count)
            changed = copy.deepcopy(report);changed['groups'][0]['cached'] = True
            with self.assertRaises(ValueError): C.fresh(changed,'x',count)

    def test_duplicate_group_rejected(self):
        with self.assertRaises(ValueError):
            C.fresh(dict(format=1,crate='x',inferred_groups=2,reused_groups=0,groups=[dict(id='a',cached=False)]*2),'x',2)

    def test_public_show_crate_contract(self):
        C.interface('crate c\nmodule A\ndependency dep /path/to/unit.mlfci hash\n','c',['A'],{'dep':'/path/to/unit.mlfci'})
        for text in ['crate c\nmodule A\nmodule A\n','crate c\nmodule B\n','crate wrong\nmodule A\n']:
            with self.assertRaises(ValueError): C.interface(text,'c',['A'],{})
        with self.assertRaises(ValueError):
            C.interface('crate c\nmodule A\ndependency dep /changed hash\n','c',['A'],{'dep':'/expected'})

    def test_builtin_module_ownership_fixed(self):
        C.interface('crate '+C.BUILTIN+'\nmodule Prelude\nmodule MLF.Primitive\n',C.BUILTIN,['Prelude','MLF.Primitive'],{})
        data = (C.SOURCE/'libraries/mlf-crates/Bootstrap/CrateArtifact.hs').read_text()
        self.assertIn('CrateInterface identity [] ((:) "Prelude" ((:) "MLF.Primitive" []))',data)

    def test_forbidden_environment_even_empty(self):
        C.reject_instrumentation({})
        for key in C.FORBIDDEN:
            with self.assertRaises(ValueError): C.reject_instrumentation({key:''})

    def test_exact_allowlist_no_leak(self):
        runtime = C.module(C.RUNTIME,C.FIXED[str(C.RUNTIME)],'runtime_test')
        with patch.dict(os.environ,{'LD_PRELOAD':'evil','GHCRTS':'-A1G','MLF_DIAGNOSTIC_X':'1'},clear=False):
            env = runtime.target_environment(Path(self.admission['runtime_library_dir']))
        self.assertNotIn('LD_PRELOAD',env);self.assertNotIn('MLF_DIAGNOSTIC_X',env);self.assertEqual(env['GHCRTS'],'')
        self.assertEqual(env['PATH'],'/usr/bin:/bin')

    def test_deadline_cap(self):
        with patch.object(C.time,'monotonic_ns',return_value=100*10**9):
            self.assertEqual(C.remaining(400*10**9,180),180)
            self.assertEqual(C.remaining(110*10**9,180),10)
            with self.assertRaises(ValueError): C.remaining(100*10**9,180)

    def test_fresh_absence_including_dangling_symlink(self):
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            root = Path(tmp); C.absent(root/'missing')
            (root/'link').symlink_to(root/'missing')
            with self.assertRaises(ValueError): C.absent(root/'link')
            with self.assertRaises(ValueError): C.safe(root/'link')
            (root/'file').write_text('x')
            with self.assertRaises(ValueError): C.absent(root/'file')

    def test_full_object_inputs_real_and_negative(self):
        producer = C.UPSTREAM/'build/producer'
        pins = C.object_inputs(self.auth,producer)
        self.assertEqual(len(pins),284)
        for variant in ['missing','extra','bad_hash']:
            auth = copy.deepcopy(self.auth); key = next(iter(auth['object_inputs']))
            if variant == 'missing': del auth['object_inputs'][key]
            elif variant == 'extra': auth['object_inputs']['objects/unlisted.o'] = '0'*64
            else: auth['object_inputs'][key] = '0'*64
            with self.subTest(variant=variant),self.assertRaises(ValueError): C.object_inputs(auth,producer)

    def test_bound_real_producer_and_postcontrols(self):
        C.bind_upstream(self.admission,self.auth)

    def test_unrelated_guard_rejected(self):
        original = C.load
        for key in ['command','cwd','complete']:
            def fake(path,key=key):
                result = original(path)
                if Path(path) == C.UPSTREAM_PATHS['build_controller']:
                    result[key] = [] if key == 'command' else ('/tmp' if key == 'cwd' else False)
                return result
            with patch.object(C,'load',side_effect=fake),self.assertRaises(ValueError):
                C.bind_upstream(self.admission,self.auth)

    def test_static_recipe_matches_current_plan(self):
        planner = C.module(C.PLANNER,C.sha(C.PLANNER),'planner_test')
        pins = C.source_inputs(self.admission,self.plan,planner)
        self.assertGreater(len(pins),3800)
        self.assertFalse(C.WORKSPACE.exists())

    def test_owned_pid_identity_and_cross_session(self):
        def row(ppid,session,start='100',state='S'):
            return dict(ppid=ppid,pgid=session,session=session,starttime=start,state=state)
        rows = {10:row(1,10),11:row(10,11),12:row(11,12),99:row(1,99)}
        tracked = {}; owned = L.owned_rows(rows,tracked,10,'100')
        self.assertEqual(set(owned),{10,11,12})
        # Previously owned orphan remains owned across session/parent changes.
        rows.pop(10);rows[11]['ppid'] = 1
        self.assertEqual(set(L.owned_rows(rows,tracked,10,'100')),{11,12})
        # Reused PID must not become owned again without ancestry evidence.
        rows[11] = row(1,11,'101');rows[12]['ppid'] = 1
        self.assertEqual(set(L.owned_rows(rows,tracked,10,'100')),{12})

    def test_compile_failure_retains_receipt_and_stops_before_libraries(self):
        import types
        calls = []
        class FakeRunner:
            def __init__(self,*args): pass
            def run(self,argv,cwd,folder,timed=False):
                calls.append([str(x) for x in argv]); folder.mkdir(parents=True)
                (folder/'stdout').write_bytes(b''); (folder/'stderr').write_bytes(b'')
                failed = '--compile-crate' in calls[-1]
                row = dict(complete=not failed,exit_code=1 if failed else 0)
                C.save(folder/'command.json',row)
                if failed: raise RuntimeError('intentional fake compile failure')
                return row
        H = types.SimpleNamespace(Runner=FakeRunner,authenticate=lambda *args:self.auth)
        runtime = types.SimpleNamespace(target_environment=lambda *args:{},runtime_configuration=lambda *args:{},
            identity=lambda H,p:dict(path=str(p)),elf_interpreter=lambda *args:Path('/not-executed/loader'),
            loader_rows=lambda *args:[])
        def fake_module(path,*args):
            return H if path == C.HELPER else (runtime if path == C.RUNTIME else object())
        a = dict(self.admission,producer=str(C.UPSTREAM/'build/producer'),plan=dict(path='fake',sha256='0'*64),
                 code_pins={str(C.PLANNER):C.sha(C.PLANNER)})
        with tempfile.TemporaryDirectory(dir=HERE) as tmp:
            work = Path(tmp)/'fresh';work.mkdir()
            with patch.object(C,'WORKSPACE',work),patch.object(C,'module',side_effect=fake_module),\
                 patch.object(C,'validate_admission',return_value=(a,self.plan,{})),\
                 patch.object(C,'source_inputs',return_value={}),patch.object(C,'object_inputs',return_value={}),\
                 patch.object(C,'bind_upstream'),patch.dict(os.environ,{'MLF_BUILD_SCOPE':str(os.getpgrp())}):
                with self.assertRaisesRegex(RuntimeError,'intentional fake compile failure'):
                    C.worker(Path('fake'),'0'*64,C.time.monotonic_ns()+300*10**9)
            receipt = C.load(work/'prerequisites/receipt.json')
            self.assertFalse(receipt['complete'])
            self.assertEqual([r['name'] for r in receipt['slices']],['builtin-fixture'])
            self.assertEqual(sum('--compile-crate' in argv for argv in calls),1)
            self.assertFalse((work/'dependencies/mlf-foundation').exists())

    def test_no_heavy_execution_in_static_test(self):
        source = (HERE/'controller.py').read_text()
        self.assertNotIn('--crate-to-llvm',source)
        self.assertNotIn('clang',source)
        self.assertNotIn('verifyAll=True',source)
        self.assertIn('H.Runner(WORKSPACE,dict(LIMITS,wall_seconds=cap))',source)
        self.assertIn('H.authenticate(producer,SOURCE)',source)


if __name__ == '__main__':
    import sys
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Contracts)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    C.save(HERE/'static-tests.json',dict(complete=result.wasSuccessful(),compiler_started=False,source_commit=C.BASE,
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        tested_code={str(HERE/n):C.sha(HERE/n) for n in ['controller.py','run-phase.py','test_controller.py']}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
