#!/usr/bin/env python3
"""Static Core opt-in registration/isolation controls; no semantic test runs."""
import difflib
import functools
import hashlib
import json
import copy
from pathlib import Path
import re
from history_refs import historical_bytes

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "8a3e69b165765931c3ff762379a78db9659b2cd8"


# Reviewed source-only projection of the standard-core cutover. String contents,
# comments and character literals are opaque: this never rewrites test inputs.
CANONICAL_IDENTIFIERS = {
    "List": "[]", "Nil": "[]", "Cons": "(:)", "Pair": "(,)",
    "Triple": "(,,)", "Quad": "(,,,)", "Quint": "(,,,,)", "Unit": "()",
}
CANONICAL_TOKEN = re.compile(r"--[^\n]*|\{-[\s\S]*?-\}|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])'|[A-Za-z_][A-Za-z_0-9']*")


def canonical_source(text):
    return CANONICAL_TOKEN.sub(lambda match: CANONICAL_IDENTIFIERS.get(match.group(), match.group()), text)


def frozen_raw(path):
    return historical_bytes(BASELINE, path).decode("utf-8")


def frozen(path):
    # Strict UTF-8 decoding is reversible and does not normalize CRLF bytes.
    text = canonical_source(frozen_raw(path))
    if path == "tests/Tests/CoreLanguage.emlf":
        # Only the two authenticated intended expression annotations changed.
        text = text.replace('"42 : Bool"', '"42 :: Bool"').replace('"42 : Int Bool"', '"42 :: Int Bool"')
    return text


def source_text(path):
    return (ROOT / path).read_bytes().decode("utf-8")


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
    raw = historical_bytes(revision, path)
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

RECURSION_HELPERS_START = "\n\n-- Reserved export IDs 7 and 8 are deliberately absent."
CORE_FAMILIES_START = '\nfamilies : [] ((,) String ([] ((,) String (IO ()))))\n'
RECURSION_SOURCE_REVIEW = "2ea93adf6d8c76857e0d202a033e9bfee191e444"
RECURSION_HELPERS_SHA256 = "ca4763f18b12a5e45e835e8e3cf81fb76ae026d2fbaecc218c191bf31185f72c"
RECURSION_GRAPH_LABEL = "recursive exports preserve scoped identities and independent copies"
RECURSION_IMPORTS = (
    ("import qualified Bootstrap.IntMap as IM\n", "import qualified Bootstrap.IntSet as IS\n"),
    ("import qualified Tests.Graph as G\n",
     "import qualified Bootstrap.Graph as NativeGraph\n"
     "import Bootstrap.Elaborate (schemeType, boundsAt)\n"
     "import qualified Bootstrap.X.Type as XType\n"
     "import qualified Tests.GraphValidation as GraphValidation\n"),
)


def verify_family_source(path, current, original):
    # Reconstruct from the frozen original, never from a candidate-derived
    # whole-file digest. Every historical body byte remains required. Only the
    # separately pinned helper block, five imports and one graph-test wrapper
    # are admitted in addition to the previously reviewed class import.
    if path != "tests/Tests/CoreSolver.emlf":
        require(project_reviewed(path, current) == reviewed_source(CUTOVER_BEFORE, path),
                "current family differs from pinned canonical transcription")
    expected = original
    if path == "tests/Tests/CoreSolver.emlf":
        header = "module Tests.CoreSolver where\n"
        require(original.startswith(header), "frozen CoreSolver header changed")
        expected = header + CORE_SOLVER_IMPORTS + original[len(header):]
        require(current.count(RECURSION_HELPERS_START) == 1 and
                current.count(CORE_FAMILIES_START) == 1, "recursive helper boundaries changed")
        start, end = current.index(RECURSION_HELPERS_START), current.index(CORE_FAMILIES_START)
        require(start < end, "recursive helper placement changed")
        helpers = current[start:end]
        reviewed = historical_bytes(RECURSION_SOURCE_REVIEW, path).decode("utf-8")
        legacy_boundary = "\nfamilies : List (Pair String (List (Pair String (IO Unit))))\n"
        reviewed_helpers = reviewed[reviewed.index(RECURSION_HELPERS_START):reviewed.index(legacy_boundary)]
        require(len(reviewed_helpers.encode()) == 12282 and
                hashlib.sha256(reviewed_helpers.encode()).hexdigest() == RECURSION_HELPERS_SHA256,
                "frozen recursive graph helper provenance changed")
        require(helpers == canonical_source(reviewed_helpers),
                "reviewed recursive graph assertions changed")
        for anchor, inserted in RECURSION_IMPORTS:
            require(expected.count(anchor) == 1, "frozen graph import anchor changed")
            expected = expected.replace(anchor, anchor + inserted, 1)
        graph_lines = list(re.finditer(r"^graphTests = (.+)$", expected, re.M))
        require(len(graph_lines) == 1, "frozen graph test registration changed")
        line = graph_lines[0]
        wrapped = 'graphTests = ((:) ((,) "' + RECURSION_GRAPH_LABEL + '" recursiveExportChecks) ' + line[1] + ')'
        expected = expected[:line.start()] + wrapped + expected[line.end():]
        require(expected.count(CORE_FAMILIES_START) == 1, "frozen family boundary changed")
        expected = expected.replace(CORE_FAMILIES_START, helpers + CORE_FAMILIES_START, 1)
    require(current == expected, f"original Core family composition changed: {path}")


