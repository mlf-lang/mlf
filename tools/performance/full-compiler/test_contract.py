#!/usr/bin/env python3
"""Independent arithmetic fixtures for the four-leg descriptive decision."""
from pathlib import Path
import contextlib,importlib.util,io,json,tempfile,unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('four_leg_analysis',HERE/'analyze.py')
A=importlib.util.module_from_spec(spec);spec.loader.exec_module(A)


def window(cases):
    blocks=[];rows=[]
    for index,(case,order,times) in enumerate(cases):
        blocks.append({'case':case,'order':order})
        for side,seconds in zip(order,times):
            rows.append({'block':index,'case':case,'side':side,'command':{'wall_seconds':seconds}})
    return {'blocks':blocks,'analysis':{'analyzer_sha256':A.R.sha(HERE/'analyze.py'),'validation_analyzer_sha256':A.R.sha(A.READER)}},rows


class DecisionFixtures(unittest.TestCase):
    def decision(self,primary,guards=None):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'result.json'
            argv=['analyze','--compiler','compiler','--output',str(output)]
            if guards is not None:argv+=['--guards','guards']
            def read(path):return primary if str(path)=='compiler' else guards
            with patch.object(A.R,'read_window',side_effect=read),patch('sys.argv',argv),contextlib.redirect_stdout(io.StringIO()):A.main()
            return json.loads(output.read_text())

    def test_known_three_quarters_ratio_in_both_execution_orders(self):
        for order,times in [('ABBA',[4,3,6,8]),('BAAB',[3,4,8,6])]:
            with self.subTest(order=order),patch.object(A.R,'read_window',return_value=window([('compiler',order,times)])):
                result=A.summarize(Path('compiler'))['compiler']
                self.assertAlmostEqual(result['ratio'],0.75)
                self.assertAlmostEqual(result['gain'],0.25)

    def test_positive_primary_requires_complete_guard_window(self):
        result=self.decision(window([('compiler','ABBA',[4,3,6,8])]))
        self.assertTrue(result['positive_primary'])
        self.assertFalse(result['timing_rule_passed'])

    def test_zero_is_not_strictly_positive(self):
        guards=window([('flat_functions-512','ABBA',[4]*4),('higher_order_chain-128','BAAB',[4]*4)])
        result=self.decision(window([('compiler','ABBA',[4]*4)]),guards)
        self.assertFalse(result['positive_primary'])
        self.assertFalse(result['timing_rule_passed'])

    def test_regression_needs_both_relative_and_absolute_thresholds(self):
        guards=window([('flat_functions-512','ABBA',[1,1.02,1.02,1]),('higher_order_chain-128','BAAB',[0.02,0.01,0.01,0.02])])
        result=self.decision(window([('compiler','ABBA',[4,3,6,8])]),guards)
        self.assertTrue(result['timing_rule_passed'])
        guards=window([('flat_functions-512','ABBA',[2,2.2,2.2,2]),('higher_order_chain-128','BAAB',[1]*4)])
        result=self.decision(window([('compiler','ABBA',[4,3,6,8])]),guards)
        self.assertTrue(result['guards']['flat_functions-512']['meaningful_regression'])
        self.assertFalse(result['timing_rule_passed'])

    def test_additional_primary_runs_fail_the_fixed_budget(self):
        with self.assertRaises(ValueError):
            self.decision(window([('compiler','ABBA',[4,3,6,8]),('compiler','BAAB',[3,4,8,6])]))


if __name__=='__main__':unittest.main()
