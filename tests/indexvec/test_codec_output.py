"""Check the native wire probe's acceptance and rejection output."""

import hashlib
from types import SimpleNamespace
import unittest

from run import check_codec_output


class CodecOutputTests(unittest.TestCase):
    def setUp(self):
        self.case = SimpleNamespace(name="wire-case", data=b"wire bytes")

    def test_accepts_one_rejection_with_reason(self):
        check_codec_output(self.case, False, b"E invalid magic\n")

    def test_rejects_missing_or_malformed_rejection(self):
        for output in (
            b"", b"garbage\n", b"OK\n", b"E invalid magic", b"E\n", b"E \n", b"E \t\n",
            b"E invalid magic\r\n", b"E invalid magic\ngarbage\n", b"E invalid magic\n\n",
        ):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "one rejection line"):
                check_codec_output(self.case, False, output)

    def test_acceptance_still_checks_ok_header_and_sha(self):
        digest = hashlib.sha256(self.case.data).hexdigest().encode()
        check_codec_output(self.case, True, b"OK\n0\n" + digest + b"\n")
        with self.assertRaisesRegex(ValueError, "acceptance differs"):
            check_codec_output(self.case, True, b"E invalid magic\n" + digest + b"\n")
        with self.assertRaisesRegex(ValueError, "roundtrip exactly"):
            check_codec_output(self.case, True, b"OK\n" + b"0" * 64 + b"\n")


if __name__ == "__main__":
    unittest.main()
