#!/usr/bin/env python3
"""NEW recovery controls, based on the retained 94 schema tests.

These are not recovered original 55 tests or production-source validation.
Packages/modules are synthetic except the explicitly labelled retained actual-plan
readback, enabled only with MLF_PREREQUISITE_PLAN_SOURCE_ROOT. No compiler/manager is executed.
Filesystem/mock controls are NEVER qualification evidence.
"""
import copy
import importlib.util
import json
import io
import os
import signal
import subprocess
import sys
import time
import types
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location('prerequisites', Path(__file__).with_name('collect_ghc_native_prerequisites.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class MockBudget:
    """Synthetic observations ONLY for schema tests, never resource measurement."""
    def __init__(self, output, workspace, args):
        self.args = args
    def start(self): pass
    def check(self): pass
    def stop_monitor(self): pass
    def close(self): pass
    def summary(self):
        return {'scope': 'whole driver and observed descendants', 'samples': 1,
                'last_sample': {'seconds': 0.1, 'process_tree_rss_bytes': 1,
                    'output_bytes': 1, 'workspace_allocated_bytes': 1,
                    'host_available_bytes': 4 * 1024**3, 'disk_free_bytes': 9 * 1024**3},
                'peaks': {'process_tree_rss_bytes': 1, 'output_bytes': 1, 'workspace_allocated_bytes': 1},
                'failure': None, 'driver_address_space_bytes': self.args.address_space_mib * p.MIB,
                'checkpoint_reserve_mib': 512}


class PrerequisiteControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'source'; self.root.mkdir()
        self.output = self.base / 'evidence'
        synthetic = {
            'mlf-foundation': {'Fixture.Foundation': 'Fixture/Foundation.hs'},
            'mlf-async': {'Async.Task': 'Async/Task.hs', 'Fixture.AsyncTypes': 'Fixture/AsyncTypes.hs'},
            'mlf-language-core': {'Fixture.LanguageCore': 'Fixture/LanguageCore.hs'},
            'mlf-frontend': {'Fixture.Frontend': 'Fixture/Frontend.hs'},
        }
        for name in p.FOUNDATIONS:
            dependencies = {} if name == 'mlf-foundation' else {'mlf-foundation': {'path': '../mlf-foundation'}}
            if name == 'mlf-frontend':
                dependencies['mlf-language-core'] = {'path': '../mlf-language-core'}
            self.package('libraries/' + name, name, synthetic[name], dependencies)
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
                        'supervisor': p.identity(p.ROOT / 'tools/shared/bootstrap_ghc_native.py'),
                        'git': p.identity(git), 'python': p.identity(python),
                        'authentication_helpers': {str(self.root / 'tools/shared' / n): p.sha(self.root / 'tools/shared' / n) for n in p.AUTH_HELPERS},
                        'workspace_root': str(self.base), 'environment': p.environment(self.output),
                        'allocation': {'plan_seconds': 120, 'crate_seconds': 600, 'total_seconds': 4000,
                                       'address_space_mib': 512, 'rss_mib': 512, 'disk_free_mib': 8192,
                                       'output_mib': 16, 'workspace_mib': 1024}}
        self.real_load_supervisor = p.load_supervisor
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'managed_run', side_effect=self.command), \
                mock.patch.object(p, 'load_supervisor', side_effect=self.mock_supervisor), redirect_stdout(io.StringIO()):
            p.collect(self.binding, self.output)
        self.gate_path = self.output / 'gate.json'
        self.plans_path = self.output / 'plans/receipt.json'
        self.gate = p.read(self.gate_path)
        self.plans = p.read(self.plans_path)

    def mock_supervisor(self, expected=None):
        module = self.real_load_supervisor(expected)
        module.DriverBudget = MockBudget
        return module

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

    def command(self, wrapper, *, cwd, env, stdout, timeout, teardown=None, supervisor=None):
        teardown.update(drained=True, remaining=[], initial=[], seconds=0)
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
            # Mirror the reviewed four-crate inheritance layout, not CI encoding.
            # Only foundation installs; dependency consumers leave the fallback
            # builtin destination empty. These bytes are synthetic, not evidence.
            if crate == 'mlf-foundation/0.3.0/library':
                self.write(directory / 'builtin/unit.mlfci', 'MOCK builtin metadata')
                self.write(directory / 'builtin/unit.mlfco', 'MOCK builtin object')
                self.write(directory / 'builtin/unit.lock', '')
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
        resource_path = self.output / 'driver-resources-final.json'
        if resource_path.exists():
            resources = p.read(resource_path)
            resources['seal'] = p.identity(self.output / 'complete.json')
            self.write(resource_path, resources)
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
                         5)  # This is the explicit synthetic inventory, never the production count.
        self.assertFalse((self.output / 'failure.json').exists())
        self.assertEqual(len(self.plans['roots']), 6)
        self.assertEqual(len(self.gate['commands']), 4)

    def test_mock_four_crate_inheritance_layout(self):
        self.check()
        owner = self.output / 'crates/mlf-foundation/builtin'
        self.assertEqual({f.name for f in owner.iterdir()}, {'unit.mlfci', 'unit.mlfco', 'unit.lock'})
        for name in ('mlf-async', 'mlf-language-core', 'mlf-frontend'):
            self.assertEqual(list((self.output / 'crates' / name / 'builtin').iterdir()), [])
        frontend = self.root / 'libraries/mlf-frontend/mlf-package.json'
        self.assertEqual(p.read(frontend)['dependencies'], {
            'mlf-foundation': {'path': '../mlf-foundation'},
            'mlf-language-core': {'path': '../mlf-language-core'}})
        for dep in ('mlf-foundation', 'mlf-language-core'):
            self.assertIn(str(self.output / 'crates' / dep / 'unit.mlfci'),
                          (self.output / 'crates/mlf-frontend/crate.spec').read_text())

    def test_missing_owner_files_even_with_rebound_inventory(self):
        for name in ('unit.mlfci', 'unit.mlfco', 'unit.lock'):
            with self.subTest(name=name):
                path = self.output / 'crates/mlf-foundation/builtin' / name
                raw, digest = path.read_bytes(), self.gate['artifacts'].pop(str(path))
                path.unlink()
                self.reject()
                path.write_bytes(raw); self.gate['artifacts'][str(path)] = digest

    def test_empty_owner_pair_even_with_rebound_hashes(self):
        for name in ('unit.mlfci', 'unit.mlfco'):
            with self.subTest(name=name):
                path = self.output / 'crates/mlf-foundation/builtin' / name
                raw = path.read_text()
                self.update_artifact(path, ''); self.reject()
                self.update_artifact(path, raw)

    def test_owner_files_reject_hardlinks_and_symlinks(self):
        for name in ('unit.mlfci', 'unit.mlfco', 'unit.lock'):
            path = self.output / 'crates/mlf-foundation/builtin' / name
            for kind in ('hardlink', 'symlink', 'dangling'):
                with self.subTest(name=name, kind=kind):
                    alias = self.base / 'alias'
                    raw = path.read_bytes()
                    if kind == 'hardlink':
                        os.link(path, alias)
                    else:
                        path.rename(alias)
                        path.symlink_to(alias if kind == 'symlink' else self.base / 'missing')
                    self.reject()
                    if kind != 'hardlink':
                        path.unlink(); path.write_bytes(raw)
                    alias.unlink()

    def test_builtin_directories_reject_symlink_ancestors(self):
        for name in p.FOUNDATIONS:
            with self.subTest(name=name):
                path = self.output / 'crates' / name / 'builtin'
                target = self.base / 'moved-builtin'
                path.rename(target); path.symlink_to(target, target_is_directory=True)
                self.reject()
                path.unlink(); target.rename(path)

    def test_builtin_directories_are_required_even_for_consumers(self):
        for name in ('mlf-async', 'mlf-language-core', 'mlf-frontend'):
            with self.subTest(name=name):
                path = self.output / 'crates' / name / 'builtin'
                path.rmdir(); self.reject(); path.mkdir()

    def test_nonowner_local_contents_rejected_even_if_inventory_rebound(self):
        for name in ('mlf-async', 'mlf-language-core', 'mlf-frontend'):
            for leaf in ('unit.mlfci', 'unit.mlfco', 'unit.lock', 'unexpected', 'directory', 'dangling'):
                with self.subTest(name=name, leaf=leaf):
                    path = self.output / 'crates' / name / 'builtin' / leaf
                    if leaf == 'directory':
                        path.mkdir()
                    elif leaf == 'dangling':
                        path.symlink_to(self.base / 'missing')
                    else:
                        self.update_artifact(path, 'MOCK unexpected local builtin')
                    self.reject()
                    path.rmdir() if leaf == 'directory' else path.unlink()
                    self.gate['artifacts'].pop(str(path), None)

    def test_owner_extra_contents_rejected_even_if_inventory_rebound(self):
        for leaf in ('unexpected', 'directory'):
            with self.subTest(leaf=leaf):
                path = self.output / 'crates/mlf-foundation/builtin' / leaf
                if leaf == 'directory':
                    path.mkdir()
                else:
                    self.update_artifact(path, 'MOCK unexpected owner file')
                self.reject()
                path.rmdir() if leaf == 'directory' else path.unlink()
                self.gate['artifacts'].pop(str(path), None)

    def test_owner_artifact_bytes_and_full_hash_inventory_required(self):
        for name in ('unit.mlfci', 'unit.mlfco', 'unit.lock'):
            path = self.output / 'crates/mlf-foundation/builtin' / name
            with self.subTest(name=name, mutation='bytes'):
                raw = path.read_bytes(); path.write_bytes(raw + b'tampered external reference')
                self.reject(); path.write_bytes(raw)
            with self.subTest(name=name, mutation='map omission'):
                digest = self.gate['artifacts'].pop(str(path))
                self.reject(); self.gate['artifacts'][str(path)] = digest

    def test_frozen_foundational_dependency_closure_required(self):
        changes = [
            ('mlf-foundation', {'mlf-frontend': {'path': '../mlf-frontend'}}),
            ('mlf-async', {}),
            ('mlf-language-core', {'mlf-async': {'path': '../mlf-async'}}),
            ('mlf-frontend', {'mlf-foundation': {'path': '../mlf-foundation'}}),
            ('mlf-frontend', {'mlf-foundation': {'path': '../mlf-foundation'},
                              'mlf-language-core': {'path': '../mlf-language-core'},
                              'unknown': {'path': '../unknown'}}),
            ('mlf-async', {'mlf-foundation': {'path': '../old-foundation'}}),
        ]
        for name, dependencies in changes:
            with self.subTest(name=name, dependencies=dependencies):
                path = self.root / 'libraries' / name / 'mlf-package.json'
                original = p.read(path); changed = dict(original, dependencies=dependencies)
                self.write(path, changed)
                with self.assertRaisesRegex(ValueError, 'unreviewed foundational dependency graph'):
                    p.foundational_inventory(self.root)
                self.reject()
                self.write(path, original)

    def test_rebound_specs_cannot_change_dependency_or_builtin_paths(self):
        path = self.output / 'crates/mlf-frontend/crate.spec'
        original = path.read_text()
        dependency = str(self.output / 'crates/mlf-language-core/unit.mlfci')
        builtin = str(self.output / 'crates/mlf-frontend/builtin/unit')
        for old, replacement in ((p.pack([dependency]), ''),
                                 (dependency, str(self.base / 'old-run/unit.mlfci')),
                                 (builtin, str(self.base / 'external-builtin/unit'))):
            with self.subTest(replacement=replacement):
                changed = original.replace(old, replacement)
                self.assertNotEqual(changed, original)
                self.update_artifact(path, changed)
                self.gate['inputs'][str(path)] = p.sha(path)
                self.reject()
        self.update_artifact(path, original); self.gate['inputs'][str(path)] = p.sha(path)

    def test_builtin_layout_failure_is_retained_without_success_seals(self):
        self.next_output('failed-builtin-layout')
        def command(wrapper, **kwargs):
            result = self.command(wrapper, **kwargs)
            if '--compile-crate' in wrapper:
                spec_path = Path(wrapper[wrapper.index('--compile-crate') + 1])
                if spec_path.parent.name == 'mlf-async':
                    self.write(spec_path.parent / 'builtin/unexpected', 'MOCK local content')
            return result
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'load_supervisor', side_effect=self.mock_supervisor), \
                mock.patch.object(p, 'managed_run', side_effect=command), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, 'unexpected builtin directory contents'):
                p.collect(self.binding, self.output)
        self.assertTrue((self.output / 'gate.json').exists())
        self.assertFalse(p.read(self.output / 'failure.json')['complete'])
        self.assertFalse((self.output / 'complete.json').exists())
        self.assertFalse((self.output / 'driver-resources-final.json').exists())

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
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'load_supervisor', side_effect=self.mock_supervisor), \
                mock.patch.object(p, 'managed_run') as run:
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
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'load_supervisor', side_effect=self.mock_supervisor), \
                mock.patch.object(p, 'managed_run') as run:
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
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'load_supervisor', side_effect=self.mock_supervisor), \
                mock.patch.object(p, 'run_command', side_effect=ValueError('failed action')):
            with self.assertRaisesRegex(ValueError, 'failed action'):
                p.collect(binding, output)
        self.assertFalse((output / 'gate.json').exists())
        self.assertFalse((output / 'complete.json').exists())
        self.assertFalse(p.read(output / 'failure.json')['complete'])


    def test_source_helper_inventory_matches_supervisor(self):
        self.assertEqual(p.AUTH_HELPERS, self.real_load_supervisor().PRODUCER_AUTH_HELPERS)
        self.assertEqual(len(p.AUTH_HELPERS), 6)
        self.assertIn('native_install.py', p.AUTH_HELPERS)
        self.assertIn('pool_generated_strings.py', p.AUTH_HELPERS)

    def test_native_install_tamper_rejected(self):
        self.write(self.root / 'tools/shared/native_install.py', 'changed')
        self.reject()

    def test_pool_helper_tamper_rejected(self):
        self.write(self.root / 'tools/shared/pool_generated_strings.py', 'changed')
        self.reject()

    def test_helper_mutation_during_authentication_rejected(self):
        helper = self.root / 'tools/shared/test_direct.py'
        helper.write_text("def authenticate_build(path, binaries, root):\n"
                          "    (root / 'tools/shared/native_install.py').write_text('mutated')\n"
                          "    return {'optimization': '2'}\n")
        original = p.authentication_inputs(self.root)
        with self.assertRaisesRegex(ValueError, 'changed during authentication'):
            p.authenticate_producer(Path(self.binding['producer']['path']), self.root, original)

    def test_helper_drift_before_authentication_rejected(self):
        original = p.authentication_inputs(self.root)
        self.write(self.root / 'tools/shared/pool_generated_strings.py', 'changed')
        with self.assertRaisesRegex(ValueError, 'before authentication'):
            p.authenticate_producer(Path(self.binding['producer']['path']), self.root, original)

    def test_supervisor_hash_drift_rejected(self):
        changed = dict(self.binding['supervisor'], sha256='0' * 64)
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            self.real_load_supervisor(changed)

    def test_supervisor_wrong_path_rejected(self):
        changed = dict(self.binding['supervisor'], path=str(self.base / 'wrong.py'))
        with self.assertRaisesRegex(ValueError, 'wrong supervisor path'):
            self.real_load_supervisor(changed)

    def test_named_module_poison_does_not_redirect_supervisor(self):
        before = list(sys.path)
        poison = types.ModuleType('prerequisite_resource_supervisor')
        with mock.patch.dict(sys.modules, {'prerequisite_resource_supervisor': poison, 'direct_auth': poison}):
            module = self.real_load_supervisor(self.binding['supervisor'])
            self.assertIsNot(module, poison)
            self.assertEqual(module.ROOT, p.ROOT)
            self.assertIs(sys.modules['prerequisite_resource_supervisor'], poison)
        self.assertEqual(sys.path, before)

    def test_parent_resource_record_required(self):
        (self.output / 'driver-resources-final.json').unlink()
        self.reject()

    def test_parent_resource_overage_rejected(self):
        path = self.output / 'driver-resources-final.json'
        value = p.read(path)
        value['observation']['last_sample']['output_bytes'] = 17 * p.MIB
        self.write(path, value)
        self.reject()

    def test_parent_resource_peak_overage_rejected(self):
        path = self.output / 'driver-resources-final.json'
        value = p.read(path)
        value['observation']['peaks']['process_tree_rss_bytes'] = 513 * p.MIB
        self.write(path, value)
        self.reject()

    def test_parent_resource_failure_rejected(self):
        path = self.output / 'driver-resources-final.json'
        value = p.read(path)
        value['observation']['failure'] = 'sample failed'
        self.write(path, value)
        self.reject()

    def test_parent_supervisor_undrained_rejected(self):
        path = self.output / 'crates/mlf-async/supervisor.json'
        self.update_artifact(path, {'drained': False, 'remaining': [{'pid': 123, 'start_time': 'test'}]})
        self.reject()

    def test_parent_supervisor_evidence_required(self):
        (self.output / 'crates/mlf-async/supervisor.json').unlink()
        self.reject()

    def test_parent_supervisor_failure_evidence_is_retained(self):
        directory = self.output / 'extra-command'
        def interrupted(wrapper, **kwargs):
            kwargs['teardown'].update(drained=False, remaining=[{'pid': 123, 'start_time': 'fixture'}])
            raise subprocess.TimeoutExpired(wrapper, 1)
        with mock.patch.object(p, 'managed_run', side_effect=interrupted):
            with self.assertRaises(subprocess.TimeoutExpired):
                p.run_command(self.binding, self.output, directory,
                              p.plan_command(self.binding, self.output, 'root'), 'plan')
        self.assertFalse(p.read(directory / 'supervisor.json')['drained'])
        self.assertFalse((directory / 'exit.json').exists())

    def next_output(self, name):
        self.output = self.base / name
        self.binding = copy.deepcopy(self.binding)
        self.binding['environment'] = p.environment(self.output)

    def test_actual_parent_rss_limit_precedes_command(self):
        self.next_output('rss-failure')
        self.binding['allocation']['rss_mib'] = 1
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'managed_run') as run:
            with self.assertRaisesRegex(ValueError, 'RSS limit'):
                p.collect(self.binding, self.output)
        run.assert_not_called()
        failure = p.read(self.output / 'failure.json')
        self.assertFalse(failure['complete'])
        self.assertGreater(failure['driver_resource']['last_sample']['process_tree_rss_bytes'], p.MIB)

    def test_actual_parent_address_space_limit_and_restore(self):
        import resource
        self.next_output('address-space')
        self.binding['allocation']['address_space_mib'] = 256
        previous = resource.getrlimit(resource.RLIMIT_AS)
        observed = []
        def authentication(*args):
            observed.append(resource.getrlimit(resource.RLIMIT_AS)[0])
            raise ValueError('stop after address-space observation')
        with mock.patch.object(p, 'checkpoint'), \
                mock.patch.object(p, 'authenticate_producer', side_effect=authentication), \
                mock.patch.object(p, 'managed_run') as run:
            with self.assertRaisesRegex(ValueError, 'address-space observation'):
                p.collect(self.binding, self.output)
        run.assert_not_called()
        self.assertEqual(len(observed), 1)
        self.assertLessEqual(observed[0], 256 * p.MIB)
        self.assertEqual(resource.getrlimit(resource.RLIMIT_AS), previous)

    def test_actual_parent_alarm_covers_python_authentication(self):
        self.next_output('alarm-failure')
        self.binding['allocation']['total_seconds'] = 1
        began = time.monotonic()
        with mock.patch.object(p, 'checkpoint'), \
                mock.patch.object(p, 'authenticate_producer', side_effect=lambda *a: time.sleep(5)), \
                mock.patch.object(p, 'managed_run') as run:
            with self.assertRaises((InterruptedError, ValueError, RuntimeError)):
                p.collect(self.binding, self.output)
        run.assert_not_called()
        self.assertLess(time.monotonic() - began, 4)
        self.assertFalse(p.read(self.output / 'failure.json')['complete'])
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_parent_does_not_cancel_existing_alarm(self):
        self.next_output('foreign-alarm')
        previous_handler = signal.getsignal(signal.SIGALRM)
        signal.setitimer(signal.ITIMER_REAL, 60)
        try:
            with self.assertRaisesRegex(ValueError, 'existing alarm'):
                p.collect(self.binding, self.output)
            remaining, interval = signal.getitimer(signal.ITIMER_REAL)
            self.assertGreater(remaining, 50)
            self.assertEqual(interval, 0)
            self.assertEqual(signal.getsignal(signal.SIGALRM), previous_handler)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    def assert_actual_final_growth_rejected(self, phase):
        self.next_output('growth-' + phase)
        self.binding['allocation']['output_mib'] = 1
        original_write = p.write_new
        original_verify = p.verify_prerequisites
        def grow():
            self.write(self.output / 'injected-after-final-step', 'x' * (2 * p.MIB))
        def write(path, value):
            original_write(path, value)
            if path.name == phase:
                grow()
        def verify(**kwargs):
            result = original_verify(**kwargs)
            if phase == 'readback':
                grow()
            return result
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'managed_run', side_effect=self.command), \
                mock.patch.object(p, 'write_new', side_effect=write), \
                mock.patch.object(p, 'verify_prerequisites', side_effect=verify):
            with self.assertRaises((ValueError, RuntimeError, InterruptedError)):
                p.collect(self.binding, self.output)
        self.assertTrue((self.output / 'complete.json').exists())
        failure = p.read(self.output / 'failure.json')
        self.assertFalse(failure['complete'])
        self.assertIn('output limit', failure['driver_resource']['failure'])
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'):
            with self.assertRaises(ValueError):
                original_verify(gate_receipt=self.output / 'gate.json', gate_sha256=p.sha(self.output / 'gate.json'),
                    plans_dir=self.output / 'plans', plans_sha256=p.sha(self.output / 'plans/receipt.json'),
                    producer_receipt=self.binding['producer']['path'], producer_sha256=self.binding['producer']['sha256'],
                    source_root=self.root, source_checkpoint=self.binding['source_checkpoint'])

    def test_actual_budget_covers_final_seal_write(self):
        self.assert_actual_final_growth_rejected('complete.json')

    def test_actual_budget_covers_resource_record_write(self):
        self.assert_actual_final_growth_rejected('driver-resources-final.json')

    def test_actual_budget_covers_final_readback(self):
        self.assert_actual_final_growth_rejected('readback')


    def test_failure_record_survives_deferred_signals_after_monitor_stop(self):
        import threading
        self.next_output('signal-safe-failure')
        self.binding['allocation']['output_mib'] = 1
        monitor_waiting = threading.Event()
        budgets = []
        write = p.write_new
        before = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGALRM)}
        def load_with_barrier(expected=None):
            module = self.real_load_supervisor(expected)
            check = module.DriverBudget.check
            initialize = module.DriverBudget.__init__
            def init(budget, *args):
                initialize(budget, *args)
                budgets.append(budget)
            def delayed_check(budget):
                if threading.current_thread().name == 'bootstrap-driver-budget':
                    monitor_waiting.set()
                    self.assertTrue(budget.stop_event.wait(5), 'monitor not stopped before failure write')
                return check(budget)
            module.DriverBudget.__init__ = init
            module.DriverBudget.check = delayed_check
            return module
        def interrupted_write(path, value):
            if path.name == 'failure.json':
                self.assertTrue(budgets[0].stop_event.is_set())
                self.assertFalse(budgets[0].thread.is_alive())
                self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
                with path.open('x') as stream:
                    # Deferred notifications can already be pending when the
                    # monitor joins. They must not interrupt failure JSON I/O.
                    os.kill(os.getpid(), signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGALRM)
                    os.kill(os.getpid(), signal.SIGTERM)
                    stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
                return
            write(path, value)
            if path.name == 'complete.json':
                self.assertTrue(monitor_waiting.wait(2))
                (self.output / 'injected-growth').write_bytes(b'x' * (2 * p.MIB))
        with mock.patch.object(p, 'checkpoint'), mock.patch.object(p, 'authenticate_producer'), \
                mock.patch.object(p, 'managed_run', side_effect=self.command), \
                mock.patch.object(p, 'load_supervisor', side_effect=load_with_barrier), \
                mock.patch.object(p, 'write_new', side_effect=interrupted_write):
            with self.assertRaisesRegex(ValueError, 'driver cumulative output limit'):
                p.collect(self.binding, self.output)
        failure = p.read(self.output / 'failure.json')
        self.assertFalse(failure['complete'])
        self.assertIsNone(failure['monitor_stop_error'])
        self.assertIn('driver cumulative output limit', failure['error'])
        self.assertEqual({s: signal.getsignal(s) for s in before}, before)
        self.assertFalse((self.output / 'driver-resources-final.json').exists())

    def assert_first_signal_cancels_and_failure_is_parseable(self, signal_source):
        self.next_output('cancel-' + signal_source)
        self.binding['allocation']['output_mib'] = 1
        write = p.write_new
        def authentication(*args):
            if signal_source == 'direct':
                os.kill(os.getpid(), signal.SIGTERM)
            else:
                (self.output / 'injected-growth').write_bytes(b'x' * (2 * p.MIB))
                time.sleep(4)  # Actual monitor must interrupt this wait.
            self.fail('first cancellation did not interrupt authentication')
        def interrupt_failure_write(path, value):
            if path.name == 'failure.json':
                with path.open('x') as stream:
                    os.kill(os.getpid(), signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGALRM)
                    stream.write(json.dumps(value) + '\n')
            else:
                write(path, value)
        started = time.monotonic()
        with mock.patch.object(p, 'checkpoint'), \
                mock.patch.object(p, 'authenticate_producer', side_effect=authentication), \
                mock.patch.object(p, 'managed_run') as run, \
                mock.patch.object(p, 'write_new', side_effect=interrupt_failure_write):
            with self.assertRaises(InterruptedError):
                p.collect(self.binding, self.output)
        run.assert_not_called()
        self.assertLess(time.monotonic() - started, 3)
        failure = p.read(self.output / 'failure.json')
        self.assertFalse(failure['complete'])
        self.assertTrue(failure['error'].startswith('InterruptedError:'))
        self.assertIsNone(failure['monitor_stop_error'])

    def test_first_direct_signal_cancels_and_failure_json_survives_repeats(self):
        self.assert_first_signal_cancels_and_failure_is_parseable('direct')

    def test_first_monitor_signal_cancels_and_failure_json_survives_repeats(self):
        self.assert_first_signal_cancels_and_failure_is_parseable('monitor')


