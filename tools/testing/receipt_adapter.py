"""Import observations certified by an existing suite's own result verifier."""

import hashlib
import json
from pathlib import Path
import re
import unicodedata


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def decode(raw):
    return json.loads(raw, object_pairs_hook=unique_object)

def source(root, spec, args):
    output = spec["output"]
    if isinstance(output, int):
        directory = args[output]
    else:
        directory = None
        tokens = iter(args)
        for arg in tokens:
            if arg == "--":
                break
            if arg == output:
                directory = next(tokens, None)
            elif arg.startswith(output + "="):
                directory = arg.split("=", 1)[1]
        if directory is None:
            raise ValueError(f"missing receipt directory for {output}")
    return (root / directory / spec.get("file", "receipt.json")).resolve()


def fingerprint(path):
    try:
        with path.open("rb") as f:
            before = path.stat()
            digest = hashlib.sha256(f.read()).hexdigest()
        return before.st_ino, before.st_size, before.st_mtime_ns, digest
    except FileNotFoundError:
        return None


_REQUIRED = object()


def field(document, dotted, missing=_REQUIRED):
    for part in dotted.split("."):
        if missing is not _REQUIRED and (not isinstance(document, dict) or part not in document):
            return missing
        document = document[part]
    return document


def slug(value):
    normalized = unicodedata.normalize("NFKC", str(value))
    identity = re.sub(r"[^a-zA-Z0-9/_.-]+", "-", normalized.strip()).strip("-")
    if not identity:
        raise ValueError("empty receipt case ID")
    return identity


def import_results(path, before, spec, evidence, exit_code, available, exact=None):
    after = fingerprint(path)
    if after is None or after == before:
        raise ValueError(f"missing or unchanged result receipt: {path}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != after[3]:
        raise ValueError(f"result receipt changed during import: {path}")
    receipt = decode(raw)
    if not isinstance(receipt, dict):
        raise ValueError("invalid result receipt object")
    rules = spec["receipt"]
    complete = receipt.get(rules.get("complete_field", "complete")) is True
    evidence["adapter_receipt"] = {"path": str(path), "sha256": after[3]}
    if "stdout" in rules:
        # The original driver has already validated these exact terminal
        # observations. An unsealed producer receipt cannot attest stdout.
        cases = []
        digest = field(receipt, rules["stdout_sha256"], missing=None) if "stdout_sha256" in rules else None
        if complete or digest is not None:
            raw = (path.parent / rules["stdout"]).read_bytes()
            if digest is not None and hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError("specialized report's stdout changed")
            prefix = rules.get("line_prefix", "PASS ")
            cases = [line.rstrip("\r\n").removeprefix(prefix)
                     for line in raw.decode("utf-8").splitlines(keepends=True)
                     if line.startswith(prefix) and line.endswith("\n")]
    else:
        cases = field(receipt, rules["cases"], missing=[])
    if not isinstance(cases, list):
        raise ValueError("invalid result receipt inventory")
    expected = evidence["expected_ids"]
    expected_set = set(expected)
    declared = receipt.get("selected_ids")
    if declared is not None and (not isinstance(declared, list)
                                 or len(declared) != len(expected)
                                 or set(declared) != expected_set):
        raise ValueError("producer selected IDs differ from the pre-run plan")
    results = evidence["results"]
    seen = set()
    observed = set()
    for case in cases:
        label = field(case, rules["id"]) if "id" in rules else case
        if label in rules.get("ignore", []) or re.search(rules.get("ignore_pattern", "(?!)"), str(label)):
            continue
        identity = spec["prefix"] + slug(label)
        if identity in seen:
            raise ValueError(f"duplicate receipt observation: {identity}")
        seen.add(identity)
        prerequisite = exact is not None and isinstance(case, dict) and case.get("prerequisite") is True
        if prerequisite:
            if identity in expected_set or identity not in available:
                raise ValueError(f"invalid prerequisite case: {identity}")
        elif identity not in expected_set:
            raise ValueError(f"case outside the pre-run plan: {identity}")
        verdict = field(case, rules["verdict"], missing=None) if "verdict" in rules else True
        if verdict in rules.get("omit_if_verdict", []):
            evidence["started_ids"].append(identity)
            continue
        if "verdict_equals" in rules:
            verdict = verdict == rules["verdict_equals"]
        if not isinstance(verdict, bool):
            raise ValueError(f"invalid receipt outcome: {identity}")
        row = {"id": identity, "status": "pass" if verdict else "fail", "evidence": case}
        if prerequisite:
            evidence["prerequisite_results"].append(row)
        else:
            observed.add(identity)
            results.append(row)
    evidence["missing_ids"] = [identity for identity in expected if identity not in observed]
    if "plan" in rules:
        authored = receipt.get(rules["plan"])
        if authored is not None or complete:
            if not isinstance(authored, list):
                raise ValueError("missing or invalid receipt plan")
            declared = [spec["prefix"] + slug(label) for label in authored]
            if len(declared) != len(expected) or set(declared) != expected_set:
                raise ValueError("receipt plan differs from pre-run discovery")
    if complete and evidence["missing_ids"]:
        raise ValueError("receipt omitted results from the pre-run plan")
    prerequisites_passed = all(row["status"] == "pass" for row in evidence.get("prerequisite_results", []))
    return complete and prerequisites_passed and not evidence["missing_ids"] and exit_code == 0
