"""Corruption controls for complete retained native/model trace reconciliation."""
import argparse
import copy
import json
import pathlib
import sys
import unittest

p=argparse.ArgumentParser(add_help=False)
p.add_argument('--receipt',type=pathlib.Path)
args,rest=p.parse_known_args()
sys.argv=[sys.argv[0],*rest]
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import run_native
RECEIPT=json.loads(args.receipt.read_text()) if args.receipt else None

@unittest.skipIf(RECEIPT is None, 'requires explicit fresh --receipt path; see README')
class EventContract(unittest.TestCase):
    def setUp(self):
        self.native=copy.deepcopy(RECEIPT['native']['events'])
        self.model=copy.deepcopy(RECEIPT['python_reference']['events'])
        self.program=copy.deepcopy(RECEIPT['program'])
        self.marker=next(i for i,e in enumerate(self.native) if e['event']=='ir_force_result')
    def check(self):return run_native.compare_event_streams(self.native,self.model,self.program)
    def test_all_raw_events_accounted_for(self):
        r=self.check()
        self.assertEqual(r['native_only_force_markers_checked'],sum(e['event']=='ir_force_result' for e in self.native))
        self.assertEqual(r['raw_native_events'],len(self.native))
        self.assertEqual(r['model_common_events'],len(self.model))
    def test_wrong_actual_owner_rejects(self):
        self.native[self.marker]['owner']+=100
        with self.assertRaises(run_native.NativeError):self.check()
    def test_wrong_ir_binding_rejects(self):
        self.native[self.marker]['source_variable']='wrong'
        with self.assertRaises(run_native.NativeError):self.check()
    def test_missing_marker_rejects(self):
        self.native.pop(self.marker)
        with self.assertRaises(run_native.NativeError):self.check()
    def test_extra_marker_rejects(self):
        self.native.insert(self.marker+1,copy.deepcopy(self.native[self.marker]))
        with self.assertRaises(run_native.NativeError):self.check()
    def test_unaccounted_common_payload_change_rejects(self):
        i=next(i for i,e in enumerate(self.native) if e['event']=='scalar_value')
        self.native[i]['value']=0
        with self.assertRaises(run_native.NativeError):self.check()
    def test_wrong_frame_rejects(self):
        self.native[self.marker]['frame']=999
        with self.assertRaises(run_native.NativeError):self.check()
    def test_extra_marker_key_rejects(self):
        self.native[self.marker]['ignored']=True
        with self.assertRaises(run_native.NativeError):self.check()

if __name__=='__main__':unittest.main()