class GitCheckpointControls(unittest.TestCase):
    """Mock Git argv and fail-closed checks, not repository qualification."""
    def invoke(self, outputs):
        root = Path('/source-fixture')
        git = Path('/tool-fixture/git')
        env = {'LANG': 'C'}
        with mock.patch.object(p.subprocess, 'check_output', side_effect=outputs) as query:
            p.checkpoint(root, 'a' * 40, git, env)
        prefix = [str(git), '-c', 'core.preloadIndex=false', '-c', 'index.threads=1']
        self.assertEqual(query.call_args_list, [
            mock.call(prefix + ['rev-parse', '--show-toplevel'], cwd=root, env=env, text=True, timeout=15),
            mock.call(prefix + ['rev-parse', 'HEAD'], cwd=root, env=env, text=True, timeout=15),
            mock.call(prefix + ['status', '--porcelain', '--untracked-files=normal'], cwd=root, env=env, text=True, timeout=15),
        ])

    def test_exact_clean_identity_uses_serial_git_settings(self):
        self.invoke(['/source-fixture\n', 'a' * 40 + '\n', ''])

    def test_wrong_source_root_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'checkpoint is not exact and clean'):
            self.invoke(['/other-source\n'])

    def test_wrong_head_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'checkpoint is not exact and clean'):
            self.invoke(['/source-fixture\n', 'b' * 40 + '\n'])

    def test_tracked_modification_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'checkpoint is not exact and clean'):
            self.invoke(['/source-fixture\n', 'a' * 40 + '\n', ' M source.hs\n'])

    def test_untracked_file_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'checkpoint is not exact and clean'):
            self.invoke(['/source-fixture\n', 'a' * 40 + '\n', '?? extra.hs\n'])

    def test_git_error_is_not_treated_as_clean(self):
        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke([subprocess.CalledProcessError(128, ['/tool-fixture/git'])])

    def test_invalid_commit_rejected_before_git(self):
        with mock.patch.object(p.subprocess, 'check_output') as query:
            with self.assertRaisesRegex(ValueError, 'exact reviewed checkpoint required'):
                p.checkpoint(Path('/source-fixture'), 'not-a-commit', Path('/tool-fixture/git'), {})
            query.assert_not_called()


