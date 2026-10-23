#!/usr/bin/env python3
"""Bounded real-Git and malformed-input controls for the production selector."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("async-change-scope.py")
spec = importlib.util.spec_from_file_location("async_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class Selection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Scope fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        for path in ("README.md", "docs/topic.md", "runtime/example.c"):
            self.write(path)
        self.base = self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args],
                                       stderr=subprocess.PIPE).decode().strip()

    def write(self, path, text="fixture\n"):
        target = self.repo / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "fixture", "--allow-empty")
        return self.git("rev-parse", "HEAD")

    def decision(self, head=None, base=None, checkout=None, event="pull_request"):
        head = head or self.git("rev-parse", "HEAD")
        payload = {"pull_request": {"base": {"sha": base or self.base},
                                    "head": {"sha": head}}}
        return scope.decide(self.repo, event, payload, checkout or head)

    def test_verified_unrelated_and_receipt(self):
        for path in ("docs/topic.md", "papers/note.pdf", "examples/identity.emlf",
                     "benchmarks/fasta/mlf/main.emlf", "CHANGELOG.md"):
            self.write(path, "changed\n")
        result = self.decision(self.commit())
        self.assertFalse(result["required"])
        self.assertEqual(result["parity_execution"], "not-executed")
        self.assertEqual(result["reason"], "verified-unrelated-pr-diff")
        self.assertEqual(len(result["changes"]), 5)
        self.assertRegex(result["diff_sha256"], r"^[0-9a-f]{64}$")

    def test_full_dependency_closure_and_unknown_paths(self):
        paths = ["bootstrap/Main.emlf", "libraries/mlf-frontend/Module.emlf",
                 "libraries/mlf-async/Async/Task.emlf", "package/Main.emlf",
                 "runtime/example.c", "scripts/bootstrap-async.sh", "VERSION",
                 "mlf-package.json", "mlf.lock", ".gitattributes",
                 ".github/workflows/ci.yml", ".github/smoke-seed-linux.env",
                 "tools/release/fetch-seed.sh", "tools/release/test-async-task.sh",
                 "tools/new-build-tool.py", "tests/native/completion_cell_tests.c",
                 "tests/async-package/Main.emlf", "tests/async-process/fixture.c",
                 "tests/async-task/Main.emlf", "tests/fixtures/async-completion/check.sh",
                 "new-compiler-location/Main.emlf", "docs-lookalike/file.md"]
        for path in paths:
            with self.subTest(path=path):
                self.git("reset", "--hard", self.base)
                self.write(path, "dependency changed\n")
                self.assertTrue(self.decision(self.commit())["required"])

    def test_deleted_dependency_runs(self):
        (self.repo / "runtime/example.c").unlink()
        self.assertTrue(self.decision(self.commit())["required"])

    def test_deleted_unrelated_file_can_skip(self):
        (self.repo / "docs/topic.md").unlink()
        self.assertFalse(self.decision(self.commit())["required"])

    def test_rename_both_directions_considers_old_and_new_paths(self):
        for old, new in (("docs/topic.md", "runtime/moved.c"),
                         ("runtime/example.c", "docs/moved.md")):
            with self.subTest(old=old):
                self.git("reset", "--hard", self.base)
                self.git("mv", old, new)
                result = self.decision(self.commit())
                self.assertTrue(result["required"])
                self.assertEqual({x["path"] for x in result["changes"]}, {old, new})

    def test_type_change_is_uncertain(self):
        target = self.repo / "docs/topic.md"
        target.unlink()
        target.symlink_to("../runtime/example.c")
        result = self.decision(self.commit())
        self.assertTrue(result["required"])
        self.assertEqual(result["reason"], "uncertain-diff-run-full")

    def test_control_character_in_allowed_path_runs(self):
        self.write("docs/line\nbreak.md")
        self.assertTrue(self.decision(self.commit())["required"])

    def test_main_manual_merge_queue_and_unknown_events_run(self):
        self.write("docs/topic.md", "changed\n")
        head = self.commit()
        for event in ("push", "workflow_dispatch", "merge_group", "unknown", ""):
            with self.subTest(event=event):
                self.assertTrue(self.decision(head, event=event)["required"])

    def test_missing_or_invalid_event_and_commit_runs(self):
        for event in ({}, {"pull_request": None},
                      {"pull_request": {"base": {"sha": "bad"}, "head": {"sha": self.base}}}):
            self.assertTrue(scope.decide(self.repo, "pull_request", event, self.base)["required"])
        self.assertTrue(self.decision(base="f" * 40)["required"])
        self.assertTrue(self.decision(checkout="f" * 40)["required"])

    def test_unrelated_diverged_base_uses_pr_merge_base(self):
        self.git("checkout", "-qb", "feature")
        self.write("docs/topic.md", "feature\n")
        head = self.commit()
        self.git("checkout", "main")
        self.write("runtime/example.c", "base advance\n")
        base = self.commit()
        self.git("merge", "--no-ff", "-qm", "test merge", "feature")
        checkout = self.git("rev-parse", "HEAD")
        result = self.decision(head, base, checkout)
        self.assertFalse(result["required"])
        self.assertEqual(result["merge_base_sha"], self.base)
        self.assertTrue(self.decision(head, base, head)["required"],
                        "An unverified stale checkout cannot skip")

    def test_git_failure_runs(self):
        with patch.object(scope.subprocess, "run", side_effect=OSError("git unavailable")):
            self.assertTrue(self.decision(self.base)["required"])

    def test_incomplete_oversized_and_invalid_diff_rejected(self):
        for raw in (b"M\0docs/topic.md", b"M\0", b"R100\0docs/a\0docs/b\0",
                    b"M\0docs/\xff\0", b"T\0docs/a\0", b"A" * (scope.MAX_DIFF_BYTES + 1)):
            with self.subTest(raw=raw[:30]):
                with self.assertRaises((ValueError, UnicodeError)):
                    scope.parse_diff(raw)

    def test_cli_invalid_event_runs_and_writes_receipt_before_output(self):
        event = self.repo / "event.json"
        event.write_text("truncated {")
        receipt, output = self.repo / "decision.json", self.repo / "outputs"
        subprocess.run(["python3", str(SCRIPT), "--repo", str(self.repo),
                        "--event-name", "pull_request", "--event-path", str(event),
                        "--checkout-sha", self.base, "--output", str(receipt),
                        "--github-output", str(output)], check=True, stdout=subprocess.PIPE)
        self.assertTrue(json.loads(receipt.read_text())["required"])
        self.assertEqual(output.read_text(), "required=true\n")

    def test_cli_verified_skip_emits_false_and_explicit_nonexecution(self):
        self.write("docs/topic.md", "prose only\n")
        head = self.commit()
        event = self.repo / "event.json"
        event.write_text(json.dumps({"pull_request": {"base": {"sha": self.base},
                                                     "head": {"sha": head}}}))
        receipt, output = self.repo / "decision.json", self.repo / "outputs"
        completed = subprocess.run(["python3", str(SCRIPT), "--repo", str(self.repo),
                                    "--event-name", "pull_request", "--event-path", str(event),
                                    "--checkout-sha", head, "--output", str(receipt),
                                    "--github-output", str(output)], check=True, stdout=subprocess.PIPE)
        self.assertEqual(json.loads(receipt.read_text())["parity_execution"], "not-executed")
        self.assertEqual(output.read_text(), "required=false\n")
        self.assertIn(b"NOT EXECUTED", completed.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
