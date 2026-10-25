#!/usr/bin/env python3
"""Pure/fake controls for the opt-in benchmark; no GHC or compiler suite."""
import tempfile
import contextlib
import io
import json
import sys
import subprocess
from unittest.mock import patch
import unittest
from pathlib import Path
import perf_inference as perf


class ProbeOracle(unittest.TestCase):
    def test_exact_oracle(self):
        self.assertEqual(perf.parse_probe_output('PASS /tmp/a.emlf wall_ns=12 cpu_ps=34\n', '/tmp/a.emlf'),
                         {'wall_s': 12/1e9, 'cpu_s': 34/1e12})

    def test_rejects_missing_extra_reordered_and_wrong_path(self):
        for text in [
            'PASS /tmp/a.emlf wall_ns=12 cpu_ps=34',
            'PASS /tmp/a.emlf wall_ns=12 cpu_ps=34\nextra\n',
            'extra\nPASS /tmp/a.emlf wall_ns=12 cpu_ps=34\n',
            'PASS /tmp/b.emlf wall_ns=12 cpu_ps=34\n',
            'PASS /tmp/a.emlf cpu_ps=34 wall_ns=12\n',
            'PASS /tmp/a.emlf wall_ns=12 cpu_ps=34\r\n',
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                perf.parse_probe_output(text, '/tmp/a.emlf')

    def test_guards_and_rehash_are_explicit(self):
        with self.assertRaises(ValueError):
            perf.require(False, 'not disabled by python -O')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'source'
            path.write_text('before')
            inputs = {str(path): perf.sha(path)}
            perf.verify_inputs(inputs)
            path.write_text('after')
            with self.assertRaises(ValueError):
                perf.verify_inputs(inputs)



class FakeMainAdmission(unittest.TestCase):
    def exercise(self, change=None, overrides=None, mismatch=False, mutate=False, fail=False, controls=False, mutate_object=False,
                 reuse=False, reuse_change=False, reuse_tamper=False, reuse_incomplete=False, reuse_flags=False,
                 reuse_probe_change=None, reuse_control_change=False, reuse_escape=False, reuse_mismatch=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = root/'probes'
            sources.mkdir()
            for name in ['Main.hs', 'Controls.hs', 'fixtures.py']:
                (sources/name).write_text('fixture ' + name)
            implementation = root/'libraries/Bootstrap/ClassDemand.hs'
            implementation.parent.mkdir(parents=True)
            implementation.write_text('baseline implementation\n')
            test_source = root/'tests/shared/MLF/Tests/ClassDemand.hs'
            test_source.parent.mkdir(parents=True)
            test_source.write_text('planner test source\n')
            host = root/'host/ghc/cbits/host.c'
            supervisor = root/'runtime/mlf_process_supervisor.c'
            for source in [host, supervisor]:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('/* no local includes in this fake transport */\n')
            manifest = root/'shared-sources.json'
            manifest.write_text('{"source_roots":["libraries","tests/shared","host/ghc"]}')
            tools = {}
            for name in ['ghc', 'cc']:
                path = root/name
                path.write_text('fake official tool bytes ' + name)
                tools[name] = {'path': str(path), 'sha256': perf.sha(path)}
            tools['ghc']['version'] = '9.14.1'
            producer = root/'producer'
            (producer/'objects/Bootstrap').mkdir(parents=True)
            objects = {}
            for suffix in ['.o', '.hi']:
                path = producer/('objects/Bootstrap/ClassDemand'+suffix)
                path.write_text('held artifact '+suffix)
                objects[str(path.relative_to(producer))] = perf.sha(path)
            def item(path, role=None):
                value = {'path': str(path), 'sha256': perf.sha(path)}
                if role:
                    value['role'] = role
                return value
            receipt = {
                'complete': True, 'optimization': '2', 'typecheck_only': False,
                'cabal_manifest': {'path': str(root/'mlf-shared.cabal')},
                **tools,
                'flags': ['-O2','-fpedantic-bottoms','-fno-state-hack','-clear-package-db',
                          '-global-package-db','-no-user-package-db','-hide-all-packages'],
                'shared_inputs': {'Bootstrap.ClassDemand': item(implementation, 'implementation')},
                'host_inputs': {str(p.relative_to(root)): item(p) for p in [host,supervisor]},
                'configuration_inputs': {'shared-sources.json':item(manifest)}, 'object_inputs': objects,
                'toolchain': {'files': {}}, 'installed_dependencies': {'files': {}},
            }
            if change:
                change(receipt)
            receipt_path = producer/'receipt.json'
            receipt_path.write_text(json.dumps(receipt))
            baselines = {str(p.relative_to(root)): p.read_bytes() for p in [implementation,host,supervisor,manifest]}
            calls = []
            class FakeRunner:
                def __init__(self, task_root, output, evidence, save):
                    self.output, self.evidence, self.save = output, evidence, save
                def run(self, name, command, **kwargs):
                    argv = list(map(str, command));calls.append(name)
                    entry = {'name':name, 'argv':argv, 'state':'running'}
                    self.evidence['commands'].append(entry)
                    self.save()
                    if fail and name == 'link-baseline':
                        entry['state'] = 'failed';self.save()
                        raise RuntimeError('deliberate fake tool failure')
                    stdout = b''
                    if name == 'resolve-baseline':
                        stdout = b'a'*40+b'\n'
                    elif name.startswith('authenticate-source-'):
                        rel = argv[2].split(':',1)[1]
                        stdout = b'incorrect pinned bytes' if mismatch else baselines[rel]
                    elif name.startswith('build-') or name.startswith('compile-') or name.startswith('link-'):
                        if '--make' in argv:
                            objects_dir = Path(argv[argv.index('-odir')+1])
                            if name in ['build-baseline','build-candidate']:
                                entry['candidate_cache_present_before_make'] = (objects_dir/'Bootstrap/ClassDemand.hi').exists()
                                entry['cache_before_make'] = {module:(objects_dir/(module+'.hi')).exists()
                                    for module in ['Main','PerfControls','MLF/Tests/ClassDemand']}
                            module = 'PerfControls' if '-main-is' in argv else 'Main'
                            relative_names = [module] if module == 'PerfControls' else ['Main','Bootstrap/ClassDemand','MLF/Tests/ClassDemand']
                            for relative in relative_names:
                                for suffix in ['.o','.hi']:
                                    path = objects_dir/(relative+suffix)
                                    path.parent.mkdir(parents=True,exist_ok=True)
                                    path.write_text('fake built artifact '+name+relative)
                        for option in ['-o','-ohi']:
                            if option in argv:
                                path = Path(argv[argv.index(option)+1])
                                path.parent.mkdir(parents=True, exist_ok=True)
                                path.write_text('fake built artifact '+name)
                        if mutate and name == 'build-candidate':
                            implementation.write_text('changed after compiler read\n')
                    elif name == 'fixtures':
                        fixture_dir = Path(argv[-1]);fixture_dir.mkdir()
                        (fixture_dir/'control.emlf').write_text('42\n')
                        (fixture_dir/'index.json').write_text('{"control":"int"}')
                    elif name.startswith('run-'):
                        stdout = ('PASS '+argv[1]+' wall_ns=100 cpu_ps=1000\n').encode()
                        if mutate_object and name == 'run-0-3-control':
                            (self.output/'candidate/objects/Bootstrap/ClassDemand.o').write_text('mutation after timed samples\n')
                    elif name.startswith('controls-'):
                        stdout = kwargs['expected']
                    entry['state'] = 'passed';self.save()
                    return subprocess.CompletedProcess(argv,0,stdout,b'')
            output = root/'output'
            args = ['perf_inference.py','--producer',str(receipt_path),'--baseline-ref','HEAD',
                    '--cycles','1','--out',str(output)]
            if controls:
                args += ['--controls']
            for name in overrides or []:
                args += ['--override',name]
            def invoke(arguments):
                caught = None
                with patch.object(perf,'ROOT',root), patch.object(perf,'SOURCES',sources), \
                     patch.object(perf,'CommandRunner',FakeRunner), patch.object(sys,'argv',arguments), \
                     contextlib.redirect_stdout(io.StringIO()):
                    try:
                        perf.main()
                    except (ValueError,RuntimeError) as error:
                        caught = error
                return caught
            caught = invoke(args)
            if reuse and caught is None:
                old_output = output
                prior_path = old_output/'receipt.json'
                if reuse_change:
                    implementation.write_text('intended candidate edit before warm run\\n')
                if reuse_probe_change:
                    (sources/reuse_probe_change).write_text('changed probe source '+reuse_probe_change)
                if reuse_control_change:
                    test_source.write_text('changed focused planner tests')
                if reuse_tamper:
                    (old_output/'candidate/objects/Bootstrap/ClassDemand.o').write_text('corrupted cache')
                if reuse_incomplete or reuse_flags or reuse_escape or reuse_mismatch:
                    previous = json.loads(prior_path.read_text())
                    if reuse_incomplete:
                        previous['complete'] = False
                    if reuse_flags:
                        previous['flags'] = ['-O0']
                    if reuse_mismatch == 'baseline':
                        previous['baseline_commit'] = 'b'*40
                    elif reuse_mismatch == 'toolchain':
                        previous['toolchain']['ghc']['sha256'] = '0'*64
                    elif reuse_mismatch == 'overrides':
                        previous['overrides'] = ['Bootstrap.Other']
                    if reuse_escape:
                        previous['build_artifacts']['candidate'][str(root/'ghc')] = perf.sha(root/'ghc')
                    prior_path.write_text(json.dumps(previous))
                output = root/'output-warm'
                args[args.index('--out')+1] = str(output)
                args += ['--reuse',str(prior_path)]
                calls.clear()
                caught = invoke(args)
            recorded = json.loads((output/'receipt.json').read_text()) if (output/'receipt.json').exists() else {}
            return caught, calls, recorded

    def test_incomplete_and_o0_reject_before_compiler(self):
        for change in [lambda r:r.update(complete=False),lambda r:r.update(optimization='0')]:
            error,calls,record = self.exercise(change=change)
            self.assertIsInstance(error,ValueError)
            self.assertFalse(any(name in ['build-baseline','build-candidate'] for name in calls))
            self.assertFalse(record.get('complete',False))

    def test_duplicate_and_unknown_override_reject_before_compiler(self):
        for overrides in [['Bootstrap.ClassDemand','Bootstrap.ClassDemand'],['Missing']]:
            error,calls,record = self.exercise(overrides=overrides)
            self.assertIsInstance(error,ValueError)
            self.assertFalse(any(name in ['build-baseline','build-candidate'] for name in calls))
            self.assertFalse(record.get('complete',False))

    def test_pinned_source_mismatch_rejects_before_compiler(self):
        error,calls,record = self.exercise(mismatch=True)
        self.assertIsInstance(error,ValueError)
        self.assertFalse(any(name in ['build-baseline','build-candidate'] for name in calls))
        self.assertFalse(record.get('complete',False))

    def test_candidate_change_never_completes(self):
        error,calls,record = self.exercise(mutate=True)
        self.assertIsInstance(error,ValueError)
        self.assertIn('input changed',str(error))
        self.assertFalse(record.get('complete',False))

    def test_controls_cannot_repin_mutated_candidate_object(self):
        error,calls,record = self.exercise(controls=True,mutate_object=True)
        self.assertIsInstance(error,ValueError)
        self.assertIn('input changed',str(error))
        self.assertFalse(any(name.startswith('controls-') for name in calls))
        self.assertFalse(record.get('complete',False))

    def test_controls_add_new_pins_without_replacing_old(self):
        error,calls,record = self.exercise(controls=True)
        self.assertIsNone(error)
        self.assertIn('controls-baseline',calls)
        self.assertIn('controls-candidate',calls)
        self.assertTrue(record['complete'])

    def test_failed_command_never_completes(self):
        error,calls,record = self.exercise(fail=True)
        self.assertIsInstance(error,RuntimeError)
        self.assertFalse(record.get('complete',False))

    def test_authenticated_unchanged_cache_is_copied(self):
        error,calls,record = self.exercise(controls=True,reuse=True)
        self.assertIsNone(error)
        self.assertTrue(record['complete'])
        for variant in ['baseline','candidate']:
            command = next(c for c in record['commands'] if c['name']=='build-'+variant)
            self.assertTrue(command['candidate_cache_present_before_make'])
        self.assertFalse(record['reuse']['removed_changed_module_artifacts'])

    def test_changed_source_invalidates_only_its_cloned_cache_before_make(self):
        error,calls,record = self.exercise(reuse=True,reuse_change=True)
        self.assertIsNone(error)
        baseline = next(c for c in record['commands'] if c['name']=='build-baseline')
        candidate = next(c for c in record['commands'] if c['name']=='build-candidate')
        self.assertTrue(baseline['candidate_cache_present_before_make'])
        self.assertFalse(candidate['candidate_cache_present_before_make'])
        self.assertTrue(record['complete'])

    def test_changed_probe_and_control_sources_invalidate_cloned_modules(self):
        for source,module in [('Main.hs','Main'),('Controls.hs','PerfControls')]:
            with self.subTest(source=source):
                error,calls,record = self.exercise(controls=True,reuse=True,reuse_probe_change=source)
                self.assertIsNone(error)
                for variant in ['baseline','candidate']:
                    command = next(c for c in record['commands'] if c['name']=='build-'+variant)
                    self.assertFalse(command['cache_before_make'][module])
        error,calls,record = self.exercise(controls=True,reuse=True,reuse_control_change=True)
        self.assertIsNone(error)
        for variant in ['baseline','candidate']:
            command = next(c for c in record['commands'] if c['name']=='build-'+variant)
            self.assertFalse(command['cache_before_make']['MLF/Tests/ClassDemand'])

    def test_corrupt_incomplete_or_flag_changed_cache_rejects_before_make(self):
        for options in [dict(reuse_tamper=True),dict(reuse_incomplete=True),dict(reuse_flags=True),dict(reuse_escape=True)]:
            with self.subTest(options=options):
                error,calls,record = self.exercise(reuse=True,**options)
                self.assertIsInstance(error,ValueError)
                self.assertFalse(any(name in ['build-baseline','build-candidate'] for name in calls))
                self.assertFalse(record.get('complete',False))

    def test_reuse_baseline_toolchain_or_override_mismatch_rejects(self):
        for mismatch in ['baseline','toolchain','overrides']:
            with self.subTest(mismatch=mismatch):
                error,calls,record = self.exercise(reuse=True,reuse_mismatch=mismatch)
                self.assertIsInstance(error,ValueError)
                self.assertFalse(any(name in ['build-baseline','build-candidate'] for name in calls))
                self.assertFalse(record.get('complete',False))

    def test_real_admission_and_hash_logic_with_fake_tools(self):
        error,calls,record = self.exercise()
        self.assertIsNone(error)
        self.assertTrue(record['complete'])
        self.assertTrue(record['all_run_inputs_verified_after'])
        self.assertEqual(record['baseline_commit'],'a'*40)
        self.assertFalse(record['held_objects_linked'])
        for command in record['commands']:
            self.assertFalse(any('/producer/objects/' in argument for argument in command['argv']))
        for variant in ['baseline','candidate']:
            command = next(c for c in record['commands'] if c['name']=='build-'+variant)
            self.assertIn('--make',command['argv'])
            self.assertTrue(any('/'+variant+'/source/' in arg for arg in command['argv']))

if __name__ == '__main__':
    unittest.main()
