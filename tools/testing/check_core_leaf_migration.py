#!/usr/bin/env python3
"""Static Core opt-in registration/isolation controls; no semantic test runs."""
import difflib
import functools
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


# These immutable commits delimit the already reviewed canonical collection/unit
# and explicit-annotation transcription. Never derive projection rules from the
# working tree or globally rewrite identifiers/string literals.
CUTOVER_BEFORE = "c0c5dddd11ed5775e2a3d5564cfeeef8383610a5"
# Original reviewed commit 1edcfec952b0517e3433cb3a394e331d20875ba7 was
# sequentially published as 83e5c3141a8417355e26edfd3b0b293ed4b3b943.
# Both have this exact tree; use the published tree, not the local-only commit.
CUTOVER_REVIEW = "177b951a4a870e0350c5a3eef5196f79be0624db"
PROJECTED_PATHS = frozenset("tests/Tests/" + name for name in (
    "Core.emlf", "CoreCrates.emlf", "CoreSolver.emlf", "CoreLanguage.emlf",
    "CoreModules.emlf", "CoreRunner.emlf", "CoreRegistry.emlf", "CorePartitions.hs"))


# Independent per-file pins make the permitted transcription inventory explicit.
PROJECTED_BLOBS = {
    'tests/Tests/Core.emlf': ('903d453e6cce94c5fcf598cd2561a6e6f212b9b35bb1cd85782386faf3e56a90',
        '70907eb2190ba1d384fef80c3462b3e11313e3fc0d36692d8c2b8223f09bb8ab'),
    'tests/Tests/CoreCrates.emlf': ('d5ac473b10ac736e70329c402a8dfb6c40cc38e96fd44b9a570955b03cb3d310',
        'b0abca94739e2c704a7db7db361a08c0c1465f9aeef85372cb1268ba2fdfc3e5'),
    'tests/Tests/CoreSolver.emlf': ('494c3d992e07cace2ebf9cd952fccb5bbd301de9dd05175ec5da9b9c2a3e83ee',
        '634b8cd86ab6ea82eca29b0e709db2e847c622611d8428dc5e7c326544d2ee48'),
    'tests/Tests/CoreLanguage.emlf': ('59565c2f3339b729de477e69822a22dad69e387140ead4f6c8ff5e8d0ee94d92',
        '68058072337b7e6392fffcdb4fd0a80a57d083c3586c1cea54a21bd1c3e0950d'),
    'tests/Tests/CoreModules.emlf': ('e89faaac88e753d6b7ce25802d1f969f65c3975ce1ebc16d7d7a45408aaad9b7',
        '241c69cfcaf7525dd6c5073809986d840c82ecd8c2c4194d1fe6c98cd3b600d1'),
    'tests/Tests/CoreRunner.emlf': ('9ff159956454996496e752f86beb7d5dcd3e1903f1b320321dc0b905d146b635',
        '30004d32181c7b86475654d9a908ea82818868511ca1d58cde32f89bcd4e83d3'),
    'tests/Tests/CoreRegistry.emlf': ('cc29bf0987b2d3d6e22359dccb43560a5e79930e41cc2395d379d45f6511d79f',
        '991d66ba4a104260f0a378c2d8e2d6d7abde2d1e5e48da647868fadfa3264116'),
    'tests/Tests/CorePartitions.hs': ('074ec18485fc1fb79a4186cbf6b9eb9bfe9ad9e8d87c7e9b1ea97699e8590aab',
        'b020a93ed6d93bf92766016f06ad6eb59f89b7c3b288b934b3568c28cc14284b'),
}


@functools.lru_cache(maxsize=None)
def reviewed_source(revision, path):
    require(path in PROJECTED_PATHS, "unreviewed Core projection path")
    require(revision in (CUTOVER_BEFORE, CUTOVER_REVIEW), "unreviewed Core projection revision")
    raw = subprocess.check_output(["git", "show", revision + ":" + path], cwd=ROOT)
    expected = PROJECTED_BLOBS[path][0 if revision == CUTOVER_BEFORE else 1]
    require(hashlib.sha256(raw).hexdigest() == expected, "reviewed Core projection blob changed: " + path)
    return raw.decode("utf-8")


def project_reviewed(path, current):
    """Undo only exact pinned changed spans; retain every other candidate byte."""
    before = reviewed_source(CUTOVER_BEFORE, path)
    after = reviewed_source(CUTOVER_REVIEW, path)
    require(len(current) == len(after), "reviewed Core transcription length changed: " + path)
    old_lines = before.splitlines(keepends=True)
    new_lines = after.splitlines(keepends=True)
    offsets = [0]
    for line in new_lines:
        offsets.append(offsets[-1] + len(line))
    pieces = []
    for tag, a, b, c, d in difflib.SequenceMatcher(
            None, old_lines, new_lines, autojunk=False).get_opcodes():
        # Line boundaries are from frozen text, not candidate-dependent parsing.
        # Changed lines must match exactly, including quotes and annotations.
        start, end = offsets[c], offsets[d]
        fragment = current[start:end]
        if tag == "equal":
            pieces.append(fragment)
        else:
            require(fragment == "".join(new_lines[c:d]),
                    "unreviewed Core transcription span: " + path)
            pieces.append("".join(old_lines[a:b]))
    return "".join(pieces)



