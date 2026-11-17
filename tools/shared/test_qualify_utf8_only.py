"""Pure single-target dispatch and qualification-boundary controls.

No compiler, interpreter, subprocess or full original-direct execution.
"""
import copy
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import qualify_utf8_only as Q


class QualificationControls(unittest.TestCase):
    def good_producer(self):
        return dict(
            complete=True,
            typecheck_only=False,
            producer_host="GHC",
            optimization="0",
        )

    def test_requires_actual_o0_executable_producer(self):
        Q.require_o0(self.good_producer())
        for field, wrong_values in {
            "complete": [False, 1, None],
            "typecheck_only": [True, 0, None],
            "producer_host": ["native", None],
            "optimization": ["2", 0, None],
        }.items():
            for value in wrong_values:
                changed = self.good_producer()
                changed[field] = value
                with self.subTest(field=field, value=value):
                    with self.assertRaises(RuntimeError):
                        Q.require_o0(changed)

    def test_missing_producer_fields_rejected(self):
        for field in self.good_producer():
            changed = self.good_producer()
            del changed[field]
            with self.assertRaises(RuntimeError):
                Q.require_o0(changed)

    def test_inputs_rechecked_from_actual_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input"
            path.write_bytes(b"original")
            inputs = {str(path): Q.digest(b"original")}
            Q.check_inputs(inputs)
            path.write_bytes(b"changed")
            with self.assertRaises(RuntimeError):
                Q.check_inputs(inputs)
            path.unlink()
            with self.assertRaises(RuntimeError):
                Q.check_inputs(inputs)

    def dispatch(self, returncode=0):
        runner = mock.Mock()
        runner.run.return_value = types.SimpleNamespace(returncode=returncode)
        composed = types.SimpleNamespace(CommandRunner=mock.Mock(
            return_value=runner))
        entry = types.SimpleNamespace(compose=mock.Mock(return_value=composed))
        direct = types.SimpleNamespace(
            ROOT=Path("/fixed/source"),
            main=mock.Mock(side_effect=AssertionError("direct.main forbidden")),
        )
        worker, crc, pins = object(), object(), {"worker": "pinned"}
        record, save = {"commands": []}, mock.Mock()
        output = Path("/fresh/out")
        receipt = Path("/build/receipt.json")
        clang = Path("/toolchain/clang")
        args = (
            entry, worker, crc, direct, pins, output, record, save,
            receipt, clang,
        )
        return args, runner, composed, direct

    def test_exact_single_target_uses_composition_not_original_main(self):
        args, runner, composed, direct = self.dispatch()
        argv = Q.run_one(*args)
        entry, worker, crc, _, pins, output, record, save, receipt, clang = args
        entry.compose.assert_called_once_with(direct, crc, worker, pins)
        composed.CommandRunner.assert_called_once_with(
            direct.ROOT, output, record, save)
        expected = [
            Q.sys.executable, "-B", str(Q.HERE / "test_utf8_length.py"),
            "--build-receipt", str(receipt),
            "--clang", str(clang),
            "--output", str(output / "utf8-length"),
        ]
        self.assertEqual(argv, expected)
        runner.run.assert_called_once_with("utf8-length", expected, timeout=600)
        direct.main.assert_not_called()

    def test_nonzero_and_bool_result_rejected(self):
        for status in (1, -9, False, True, None):
            args, runner, composed, direct = self.dispatch(status)
            with self.subTest(status=status), self.assertRaises(RuntimeError):
                Q.run_one(*args)
            direct.main.assert_not_called()

    def test_managed_failure_propagates(self):
        args, runner, composed, direct = self.dispatch()
        runner.run.side_effect = RuntimeError("managed cancellation")
        with self.assertRaisesRegex(RuntimeError, "managed cancellation"):
            Q.run_one(*args)
        direct.main.assert_not_called()

    def test_single_result_rejects_inventory_before_reading_files(self):
        command = {
            "name": "utf8-length",
            "argv": ["expected"],
            "state": "passed",
            "exit_code": 0,
        }
        bad_records = [
            {},
            {"commands": []},
            {"commands": [command, command]},
            {"commands": [dict(command, name="bulk-crc")]},
            {"commands": [dict(command, argv=["changed"])]},
            {"commands": [dict(command, state="failed")]},
            {"commands": [dict(command, exit_code=False)]},
        ]
        for key in (
            "error", "evidence_error", "cleanup_unverified",
            "leader_reap_unverified",
        ):
            changed = dict(command)
            changed[key] = None
            bad_records.append({"commands": [changed]})
        for record in bad_records:
            with self.subTest(record=record), self.assertRaises(RuntimeError):
                Q.validate_single_result(
                    copy.deepcopy(record), None, Path("/not-read"), ["expected"],
                )

    def test_fresh_destination_refuses_existing_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "receipt.json"
            receipt.write_bytes(b"not loaded")
            binaries = root / "bin"
            binaries.mkdir()
            output = root / "out"
            output.mkdir()
            marker = output / "preserve"
            marker.write_bytes(b"original")
            with self.assertRaisesRegex(RuntimeError, "fresh qualification"):
                Q.qualify(receipt, binaries, output, "not-resolved")
            self.assertEqual(marker.read_bytes(), b"original")




