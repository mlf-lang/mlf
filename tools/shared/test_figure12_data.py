#!/usr/bin/env python3
"""Data-decoder controls only: no compiler execution or source translation."""
import json
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import figure12_data as data


class Figure12Data(unittest.TestCase):
    def test_maintained_inventory(self):
        fixture = data.decode()
        self.assertEqual(len(fixture['cases']), 43)
        self.assertEqual(len(fixture['type_checks']), 4)
        self.assertEqual(len(fixture['repairs']), 3)
        cases = fixture['cases']
        self.assertEqual([c['id'] for c in cases if not c['paper_acceptance']], ['A11', 'C1a', 'C1c', 'E1a'])
        self.assertEqual([c['id'] for c in cases if not c['expected_acceptance']], ['A8', 'A11', 'C1a', 'C1c', 'E1a'])
        self.assertEqual([c['id'] for c in cases if c['paper_acceptance'] != c['expected_acceptance']], ['A8'])
        self.assertEqual([c['id'] for c in fixture['repairs']], ['A11', 'C1a', 'C1c'])
        self.assertTrue(all(c['expected_acceptance'] for c in fixture['repairs']))
        self.assertEqual(json.loads(json.dumps(fixture)), fixture)

    def test_lexical_binding_and_constructor_data(self):
        parsed = data.Parser('(let { yes n e = Case n e true true [] } in (:) (yes "x" "guest") [])').parse()
        value = data.evaluate(parsed, data.environment())
        self.assertEqual(value, [dict(id='x', expression='guest', paper_acceptance=True, expected_acceptance=True, local_signatures=[])])

    def test_reject_unsupported_syntax(self):
        for source in ['(:) 1 2', '(,) \"a\" \"b\" trailing', 'Nil', 'Cons 1 Nil', '[1,2]', '\\x -> x', 'let rec { x = 1 } in x', 'Cons 1 Nil trailing', 'unknown', '"bad\\q"', 'Pair "a" "b" garbage', '(Pair "a" "b") )']:
            with self.subTest(source=source), self.assertRaises((data.FixtureError, TypeError)):
                data.evaluate(data.Parser(source).parse(), data.environment())

    def test_no_guest_expression_evaluation(self):
        source = 'Case "x" "unsafe-looking opaque guest source: (panic 1)" true false []'
        decoded = data.evaluate(data.Parser(source).parse(), data.environment())
        self.assertEqual(decoded['expression'], 'unsafe-looking opaque guest source: (panic 1)')

    def changed(self, relative, old, new):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for fixture_relative in data.REVIEWED_SEMANTIC_SHA256:
            name = Path(fixture_relative).name
            target = root / 'tests/Tests' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(data.ROOT / 'tests/Tests' / name, target)
        target = root / relative
        text = target.read_text()
        self.assertIn(old, text)
        target.write_text(text.replace(old, new, 1))
        return root

    def reviewed_decode_for_data_control(self, root):
        # Test-only simulation of an explicit re-review. There is no production
        # bypass flag: ordinary decode MUST reject the same mutation first.
        with self.assertRaisesRegex(data.FixtureError, 'unreviewed Figure12 oracle semantics'):
            data.decode(root)
        reviewed = {relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
                    for relative in data.REVIEWED_SEMANTIC_SHA256}
        with patch.object(data, 'REVIEWED_SEMANTIC_SHA256', reviewed):
            return data.decode(root)

    def test_fixture_changes_flow_into_output(self):
        root = self.changed('tests/Tests/Figure12.emlf', 'yes "A2" "choose id"', 'yes "A2" "choose nil"')
        self.assertEqual(self.reviewed_decode_for_data_control(root)['cases'][1]['expression'], 'choose nil')
        self.assertNotEqual(self.reviewed_decode_for_data_control(root)['fixture_sha256'], data.decode()['fixture_sha256'])

    def test_type_expectation_is_decoded_not_recomputed(self):
        root = self.changed('tests/Tests/Figure12Suite.emlf', 'identity = (XForall (XTyVar 0) XBot', 'identity = (XForall (XTyVar 99) XBot')
        expected = self.reviewed_decode_for_data_control(root)['type_checks'][3]['expected']
        self.assertEqual(expected[1][1], ['XTyVar', 99])

    def test_repair_source_is_decoded(self):
        root = self.changed('tests/Tests/Figure12Suite.emlf', 'then "k (', 'then "changed (')
        self.assertTrue(self.reviewed_decode_for_data_control(root)['repairs'][0]['expression'].startswith('changed ('))

    def test_changed_repair_logic_fails_closed(self):
        root = self.changed('tests/Tests/Figure12Suite.emlf', 'if eqString label "A11" then', 'if otherPredicate label "A11" then')
        with self.assertRaises(data.FixtureError):
            self.reviewed_decode_for_data_control(root)

    def test_changed_repaired_constructor_fails_closed(self):
        root = self.changed('tests/Tests/Figure12Suite.emlf', 'expression (paperAcceptance c) true (localSignatures c)', 'expression (paperAcceptance c) false (localSignatures c)')
        with self.assertRaises(data.FixtureError):
            self.reviewed_decode_for_data_control(root)

    def test_changed_projection_fails_closed(self):
        root = self.changed('tests/Tests/Figure12.emlf',
                            'expectedAcceptance (Case _ _ _ a _) = a',
                            'expectedAcceptance (Case _ _ a _ _) = a')
        with self.assertRaises(data.FixtureError):
            self.reviewed_decode_for_data_control(root)

    def test_malformed_expected_type_fails_closed(self):
        root = self.changed('tests/Tests/Figure12Suite.emlf',
                            'identity = (XForall (XTyVar 0) XBot',
                            'identity = (XForall (XTyVar "wrong") XBot')
        with self.assertRaises(data.FixtureError):
            self.reviewed_decode_for_data_control(root)

    def test_semantic_oracle_mutations_fail_closed(self):
        mutations = [
            ('Figure12.emlf', 'import Prelude hiding (Monad, return, bind)\nimport MLF.Primitive (Monad, return, bind)\n', ''),
            ('Figure12Suite.emlf', 'T.alphaEq (inferredType result) expected', 'true'),
            ('Figure12Suite.emlf', 'S.find (\\c -> eqString label (caseId c)) cases',
             'S.find (\\c -> eqString "A11" (caseId c)) cases'),
            ('Figure12.emlf', 'H.append signatures (localSignatures c)',
             'H.append (localSignatures c) signatures'),
            ('Figure12Suite.emlf', 'X.equalErased (X.erase parsed) (X.erase (compiledTerm result))', 'true'),
            ('Figure12.emlf', '(Set.delete x (freeNames b))', '(freeNames b)'),
            ('Figure12.emlf', '(expression c) ss', '(expression c) []'),
            ('Helpers.emlf', 'instance Ord String where { compare = compareString }',
             'instance Ord String where { compare = compareInt }'),
            ('Helpers.emlf', 'S.mapEither IM.fromList', 'fmap IM.fromList'),
            ('Helpers.emlf', 'S.mapEither ((,) k) (f k v)', 'fmap ((,) k) (f k v)'),
            ('Map.emlf', 'fromList xs = M.fromList H.compare xs', 'fromList xs = M.empty'),
            ('Set.emlf', 'toAscList = S.toList', 'toAscList = S.empty'),
        ]
        for filename, old, new in mutations:
            with self.subTest(filename=filename, old=old):
                root = self.changed('tests/Tests/' + filename, old, new)
                with self.assertRaisesRegex(data.FixtureError, 'unreviewed Figure12 oracle semantics'):
                    data.decode(root)

    def test_reviewed_transcriptions_reconstruct_old_allowlist(self):
        self.assertEqual(set(data.REVIEWED_SOURCE_TRANSITIONS),
                         {'tests/Tests/Figure12.emlf', 'tests/Tests/Helpers.emlf'})
        for relative, transition in data.REVIEWED_SOURCE_TRANSITIONS.items():
            with self.subTest(relative=relative):
                current = (data.ROOT / relative).read_text()
                previous = current
                for before, after in reversed(transition['edits']):
                    self.assertEqual(previous.count(after), 1)
                    previous = previous.replace(after, before, 1)
                self.assertEqual(hashlib.sha256(previous.encode()).hexdigest(),
                                 data.REVIEWED_SEMANTIC_SHA256[relative])
                self.assertEqual(transition['preimage_sha256'], data.REVIEWED_SEMANTIC_SHA256[relative])
                self.assertEqual(hashlib.sha256(current.encode()).hexdigest(), transition['postimage_sha256'])
                self.assertEqual(data.authenticate_semantic_source(
                    relative, previous.encode(), data.REVIEWED_SEMANTIC_SHA256[relative]), previous)
                root = self.changed(relative, current, previous)
                self.assertEqual(data.decode(root)['cases'], data.decode()['cases'])

    def test_partial_or_mutated_transcriptions_fail_closed(self):
        mutations = [
            ('Figure12.emlf', '  bound (SIndexedStringPattern _ _ _) = [];\n', ''),
            ('Figure12.emlf', 'SGlobal _ _ -> panic', 'SGlobal _ _ -> Set.empty; -- panic'),
            ('Figure12.emlf', 'SDeclScope _ _ -> panic', 'SDeclScope _ body -> freeNames body; -- panic'),
            ('Figure12.emlf', 'SWantedRefs _ _ -> panic', 'SWantedRefs _ _ -> Set.empty; -- panic'),
            ('Figure12.emlf', 'references (SIndexedStringPattern _ _ _) = panic',
             'references (SIndexedStringPattern _ _ _) = Set.empty; -- panic'),
            ('Figure12.emlf', 'bound (SIndexedStringPattern _ _ _) = []',
             'bound (SIndexedStringPattern _ _ _) = ["hint"]'),
            ('Helpers.emlf', 'import Prelude hiding (Eq, fail)\n', ''),
            ('Helpers.emlf', 'SSignature body annotation -> SSignature (layoutExpr body) annotation',
             'SSignature body annotation -> layoutExpr body'),
            ('Helpers.emlf', 'SourceSpan package owner "" 0 0 0 0', 'SourceSpan "" "" "" 0 0 0 0'),
            ('Helpers.emlf', 'S.map layoutInstance instances', 'instances'),
        ]
        for filename, old, new in mutations:
            with self.subTest(filename=filename, old=old):
                root = self.changed('tests/Tests/' + filename, old, new)
                with self.assertRaisesRegex(data.FixtureError, 'unreviewed Figure12 oracle semantics'):
                    data.decode(root)

    def test_postimage_digest_cannot_authorize_unreviewed_source(self):
        relative = 'tests/Tests/Figure12.emlf'
        root = self.changed(relative, '(Set.delete x (freeNames b))', '(freeNames b)')
        transitions = {key: dict(value) for key, value in data.REVIEWED_SOURCE_TRANSITIONS.items()}
        transitions[relative]['postimage_sha256'] = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        with patch.object(data, 'REVIEWED_SOURCE_TRANSITIONS', transitions):
            with self.assertRaisesRegex(data.FixtureError, 'unreviewed Figure12 oracle semantics'):
                data.decode(root)

    def test_appended_or_reordered_semantics_fail_closed(self):
        for relative, transition in data.REVIEWED_SOURCE_TRANSITIONS.items():
            current = (data.ROOT / relative).read_text()
            before, after = transition['edits'][-1]
            for mutant in [current + '\nfreeNames expression = Set.empty\n',
                           current.replace(after, before, 1) + after]:
                with self.subTest(relative=relative, mutant=hashlib.sha256(mutant.encode()).hexdigest()):
                    root = self.changed(relative, current, mutant)
                    with self.assertRaisesRegex(data.FixtureError, 'unreviewed Figure12 oracle semantics'):
                        data.decode(root)

    def test_multiline_or_ambiguous_data_fails_closed(self):
        for new in ['signatures =\n ', 'signatures = []\nsignatures = ']:
            root = self.changed('tests/Tests/Figure12.emlf', 'signatures = ', new)
            with self.assertRaises(data.FixtureError):
                self.reviewed_decode_for_data_control(root)


if __name__ == '__main__':
    unittest.main()