CORE_SOLVER_IMPORTS = ("-- Select the standard Monad used by shared Either; retain legacy guest syntax.\n"
                       "import Prelude hiding (Monad, return, bind)\n"
                       "import MLF.Primitive (Monad, return, bind)\n")


def verify_family_source(path, current, original):
    # This one reviewed import insertion selects the class already used by
    # parseExpr/generate. Every original byte (including all family bodies)
    # remains required; never normalize arbitrary imports or update BASELINE.
    current = project_reviewed(path, current)
    expected = original
    if path == "tests/Tests/CoreSolver.emlf":
        header = "module Tests.CoreSolver where\n"
        require(original.startswith(header), "frozen CoreSolver header changed")
        expected = header + CORE_SOLVER_IMPORTS + original[len(header):]
    require(current == expected, f"original Core family composition changed: {path}")


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
    verify_legacy(project_reviewed("tests/Tests/CoreRegistry.emlf", registry),
                  project_reviewed("tests/Tests/CoreRunner.emlf", runner), original, expected)


def verify_legacy(registry, runner, original, expected):
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


def verify_historical_partitions(raw):
    # Fail closed against the published reviewed source, not candidate-derived
    # expectations. The frozen family oracle above remains BASELINE's catalog.
    require(hashlib.sha256(raw).hexdigest() == PARTITIONS_SHA256,
            "reviewed shared Core partition algorithm changed")


def verify_shared_partitions(raw):
    projected = project_reviewed(PARTITIONS, raw.decode())
    verify_historical_partitions(projected.encode())


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
    verify_historical_partitions(published)
    raw = (ROOT / PARTITIONS).read_bytes()
    verify_shared_partitions(raw)
    require(not (ROOT / "tests/Tests/CorePartitions.emlf").exists(), "duplicate live legacy CorePartitions")
    mutants = [raw.replace(b'core/guards', b'core/invented', 1),
               raw.replace(b'if ((S.length flat', b'if ((S.length familyNames', 1),
               raw.replace(b'then Right ()', b'then Left "weakened"', 1)]
    for mutant in mutants:
        require(mutant != raw, "inactive shared Core partition mutation")
        try:
            verify_shared_partitions(mutant)
        except ValueError:
            continue
        raise ValueError("shared Core partition mutant accepted")


def verify_projection_controls():
    for path in PROJECTED_PATHS:
        require(project_reviewed(path, reviewed_source(CUTOVER_REVIEW, path)) ==
                reviewed_source(CUTOVER_BEFORE, path), "reviewed projection is not exact: " + path)
    language = "tests/Tests/CoreLanguage.emlf"
    current = reviewed_source(CUTOVER_REVIEW, language)
    mutations = {
        "stale_legacy_representation": reviewed_source(CUTOVER_BEFORE, language),
        "unreviewed_collection_span": current.replace("(:)", "Cons", 1),
        "annotation_transcription_removed": current.replace("42 :: Bool", "42 : Bool", 1),
        "abstract_nominal_literal_changed": current.replace('XCon "List"', 'XCon "Lisp"', 1),
        "unreviewed_offset_insertion": "\n" + current,
    }
    for name, mutant in mutations.items():
        require(mutant != current, "inactive projection mutation " + name)
        try:
            verify_family_source(language, mutant, frozen(language))
        except ValueError:
            continue
        raise ValueError("projection accepted " + name)
    # Equal spans are not replaced with frozen bytes: an altered module header
    # survives projection, then the original family byte-comparison rejects it.
    mutant = current.replace("module Tests.CoreLanguage", "module Tests.CoreLanguagX", 1)
    projected = project_reviewed(language, mutant)
    require(projected.startswith("module Tests.CoreLanguagX"), "projection hid an untouched-byte mutation")
    try:
        verify_family_source(language, mutant, frozen(language))
    except ValueError:
        pass
    else:
        raise ValueError("family guard accepted untouched-byte mutation")
    try:
        project_reviewed("tests/Tests/Unreviewed.emlf", current)
    except ValueError:
        pass
    else:
        raise ValueError("projection accepted unreviewed path")
    return len(mutations) + 2


