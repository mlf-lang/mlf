#!/usr/bin/env python3
"""Light control tests for direct-source provenance. No GHC/native codegen runs."""
import copy
import hashlib
import importlib.util
import json
import re
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/shared' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build, direct = load('build'), load('test_direct')


class FrontendExecutionBudget(unittest.TestCase):
    def test_authenticated_o0_budget_is_bounded(self):
        self.assertEqual(direct.frontend_timeout_seconds('0'), 1800)

    def test_o2_budget_is_unchanged(self):
        self.assertEqual(direct.frontend_timeout_seconds('2'), 120)

    def test_ci_only_expands_o0_job_budget(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        shared_job = workflow.split('  native:\n', 1)[1].split('\n  native-', 1)[0]
        self.assertIn("timeout-minutes: ${{ matrix.optimization == '0' && 330 || 120 }}", shared_job)
        self.assertIn("optimization: ['0', '2']", shared_job)

    def test_ci_uses_one_authenticated_tuple_suite_owner(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        shared_job = workflow.split('  native:\n', 1)[1].split('\n  native-', 1)[0]
        self.assertEqual(shared_job.count('python3 tools/shared/test_framework_direct.py '), 1)
        self.assertNotIn('bin/tuple-list |', shared_job)
        self.assertNotIn('bin/tuple-list --', shared_job)
        timeout = re.search(r"timeout-minutes: \$\{\{ matrix.optimization == '0' && (\d+) \|\| (\d+) \}\}", shared_job)
        self.assertIsNotNone(timeout)
        self.assertEqual(tuple(map(int, timeout.groups())), (330, 120))
        self.assertLessEqual(max(map(int, timeout.groups())), 360)

    def test_unknown_or_untyped_optimization_is_rejected(self):
        for value in ['1', '', None, 0, 2, False, {}, {'optimization': '0'}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                direct.frontend_timeout_seconds(value)


class ManifestParity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mlf-parity-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        manifest = json.loads((ROOT / 'shared-sources.json').read_text())
        paths = {x['path'] for x in manifest['modules']} | set(manifest['host_only'])
        paths |= {'shared-sources.json', 'mlf-shared.cabal', 'mlf-package.json',
                  'tests/mlf-package.json', 'tests/shared/mlf-package.json',
                  'testing/mlf-package.json', 'testing/tools/mlf-package.json'}
        paths |= {str(p.relative_to(ROOT)) for p in ROOT.glob('libraries/*/mlf-package.json')}
        for path in paths:
            destination = self.root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, destination)

    def check(self):
        with patch.object(build, 'ROOT', self.root):
            return build.load_manifest()

    def mutate_json(self, path, mutation):
        path = self.root / path
        data = json.loads(path.read_text())
        mutation(data)
        path.write_text(json.dumps(data))

    def test_closed_corpus_has_matching_106_modules_12_executables(self):
        manifest = self.check()
        self.assertEqual(len(manifest['modules']), 106)
        modules = {entry['module']: entry for entry in manifest['modules']}
        for name, path in (
            ('Bootstrap.Standalone', 'libraries/mlf-frontend/Bootstrap/Standalone.hs'),
            ('Bootstrap.EvidenceBoundary', 'libraries/mlf-inference/Bootstrap/EvidenceBoundary.hs'),
            ('Bootstrap.SourceInference', 'libraries/mlf-crates/Bootstrap/SourceInference.hs'),
        ):
            self.assertEqual(modules[name], {
                'module': name, 'path': path, 'role': 'implementation',
            })
        self.assertEqual(len(manifest['executables']), 12)

    def test_cabal_wrong_wrapper_rejected(self):
        path = self.root / 'mlf-shared.cabal'
        path.write_text(path.read_text().replace('hs-source-dirs: host/ghc/app/emlf', 'hs-source-dirs: host/ghc/app/mlfpkg'))
        with self.assertRaisesRegex(RuntimeError, 'different wrapper'):
            self.check()

    def test_cabal_wrong_main_rejected(self):
        path = self.root / 'mlf-shared.cabal'
        path.write_text(path.read_text().replace('main-is: Main.hs', 'main-is: Other.hs', 1))
        with self.assertRaisesRegex(RuntimeError, 'different wrapper'):
            self.check()

    def test_wrapper_wrong_entry_rejected(self):
        path = self.root / 'host/ghc/app/emlf/Main.hs'
        path.write_text(path.read_text().replace('MLF.Entry.Emlf', 'MLF.Entry.Mlfpkg'))
        with self.assertRaisesRegex(RuntimeError, 'declared shared entry'):
            self.check()

    def test_native_wrong_entry_rejected(self):
        self.mutate_json('mlf-package.json', lambda x: x['executables']['emlf'].update(main='package/MLF/Entry/Mlfpkg.hs'))
        with self.assertRaisesRegex(RuntimeError, 'executable entry disagrees|closed module inventories'):
            self.check()

    def test_native_wrong_module_path_rejected(self):
        self.mutate_json('libraries/mlf-foundation/mlf-package.json',
                         lambda x: x['library']['modules'].update({'Bootstrap.Types': 'Bootstrap/Std.hs'}))
        with self.assertRaisesRegex(RuntimeError, 'module path disagrees'):
            self.check()

    def test_native_frontend_inference_and_runtime_dependencies_required(self):
        self.mutate_json('tests/shared/mlf-package.json',
                         lambda x: x['executables']['shared-frontend'].update(dependencies=['mlf-foundation', 'mlf-frontend']))
        with self.assertRaisesRegex(RuntimeError, 'direct dependency visibility omits imports'):
            self.check()

    def test_target_transitive_only_frontend_import_rejected(self):
        # Crates/inference still depend on frontend, but the entry cannot import
        # its modules unless frontend is a selected direct dependency itself.
        self.mutate_json('mlf-package.json',
                         lambda x: x['executables']['emlf']['dependencies'].remove('mlf-frontend'))
        with self.assertRaisesRegex(RuntimeError, r'MLF\.Entry\.Emlf: .*Bootstrap\.Parser'):
            self.check()

    def test_library_transitive_only_frontend_import_rejected(self):
        # Inference -> xmlf -> frontend must not grant inference frontend imports.
        self.mutate_json('libraries/mlf-inference/mlf-package.json',
                         lambda x: x['dependencies'].pop('mlf-frontend'))
        with self.assertRaisesRegex(RuntimeError, 'direct dependency visibility omits imports'):
            self.check()

    def test_target_omitted_selection_defaults_to_all_direct_dependencies(self):
        self.mutate_json('mlf-package.json', lambda x: x['executables']['emlf'].pop('dependencies'))
        self.check()

    def test_target_empty_selection_does_not_mean_all_dependencies(self):
        self.mutate_json('mlf-package.json', lambda x: x['executables']['emlf'].update(dependencies=[]))
        with self.assertRaisesRegex(RuntimeError, r'MLF\.Entry\.Emlf:'):
            self.check()

    def test_target_duplicate_dependency_rejected(self):
        self.mutate_json('mlf-package.json',
                         lambda x: x['executables']['emlf']['dependencies'].append('mlf-frontend'))
        with self.assertRaisesRegex(RuntimeError, 'duplicate dependency'):
            self.check()

    def test_target_selection_does_not_restrict_own_library_dependencies(self):
        # A target can import its own library without selecting that library's
        # dependencies. Each library module is checked in its package scope.
        source = self.root / 'bootstrap/MLF/Entry/Emlf.hs'
        source.write_text('-- mlf:syntax shared-haskell-v1\nmodule MLF.Entry.Emlf where {\n'
                          '  import Bootstrap.Crate;\n}\n')
        self.mutate_json('libraries/mlf-crates/mlf-package.json',
                         lambda x: x.update(executables={'local-library-probe': {
                             'main': '../../bootstrap/MLF/Entry/Emlf.hs', 'dependencies': []}}))
        self.check()

    def test_missing_native_module_rejected(self):
        self.mutate_json('libraries/mlf-foundation/mlf-package.json', lambda x: x['library']['modules'].pop('Bootstrap.Fresh'))
        with self.assertRaisesRegex(RuntimeError, 'closed module inventories'):
            self.check()

    def test_missing_rts_argv_flag_rejected(self):
        path = self.root / 'mlf-shared.cabal'
        path.write_text(path.read_text().replace('-rtsopts=ignoreAll', '', 1))
        with self.assertRaisesRegex(RuntimeError, 'contract flags'):
            self.check()


class InferredSchemeEvidence(unittest.TestCase):
    def log(self, name, schemes):
        return ('[1 of 1] Compiling ' + name + ' ( Example.hs, nothing )\n' + schemes +
                'Dependent modules: []\n!!! Renamer/typechecker [' + name + ']: finished in 1.0 milliseconds\n')

    def test_absent_dump_fails_closed(self):
        with self.assertRaises(RuntimeError):
            build.audit_inferred_interfaces('[1 of 1] Compiling Example ( Example.hs, nothing )\n', {'Example': {}})

    def test_value_module_needs_schemes(self):
        with self.assertRaises(RuntimeError):
            build.audit_inferred_interfaces(self.log('Example', ''), {'Example': {}})

    def test_literal_polymorphism_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'unresolved host literal'):
            build.audit_inferred_interfaces(self.log('Example', 'TYPE SIGNATURES\n  value :: Num a => a\n'), {'Example': {}})

    def test_actual_monomorphic_scheme_accepted(self):
        result = build.audit_inferred_interfaces(self.log('Example', 'TYPE SIGNATURES\n  value :: Int\n'), {'Example': {}})
        self.assertIn('value :: Int', result['Example']['signatures'])

    def test_explicit_datatype_only_module_accepted(self):
        name = 'Bootstrap.Types'
        result = build.audit_inferred_interfaces(self.log(name, 'TYPE CONSTRUCTORS\n  data Unit\n'), {name: {}})
        self.assertEqual(result[name]['signatures'], '')


class ProducerPreflight(unittest.TestCase):
    def test_failed_preflight_invalidates_previous_success(self):
        with tempfile.TemporaryDirectory(prefix='mlf-preflight-control-') as temporary:
            output = Path(temporary)
            (output / 'receipt.json').write_text('{"complete":true}')
            with patch.object(sys, 'argv', ['build.py', '--build-dir', str(output)]), patch.object(
                    build, 'load_manifest', side_effect=RuntimeError('injected invalid manifest')):
                with self.assertRaisesRegex(RuntimeError, 'injected invalid manifest'):
                    build.main()
            receipt = json.loads((output / 'receipt.json').read_text())
            self.assertIs(receipt['complete'], False)
            self.assertEqual(receipt['phase'], 'preflight')


class InstalledClosure(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mlf-package-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.interfaces, self.libraries = self.root / 'interfaces', self.root / 'libraries'
        self.interfaces.mkdir()
        self.libraries.mkdir()
        (self.interfaces / 'Base.hi').write_text('interface fixture')
        (self.libraries / 'libHSbase.a').write_text('archive fixture')
        self.dump = ('name: base\nid: base-1\npkgroot: ' + str(self.root) + '\nimport-dirs: ' + str(self.interfaces) +
                     '\nlibrary-dirs: ' + str(self.libraries) + '\nhs-libraries: HSbase\n')

    def test_complete_interface_and_archive_are_bound(self):
        result = build.package_inputs(self.dump, ['base'])
        self.assertEqual(result['packages'], ['base-1'])
        self.assertEqual(set(result['files']), {str(self.interfaces / 'Base.hi'), str(self.libraries / 'libHSbase.a')})

    def test_missing_library_directory_rejected(self):
        shutil.rmtree(self.libraries)
        with self.assertRaisesRegex(RuntimeError, 'missing package library directory'):
            build.package_inputs(self.dump, ['base'])

    def test_missing_library_archive_rejected(self):
        (self.libraries / 'libHSbase.a').unlink()
        with self.assertRaisesRegex(RuntimeError, 'missing installed package library'):
            build.package_inputs(self.dump, ['base'])


class DirectProducerReceipt(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mlf-direct-receipt-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.bin = self.root / 'build/bin'
        self.bin.mkdir(parents=True)
        self.receipt_path = self.root / 'build/receipt.json'
        manifest = {'source_syntax': 'shared-haskell-v1', 'frontend_semantics': 'test/2',
                    'builtin_interface': 'test/3', 'primitive_abi': 'test/95',
                    'modules': [{'module': 'Example', 'path': 'source/Example.hs'}],
                    'host_only': ['host/ghc/MLF/Primitive.hs', 'host/ghc/MLF/Host/Base.hs', 'host/ghc/MLF/Host/IO.hs', 'host/ghc/MLF/Host/Async.hs', 'runtime/mlf_process_supervisor.c'],
                    'executables': [{'name': 'probe', 'module': 'Example'}]}
        self.file('shared-sources.json', json.dumps(manifest))
        module = self.file('source/Example.hs')
        hosts = {name: self.file(path) for name, path in {'MLF.Primitive': 'host/ghc/MLF/Primitive.hs', 'MLF.Host.Base': 'host/ghc/MLF/Host/Base.hs', 'MLF.Host.IO': 'host/ghc/MLF/Host/IO.hs', 'MLF.Host.Async': 'host/ghc/MLF/Host/Async.hs'}.items()}
        runtime = self.file('runtime/mlf_process_supervisor.c')
        self.file('build/packages.txt')
        self.file('build/ghc-info.txt')
        self.file('build/bin/probe')
        log = self.file('build/compile.log')
        dependency = self.file('installed/base.hi')
        audit = '  value :: Int\n'
        self.receipt = {'complete': True, 'typecheck_only': False, 'producer_host': 'GHC',
            'implementation_identity': 'MLF/shared-haskell-v1 GHC', 'optimization': '0',
            'flags': ['-fpedantic-bottoms', '-fno-state-hack', '-clear-package-db', '-global-package-db', '-no-user-package-db'], **{x: manifest[x] for x in
                ['source_syntax', 'frontend_semantics', 'builtin_interface', 'primitive_abi']},
            'manifest_sha256': direct.sha(self.root / 'shared-sources.json'),
            'shared_inputs': {'Example': direct.identified(module)},
            'resolved_modules': {'Example': direct.identified(module)},
            'inferred_shared_interfaces': {'Example': {'signatures': audit,
                'sha256': hashlib.sha256(audit.encode()).hexdigest(), 'unresolved_literal_constraints': False}},
            'host_inputs': {**{str(path.relative_to(self.root)): direct.identified(path) for path in hosts.values()}, 'runtime/mlf_process_supervisor.c': direct.identified(runtime)},
            'resolved_host_modules': {name: direct.identified(path) for name, path in hosts.items()},
            'installed_dependencies': {'files': {str(dependency): direct.sha(dependency)}},
            'package_database_sha256': direct.sha(self.root / 'build/packages.txt'),
            'ghc_info_sha256': direct.sha(self.root / 'build/ghc-info.txt'),
            'outputs': {'probe': direct.identified(self.bin / 'probe')},
            'commands': [{'exit_code': 0, 'log': str(log), 'log_sha256': direct.sha(log)}]}
        for name, relative in [('ghc', 'tools/ghc'), ('cc', 'tools/cc'), ('orchestrator', 'tools/python'),
                               ('build_driver', 'tools/shared/build.py'), ('cabal_manifest', 'mlf-shared.cabal'),
                               ('ghc_settings', 'installed/settings')]:
            self.receipt[name] = direct.identified(self.file(relative))
        configs = ['cabal.project', 'mlf-shared.cabal', 'shared-sources.json', 'mlf-package.json',
                   'tests/mlf-package.json', 'tests/shared/mlf-package.json', 'testing/mlf-package.json',
                   'testing/tools/mlf-package.json']
        for relative in configs:
            if not (self.root / relative).exists():
                self.file(relative)
        self.receipt['configuration_inputs'] = {relative: direct.identified(self.root / relative) for relative in configs}
        self.receipt['ghc']['version'] = '9.14.1'
        actual = self.file('tools/private-ghc')
        self.receipt['toolchain'] = {'actual_ghc': direct.identified(actual), 'files': {str(actual): direct.sha(actual)}}

    def file(self, relative, contents='fixture\n'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        return path

    def check(self):
        self.receipt_path.write_text(json.dumps(self.receipt))
        return direct.authenticate_build(self.receipt_path, self.bin, self.root)

    def test_valid_receipt(self):
        self.assertTrue(self.check()['complete'])

    def test_incomplete_and_typecheck_receipts_rejected(self):
        for field, value in [('complete', False), ('typecheck_only', True)]:
            original = self.receipt[field]
            self.receipt[field] = value
            with self.assertRaises(ValueError):
                self.check()
            self.receipt[field] = original

    def test_old_or_unrelated_binary_rejected(self):
        self.file('build/bin/probe', 'different binary\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.check()

    def test_current_source_cannot_relabel_old_binary(self):
        self.file('source/Example.hs', 'new source\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.check()

    def test_missing_actual_resolution_rejected(self):
        self.receipt['resolved_modules'] = {}
        with self.assertRaisesRegex(ValueError, 'module inventory'):
            self.check()

    def test_missing_host_inventory_rejected(self):
        self.receipt['host_inputs'] = {}
        with self.assertRaisesRegex(ValueError, 'host inventory'):
            self.check()

    def test_tool_mutation_rejected(self):
        self.file('tools/cc', 'changed compiler\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.check()

    def test_native_configuration_mutation_rejected(self):
        self.file('tests/shared/mlf-package.json', 'changed dependency selection\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.check()

    def test_actual_compiler_mutation_rejected(self):
        self.file('tools/private-ghc', 'changed compiler engine\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.check()

    def test_missing_host_resolution_rejected(self):
        self.receipt['resolved_host_modules'] = {}
        with self.assertRaisesRegex(ValueError, 'host module resolution'):
            self.check()

    def test_installed_dependency_mutation_rejected(self):
        self.file('installed/base.hi', 'changed interface\n')
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.check()

    def test_producer_command_failure_rejected(self):
        self.receipt['commands'][0]['exit_code'] = 1
        with self.assertRaisesRegex(ValueError, 'finish every command'):
            self.check()

    def test_native_aggregate_is_not_direct_source_proof(self):
        self.receipt['producer_host'] = 'native-MLF'
        with self.assertRaisesRegex(ValueError, 'native aggregate reports'):
            self.check()


class CommandEvidence(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mlf-command-control-')
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.receipt = {'complete': False, 'commands': []}
        self.saves = []
        self.runner = direct.CommandRunner(self.output, self.output, self.receipt,
                                          lambda: self.saves.append(copy.deepcopy(self.receipt)))

    def test_attempt_logged_before_launch_failure(self):
        with self.assertRaises(FileNotFoundError):
            self.runner.run('missing', [self.output / 'missing'])
        self.assertEqual(self.saves[0]['commands'][0]['state'], 'running')
        self.assertEqual(self.receipt['commands'][0]['state'], 'failed')
        self.assertTrue((self.output / 'missing.stdout').is_file())

    def test_timeout_retains_command_and_partial_streams(self):
        with self.assertRaisesRegex(RuntimeError, 'exceeded'):
            self.runner.run('timeout', [sys.executable, '-c',
                'import sys,time; print("partial",flush=True); print("diagnostic",file=sys.stderr,flush=True); time.sleep(30)'], timeout=0.2)
        self.assertEqual((self.output / 'timeout.stdout').read_bytes(), b'partial\n')
        self.assertEqual((self.output / 'timeout.stderr').read_bytes(), b'diagnostic\n')
        entry = self.receipt['commands'][0]
        self.assertTrue(entry['timed_out'])
        self.assertEqual(entry['state'], 'failed')
        self.assertLess(entry['seconds'], 5)

    def test_success_checks_exact_stdout(self):
        self.runner.run('success', [sys.executable, '-c', 'print("okay")'], expected=b'okay\n')
        self.assertEqual(self.receipt['commands'][0]['state'], 'passed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