def catalog_bindings(catalog):
    result = {}
    for family in catalog["families"]:
        if family["unit"] == "core":
            require(family["id"] not in result, "duplicate Core catalog family")
            result[family["id"]] = [
                (label, family["id"] + "/" + re.sub("[^a-z0-9]+", "-", label.lower()).strip("-"))
                for label in family["evidence"]["executions"]
            ]
    return result


# Reviewed ordinary-recursion delta. Keep BASELINE frozen: four formerly
# signature-required sources now have positive oracles, and three new leaves
# exercise graph exports and qualified module/crate exports. No candidate file
# supplies these expectations, and every unlisted historical row stays exact.
RECURSION_RENAMES = (
    ("core/readability", "readability rejection: mutual recursion needs every signature",
     "recursion: mixed signed and inferred group", None),
    ("core/readability", "readability rejection: local recursion needs a signature",
     "recursion: unsigned local group", None),
    ("core/modules", "modules rejection: cross-module recursion retains existing signature requirement",
     "modules typing: cross-module recursion infers unsigned cycle",
     "crate namespaces resolve recursive declarations before inference"),
    ("core/separate-compilation", "crate rejects: cross-module recursion retains existing signature requirement",
     "crate typing: cross-module recursion infers unsigned cycle",
     "crate paths and native cache commands"),
)
RECURSION_ADDITIONS = (
    ("core/graph-expansion", "recursive exports preserve scoped identities and independent copies",
     "expansion resets scheme flag and binding"),
    ("core/modules", "modules typing: cross-module qualified recursion generalizes shared exports",
     "crate namespaces resolve recursive declarations before inference"),
    ("core/separate-compilation", "crate typing: cross-module qualified recursion generalizes shared exports",
     "crate paths and native cache commands"),
)


def binding(family, label):
    return label, family + "/" + re.sub("[^a-z0-9]+", "-", label.lower()).strip("-")


def reviewed_recursion_bindings(original):
    result = {family: list(rows) for family, rows in original.items()}
    require(sum(map(len, result.values())) == 739, "frozen Core inventory changed")
    for family, old, new, before in RECURSION_RENAMES:
        rows = result[family]
        require(rows.count(binding(family, old)) == 1 and binding(family, new) not in rows,
                "reviewed recursive migration preimage changed")
        position = rows.index(binding(family, old))
        rows.pop(position)
        if before is not None:
            require(rows.count(binding(family, before)) == 1, "migration anchor changed")
            position = rows.index(binding(family, before))
        rows.insert(position, binding(family, new))
    for family, label, before in RECURSION_ADDITIONS:
        rows = result[family]
        require(binding(family, label) not in rows and rows.count(binding(family, before)) == 1,
                "reviewed recursive addition preimage changed")
        rows.insert(rows.index(binding(family, before)), binding(family, label))
    return result