class PlanInventoryControls(unittest.TestCase):
    """Synthetic source/plan data with deliberately nonalphabetical declarations."""
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.manifest = self.root / 'mlf-package.json'
        def source(name, relative):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('module ' + name + ' where {}\n')
        def package(relative, name, module):
            directory = self.root / relative
            directory.mkdir()
            (directory / 'mlf-package.json').write_text(json.dumps({'format':1, 'name':name, 'version':'0.3.0',
                'library':{'modules':{module:'Module.hs'}}, 'dependencies':{}}))
            source(module, relative + '/Module.hs')
        package('a-dep', 'a-dep', 'Fixture.ADep')
        package('z-dep', 'z-dep', 'Fixture.ZDep')
        self.data = {'format':1, 'name':'fixture-root', 'version':'0.3.0',
            'library':{'modules':{'Fixture.Root':'Root.hs'}},
            'dependencies':{'z-dep':{'path':'z-dep'}, 'a-dep':{'path':'a-dep'}},
            'executables':{
                'z-run':{'main':'ZMain.hs', 'modules':{'Fixture.ZPrivate':'ZPrivate.hs'}, 'dependencies':['z-dep','a-dep']},
                'a-run':{'main':'AMain.hs', 'dependencies':[]}},
            'tests':{'z-command':{'command':['echo','synthetic']}, 'a-compiled':{'main':'Test.hs'}}}
        self.manifest.write_text(json.dumps(self.data))
        for name, relative in [('Fixture.Root','Root.hs'), ('Fixture.ZMain','ZMain.hs'),
                               ('Fixture.ZPrivate','ZPrivate.hs'), ('Fixture.AMain','AMain.hs'), ('Fixture.Test','Test.hs')]:
            source(name, relative)
        snapshot, _ = p.package_graph(self.root, self.manifest)
        (self.root / 'mlf.lock').write_text(json.dumps(snapshot))
        a, z, own = 'a-dep/0.3.0/library', 'z-dep/0.3.0/library', 'fixture-root/0.3.0/library'
        self.plan = copy.deepcopy(snapshot)
        self.plan.update(executables=['z-run','a-run'], tests=['z-command','a-compiled'],
            modules=['Fixture.ZDep','Fixture.ADep','Fixture.Root'], crates=[
                {'crate':a, 'entry':'', 'modules':['Fixture.ADep'], 'dependencies':[]},
                {'crate':z, 'entry':'', 'modules':['Fixture.ZDep'], 'dependencies':[]},
                {'crate':own, 'entry':'', 'modules':['Fixture.Root'], 'dependencies':[a,z]},
                {'crate':'fixture-root/0.3.0/target-z-run', 'entry':'Fixture.ZMain',
                 'modules':['Fixture.ZMain','Fixture.ZPrivate'], 'dependencies':[a,z,own]},
                {'crate':'fixture-root/0.3.0/target-a-run', 'entry':'Fixture.AMain',
                 'modules':['Fixture.AMain'], 'dependencies':[own]},
                {'crate':'fixture-root/0.3.0/target-test-a-compiled', 'entry':'Fixture.Test',
                 'modules':['Fixture.Test'], 'dependencies':[a,z,own]}])

    def reject_target(self, transform):
        for key in ('executables','tests'):
            with self.subTest(section=key):
                plan = copy.deepcopy(self.plan)
                plan[key] = transform(plan[key])
                with self.assertRaisesRegex(ValueError, 'plan target inventory mismatch'):
                    p.verify_plan(plan, self.root, self.manifest)

    def reject_plan(self, transform, error):
        plan = copy.deepcopy(self.plan); transform(plan)
        with self.assertRaisesRegex(ValueError, error):
            p.verify_plan(plan, self.root, self.manifest)

    def test_nonalphabetical_manifest_order_is_required(self):
        self.assertNotEqual(self.plan['executables'], sorted(self.plan['executables']))
        self.assertNotEqual(self.plan['tests'], sorted(self.plan['tests']))
        self.assertIn(str(self.manifest), p.verify_plan(self.plan, self.root, self.manifest))

    def test_missing_target_rejected(self):
        self.reject_target(lambda names: names[:-1])

    def test_extra_target_rejected(self):
        self.reject_target(lambda names: names + ['invented'])

    def test_duplicate_target_rejected(self):
        self.reject_target(lambda names: names + [names[0]])

    def test_same_length_duplicate_target_rejected(self):
        self.reject_target(lambda names: [names[0], names[0]])

    def test_alphabetically_sorted_target_array_rejected(self):
        self.reject_target(sorted)

    def test_wrong_target_array_order_rejected(self):
        self.reject_target(lambda names: list(reversed(names)))

    def test_wrong_target_array_type_rejected(self):
        self.reject_target(lambda names: {name:{} for name in names})

    def test_empty_target_sections_are_valid(self):
        self.data.pop('executables'); self.data.pop('tests')
        self.manifest.write_text(json.dumps(self.data))
        snapshot, _ = p.package_graph(self.root, self.manifest)
        (self.root / 'mlf.lock').write_text(json.dumps(snapshot))
        self.plan['packages'] = snapshot['packages']
        self.plan.update(executables=[], tests=[], crates=self.plan['crates'][:3])
        p.verify_plan(self.plan, self.root, self.manifest)

    def test_manifest_declaration_order_changes_expected_targets(self):
        self.data['executables'] = dict(reversed(list(self.data['executables'].items())))
        self.manifest.write_text(json.dumps(self.data))
        snapshot, _ = p.package_graph(self.root, self.manifest)
        (self.root / 'mlf.lock').write_text(json.dumps(snapshot)); self.plan['packages'] = snapshot['packages']
        with self.assertRaisesRegex(ValueError, 'plan target inventory mismatch'):
            p.verify_plan(self.plan, self.root, self.manifest)
        self.plan['executables'].reverse()
        p.verify_plan(self.plan, self.root, self.manifest)

    def test_duplicate_manifest_target_key_is_rejected(self):
        raw = self.manifest.read_text().replace('"z-run":', '"a-run":', 1)
        self.manifest.write_text(raw)
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            p.verify_plan(self.plan, self.root, self.manifest)

    def test_missing_package_rejected(self):
        self.reject_plan(lambda plan: plan['packages'].pop(), 'plan package/source snapshot mismatch')

    def test_duplicate_package_rejected(self):
        self.reject_plan(lambda plan: plan['packages'].__setitem__(1,plan['packages'][0]), 'plan package/source snapshot mismatch')

    def test_missing_crate_rejected(self):
        self.reject_plan(lambda plan: plan['crates'].pop(), 'plan crate/module/dependency mismatch')

    def test_duplicate_crate_rejected(self):
        self.reject_plan(lambda plan: plan['crates'].__setitem__(1,plan['crates'][0]), 'plan crate/module/dependency mismatch')

    def test_crate_module_order_is_still_sorted(self):
        self.reject_plan(lambda plan: plan['crates'][3]['modules'].reverse(), 'plan crate/module/dependency mismatch')

    def test_crate_dependency_order_is_still_sorted_then_own_library(self):
        self.reject_plan(lambda plan: plan['crates'][3]['dependencies'].reverse(), 'plan crate/module/dependency mismatch')

    def test_duplicate_top_level_module_rejected(self):
        self.reject_plan(lambda plan: plan['modules'].__setitem__(1,plan['modules'][0]), 'plan module inventory mismatch')

    def test_missing_top_level_module_rejected(self):
        self.reject_plan(lambda plan: plan['modules'].pop(), 'plan module inventory mismatch')

    def test_top_level_modules_remain_an_exact_inventory_not_a_sorted_array(self):
        self.plan['modules'].reverse()
        p.verify_plan(self.plan, self.root, self.manifest)


