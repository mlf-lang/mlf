#!/usr/bin/env python3
"""Static preservation checks, not compilation or semantic execution evidence."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "8a3e69b165765931c3ff762379a78db9659b2cd8"
SOURCE = "tests/TupleListMain.emlf"
IMPLEMENTATION = "tests/Tests/TupleList.emlf"


def frozen(path):
    return subprocess.check_output(
        ["git", "show", f"{BASELINE}:{path}"], cwd=ROOT, text=True
    )


def require(condition, message):
    if not condition:
        raise ValueError(message)


def helper_body(source, name):
    found = re.search(
        r"^" + name + r" .*?= do\n(.*?)(?=\n[^ \n]|\Z)", source, re.M | re.S
    )
    require(found is not None, f"missing helper: {name}")
    return found.group(1)


def expected_projection(s):
    """An explicit, fail-closed source rewrite contract, not a semantic proof.

    Compare the whole emitted module, including support constants, assertion
    transport, registration nesting and final reachable union. Membership checks
    alone accept dead registrations or weakened helpers. Changes to this strict
    projection require independent review alongside any implementation update.
    """
    # Extract complete top-level action statements, including multiline fixed ASTs.
    groups={}
    for name in ['parserChecks','boundaryChecks','checkingChecks','runtimeChecks','scopeChecks']:
     body=re.search(r'^'+name+r' = do\n(.*?)(?=\n[^ \n]|\Z)',s,re.M|re.S).group(1)
     groups[name]=re.findall(r'^ (\S[^\n]*(?:\n  [^\n]*)*)',body,re.M)
    head=s[:s.index('parserChecks : IO Unit')]
    head=re.sub(r'-- A surrounding parser owns these delimiters; no guards grammar is needed\.\nboundaryChecks : IO Unit\nboundaryChecks = do\n.*?(?=sameAnnotation :)','',head,flags=re.S)
    tail=s[s.index('shapes :'):s.index('scopeChecks :')]
    helpers=head+tail
    helpers=helpers.replace('module TupleListMain where','module Tests.TupleList where')
    helpers=helpers.replace('import qualified Tests.IndependentType as IndependentType','import qualified Tests.IndependentType as IndependentType\nimport qualified Test.Assert as A\nimport qualified Test.Case as C')
    helpers=helpers.replace('IO a','A.Test a').replace('IO Unit','A.Test Unit').replace('IO Compiler.Compilation','A.Test Compiler.Compilation')
    helpers=helpers.replace('fatal message = do { putErr ("Tuple/list failure: " ++ message ++ "\\n"); exitWith 1 }','fatal message = A.fail ("Tuple/list failure: " ++ message)')
    helpers=helpers.replace('ioReturn','A.succeed')
    helpers=re.sub(r'passed : String -> A.Test Unit\npassed label = .*?\n','',helpers)
    helpers=re.sub(r'^ passed .*\n','',helpers,flags=re.M)
    # Runtime and compile/type leaves remain separate observations. Compilation is
    # a pure prerequisite for each leaf, not an additional passing case.
    helpers=helpers.replace(' checkResult label int result\n let term = Compiler.compiledTerm result',' let term = Compiler.compiledTerm result')
    helpers+='''\n-- Stable IDs are frozen from the reviewed authored observation inventory.
-- Assertion failures are values, so one failed leaf cannot hide later leaves.
leaf : String -> String -> String -> A.Test Unit -> C.Case
leaf identity label oracle body = C.described "language" "integration"
 (Cons "fixed" Nil) (Cons oracle Nil) (Cons "regression" (Cons "conformance" Nil))
 (C.test identity label (Cons "tuple-list" Nil) body)

withoutPrelude : A.Test Unit
withoutPrelude = do
 result <- compiled (Compiler.compileWithPrelude NoImplicitPrelude "tuple-list.emlf" (declarations ++ "case [42] of {[x] -> x; _ -> 0}"))
 checkResult "list sugar works without implicit Prelude" int result
'''
    seen=[]
    def leaf(label,action,oracle):
     identity = "tuple-list/focused/" + ("malformed-" + label[len("malformed "):].encode().hex() if oracle == "parse-rejection" else re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"))
     seen.append(identity);return 'leaf '+json.dumps(identity)+' '+json.dumps(label)+' '+json.dumps(oracle)+' ('+action+')'
    for name,statements in groups.items():
     leaves=[];locals=[]
     for st in statements:
      if st.startswith('let '): locals.append(st);continue
      if st.startswith('withoutPrelude <-'):continue
      if st=='sameFields':leaves.append(leaf('datatype field ASTs','sameFields','fixed-ast'));continue
      if st.startswith('S.mapM_'):
       for stimulus in ("(a,)", "(,a)", "(a,b,c,d,e)", "[a,]", "[,a]", "[a", "[1..3]", "[a | a <- b]", "a :"):
        label = "malformed " + stimulus
        leaves.append(leaf(label, "parseRejected " + json.dumps(label) + " " + json.dumps(stimulus), "parse-rejection"))
       continue
      if st.startswith('checkResult '):leaves.append(leaf('list sugar works without implicit Prelude','withoutPrelude','independent-reference'));continue
      m=re.match(r'(\w+) "([^"]+)"',st)
      assert m,st
      fn,label=m.groups()
      oracle={'sameBoundary':'fixed-ast','sameExpression':'fixed-ast','sameAnnotation':'fixed-ast','parseDiagnostic':'diagnostic','accepted':'independent-reference','rejected':'phase-diagnostic','moduleAccepted':'independent-reference','moduleRejected':'diagnostic','evaluates':'runtime-value'}[fn]
      if fn=='evaluates':
       assert st.endswith(' 42')
       leaves.append(leaf(label,st.replace('evaluates ','accepted ',1)[:-3]+' int','independent-reference'))
       leaves.append(leaf(label+' runtime',st,oracle))
      else: leaves.append(leaf(label,st,oracle))
     newname=name.replace('Checks','Cases')
     helpers+='\n'+newname+' : List C.Case\n'+newname+' =\n'
     for loc in locals: helpers+=' '+loc+' in\n'
     for l in leaves: helpers+=' Cons ('+l+') (\n'
     helpers+=' Nil'+')'*len(leaves)+'\n'
    helpers+='''
cases : List C.Case
cases = S.concat (Cons parserCases (Cons boundaryCases (Cons checkingCases (Cons runtimeCases (Cons scopeCases Nil)))))
'''
    require(len(seen) == 90 and len(set(seen)) == 90, "frozen projection count changed")
    return helpers


def verify(original, migrated, expected_ids):
    require(migrated == expected_projection(original),
            "module differs from reviewed frozen-source projection (support, actions or reachable registry)")
    identities = re.findall(r'leaf "([^"]+)"', migrated)
    require(len(identities) == 90, "authored leaf count changed")
    require(len(set(identities)) == 90, "duplicate authored leaf ID")
    require(set(identities) == expected_ids, "authored leaf ID set changed")
    names = ("sameExpression", "sameBoundary", "sameAnnotation", "accepted",
             "evaluates", "parseDiagnostic", "rejected", "moduleAccepted", "moduleRejected")
    call_count = 0
    for name in names:
        calls = re.findall(r'^ (' + name + r' "[^\n]*(?:\n  [^\n]*)*)', original, re.M)
        for call in calls:
            require(call in migrated, f"original input or oracle expression changed: {call}")
            call_count += 1
    helpers = ("sameExpression", "sameBoundary", "sameAnnotation", "sameFields",
               "checkResult", "accepted", "evaluates", "parseRejected",
               "parseDiagnostic", "rejected", "moduleAccepted", "moduleRejected")
    for name in helpers:
        before = re.sub(r"^ passed .*\n?", "", helper_body(original, name), flags=re.M).rstrip()
        if name == "evaluates":
            before = before.replace(" checkResult label int result\n", "")
        require(before == helper_body(migrated, name).rstrip(), f"oracle helper changed: {name}")
    # Each split runtime leaf retains its separately scheduled compile/type oracle.
    for call in re.findall(r'^ (evaluates "[^\n]*)', original, re.M):
        require(call.endswith(" 42"), "new runtime result requires review")
        checked = call.replace("evaluates ", "accepted ", 1)[:-3] + " int"
        require(checked in migrated, "runtime input lost its independent type-check leaf")
    require('Compiler.compileWithPrelude NoImplicitPrelude "tuple-list.emlf" (declarations ++ "case [42] of {[x] -> x; _ -> 0}")' in migrated,
            "NoImplicitPrelude fixture changed")
    malformed = ("(a,)", "(,a)", "(a,b,c,d,e)", "[a,]", "[,a]", "[a", "[1..3]", "[a | a <- b]", "a :")
    for source in malformed:
        action = "parseRejected " + json.dumps("malformed " + source) + " " + json.dumps(source)
        require(action in migrated, "malformed fixture changed")
    require("exitWith" not in migrated and "A.liftIO" not in migrated, "fatal/umbrella IO returned")
    return call_count


def main():
    original = frozen(SOURCE)
    # The baseline contains the source, while the design inventory was added
    # afterward. IDs are independently derived once from its authored labels.
    helpers = ("sameExpression", "sameBoundary", "sameAnnotation", "accepted",
               "evaluates", "parseDiagnostic", "rejected", "moduleAccepted", "moduleRejected", "checkResult")
    labels = []
    for name in helpers:
        for label in re.findall(r'^ ' + name + r' "([^"]+)"', original, re.M):
            labels.append(label)
            if name == "evaluates":
                labels.append(label + " runtime")
    labels.append("datatype field ASTs")
    expected = {"tuple-list/focused/" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") for label in labels}
    for source in ("(a,)", "(,a)", "(a,b,c,d,e)", "[a,]", "[,a]", "[a", "[1..3]", "[a | a <- b]", "a :"):
        expected.add("tuple-list/focused/malformed-" + source.encode().hex())
    require(len(expected) == 90, "frozen baseline derivation changed")
    migrated = (ROOT / IMPLEMENTATION).read_text()
    count = verify(original, migrated, expected)
    first = re.search(r'leaf "([^"]+)"', migrated).group(1)
    mutations = {
        "require_always_succeeds": migrated.replace("require condition message = if condition then A.succeed Unit else fatal message", "require condition message = A.succeed Unit", 1),
        "fatal_always_succeeds": migrated.replace('fatal message = A.fail ("Tuple/list failure: " ++ message)', 'fatal message = A.succeed (panic "unused")', 1),
        "datatype_declaration_changed": migrated.replace("data List a = Nil | Cons a (List a)", "data List a = Nil | Cons a a", 1),
        "pair_constructor_changed": migrated.replace('pair = apply2 (SConstructor "Pair")', 'pair = apply2 (SConstructor "Triple")', 1),
        "runtime_group_unreachable": migrated.replace("(Cons runtimeCases (Cons scopeCases Nil))", "(Cons scopeCases Nil)", 1),
        "leaf_body_discarded": migrated.replace('(C.test identity label (Cons "tuple-list" Nil) body)', '(C.test identity label (Cons "tuple-list" Nil) (A.succeed Unit))', 1),
        "missing_leaf": migrated.replace('leaf "' + first + '"', 'removed "' + first + '"', 1),
        "unknown_id": migrated.replace(first, first + "-unknown", 1),
        "duplicate_id": migrated.replace("tuple-list/focused/triple-ast", first, 1),
        "fixed_ast_changed": migrated.replace('(SConstructor "Unit")', '(SConstructor "WrongUnit")', 1),
        "independent_checker_removed": migrated.replace("independent <- right (Independent.checkClosed term)", "independent <- right (Check.checkClosed term)", 1),
        "rejection_phase_removed": migrated.replace("eqString (Compiler.prettyPhase (Compiler.phase error)) (Compiler.prettyPhase phase) && ", "", 1),
        "runtime_oracle_changed": migrated.replace("actual == expected", "actual == actual", 1),
        "location_check_removed": migrated.replace('contains "tuple-list.emlf:" error', 'contains "" error', 1),
    }
    for name, mutant in mutations.items():
        require(mutant != migrated, f"inactive mutation: {name}")
        try:
            verify(original, mutant, expected)
        except ValueError:
            continue
        raise ValueError(f"static control failed to reject {name}")
    dispatcher = (ROOT / SOURCE).read_text()
    require('Cons "--framework" rest -> finish rest' in dispatcher and
            "Runner.run args TupleList.cases" in dispatcher,
            "opt-in entrypoint bypasses registry")
    require("_ -> Legacy.main" in dispatcher, "unverified registry replaced legacy default")
    legacy = (ROOT / "tests/Tests/TupleListLegacy.emlf").read_text()
    require(legacy == original.replace("module TupleListMain where", "module Tests.TupleListLegacy where", 1),
            "frozen legacy implementation changed")
    # The separate native path is not replaced by focused interpreter checks.
    for path in ("tools/release/test-tuple-list.sh", "tests/fixtures/tuple-list-runtime.emlf", "tests/fixtures/tuple-list-runtime.stdout"):
        require((ROOT / path).read_text() == frozen(path), f"native route changed: {path}")
    print(json.dumps({"kind": "static-source-preservation", "baseline": BASELINE,
                      "leaf_ids": 90, "default_implementation": "legacy", "literal_calls_preserved": count,
                      "oracle_helpers_preserved": 12, "mutation_controls": len(mutations),
                      "compilation_verified": False, "semantic_execution_verified": False}, indent=2))


if __name__ == "__main__":
    main()
