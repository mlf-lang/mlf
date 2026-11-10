#!/usr/bin/env python3
"""Fast bookkeeping controls; these do not qualify the Haskell probe."""
from pathlib import Path
import tempfile
import unittest
import run


class Markers(unittest.TestCase):
    def markers(self):
        return '\n'.join('MLF_BACKEND_PHASE '+name+' '+str(i*10)
                         for i, name in enumerate(run.PHASES))

    def test_exact_inventory(self):
        phases = run.parse_phases(self.markers())
        self.assertEqual([p['name'] for p in phases], run.PHASES[1:])
        self.assertTrue(all(p['wall_seconds'] == 1e-8 for p in phases))

    def test_missing_duplicate_and_reordered(self):
        lines = self.markers().splitlines()
        for bad in [lines[:-1], lines+lines[-1:], [lines[1],lines[0],*lines[2:]]]:
            with self.assertRaises(ValueError):
                run.parse_phases('\n'.join(bad))

    def test_backwards_and_invalid_timestamps(self):
        lines = self.markers().splitlines()
        for value in ['0', '-1', '1.5', 'nan', '１２']:
            bad = lines[:-1]+['MLF_BACKEND_PHASE write '+value]
            with self.assertRaises(ValueError):
                run.parse_phases('\n'.join(bad))

    def test_inputs_require_complete_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [root/'unit.mlfci',root/'unit.mlfco']
            for path in paths:
                path.touch()
            self.assertEqual(run.parse_inputs('\n'.join(map(str, paths)),root), paths)
            for values in [[], paths[:1], paths+paths, list(reversed(paths))]:
                with self.assertRaises(ValueError):
                    run.parse_inputs('\n'.join(map(str, values)),root)


if __name__ == '__main__':
    unittest.main()