@unittest.skipUnless(os.environ.get('MLF_PREREQUISITE_PLAN_SOURCE_ROOT'),
                     'full retained-plan readback requires explicit original source root')
class RetainedActualPlanControls(unittest.TestCase):
    """Read-only regression using exact bytes from an actual failed collection.

    This revalidates one retained plan, not the failed collector as a whole.
    It never invokes a manager/compiler or manufactures replacement receipts.
    """
    def setUp(self):
        self.root = Path(os.environ['MLF_PREREQUISITE_PLAN_SOURCE_ROOT']).resolve(strict=True)
        fixtures = Path(__file__).with_name('fixtures') / 'ghc-prerequisites'
        self.plan_path = fixtures / 'root-plan-attempt1.json'
        self.provenance = p.read(fixtures / 'root-plan-attempt1-provenance.json')
        self.assertEqual(p.sha(self.plan_path), self.provenance['sha256'])
        self.assertEqual(p.sha(self.root / 'mlf-package.json'), self.provenance['root_manifest_sha256'])
        self.plan = p.read(self.plan_path)

    def test_actual_root_plan_full_inventory_and_snapshot_readback(self):
        inputs = p.verify_plan(self.plan, self.root, self.root / 'mlf-package.json')
        self.assertEqual(len(inputs), 141)
        self.assertFalse(self.provenance['overall_attempt_complete'])
        self.assertEqual(self.provenance['overall_attempt_exit'], 1)

    def test_old_sorted_target_requirement_reproduces_actual_rejection(self):
        manifest = p.read(self.root / 'mlf-package.json')
        for key in ('executables','tests'):
            self.assertEqual(self.plan[key], list(manifest[key]))
            self.assertNotEqual(self.plan[key], sorted(manifest[key]))
        with self.assertRaisesRegex(ValueError, 'plan target inventory mismatch'):
            p.require(self.plan['executables'] == sorted(manifest['executables']) and
                      self.plan['tests'] == sorted(manifest['tests']), 'plan target inventory mismatch')

    def test_retained_real_targets_reject_missing_extra_duplicate_and_reordered(self):
        for key in ('executables','tests'):
            for name, change in [('missing',lambda x:x[:-1]), ('extra',lambda x:x+['invented']),
                                 ('duplicate',lambda x:x+[x[0]]), ('sorted',sorted), ('reverse',lambda x:x[::-1])]:
                with self.subTest(section=key, mutation=name):
                    plan = copy.deepcopy(self.plan); plan[key] = change(plan[key])
                    with self.assertRaisesRegex(ValueError, 'plan target inventory mismatch'):
                        p.verify_plan(plan, self.root, self.root / 'mlf-package.json')


