#!/usr/bin/env python3
"""Exercise the whitespace gate against real commits in disposable repositories."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CHECK = Path(__file__).with_name("check_diff.py").resolve()


class SubmittedDiff(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="mlf-diff-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GITHUB_")}
        self.env.update(GIT_AUTHOR_NAME="Diff test", GIT_COMMITTER_NAME="Diff test",
                        GIT_AUTHOR_EMAIL="test@example.invalid", GIT_COMMITTER_EMAIL="test@example.invalid")
        self.git("init", "-q")
        self.base = self.commit("initial.txt", "clean\n")

    def git(self, *arguments):
        return subprocess.check_output(["git", *arguments], cwd=self.root, env=self.env, text=True).strip()

    def commit(self, name, contents):
        (self.root / name).write_text(contents)
        self.git("add", name)
        self.git("commit", "-qm", name)
        return self.git("rev-parse", "HEAD")

    def check(self, event=None, payload=None):
        env = dict(self.env)
        if event:
            event_file = self.root / ".git/event.json"
            event_file.write_text(json.dumps(payload or {}))
            env.update(GITHUB_ACTIONS="true", GITHUB_EVENT_NAME=event, GITHUB_EVENT_PATH=str(event_file))
        return subprocess.run([sys.executable, "-B", str(CHECK)], cwd=self.root,
                              env=env, text=True, capture_output=True)

    def test_committed_errors_rejected_for_each_ci_event(self):
        bad = self.commit("bad.txt", "trailing whitespace   \n")
        head = self.commit("later.txt", "a later clean commit\n")
        self.assertEqual(self.git("status", "--porcelain"), "")
        for event, payload in [
            ("pull_request", {"pull_request": {"base": {"sha": self.base}, "head": {"sha": head}}}),
            ("merge_group", {"merge_group": {"base_sha": self.base, "head_sha": head}}),
            ("push", {"before": self.base, "after": head}),
            ("push", {"before": "0" * 40, "after": head}),
        ]:
            with self.subTest(event=event, payload=payload):
                result = self.check(event, payload)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("bad.txt", result.stdout)
        self.git("checkout", "-q", "--detach", bad)
        self.assertEqual(self.check("workflow_dispatch").returncode, 2)

    def test_pr_ignores_unrelated_changes_on_advanced_base(self):
        head = self.commit("candidate.txt", "clean PR\n")
        self.git("checkout", "-q", "--detach", self.base)
        advanced = self.commit("base-only.txt", "unrelated trailing whitespace   \n")
        self.git("checkout", "-q", "--detach", head)
        result = self.check("pull_request", {"pull_request": {"base": {"sha": advanced}, "head": {"sha": head}}})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_local_staged_and_unstaged_errors_rejected(self):
        path = self.root / "initial.txt"
        path.write_text("bad local change   \n")
        self.assertEqual(self.check().returncode, 2)
        self.git("add", path.name)
        self.assertEqual(self.check().returncode, 2)
        path.write_text("clean\n")
        self.assertEqual(self.check().returncode, 2)
        self.git("add", path.name)
        self.assertEqual(self.check().returncode, 0)

    def test_missing_ci_range_cannot_pass_as_empty_diff(self):
        for payload in [{}, {"before": self.base, "after": "HEAD"}]:
            with self.subTest(payload=payload):
                self.assertNotEqual(self.check("push", payload).returncode, 0)


if __name__ == "__main__":
    unittest.main()
