#!/usr/bin/env python3
"""Static Core opt-in registration/isolation controls; no semantic test runs."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "8a3e69b165765931c3ff762379a78db9659b2cd8"


def frozen(path):
    return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def expected_bindings():
    catalog = json.loads(frozen("tests/test-catalog.json"))
    result = {}
    for family in catalog["families"]:
        if family["unit"] == "core":
            result[family["id"]] = [
                (label, family["id"] + "/" + re.sub("[^a-z0-9]+", "-", label.lower()).strip("-"))
                for label in family["evidence"]["executions"]
            ]
    return result


def actual_bindings(text):
    result = {}
    for match in re.finditer(r'^ Cons \(Pair "(core/[^"\n]+)" \(\n(.*?)(?=^ Cons \(Pair |^ Nil\))', text, re.M | re.S):
        family, body = match.groups()
        require(family not in result, "duplicate family")
        pairs = re.findall(r'^  Cons \(Pair ("(?:\\.|[^"\\])*") ("(?:\\.|[^"\\])*")\)', body, re.M)
        result[family] = [(json.loads(label), json.loads(identity)) for label, identity in pairs]
    return result


def verify(registry, runner, original, expected):
    actual = actual_bindings(registry)
    framework_cases = """frameworkCases target complete families = do
 entries <- Registry.register target complete families
 let substrings = if S.elem eqString "core/substring-adapter" (S.map S.fst families) then substringCases target complete else Nil
 let all = S.append substrings entries
 Runner.validate all
 Right all
