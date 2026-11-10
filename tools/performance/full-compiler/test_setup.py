#!/usr/bin/env python3
"""Private host package exposure for the original complete compiler wrapper."""
from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'compiler-shapes/prepare.py'
SPEC = importlib.util.spec_from_file_location('shape_setup', PATH)
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)


class HostExposure(unittest.TestCase):
    def test_io_exposure_is_opt_in_and_private(self):
        for expose in [False, True]:
            with self.subTest(expose=expose), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                calls = []
                with patch.object(P.subprocess, 'check_output', return_value='package-id'):
                    db = P.prepare_host_package(root / 'ghc', root / 'source',
                                                root / 'producer', root / 'deps',
                                                lambda name, cmd: calls.append((name, cmd)),
                                                expose)
                conf = (root / 'deps/package.conf').read_text()
                fields = dict(line.split(': ', 1) for line in conf.splitlines())
                self.assertEqual('MLF.Host.IO' in fields['exposed-modules'].split(), expose)
                self.assertEqual('MLF.Host.IO' in fields['hidden-modules'].split(), not expose)
                self.assertEqual(fields['exposed-modules'].split()[0], 'MLF.Primitive')
                self.assertEqual(db, root / 'deps/package-db')
                self.assertEqual(calls[-1][1][1:3], ['--package-db', db])


if __name__ == '__main__':
    unittest.main()