# Reviewed PR22 integration amendment, never a candidate-derived new baseline.
# Constructor identity / Eq / MonadFail changes require explicit label migrations.
CUTOVER_RENAMES = (
    ('core/do-notation', 'do: local let sees the outer binding',
     'do: distinct do-let binder sees the outer binding'),
    ('core/do-notation', 'do: uses the lexical bind function',
     'do: explicit bind remains lexical'),
    ('core/do-notation', 'do rejection: refutable pattern requires an explicit case',
     'do rejection: refutable pattern requires canonical MonadFail'),
    ('core/modules', 'modules rejection: primitive constructor cannot be redefined',
     'modules rejection: ordinary Unit constructor is not builtin unit'),
    ('core/separate-compilation', 'crate rejects: primitive constructor cannot be redefined',
     'crate rejects: ordinary Unit constructor is not builtin unit'),
    ('core/surface-syntax', 'surface checking: do-local function sees outer binding',
     'surface checking: distinct do-local function sees outer binding'),
    ('core/surface-syntax', 'surface rejection: comparisons do not overload String',
     'surface checking: equality supports annotated strings'),
    ('core/surface-syntax', 'surface rejection: recursion needs a signature',
     'surface checking: unsigned recursion infers bottom'),
)
CUTOVER_ADDITIONS = (
    ('core/do-notation', 'do rejection: lexical bind cannot intercept do',
     'do rejection: empty block'),
    ('core/do-notation', 'do rejection: same-name do-let is recursive, not an outer reference',
     'do rejection: empty block'),
    ('core/do-notation', 'do: annotated recursive do-let keeps its own binding',
     'do rejection: empty block'),
    ('core/surface-syntax', 'surface checking: same-name do-local function is recursive',
     'surface checking: unsigned recursion infers bottom'),
)


def reviewed_cutover_bindings(original):
    result = {family: list(rows) for family, rows in original.items()}
    require(sum(map(len, result.values())) == 742, "reviewed recursion inventory changed")
    for family, old, new in CUTOVER_RENAMES:
        rows = result[family]
        require(rows.count(binding(family, old)) == 1 and binding(family, new) not in rows,
                "reviewed cutover rename preimage changed")
        rows[rows.index(binding(family, old))] = binding(family, new)
    for family, label, before in CUTOVER_ADDITIONS:
        rows = result[family]
        require(binding(family, label) not in rows and rows.count(binding(family, before)) == 1,
                "reviewed cutover addition preimage changed")
        rows.insert(rows.index(binding(family, before)), binding(family, label))
    return result


def expected_bindings():
    return reviewed_cutover_bindings(reviewed_recursion_bindings(catalog_bindings(json.loads(frozen("tests/test-catalog.json")))))


def verify_catalog(catalog, expected):
    require(list(catalog_bindings(catalog).items()) == list(expected.items()),
            "live Core catalog family/label/semantic-ID ownership changed")


def verify_inventory(inventory, expected):
    require(inventory["suites"]["core"]["executions"] ==
            [label for rows in expected.values() for label, _ in rows],
            "live Core golden execution order changed")


def actual_bindings(text):
    result = {}
    family_pattern = (r'^ \(:\) \(\(,\) "(core/[^"\n]+)" \(\n'
                      r'(.*?)(?=^ \(:\) \(\(,\) |^ \[\]\))')
    row_pattern = r'^  \(:\) \(\(,\) ("(?:\\.|[^"\\])*") ("(?:\\.|[^"\\])*")\)'
    for match in re.finditer(family_pattern, text, re.M | re.S):
        family, body = match.groups()
        require(family not in result, "duplicate family")
        pairs = re.findall(row_pattern, body, re.M)
        result[family] = [(json.loads(label), json.loads(identity)) for label, identity in pairs]
    return result


def reviewed_current_registry(expected):
    source = reviewed_source(CUTOVER_REVIEW, "tests/Tests/CoreRegistry.emlf")
    start = source.index("bindings =\n") + len("bindings =\n")
    end = source.index("\nfamilyBindings", start)
    lines = []
    for family, entries in expected.items():
        lines.append(' (:) ((,) ' + json.dumps(family) + ' (\n')
        for label, identity in entries:
            lines.append('  (:) ((,) ' + json.dumps(label) + ' ' + json.dumps(identity) + ') (\n')
        lines.append('  []' + ')' * (len(entries) + 2) + ' (\n')
    lines.append(' []' + ')' * len(expected) + '\n')
    return source[:start] + ''.join(lines) + source[end:]


