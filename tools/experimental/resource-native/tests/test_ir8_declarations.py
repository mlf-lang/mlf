"""Finite declaration-only IR8 checks; no compiler, body or runtime execution."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import resource_ir_v8
from resource_ir_v8.declarations import DeclarationError, check_declarations, loads_declarations

FIXTURE_PATH = Path(__file__).parent / 'fixtures/ir8-declarations.json'
FIXTURES = json.loads(FIXTURE_PATH.read_text())['cases']
NEGATIVES = json.loads((FIXTURE_PATH.parent/'ir8-declaration-negative-expectations.json').read_text())
assert set(NEGATIVES)=={x['name'] for x in FIXTURES if not x['accepted']}

def immutable(value, seen=None):
    if seen is None:
        seen=set()
    if value is None or isinstance(value, (str, int, bool)):
        return True
    if not isinstance(value, tuple):
        return False
    if id(value) in seen:
        return True
    seen.add(id(value))
    return all(immutable(x,seen) for x in value)

def lists(value):
    if isinstance(value, tuple):
        return [lists(x) for x in value]
    return value

class DeclarationFixtures(unittest.TestCase):
    pass

def fixture_test(case):
    def test(self):
        if not case['accepted']:
            with self.assertRaises(DeclarationError) as caught:
                loads_declarations(case['text'])
            expected=NEGATIVES[case['name']]
            self.assertEqual(caught.exception.code,expected['code'])
            self.assertTrue(caught.exception.path.startswith(expected['path_prefix']),caught.exception.path)
            return
        index = loads_declarations(case['text'])
        self.assertEqual(hashlib.sha256(index.canonical_json.encode()).hexdigest(), index.sha256)
        for field in ('type_rows','environments','schemes','instantiations'):
            self.assertTrue(immutable(getattr(index,field)),field)
        report = json.dumps(index.report()).lower()
        self.assertIn('declaration',report)
        self.assertNotIn('"status": "accepted"',report)
        for check in case['checks']:
            with self.subTest(check=check):
                if check['op']=='same':
                    self.assertIs(index.same(check['left'],check['right'],scope=check['scope']),check['value'])
                elif check['op']=='use':
                    self.assertEqual(lists(index.instantiated(check['name'])),[check['scheme'],check['arguments'],check['result']])
                elif check['op']=='environment_count':
                    self.assertEqual(len(index.environments),check['value'])
                elif check['op']=='resolve_reject':
                    with self.assertRaises(DeclarationError) as caught:
                        index.resolve(check['reference'],scope=check['scope'])
                    self.assertEqual(caught.exception.code,check['code'])
                    self.assertTrue(caught.exception.path.startswith(check['path_prefix']))
                else:
                    self.fail('unregistered fixture assertion')
    return test

for case in FIXTURES:
    setattr(DeclarationFixtures,'test_'+case['name'],fixture_test(case))

class SnapshotAndBoundary(unittest.TestCase):
    def valid(self):
        return json.loads(next(x['text'] for x in FIXTURES if x['name']=='shared_int_bool_full_vectors'))

    def test_caller_mutation_cannot_change_snapshot(self):
        raw=self.valid();index=check_declarations(raw);before=index.canonical_json
        raw['types']['I']['layout']='#bool';raw['instantiations']['i']['arguments'][0]='B'
        self.assertEqual(index.canonical_json,before)
        self.assertEqual(lists(index.resolve('^I')),['closed','#i64'])
        self.assertEqual(lists(index.instantiated('i'))[1],[['closed','#i64']])
        with self.assertRaises((AttributeError,dataclasses.FrozenInstanceError)):
            index.canonical_json='tampered'

    def test_order_does_not_change_canonical_result(self):
        raw=self.valid();ordered={k:dict(reversed(list(v.items()))) for k,v in reversed(list(raw.items()))}
        a=check_declarations(raw);b=check_declarations(ordered)
        self.assertEqual(a.sha256,b.sha256)
        self.assertEqual(a.type_rows,b.type_rows)
        self.assertEqual(a.environments,b.environments)

    def test_no_executable_acceptance_export(self):
        for name in ('CheckedProgram','check','run','emit','execute'):
            self.assertFalse(hasattr(resource_ir_v8,name),name)

    def test_unknown_query_rejects(self):
        index=check_declarations(self.valid())
        for ref,scope,code,path in [('^Missing',None,'REFERENCE','query.reference'),('Missing',None,'REFERENCE','query.reference'),('^I','Missing','SCOPE','query.scope'),('^A',None,'SCOPE','query.reference')]:
            with self.subTest(ref=ref,scope=scope):
                with self.assertRaises(DeclarationError) as caught:
                    index.resolve(ref,scope=scope)
                self.assertEqual(caught.exception.code,code)
                self.assertEqual(caught.exception.path,path)
        with self.assertRaises(DeclarationError) as caught:
            index.instantiated('missing')
        self.assertEqual(caught.exception.code,'USE')
        self.assertEqual(caught.exception.path,'query.instantiation')

    def test_cyclic_python_input_rejects(self):
        raw=self.valid();raw['types']['Cycle']=raw
        with self.assertRaises(DeclarationError) as caught:
            check_declarations(raw)
        self.assertEqual(caught.exception.code,'INPUT_CYCLE')
        self.assertTrue(caught.exception.path.startswith('declarations'))

    def test_python_nonfinite_rejects(self):
        raw=self.valid();raw['types']['bad']=float('nan')
        with self.assertRaises(DeclarationError) as caught:
            check_declarations(raw)
        self.assertEqual(caught.exception.code,'INPUT_VALUE')

    def test_deep_malformed_json_rejects(self):
        with self.assertRaises(DeclarationError) as caught:
            loads_declarations('['*2000+'0'+']'*2000)
        self.assertEqual(caught.exception.code,'INPUT_DEPTH')

    def test_oversized_input_rejects(self):
        with self.assertRaises(DeclarationError) as caught:
            loads_declarations(' '*(4*1024*1024+1))
        self.assertEqual(caught.exception.code,'INPUT_SIZE')

if __name__=='__main__':
    unittest.main(verbosity=2)
