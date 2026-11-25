#!/usr/bin/env python3
"""Pure source/spec admission controls; never builds a compiler or native fixture."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('artifact_modular_actual', HERE / 'test_artifact_binary.py')
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
parser = argparse.ArgumentParser()
parser.add_argument('--source-root', type=Path, default=HERE.parents[1])
args, rest = parser.parse_known_args()
SOURCE = args.source_root.resolve(strict=True)


def unpack(text):
    values = []
    while text:
        n, colon, text = text.partition(':')
        if not colon or not n.isdecimal() or len(text) < int(n):
            raise ValueError('bad independent length field')
        size = int(n)
        values.append(text[:size])
        text = text[size:]
    return values


class ModularControls(unittest.TestCase):
    def test_wire_limits_projections_only_add_rejections_to_the_frozen_fixtures(self):
        for path, project, added in (
            (M.LEGACY_GHC_FIXTURE, M.project_legacy_limits_fixture, 9),
            (M.LEGACY_QUERY_FIXTURE, M.project_legacy_query_fixture, 1),
        ):
            with self.subTest(path=path):
                archive = (SOURCE / path).read_bytes()
                projected = project(archive)
                original = [line for line in projected.splitlines(keepends=True)
                            if b'W.IndexedText _' not in line]
                self.assertEqual(b''.join(original), archive)
                self.assertEqual(projected.count(b'W.IndexedText _'), added)
                with self.assertRaisesRegex(ValueError, 'archived GHC .*fixture identity mismatch'):
                    project(archive + b'\n')

    def test_current_primitive_abi_is_append_only_and_closed(self):
        import artifact_binary_reference as R
        import artifact_binary_typed as T
        self.assertEqual([code for _, code in T.CONTRACT['primitive_codes']], list(range(137)))
        self.assertEqual(T.CONTRACT['primitive_codes'][-1], ['PStringUtf8Length', 136])
        for code in range(137):
            doc = R.read_document(R.tree_document([T.n(32, ('int', code))], 7), 7)
            T.validate_type(doc, doc.roots[0], 'Primitive')
        for value in [('int', -1), ('int', 137), ('int', 2147483647), ('bits', 136)]:
            with self.subTest(value=value):
                doc = R.read_document(R.tree_document([T.n(32, value)], 7), 7)
                with self.assertRaises(R.Invalid):
                    T.validate_type(doc, doc.roots[0], 'Primitive')

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((SOURCE / 'shared-sources.json').read_text())
        cls.fixture = SOURCE / 'tools/shared/fixtures/item4/RawBinaryShared.hs'
        cls.rows = M.native_source_closure(SOURCE, cls.fixture, cls.manifest)

    def test_closed_companion_owner_checks_exact_crate_and_full_membership(self):
        import artifact_binary_open as O
        crate, members = 'crate/λ', ['a', 'bc']
        encoded = lambda value: ''.join(str(ord(c)) + '_' for c in value)
        legacy = 'Query_' + encoded(crate) + 'z_' + encoded(members[0])
        owner = O.pack(['MLF-OPEN-GROUP-1', crate, O.pack(sorted(members))])
        self.assertTrue(O.companion_group_matches(crate, legacy, owner, members))
        self.assertFalse(O.companion_group_matches('other', legacy, owner, members))
        self.assertFalse(O.companion_group_matches(crate, legacy, owner, ['a']))
        self.assertFalse(O.companion_group_matches(crate, legacy, owner + 'x', members))
        self.assertFalse(O.companion_group_matches(crate, 'wrong', owner, members))

    def test_query_fixture_separates_dictionary_and_legacy_payload_contracts(self):
        source = (SOURCE / 'tools/shared/fixtures/item4/QueryIndex.hs').read_text()
        self.assertIn('rootRow = row 3 1 [refs 2 0, refs 2 0] (just (W.VInt 0))', source)
        self.assertIn('(\"root\",Q.QueryNode \"root\" hashB [(\"leaf\",hashA),(\"leaf\",hashA)] (T.Just hashB))', source)
        self.assertIn('right "legacy index reader" (decode (Q.encodeLegacyIndex "config" legacyNodes)) >>= same "legacy compatibility" legacyNodes', source)
        self.assertIn('decodeReject "legacy mismatched payload" "invalid query graph digest"\n    (Q.encodeLegacyIndex "config" decoded)', source)
        self.assertIn('oldRoot = legacyNode "root" hashB [("leaf",hashA)] (just (W.VText hashB))', source)
        self.assertIn('decodeReject "legacy duplicate" "duplicate" (legacy [oldLeaf,oldLeaf,oldRoot])', source)
        self.assertIn('decodeReject "legacy missing" "unpublished" (legacy [oldRoot])', source)

    def test_compact_owner_preserves_full_names_and_canonical_tags(self):
        import artifact_binary_open as O
        for crate in ('crate', 'crate/λ', '9:a\0😀'):
            for version, encode, stem, separator in [
                ('MLF-OPEN-GROUP-2', lambda s: ''.join(str(ord(c)) + '_' for c in s), '', 'z_'),
                ('MLF-OPEN-GROUP-3', O.compact_name, 'c1_', '_'),
            ]:
                prefix = stem + encode(crate) + separator
                members = ['module_' + prefix + 'a', 'Module_' + prefix + 'T', 'raw:λ']
                make = O.compact_group_owner_v2 if version.endswith('2') else O.compact_group_owner
                owner = make(crate, members)
                actual_version, actual_crate, body = O.unpack(owner)
                self.assertEqual((actual_version, actual_crate), (version, crate))
                prefixes = {'raw': '', 'value': 'module_' + prefix, 'type': 'Module_' + prefix}
                expanded = [prefixes[tag] + suffix for tag, suffix in map(O.unpack, O.unpack(body))]
                self.assertEqual(expanded, sorted(members))
                encoded = lambda value: ''.join(str(ord(c)) + '_' for c in value)
                legacy = 'Query_' + encoded(crate) + 'z_' + encoded(min(members))
                self.assertTrue(O.companion_group_matches(crate, legacy, owner, members))
                for changed in (members[:-1], members + ['extra'], [*members, members[0]]):
                    self.assertFalse(O.companion_group_matches(crate, legacy, owner, changed))
                self.assertFalse(O.companion_group_matches('other', legacy, owner, members))
                self.assertFalse(O.companion_group_matches(crate, legacy, owner + 'x', members))

    def test_ground_variable_preserves_evidence_and_utf8_work_at_each_use(self):
        import artifact_binary_open as O
        from artifact_binary_reference import read_document, tree_document
        integer = lambda x: ('int', x)
        hint, ty = O.string('xλ'), O.string('型')
        ground = O.node(85, integer(-4), hint, ty)
        join = lambda left, right: O.node(88, integer(left), integer(right))
        rows = [O.node(87), ground, join(1, 0), join(2, 2), join(3, 3), join(4, 4)]
        run = O.node(89, integer(-2), integer(1), integer(8))
        def pattern(entries):
            return O.node(86, O.sequence(entries), O.sequence([run]), integer(len(entries) - 1))
        raw = pattern(rows)
        doc = read_document(tree_document([raw, raw], 10), 10)
        logical_leaf = O.node(74, O.node(70, O.node(31, integer(-4), hint)),
                              O.node(58, O.node(53, O.node(51, O.node(44, ty, O.sequence([])))), O.node(55)))
        terms = [O.node(72, logical_leaf, O.node(77, integer(i))) for i in range(-2, 6)]
        while len(terms) > 1:
            terms = [O.node(72, *terms[i:i+2]) for i in range(0, len(terms), 2)]
        ordinary = read_document(tree_document(terms * 2, 8), 8)
        budget = sum(ordinary.expanded_work[i] for i in ordinary.roots)
        values, work = O.expand_application_document(doc, budget, allow_ground=True)
        self.assertEqual((values, work), (tuple(terms * 2), budget))
        with self.assertRaises(O.OpenPairError):
            O.expand_application_document(doc, budget)
        with self.assertRaises(O.OpenPairError):
            O.expand_application_document(doc, budget - 1, allow_ground=True)
        for broken in (O.node(85, integer(-4), hint), O.node(85, hint, integer(-4), ty),
                       O.node(85, integer(-4), hint, O.sequence([]))):
            with self.assertRaises(O.OpenPairError):
                O._read_application_pattern(pattern([rows[0], broken, *rows[2:]])[2], allow_ground=True)

    def test_application_pattern_restores_each_signed_literal_and_charges_each_root(self):
        import artifact_binary_open as O
        from artifact_binary_reference import Limits, read_document, tree_document
        value = lambda n: ('int', n)
        hole = O.node(87)
        join = lambda a, b: O.node(88, value(a), value(b))
        rows = [hole, join(0, 0), join(1, 1), join(2, 2)]

        def document(entries, count, root):
            run = O.node(89, value(2**63 - 1), value(1), value(count))
            pattern = O.node(86, O.sequence(entries), O.sequence([run]), value(root))
            return read_document(tree_document([pattern, pattern], 9), 9, Limits())

        graph = document(rows, 8, 3)
        logical, work = O.expand_application_document(graph, 46)
        literals = [O.node(77, value((2**63 - 1 + i + 2**63) % 2**64 - 2**63)) for i in range(8)]
        while len(literals) > 1:
            literals = [O.node(72, a, b) for a, b in zip(literals[::2], literals[1::2])]
        self.assertEqual((logical, work), ((literals[0], literals[0]), 46))
        with self.assertRaises(ValueError):
            O.expand_application_document(graph, 45)
        for entries, count, root in [(rows, 7, 3), (rows, 9, 3), ([hole, join(0, 1)], 8, 1),
                                     ([*rows, join(1, 1)], 8, 4)]:
            with self.subTest(count=count, root=root), self.assertRaises(ValueError):
                O.expand_application_document(document(entries, count, root), 1000)

    def test_repeated_application_heads_preserve_order_and_logical_limits(self):
        import artifact_binary_open as O
        from artifact_binary_reference import read_document, tree_document
        integer = lambda value: ('int', value)
        ctor = O.node(82, ('text', 'C:λ'), O.sequence([]))
        last = O.node(82, ('text', 'end'), O.sequence([]))
        tables = [O.node(87), ctor, O.node(88, integer(1), integer(0)), last]

        def graph(count):
            repeat = O.node(88, integer(2), integer(3), integer(count))
            run = O.node(89, integer(2**63 - 1), integer(1), integer(257))
            pattern = O.node(86, O.sequence([*tables, repeat]), O.sequence([run]), integer(4))
            return read_document(tree_document([pattern, pattern], 11), 11)

        expected = last
        for i in reversed(range(257)):
            value = (2**63 - 1 + i + 2**63) % 2**64 - 2**63
            expected = O.node(72, O.node(72, ctor, O.node(77, integer(value))), expected)
        canonical = tree_document([expected, expected], 8)
        old = read_document(canonical, 8)
        bound = sum(old.expanded_work[i] for i in old.roots)
        wire = graph(257)
        values, charged = O.expand_application_document(wire, bound, allow_ground=True, allow_spines=True)
        self.assertEqual((tree_document(values, 8), charged), (canonical, bound))
        with self.assertRaises(O.OpenPairError):
            O.expand_application_document(wire, bound, allow_ground=True)
        with self.assertRaises(O.OpenPairError):
            O.expand_application_document(wire, bound-1, allow_ground=True, allow_spines=True)
        for n in (-1, 0, 1, 256, 16384, 2**63 - 1):
            with self.subTest(n=n), self.assertRaises(O.OpenPairError):
                O.expand_application_document(graph(n), bound, allow_ground=True, allow_spines=True)

    def test_stamp_syntax_and_semantic_mutations_remain_distinct(self):
        import artifact_binary_open as O
        for value in ('0-0', '0-1', '2147483646-2147483628'):
            O.checked_stamp_syntax(value)
            changed = O.different_content_stamp(value)
            self.assertNotEqual(changed, value)
            O.checked_stamp_syntax(changed)
        for value in ('', '1', '-1-2', '+1-2', '01-2', '1-02', '1-2-forged',
                      '2147483647-0', '0-2147483629', '１-2', '1-2\n', '9' * 100 + '-0'):
            with self.subTest(value=value), self.assertRaises(O.OpenPairError):
                O.checked_stamp_syntax(value)
        n, text, seq = O.node, O.string, O.sequence
        ty = n(44, text('Int'), seq([]))
        name = n(31, ('int', 1), text('value'))
        interface = n(242, text('fixture'), seq([]), seq([text('Main')]),
                      seq([]), seq([]), seq([]), seq([]), seq([]), seq([]),
                      seq([n(2, text('value'), ty)]), text('value'), text(''), seq([]))
        body = n(75, name, n(77, ('int', 41)), n(82, text('()'), seq([])))
        fragment = n(401, text('g'), text('0-1'), seq([]), seq([]), body,
                     seq([name]), seq([]))
        # Synthetic canonical syntax only: this stamp is not claimed to bind body.
        for schema in (7, 8):
            opened = [text(O.OPEN_FORMATS[schema]), text(O.compatibility_identity()),
                      text(O.pack([O.interface_association(interface)])),
                      seq([n(2, text('value'), text(O.fingerprint(ty)))]), seq([]), seq([fragment])]
            pair = O.repinned((O.tree_document([interface], 3), b''), O.open_bytes(schema, opened))
            O.inspect_pair(pair, [])
            label, changed, diagnostic = O.content_stamp_mutation(pair)
            self.assertEqual(label, ('schema7-' if schema == 7 else '') + 'wrong-open-fragment-content-stamp')
            self.assertEqual(diagnostic, 'open crate fragment fingerprint mismatch')
            O.inspect_pair(changed, [])  # semantic authentication is NOT Python's claim
            _, _, changed_fields = O.open_document(changed[1])
            changed_fragment = list(O.fields(O.items(changed_fields[5])[0], 401, 7))
            self.assertEqual(O.text(changed_fragment[1]), '1-1')
            changed_fragment[1] = O.fields(fragment, 401, 7)[1]
            self.assertEqual(O.node(401, *changed_fragment), fragment)
            self.assertEqual(changed_fields[:5], tuple(opened[:5]))
            malformed = next(row for row in O.mutation_cases(pair) if row[0] == 'wrong-open-fragment-stamp')
            with self.assertRaisesRegex(O.OpenPairError, '^malformed open fragment stamp$'):
                O.inspect_pair(malformed[1], [])

    def test_both_stamp_schemas_require_all_three_actual_readers(self):
        expected = {backend + '-' + case
                    for backend in ('formal', 'shared-ghc', 'shared-native')
                    for case in ('wrong-open-fragment-stamp', 'wrong-open-fragment-content-stamp',
                                 'schema7-wrong-open-fragment-content-stamp')}
        self.assertTrue(expected <= M.CONTROL_COMMANDS)
        for name in expected:
            rows = self.complete_commands()
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.require_control_commands([row for row in rows if row['name'] != name])
            next(row for row in rows if row['name'] == name)['state'] = 'failed'
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.require_control_commands(rows)

    def test_complete_source_closure(self):
        self.assertEqual(next(r['path'] for r in self.rows if r['module'] == 'Main'), str(self.fixture))
        for row in self.rows:
            self.assertEqual(row['sha256'], M.sha(Path(row['path'])))
            self.assertEqual(row['bytes'], Path(row['path']).stat().st_size)

    def test_specs_independent_decode(self):
        directory = Path('/fresh/binary gate/π😀')
        plan = M.native_crate_plan(self.rows, directory, SOURCE)
        names = ['mlf-foundation', 'mlf-language-core', 'mlf-frontend',
                 'mlf-xmlf', 'mlf-inference', 'mlf-crates', 'fixture']
        self.assertEqual([p['name'] for p in plan], names)
        all_modules = [name for p in plan for name in p['modules']]
        self.assertEqual(sorted(all_modules), sorted(row['module'] for row in self.rows))
        self.assertEqual(len(all_modules), len(set(all_modules)))
        expected_dependencies = [[], names[:1], names[:2], names[:3], names[:4], names[:5],
                                 ['mlf-crates', 'mlf-foundation', 'mlf-xmlf']]
        paths = {row['module']: row['path'] for row in self.rows}
        finished = {}
        for component, dependencies in zip(plan, expected_dependencies):
            name = component['name']
            prefix = directory / 'fixture' if name == 'fixture' else directory / name / 'unit'
            self.assertEqual(component['prefix'], str(prefix))
            fields = unpack(component['spec'])
            self.assertEqual(fields[:4], ['MLF-CRATE-1', 'artifact-binary-native-' + name,
                                         'Main' if name == 'fixture' else '', 'false'])
            self.assertEqual([unpack(x) for x in unpack(fields[4])],
                             [[module, paths[module]] for module in component['modules']])
            self.assertEqual(component['dependencies'], sorted(dependencies))
            self.assertEqual(unpack(fields[5]), [finished[dep] for dep in sorted(dependencies)])
            self.assertEqual(fields[6:], [str(directory / name / 'inference-cache'),
                                         str(directory / 'builtin/prelude')])
            finished[name] = str(prefix.with_suffix('.mlfci'))
        self.assertEqual(plan[-1]['modules'], ['Main'])
        self.assertEqual(paths['Main'], str(self.fixture))

    def test_specs_reject_wrong_owner(self):
        rows = copy.deepcopy(self.rows)
        row = next(r for r in rows if r['module'] == 'Bootstrap.ST')
        row['path'] = str(SOURCE / 'libraries/mlf-crates/Bootstrap/ST.hs')
        with self.assertRaisesRegex(ValueError, 'module declaration'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def test_specs_reject_unknown_import(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['imports'].append('Missing.Module')
        with self.assertRaisesRegex(ValueError, 'outside authenticated closure'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def test_specs_reject_undeclared_dependency(self):
        rows = copy.deepcopy(self.rows)
        next(r for r in rows if r['module'] == 'Bootstrap.ST')['imports'].append('Bootstrap.CrateArtifact')
        with self.assertRaisesRegex(ValueError, 'undeclared native library dependency'):
            M.native_crate_plan(rows, Path('/fresh'), SOURCE)

    def manifest_mutation(self, mutate, expected):
        # Exercise the actual JSON/path admissions on a tiny owner-manifest tree.
        # Source hashes/headers are covered separately by the closure controls.
        with tempfile.TemporaryDirectory() as d:
            source = Path(d).resolve()
            manifests = {}
            for name in M.NATIVE_LIBRARIES:
                manifests[name] = json.loads((SOURCE / 'libraries' / name / 'mlf-package.json').read_text())
            rows = copy.deepcopy(self.rows)
            for row in rows:
                if row['module'] != 'Main':
                    row['path'] = str(source / Path(row['path']).relative_to(SOURCE))
            mutate(manifests, rows)
            for name, manifest in manifests.items():
                path = source / 'libraries' / name / 'mlf-package.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, expected):
                M.native_crate_plan(rows, Path('/fresh'), source)

    def test_specs_reject_manifest_identity(self):
        def mutate(manifests, rows):
            manifests['mlf-crates']['name'] = 'different-owner'
        self.manifest_mutation(mutate, 'identity mismatch')

    def test_specs_reject_module_path(self):
        def mutate(manifests, rows):
            manifests['mlf-foundation']['library']['modules']['Bootstrap.ST'] = 'Bootstrap/Different.hs'
        self.manifest_mutation(mutate, 'module declaration')

    def test_specs_reject_external_dependency_path(self):
        def mutate(manifests, rows):
            manifests['mlf-crates']['dependencies']['mlf-foundation']['path'] = '/installed/mlf-foundation'
        self.manifest_mutation(mutate, 'local library owner')

    def test_specs_reject_dependency_cycle(self):
        def mutate(manifests, rows):
            manifests['mlf-foundation']['dependencies'] = {'mlf-crates': {'path': '../mlf-crates'}}
            next(r for r in rows if r['module'] == 'Bootstrap.ST')['imports'].append('Bootstrap.CrateArtifact')
        self.manifest_mutation(mutate, 'cyclic native library dependencies')

    def test_scalar_field_roundtrip(self):
        values = ['', 'a:b', 'π😀', 'space path']
        self.assertEqual(unpack(M.crate_fields(values)), values)

    def test_field_rejects_nul(self):
        with self.assertRaises(ValueError): M.crate_fields(['a\0b'])

    def test_field_rejects_surrogate(self):
        with self.assertRaises(ValueError): M.crate_fields(['\ud800'])

    def test_field_rejects_nonstring(self):
        with self.assertRaises(ValueError): M.crate_fields([1])

    def test_spec_rejects_omission(self):
        with self.assertRaises(ValueError): M.native_crate_plan(self.rows[:-1], Path('/fresh'), SOURCE)

    def test_spec_rejects_reordering(self):
        with self.assertRaises(ValueError): M.native_crate_plan(list(reversed(self.rows)), Path('/fresh'), SOURCE)

    def test_manifest_rejects_duplicate(self):
        m = copy.deepcopy(self.manifest); m['modules'].append(m['modules'][0])
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_escape(self):
        m = copy.deepcopy(self.manifest); m['modules'][0]['path'] = '../outside.hs'
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_absolute(self):
        m = copy.deepcopy(self.manifest); m['modules'][0]['path'] = '/outside.hs'
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def test_manifest_rejects_missing_dependency(self):
        m = copy.deepcopy(self.manifest)
        m['modules'] = [r for r in m['modules'] if r['module'] != 'Bootstrap.CrateArtifact']
        with self.assertRaises(ValueError): M.native_source_closure(SOURCE, self.fixture, m)

    def bad_fixture(self, text):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'Main.hs'; p.write_text(text)
            with self.assertRaises(ValueError): M.native_source_closure(SOURCE, p, self.manifest)

    def test_fixture_rejects_wrong_header(self):
        self.bad_fixture(self.fixture.read_text().replace('module Main where', 'module Wrong where', 1))

    def test_fixture_rejects_unknown_import(self):
        self.bad_fixture(self.fixture.read_text().replace('  import MLF.Primitive;', '  import Missing.Module;'))

    def test_fixture_rejects_reduced_scope(self):
        self.bad_fixture('module Main where {\n import MLF.Primitive;\n main = return ();\n}\n')

    def complete_commands(self):
        return [{'name': name, 'state': 'passed',
                 'exit_code': 1 if name in M.CONTROL_REJECTIONS else 0}
                for name in sorted(M.CONTROL_COMMANDS)]

    def test_complete_control_inventory(self):
        self.assertEqual(len(M.CONTROL_COMMANDS), 142)
        self.assertEqual(len(M.CONTROL_REJECTIONS), 13)
        self.assertIn('shared-native-public-pair-closed', M.CONTROL_COMMANDS)
        self.assertIn('formal-corrupt-4', M.CONTROL_COMMANDS)
        self.assertEqual(len(M.require_control_commands(self.complete_commands())), 142)

    def test_controls_reject_omitted_materialization(self):
        rows = [row for row in self.complete_commands() if row['name'] != 'release-materialize-warm']
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_reject_duplicate(self):
        rows = self.complete_commands()
        with self.assertRaises(ValueError): M.require_control_commands(rows + rows[:1])

    def test_controls_reject_unknown_stage(self):
        rows = self.complete_commands(); rows[0]['name'] = 'unreviewed-stage'
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_reject_unchecked_failure(self):
        rows = self.complete_commands(); rows[0]['state'] = 'failed'
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_require_actual_negative_exit(self):
        rows = self.complete_commands()
        next(row for row in rows if row['name'] == 'release-forged-current')['exit_code'] = 0
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_controls_keep_self_checked_rejections_successful(self):
        rows = self.complete_commands()
        next(row for row in rows if row['name'] == 'formal-corrupt-4')['exit_code'] = 1
        with self.assertRaises(ValueError): M.require_control_commands(rows)

    def test_cold_query_accepts_fresh(self):
        M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_empty(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [], 'inferred_groups': 0, 'reused_groups': 0})

    def test_cold_query_rejects_reuse(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': True}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_bool_count(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': True, 'reused_groups': 0})

    def test_cold_query_rejects_missing_cached(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{}], 'inferred_groups': 1, 'reused_groups': 0})

    def test_cold_query_rejects_count_mismatch(self):
        with self.assertRaises(ValueError): M.require_cold_queries({'groups': [{'cached': False}], 'inferred_groups': 2, 'reused_groups': 0})


if __name__ == '__main__':
    unittest.main(argv=[__file__, *rest])
