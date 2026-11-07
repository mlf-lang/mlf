#!/usr/bin/env python3
"""Pure filesystem/mock controls. Fabricated fixtures are NEVER qualification evidence."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('prerequisites', Path(__file__).with_name('collect_ghc_native_prerequisites.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PrerequisiteControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'source'; self.root.mkdir()
        self.output = self.base / 'evidence'
        for name in p.FOUNDATIONS:
            original = p.read(p.ROOT / 'libraries' / name / 'mlf-package.json')
            self.package('libraries/' + name, name, original['library']['modules'], original.get('dependencies', {}))
        for label, relative in p.PLAN_ROOTS.items():
            if label == 'async':
                continue
            dependencies = {name: {'path': __import__('os').path.relpath(self.root / 'libraries' / name,
                                                                         self.root / relative)} for name in p.FOUNDATIONS}
            self.package(relative, 'fixture-' + label, {'Fixture.' + label.replace('-', '').capitalize(): 'Module.hs'}, dependencies)
        for rel in p.PLAN_ROOTS.values():
            manifest = self.root / rel / 'mlf-package.json'
            snapshot, _ = p.package_graph(self.root, manifest)
            self.write(manifest.parent / 'mlf.lock', snapshot)
        producer = self.base / 'producer/receipt.json'
        self.write(producer, {'fixture': 'MOCK ONLY, NOT AUTHENTICATED GHC EVIDENCE'})
        self.write(producer.parent / 'bin/emlf', 'fixture compiler')
        self.write(producer.parent / 'bin/mlfpkg', 'fixture manager')
        for name in p.AUTH_HELPERS:
            self.write(self.root / 'tools/shared' / name, 'MOCK authentication helper')
        python = self.write(self.base / 'python', 'MOCK Python')
        git = self.write(self.base / 'git', 'MOCK Git')
        self.binding = {'source_root': str(self.root), 'source_checkpoint': 'a' * 40,
                        'driver_root': str(p.ROOT), 'driver_checkpoint': 'b' * 40,
                        'producer': p.identity(producer), 'compiler': p.identity(producer.parent / 'bin/emlf'),
                        'manager': p.identity(producer.parent / 'bin/mlfpkg'),
                        'collector': p.identity(Path(p.__file__).resolve()),
                        'watchdog': p.identity(Path(p.__file__).with_name('resource_watchdog.py').resolve()),
                        'git': p.identity(git), 'python': p.identity(python),
                        'authentication_helpers': {str(self.root / 'tools/shared' / n): p.sha(self.root / 'tools/shared' / n) for n in p.AUTH_HELPERS},
                        'workspace_root': str(self.base), 'environment': p.environment(self.output),
                        'allocation': {'plan_seconds': 120, 'crate_seconds': 600, 'total_seconds': 4000,
                                       'address_space_mib': 512, 'rss_mib': 512, 'disk_free_mib': 8192,
                                       'output_mib': 16, 'workspace_mib': 1024}}
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'managed_run', side_effect=self.command):
            p.collect(self.binding, self.output)
        self.gate_path = self.output / 'gate.json'
        self.plans_path = self.output / 'plans/receipt.json'
        self.gate = p.read(self.gate_path)
        self.plans = p.read(self.plans_path)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value))
        return path

    def package(self, relative, name, modules, dependencies):
        directory = self.root / relative
        self.write(directory / 'mlf-package.json', {'format': 1, 'name': name, 'version': '0.3.0',
                   'library': {'modules': modules}, 'dependencies': dependencies})
        for module, relative in modules.items():
            self.write(directory / relative, 'module ' + module + ' where {}\n')

    def plan_fixture(self, manifest):
        snapshot, _ = p.package_graph(self.root, manifest)
        result = copy.deepcopy(snapshot)
        crates, modules = [], []
        packages = {r['name']: r for r in snapshot['packages']}
        for row in snapshot['packages']:
            data = p.read((manifest.parent / row['path']).resolve() / 'mlf-package.json')
            names = sorted(data.get('library', {}).get('modules', {}))
            modules.extend(names)
            if names:
                crates.append({'crate': row['name'] + '/0.3.0/library', 'entry': '', 'modules': names,
                               'dependencies': [name + '/0.3.0/library' for name in sorted(data['dependencies'])
                                                if name in packages]})
        result.update(crates=crates, modules=modules, executables=[], tests=[])
        return result

    def command(self, wrapper, *, cwd, env, stdout, timeout):
        # Tests fake the OS boundary, while collection/read-back logic stays real.
        # Locate fixed option tail, rather than accepting a fixture-controlled argv.
        index = wrapper.index('--disk-free-mib')
        directory = Path(wrapper[index + 2]); argv = wrapper[index + 3:]
        if argv[0] == self.binding['manager']['path']:
            manifest = Path(argv[argv.index('--manifest') + 1])
            raw = json.dumps(self.plan_fixture(manifest)) + '\n'
            phase = 'plan'
        else:
            crate = p.read(directory / 'cold-start.json')['crate']
            self.write(directory / 'unit.mlfci', 'MOCK metadata')
            self.write(directory / 'unit.mlfco', 'MOCK object')
            self.write(directory / 'builtin/unit.mlfci', 'MOCK builtin metadata')
            self.write(directory / 'builtin/unit.mlfco', 'MOCK builtin object')
            self.write(directory / 'queries/query-fixture', 'MOCK cache')
            report = {'format': 1, 'crate': crate, 'semantic_fingerprint': 'fixture-semantic',
                      'inferred_groups': 1, 'reused_groups': 0,
                      'groups': [{'id': 'fixture-group', 'members': ['fixture-value'], 'cached': False,
                                  'query_key': 'fixture-key', 'semantic_fingerprint': 'fixture-semantic'}]}
            self.write(directory / 'unit.queries', report)
            raw, phase = 'fixture compiler output\n', 'crate'
        self.write(directory / 'build.log', raw)
        bounded = {'complete': True, 'exit_code': 0, 'reason': None, 'command': argv,
                   'output_root': str(self.output), 'workspace_root': str(self.base),
                   'limits': p.limits(self.binding, phase), 'elapsed_seconds': 0.5,
                   'peak_group_rss': 1, 'process_group': 123, 'final_owned_descendants': [],
                   'samples': [{'seconds': 0.25, 'group_rss': 1, 'host_available': 4 * 1024 ** 3,
                                'disk_free': 9 * 1024 ** 3, 'output_bytes': 1024, 'workspace_allocated_bytes': 2048}]}
        self.write(directory / 'bounded-receipt.json', bounded)
        stdout.write(json.dumps({k: v for k, v in bounded.items() if k != 'samples'}).encode() + b'\n')
        return mock.Mock(returncode=0)

    def check(self):
        self.write(self.gate_path, self.gate); self.write(self.plans_path, self.plans)
        seal = p.read(self.output / 'complete.json')
        seal.update(gate=p.identity(self.gate_path), plans=p.identity(self.plans_path))
        self.write(self.output / 'complete.json', seal)
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'):
            return p.verify_prerequisites(gate_receipt=self.gate_path, gate_sha256=p.sha(self.gate_path),
                plans_dir=self.plans_path.parent, plans_sha256=p.sha(self.plans_path),
                producer_receipt=self.binding['producer']['path'], producer_sha256=self.binding['producer']['sha256'],
                source_root=self.root, source_checkpoint=self.binding['source_checkpoint'],
                driver_root=p.ROOT, driver_checkpoint=self.binding['driver_checkpoint'])

    def reject(self):
        with self.assertRaises((ValueError, KeyError, FileNotFoundError)):
            self.check()

    def update_artifact(self, path, value, gate=True):
        self.write(path, value)
        (self.gate if gate else self.plans)['artifacts'][str(path)] = p.sha(path)

    def test_full_mock_collection_and_readback(self):
        result = self.check()
        self.assertIn(str(self.gate_path), result['inputs'])
        self.assertEqual(sum(len(x['modules']) for x in self.gate['inventory'].values()),
                         sum(len(x['modules']) for x in p.foundational_inventory(p.ROOT).values()))
        self.assertFalse((self.output / 'failure.json').exists())
        self.assertEqual(len(self.plans['roots']), 6)
        self.assertEqual(len(self.gate['commands']), 4)

    def test_output_not_overwritten(self):
        with self.assertRaises(FileExistsError):
            p.collect(self.binding, self.output)

    def test_missing_async(self):
        del self.gate['results']['mlf-async/0.3.0/library']; self.reject()

    def test_duplicate_gate_command(self):
        self.gate['commands'][-1] = self.gate['commands'][0]; self.reject()

    def test_duplicate_plan_root(self):
        self.plans['roots'][-1] = self.plans['roots'][0]; self.reject()

    def test_wrong_root_manifest(self):
        self.plans['roots'][0]['manifest'] = self.plans['roots'][1]['manifest']; self.reject()

    def test_wrong_producer(self):
        self.gate['producer_receipt_sha256'] = '0' * 64; self.reject()

    def test_wrong_source_root(self):
        self.gate['binding']['source_root'] = str(self.base); self.reject()

    def test_wrong_source_checkpoint(self):
        self.gate['binding']['source_checkpoint'] = 'c' * 40; self.reject()

    def test_warm_as_cold(self):
        path = self.output / 'crates/mlf-async/unit.queries'
        report = p.read(path); report['reused_groups'] = 1
        self.update_artifact(path, report); self.reject()

    def test_cached_group(self):
        path = self.output / 'crates/mlf-async/unit.queries'
        report = p.read(path); report['groups'][0]['cached'] = True
        self.update_artifact(path, report); self.reject()

    def test_same_count_wrong_modules(self):
        value = self.gate['inventory']['mlf-async/0.3.0/library']['modules']
        value['Wrong.Module'] = value.pop(next(iter(value))); self.reject()

    def test_wrong_result_count(self):
        self.gate['results']['mlf-async/0.3.0/library']['module_count'] += 1; self.reject()

    def test_changed_source(self):
        path = self.root / 'libraries/mlf-async/Async/Task.hs'
        path.write_text(path.read_text() + '-- changed\n'); self.reject()

    def test_missing_input_even_with_matching_inventory(self):
        self.gate['inputs'].pop(str(self.root / 'libraries/mlf-async/mlf-package.json')); self.reject()

    def test_aliased_manifest_module_path(self):
        manifest = self.root / 'libraries/mlf-async/mlf-package.json'
        value = p.read(manifest); value['library']['modules']['Async.Task'] = 'Async/./Task.hs'
        self.write(manifest, value)
        with self.assertRaisesRegex(ValueError, 'aliased'):
            p.foundational_inventory(self.root)

    def test_symlink_source(self):
        path = self.root / 'libraries/mlf-async/Async/Task.hs'
        path.rename(path.with_suffix('.real')); path.symlink_to(path.with_suffix('.real'))
        with self.assertRaisesRegex(ValueError, 'noncanonical'):
            p.foundational_inventory(self.root)

    def test_duplicate_json_key(self):
        path = self.base / 'duplicate.json'; path.write_text('{"x": 1, "x": 2}')
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            p.read(path)

    def test_changed_argv_with_rehashed_raw_invocation(self):
        row = self.gate['commands'][0]
        path = Path(row['invocation']['path']); value = p.read(path)
        value['argv'].append('--warm'); row['argv'].append('--warm')
        self.update_artifact(path, value); row['invocation'] = p.identity(path); self.reject()

    def test_changed_crate_spec(self):
        path = self.output / 'crates/mlf-async/crate.spec'
        self.update_artifact(path, 'unreviewed spec'); self.gate['inputs'][str(path)] = p.sha(path); self.reject()

    def test_failed_exit_despite_complete(self):
        path = self.output / 'crates/mlf-async/exit.json'
        self.update_artifact(path, {'wrapper_exit': 1}); self.reject()

    def test_tampered_resource_limit(self):
        row = self.gate['commands'][0]; path = Path(row['receipt']); value = p.read(path)
        value['limits']['process_tree_rss_bytes'] *= 2
        self.update_artifact(path, value); row['receipt_sha256'] = p.sha(path); self.reject()

    def test_resource_overage_despite_complete(self):
        row = self.gate['commands'][0]; path = Path(row['receipt']); value = p.read(path)
        value['samples'][0]['output_bytes'] = 100 * p.MIB
        self.update_artifact(path, value); row['receipt_sha256'] = p.sha(path); self.reject()

    def test_descendant_teardown_required(self):
        row = self.gate['commands'][0]; path = Path(row['receipt']); value = p.read(path)
        value['final_owned_descendants'] = [{'pid': 123, 'starttime': '456'}]
        self.update_artifact(path, value); row['receipt_sha256'] = p.sha(path); self.reject()

    def test_raw_wrapper_output_changed(self):
        path = self.output / 'crates/mlf-async/wrapper.log'
        self.update_artifact(path, {'complete': True}); self.reject()

    def test_cold_start_not_empty(self):
        path = self.output / 'crates/mlf-async/cold-start.json'; value = p.read(path)
        value['queries'] = ['warm-cache']; self.update_artifact(path, value); self.reject()

    def test_unmapped_cache_file(self):
        self.write(self.output / 'crates/mlf-async/queries/unbound', 'changed'); self.reject()

    def test_missing_output(self):
        (self.output / 'crates/mlf-async/unit.mlfco').unlink(); self.reject()

    def test_stale_lock(self):
        self.write(self.root / 'mlf.lock', {'format': 1, 'packages': []}); self.reject()

    def test_lock_change_record(self):
        self.plans['roots'][0]['before_lock'] = '0' * 64; self.reject()

    def test_lock_validation_not_lock_writer(self):
        self.plans['roots'][0]['lock-validation']['mode'] = 'lock'; self.reject()

    def test_plan_bytes_not_raw_output(self):
        path = self.output / 'plans/root-plan.json'
        value = p.read(path); value['unexpected'] = True
        self.update_artifact(path, value, gate=False)
        self.plans['roots'][0]['plan_sha256'] = p.sha(path); self.reject()

    def test_plan_package_omission(self):
        manifest = self.root / 'mlf-package.json'
        plan = self.plan_fixture(manifest); plan['packages'].pop()
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            p.verify_plan(plan, self.root, manifest)

    def test_plan_crate_module_tamper(self):
        manifest = self.root / 'mlf-package.json'
        plan = self.plan_fixture(manifest); plan['crates'][0]['modules'][0] = 'Wrong.Module'
        with self.assertRaisesRegex(ValueError, 'crate/module'):
            p.verify_plan(plan, self.root, manifest)

    def test_source_checkpoint_is_enforced_by_public_verifier(self):
        with mock.patch.object(p, 'checkpoint', side_effect=ValueError('dirty checkpoint')):
            with self.assertRaisesRegex(ValueError, 'dirty checkpoint'):
                p.verify_prerequisites(gate_receipt=self.gate_path, gate_sha256=p.sha(self.gate_path),
                    plans_dir=self.plans_path.parent, plans_sha256=p.sha(self.plans_path),
                    producer_receipt=self.binding['producer']['path'], producer_sha256=self.binding['producer']['sha256'],
                    source_root=self.root, source_checkpoint=self.binding['source_checkpoint'])

    def test_stale_lock_stops_before_manager_invocation(self):
        self.write(self.root / 'mlf.lock', {'format': 1, 'packages': []})
        output = self.base / 'stale'; binding = copy.deepcopy(self.binding)
        binding['environment'] = p.environment(output)
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'managed_run') as run:
            with self.assertRaisesRegex(ValueError, 'stale source lock'):
                p.collect(binding, output)
            run.assert_not_called()
        self.assertFalse(p.read(output / 'failure.json')['complete'])

    def test_final_seal_required(self):
        (self.output / 'complete.json').unlink()
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'):
            with self.assertRaises((ValueError, FileNotFoundError)):
                p.verify_prerequisites(gate_receipt=self.gate_path, gate_sha256=p.sha(self.gate_path),
                    plans_dir=self.plans_path.parent, plans_sha256=p.sha(self.plans_path),
                    producer_receipt=self.binding['producer']['path'], producer_sha256=self.binding['producer']['sha256'],
                    source_root=self.root, source_checkpoint=self.binding['source_checkpoint'])

    def test_retained_failure_disqualifies_complete_seal(self):
        self.write(self.output / 'failure.json', {'complete': False})
        self.reject()

    def test_changed_source_authentication_helper(self):
        self.write(self.root / 'tools/shared/test_direct.py', 'changed source helper')
        self.reject()

    def test_hardlink_artifact_rejected(self):
        import os
        path = self.output / 'crates/mlf-async/unit.mlfco'
        os.link(path, self.base / 'shared-artifact')
        self.reject()

    def test_incomplete_six_root_artifact_inventory(self):
        self.write(self.output / 'plans/unbound', 'unexpected artifact')
        self.reject()

    def test_no_room_for_next_bounded_action(self):
        output = self.base / 'too-short'; binding = copy.deepcopy(self.binding)
        binding['environment'] = p.environment(output)
        binding['allocation']['total_seconds'] = 1
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'managed_run') as run:
            with self.assertRaisesRegex(ValueError, 'window'):
                p.collect(binding, output)
            run.assert_not_called()
        self.assertFalse(p.read(output / 'failure.json')['complete'])

    def test_source_original_path_loading_without_pyc(self):
        helper = self.root / 'tools/shared/test_direct.py'
        helper.write_text("def authenticate_build(path, binaries, root):\n"
                          "    return {'optimization': '2', 'loaded_path': __file__}\n")
        value = p.authenticate_producer(Path(self.binding['producer']['path']), self.root)
        self.assertEqual(value['loaded_path'], str(helper))
        self.assertFalse((helper.parent / '__pycache__').exists())

    def test_failed_collection_is_retained_not_passed(self):
        output = self.base / 'failed'; binding = copy.deepcopy(self.binding)
        binding['environment'] = p.environment(output)
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'run_command', side_effect=ValueError('failed action')):
            with self.assertRaisesRegex(ValueError, 'failed action'):
                p.collect(binding, output)
        self.assertFalse((output / 'gate.json').exists())
        self.assertFalse((output / 'complete.json').exists())
        self.assertFalse(p.read(output / 'failure.json')['complete'])


if __name__ == '__main__':
    unittest.main()