"""
    require(framework_cases in runner, "reachable framework registry union or validation changed")
    require(actual == expected, "Core family/label/semantic-ID ownership changed")
    ids = [identity for rows in actual.values() for _, identity in rows]
    require(len(ids) == 739 and len(set(ids)) == 739, "Core ID inventory is not exactly 739 unique leaves")
    require('C.fromIO identity (Cons ("family:" ++ family) Nil) (Pair label body)' in registry,
            "legacy body identity not retained")
    require('S.eqList eqString (S.map S.fst actions) (S.map S.fst expected)' in registry,
            "frozen family labels not checked before registration")
    require('Cons "qualification:ineligible"' in registry and '"logical-scope:"' in registry,
            "physical registry lost qualification boundary")
    # The legacy dispatcher stays byte-identical after its new function header.
    old_dispatch = original[original.index(' if Selection.listing args'):]
    new_dispatch = runner[runner.index(' if Selection.listing args'):]
    require(old_dispatch == new_dispatch, "legacy family/default dispatch changed")
    old_run = original[original.index('runCases :'):original.index('main :')]
    new_run = runner[runner.index('runCases :'):runner.index('main :')]
    require(old_run == new_run, "legacy action and coverage wrapper changed")
    triple = r'Triple "(?:\\.|[^"\\])*" "(?:\\.|[^"\\])*" (?:true|false)'
    require(re.findall(triple, original) == re.findall(triple, runner), "substring stimulus/oracle/order changed")
    predicate = 'O.require (H.eq (H.contains needle text) expected) "substring adapter differs from scalar substring semantics"'
    require(predicate in runner and 'Coverage.mapCounted "core" "substring-executed"' in runner,
            "original substring oracle or counted metric removed")
    require('Runner.listing options || exact && S.length selected == 1' in runner,
            "child can execute multiple fatal legacy actions")
    require('Cons "--" (Cons self (Cons "--framework-child" Nil))' in runner and 'Process.run' in runner,
            "parent no longer delegates individual children to the supervisor")
    require('Cons "--framework-list" rest -> frameworkChild' in runner,
            "read-only discovery route missing")
    require('setEnv "MLF_TEST_COVERAGE_REPORT" (directory ++ "/legacy-coverage.jsonl")' in runner,
            "child can corrupt parent campaign evidence")
    require('_ -> legacyMain target complete families args names cases' in runner,
            "default campaign no longer uses legacy implementation")


SHARED_REVIEW = "65e9e66680ee65f5e24745240dfe7ec8706e3e3b"
PARTITIONS = "tests/Tests/CorePartitions.hs"
PARTITIONS_SHA256 = "074ec18485fc1fb79a4186cbf6b9eb9bfe9ad9e8d87c7e9b1ea97699e8590aab"


def verify_shared_partitions(raw):
    # Fail closed against the published reviewed source, not candidate-derived
    # expectations. The frozen family oracle above remains BASELINE's catalog.
    require(hashlib.sha256(raw).hexdigest() == PARTITIONS_SHA256,
            "reviewed shared Core partition algorithm changed")


def verify_partition_provenance():
    original = frozen("tests/Tests/CorePartitions.emlf").encode()
    evidence = []
    for name in ("migration-manifest.json", "standard-hierarchy-adjustment.json"):
        path = "tools/shared-migration/evidence/" + name
        pinned = subprocess.check_output(["git", "show", SHARED_REVIEW + ":" + path], cwd=ROOT)
        require((ROOT / path).read_bytes() == pinned, "historical migration evidence changed: " + path)
        records = json.loads(pinned)["files"]
        evidence.append(next(r for r in records if r["module"] == "Tests.CorePartitions"))
    migration, hierarchy = evidence
    require(migration["old_sha256"] == hashlib.sha256(original).hexdigest(), "frozen Core migration preimage changed")
    require(migration["new_sha256"] == hierarchy["old_sha256"] and
            hierarchy["new_sha256"] == PARTITIONS_SHA256 and
            hierarchy["legacy_instances"] == 0 and
            hierarchy["expression_string_tokens"] == 11, "Core migration evidence chain changed")
    published = subprocess.check_output(["git", "show", SHARED_REVIEW + ":" + PARTITIONS], cwd=ROOT)
    verify_shared_partitions(published)
    raw = (ROOT / PARTITIONS).read_bytes()
    verify_shared_partitions(raw)
    require(not (ROOT / "tests/Tests/CorePartitions.emlf").exists(), "duplicate live legacy CorePartitions")
    mutants = [raw.replace(b'core/guards', b'core/invented', 1),
               raw.replace(b'if ((S.length flat', b'if ((S.length familyNames', 1),
               raw.replace(b'then Right Unit', b'then Left "weakened"', 1)]
    for mutant in mutants:
        require(mutant != raw, "inactive shared Core partition mutation")
        try:
            verify_shared_partitions(mutant)
        except ValueError:
            continue
        raise ValueError("shared Core partition mutant accepted")


def main():
    expected = expected_bindings()
    registry = (ROOT / "tests/Tests/CoreRegistry.emlf").read_text()
    runner = (ROOT / "tests/Tests/CoreRunner.emlf").read_text()
    original = frozen("tests/Tests/CoreRunner.emlf")
    verify(registry, runner, original, expected)
    mutations = {
        "legacy_actions_unreachable": (registry, runner.replace("let all = S.append substrings entries", "let all = substrings", 1)),
        "substring_cases_unreachable": (registry, runner.replace("let all = S.append substrings entries", "let all = entries", 1)),
        "unknown_semantic_id": (registry.replace('core/optimizer-uses/optimizer-free-use-indices-agree-with-independent-scoped-scans', 'core/unknown', 1), runner),
        "original_label_changed": (registry.replace('optimizer free-use indices agree with independent scoped scans', 'changed label', 1), runner),
        "runtime_binding_check_removed": (registry.replace('S.eqList eqString (S.map S.fst actions) (S.map S.fst expected)', 'true', 1), runner),
        "qualification_boundary_removed": (registry.replace('Cons "qualification:ineligible"', 'Cons "qualified"', 1), runner),
        "substring_oracle_changed": (registry, runner.replace('Triple "ab" "abc" true', 'Triple "ab" "abc" false', 1)),
        "single_child_guard_removed": (registry, runner.replace('Runner.listing options || exact && S.length selected == 1', 'true', 1)),
        "default_switched": (registry, runner.replace('_ -> legacyMain target complete families args names cases', '_ -> framework target complete families args', 1)),
        "parent_evidence_isolation_removed": (registry, runner.replace('setEnv "MLF_TEST_COVERAGE_REPORT" (directory ++ "/legacy-coverage.jsonl")', 'return Unit', 1)),
    }
    for name, (mutated_registry, mutated_runner) in mutations.items():
        require((mutated_registry, mutated_runner) != (registry, runner), f"inactive mutation {name}")
        try:
            verify(mutated_registry, mutated_runner, original, expected)
        except ValueError:
            continue
        raise ValueError(f"failed to reject {name}")
    for path in ("tests/Tests/Core.emlf", "tests/Tests/CoreCrates.emlf", "tests/Tests/CoreSolver.emlf", "tests/Tests/CoreLanguage.emlf", "tests/Tests/CoreModules.emlf"):
        require((ROOT / path).read_text() == frozen(path), f"original Core family composition changed: {path}")
    verify_partition_provenance()
    print(json.dumps({"kind": "static-core-opt-in-controls", "baseline": BASELINE,
                      "family_count": len(expected), "legacy_actions": 739,
                      "named_substring_observations": 13, "mutation_controls": len(mutations),
                      "shared_partition_mutation_controls": 3,
                      "shared_partition_sha256": PARTITIONS_SHA256,
                      "default_campaign": "legacy", "qualification_eligible": False,
                      "compilation_verified": False, "semantic_execution_verified": False}, indent=2))


if __name__ == "__main__":
    main()
