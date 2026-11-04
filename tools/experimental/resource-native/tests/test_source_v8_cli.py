#!/usr/bin/env python3
"""Host ingress tests; compiling/running source is explicitly opt-in.

Host only:
  python3 -B tests/test_source_v8_cli.py
Integration (fresh output, trusted official GHC 9.14.1 installation):
  python3 -B tests/test_source_v8_cli.py --integration --ghc /path/to/ghc \
      --cc cc --output /path/to/new-output

Integration makes eight fresh, separately bounded CLI calls: two pre-native
rejections, Int-first, two same-source low-fuel policies, Bool-first, curried,
and a renamed nested module. It never reuses a prior producer or capture.

Host tests never invoke a compiler, source producer, or native executable and
do not establish source admission. Integration retains every CLI run's output.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(BASE))

import source_snapshot_v8 as custody
import run_source_v8 as cli

MIB = 1 << 20


class ParserTests(unittest.TestCase):
    def arguments(self, *extra):
        return ['main.emlf', '--module-root', '/inputs', '--ghc', '/trusted/ghc',
                '--output', '/fresh-output', *extra]

    def rejects(self, arguments):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                cli.parser().parse_args(arguments)
        self.assertEqual(caught.exception.code, 2)

    def test_defaults(self):
        args = cli.parser().parse_args(self.arguments())
        self.assertEqual(args.fuel, 1000000)
        self.assertEqual(args.failure_policy, 'retain')

    def test_explicit_bounds_and_policy(self):
        for fuel in ('1', '10000000'):
            args = cli.parser().parse_args(self.arguments(
                '--fuel', fuel, '--failure-policy', 'destroy-terminal'))
            self.assertEqual(args.fuel, int(fuel))
            self.assertEqual(args.failure_policy, 'destroy-terminal')

    def test_bad_fuel(self):
        for fuel in ('0', '-1', '10000001', '1.5', 'NaN'):
            with self.subTest(fuel=fuel):
                self.rejects(self.arguments('--fuel', fuel))

    def test_bad_failure_policy(self):
        self.rejects(self.arguments('--failure-policy', 'diagnostic'))

    def test_required_options(self):
        self.rejects([])
        for flag in ('--module-root', '--ghc', '--output'):
            arguments = self.arguments()
            index = arguments.index(flag)
            del arguments[index:index + 2]
            with self.subTest(flag=flag):
                self.rejects(arguments)

    def test_rejects_cached_admission_options(self):
        for flag in ('--producer', '--capture', '--receipt', '--packet'):
            with self.subTest(flag=flag):
                self.rejects(self.arguments(flag, '/prior-artifact'))


class SnapshotIngressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='source-v8-host-')
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name).resolve()
        self.root = self.directory / 'inputs'
        self.root.mkdir()
        self.entry = self.root / 'main.emlf'
        self.entry.write_bytes(b'42\n')
        self.output = self.directory / 'output'
        self.output.mkdir()

    def rejected(self, action):
        with self.assertRaises((ValueError, OSError, UnicodeError)):
            action()

    def take_snapshot(self):
        return custody.snapshot(self.entry, self.root, self.output)

    def test_snapshot_preserves_whole_source_inventory(self):
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'unused.emlf').write_bytes(b'0\n')
        (self.root / 'README.txt').write_bytes(b'not source')
        canonical, files = custody.inventory(self.root)
        self.assertEqual(Path(canonical), self.root)
        self.assertEqual(files, {'main.emlf': b'42\n', 'nested/unused.emlf': b'0\n'})
        package, entry_bytes = self.take_snapshot()
        self.assertEqual(entry_bytes, b'42\n')
        self.assertEqual((self.output / 'sources/main.emlf').read_bytes(), entry_bytes)
        self.assertEqual((self.output / 'sources/nested/unused.emlf').read_bytes(), b'0\n')
        custody.verify_package(package)

    def test_empty_inventory(self):
        self.entry.unlink()
        self.rejected(lambda: custody.inventory(self.root))

    def test_invalid_utf8(self):
        self.entry.write_bytes(b'\xff')
        self.rejected(lambda: custody.inventory(self.root))

    def test_file_byte_limit(self):
        self.entry.write_bytes(b' ' * (MIB + 1))
        self.rejected(lambda: custody.inventory(self.root))

    def test_source_file_count_limit_includes_unused(self):
        for index in range(32):
            (self.root / ('unused%d.emlf' % index)).write_bytes(b'0\n')
        self.rejected(lambda: custody.inventory(self.root))

    def test_file_count_and_byte_bounds_are_inclusive(self):
        self.entry.write_bytes(b' ' * MIB)
        for index in range(31):
            (self.root / ('unused%d.emlf' % index)).write_bytes(b'0\n')
        _, files = custody.inventory(self.root)
        self.assertEqual(len(files), 32)
        self.assertEqual(len(files['main.emlf']), MIB)

    def test_total_byte_limit_includes_unused(self):
        for index in range(8):
            (self.root / ('unused%d.emlf' % index)).write_bytes(b' ' * MIB)
        self.rejected(lambda: custody.inventory(self.root))

    def test_total_byte_bound_is_inclusive(self):
        self.entry.write_bytes(b' ' * MIB)
        for index in range(7):
            (self.root / ('unused%d.emlf' % index)).write_bytes(b' ' * MIB)
        files = custody.inventory(self.root)[1]
        self.assertEqual(sum(map(len, files.values())), 8 * MIB)

    def test_guest_haskell_even_if_unused(self):
        (self.root / 'unused.hs').write_bytes(b'module Unused where\n')
        self.rejected(lambda: custody.inventory(self.root))

    def test_file_symlink_even_if_non_source(self):
        (self.root / 'notes.txt').symlink_to(self.entry)
        self.rejected(lambda: custody.inventory(self.root))

    def test_directory_symlink(self):
        (self.root / 'loop').symlink_to(self.root, target_is_directory=True)
        self.rejected(lambda: custody.inventory(self.root))

    def test_symlink_module_root(self):
        alias = self.directory / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.rejected(lambda: custody.inventory(alias))

    @unittest.skipUnless(hasattr(os, 'mkfifo'), 'FIFO ingress test requires POSIX')
    def test_special_file(self):
        os.mkfifo(self.root / 'pipe')
        self.rejected(lambda: custody.inventory(self.root))

    def test_visited_entry_limit_counts_non_sources(self):
        for index in range(1025):
            (self.root / ('note%d.txt' % index)).touch()
        self.rejected(lambda: custody.inventory(self.root))

    def test_visited_entry_bound_is_inclusive(self):
        for index in range(1023):
            (self.root / ('note%d.txt' % index)).touch()
        self.assertEqual(custody.inventory(self.root)[1], {'main.emlf': b'42\n'})

    def test_directory_depth_limit(self):
        current = self.root
        for index in range(18):
            current = current / ('d%d' % index)
            current.mkdir()
        self.rejected(lambda: custody.inventory(self.root))

    def test_sixteen_component_source_path_is_allowed(self):
        current = self.root
        for index in range(15):
            current = current / ('d%d' % index)
            current.mkdir()
        (current / 'deep.emlf').write_bytes(b'0\n')
        self.assertEqual(len(custody.inventory(self.root)[1]), 2)

    def test_entry_outside_root(self):
        outside = self.directory / 'outside.emlf'
        outside.write_bytes(b'42\n')
        self.rejected(lambda: custody.snapshot(outside, self.root, self.output))

    def test_non_source_entry(self):
        entry = self.root / 'main.txt'
        entry.write_bytes(b'42\n')
        self.rejected(lambda: custody.snapshot(entry, self.root, self.output))

    def test_output_inside_input(self):
        inside = self.root / 'output'
        inside.mkdir()
        self.rejected(lambda: custody.snapshot(self.entry, self.root, inside))

    def test_snapshot_will_not_overwrite_sources(self):
        self.take_snapshot()
        self.rejected(self.take_snapshot)

    def test_live_root_mutation(self):
        package, _ = self.take_snapshot()
        self.entry.write_bytes(b'43\n')
        self.rejected(lambda: custody.verify_package(package))

    def test_unused_live_source_addition(self):
        package, _ = self.take_snapshot()
        (self.root / 'added.emlf').write_bytes(b'0\n')
        self.rejected(lambda: custody.verify_package(package))

    def test_unused_live_source_deletion(self):
        unused = self.root / 'unused.emlf'
        unused.write_bytes(b'0\n')
        package, _ = self.take_snapshot()
        unused.unlink()
        self.rejected(lambda: custody.verify_package(package))

    def test_private_snapshot_mutation(self):
        package, _ = self.take_snapshot()
        (self.output / 'sources/main.emlf').write_bytes(b'43\n')
        self.rejected(lambda: custody.verify_package(package))

    def test_private_snapshot_addition(self):
        package, _ = self.take_snapshot()
        (self.output / 'sources/extra.emlf').write_bytes(b'0\n')
        self.rejected(lambda: custody.verify_package(package))

    def test_bounded_read_exact_limit_and_overflow(self):
        self.entry.write_bytes(b'abcd')
        self.assertEqual(custody.bounded_read(self.entry, 4), b'abcd')
        self.rejected(lambda: custody.bounded_read(self.entry, 3))

    def test_bounded_read_symlink(self):
        alias = self.directory / 'alias.emlf'
        alias.symlink_to(self.entry)
        self.rejected(lambda: custody.bounded_read(alias, MIB))

    def loader_custody_fixture(self):
        # Synthetic file association only. This incomplete envelope is NOT a
        # checked source capture and must never pass the independent verifier.
        (self.root / 'Shared.emlf').write_bytes(b'module Shared where\n')
        package, source = self.take_snapshot()
        imported = {'source': {'path': './Shared.emlf'},
                    'text': 'module Shared where\n', 'is_root': False}
        root = {'source': {'path': '<stdin>'}, 'text': '42\n', 'is_root': True}
        document = {'format': 'mlf-shared-source-capture/1',
                    'status': 'diagnostic-not-runtime-admission',
                    'module_custody': {'loaded': [imported, root]}}
        return package, source, document

    def check_loader_custody(self, package, source, document):
        path = self.output / 'synthetic-custody-only.json'
        path.write_text(json.dumps(document), encoding='utf-8')
        return custody.loaded_subset(path, package, source)

    def test_loader_file_association_only(self):
        package, source, document = self.loader_custody_fixture()
        selected = self.check_loader_custody(package, source, document)
        self.assertEqual(selected, {
            'main.emlf': hashlib.sha256(b'42\n').hexdigest(),
            'Shared.emlf': hashlib.sha256(b'module Shared where\n').hexdigest()})

    def test_loader_wrong_root_bytes(self):
        package, source, document = self.loader_custody_fixture()
        document['module_custody']['loaded'][-1]['text'] = '43\n'
        self.rejected(lambda: self.check_loader_custody(package, source, document))

    def test_loader_wrong_import_bytes(self):
        package, source, document = self.loader_custody_fixture()
        document['module_custody']['loaded'][0]['text'] += 'changed\n'
        self.rejected(lambda: self.check_loader_custody(package, source, document))

    def test_loader_duplicate_root(self):
        package, source, document = self.loader_custody_fixture()
        rows = document['module_custody']['loaded']
        rows.append(rows[-1])
        self.rejected(lambda: self.check_loader_custody(package, source, document))

    def test_loader_duplicate_import(self):
        package, source, document = self.loader_custody_fixture()
        rows = document['module_custody']['loaded']
        rows.insert(0, rows[0])
        self.rejected(lambda: self.check_loader_custody(package, source, document))

    def test_loader_missing_root(self):
        package, source, document = self.loader_custody_fixture()
        document['module_custody']['loaded'].pop()
        self.rejected(lambda: self.check_loader_custody(package, source, document))

    def test_loader_root_not_last(self):
        package, source, document = self.loader_custody_fixture()
        document['module_custody']['loaded'].reverse()
        self.rejected(lambda: self.check_loader_custody(package, source, document))

    def test_loader_unknown_and_escaped_import(self):
        package, source, document = self.loader_custody_fixture()
        for path in ('missing.emlf', '../Shared.emlf', '/Shared.emlf'):
            with self.subTest(path=path):
                document['module_custody']['loaded'][0]['source']['path'] = path
                self.rejected(lambda: self.check_loader_custody(package, source, document))


def check_memory(report, *, healthy):
    """Check evaluation accounting separately from terminal raw retirement."""
    categories = report['memory_categories']
    assert set(categories) == {'context', 'groups', 'nodes', 'slots',
                               'handles', 'captures', 'pending'}
    for field in ('allocated_bytes', 'freed_bytes', 'live_bytes',
                  'allocations', 'frees', 'live_blocks'):
        assert report['memory'][field] == sum(row[field] for row in categories.values()), field
    for row in [report['memory'], *categories.values()]:
        assert row['allocated_bytes'] - row['freed_bytes'] == row['live_bytes']
        assert row['allocations'] - row['frees'] == row['live_blocks']
        if healthy:
            assert row['live_bytes'] == row['live_blocks'] == 0
    if not healthy:
        assert report['memory']['live_bytes'] > 0
        assert report['memory']['live_blocks'] > 0


def integration(args):
    """Each invocation builds a fresh producer; never accepts old captures."""
    # Importing fixtures does not run their main/build path. Their stronger
    # graph assertions are applied to this invocation's fresh artifacts only.
    from test_shared_source_native import CASES, NEGATIVE, SHARED_ID, check_structure, check_native

    import source_build_v8 as build

    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    results = []
    primary_error = None
    env = cli.environment(output)

    def invoke(name, entry, inputs, *, fuel=1000000, policy='retain', rejection=None):
        case = output / name
        command = [sys.executable, '-B', str(BASE / 'run_source_v8.py'), str(entry),
                   '--module-root', str(inputs), '--ghc', args.ghc, '--cc', args.cc,
                   '--output', str(case), '--fuel', str(fuel), '--failure-policy', policy]
        # Reuse the production bounded runner, including cleanup and retained
        # argv/process evidence. Outer hard ceilings permit its child-specific
        # compiler/capture limits; each CLI also has its own 900-second deadline.
        build.run(command, output, name, cwd=BASE, env=env,
                  wall=1200, cpu=900, memory=16 << 30, termination_grace=15,
                  stdout_limit=MIB, stderr_limit=MIB, file_limit=64 * MIB,
                  expected=(0, 1, 2))
        returncode = json.loads((output / (name + '.result.json')).read_bytes())['returncode']
        row = {'case': name, 'returncode': returncode,
               'fuel': fuel, 'failure_policy': policy}
        results.append(row)
        (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        if rejection is not None:
            assert returncode == 1, row
            assert not (case / 'native').exists(), 'rejected source reached native compilation'
            assert not (case / 'result.json').exists(), 'rejected source got successful result'
            failure = json.loads((case / 'failure.json').read_bytes())
            assert failure['status'] == 'failed'
            capture_process = json.loads((case / 'capture.result.json').read_bytes())
            if rejection == 'inference':
                assert capture_process['returncode'] == 1
                assert not (case / 'capture.stdout').read_bytes()
                assert (case / 'capture.stderr').read_text() == (
                    'Inference: type constructor mismatch: Con "Bool" [] versus Con "Int" []\n')
                assert not (case / 'verification.json').exists()
            else:
                assert rejection == 'fragment'
                assert capture_process['returncode'] == 0
                assert not (case / 'capture.stderr').read_bytes()
                verified = json.loads((case / 'verification.json').read_bytes())
                assert verified['fragment_admitted'] is False
                assert verified['status'] == 'diagnostic-custody-pass-fragment-rejected'
            row.update(status='passed', rejection=rejection, native_started=False)
            return case, None
        result = json.loads((case / 'result.json').read_bytes())
        native = json.loads((case / 'native/run.stdout').read_bytes())
        assert result['fuel'] == fuel and result['failure_policy'] == policy
        assert result['native'] == native
        expected_fault = fuel == 1
        assert result['status'] == ('fault' if expected_fault else 'complete')
        assert returncode == (2 if expected_fault else 0), row
        if policy == 'destroy-terminal':
            assert native['schema'] == 'resource-ir-v8-terminal-run/1'
            evaluation = native['evaluation']
        else:
            assert native['schema'] == 'resource-ir-v8-run/1'
            assert 'destruction' not in native
            evaluation = native
        assert evaluation['schema'] == 'resource-ir-v8-run/1'
        assert bool(evaluation['fault']) == expected_fault
        if expected_fault:
            assert evaluation['fault'] == 4  # RT8_FAULT_FUEL, not another failure.
            assert evaluation['state'] == 1
            assert evaluation['metrics']['entries_completed'] == 0
        assert evaluation['events_omitted'] == 0
        check_memory(evaluation, healthy=not expected_fault)
        if expected_fault and policy == 'destroy-terminal':
            destroyed = native['destruction']
            assert destroyed['status'] == 1 and not destroyed['totals_overflow']
            assert destroyed['retired_bytes'] == evaluation['memory']['live_bytes']
            assert destroyed['retired_blocks'] == evaluation['memory']['live_blocks']
            for key, value in evaluation['memory_categories'].items():
                assert destroyed['categories'][key] == {
                    'bytes': value['live_bytes'], 'blocks': value['live_blocks']}
        row['status'] = 'passed' if expected_fault else 'runtime-checked'
        return case, evaluation

    try:
        # Ordinary inference rejection and later fragment rejection must remain
        # distinct, and both must stop before native compilation or execution.
        explicit_coerce = ('module SharedPoly (sharedId) where\n'
                           'sharedId : forall a. a -> a\n'
                           'sharedId = (\\coerce -> coerce) (\\x -> let x2 = '
                           '(\\coerce2 -> coerce2) x in x2)\n')
        assert hashlib.sha256(explicit_coerce.encode()).hexdigest() == (
            '13aa77126b59e15388371389e9a0ff954d02a1262a82d72eff842a7a10e33935')
        for name, shared, entry_text, rejection in (
                ('unused-type-error', SHARED_ID, NEGATIVE, 'inference'),
                ('unsupported-fragment', explicit_coerce, CASES[0][2], 'fragment')):
            inputs = output / (name + '-inputs')
            inputs.mkdir()
            (inputs / 'SharedPoly.emlf').write_text(shared, encoding='utf-8')
            entry = inputs / 'main.emlf'
            entry.write_text(entry_text, encoding='utf-8')
            invoke(name, entry, inputs, rejection=rejection)
        nested = ('nested-module',
                  CASES[0][1].replace('SharedPoly', 'Demo.Polymorphism').replace('sharedId', 'selectValue'),
                  CASES[0][2].replace('SharedPoly', 'Demo.Polymorphism').replace('sharedId', 'selectValue'),
                  CASES[0][3], CASES[0][4])
        for name, shared, entry_text, vectors, expected_arguments in (*CASES, nested):
            inputs = output / (name + '-inputs')
            inputs.mkdir()
            module = inputs / ('Demo/Polymorphism.emlf' if name == 'nested-module' else 'SharedPoly.emlf')
            module.parent.mkdir(parents=True, exist_ok=True)
            module.write_text(shared, encoding='utf-8')
            if name == 'nested-module':
                # Exact unused bytes: copied and mutation-checked, never
                # claimed parsed, inferred, checked, or loaded by the compiler.
                (inputs / 'unimported.emlf').write_bytes(b'not valid source\n')
            entry = inputs / 'main.emlf'
            entry.write_text(entry_text, encoding='utf-8')
            case, evaluation = invoke(name, entry, inputs)
            if name == 'nested-module':
                result = json.loads((case / 'result.json').read_bytes())
                self_package = json.loads((case / 'package.json').read_bytes())
                assert result['copied_source_files'] == 3
                assert len(result['loaded_sources']) == 2
                assert result['unimported_sources_are_not_claimed_type_checked'] is True
                assert 'unimported.emlf' in self_package['files']
            plan = json.loads((case / 'planned.json').read_bytes())
            verified = json.loads((case / 'verification.json').read_bytes())
            graph = check_structure(plan, verified, vectors)
            check_native({'evaluation': evaluation}, plan, graph,
                         expected_arguments, name == 'curried-const')
            results[-1]['status'] = 'passed'
            if name == 'int-first':
                # Exactly the same unchanged input, no special fault fixture or
                # driver hook, with independent fresh production each time.
                _, retained = invoke('low-fuel-retain', entry, inputs, fuel=1)
                _, terminal = invoke('low-fuel-destroy-terminal', entry, inputs,
                                     fuel=1, policy='destroy-terminal')
                assert retained == terminal, 'terminal retirement rewrote evaluation evidence'
    except BaseException as exc:
        primary_error = exc
        try:
            (output / 'failure.json').write_text(json.dumps({
                'error': '%s: %s' % (type(exc).__name__, exc),
                'scope': 'explicit source CLI integration; no cached producer admission',
            }, indent=2) + '\n')
        except BaseException as save_error:
            exc.add_note('Failure result persistence also failed: ' + repr(save_error))
        raise
    finally:
        try:
            (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        except BaseException as save_error:
            if primary_error is not None:
                primary_error.add_note('Results persistence also failed: ' + repr(save_error))
            else:
                raise


def main():
    if sys.flags.optimize:
        raise SystemExit('Run without -O: integration invariants must remain enabled')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integration', action='store_true')
    parser.add_argument('--ghc')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.integration and (not args.ghc or not args.output):
        parser.error('--integration requires --ghc and --output')
    if not args.integration and (args.ghc or args.output):
        parser.error('--ghc/--output require explicit --integration')
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    if args.integration:
        integration(args)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
