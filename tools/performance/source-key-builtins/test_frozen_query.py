"""Constructor-level compatibility of the independent named query oracle."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from frozen_query import prepare_frozen_query

ROOT = Path(__file__).resolve().parents[3]
TYPES = ROOT / 'libraries/mlf-foundation/Bootstrap/Types.hs'
DATA = ROOT / 'tools/performance/datatype-context'
SPARSE = ROOT / 'tools/performance/sparse-contracts'
EXCLUSIONS = [b'\n      ' + ctor + b' -> panic "indexed syntax in historical named query oracle";'
              for ctor in (b'SApplyDictionaries _ _', b'SBindDictionaries _ _')]

# Authored constructor interface; the mutation tests do not rewrite whatever
# spelling or line layout happens to be in the current compiler source.
NAMED_INTERFACE = """
data SExpr =
  SGlobal (Index Declaration) String | SDeclScope ([] Declaration) SExpr |
  SWantedRefs String ([] Candidate) | SWantedScope String Environment |
  SGivenScope ([] String) SExpr |
  SVar String | SConstructor String | SLam String (Maybe Annotation) SExpr |
  SApp SExpr SExpr | SLet String SExpr SExpr | SAnn SExpr Annotation |
  SSignature SExpr Annotation | SIntLit Int | SDoubleLit Double |
  SBoolLit Bool | SStringLit String | SPrimitive Primitive |
  SCase SExpr ([] Alternative) | SDo ([] Statement) SExpr |
  SEquations ([] Equation) | SLetRec ([] Definition) SExpr |
  SWanted String ([] Candidate) | SChecked Type SExpr |
  SSourceDefinition SExpr | SCallSite String Span SExpr |
  SSharedBind SPattern SExpr SExpr SExpr SExpr;
data SPattern =
  SConstructorPattern String ([] (Maybe String)) | SDefaultPattern (Maybe String) |
  SNestedPattern String ([] SPattern) | SAnnotatedPattern String Annotation |
  SIntPattern Int | SStringPattern String |
  SOverloadedStringPattern SourceString String String |
  SIndexedStringPattern SourceString TermRef TermRef |
  SBoolPattern Bool | SAsPattern String SPattern | SLazyPattern SPattern;
"""
DICTIONARY_INTERFACE = NAMED_INTERFACE.replace(
    'SSharedBind SPattern SExpr SExpr SExpr SExpr;',
    'SSharedBind SPattern SExpr SExpr SExpr SExpr | '
    'SApplyDictionaries TermRef ([] String) | SBindDictionaries ([] String) SExpr;')


class FrozenQueryTests(unittest.TestCase):
    def prepare(self, folder, out, types):
        oracle = json.loads((folder / 'oracle.json').read_text())
        if folder == SPARSE:
            oracle = oracle['sources']['CrateQuery']
        return prepare_frozen_query(folder / 'FrozenCrateQuery.hs', out,
                                    expected_sha256=oracle['frozen_sha256'], types_source=types).read_bytes()

    def test_optional_dictionary_constructors_get_rejection_branches(self):
        for folder in (DATA, SPARSE):
            with self.subTest(folder=folder.name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                named = out / 'Named.hs'
                named.write_text(NAMED_INTERFACE)
                dictionary = out / 'Dictionary.hs'
                dictionary.write_text(DICTIONARY_INTERFACE)
                original = (folder / 'FrozenCrateQuery.hs').read_bytes()
                old = self.prepare(folder, out, named)
                new = self.prepare(folder, out, dictionary)
                for branch in EXCLUSIONS:
                    self.assertNotIn(branch, old)
                    self.assertEqual(new.count(branch), 3)
                    new = new.replace(branch, b'')
                self.assertEqual(new, old)
                self.assertEqual((folder / 'FrozenCrateQuery.hs').read_bytes(), original)

    def test_comments_whitespace_and_unrelated_types_do_not_change_adaptation(self):
        for folder in (DATA, SPARSE):
            with self.subTest(folder=folder.name), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                changed = out / 'Types.hs'
                changed.write_text(TYPES.read_text().replace('data SExpr =',
                    'data  SExpr\n = {- interface {- nested comment -} -}').replace(
                    'SIntLit Int |', 'SIntLit {- field -} Int |') +
                    '\n\n-- unrelated constructor evolution\ndata FutureHostType = FutureHostType Int;\n'
                    'unrelated = "data SExpr = NotAConstructor; -- literal";\n')
                self.assertEqual(self.prepare(folder, out, changed), self.prepare(folder, out, TYPES))

    def test_unknown_changed_or_missing_consumed_constructor_is_rejected(self):
        original = DICTIONARY_INTERFACE
        cases = [original.replace('SIntLit Int |', 'SIntLit Int | SFuture String |'),
                 original.replace('SBindDictionaries ([] String) SExpr;', 'SBindDictionaries SExpr;'),
                 original.replace('SIntLit Int |', ''),
                 original.replace('SIndexedStringPattern SourceString TermRef TermRef |',
                                  'SIndexedStringPattern SourceString TermRef |')]
        for changed in cases:
            with self.subTest(changed=changed != original), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                types = out / 'Types.hs'
                types.write_text(changed)
                with self.assertRaisesRegex(ValueError, 'Unsupported Bootstrap.Types'):
                    self.prepare(DATA, out, types)
                self.assertFalse((out / 'FrozenCrateQuery.hs').exists())

    def test_changed_fixed_oracle_is_rejected(self):
        source = DATA / 'FrozenCrateQuery.hs'
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            changed = out / 'ChangedOracle.hs'
            changed.write_bytes(source.read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'differs from the pinned oracle'):
                prepare_frozen_query(changed, out,
                    expected_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), types_source=TYPES)
            self.assertFalse((out / 'FrozenCrateQuery.hs').exists())


if __name__ == '__main__':
    unittest.main()