def verify(registry, runner, original, expected):
    require(registry == reviewed_current_registry(expected),
            "current registry differs from pinned source plus reviewed ordered amendments")
    require(project_reviewed("tests/Tests/CoreRunner.emlf", runner) ==
            reviewed_source(CUTOVER_BEFORE, "tests/Tests/CoreRunner.emlf"),
            "current Core runner differs from pinned canonical transcription")
    actual = actual_bindings(registry)
    framework_cases = 'frameworkCases target complete families = do\n entries <- Registry.register target complete families\n let substrings = if S.elem eqString "core/substring-adapter" (S.map S.fst families) then substringCases target complete else []\n let all = S.append substrings entries\n Runner.validate all\n Right all\n'
    require(framework_cases in runner, "reachable framework registry union or validation changed")
    require(list(actual.items()) == list(expected.items()), "Core family/label/semantic-ID ownership changed")
    ids = [identity for rows in actual.values() for _, identity in rows]
    require(len(ids) == 746 and len(set(ids)) == 746, "Core ID inventory is not exactly 746 reviewed unique leaves")
    require('C.fromIO identity ((:) ("family:" ++ family) []) ((,) label body)' in registry,
            "legacy body identity not retained")
    require('S.eqList eqString (S.map S.fst actions) (S.map S.fst expected)' in registry,
            "frozen family labels not checked before registration")
    require('(:) "qualification:ineligible"' in registry and '"logical-scope:"' in registry,
            "physical registry lost qualification boundary")
    # The legacy dispatcher stays byte-identical after its new function header.
    old_dispatch = original[original.index(' if Selection.listing args'):]
    new_dispatch = runner[runner.index(' if Selection.listing args'):]
    require(old_dispatch == new_dispatch, "legacy family/default dispatch changed")
    old_run = original[original.index('runCases :'):original.index('main :')]
    new_run = runner[runner.index('runCases :'):runner.index('main :')]
    require(old_run == new_run, "legacy action and coverage wrapper changed")
    triple = r'\(,,\) "(?:\\.|[^"\\])*" "(?:\\.|[^"\\])*" (?:true|false)'
    require(re.findall(triple, original) == re.findall(triple, runner), "substring stimulus/oracle/order changed")
    predicate = 'O.require (H.eq (H.contains needle text) expected) "substring adapter differs from scalar substring semantics"'
    require(predicate in runner and 'Coverage.mapCounted "core" "substring-executed"' in runner,
            "original substring oracle or counted metric removed")
    require('Runner.listing options || exact && S.length selected == 1' in runner,
            "child can execute multiple fatal legacy actions")
    require('(:) "--" ((:) self ((:) "--framework-child" []))' in runner and 'Process.run' in runner,
            "parent no longer delegates individual children to the supervisor")
    require('(:) "--framework-list" rest -> frameworkChild' in runner,
            "read-only discovery route missing")
    require('setEnv "MLF_TEST_COVERAGE_REPORT" (directory ++ "/legacy-coverage.jsonl")' in runner,
            "child can corrupt parent campaign evidence")
    require('_ -> legacyMain target complete families args names cases' in runner,
            "default campaign no longer uses legacy implementation")


def historical_bindings(text):
    result = {}
    for match in re.finditer(r'^ Cons \(Pair "(core/[^"\n]+)" \(\n(.*?)(?=^ Cons \(Pair |^ Nil\))', text, re.M | re.S):
        family, body = match.groups()
        require(family not in result, "duplicate family")
        pairs = re.findall(r'^  Cons \(Pair ("(?:\\.|[^"\\])*") ("(?:\\.|[^"\\])*")\)', body, re.M)
        result[family] = [(json.loads(label), json.loads(identity)) for label, identity in pairs]
    return result


def verify_historical_policy(registry, runner, original, expected):
    actual = historical_bindings(registry)
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


def verify_shared_partitions(raw, canonical=False):
    # Fail closed against the published reviewed source, not candidate-derived
    # expectations. The frozen family oracle above remains BASELINE's catalog.
    published = historical_bytes(SHARED_REVIEW, PARTITIONS)
    require(hashlib.sha256(published).hexdigest() == PARTITIONS_SHA256,
            "reviewed Core partition provenance changed")
    if canonical:
        require(project_reviewed(PARTITIONS, raw.decode("utf-8")).encode("utf-8") == published,
                "current partitions differ from pinned canonical transcription")
    expected = canonical_source(published.decode("utf-8")).encode("utf-8") if canonical else published
    require(raw == expected, "reviewed shared Core partition algorithm changed")


