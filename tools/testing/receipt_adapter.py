"""Import observations certified by an existing suite's own result verifier."""

import hashlib
import json
from pathlib import Path
import re
import unicodedata


def source(root, spec, args):
    output = spec["output"]
    if isinstance(output, int):
        directory = args[output]
    else:
        attached = next((arg.split("=", 1)[1] for arg in args if arg.startswith(output + "=")), None)
        directory = attached if attached is not None else args[args.index(output) + 1]
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


def import_results(path, before, spec, evidence, exit_code):
    after = fingerprint(path)
    if after is None or after == before:
        raise ValueError(f"missing or unchanged result receipt: {path}")
    receipt = json.loads(path.read_text(encoding="utf-8"))
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
            cases = [line.removeprefix(prefix) for line in raw.decode("utf-8").splitlines()
                     if line.startswith(prefix)]
    else:
        cases = field(receipt, rules["cases"], missing=[])
    if not isinstance(cases, list):
        raise ValueError("invalid result receipt inventory")
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
        verdict = field(case, rules["verdict"], missing=None) if "verdict" in rules else True
        if verdict in rules.get("omit_if_verdict", []):
            evidence["started_ids"].append(identity)
            continue
        if "verdict_equals" in rules:
            verdict = verdict == rules["verdict_equals"]
        if not isinstance(verdict, bool):
            raise ValueError(f"invalid receipt outcome: {identity}")
        observed.add(identity)
        results.append({"id": identity, "status": "pass" if verdict else "fail", "evidence": case})
    if "inventory" in rules:
        expected = [spec["prefix"] + slug(label) for label in rules["inventory"]]
    elif "plan" in rules:
        expected = [spec["prefix"] + slug(label) for label in receipt.get(rules["plan"], [])]
    else:
        # Here the specialized verifier's complete field seals its own
        # generated inventory. A partial receipt cannot declare its plan.
        expected = [entry["id"] for entry in results] if complete else []
    if len(expected) != len(set(expected)):
        raise ValueError("duplicate receipt plan IDs")
    evidence["expected_ids"] = expected or None
    if set(expected) != observed and complete:
        raise ValueError("receipt result IDs differ from its selected inventory")
    evidence["missing_ids"] = [identity for identity in expected if identity not in observed]
    return bool(expected) and complete and not evidence["missing_ids"] and exit_code == 0
