#!/usr/bin/env python3
"""Filesystem-only controls for the separate bootstrap driver; no compiler runs."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import subprocess
import os
import sys
import signal
import time

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).with_name('bootstrap_ghc_native.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class GateControls(unittest.TestCase):
    def setUp(self):
        # Port the original gate rejection controls to the strict new schema.
        path = Path(__file__).with_name('test_collect_ghc_native_prerequisites.py')
        module_spec = importlib.util.spec_from_file_location('gate_fixture_controls', path)
        module = importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(module)
        self.fixture = module.PrerequisiteControls()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.gate = self.fixture.gate

    def add_crate(self, name, count):
        crate = 'mlf-' + name + '/0.3.0/library'
        self.gate['results'][crate] = {'module_count': count, 'reused_groups': 0}
        self.gate['commands'].append({'crate': crate, 'status': 'passed', 'resource': {'complete': True}})

    def check(self):
        path = self.fixture.gate_path
        self.fixture.write(path, self.gate)
        return b.authenticate_gate(path, b.sha(path), self.fixture.binding['producer']['sha256'], self.root)

    def test_four_only(self):
        self.check()

    def test_extra_crate_cannot_replace_the_exact_four_library_gate(self):
        self.add_crate('inference', 6)
        with self.assertRaises(ValueError): self.check()

    def test_missing_required(self):
        del self.gate['results']['mlf-frontend/0.3.0/library']
        with self.assertRaises(Exception): self.check()

    def test_wrong_producer(self):
        self.gate['producer_receipt_sha256'] = 'old-producer'
        with self.assertRaises(Exception): self.check()

    def test_failed_extra_command(self):
        self.add_crate('inference', 6)
        self.gate['commands'][-1]['status'] = 'failed'
        with self.assertRaises(Exception): self.check()

    def test_failed_or_running_parent(self):
        for status in ['failed', 'running']:
            self.gate['status'] = status
            with self.assertRaises(Exception): self.check()

    def test_extra_command_not_complete(self):
        self.add_crate('inference', 6)
        self.gate['commands'][-1]['resource']['complete'] = False
        with self.assertRaises(Exception): self.check()

    def test_duplicate_command(self):
        self.gate['commands'][-1] = self.gate['commands'][0]
        with self.assertRaises(Exception): self.check()

    def test_reused_extra_row(self):
        self.add_crate('inference', 6)
        self.gate['results']['mlf-inference/0.3.0/library']['reused_groups'] = 1
        with self.assertRaises(Exception): self.check()

    def test_extra_evidence_drift(self):
        self.add_crate('inference', 6)
        extra = self.root / 'extra'
        extra.write_text('original')
        self.gate['artifacts'][str(extra)] = b.sha(extra)
        extra.write_text('modified')
        with self.assertRaises(Exception): self.check()

    def test_changed_manifest_or_source_rejected(self):
        source = Path(next(iter(self.gate['inventory']['mlf-foundation/0.3.0/library']['modules'].values()))['path'])
        source.write_text('changed source')
        with self.assertRaises(ValueError): self.check()

    def test_same_total_wrong_per_package_counts_rejected(self):
        self.gate['results']['mlf-foundation/0.3.0/library']['module_count'] -= 1
        self.gate['results']['mlf-frontend/0.3.0/library']['module_count'] += 1
        with self.assertRaisesRegex(ValueError, 'query report/result mismatch'): self.check()

    def test_missing_manifest_input_rejected(self):
        self.gate['inputs'].pop(str(self.root / 'libraries/mlf-foundation/mlf-package.json'))
        with self.assertRaises(ValueError): self.check()


class StageControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage = self.root / 'stage'
        self.cache = self.root / 'cache'
        self.pair = self.root / 'pair'
        self.helper = self.file('helper', b'helper')
        self.clang = self.file('clang', b'clang')
        self.file('pair/emlf', b'compiler')
        self.file('pair/mlfpkg', b'manager')
        self.runtime = {str(self.file('runtime.c', b'runtime')): b.sha(self.root / 'runtime.c')}
        self.targets = {t: {'main': t+'.hs'} for t in b.TARGETS}
        self.manifest = {'format': 1, 'name': 'mlf-compiler', 'version': '0.3.0', 'executables': self.targets}
        manifest = self.file('mlf-package.json', json.dumps(self.manifest).encode())
        sources = {}; self.source_values = {}; self.crates = []
        for target in b.TARGETS:
            name = 'Entry.' + target.capitalize()
            source = self.file(target+'.hs', ('-- mlf:syntax shared-haskell-v1\nmodule '+name+' where {}\n').encode())
            sources[source.name] = b.sha(source)
            self.source_values[target] = {name: {'path': str(source), 'sha256': b.sha(source), 'syntax': 'shared-haskell-v1'}}
            self.crates.append({'crate': 'mlf-compiler/0.3.0/target-'+target, 'entry': name, 'modules': [name], 'dependencies': []})
        self.packages = [{'name': 'mlf-compiler', 'version': '0.3.0', 'path': '.', 'manifest': b.sha(manifest), 'sources': sources}]
        self.rows = []
        self.artifacts = {}
        self.jobs = [{'id': 'runtime', 'kind': 'runtime', 'dependencies': []}]
        self.log = self.file('stage/commands/0.log', b'ok')
        self.plan = self.file('stage/invocations/plan.bin', b'plan')
        self.base_tools = {'clang': self.identity(self.clang), 'system': 'Linux', 'machine': 'x86_64',
                           'native_environment': {}, 'gmp': {'flags': ['-lgmp'], 'libraries': {}, 'headers': {}},
                           'runtime': self.runtime, 'runtime-path': str(self.root/'runtime.c')}
        self.gc = {'flags': ['-lgc'], 'libraries': {}, 'headers': {}}
        self.runtime_hash = self.digest(b'runtime object')
        self.artifact(20, 'runtime object', {**self.base_tools, 'gc': self.gc, 'flags': ['-O2','-std=c11']}, {'runtime.o': b'runtime object'})
        for n, target in enumerate(b.TARGETS):
            llvm, obj, native = (target.encode() + suffix for suffix in (b' llvm', b' object', b' native'))
            llvm_hash, obj_hash, native_hash = [self.digest(v) for v in (llvm, obj, native)]
            crate_path = self.cache / f'{30+n*10:064x}'
            self.artifact(30+n*10, 'crate mlf-compiler/0.3.0/target-' + target,
                          {'compiler': self.identity(self.pair/'emlf'), 'manager': self.identity(self.pair/'mlfpkg'),
                           'crate': 'mlf-compiler/0.3.0/target-'+target, 'entry': 'Entry.'+target.capitalize(),
                           'no-prelude': False, 'sources': self.source_values[target], 'dependencies': []},
                          {'unit.mlfci': b'meta', 'unit.mlfco': b'xmlf'})
            self.artifact(31+n*10, 'LLVM emission', {'compiler': self.identity(self.pair/'emlf'),
                          'crate-path': str(crate_path), 'metadata': self.digest(b'meta'), 'object': self.digest(b'xmlf')}, {'program.ll': llvm})
            self.artifact(1+n*3, 'LLVM object', {**self.base_tools, 'llvm': llvm_hash, 'flags': ['-O2','-Wno-override-module','-c']}, {'program.o': obj})
            self.artifact(2+n*3, 'native link', {**self.base_tools, 'gc': self.gc, 'llvm-object': obj_hash, 'runtime-object': self.runtime_hash, 'flags': ['-O2','-Wno-override-module','-lgmp','-lgc','-lm']}, {'program': native})
            self.artifact(3+n*3, 'executable mlf-compiler:' + target,
                          {'target': self.targets[target], 'crate-path': str(crate_path), 'llvm': llvm_hash, 'binary': native_hash,
                           'metadata': self.digest(b'meta'), 'object': self.digest(b'xmlf')},
                          {'program.ll': llvm, 'program': native, 'unit.mlfci': b'meta', 'unit.mlfco': b'xmlf'})
            self.file('stage/bin/' + target, native)
            self.jobs.extend([
                {'id': 'crate-'+target, 'kind': 'target', 'dependencies': [], 'entry': 'Entry.'+target.capitalize(),
                 'modules': [{'name': n, 'source': v['path']} for n,v in self.source_values[target].items()]},
                {'id': 'emit-'+target, 'kind': 'emit', 'crate': 'crate-'+target, 'dependencies': ['crate-'+target]},
                {'id': 'object-'+target, 'kind': 'object', 'emitted': 'emit-'+target, 'dependencies': ['emit-'+target]},
                {'id': 'link-'+target, 'kind': 'link', 'llvm': 'object-'+target, 'runtime': 'runtime', 'dependencies': ['object-'+target,'runtime']},
                {'id': 'assemble-'+target, 'kind': 'assemble', 'crate': 'crate-'+target, 'emitted': 'emit-'+target,
                 'linked': 'link-'+target, 'dependencies': ['crate-'+target,'emit-'+target,'link-'+target], 'selection': {'name': target, 'target': self.targets[target]}}])
        self.file('stage/bin/mlf-build-runner', b'helper')
        self.report = {'complete': True, 'implementation': 'MLF',
                       'toolchain': {**self.base_tools, 'compiler': self.identity(self.pair/'emlf'),
                                     'manager': self.identity(self.pair/'mlfpkg'), 'pkg-config': self.identity(self.clang),
                                     'clang': self.identity(self.clang), 'runtime': self.runtime},
                       'scheduler': [{'helper': self.identity(self.helper), 'plan': str(self.plan),
                                      'plan_digest': b.sha(self.plan)}],
                       'commands': [{'exit_code': 0, 'stdout': str(self.log), 'stderr': str(self.log)}],
                       'builds': self.rows}
        self.report['packages'] = {'format': 1, 'packages': self.packages}
        context = self.file('stage/invocations/context.json', json.dumps({'jobs': self.jobs,
            'tools': self.report['toolchain'], 'initial': self.report['packages'],
            'config': {'cache-dir': str(self.cache), 'build-directory': str(self.stage), 'jobs': '1'},
            'graph': {'packages': [{'path': str(self.root/'mlf-package.json'), 'data': self.manifest, 'modules': []}]}}).encode())
        invocation = b.sha(context)
        outcome = {'protocol_version': 1, 'complete': True, 'invocation_id': invocation,
                   'plan_digest': b.sha(self.plan), 'jobs': 1, 'exit_code': 0,
                   'tasks': [{'id': j['id'], 'state': 'succeeded', 'exit_code': 0} for j in self.jobs]}
        self.file('stage/invocations/runner-result.json', json.dumps(outcome).encode())
        self.report['scheduler'][0].update(invocation_id=invocation, jobs=self.jobs)
        self.report['scheduler_results'] = [outcome]
        for job, row in zip(self.jobs, self.rows):
            directory = self.cache/row['key']; value = b.read(directory/'artifact.json')
            worker_report = {'builds': [row.copy()]}
            self.file('stage/invocations/jobs/'+job['id']+'/build-report.json', json.dumps(worker_report).encode())
            self.file('stage/invocations/jobs/'+job['id']+'/result.json', json.dumps(
                {'complete': True, 'id': job['id'], 'invocation_id': invocation, 'report': worker_report,
                 'result': {**row, 'artifact': str(directory), 'files': value['files']}}).encode())
            row['job_id'] = job['id']
        self.report['native_inputs'] = [self.gc]
        self.report['cache_directory'] = str(self.cache)
        for target in b.TARGETS:
            directory = self.artifacts['executable mlf-compiler:'+target]
            value = b.read(directory/'artifact.json')
            value['inputs']['toolchain'] = self.report['toolchain']
            (directory/'artifact.json').write_text(json.dumps(value))
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def file(self, name, content):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
        return p

    def identity(self, path):
        return {'path': str(path), 'sha256': b.sha(path)}

    def digest(self, value):
        import hashlib
        return hashlib.sha256(value).hexdigest()

    def artifact(self, number, kind, inputs, files):
        key = f'{number:064x}'
        row = {'key': key, 'kind': kind, 'cached': False}
        self.rows.append(row)
        hashes = {}
        for name, data in files.items():
            p = self.file('cache/' + key + '/' + name, data)
            hashes[name] = b.sha(p)
        self.file('cache/' + key + '/artifact.json', json.dumps(
            {'key': key, 'inputs': inputs, 'files': hashes}).encode())
        self.artifacts[kind] = self.cache / key

    def save(self):
        self.file('stage/build-report.json', json.dumps(self.report).encode())

    def verify(self):
        return b.verify_stage(self.stage, self.cache, self.pair, self.helper, self.clang, self.runtime, self.packages, self.targets, self.clang, self.crates, self.root)

    def test_valid_mock_stage_and_fixedpoint(self):
        result = self.verify()
        self.assertEqual(set(b.compare_stages(result, result)), set(b.TARGETS))

    def test_cached_executable_rejected(self):
        self.rows[-1]['cached'] = True
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_native_object_required(self):
        directory = self.artifacts['LLVM object']
        (directory/'program.o').unlink()
        with self.assertRaises(ValueError): self.verify()

    def test_wrong_helper_rejected(self):
        self.report['scheduler'][0]['helper']['sha256'] = '0'*64
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_wrong_runtime_rejected(self):
        self.report['toolchain']['runtime'] = {}
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_failed_command_rejected(self):
        self.report['commands'][0]['exit_code'] = 1
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_changed_installed_binary_rejected(self):
        self.file('stage/bin/emlf', b'changed')
        with self.assertRaises(ValueError): self.verify()

    def test_duplicate_target_rejected(self):
        self.rows.append(self.rows[-1].copy())
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_stamp_escape_rejected(self):
        directory = self.artifacts['LLVM object']
        value = b.read(directory/'artifact.json')
        value['files']['../outside'] = '0'*64
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_fixedpoint_difference_is_not_normalized(self):
        a = self.verify(); other = json.loads(json.dumps(a))
        other['outputs']['mlfpkg']['object_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'fixed point differs'): b.compare_stages(a, other)

    def test_changed_source_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): b.verified(self.helper, '0'*64)

    def test_symlink_artifact_rejected(self):
        path = self.stage/'bin/emlf'
        path.unlink(); path.symlink_to(self.pair/'emlf')
        with self.assertRaises(ValueError): self.verify()

    def test_missing_scheduler_outcomes_rejected(self):
        self.report['scheduler_results'] = []
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_worker_result_tampering_rejected(self):
        p = self.stage/'invocations/jobs/assemble-mlfpkg/result.json'
        value = b.read(p); value['invocation_id'] = '0'*64
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_runtime_object_link_required(self):
        directory = self.artifacts['native link']
        value = b.read(directory/'artifact.json')
        value['inputs']['runtime-object'] = '0'*64
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_wrong_native_flags_rejected(self):
        directory = self.artifacts['LLVM object']
        value = b.read(directory/'artifact.json'); value['inputs']['flags'] = ['-O0']
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_genuine_published_stdout_relocation(self):
        directory = self.artifacts['executable mlf-compiler:mlfpkg']
        old = self.cache/(directory.name+'.work-Ab12Cd34')/'program.ll'
        self.report['commands'][0]['stdout'] = str(old)
        self.save()
        result = self.verify()
        self.assertEqual(result['relocated_command_outputs'][str(old)]['published'], str(directory/'program.ll'))

    def test_final_input_digest_tamper_rejected(self):
        directory = self.artifacts['executable mlf-compiler:mlfpkg']
        value = b.read(directory/'artifact.json'); value['inputs']['llvm'] = '0'*64
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_package_snapshot_mismatch_rejected(self):
        self.report['packages'] = [{}]; self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_substitute_unrelated_valid_worker_artifact_rejected(self):
        p = self.stage/'invocations/jobs/assemble-mlfpkg/result.json'
        value = b.read(p)
        runtime = b.read(self.stage/'invocations/jobs/runtime/result.json')
        value['result'] = runtime['result']
        p.write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_missing_crate_emission_chain_rejected(self):
        self.report['scheduler'][0]['jobs'] = [j for j in self.jobs if j['kind'] not in ('target', 'emit')]
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_reused_intermediate_actions_rejected(self):
        for row in self.rows:
            if row['kind'] in ('runtime object', 'LLVM object', 'native link'):
                row['cached'] = True
        self.save()
        with self.assertRaises(ValueError): self.verify()

    def test_equal_bytes_with_different_native_flags_rejected(self):
        first = self.verify(); other = json.loads(json.dumps(first))
        other['native_input_signature']['action_flags'] = ['changed flags']
        with self.assertRaisesRegex(ValueError, 'native inputs/flags'): b.compare_stages(first, other)

    def test_wrong_crate_compiler_rejected(self):
        directory = self.artifacts['crate mlf-compiler/0.3.0/target-mlfpkg']
        value = b.read(directory/'artifact.json'); value['inputs']['compiler'] = {'path': '/wrong', 'sha256': '0'*64}
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'crate producer'): self.verify()

    def test_escaped_crate_source_rejected(self):
        directory = self.artifacts['crate mlf-compiler/0.3.0/target-mlfpkg']
        value = b.read(directory/'artifact.json')
        value['inputs']['sources']['Entry.Mlfpkg']['path'] = '/outside/unreviewed.hs'
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaises(ValueError): self.verify()

    def test_missing_crate_sources_rejected(self):
        directory = self.artifacts['crate mlf-compiler/0.3.0/target-mlfpkg']
        value = b.read(directory/'artifact.json'); value['inputs']['sources'] = {}
        (directory/'artifact.json').write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'module inventory'): self.verify()

    def test_stage_command_explicit_isolation(self):
        argv = b.stage_command(self.root, self.pair, self.stage, self.cache, self.clang, self.root/'gc', 30, self.clang)
        self.assertIn('--locked', argv); self.assertIn('--offline', argv)
        self.assertEqual(argv[argv.index('--cache-dir')+1], str(self.cache))
        self.assertEqual(argv[-4:], ['--target','emlf','--target','mlfpkg'])


class MainControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.git = Path('/usr/bin/git').resolve()
        self.env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
        subprocess.run([self.git, 'init', '-q', self.root], check=True, env=self.env)
        subprocess.run([self.git, '-C', self.root, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid',
                        'commit', '--allow-empty', '-qm', 'checkpoint'], check=True, env=self.env)
        self.head = subprocess.check_output([self.git, '-C', self.root, 'rev-parse', 'HEAD'], text=True, env=self.env).strip()

    def tearDown(self): self.temp.cleanup()

    def test_clean_exact_checkpoint(self):
        self.assertFalse(b.source_checkpoint(self.root, self.git, self.env, self.head, True)['dirty'])

    def test_wrong_or_dirty_checkpoint_rejected(self):
        with self.assertRaises(ValueError): b.source_checkpoint(self.root, self.git, self.env, '0'*40, True)
        (self.root/'unreviewed').write_text('x')
        with self.assertRaises(ValueError): b.source_checkpoint(self.root, self.git, self.env, self.head, True)

    def test_ambient_git_directory_cannot_redirect_checkpoint(self):
        other = self.root/'other'; other.mkdir()
        subprocess.run([self.git, 'init', '-q', other], check=True, env=self.env)
        result = b.source_checkpoint(self.root, self.git, {**self.env, 'GIT_DIR': str(other/'.git'),
                                     'GIT_WORK_TREE': str(other)}, None, False)
        self.assertEqual(result['head'], self.head)

    def test_execute_missing_release_checkpoint_stops_before_auth(self):
        args = ['driver']
        for option in ['producer-receipt','frontend-receipt','plans-dir','output','clang','gc-prefix',
                       'producer-sha256','frontend-sha256','plans-sha256']:
            args += ['--'+option, str(self.root/'unused')]
        args += ['--execute']
        with mock.patch('sys.argv', args), mock.patch.object(b, 'authenticate_producer') as authenticate:
            with self.assertRaises(ValueError): b.main()
            authenticate.assert_not_called()
        self.assertFalse((self.root/'unused').exists())

    def test_failure_cleanup_never_leaves_public_pointers(self):
        for name in ('compiler.path','manager.path'): (self.root/name).write_text('partial')
        b.clear_pointers(self.root)
        self.assertFalse((self.root/'compiler.path').exists())
        self.assertFalse((self.root/'manager.path').exists())

    def test_second_pointer_publication_failure_cleans_both(self):
        original = Path.replace
        def replace(path, target):
            if Path(target).name == 'manager.path': raise OSError('injected second publication failure')
            return original(path, target)
        with mock.patch.object(Path, 'replace', replace):
            with self.assertRaises(OSError): b.publish_pointers(self.root, self.root/'emlf', self.root/'mlfpkg')
        for name in ('compiler.path','manager.path','compiler.path.pending','manager.path.pending'):
            self.assertFalse((self.root/name).exists())

    def test_sigterm_reaps_watchdog_sleeping_descendant(self):
        pidfile = self.root/'child.pid'
        bounded = self.root/'bounded'
        driver = Path(b.__file__)
        watchdog = driver.with_name('resource_watchdog.py')
        argv = [sys.executable, str(watchdog), '--seconds', '60', '--address-space-mib', '256',
                '--rss-mib', '512', '--disk-free-mib', '768', str(bounded),
                '/bin/sh', '-c', 'sleep 60 & echo $! > '+str(pidfile)+'; wait']
        code = ("import importlib.util,signal,sys; "
                "s=importlib.util.spec_from_file_location('b',sys.argv[1]);b=importlib.util.module_from_spec(s);s.loader.exec_module(b); "
                "signal.signal(signal.SIGTERM,b.interrupted); "
                "b.managed_run(__import__('json').loads(sys.argv[2]),sys.argv[3],dict(__import__('os').environ))")
        with (self.root/'cancel.log').open('w') as log:
            proc = subprocess.Popen([sys.executable, '-c', code, str(driver), json.dumps(argv), str(self.root)],
                                    stdout=log, stderr=log, start_new_session=True)
            try:
                deadline = time.monotonic()+10
                while not pidfile.exists() and proc.poll() is None and time.monotonic()<deadline: time.sleep(.05)
                self.assertTrue(pidfile.exists())
                child = int(pidfile.read_text())
                proc.send_signal(signal.SIGTERM)
                self.assertNotEqual(proc.wait(timeout=20), 0)
                status = Path('/proc')/str(child)/'stat'
                self.assertTrue(not status.exists() or status.read_text().rsplit(') ',1)[1].startswith('Z'))
                receipt = b.read(bounded/'bounded-receipt.json')
                self.assertFalse(receipt['complete'])
                self.assertTrue(receipt['teardown']['drained'])
                self.assertEqual(receipt['teardown']['remaining'], [])
                self.assertFalse((self.root/'compiler.path').exists())
                self.assertFalse((self.root/'manager.path').exists())
            finally:
                if proc.poll() is None: proc.kill(); proc.wait()

    def test_selected_linker_and_crt_bytes_are_pinned(self):
        tool = self.root/'ld'; tool.write_bytes(b'linker')
        crt = self.root/'crt1.o'; crt.write_bytes(b'crt')
        library = self.root/'libx.a'; library.write_bytes(b'!<arch>')
        inputs = {}
        b.pin_clang_trace('"'+str(tool)+'" "'+str(crt)+'" "-L'+str(self.root)+'" "-lx"',
                          lambda path: inputs.update({str(path.resolve()): b.sha(path)}))
        self.assertIn(str(crt), inputs)
        self.assertIn(str(tool), inputs)
        tool.write_bytes(b'changed linker')
        with self.assertRaises(ValueError): b.verified(tool, inputs[str(tool)])
        crt.write_bytes(b'changed crt')
        with self.assertRaises(ValueError): b.verified(crt, inputs[str(crt)])


class ResumptionControls(unittest.TestCase):
    """Mock orchestration only; every alleged native output here is test data."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / 'source'; self.source.mkdir()
        self.driver = self.base / 'driver'; self.driver.mkdir()
        self.out = self.base / 'run'
        self.plans = self.base / 'plans'; self.plans.mkdir()
        self.executed = []
        self.fail_label = None
        self.file('source/mlf-package.json', json.dumps({'executables': {'emlf': {}, 'mlfpkg': {}}}))
        self.file('source/runtime/mlf_runtime.c', 'runtime')
        self.file('source/runtime/mlf_build_runner.c', 'runner')
        self.file('producer/receipt.json', '{}')
        self.file('producer/bin/emlf', 'GHC compiler')
        self.file('producer/bin/mlfpkg', 'GHC manager')
        self.file('gate.json', '{}')
        self.file('plans/receipt.json', '{}')
        self.file('plans/root-plan.json', json.dumps({'packages': [], 'crates': []}))
        for name in ('clang', 'pkg-config', 'nice', 'ldd', 'ld'):
            self.file('tools/' + name, name)
        self.file('gc/lib/libgc.a', 'gc')
        self.file('gmp/libgmp.so', 'gmp')
        self.file('gc/include/gc.h', 'header')
        for name in ('test_direct.py', 'resource_watchdog.py', 'collect_ghc_native_prerequisites.py'):
            self.file('driver/tools/shared/' + name, name)
        self.patches = [
            mock.patch.object(b, 'ROOT', self.driver),
            mock.patch.object(b, 'source_checkpoint', side_effect=lambda root, git, env, expected, active:
                              {'root': str(root), 'head': expected, 'expected': expected, 'dirty': False}),
            mock.patch.object(b, 'authenticate_producer', return_value={'complete': True}),
            mock.patch.object(b, 'producer_authentication_inputs', return_value={}),
            mock.patch.object(b, 'verify_prerequisites', side_effect=lambda **kwargs:
                              {'inputs': {str(self.plans / 'receipt.json'): b.sha(self.plans / 'receipt.json')}}),
            mock.patch.object(b.shutil, 'which', side_effect=lambda name: str(self.base / 'tools' / name)),
            mock.patch.object(b, 'managed_run', side_effect=self.run_mock),
            mock.patch.object(b, 'verify_stage', side_effect=self.stage_mock)]
        for patch in self.patches:
            patch.start(); self.addCleanup(patch.stop)

    def file(self, name, value):
        path = self.base / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value); return path

    def argv(self, stop='runner', resume=None):
        result = ['driver', '--source-root', str(self.source), '--checkpoint', 'a'*40,
                  '--driver-checkpoint', 'b'*40, '--release-note', 'mock control, never native evidence',
                  '--execute', '--stop-after', stop, '--window-seconds', '30', '--seconds', '15',
                  '--max-output-mib', '8', '--workspace-root', str(self.base), '--output', str(self.out)]
        for option, name in [('producer-receipt', 'producer/receipt.json'), ('frontend-receipt', 'gate.json')]:
            result += ['--' + option, str(self.base / name)]
        for option, name in [('producer-sha256', 'producer/receipt.json'), ('frontend-sha256', 'gate.json'), ('plans-sha256', 'plans/receipt.json')]:
            result += ['--' + option, b.sha(self.base / name)]
        result += ['--plans-dir', str(self.plans), '--clang', str(self.base / 'tools/clang'), '--gc-prefix', str(self.base / 'gc')]
        if resume is not None: result += ['--resume-sha256', resume]
        return result

    def invoke(self, stop='runner', resume=None, extra=()):
        with mock.patch('sys.argv', self.argv(stop, resume) + list(extra)):
            b.main()
        return b.read(self.out / 'receipt.json')

    def run_mock(self, wrapper, cwd, env, teardown=None):
        if teardown is not None:
            teardown.update(drained=True, remaining=[], mock=True)
        self.assertEqual(cwd, self.source)
        self.assertEqual(env['HOME'], str(self.out / 'home'))
        self.assertEqual(env['TMPDIR'], str(self.out / 'tmp'))
        i = wrapper.index(str(self.base / 'tools/nice')); directory = Path(wrapper[i-1]); command = wrapper[i+3:]
        label = directory.name; self.executed.append(label)
        self.assertEqual(wrapper[wrapper.index('--output-root')+1], str(self.out))
        self.assertEqual(wrapper[wrapper.index('--workspace-limit-mib')+1], '15872')
        self.assertLessEqual(int(wrapper[wrapper.index('--seconds')+1]), 30)
        directory.mkdir(parents=True)
        text = ''
        if label == 'gmp-flags': text = '-lgmp\n'
        if label == 'gmp-libdir': text = str(self.base / 'gmp') + '\n'
        if label == 'clang-link-selection': text = '"' + str(self.base / 'tools/ld') + '"\n'
        if label in ('runner-dependencies', 'runtime-dependencies'):
            Path(command[command.index('-MF')+1]).write_text('probe: ' + command[-1] + '\n')
        if label == 'build-runner': Path(command[-1]).write_text('mock runner')
        if label == 'runner-protocol': text = '1\n'
        if label.startswith('stage-'):
            stage = Path(command[command.index('--build-dir')+1]); (stage / 'bin').mkdir(parents=True)
            Path(command[command.index('--cache-dir')+1]).mkdir()
            for target in b.TARGETS: (stage / 'bin' / target).write_text('mock native ' + target)
            (stage / 'bin/mlf-build-runner').write_text('mock runner')
        if label.endswith('-identity'): text = 'MLF/shared-haskell-v1 native-MLF\n'
        (directory / 'build.log').write_text(text)
        failed = label == self.fail_label
        (directory / 'bounded-receipt.json').write_text(json.dumps({
            'complete': not failed, 'exit_code': 1 if failed else 0,
            'reason': 'injected timeout' if failed else None, 'command': wrapper[i:], 'final_owned_descendants': []}))
        return 1 if failed else 0

    def stage_mock(self, stage, *args):
        paths = list((stage / 'bin').iterdir())
        return {'report_sha256': '0'*64,
                'outputs': {t: {kind: ('1' if t == 'emlf' else '2')*64 for kind in ('llvm_sha256', 'object_sha256', 'binary_sha256')} for t in b.TARGETS},
                'evidence': {str(p): b.sha(p) for p in paths},
                'native_input_signature': {'mock': True}, 'dependency_path_bindings': {}}

    def test_runner_then_a_then_b_without_replay_or_early_pointers(self):
        first = self.invoke()
        self.assertEqual(first['phase'], 'runner-preflight-complete')
        self.assertFalse(first['complete']); self.assertFalse(first['fixed_point_qualified'])
        initial_calls = list(self.executed)
        old_checkpoint = Path(first['boundary_checkpoint']['path']).read_bytes()
        second = self.invoke('A', b.sha(self.out / 'receipt.json'))
        self.assertEqual(second['phase'], 'native-A-complete')
        self.assertFalse(second['fixed_point_qualified'])
        self.assertFalse((self.out / 'compiler.path').exists())
        self.assertEqual(self.executed[len(initial_calls):], ['stage-A', 'A-emlf-identity', 'A-mlfpkg-identity'])
        third = self.invoke('B', b.sha(self.out / 'receipt.json'))
        self.assertTrue(third['fixed_point_qualified']); self.assertTrue(third['complete'])
        self.assertEqual(set(third['comparisons']), set(b.TARGETS))
        self.assertEqual((self.out / 'compiler.path').read_text().strip(), str(self.out / 'stage-B/bin/emlf'))
        self.assertEqual(Path(first['boundary_checkpoint']['path']).read_bytes(), old_checkpoint)
        self.assertEqual(self.executed.count('build-runner'), 1)
        self.assertEqual(self.executed.count('stage-A'), 1)
        self.assertEqual(self.executed.count('stage-B'), 1)

    def test_bad_resume_digest_does_not_change_original_receipt(self):
        self.invoke(); before = (self.out / 'receipt.json').read_bytes(); calls = list(self.executed)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'): self.invoke('A', '0'*64)
        self.assertEqual((self.out / 'receipt.json').read_bytes(), before)
        self.assertEqual(self.executed, calls)

    def test_changed_source_driver_or_budget_contract_rejected_before_commands(self):
        self.invoke(); before = (self.out / 'receipt.json').read_bytes(); digest = b.sha(self.out / 'receipt.json')
        for extra in [('--checkpoint', 'c'*40), ('--driver-checkpoint', 'd'*40), ('--seconds', '42')]:
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'contract differs'):
                self.invoke('A', digest, extra)
            self.assertEqual((self.out / 'receipt.json').read_bytes(), before)

    def test_concurrent_or_abandoned_lock_never_overwrites_receipt(self):
        self.invoke(); before = (self.out / 'receipt.json').read_bytes()
        (self.out / 'driver.lock').write_text('another owner')
        with self.assertRaises(FileExistsError): self.invoke('A', b.sha(self.out / 'receipt.json'))
        self.assertEqual((self.out / 'receipt.json').read_bytes(), before)
        self.assertEqual((self.out / 'driver.lock').read_text(), 'another owner')

    def test_changed_completed_a_artifact_blocks_b(self):
        self.invoke('A'); digest = b.sha(self.out / 'receipt.json'); calls = list(self.executed)
        (self.out / 'stage-A/bin/mlfpkg').write_text('tampered manager')
        with self.assertRaisesRegex(ValueError, 'inventory differs|hash mismatch'): self.invoke('B', digest)
        self.assertEqual(self.executed, calls)
        self.assertFalse((self.out / 'compiler.path').exists())

    def test_all_future_sidecar_and_directory_aliases_rejected_before_writes(self):
        self.invoke(); digest = b.sha(self.out / 'receipt.json')
        before = (self.out / 'receipt.json').read_bytes()
        external = self.file('external-prior-evidence', 'must remain unchanged')
        for name in ['receipt.json.tmp', 'manager.path.pending', 'compiler.path.pending',
                     'commands/future', 'checkpoints/future.json', 'tmp/future', 'home/future', 'tools/future']:
            for hardlink in [False, True]:
                with self.subTest(name=name, hardlink=hardlink):
                    path = self.out / name
                    if hardlink: os.link(external, path)
                    else: path.symlink_to(external)
                    calls = list(self.executed)
                    with self.assertRaisesRegex(ValueError, 'output symlink|hardlink'):
                        self.invoke('A', digest)
                    self.assertEqual((self.out / 'receipt.json').read_bytes(), before)
                    self.assertEqual(external.read_text(), 'must remain unchanged')
                    self.assertEqual(self.executed, calls)
                    path.unlink()
        external_dir = self.base / 'external-dir'; external_dir.mkdir()
        (self.out / 'future-directory').symlink_to(external_dir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'output symlink'): self.invoke('A', digest)
        self.assertEqual(list(external_dir.iterdir()), [])

    def test_unreferenced_new_regular_file_rejects_resume(self):
        self.invoke(); digest = b.sha(self.out / 'receipt.json')
        (self.out / 'unreviewed-new-file').write_text('new')
        with self.assertRaisesRegex(ValueError, 'output inventory differs'):
            self.invoke('A', digest)

    def test_pinned_absolute_nice_is_actual_executed_tool(self):
        result = self.invoke()
        nice = str(self.base/'tools/nice')
        self.assertEqual(result['contract']['nice'], nice)
        for command in result['commands']:
            bounded = b.read(command['bounded_receipt'])
            self.assertEqual(bounded['command'][0], nice)
            self.assertIn(nice, command['watchdog_argv'])
            self.assertEqual(command['watchdog_argv'][0], str(Path(sys.executable).resolve()))
            self.assertEqual(result['contract']['python'], command['watchdog_argv'][0])

    def test_parent_rss_budget_is_enforced_before_authentication(self):
        with self.assertRaisesRegex(ValueError, 'driver process-tree RSS limit'):
            self.invoke(extra=('--rss-mib', '1'))
        receipt = b.read(self.out/'receipt.json')
        self.assertFalse(receipt['complete']); self.assertFalse(receipt['fixed_point_qualified'])
        self.assertEqual(self.executed, [])
        self.assertIn('RSS limit', receipt['driver_resource']['failure'])

    def test_signal_handlers_are_restored_after_success(self):
        before = {name: signal.getsignal(name) for name in (signal.SIGTERM, signal.SIGALRM)}
        self.invoke()
        self.assertEqual({name: signal.getsignal(name) for name in before}, before)

    def test_failed_receipt_survives_deferred_signals(self):
        before = {name: signal.getsignal(name) for name in (signal.SIGTERM, signal.SIGALRM)}
        original_boundary = b.retain_boundary
        original_write = b.write_new_json
        budgets = []
        original_init = b.DriverBudget.__init__
        def initialize(budget, *args):
            original_init(budget, *args)
            budgets.append(budget)
        def oversize(output, receipt, phase):
            original_boundary(output, receipt, phase)
            (output / 'injected-final-growth').write_bytes(b'x' * (2 * 1024**2))
        def interrupt_failed_write(path, value):
            if path.name == 'receipt.json.tmp' and value.get('status') == 'failed':
                self.assertTrue(budgets[0].stop_event.is_set())
                self.assertFalse(budgets[0].thread.is_alive())
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
                with path.open('x') as stream:
                    os.kill(os.getpid(), signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGALRM)
                    stream.write(json.dumps(value) + '\n')
                return
            original_write(path, value)
        with mock.patch.object(b.DriverBudget, '__init__', initialize), \
                mock.patch.object(b, 'retain_boundary', side_effect=oversize), \
                mock.patch.object(b, 'write_new_json', side_effect=interrupt_failed_write):
            with self.assertRaises((ValueError, RuntimeError, InterruptedError)):
                self.invoke(extra=('--max-output-mib', '1'))
        receipt = b.read(self.out / 'receipt.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(receipt['complete']); self.assertFalse(receipt['fixed_point_qualified'])
        self.assertFalse((self.out / 'compiler.path').exists())
        self.assertFalse((self.out / 'manager.path').exists())
        self.assertEqual({name: signal.getsignal(name) for name in before}, before)

    def reject_late_monitor_failure(self, final_stage):
        if final_stage == 'B':
            self.invoke('A')
        resume = b.sha(self.out / 'receipt.json') if final_stage == 'B' else None
        original_stop = b.DriverBudget.stop_monitor
        injected = []
        def late_failure(budget):
            original_stop(budget)
            if not injected:
                injected.append(True)
                budget.failure = 'controlled late monitor failure at stop'
        with mock.patch.object(b.DriverBudget, 'stop_monitor', late_failure):
            with self.assertRaisesRegex(RuntimeError, 'controlled late monitor failure'):
                self.invoke(final_stage, resume)
        receipt = b.read(self.out / 'receipt.json')
        self.assertTrue(injected)
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(receipt['complete']); self.assertFalse(receipt['fixed_point_qualified'])
        self.assertFalse(receipt['boundary_complete'])
        self.assertFalse((self.out / 'compiler.path').exists())
        self.assertFalse((self.out / 'manager.path').exists())

    def test_late_monitor_failure_cannot_escape_runner_boundary(self):
        self.reject_late_monitor_failure('runner')

    def test_late_monitor_failure_revokes_qualified_pointers(self):
        self.reject_late_monitor_failure('B')

    def reject_post_stop_save_growth(self, final_stage):
        if final_stage == 'B':
            self.invoke('A')
        resume = b.sha(self.out / 'receipt.json') if final_stage == 'B' else None
        budgets = []
        original_init = b.DriverBudget.__init__
        original_write = b.write_new_json
        injected = []
        def initialize(budget, *args):
            original_init(budget, *args)
            budgets.append(budget)
        def grow_after_last_save(path, value):
            original_write(path, value)
            if (path.name == 'receipt.json.tmp' and budgets and budgets[0].stop_event.is_set()
                    and value.get('status') in ('paused', 'passed') and not injected):
                injected.append(True)
                (self.out / 'extra-post-stop-save-bytes').write_bytes(b'x' * (1024**2 + 1))
        with mock.patch.object(b.DriverBudget, '__init__', initialize), \
                mock.patch.object(b, 'write_new_json', side_effect=grow_after_last_save):
            with self.assertRaisesRegex(ValueError, 'driver cumulative output limit'):
                self.invoke(final_stage, resume, ('--max-output-mib', '1'))
        self.assertTrue(injected, 'must inject after the monitor has stopped')
        receipt = b.read(self.out / 'receipt.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(receipt['complete']); self.assertFalse(receipt['fixed_point_qualified'])
        self.assertFalse((self.out / 'compiler.path').exists())
        self.assertFalse((self.out / 'manager.path').exists())
        self.assertIn('output limit', receipt['driver_resource']['failure'])

    def test_final_post_stop_runner_save_growth_is_checked(self):
        self.reject_post_stop_save_growth('runner')

    def test_final_post_stop_qualified_save_growth_revokes_pointers(self):
        self.reject_post_stop_save_growth('B')

    def test_driver_address_space_soft_limit_is_restored(self):
        import resource
        before = resource.getrlimit(resource.RLIMIT_AS)
        result = self.invoke(extra=('--address-space-mib', '256'))
        self.assertLessEqual(result['driver_resource']['driver_address_space_bytes'], 256*1024**2)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_AS), before)

    def test_final_pointer_metadata_growth_fails_and_removes_both_pointers(self):
        self.invoke('A')
        original = b.publish_pointers
        def oversized(output, compiler, manager):
            original(output, compiler, manager)
            (output/'unexpected-final-metadata').write_bytes(b'x'*(2*1024*1024))
        # Disable only the background timer so this exercises the explicit
        # post-publication guard, without a race against the same guard thread.
        with mock.patch.object(b.DriverBudget, 'start', lambda guard: guard.check()), \
             mock.patch.object(b, 'publish_pointers', side_effect=oversized), \
             self.assertRaisesRegex(ValueError, 'driver cumulative output limit'):
            self.invoke('B', b.sha(self.out/'receipt.json'), ('--max-output-mib', '1'))
        receipt = b.read(self.out/'receipt.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(receipt['complete']); self.assertFalse(receipt['fixed_point_qualified'])
        self.assertFalse((self.out/'compiler.path').exists())
        self.assertFalse((self.out/'manager.path').exists())
        self.assertIn('cumulative output limit', receipt['driver_resource']['failure'])

    def test_boundary_checkpoint_growth_is_covered_after_last_command(self):
        original = b.retain_boundary
        def oversized(output, receipt, phase):
            original(output, receipt, phase)
            (output/'final-boundary-metadata').write_bytes(b'x'*(2*1024*1024))
        with mock.patch.object(b.DriverBudget, 'start', lambda guard: guard.check()), \
             mock.patch.object(b, 'retain_boundary', side_effect=oversized), \
             self.assertRaisesRegex(ValueError, 'driver cumulative output limit'):
            self.invoke(extra=('--max-output-mib', '1'))
        receipt = b.read(self.out/'receipt.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(receipt['boundary_complete'])
        self.assertFalse(receipt['fixed_point_qualified'])

    def test_prior_undrained_driver_command_cannot_resume(self):
        receipt = self.invoke()
        receipt['commands'][0]['driver_teardown']['drained'] = False
        with self.assertRaisesRegex(ValueError, 'prior bounded command'):
            b.authenticate_commands(receipt, self.out)

    def test_prior_command_log_tampering_rejected(self):
        receipt = self.invoke(); digest = b.sha(self.out / 'receipt.json')
        log = self.out / 'commands' / receipt['commands'][0]['label'] / 'build.log'
        log.write_text('changed')
        with self.assertRaisesRegex(ValueError, 'inventory differs|hash mismatch'): self.invoke('A', digest)

    def test_helper_tampering_rejected(self):
        self.invoke(); digest = b.sha(self.out / 'receipt.json')
        (self.out / 'tools/mlf-build-runner').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'inventory differs|hash mismatch'): self.invoke('A', digest)

    def test_preseeded_next_cache_rejected(self):
        self.invoke(); digest = b.sha(self.out / 'receipt.json')
        (self.out / 'cache-A').mkdir()
        with self.assertRaisesRegex(ValueError, 'inventory differs|preseeded'): self.invoke('A', digest)

    def test_failed_a_is_retained_not_qualified_or_resumable(self):
        self.invoke(); self.fail_label = 'stage-A'
        with self.assertRaisesRegex(ValueError, 'bounded command failed'):
            self.invoke('A', b.sha(self.out / 'receipt.json'))
        receipt = b.read(self.out / 'receipt.json'); before = (self.out / 'receipt.json').read_bytes()
        self.assertEqual(receipt['status'], 'failed'); self.assertFalse(receipt['fixed_point_qualified'])
        self.assertTrue((self.out / 'stage-A/bin/emlf').exists())
        with self.assertRaisesRegex(ValueError, 'inventory differs|natural boundary'):
            self.invoke('A', b.sha(self.out / 'receipt.json'))
        self.assertEqual((self.out / 'receipt.json').read_bytes(), before)
        self.assertEqual(self.executed.count('stage-A'), 1)

    def test_a_requires_explicit_b_resumption(self):
        self.invoke('A'); digest = b.sha(self.out / 'receipt.json'); before = (self.out / 'receipt.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'select B'): self.invoke('A', digest)
        self.assertEqual((self.out / 'receipt.json').read_bytes(), before)

    def test_ambient_loader_and_home_are_never_inherited(self):
        with mock.patch.dict(os.environ, {'LD_PRELOAD': '/unreviewed.so', 'LD_LIBRARY_PATH': '/unreviewed', 'HOME': '/bad', 'TMPDIR': '/bad'}):
            env = b.isolated_environment(self.out, self.base/'tools/clang', self.base/'tools/pkg-config', self.base/'gc', [])
        self.assertNotIn('LD_PRELOAD', env); self.assertNotIn('LD_LIBRARY_PATH', env)
        self.assertEqual(env['HOME'], str(self.out/'home'))

    def test_explicit_loader_inventory_detects_added_changed_and_retargeted_files(self):
        lib = self.file('loader/libactual.so', 'original')
        link = self.base/'loader/libalias.so'; link.symlink_to(lib)
        before = b.loader_inventory([lib.parent])
        self.assertEqual(before['bindings'][str(link)], str(lib))
        lib.write_text('changed'); self.assertNotEqual(b.loader_inventory([lib.parent]), before)
        lib.write_text('original'); self.file('loader/injected.so', 'injected')
        self.assertNotEqual(b.loader_inventory([lib.parent]), before)

    def test_native_b_mismatch_never_publishes(self):
        self.invoke('A')
        original = self.stage_mock
        def changed(stage, *args):
            result = original(stage, *args)
            if stage.name == 'stage-B': result['outputs']['mlfpkg']['object_sha256'] = 'e'*64
            return result
        with mock.patch.object(b, 'verify_stage', side_effect=changed), self.assertRaisesRegex(ValueError, 'fixed point differs: mlfpkg'):
            self.invoke('B', b.sha(self.out/'receipt.json'))
        self.assertFalse((self.out/'compiler.path').exists())
        self.assertFalse(b.read(self.out/'receipt.json')['fixed_point_qualified'])


class ProducerLocationControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.helpers = self.root / 'tools/shared'; self.helpers.mkdir(parents=True)
        for name in b.PRODUCER_AUTH_HELPERS:
            (self.helpers / name).write_text('# pinned test helper\n')
        (self.helpers / 'test_direct.py').write_text('''from pathlib import Path
import types

def authenticate_build(receipt, pair, root):
    helper = Path(__file__).with_name('verify_builtin_prelude.py')
    module = types.ModuleType('verify_builtin_prelude')
    module.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), module.__dict__)
    return {'direct_path': __file__, 'verification_driver': module.__file__, 'value': module.value}
''')
        (self.helpers / 'verify_builtin_prelude.py').write_text('value = "original source helper"\n')

    def test_original_helper_paths_and_no_named_module_reuse(self):
        import types
        poison = types.ModuleType('verify_builtin_prelude'); poison.value = 'wrong checkout'
        with mock.patch.dict(sys.modules, {'verify_builtin_prelude': poison, 'test_direct': poison}):
            result = b.authenticate_producer(self.root/'receipt', self.root/'bin', self.root, b.producer_authentication_inputs(self.root))
            self.assertIs(sys.modules['verify_builtin_prelude'], poison)
        self.assertEqual(result['verification_driver'], str(self.helpers/'verify_builtin_prelude.py'))
        self.assertEqual(result['direct_path'], str(self.helpers/'test_direct.py'))
        self.assertEqual(result['value'], 'original source helper')

    def test_pinned_source_helper_tampering_rejected(self):
        inputs = b.producer_authentication_inputs(self.root)
        (self.helpers/'verify_builtin_prelude.py').write_text('value = "changed"\n')
        with self.assertRaisesRegex(ValueError, 'verifier closure changed'):
            b.authenticate_producer(self.root/'receipt', self.root/'bin', self.root, inputs)

    def test_same_named_pyc_is_never_used(self):
        # A deliberately invalid cache cannot influence explicit source-byte execution.
        (self.helpers/'test_direct.pyc').write_bytes(b'not python bytecode')
        result = b.authenticate_producer(self.root/'receipt', self.root/'bin', self.root, b.producer_authentication_inputs(self.root))
        self.assertEqual(result['value'], 'original source helper')


if __name__ == '__main__':
    unittest.main()