def verify_partition_provenance():
    original = frozen_raw("tests/Tests/CorePartitions.emlf").encode()
    evidence = []
    for name in ("migration-manifest.json", "standard-hierarchy-adjustment.json"):
        path = "tools/shared-migration/evidence/" + name
        pinned = historical_bytes(SHARED_REVIEW, path)
        require((ROOT / path).read_bytes() == pinned, "historical migration evidence changed: " + path)
        records = json.loads(pinned)["files"]
        evidence.append(next(r for r in records if r["module"] == "Tests.CorePartitions"))
    migration, hierarchy = evidence
    require(migration["old_sha256"] == hashlib.sha256(original).hexdigest(), "frozen Core migration preimage changed")
    require(migration["new_sha256"] == hierarchy["old_sha256"] and
            hierarchy["new_sha256"] == PARTITIONS_SHA256 and
            hierarchy["legacy_instances"] == 0 and
            hierarchy["expression_string_tokens"] == 11, "Core migration evidence chain changed")
    published = historical_bytes(SHARED_REVIEW, PARTITIONS)
    verify_shared_partitions(published)
    raw = (ROOT / PARTITIONS).read_bytes()
    verify_shared_partitions(raw, canonical=True)
    require(not (ROOT / "tests/Tests/CorePartitions.emlf").exists(), "duplicate live legacy CorePartitions")
    mutants = [raw.replace(b'core/guards', b'core/invented', 1),
               raw.replace(b'if ((S.length flat', b'if ((S.length familyNames', 1),
               raw.replace(b'then Right ()', b'then Left "weakened"', 1)]
    for mutant in mutants:
        require(mutant != raw, "inactive shared Core partition mutation")
        try:
            verify_shared_partitions(mutant, canonical=True)
        except ValueError:
            continue
        raise ValueError("shared Core partition mutant accepted")


