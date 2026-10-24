#!/usr/bin/env python3
"""Fail-closed shared migration controls; no compiler/build or expected-output generation."""
import re
import tempfile
import unittest
from pathlib import Path
import check_tuple_list_migration as audit


def shared_mutations(source):
    def replace(old, new):
        if old not in source:
            raise ValueError('inactive shared mutation: ' + old)
        return source.replace(old, new, 1)
    first = re.search(r'leaf "([^"]+)"', source).group(1)
    return {
        'require_always_succeeds': replace('if condition then', 'if True then'),
        'fatal_always_succeeds': replace('A.fail', 'A.succeed'),
        'datatype_declaration_changed': replace('data List a = Nil | Cons a (List a)', 'data List a = Nil | Cons a a'),
        'pair_constructor_changed': replace('SConstructor "(,)"', 'SConstructor "(,,)"'),
        'runtime_group_unreachable': replace('(:) runtimeCases', '(:) scopeCases'),
        'leaf_body_discarded': replace('[]) body', '[]) (A.succeed ())'),
        'missing_leaf': replace('leaf "' + first + '"', 'removed "' + first + '"'),
        'unknown_id': replace(first, first + '-unknown'),
        'duplicate_id': replace('tuple-list/focused/triple-ast', first),
        'fixed_ast_changed': replace('SConstructor "()"', 'SConstructor "WrongUnit"'),
        'independent_checker_removed': replace('Independent.checkClosed', 'Check.checkClosed'),
        'rejection_phase_removed': replace('Compiler.prettyPhase phase', 'Compiler.prettyPhase (Compiler.phase error)'),
        'runtime_oracle_changed': replace('actual == expected', 'actual == actual'),
        'location_check_removed': replace('contains "tuple-list.emlf:" error', 'contains "" error'),
    }


class SharedTupleMigrationControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Never mock the production semantic-contract pins for candidate sources.
        cls.sources = audit.verify_current_sources()

    def test_exact_reviewed_sources(self):
        self.assertEqual(len(self.sources), 3)

    def test_fourteen_semantic_mutants_rejected(self):
        mutants = shared_mutations(self.sources[audit.IMPLEMENTATION])
        self.assertEqual(len(mutants), 14)
        for name, mutant in mutants.items():
            with self.subTest(name=name), self.assertRaises(ValueError):
                audit.verify_shared(audit.IMPLEMENTATION, mutant)

    def test_default_or_dispatcher_change_rejected(self):
        for path in (audit.SOURCE, audit.LEGACY):
            with self.subTest(path=path), self.assertRaises(ValueError):
                audit.verify_shared(path, self.sources[path] + '\n-- unreviewed change\n')

    def test_unknown_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'requires review'):
            audit.verify_shared('tests/Unreviewed.hs', '')

    def test_duplicate_legacy_source_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, source in self.sources.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(source)
            (root / audit.FROZEN_SOURCE).write_text('-- stale duplicate')
            with self.assertRaisesRegex(ValueError, 'duplicate live'):
                audit.verify_current_sources(root)


if __name__ == '__main__':
    unittest.main()
