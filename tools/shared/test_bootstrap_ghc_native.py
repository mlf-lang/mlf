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
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        evidence = self.root / 'evidence'
        evidence.write_text('original execution evidence')
        self.gate = {'status': 'passed', 'producer_receipt_sha256': 'producer',
                     'inputs': {str(evidence): b.sha(evidence)},
                     'artifacts': {str(evidence): b.sha(evidence)}, 'results': {}, 'commands': []}
        for name, count in [('foundation', 12), ('async', 5), ('language-core', 4), ('frontend', 10)]:
            self.add_crate(name, count)

    def add_crate(self, name, count):
        crate = 'mlf-' + name + '/0.3.0/library'
        self.gate['results'][crate] = {'module_count': count, 'reused_groups': 0}
        self.gate['commands'].append({'crate': crate, 'status': 'passed', 'resource': {'complete': True}})

    def check(self):
        path = self.root / 'receipt.json'
        path.write_text(json.dumps(self.gate))
        return b.authenticate_gate(path, b.sha(path), 'producer')

    def test_four_only(self):
        self.check()

    def test_combined(self):
        self.add_crate('inference', 6)
        self.check()

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
        with mock.patch('sys.argv', args), mock.patch.object(b.direct, 'authenticate_build') as authenticate:
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
        argv = [sys.executable, str(watchdog), '--seconds', '60', '--address-space-mib', '1024',
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


if __name__ == '__main__':
    unittest.main()