class SourceBasisControls(unittest.TestCase):
    def test_tree_parser_rejects_nonregular_escaped_duplicate_and_empty_inputs(self):
        import qualification_source as S
        sha = b"1"*40
        good = b"100644 blob "+sha+b"\tproduction.hs\0"
        self.assertEqual(set(S.parse_tree(good)), {"production.hs"})
        for raw in (b"", good+good, good.replace(b"100644", b"120000"),
                    good.replace(b"production.hs", b"../escape"),
                    good.replace(b"production.hs", b"/escape"),
                    good.replace(b"blob", b"tree")):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                S.parse_tree(raw)

    def test_source_gate_requires_one_exact_parent_and_closed_delta(self):
        import os
        import qualification_source as S
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"unchanged production\n"
            (root/"production.hs").write_bytes(raw)
            (root/"candidate.py").write_bytes(b"candidate\n")
            def git_blob(data):
                return S.hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            base_tree = ("100644 blob "+git_blob(raw)+"\tproduction.hs\0").encode()
            candidate_tree = base_tree+("100644 blob "+git_blob(b"candidate\n")+"\tcandidate.py\0").encode()
            expected = "a"*40
            environment = dict(GITHUB_SHA=expected, GITHUB_REF=S.BRANCH,
                               GITHUB_EVENT_NAME="push", GITHUB_REPOSITORY="mlf-lang/mlf")
            def response(*args):
                if args == ("rev-parse", "HEAD"): return (expected+"\n").encode()
                if args == ("rev-parse", S.BASE+"^{tree}"): return (S.BASE_TREE+"\n").encode()
                if args == ("rev-list", "--parents", "-n", "1", expected):
                    return (expected+" "+S.BASE+"\n").encode()
                if args == ("ls-tree", "-rz", "--full-tree", S.BASE): return base_tree
                if args == ("ls-tree", "-rz", "--full-tree", expected): return candidate_tree
                if args == ("diff", "--name-only", "-z", "HEAD", "--"): return b""
                raise AssertionError(args)
            with mock.patch.object(S,"ROOT",root), mock.patch.object(S,"ALLOW",["candidate.py"]), \
                 mock.patch.object(S,"git",side_effect=response), mock.patch.dict(os.environ,environment):
                result = S.snapshot(root/"positive.json")
                self.assertTrue(result["complete"])
                self.assertTrue(result["tracked_inputs"]["production.hs"]["baseline_identical"])
                self.assertFalse(result["tracked_inputs"]["candidate.py"]["baseline_identical"])
                for key, value in (("GITHUB_SHA","wrong"), ("GITHUB_REF","refs/heads/main"),
                                   ("GITHUB_EVENT_NAME","pull_request"), ("GITHUB_REPOSITORY","foreign/repo")):
                    with mock.patch.dict(os.environ,{key:value}), self.assertRaises(RuntimeError):
                        S.snapshot(root/("reject-"+key+".json"))
                with mock.patch.object(S,"ALLOW",[]), self.assertRaises(RuntimeError):
                    S.snapshot(root/"wrong-delta.json")
                def wrong_parent(*args):
                    if args[:1] == ("rev-list",): return (expected+" "+"b"*40+"\n").encode()
                    return response(*args)
                with mock.patch.object(S,"git",side_effect=wrong_parent), self.assertRaises(RuntimeError):
                    S.snapshot(root/"wrong-parent.json")
                (root/"production.hs").write_bytes(b"changed production\n")
                with self.assertRaises(RuntimeError):
                    S.snapshot(root/"changed-production.json")

if __name__ == "__main__":
    unittest.main()
