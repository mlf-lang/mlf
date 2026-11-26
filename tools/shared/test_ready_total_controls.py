#!/usr/bin/env python3
"""Keep the thunk shape check aligned with emitted allocation entry points."""
import unittest

from test_ready_total import loop_allocations


def worker(calls):
    return ('define private ptr @mlf.worker.0(ptr %a, ptr %b, ptr %c) noinline {\n'
            + ''.join(f'  %v{i} = call ptr @{name}(ptr null, i64 1)\n'
                      for i, name in enumerate(calls))
            + '  %next = musttail call ptr @mlf.worker.0(ptr %a, ptr %b, ptr %c)\n'
            + '  ret ptr %next\n}\n')


class ThunkAllocationControls(unittest.TestCase):
    def test_direct_and_captured_allocations(self):
        self.assertEqual(loop_allocations(worker([
            'mlf.allocate.thunk', 'mlf.allocate.thunk.fill.1',
            'mlf.allocate.thunk.fill.16', 'mlf_thunk_new',
        ]))['thunk_allocations'], 4)

    def test_nonallocation_names_do_not_count(self):
        self.assertEqual(loop_allocations(worker([
            'mlf.thunk_new', 'mlf_thunk_newer', 'mlf.allocate.thunkish',
            'mlf.allocate.thunk.fill.word', 'mlf.force.worker',
        ]))['thunk_allocations'], 0)

    def test_allocations_outside_the_recursive_worker_do_not_count(self):
        helper = ('define private ptr @mlf.helper(ptr %a) {\n'
                  '  %value = call ptr @mlf.allocate.thunk(ptr %a, i64 0)\n'
                  '  ret ptr %value\n}\n')
        self.assertEqual(loop_allocations(helper + worker([]))['thunk_allocations'], 0)


if __name__ == '__main__':
    unittest.main()
