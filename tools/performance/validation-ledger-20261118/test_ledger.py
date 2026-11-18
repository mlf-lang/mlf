import unittest
from ledger import parse,eligible,main
class Tests(unittest.TestCase):
 def test_real_archive(self):
  r=main('observer-results.json');self.assertEqual(r['all_sidecars_verified'],71);self.assertEqual(len(r['reports']),14)
  self.assertEqual(r['reports']['forced-kind.events']['status'],'unavailable')
  self.assertEqual(r['reports']['sparse-unobserved.events']['status'],'sparse-unobserved')
  self.assertGreater(r['reports']['cached-kind-edge.events']['unkeyed_edge_frames'],0)
  self.assertFalse(r['production_eligible'])
 def test_order(self):
  with self.assertRaises(ValueError):parse('entry:kind-fact\t1\nentry:require\t2\nsuccess:kind-fact\t1\n')
 def test_truncation(self):
  with self.assertRaises(ValueError):parse('entry:kind-fact\t1\n')
 def test_outside(self):
  with self.assertRaises(ValueError):parse('alias:absent\t1\n')
 def test_cap(self):
  with self.assertRaises(ValueError):parse('entry:kind-fact\t1\n'+'node:present\t1\n'*8192+'success:kind-fact\t1\n')
 def gate(self,dep,chg,**kw):return eligible(dep,chg,**dict(same_owner=True,prepasses_passed=True,complete_write_log=True,**kw))
 def test_alias_absence_invalidates(self):self.assertFalse(self.gate([('alias',10)], [('alias',10)]))
 def test_ancestor_invalidates_global(self):self.assertFalse(self.gate([('global-binding',0)],[('global-binding',0)]))
 def test_incarnation_not_numeric_identity(self):self.assertFalse(self.gate([('node-incarnation',3)],[('node-incarnation',3)]))
 def test_binder_change(self):self.assertFalse(self.gate([('binder',2)],[('binder',2)]))
 def test_prepass_before_later_payload(self):
  class Poison:
   def __hash__(self):raise AssertionError('forced before prefix')
  self.assertFalse(eligible([Poison()],[],same_owner=True,prepasses_passed=False,complete_write_log=True))
 def test_unknown_write_or_owner(self):
  for owner,log in [(False,True),(True,False)]:self.assertFalse(eligible([],[],same_owner=owner,prepasses_passed=True,complete_write_log=log))
 def test_sparse(self):self.assertFalse(self.gate([],[],dense_mode=False))
 def test_foreign_field_no_payload(self):self.assertTrue(self.gate([('kind-origin',2)],[('name-origin',4)]))
 def test_unknown_rule(self):
  with self.assertRaises(ValueError):parse('entry:invented\t1\nsuccess:invented\t1\n')
 def test_bad_global_context(self):
  with self.assertRaises(ValueError):parse('entry:kind-fact\t1\nsuccess:global-euler\t999\nsuccess:kind-fact\t1\n')
 def test_archive_corruption(self):
  import tempfile,json,pathlib
  original=json.loads(pathlib.Path('observer-results.json').read_text())
  for duplicate in [True,False]:
   j=json.loads(json.dumps(original))
   if duplicate:j['sidecars'].append(j['sidecars'][0])
   else:j['sidecars'][0]['sha256']='0'*64
   with tempfile.TemporaryDirectory() as d:
    p=pathlib.Path(d)/'bad.json';p.write_text(json.dumps(j))
    with self.assertRaises(ValueError):main(p)
if __name__=='__main__':unittest.main()