class ActualSupervisorControls(unittest.TestCase):
    """Real small Python process trees; no GHC/manager/compiler/native binaries."""
    def run_case(self, timeout):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            pid_path = root / 'child.pid'
            child = ("import os,signal,time,json; from pathlib import Path; "
                     "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                     "Path(" + repr(str(pid_path)) + ").write_text(json.dumps({'pid':os.getpid(),'start':Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()[19]})); "
                     "time.sleep(30)")
            parent = ("import subprocess,sys,time; from pathlib import Path; "
                      "subprocess.Popen([sys.executable,'-B','-c'," + repr(child) + "],start_new_session=True); "
                      "time.sleep(" + ('30' if timeout else '0.8') + "); sys.exit(7)")
            teardown = {}
            try:
                with (root / 'wrapper.log').open('xb') as log:
                    with self.assertRaises(subprocess.TimeoutExpired if timeout else ValueError):
                        p.managed_run([sys.executable, '-B', '-c', parent], cwd=root, env=dict(os.environ),
                                      stdout=log, timeout=1 if timeout else 5, teardown=teardown,
                                      supervisor=p.identity(p.ROOT / 'tools/shared/bootstrap_ghc_native.py'))
                self.assertTrue(teardown['drained'])
                self.assertEqual(teardown['remaining'], [])
                self.assertTrue(teardown['initial'])
                self.assertTrue(all('start_time' in row for row in teardown['initial']))
                child_identity = json.loads(pid_path.read_text())
                child_pid = child_identity['pid']
                stat_path = Path('/proc') / str(child_pid) / 'stat'
                if stat_path.exists():
                    row = stat_path.read_text().rsplit(') ', 1)[1].split()
                    if row[19] == child_identity['start']:
                        self.assertEqual(row[0], 'Z')
            finally:
                # Do not leave a tiny fixture child alive even if an assertion fails.
                if pid_path.exists():
                    try:
                        child_identity = json.loads(pid_path.read_text())
                        stat_path = Path('/proc') / str(child_identity['pid']) / 'stat'
                        row = stat_path.read_text().rsplit(') ', 1)[1].split()
                        if row[19] == child_identity['start'] and row[0] != 'Z':
                            os.kill(child_identity['pid'], signal.SIGKILL)
                    except (ProcessLookupError, FileNotFoundError):
                        pass

    def test_abnormal_watchdog_exit_drains_independent_child(self):
        self.run_case(False)

    def test_watchdog_timeout_drains_independent_child(self):
        self.run_case(True)


if __name__ == '__main__':
    unittest.main()
