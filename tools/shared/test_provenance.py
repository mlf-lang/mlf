#!/usr/bin/env python3
"""Light control tests for direct-source provenance. No GHC/native codegen runs."""
import copy
import contextlib
import io
import types
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/shared' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build, direct = load('build'), load('test_direct')
builtin_controls = load('test_builtin_prelude_verification')
# Keep these finite failure controls on the existing release metadata gate.
BuiltinPreludeVerification = builtin_controls.BuiltinPreludeVerification


class FrontendExecutionBudget(unittest.TestCase):
    # Preserve upstream's authenticated-budget and untyped-input controls while
    # reconciling its serial job with the reviewed per-mode parallel partition.
    def test_authenticated_o0_budget_is_bounded(self):
        self.assertEqual(direct.frontend_case_timeout('frontend', '0'), 3600)
        self.assertEqual(direct.frontend_case_timeout('native-first', '0'), 1800)
        self.assertEqual(direct.frontend_case_timeout('native-second', '0'), 1200)

    def test_o2_budgets_have_only_the_reviewed_native_first_margin(self):
        self.assertEqual(direct.frontend_case_timeout('frontend', '2'), 1200)
        self.assertEqual(direct.frontend_case_timeout('native-first', '2'), 180)
        self.assertEqual(direct.frontend_case_timeout('native-second', '2'), 120)

    def test_ci_partitions_o0_with_bounded_jobs(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        shared_job = workflow.split('  native:\n', 1)[1].split('  build-runner:', 1)[0]
        self.assertIn('timeout-minutes: 120', shared_job)
        for suite in ['direct', 'default', 'framework']:
            self.assertIn("optimization: '0'\n            suite: " + suite, shared_job)
        self.assertIn("optimization: '2'\n            suite: all", shared_job)

    def test_ci_uses_one_authenticated_tuple_suite_owner(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text()
        shared_job = workflow.split('  native:\n', 1)[1].split('  build-runner:', 1)[0]
        self.assertEqual(shared_job.count('python3 tools/shared/test_framework_direct.py '), 1)
        self.assertNotIn('bin/tuple-list |', shared_job)
        self.assertNotIn('bin/tuple-list --', shared_job)
        # The measured upstream serial budget is represented by three bounded
        # O0 shards here, not by stacking a 330-minute timeout onto each shard.
        self.assertEqual(shared_job.count('timeout-minutes: 120'), 1)
        self.assertNotIn('330', shared_job)

    def test_unknown_or_untyped_optimization_is_rejected(self):
        for value in ['1', '', None, 0, 2, False, {}, {'optimization': '0'}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                direct.frontend_case_timeout('frontend', value)


class ManifestParity(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mlf-parity-control-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
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

    def test_closed_corpus_has_matching_121_modules_13_executables(self):
        manifest = self.check()
        self.assertEqual(len(manifest['modules']), 121)
        modules = {entry['module']: entry for entry in manifest['modules']}
        self.assertEqual(len(modules), 121)
        for name, path, role in (
            ('Bootstrap.ClassDemand', 'libraries/mlf-inference/Bootstrap/ClassDemand.hs', 'implementation'),
            ('MLF.Tests.ClassDemand', 'tests/shared/MLF/Tests/ClassDemand.hs', 'direct-test'),
            ('Bootstrap.Standalone', 'libraries/mlf-frontend/Bootstrap/Standalone.hs', 'implementation'),
            ('Bootstrap.EvidenceBoundary', 'libraries/mlf-inference/Bootstrap/EvidenceBoundary.hs', 'implementation'),
            ('Bootstrap.SourceInference', 'libraries/mlf-crates/Bootstrap/SourceInference.hs', 'implementation'),
            ('Bootstrap.BuiltinPreludeContext', 'libraries/mlf-crates/Bootstrap/BuiltinPreludeContext.hs', 'implementation'),
            ('Bootstrap.BuiltinPreludeLiteral', 'libraries/mlf-crates/Bootstrap/BuiltinPreludeLiteral.hs', 'implementation'),
            ('Bootstrap.ImportParameters', 'libraries/mlf-crates/Bootstrap/ImportParameters.hs', 'implementation'),
            ('Bootstrap.ImportedRoot', 'libraries/mlf-crates/Bootstrap/ImportedRoot.hs', 'implementation'),
            ('Bootstrap.PreparedLibraries', 'libraries/mlf-crates/Bootstrap/PreparedLibraries.hs', 'implementation'),
            ('Bootstrap.PreparedLibraryLiteral', 'libraries/mlf-crates/Bootstrap/PreparedLibraryLiteral.hs', 'implementation'),
            ('MLF.BuiltinPreludeData', 'bootstrap/MLF/BuiltinPreludeData.hs', 'implementation'),
            ('MLF.Entry.BuiltinPrelude', 'bootstrap/MLF/Entry/BuiltinPrelude.hs', 'implementation'),
            ('MLF.PreparedCompiler', 'bootstrap/MLF/PreparedCompiler.hs', 'implementation'),
            ('MLF.PreparedLibraryData', 'bootstrap/MLF/PreparedLibraryData.hs', 'implementation'),
        ):
            self.assertEqual(modules[name], {
                'module': name, 'path': path, 'role': role,
            })
        self.assertEqual(len(manifest['executables']), 13)
        self.assertEqual(next(entry for entry in manifest['executables'] if entry['name'] == 'builtin-prelude'), {
            'name': 'builtin-prelude', 'module': 'MLF.Entry.BuiltinPrelude',
            'wrapper': 'host/ghc/app/builtin-prelude/Main.hs',
        })

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
        # Crates/inference still depend on frontend, but owned target modules
        # cannot import it without a selected direct dependency. The generated
        # builtin data is now the first owned module requiring frontend.
        self.mutate_json('mlf-package.json',
                         lambda x: x['executables']['emlf']['dependencies'].remove('mlf-frontend'))
        with self.assertRaisesRegex(RuntimeError,
                r'^native direct dependency visibility omits imports for MLF\.BuiltinPreludeData: Bootstrap\.Module$'):
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
        with self.assertRaisesRegex(RuntimeError,
                r'^native direct dependency visibility omits imports for MLF\.BuiltinPreludeData: '
                r'Bootstrap\.BuiltinPreludeContext, Bootstrap\.CrateArtifact, Bootstrap\.Module, Bootstrap\.SourceInference$'):
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
        self.root = Path(self.temporary.name).resolve()
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
        self.root = Path(self.temporary.name).resolve()
        self.builtin = builtin_controls.BuiltinFixture(self.root)
        self.bin = self.root / 'build/bin'
        self.receipt_path = self.root / 'build/receipt.json'
        manifest = copy.deepcopy(self.builtin.manifest)
        manifest['host_only'] = ['host/ghc/MLF/Primitive.hs', 'host/ghc/MLF/Host/Base.hs',
            'host/ghc/MLF/Host/IO.hs', 'host/ghc/MLF/Host/Async.hs', 'runtime/mlf_process_supervisor.c']
        manifest['executables'].append({'name': 'probe', 'module': 'Example'})
        self.file('shared-sources.json', json.dumps(manifest))
        modules = {row['module']: self.root / row['path'] for row in manifest['modules']}
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
            'shared_inputs': {name: direct.identified(path) for name, path in modules.items()},
            'resolved_modules': {name: direct.identified(path) for name, path in modules.items()},
            'inferred_shared_interfaces': {name: {'signatures': audit,
                'sha256': hashlib.sha256(audit.encode()).hexdigest(), 'unresolved_literal_constraints': False}
                for name in modules},
            'host_inputs': {**{str(path.relative_to(self.root)): direct.identified(path) for path in hosts.values()}, 'runtime/mlf_process_supervisor.c': direct.identified(runtime)},
            'resolved_host_modules': {name: direct.identified(path) for name, path in hosts.items()},
            'installed_dependencies': {'files': {str(dependency): direct.sha(dependency)}},
            'package_database_sha256': direct.sha(self.root / 'build/packages.txt'),
            'ghc_info_sha256': direct.sha(self.root / 'build/ghc-info.txt'),
            'outputs': {row['name']: direct.identified(self.bin / row['name']) for row in manifest['executables']},
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
        self.receipt['builtin_verification_helpers'] = {
            name: direct.identified(self.root / name) for name in builtin_controls.verifier.HELPERS}
        self.receipt['builtin_verification'] = direct.identified(self.builtin.verify())

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

    def test_missing_builtin_evidence_and_helper_inventory_are_rejected(self):
        for name in ['builtin_verification', 'builtin_verification_helpers']:
            original = self.receipt.pop(name)
            try:
                with self.subTest(field=name), self.assertRaises(ValueError):
                    self.check()
            finally:
                self.receipt[name] = original

    def test_rehashed_but_incomplete_builtin_evidence_is_rejected(self):
        path = Path(self.receipt['builtin_verification']['path'])
        receipt = json.loads(path.read_text())
        receipt['complete'] = False
        path.write_text(json.dumps(receipt))
        self.receipt['builtin_verification'] = direct.identified(path)
        with self.assertRaisesRegex(ValueError, 'complete builtin verification receipt required'):
            self.check()

    def test_old_builtin_receipt_cannot_authenticate_relabelled_new_binary(self):
        self.file('build/bin/emlf', 'different binary\n')
        self.receipt['outputs']['emlf'] = direct.identified(self.bin / 'emlf')
        with self.assertRaisesRegex(ValueError, 'builtin verification input inventory mismatch: compiler'):
            self.check()


class FrontendTimeoutSelection(unittest.TestCase):
    def run_dispatch(self, extra, optimization="2"):
        # Exercise the real CLI/default and dispatch loop, not a copied timeout
        # expression. Mock process execution and provenance only in this test.
        with tempfile.TemporaryDirectory(prefix='mlf-timeout-selection-') as temporary:
            root = Path(temporary)
            receipt = root / 'producer.json'
            receipt.write_text('{}')
            calls = []

            class RecordingRunner:
                def __init__(self, *args):
                    pass

                def run(self, name, command, **options):
                    calls.append((name, command, options))
                    return types.SimpleNamespace(stderr=b'async-scope-panic')

            argv = ['test_direct.py', '--bin-dir', str(root / 'bin'),
                    '--build-receipt', str(receipt), '--output', str(root / 'output'), *extra]
            with patch.object(sys, 'argv', argv), \
                    patch.object(direct, 'CommandRunner', RecordingRunner), \
                    patch.object(direct, 'authenticate_build', return_value={'producer_host': 'GHC', 'optimization': optimization}), \
                    patch.object(direct.shutil, 'which', return_value=sys.executable), \
                    patch.object(direct, 'sha', return_value='0' * 64):
                direct.main()
            return {name: options['timeout'] for name, _, options in calls
                    if name.startswith('shared-frontend-')}

    def test_default_frontend_budget_and_mode_specific_native_budgets(self):
        self.assertEqual(self.run_dispatch([]), {
            'shared-frontend-frontend': 1200,
            'shared-frontend-native-first': 180,
            'shared-frontend-native-second': 120,
        })

    def test_override_applies_only_to_frontend(self):
        self.assertEqual(self.run_dispatch(['--frontend-timeout', '333']), {
            'shared-frontend-frontend': 333,
            'shared-frontend-native-first': 180,
            'shared-frontend-native-second': 120,
        })

    def test_o0_budgets_come_from_authenticated_receipt(self):
        self.assertEqual(self.run_dispatch([], optimization='0'), {
            'shared-frontend-frontend': 3600,
            'shared-frontend-native-first': 1800,
            'shared-frontend-native-second': 1200,
        })
        self.assertEqual(self.run_dispatch(['--frontend-timeout', '3000'], optimization='0'), {
            'shared-frontend-frontend': 3000,
            'shared-frontend-native-first': 1800,
            'shared-frontend-native-second': 1200,
        })
        self.assertEqual(self.run_dispatch(['--frontend-timeout', '3600'], optimization='0'), {
            'shared-frontend-frontend': 3600,
            'shared-frontend-native-first': 1800,
            'shared-frontend-native-second': 1200,
        })

    def test_authenticated_o0_frontend_ceiling_is_finite(self):
        with self.assertRaisesRegex(ValueError, '3600'):
            direct.frontend_case_timeout('frontend', '0', 3601)

    def test_native_first_margin_cannot_be_selected_by_an_unknown_mode(self):
        for mode in ('native', 'native-first-extra', '--native-first', ''):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'unknown frontend case'):
                direct.frontend_case_timeout(mode, '2')

    def test_frontend_override_cannot_enlarge_either_native_mode(self):
        for override in (1, 1800):
            with self.subTest(override=override):
                self.assertEqual(direct.frontend_case_timeout('native-first', '2', override), 180)
                self.assertEqual(direct.frontend_case_timeout('native-second', '2', override), 120)
        for mode in ('native-first', 'native-second'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, '1800'):
                direct.frontend_case_timeout(mode, '2', 1801)
        for override in (1, 3600):
            self.assertEqual(direct.frontend_case_timeout('native-first', '0', override), 1800)
            self.assertEqual(direct.frontend_case_timeout('native-second', '0', override), 1200)

    def test_o2_rejects_o0_only_override(self):
        with self.assertRaisesRegex(ValueError, '1800'):
            self.run_dispatch(['--frontend-timeout', '1801'], optimization='2')

    def test_untrusted_optimization_cannot_select_a_budget(self):
        with self.assertRaisesRegex(ValueError, 'authenticated optimization'):
            self.run_dispatch([], optimization='unqualified')
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'output'
            argv = ['test_direct.py', '--bin-dir', temporary, '--output', str(output),
                    '--optimization', '0']
            with patch.object(sys, 'argv', argv), patch.object(direct, 'CommandRunner') as runner, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                direct.main()
            self.assertEqual(error.exception.code, 2)
            runner.assert_not_called()
            self.assertFalse(output.exists())

    def test_invalid_cli_budgets_fail_before_output_or_execution(self):
        for seconds in ('0', '-1', '3601'):
            with self.subTest(seconds=seconds), tempfile.TemporaryDirectory(prefix='mlf-timeout-invalid-') as temporary:
                output = Path(temporary) / 'output'
                argv = ['test_direct.py', '--bin-dir', temporary, '--output', str(output),
                        '--frontend-timeout', seconds]
                with patch.object(sys, 'argv', argv), patch.object(direct, 'CommandRunner') as runner, \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                    direct.main()
                self.assertEqual(error.exception.code, 2)
                runner.assert_not_called()
                self.assertFalse(output.exists())


class ChildCpuAccounting(unittest.TestCase):
    def sample(self, user, system):
        fake = types.SimpleNamespace(RUSAGE_CHILDREN=-1,
            getrusage=lambda who: types.SimpleNamespace(ru_utime=user, ru_stime=system))
        with patch.object(direct, 'resource', fake):
            return direct.child_cpu_sample()

    def test_interval_is_finite_nonnegative_and_explicitly_scoped(self):
        result = direct.child_cpu_interval(self.sample(1.0, 2.0), self.sample(1.25, 2.5))
        self.assertTrue(result['available'])
        self.assertEqual(result['user_seconds'], 0.25)
        self.assertEqual(result['system_seconds'], 0.5)
        self.assertEqual(result['total_seconds'], 0.75)
        self.assertEqual(result['scope'], 'RUSAGE_CHILDREN-reaped-child-interval')
        self.assertIn('not total process-group CPU', result['limits'])

    def test_unsupported_and_sampling_error_are_unavailable_not_zero(self):
        with patch.object(direct, 'resource', None):
            missing = direct.child_cpu_sample()
        fake = types.SimpleNamespace(RUSAGE_CHILDREN=-1, getrusage=lambda who: (_ for _ in ()).throw(OSError('accounting unavailable')))
        with patch.object(direct, 'resource', fake):
            error = direct.child_cpu_sample()
        for sample in (missing, error):
            result = direct.child_cpu_interval(self.sample(0, 0), sample)
            self.assertFalse(result['available'])
            self.assertNotIn('total_seconds', result)
            self.assertIn('unavailable', result['reason'])

    def test_invalid_counters_and_negative_intervals_are_unavailable(self):
        for value in (-1, float('nan'), float('inf'), True, '1'):
            with self.subTest(value=value):
                self.assertFalse(self.sample(value, 0)['available'])
        result = direct.child_cpu_interval(self.sample(2, 1), self.sample(1, 1))
        self.assertFalse(result['available'])
        self.assertNotIn('total_seconds', result)


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
        self.assertIn('child_cpu', entry)
        self.assertEqual(entry['child_cpu']['scope'], 'RUSAGE_CHILDREN-reaped-child-interval')
        self.assertLess(entry['seconds'], 5)

    def child_command(self, name, *, redirected, leader_exits=False, escaped=False):
        marker = self.output / (name + '.pid')
        child = ('import os,signal,sys,time; from pathlib import Path; '
                 'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                 'Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)')
        streams = (', stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, '
                   'stderr=subprocess.DEVNULL' if redirected else '')
        session = ', start_new_session=True' if escaped else ''
        parent = ('import subprocess,sys,time; from pathlib import Path\n'
                  'marker = Path(sys.argv[1])\n'
                  'child = subprocess.Popen([sys.executable, "-c", ' + repr(child) + ', str(marker)]' + streams + session + ')\n'
                  'deadline = time.monotonic() + 5\n'
                  'while not marker.exists() and time.monotonic() < deadline:\n'
                  '    time.sleep(0.01)\n'
                  'assert marker.exists(), "child did not install its SIGTERM handler"\n'
                  'print("partial", flush=True)\n'
                  'print("diagnostic", file=sys.stderr, flush=True)\n' +
                  ('' if leader_exits else 'time.sleep(60)\n'))

        def cleanup_child():
            if marker.exists():
                try:
                    os.kill(int(marker.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.addCleanup(cleanup_child)
        return [sys.executable, '-c', parent, str(marker)], marker

    def assert_child_stopped(self, marker):
        self.assertTrue(marker.exists(), 'child must start before exercising cleanup')
        pid = int(marker.read_text())
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                state = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(') ', 1)[1].split()[0]
            except (FileNotFoundError, ProcessLookupError):
                return
            # Orphaned grandchildren can await the host init's reaper. A zombie
            # cannot execute or keep pipes open and is not a surviving child.
            if state == 'Z':
                return
            time.sleep(0.01)
        self.fail('SIGTERM-ignoring grandchild survived command cleanup')

    @unittest.skipUnless(os.name == 'posix' and Path('/proc').is_dir(), 'requires POSIX groups and /proc liveness')
    def test_timeout_kills_grandchild_with_inherited_pipes(self):
        self.check_timeout_child(redirected=False)

    @unittest.skipUnless(os.name == 'posix' and Path('/proc').is_dir(), 'requires POSIX groups and /proc liveness')
    def test_timeout_kills_grandchild_with_redirected_stdio(self):
        self.check_timeout_child(redirected=True)

    def check_timeout_child(self, *, redirected):
        command, marker = self.child_command('timeout-child', redirected=redirected)
        with self.assertRaisesRegex(RuntimeError, 'exceeded'):
            self.runner.run('timeout-child', command, timeout=1)
        self.assert_child_stopped(marker)
        self.assertEqual((self.output / 'timeout-child.stdout').read_bytes(), b'partial\n')
        self.assertEqual((self.output / 'timeout-child.stderr').read_bytes(), b'diagnostic\n')
        entry = self.receipt['commands'][-1]
        self.assertTrue(entry['timed_out'])
        self.assertEqual(entry['state'], 'failed')
        self.assertEqual(entry['exit_code'], -signal.SIGTERM)
        self.assertTrue(entry['cleanup']['complete'])
        self.assertLess(entry['seconds'], 5)

    @unittest.skipUnless(os.name == 'posix' and Path('/proc').is_dir(), 'requires POSIX groups and /proc liveness')
    def test_escaped_group_pipes_cannot_make_failure_cleanup_unbounded(self):
        command, marker = self.child_command('escaped-child', redirected=False, escaped=True)
        with self.assertRaisesRegex(RuntimeError, 'escaped-child exceeded 1 seconds'):
            self.runner.run('escaped-child', command, timeout=1)
        self.assertTrue(marker.exists())
        pid = int(marker.read_text())
        self.assertEqual(os.getpgid(pid), pid, 'escaped child must have its own process group')
        state = Path('/proc/' + str(pid) + '/stat').read_text().rsplit(') ', 1)[1].split()[0]
        self.assertNotEqual(state, 'Z', 'runner must not signal the escaped process group')
        self.assertEqual((self.output / 'escaped-child.stdout').read_bytes(), b'partial\n')
        self.assertEqual((self.output / 'escaped-child.stderr').read_bytes(), b'diagnostic\n')
        entry = self.receipt['commands'][-1]
        self.assertEqual(entry['state'], 'failed')
        self.assertEqual(entry['error'], 'escaped-child exceeded 1 seconds')
        self.assertTrue(entry['timed_out'])
        self.assertEqual(entry['exit_code'], -signal.SIGTERM)
        self.assertEqual(entry['cleanup']['scope'], 'original-process-group')
        self.assertFalse(entry['cleanup']['capture_drained'])
        self.assertTrue(entry['cleanup']['leader_reaped'])
        self.assertFalse(entry['cleanup']['complete'])
        self.assertIn('within its bounds', entry['cleanup']['error'])
        self.assertLess(entry['seconds'], 8)

    @unittest.skipUnless(os.name == 'posix' and Path('/proc').is_dir(), 'requires POSIX groups and /proc liveness')
    def test_cancellation_kills_grandchild_after_leader_exit(self):
        command, marker = self.child_command('cancelled-child', redirected=True, leader_exits=True)
        real_popen = direct.subprocess.Popen

        def cancellable_popen(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            communicate = process.communicate
            first = True

            def cancel_once(*args, **kwargs):
                nonlocal first
                if first:
                    first = False
                    # Only inject cancellation; the leader and grandchild are
                    # real processes, and the leader has already exited here.
                    self.assertEqual(process.wait(timeout=5), 0)
                    raise KeyboardInterrupt('test cancellation')
                return communicate(*args, **kwargs)
            process.communicate = cancel_once
            return process

        with patch.object(direct.subprocess, 'Popen', side_effect=cancellable_popen), \
                self.assertRaisesRegex(KeyboardInterrupt, 'test cancellation'):
            self.runner.run('cancelled-child', command)
        self.assert_child_stopped(marker)
        self.assertEqual((self.output / 'cancelled-child.stdout').read_bytes(), b'partial\n')
        self.assertEqual((self.output / 'cancelled-child.stderr').read_bytes(), b'diagnostic\n')
        entry = self.receipt['commands'][-1]
        self.assertEqual(entry['state'], 'failed')
        self.assertEqual(entry['exit_code'], 0)
        self.assertEqual(entry['error'], 'test cancellation')
        self.assertTrue(entry['cleanup']['complete'])
        self.assertLess(entry['seconds'], 5)

    def test_success_checks_exact_stdout(self):
        self.runner.run('success', [sys.executable, '-c', 'print("okay")'], expected=b'okay\n')
        self.assertEqual(self.receipt['commands'][0]['state'], 'passed')

    def test_cpu_metadata_does_not_change_success_or_expected_nonzero(self):
        samples = [{'available': True, 'user_seconds': 2.0, 'system_seconds': 1.0},
                   {'available': True, 'user_seconds': 2.25, 'system_seconds': 1.5}]
        for status in (0, 7):
            with self.subTest(status=status), patch.object(direct, 'child_cpu_sample', side_effect=samples):
                self.runner.run('cpu-' + str(status), [sys.executable, '-c', 'raise SystemExit(' + str(status) + ')'],
                                status=status, expected=b'')
            entry = self.receipt['commands'][-1]
            self.assertEqual(entry['state'], 'passed')
            self.assertEqual(entry['exit_code'], status)
            self.assertEqual(entry['child_cpu']['total_seconds'], 0.75)

    def test_cpu_sampling_error_does_not_mask_success_or_failure(self):
        fake = types.SimpleNamespace(RUSAGE_CHILDREN=-1, getrusage=lambda who: (_ for _ in ()).throw(OSError('diagnostic unavailable')))
        with patch.object(direct, 'resource', fake):
            self.runner.run('cpu-unavailable', [sys.executable, '-c', 'print("okay")'], expected=b'okay\n')
            with self.assertRaisesRegex(RuntimeError, 'cpu-failed failed'):
                self.runner.run('cpu-failed', [sys.executable, '-c', 'raise SystemExit(3)'])
        for entry in self.receipt['commands'][-2:]:
            self.assertFalse(entry['child_cpu']['available'])
            self.assertNotIn('total_seconds', entry['child_cpu'])
            self.assertIn('OSError', entry['child_cpu']['reason'])
        self.assertEqual(self.receipt['commands'][-2]['state'], 'passed')
        self.assertEqual(self.receipt['commands'][-1]['state'], 'failed')

    def test_cpu_unavailable_platform_keeps_command_outcome(self):
        with patch.object(direct, 'resource', None):
            self.runner.run('cpu-unsupported', [sys.executable, '-c', 'pass'], expected=b'')
        entry = self.receipt['commands'][-1]
        self.assertEqual(entry['state'], 'passed')
        self.assertFalse(entry['child_cpu']['available'])
        self.assertNotIn('total_seconds', entry['child_cpu'])

    def test_frontend_success_requires_all_maintained_banners(self):
        expected = next(output for _, mode, output in direct.FRONTEND_CASES if mode == '--frontend')
        actual = (b'shared frontend: qualified recursive inference checks passed\n'
                  b'shared frontend: declaration provenance and declared forall field checks passed\n'
                  b'shared frontend: recursive inference checks passed\n'
                  b'shared frontend: parser and namespace checks passed\n')
        self.assertEqual(expected, actual)
        self.runner.run('frontend', [sys.executable, '-c',
            'import sys; sys.stdout.buffer.write(' + repr(actual) + ')'], expected=expected)
        self.assertEqual(self.receipt['commands'][-1]['state'], 'passed')

    def test_frontend_rejects_partial_extra_reordered_or_failed_output(self):
        expected = next(output for _, mode, output in direct.FRONTEND_CASES if mode == '--frontend')
        lines = expected.splitlines(keepends=True)
        cases = [('missing', lines[-1], b'', 0),
                 ('extra', expected + b'unexpected success\n', b'', 0),
                 ('reordered', b''.join([lines[1], lines[0], *lines[2:]]), b'', 0),
                 ('stderr', expected, b'diagnostic\n', 0),
                 ('failed', expected, b'', 1)]
        for name, output, error, status in cases:
            with self.subTest(name=name):
                code = ('import sys; sys.stdout.buffer.write(' + repr(output) + '); '
                        'sys.stderr.buffer.write(' + repr(error) + '); sys.exit(' + str(status) + ')')
                with self.assertRaises(RuntimeError):
                    self.runner.run(name, [sys.executable, '-c', code], expected=expected)
                self.assertEqual(self.receipt['commands'][-1]['state'], 'failed')


if __name__ == '__main__':
    unittest.main(verbosity=2)
