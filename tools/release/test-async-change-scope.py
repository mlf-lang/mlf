#!/usr/bin/env python3
"""Cheap controls for the actual explicit async-parity policy and receipt."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("async-change-scope.py")
spec = importlib.util.spec_from_file_location("async_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)
SHA = "a" * 40


def event(labels=None):
    return {"pull_request": {"base": {"sha": "b" * 40}, "head": {"sha": SHA},
                             "labels": [] if labels is None else labels}}


class Selection(unittest.TestCase):
    def test_default_pr_is_explicit_nonexecution(self):
        result = scope.decide(".", "pull_request", event(), SHA)
        self.assertFalse(result["required"])
        self.assertEqual(result["reason"], "pull-request-default-opt-out")
        self.assertEqual(result["parity_execution"], "not-executed")
        self.assertTrue(result["complete"])

    def test_explicit_opt_in_pr_runs_even_without_source_diff(self):
        result = scope.decide(".", "pull_request", event([{"name": "ci:async-parity"}]), SHA)
        self.assertTrue(result["required"])
        self.assertEqual(result["reason"], "pull-request-explicit-opt-in")
        self.assertEqual(result["parity_execution"], "required")

    def test_unrelated_or_similar_labels_do_not_opt_in(self):
        for name in ("bug", "ci:async-parity-extra", "CI:ASYNC-PARITY", " ci:async-parity"):
            self.assertFalse(scope.decide(".", "pull_request", event([{"name": name}]), SHA)["required"])

    def test_main_manual_queue_and_unknown_events_keep_coverage(self):
        for name in ("push", "workflow_dispatch", "merge_group", "unknown", ""):
            for payload in ({}, event(), event([{"name": "ci:async-parity"}])):
                self.assertTrue(scope.decide(".", name, payload, SHA)["required"])

    def test_missing_invalid_labels_fail_closed(self):
        values = [{}, {"pull_request": None}]
        for labels in (None, {}, "ci:async-parity", [None], [{}], [{"name": 12}]):
            value = event(); value["pull_request"]["labels"] = labels; values.append(value)
        missing = event(); del missing["pull_request"]["labels"]; values.append(missing)
        for value in values:
            self.assertTrue(scope.decide(".", "pull_request", value, SHA)["required"])

    def test_invalid_commit_identity_fails_closed(self):
        for field in ("head", "base"):
            value = event(); value["pull_request"][field]["sha"] = "bad"
            self.assertTrue(scope.decide(".", "pull_request", value, SHA)["required"])
        self.assertTrue(scope.decide(".", "pull_request", event(), "bad")["required"])

    def test_label_addition_and_removal_change_only_execution_policy(self):
        value = event(); opted = copy.deepcopy(value)
        opted["pull_request"]["labels"] = [{"name": "ci:async-parity"}]
        self.assertEqual([scope.decide(".", "pull_request", v, SHA)["required"]
                          for v in (value, opted, value)], [False, True, False])

    def test_cli_receipt_and_output_match_for_skip_opt_in_and_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for payload, required in ((event(), False), (event([{"name": "ci:async-parity"}]), True), (None, True)):
                source, receipt, output = root / "event.json", root / "decision.json", root / "output"
                source.write_text(json.dumps(payload) if payload is not None else "truncated {")
                output.write_text("")
                run = subprocess.run(["python3", str(SCRIPT), "--event-name", "pull_request",
                                      "--event-path", str(source), "--checkout-sha", SHA,
                                      "--output", str(receipt), "--github-output", str(output)],
                                     check=True, stdout=subprocess.PIPE, text=True)
                self.assertEqual(json.loads(receipt.read_text())["required"], required)
                self.assertEqual(output.read_text(), "required=" + str(required).lower() + "\n")
                self.assertEqual("NOT EXECUTED" in run.stdout, not required)


if __name__ == "__main__":
    unittest.main(verbosity=2)
