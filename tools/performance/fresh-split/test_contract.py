#!/usr/bin/env python3
"""Cheap contract negatives; no compiler process or performance measurement."""
import copy
import unittest
from common import H, fresh, interface, topological, validate
from prepare import fixture_plan


class ContractTests(unittest.TestCase):
    def test_fixture_inventory(self):
        plan = fixture_plan()
        self.assertEqual(len(validate(plan)), 3)

    def test_duplicate_owner(self):
        plan = fixture_plan()
        plan['slices'][1]['modules'] += plan['slices'][0]['modules']
        with self.assertRaisesRegex(RuntimeError, 'nonunique module'):
            validate(plan)

    def test_missing_dependency(self):
        plan = fixture_plan()
        plan['slices'][1]['dependencies'] = []
        with self.assertRaises(RuntimeError):
            validate(plan)

    def test_source_pin(self):
        plan = fixture_plan()
        plan['slices'][0]['modules'][0]['sha256'] = '0'*64
        with self.assertRaisesRegex(RuntimeError, 'source bytes changed'):
            validate(plan)

    def test_cycle(self):
        plan = fixture_plan()
        plan['slices'][0]['dependencies'] = ['entry']
        with self.assertRaisesRegex(RuntimeError, 'cycle'):
            topological(plan['slices'])

    def test_source_total(self):
        plan = fixture_plan()
        plan['source_bytes'] -= 1
        with self.assertRaisesRegex(RuntimeError, 'bytes differ'):
            validate(plan)

    def test_fresh(self):
        report = dict(crate='c',reused_groups=0,inferred_groups=1,
                      groups=[dict(id='g',cached=False)])
        self.assertEqual(fresh(report,'c'),1)
        report['groups'][0]['cached'] = True
        with self.assertRaisesRegex(RuntimeError, 'cache hit'):
            fresh(report,'c')

    def test_reused(self):
        with self.assertRaisesRegex(RuntimeError, 'freshly'):
            fresh(dict(crate='c',reused_groups=1,inferred_groups=0,
                       groups=[dict(id='g',cached=True)]),'c')

    def test_interface(self):
        text = 'crate c\ninterface f\ndependency d /space here/d.mlfci f\nmodule M\n  export x\n'
        interface(text,'c',['M'],{'d':'/space here/d.mlfci'})
        with self.assertRaisesRegex(RuntimeError,'module ownership'):
            interface(text,'c',['N'],{'d':'/space here/d.mlfci'})
        with self.assertRaisesRegex(RuntimeError,'dependency identities'):
            interface(text,'c',['M'],{'d':'/other/d.mlfci'})

    def test_unknown_dependency(self):
        with self.assertRaisesRegex(RuntimeError,'unknown slice'):
            topological([dict(name='a',dependencies=['b'])])


if __name__ == '__main__':
    unittest.main()
