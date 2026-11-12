"""Synthetic record tests only: these do not execute any Haskell fixture."""
import copy
import json
import unittest
from validate_host_outputs import (OPEN_HASHES, SOURCE_COMMIT, ValidationError,
                                   compare_records, digest, strict_json)

FIXTURE = b"synthetic source bytes, not executable Haskell\n"
MAP = json.dumps({"cases": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}).encode()
STDOUT = 'PASS\ta\t"one"\nPASS\tb\t"two\\nlines"\nPASS\tc\t"three"\nSUMMARY\t3\t3\n'


def records():
    return {v: {"schema_version": 1, "variant": v, "fixture_sha256": digest(FIXTURE),
                "case_map_sha256": digest(MAP), "baseline_source_commit": SOURCE_COMMIT,
                "openfragment_sha256": sha, "build_kind": "ordinary",
                "shared_build_inputs_sha256": "a" * 64,
                "evidence_kind": "synthetic-test-output", "stdout": STDOUT,
                "stdout_sha256": digest(STDOUT.encode())} for v, sha in OPEN_HASHES.items()}


def replace_stdout(rs, stdout):
    rs["spine-only"]["stdout"] = stdout
    rs["spine-only"]["stdout_sha256"] = digest(stdout.encode())


class OutputValidationTests(unittest.TestCase):
    def reject(self, rs, fixture=FIXTURE, case_map=MAP):
        with self.assertRaises(ValidationError):
            compare_records(fixture, case_map, rs)

    def test_complete_matching_synthetic_records_pass_content_only(self):
        result = compare_records(FIXTURE, MAP, records())
        self.assertTrue(result["content_comparison_passed"])
        self.assertTrue(result["synthetic_inputs"])
        for key in ("actual_haskell_execution_established", "build_provenance_authenticated",
                    "artifact_equivalence_established", "performance_claim_established", "resume_authorized"):
            self.assertFalse(result[key])

    def test_missing_case_not_hidden_by_intersection(self):
        rs = records(); replace_stdout(rs, STDOUT.replace('PASS\tb\t"two\\nlines"\n', ''))
        self.reject(rs)

    def test_duplicate_or_reordered_case_rejected(self):
        for text in (STDOUT.replace('PASS\tb\t', 'PASS\ta\t'),
                     STDOUT.replace('PASS\ta\t', 'PASS\tz\t')):
            rs = records(); replace_stdout(rs, text); self.reject(rs)

    def test_truncated_output_and_bad_summary_rejected(self):
        for text in (STDOUT[:-1], STDOUT.replace('SUMMARY\t3\t3', 'SUMMARY\t3\t2'),
                     STDOUT.replace('SUMMARY\t3\t3\n', '')):
            rs = records(); replace_stdout(rs, text); self.reject(rs)

    def test_fail_and_extra_diagnostic_lines_rejected(self):
        for text in (STDOUT.replace('PASS\ta', 'FAIL\ta'), STDOUT + 'diagnostic\n'):
            rs = records(); replace_stdout(rs, text); self.reject(rs)

    def test_changed_actual_payload_rejected_even_if_all_pass(self):
        rs = records(); replace_stdout(rs, STDOUT.replace('"three"', '"different"')); self.reject(rs)

    def test_fixture_or_case_map_digest_mismatch_rejected(self):
        self.reject(records(), fixture=FIXTURE + b" ")
        self.reject(records(), case_map=MAP + b" ")

    def test_wrong_variant_hash_or_label_rejected(self):
        for key, value in (("openfragment_sha256", OPEN_HASHES["baseline"]), ("variant", "baseline")):
            rs = records(); rs["spine-only"][key] = value; self.reject(rs)

    def test_profiled_or_different_build_inputs_rejected(self):
        for key, value in (("build_kind", "profiled"), ("shared_build_inputs_sha256", "b" * 64)):
            rs = records(); rs["spine-only"][key] = value; self.reject(rs)

    def test_missing_variant_and_bad_source_pin_rejected(self):
        rs = records(); del rs["delete-only"]; self.reject(rs)
        rs = records(); rs["baseline"]["baseline_source_commit"] = "f" * 40; self.reject(rs)

    def test_unknown_or_mixed_evidence_kind_rejected(self):
        for kind in ("", "trusted-real-execution", "reported-host-output"):
            rs = records(); rs["spine-only"]["evidence_kind"] = kind; self.reject(rs)

    def test_empty_or_duplicate_case_map_rejected(self):
        for value in ({"cases": []}, {"cases": [{"id": "a"}, {"id": "a"}]}):
            self.reject(records(), case_map=json.dumps(value).encode())

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValidationError):
            strict_json('{"variant":"baseline","variant":"spine-only"}')

    def test_stale_stdout_hash_rejected(self):
        rs = records(); rs["spine-only"]["stdout_sha256"] = "0" * 64; self.reject(rs)

    def test_boolean_is_not_a_schema_version(self):
        rs = records(); rs["spine-only"]["schema_version"] = True; self.reject(rs)

    def test_reported_records_do_not_authenticate_haskell_execution(self):
        rs = records()
        for row in rs.values():
            row["evidence_kind"] = "reported-host-output"
        result = compare_records(FIXTURE, MAP, rs)
        self.assertFalse(result["synthetic_inputs"])
        self.assertFalse(result["actual_haskell_execution_established"])
        self.assertFalse(result["build_provenance_authenticated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
