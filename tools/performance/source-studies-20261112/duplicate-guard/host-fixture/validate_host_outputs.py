"""Compare complete future host-fixture outputs; never run/build the fixture.

Records are content claims, not authenticated build/execution or cleanup proof.
The unit tests use synthetic records only. No real Haskell result is supplied.
"""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_COMMIT = "f9bdb40a659bfdff4cbb782d438afbb0417dd2e1"
OPEN_HASHES = {
    "baseline": "e392aae043afc2c13cda16e00caa6a3562dc5180d78dce27f699da7046c57c8b",
    "delete-only": "2fce9e0bc418994b321ea453034b5e2ee69b3ca2b4e5b929f0f826fea62c09ae",
    "spine-only": "76539b0c774841050c591d258ec3ed34b050bcf8bb727ca018cea50d2118671c",
}


class ValidationError(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs)


def case_ids(case_map):
    require(isinstance(case_map, dict), "case map must be an object")
    rows = case_map.get("cases")
    require(isinstance(rows, list) and rows, "nonempty case list required")
    ids = []
    for row in rows:
        require(isinstance(row, dict), "case row must be an object")
        name = row.get("id")
        require(isinstance(name, str) and bool(name) and
                all(c.isascii() and (c.isalnum() or c in "-_./") for c in name),
                "invalid case ID")
        ids.append(name)
    require(len(set(ids)) == len(ids), "duplicate case ID in case map")
    return ids


def parse_stdout(stdout, expected):
    require(isinstance(stdout, str) and stdout.endswith("\n"), "complete LF-terminated stdout required")
    require("\r" not in stdout, "unexpected CR in stdout")
    lines = stdout[:-1].split("\n")
    require(len(lines) == len(expected) + 1, "missing/extra observation or summary line")
    observations = []
    for line, name in zip(lines[:-1], expected):
        parts = line.split("\t")
        require(len(parts) == 3, "observation must have exactly three tab-separated fields")
        status, actual_id, payload = parts
        require(status == "PASS", "failed or unknown observation status")
        require(actual_id == name, "missing, duplicated, unknown or reordered case: " + actual_id)
        require(len(payload) >= 2 and payload[0] == '"' and payload[-1] == '"',
                "opaque observation must be a shown single-line string")
        observations.append(payload)
    require(lines[-1] == "SUMMARY\t" + str(len(expected)) + "\t" + str(len(expected)),
            "summary counts must match complete passing case list")
    return observations


def compare_records(fixture_bytes, case_map_bytes, records):
    expected = case_ids(strict_json(case_map_bytes))
    require(isinstance(records, dict) and set(records) == set(OPEN_HASHES),
            "exactly baseline, delete-only and spine-only records required")
    reference = None
    shared = None
    evidence_kind = None
    record_hashes = {}
    for variant in OPEN_HASHES:
        record = records[variant]
        require(isinstance(record, dict), "record must be an object")
        require(type(record.get("schema_version")) is int and record["schema_version"] == 1,
                "unsupported record schema")
        require(record.get("variant") == variant, "record variant mislabeled")
        require(record.get("fixture_sha256") == digest(fixture_bytes), "fixture digest mismatch")
        require(record.get("case_map_sha256") == digest(case_map_bytes), "case-map digest mismatch")
        require(record.get("baseline_source_commit") == SOURCE_COMMIT, "baseline source pin mismatch")
        require(record.get("openfragment_sha256") == OPEN_HASHES[variant], "wrong variant source digest")
        require(record.get("build_kind") == "ordinary", "profiled/instrumented/mixed build not accepted")
        inputs = record.get("shared_build_inputs_sha256")
        require(isinstance(inputs, str) and len(inputs) == 64 and
                all(c in "0123456789abcdef" for c in inputs), "shared build-input digest required")
        if shared is None:
            shared = inputs
        require(inputs == shared, "shared build-input manifest differs")
        kind = record.get("evidence_kind")
        require(kind in ("synthetic-test-output", "reported-host-output"), "unknown evidence kind")
        if evidence_kind is None:
            evidence_kind = kind
        require(kind == evidence_kind, "cannot mix synthetic and reported outputs")
        stdout = record.get("stdout")
        observations = parse_stdout(stdout, expected)
        require(record.get("stdout_sha256") == digest(stdout.encode()), "stdout digest mismatch")
        if reference is None:
            reference = observations
        require(observations == reference, "observed payload differs between variants")
        record_hashes[variant] = record["stdout_sha256"]
    return {"validation_scope": "complete structured-output content comparison only",
            "content_comparison_passed": True, "cases_per_variant": len(expected),
            "variants": list(OPEN_HASHES), "stdout_sha256": record_hashes,
            "synthetic_inputs": evidence_kind == "synthetic-test-output",
            "actual_haskell_execution_established": False,
            "build_provenance_authenticated": False, "artifact_equivalence_established": False,
            "performance_claim_established": False, "resume_authorized": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--case-map", required=True)
    for variant in OPEN_HASHES:
        parser.add_argument("--" + variant, required=True)
    args = parser.parse_args()
    try:
        records = {v: strict_json(Path(getattr(args, v.replace("-", "_"))).read_bytes())
                   for v in OPEN_HASHES}
        result = compare_records(Path(args.fixture).read_bytes(), Path(args.case_map).read_bytes(), records)
    except (ValidationError, ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit("REJECTED: " + str(error))
    print(json.dumps(result, indent=2))