def main():
    expected = expected_bindings()
    registry = (ROOT / "tests/Tests/CoreRegistry.emlf").read_bytes().decode("utf-8")
    runner = (ROOT / "tests/Tests/CoreRunner.emlf").read_bytes().decode("utf-8")
    original = frozen("tests/Tests/CoreRunner.emlf")
    verify(registry, runner, original, expected)
    mutations = {
        "legacy_actions_unreachable": (registry, runner.replace("let all = S.append substrings entries", "let all = substrings", 1)),
        "substring_cases_unreachable": (registry, runner.replace("let all = S.append substrings entries", "let all = entries", 1)),
        "unknown_semantic_id": (registry.replace('core/optimizer-uses/optimizer-free-use-indices-agree-with-independent-scoped-scans', 'core/unknown', 1), runner),
        "original_label_changed": (registry.replace('optimizer free-use indices agree with independent scoped scans', 'changed label', 1), runner),
        "runtime_binding_check_removed": (registry.replace('S.eqList eqString (S.map S.fst actions) (S.map S.fst expected)', 'true', 1), runner),
        "qualification_boundary_removed": (registry.replace('(:) "qualification:ineligible"', '(:) "qualified"', 1), runner),
        "substring_oracle_changed": (registry, runner.replace('(,,) "ab" "abc" true', '(,,) "ab" "abc" false', 1)),
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
    old_registry = project_reviewed("tests/Tests/CoreRegistry.emlf", registry)
    old_runner = project_reviewed("tests/Tests/CoreRunner.emlf", runner)
    legacy_mutations = {
        "legacy_actions_unreachable": (old_registry, old_runner.replace("let all = S.append substrings entries", "let all = substrings", 1)),
        "substring_cases_unreachable": (old_registry, old_runner.replace("let all = S.append substrings entries", "let all = entries", 1)),
        "unknown_semantic_id": (old_registry.replace('core/optimizer-uses/optimizer-free-use-indices-agree-with-independent-scoped-scans', 'core/unknown', 1), old_runner),
        "original_label_changed": (old_registry.replace('optimizer free-use indices agree with independent scoped scans', 'changed label', 1), old_runner),
        "runtime_binding_check_removed": (old_registry.replace('S.eqList eqString (S.map S.fst actions) (S.map S.fst expected)', 'true', 1), old_runner),
        "qualification_boundary_removed": (old_registry.replace('Cons "qualification:ineligible"', 'Cons "qualified"', 1), old_runner),
        "substring_oracle_changed": (old_registry, old_runner.replace('Triple "ab" "abc" true', 'Triple "ab" "abc" false', 1)),
        "single_child_guard_removed": (old_registry, old_runner.replace('Runner.listing options || exact && S.length selected == 1', 'true', 1)),
        "default_switched": (old_registry, old_runner.replace('_ -> legacyMain target complete families args names cases', '_ -> framework target complete families args', 1)),
        "parent_evidence_isolation_removed": (old_registry, old_runner.replace('setEnv "MLF_TEST_COVERAGE_REPORT" (directory ++ "/legacy-coverage.jsonl")', 'return Unit', 1)),
    }
    for name, candidate in legacy_mutations.items():
        require(candidate != (old_registry, old_runner), "inactive historical policy mutation " + name)
        try:
            verify_legacy(*candidate, original, expected)
        except ValueError:
            continue
        raise ValueError("historical policy accepted " + name)
    for path in ("tests/Tests/Core.emlf", "tests/Tests/CoreCrates.emlf", "tests/Tests/CoreSolver.emlf", "tests/Tests/CoreLanguage.emlf", "tests/Tests/CoreModules.emlf"):
        verify_family_source(path, (ROOT / path).read_bytes().decode("utf-8"), frozen(path))
    solver_path = "tests/Tests/CoreSolver.emlf"
    solver = (ROOT / solver_path).read_bytes().decode("utf-8")
    solver_original = frozen(solver_path)
    for mutated in (solver.replace(CORE_SOLVER_IMPORTS, "", 1),
                    solver.replace("import MLF.Primitive (Monad, return, bind)", "import MLF.Primitive (Monad, return)", 1),
                    solver + "\nchangedBody = 0\n"):
        require(mutated != solver, "inactive CoreSolver import/body mutation")
        try:
            verify_family_source(solver_path, mutated, solver_original)
        except ValueError:
            continue
        raise ValueError("accepted unreviewed CoreSolver source mutation")
    verify_partition_provenance()
    projection_mutations = verify_projection_controls()
    print(json.dumps({"kind": "static-core-opt-in-controls", "baseline": BASELINE,
                      "family_count": len(expected), "legacy_actions": 739,
                      "named_substring_observations": 13, "mutation_controls": len(mutations),
                      "historical_policy_mutation_controls": len(legacy_mutations),
                      "projection_mutation_controls": projection_mutations,
                      "reviewed_cutover": CUTOVER_REVIEW,
                      "projection_preimage": CUTOVER_BEFORE,
                      "shared_partition_mutation_controls": 3,
                      "guest_class_import_mutation_controls": 3,
                      "historical_shared_partition_sha256": PARTITIONS_SHA256,
                      "shared_partition_sha256": hashlib.sha256((ROOT / PARTITIONS).read_bytes()).hexdigest(),
                      "default_campaign": "legacy", "qualification_eligible": False,
                      "compilation_verified": False, "semantic_execution_verified": False}, indent=2))


if __name__ == "__main__":
    main()