def verify_projection_controls():
    for path in PROJECTED_PATHS:
        require(project_reviewed(path, reviewed_source(CUTOVER_REVIEW, path)) ==
                reviewed_source(CUTOVER_BEFORE, path), "reviewed projection is not exact: " + path)
    for path in PROJECTED_PATHS:
        projected = canonical_source(reviewed_source(CUTOVER_BEFORE, path))
        if path == "tests/Tests/CoreLanguage.emlf":
            projected = projected.replace('"42 : Bool"', '"42 :: Bool"').replace('"42 : Int Bool"', '"42 :: Int Bool"')
        require(projected == reviewed_source(CUTOVER_REVIEW, path),
                "canonical mapping differs from independent reviewed blob pair: " + path)
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
    lexical_control = "List (Pair String Unit)\n-- List Pair Unit\n" + '\"List Pair Unit\" \'L\' {- List Pair Unit -} Listish List\''
    lexical_expected = "[] ((,) String ())\n-- List Pair Unit\n" + '\"List Pair Unit\" \'L\' {- List Pair Unit -} Listish List\''
    require(canonical_source(lexical_control) == lexical_expected,
            "canonical projection changed strings, comments, characters or unrelated names")
    expected = expected_bindings()
    registry = source_text("tests/Tests/CoreRegistry.emlf")
    runner = source_text("tests/Tests/CoreRunner.emlf")
    original = frozen("tests/Tests/CoreRunner.emlf")
    catalog = json.loads(source_text("tests/test-catalog.json"))
    inventory = json.loads(source_text("tests/golden/unit-inventory.json"))
    verify(registry, runner, original, expected)
    verify_catalog(catalog, expected)
    verify_inventory(inventory, expected)
    graph_row = '  (:) ((,) "' + RECURSION_GRAPH_LABEL + '" "' + binding("core/graph-expansion", RECURSION_GRAPH_LABEL)[1] + '") (\n'
    old_graph_row = '  (:) ((,) "expansion resets scheme flag and binding" "core/graph-expansion/expansion-resets-scheme-flag-and-binding") (\n'
    require(registry.count(graph_row) == 1 and registry.count(old_graph_row) == 1,
            "recursive graph row mutation preimage changed")
    family_a = registry.index(' (:) ((,) "core/graph-expansion" (\n')
    family_b = registry.index(' (:) ((,) "core/graph-validation" (\n')
    family_end = registry.index('\n (:) ((,) ', family_b + 1) + 1
    swapped_families = registry[:family_a] + registry[family_b:family_end] + registry[family_a:family_b] + registry[family_end:]
    require(actual_bindings(swapped_families) == actual_bindings(registry),
            "family-order mutant changed row ownership instead of only order")
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
        "parent_evidence_isolation_removed": (registry, runner.replace('setEnv "MLF_TEST_COVERAGE_REPORT" (directory ++ "/legacy-coverage.jsonl")', 'return ()', 1)),
        "recursive_leaf_dropped": (registry.replace(graph_row, "", 1), runner),
        "recursive_leaf_wrong_owner": (registry.replace(graph_row, "", 1).replace(' (:) ((,) "core/modules" (\n', ' (:) ((,) "core/modules" (\n' + graph_row, 1), runner),
        "recursive_leaf_order_changed": (registry.replace(graph_row + old_graph_row, old_graph_row + graph_row, 1), runner),
        "retired_identity_resurrected": (registry.replace("core/readability/recursion-unsigned-local-group", "core/readability/readability-rejection-local-recursion-needs-a-signature", 1), runner),
        "family_order_changed": (swapped_families, runner),
    }
    # Each new migration has its own active counterexample; old identities
    # cannot return, and every added leaf remains ordered and correctly owned.
    def registry_row(family, label):
        return '  (:) ((,) ' + json.dumps(label) + ' ' + json.dumps(binding(family, label)[1]) + ') (\n'
    for index, (family, old, new) in enumerate(CUTOVER_RENAMES):
        row = registry_row(family, new)
        require(registry.count(row) == 1, "cutover rename mutation preimage changed")
        mutations["cutover_retired_identity_" + str(index)] = (
            registry.replace(row, registry_row(family, old), 1), runner)
    for index, (family, label, before) in enumerate(CUTOVER_ADDITIONS):
        row = registry_row(family, label)
        require(registry.count(row) == 1, "cutover addition mutation preimage changed")
        rows = expected[family]
        following = registry_row(family, rows[rows.index(binding(family, label)) + 1][0])
        require(row + following in registry, "cutover addition order preimage changed")
        mutations["cutover_leaf_dropped_" + str(index)] = (registry.replace(row, "", 1), runner)
        mutations["cutover_leaf_order_" + str(index)] = (
            registry.replace(row + following, following + row, 1), runner)
        wrong = ' (:) ((,) "core/inference-and-annotations" (\n'
        mutations["cutover_leaf_owner_" + str(index)] = (
            registry.replace(row, "", 1).replace(wrong, wrong + row, 1), runner)
    for name, (mutated_registry, mutated_runner) in mutations.items():
        require((mutated_registry, mutated_runner) != (registry, runner), f"inactive mutation {name}")
        try:
            verify(mutated_registry, mutated_runner, original, expected)
        except ValueError:
            continue
        raise ValueError(f"failed to reject {name}")
    catalog_mutations = {}
    changed = copy.deepcopy(catalog)
    graph = next(f for f in changed["families"] if f["id"] == "core/graph-expansion")
    graph["evidence"]["executions"].remove(RECURSION_GRAPH_LABEL)
    catalog_mutations["recursive_leaf_dropped"] = changed
    changed = copy.deepcopy(catalog)
    core_positions = [i for i, f in enumerate(changed["families"]) if f["unit"] == "core"]
    a, b = core_positions[:2]
    changed["families"][a], changed["families"][b] = changed["families"][b], changed["families"][a]
    catalog_mutations["family_order_changed"] = changed
    changed = copy.deepcopy(catalog)
    graph = next(f for f in changed["families"] if f["id"] == "core/graph-expansion")
    modules = next(f for f in changed["families"] if f["id"] == "core/modules")
    graph["evidence"]["executions"].remove(RECURSION_GRAPH_LABEL)
    modules["evidence"]["executions"].append(RECURSION_GRAPH_LABEL)
    catalog_mutations["recursive_leaf_wrong_owner"] = changed
    for index, (family, old, new) in enumerate(CUTOVER_RENAMES):
        changed = copy.deepcopy(catalog)
        rows = next(f for f in changed["families"] if f["id"] == family)["evidence"]["executions"]
        rows[rows.index(new)] = old
        catalog_mutations["cutover_retired_identity_" + str(index)] = changed
    for index, (family, label, before) in enumerate(CUTOVER_ADDITIONS):
        changed = copy.deepcopy(catalog)
        next(f for f in changed["families"] if f["id"] == family)["evidence"]["executions"].remove(label)
        catalog_mutations["cutover_leaf_dropped_" + str(index)] = changed
    for name, changed in catalog_mutations.items():
        require(changed != catalog, "inactive catalog mutation: " + name)
        try:
            verify_catalog(changed, expected)
        except ValueError:
            continue
        raise ValueError("accepted catalog mutation: " + name)
    for name in ("dropped", "reordered"):
        changed = copy.deepcopy(inventory)
        rows = changed["suites"]["core"]["executions"]
        if name == "dropped":
            rows.remove(RECURSION_GRAPH_LABEL)
        else:
            position = rows.index(RECURSION_GRAPH_LABEL)
            rows[position], rows[position + 1] = rows[position + 1], rows[position]
        require(changed != inventory, "inactive golden inventory mutation")
        try:
            verify_inventory(changed, expected)
        except ValueError:
            continue
        raise ValueError("accepted golden inventory mutation: " + name)
    old_registry = project_reviewed("tests/Tests/CoreRegistry.emlf", reviewed_source(CUTOVER_REVIEW, "tests/Tests/CoreRegistry.emlf"))
    old_runner = project_reviewed("tests/Tests/CoreRunner.emlf", reviewed_source(CUTOVER_REVIEW, "tests/Tests/CoreRunner.emlf"))
    old_original = frozen_raw("tests/Tests/CoreRunner.emlf")
    old_expected = catalog_bindings(json.loads(frozen_raw("tests/test-catalog.json")))
    verify_historical_policy(old_registry, old_runner, old_original, old_expected)
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
            verify_historical_policy(*candidate, old_original, old_expected)
        except ValueError:
            continue
        raise ValueError("historical policy accepted " + name)
    for path in ("tests/Tests/Core.emlf", "tests/Tests/CoreCrates.emlf", "tests/Tests/CoreSolver.emlf", "tests/Tests/CoreLanguage.emlf", "tests/Tests/CoreModules.emlf"):
        verify_family_source(path, source_text(path), frozen(path))
    solver_path = "tests/Tests/CoreSolver.emlf"
    solver = source_text(solver_path)
    solver_original = frozen(solver_path)
    helper_start, helper_end = solver.index(RECURSION_HELPERS_START), solver.index(CORE_FAMILIES_START)
    solver_mutations = (
        solver.replace(CORE_SOLVER_IMPORTS, "", 1),
        solver.replace("import MLF.Primitive (Monad, return, bind)", "import MLF.Primitive (Monad, return)", 1),
        solver + "\nchangedBody = 0\n",
        solver.replace("import qualified Bootstrap.IntSet as IS\n", "", 1),
        solver.replace("import qualified Bootstrap.IntSet as IS\n", "", 1) + "import qualified Bootstrap.IntSet as IS\n",
        solver.replace('" recursiveExportChecks) ((:)', '" (return ())) ((:)', 1),
        solver.replace("H.null es", "False", 1),
        solver.replace("NativeGraph.nextId original + 4", "NativeGraph.nextId original + 5", 1),
        solver[:helper_start] + solver[helper_end:],
        solver[:helper_start] + solver[helper_end:] + solver[helper_start:helper_end],
        solver.replace("\n", "\r\n", 1),
    )
    for mutated in solver_mutations:
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
                      "registered_actions": 746, "retained_legacy_identities": 727,
                      "reviewed_identity_migrations": 12, "new_recursive_leaves": 3,
                      "cutover_identity_migrations": 8, "new_cutover_leaves": 4,
                      "named_substring_observations": 13, "mutation_controls": len(mutations),
                      "historical_policy_mutation_controls": len(legacy_mutations),
                      "projection_mutation_controls": projection_mutations,
                      "independent_projection_blob_pairs": len(PROJECTED_BLOBS),
                      "reviewed_cutover": CUTOVER_REVIEW,
                      "projection_preimage": CUTOVER_BEFORE,
                      "shared_partition_mutation_controls": 3,
                      "core_solver_source_mutation_controls": len(solver_mutations),
                      "catalog_mutation_controls": len(catalog_mutations),
                      "golden_inventory_mutation_controls": 2,
                      "recursive_graph_helpers_sha256": RECURSION_HELPERS_SHA256,
                      "historical_shared_partition_sha256": PARTITIONS_SHA256,
                      "shared_partition_sha256": hashlib.sha256((ROOT / PARTITIONS).read_bytes()).hexdigest(),
                      "default_campaign": "legacy", "qualification_eligible": False,
                      "compilation_verified": False, "semantic_execution_verified": False}, indent=2))


if __name__ == "__main__":
    main()
