"""Synthetic protocol controls only; these are NOT compiler/source receipts."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import module_custody as c
from module_projection import ProjectionError


INT = {"tag": "constructor", "name": "Int", "arguments": []}
EDGE = {"from": 1, "to": 2}


def source(name, path, *, imports=(), values=(), body=None):
    return {"path": path, "name": name, "exports": None,
            "imports": [{"module": x, "qualified": False, "alias": None,
                         "selection": {"tag": "everything"}} for x in imports],
            "declarations": [], "classes": [], "instances": [],
            "values": list(values), "body": body, "syntax": "legacy-emlf-v1"}


def value(name, body):
    return {"name": name, "annotation": None, "body": body}


def int64(n):
    return {"tag": "int64", "value": n}


def var(n):
    return {"tag": "var", "name": n}


def synthetic_valid_custody():
    """Small coherent protocol object, deliberately not a real builtin facade.

    The public frontend must bind a genuine pinned compiler, which these unit
    fixtures do not claim. This helper must never be used for candidate admission.
    """
    prelude = source("Prelude", "<Prelude>", imports=["MLF.Primitive"])
    prelude["exports"] = [{"tag": "module", "name": "MLF.Primitive"}]
    primitive = source("MLF.Primitive", "<MLF.Primitive>")
    guest = source("Small", "./Small.emlf", values=[value("answer", int64(42))])
    root = source(None, "<stdin>", imports=["Small"], body=var("Small.answer"))
    modules = [{"source": s, "compiler_owned": s["name"] in c.BUILTINS,
                "renamed": {k: copy.deepcopy(s[k]) for k in ("declarations", "classes", "instances", "values", "body")}, "scope": []}
               for s in (prelude, primitive, guest, root)]
    # Build the exact protocol's finite namespace inventory independently of the
    # validator entrypoint. No source text is parsed or compiled by this helper.
    entities = list(c.expected_entities(modules).values())
    entities.sort(key=c.sort_entity)
    rows, counter = [], 0
    special = {("HasCallStack", "managed_constraint"): "MLFHasCallStack",
               ("CallStack", "builtin_type"): "MLFCallStack",
               ("callStack", "value"): "mlfCallStack"}
    for entity in entities:
        role, spelling = entity["role"]["tag"], entity["spelling"]
        if entity["owner"] == "MLF.Primitive" and (spelling, role) in special:
            allocated = special[spelling, role]
        elif role == "builtin_type":
            allocated = spelling
        else:
            prefix = "ModuleEntity" if entity["namespace"] == "types" or role == "constructor" else "moduleEntity"
            allocated = prefix + str(counter)
            counter += 1
        rows.append({"entity": entity, "allocated": allocated})
    answer = next(r for r in rows if r["entity"]["owner"] == "Small")
    internal = answer["allocated"]
    modules[2]["renamed"]["values"][0]["name"] = internal
    modules[3]["renamed"]["body"] = var(internal)
    for index, spellings in ((2, ("Small.answer", "answer")), (3, ("Small.answer",))):
        modules[index]["scope"] = [{"namespace": "terms", "spelling": n,
                                    "entities": [copy.deepcopy(answer["entity"])]}
                                   for n in spellings]
    display = [{"allocated": r["allocated"], "display": r["entity"]["spelling"] if r["entity"]["owner"] == "Prelude" else r["entity"]["owner"] + "." + r["entity"]["spelling"]} for r in rows]
    display.sort(key=lambda x: x["allocated"])
    resolution = {"entities": rows, "modules": modules, "display_names": display,
                  "instances": [], "value_scopes": [{"name": internal, "scope": []}],
                  "instance_scopes": [],
                  "reach": [{"owner": "MLF.Primitive", "modules": ["MLF.Primitive"]},
                            {"owner": "Main", "modules": ["MLF.Primitive", "Main", "Small"]},
                            {"owner": "Prelude", "modules": ["MLF.Primitive", "Prelude"]},
                            {"owner": "Small", "modules": ["MLF.Primitive", "Small"]}]}
    custody = {"policy": "legacy-single-root/1", "root_file": "<stdin>",
               "prelude": "NoImplicitPrelude", "include_paths": [], "search_paths": ["."],
               "loaded": [{"source": copy.deepcopy(guest), "text": "synthetic guest bytes", "is_root": False},
                          {"source": copy.deepcopy(root), "text": "synthetic root bytes", "is_root": True}],
               "resolution": resolution}
    name = {"id": 10, "hint": internal}
    expr = {"tag": "let", "name": internal, "value": int64(42), "body": var(internal)}
    raw = {"tag": "let", "name": name, "value": int64(42), "body": var(name)}
    typed = {"generation": 0, "form": {"tag": "let", "name": name,
             "value": {"generation": 1, "form": int64(42)},
             "body": {"generation": 2, "form": {"tag": "var", "name": name, "edge": None}},
             "edge": copy.deepcopy(EDGE)}}
    binding = {"name": name, "source_internal_name": internal,
               "association": "resolved_outer_declaration", "resolver_allocation": answer}
    bindings = [{"path": [], "generation": 0, "kind": "let", "bindings": [binding]}]
    origins = {"policy": "constraint-core-association/1",
               "source_program": {"declarations": [], "body": copy.deepcopy(expr)},
               "lowered_expression": copy.deepcopy(expr), "source_core": copy.deepcopy(expr),
               "typed_skeleton": typed, "resolved_evidence": [], "bindings": bindings,
               "erased_bindings": [{"path": [], "kind": "let", "names": [name]}]}
    original = {"checked_type": copy.deepcopy(INT), "annotated": copy.deepcopy(raw),
                "erased": copy.deepcopy(raw), "source_erased": copy.deepcopy(raw),
                "binder_origins": copy.deepcopy(origins), "ordinary_whole_check_passed": True,
                "root_type_alpha_equal": True, "source_erasure_equal": True}
    return custody, original


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.custody, self.original = synthetic_valid_custody()

    def rejects(self, pattern=None):
        if pattern:
            with self.assertRaisesRegex((c.CustodyError, ProjectionError), pattern):
                c.validate_custody(self.custody, self.original)
        else:
            with self.assertRaises((c.CustodyError, ProjectionError)):
                c.validate_custody(self.custody, self.original)

    def test_valid_synthetic_summary_exposes_snapshot_link_and_boundary(self):
        summary = c.validate_custody(self.custody, self.original)
        self.assertEqual(summary["source_binding_count"], 1)
        self.assertEqual(summary["resolved_outer_binding_count"], 1)
        self.assertEqual(summary["loaded_sources"][0]["path"], "./Small.emlf")
        self.assertIn("does not parse", summary["trust_boundaries"][0])

    def test_all_guards_require_actual_boolean(self):
        for key in ("ordinary_whole_check_passed", "root_type_alpha_equal", "source_erasure_equal"):
            for bad in (False, 1, "true", None):
                with self.subTest(key=key, bad=bad):
                    self.custody, self.original = synthetic_valid_custody()
                    self.original[key] = bad
                    self.rejects("guard")

    def test_unknown_original_key(self):
        self.original["approved"] = True
        self.rejects("exact keys")

    def test_unknown_nested_field(self):
        self.custody["loaded"][0]["source"]["values"][0]["body"]["shadow"] = 1
        self.rejects("exact keys")

    def test_loaded_and_resolved_ast_must_be_exact(self):
        self.custody["loaded"][0]["source"]["values"][0]["body"]["value"] = 43
        self.rejects("same-read")

    def test_joint_original_ast_mutation_hits_renamed_correspondence(self):
        self.custody["loaded"][0]["source"]["values"][0]["body"]["value"] = 43
        self.custody["resolution"]["modules"][2]["source"]["values"][0]["body"]["value"] = 43
        self.rejects("renamed non-identifier")

    def test_text_boundary_exposed_not_falsely_parsed(self):
        self.custody["loaded"][0]["text"] = "not actual source: external snapshot/producer must reject"
        result = c.validate_custody(self.custody, self.original)
        self.assertEqual(result["loaded_sources"][0]["text"], self.custody["loaded"][0]["text"])

    def test_guest_cannot_be_compiler_owned(self):
        self.custody["resolution"]["modules"][2]["compiler_owned"] = True
        self.rejects("compiler-owned")

    def test_compiler_module_path_cannot_be_guest_path(self):
        self.custody["resolution"]["modules"][1]["source"]["path"] = "./MLF/Primitive.emlf"
        self.rejects("compiler source")

    def test_unsafe_guest_path(self):
        self.custody["loaded"][0]["source"]["path"] = "../Small.emlf"
        self.rejects("unsafe")

    def test_loaded_order_omission(self):
        self.custody["loaded"] = self.custody["loaded"][1:]
        self.rejects("absent guest")

    def test_resolver_omission(self):
        self.custody["resolution"]["entities"].pop()
        self.rejects("inventory count")

    def test_same_spelling_wrong_owner(self):
        binding = self.original["binder_origins"]["bindings"][0]["bindings"][0]
        binding["resolver_allocation"]["entity"]["owner"] = "Main"
        self.rejects("origin rows")

    def test_wrong_namespace(self):
        self.custody["resolution"]["entities"][-1]["entity"]["namespace"] = "types"
        self.rejects("role/namespace")

    def test_wrong_role_payload(self):
        self.custody["resolution"]["entities"][-1]["entity"]["role"]["datatype"] = "Fake"
        self.rejects("exact keys")

    def test_same_hint_wrong_actual_id(self):
        form = self.original["binder_origins"]["typed_skeleton"]["form"]["body"]["form"]
        form["name"] = {**form["name"], "id": 99}
        self.rejects("lexical")

    def test_origin_row_generation_change(self):
        self.original["binder_origins"]["bindings"][0]["generation"] = 99
        self.rejects("origin rows")

    def test_origin_row_path_change(self):
        self.original["binder_origins"]["bindings"][0]["path"] = ["body"]
        self.rejects("origin rows")

    def test_erased_graph_row_change(self):
        self.original["binder_origins"]["erased_bindings"][0]["names"] = []
        self.rejects("erased binding rows")

    def test_typed_literal_corruption(self):
        self.original["binder_origins"]["typed_skeleton"]["form"]["value"]["form"]["value"] = 43
        self.rejects("literal")

    def test_lowered_core_corruption(self):
        self.original["binder_origins"]["source_core"]["value"]["value"] = 43
        self.rejects("Core correspondence")

    def test_original_erasure_corruption(self):
        self.original["source_erased"]["value"]["value"] = 43
        self.rejects("source erasure")

    def test_allocation_skip_or_index_forgery(self):
        self.custody["resolution"]["entities"][-1]["allocated"] = "moduleEntity999"
        self.rejects("fresh index")

    def test_dependency_reach_corruption(self):
        self.custody["resolution"]["reach"][-1]["modules"] = ["Small"]
        self.rejects("dependency reach")

    def test_instance_visibility_corruption(self):
        self.custody["resolution"]["value_scopes"][0]["scope"] = [0]
        self.rejects("visibility scopes")

    def test_unknown_source_constructor(self):
        self.custody["loaded"][0]["source"]["values"][0]["body"] = {"tag": "future"}
        self.rejects("unknown expr")

    def test_forged_source_primitive(self):
        self.custody["loaded"][0]["source"]["values"][0]["body"] = {"tag": "primitive", "id": 8, "name": "mulInt"}
        self.rejects("primitive")

    def test_boolean_not_int64(self):
        self.original["binder_origins"]["typed_skeleton"]["form"]["value"]["form"]["value"] = True
        self.rejects("signed integer")

    def test_double_signed_bits_schema(self):
        c.validate_schema({"tag": "double", "bits_i64": -(1 << 63)}, "core")
        for bad in (True, 1 << 63, -(1 << 63) - 1, 0.0):
            with self.assertRaises(c.CustodyError):
                c.validate_schema({"tag": "double", "bits_i64": bad}, "core")

    def test_cyclic_json_rejected(self):
        self.custody["loaded"].append(self.custody)
        self.rejects("cyclic")

    def test_deep_schema_no_python_recursion(self):
        expression = int64(1)
        for _ in range(1100):
            expression = {"tag": "lambda", "name": "x", "body": expression}
        with self.assertRaisesRegex(c.CustodyError, "depth"):
            c.validate_schema(expression, "core")

    def test_schema_at_depth_900_is_iterative(self):
        expression = int64(1)
        for _ in range(900):
            expression = {"tag": "lambda", "name": "x", "body": expression}
        c.validate_schema(expression, "core")

    def test_rename_lexical_shadow_not_assigned_to_module(self):
        scope = self.custody["resolution"]["modules"][2]["scope"]
        allocations = {c.entity_key(r["entity"]): r for r in self.custody["resolution"]["entities"]}
        original = {"tag": "lambda", "name": "answer", "annotation": None, "body": var("answer")}
        renamed = copy.deepcopy(original)
        renamed["body"]["name"] = self.original["binder_origins"]["bindings"][0]["bindings"][0]["source_internal_name"]
        with self.assertRaisesRegex(c.CustodyError, "lexical binder"):
            c._compare_renamed(original, renamed, scope, allocations)

    def test_source_core_checked_directed_replay(self):
        signature = {"tag": "arrow", "from": {"tag": "constructor", "name": "Int", "arguments": []}, "to": {"tag": "constructor", "name": "Int", "arguments": []}}
        expression = {"tag": "lambda", "name": "x", "annotation": None, "body": var("x")}
        directed = c._directed(signature, expression)
        self.assertEqual(directed["annotation"]["type"], signature["from"])
        core = c._desugar({"tag": "annotation", "value": directed, "annotation": {"existentials": [], "type": signature}})
        self.assertEqual(core["tag"], "application")
        self.assertEqual(core["argument"]["body"]["tag"], "let")
        self.assertEqual(core["argument"]["body"]["value"]["function"]["tag"], "coerce")

    def test_nonrecursive_rhs_not_in_scope(self):
        n = {"id": 1, "hint": "x"}
        core = {"tag": "let", "name": "x", "value": var("x"), "body": int64(0)}
        typed = {"generation": 0, "form": {"tag": "let", "name": n, "edge": EDGE,
                  "value": {"generation": 1, "form": {"tag": "var", "name": n, "edge": None}},
                  "body": {"generation": 2, "form": int64(0)}}}
        with self.assertRaisesRegex(c.CustodyError, "no lexical"):
            c._pair_core(core, typed, {}, [])

    def test_recursive_group_arity_no_zip_truncation(self):
        core = {"tag": "letrec", "bindings": [{"name": "x", "mode": {"tag": "infer"}, "value": int64(0)}], "body": var("x")}
        typed = {"generation": 0, "form": {"tag": "letrec", "bindings": [], "body": {"generation": 1, "form": int64(0)}, "edge": EDGE}}
        with self.assertRaisesRegex(c.CustodyError, "group count"):
            c._pair_core(core, typed, {}, [])

    def test_same_spelling_type_cannot_rename_to_term_allocation(self):
        term = c.entity("M", "T", "value")
        ty = c.entity("M", "T", "datatype")
        allocations = {c.entity_key(term): {"entity": term, "allocated": "moduleEntity0"},
                       c.entity_key(ty): {"entity": ty, "allocated": "ModuleEntity1"}}
        scope = [{"namespace": "terms", "spelling": "T", "entities": [term]},
                 {"namespace": "types", "spelling": "T", "entities": [ty]}]
        original = {"tag": "annotation", "value": int64(1),
                    "annotation": {"existentials": [], "type": {"tag": "constructor", "name": "T", "arguments": []}}}
        renamed = copy.deepcopy(original)
        renamed["annotation"]["type"]["name"] = "moduleEntity0"
        with self.assertRaisesRegex(c.CustodyError, "namespace allocation"):
            c._compare_renamed(original, renamed, scope, allocations)
        renamed["annotation"]["type"]["name"] = "ModuleEntity1"
        c._compare_renamed(original, renamed, scope, allocations)

    def test_type_variable_cannot_become_global_allocation(self):
        e = c.entity("M", "a", "datatype")
        scope = [{"namespace": "types", "spelling": "a", "entities": [e]}]
        allocations = {c.entity_key(e): {"entity": e, "allocated": "ModuleEntity1"}}
        original = {"existentials": [], "type": {"tag": "var", "name": "a"}}
        renamed = {"existentials": [], "type": {"tag": "var", "name": "ModuleEntity1"}}
        with self.assertRaisesRegex(c.CustodyError, "lexical binder"):
            c._compare_renamed(original, renamed, scope, allocations)

    def test_primitive_correspondence_uses_interface_not_lexical_set(self):
        entity = c.entity("Prelude", "addInt", "primitive", id=8, name="addInt")
        scope = [{"namespace": "terms", "spelling": "addInt", "entities": [entity]}]
        allocations = {c.entity_key(entity): {"entity": entity, "allocated": "moduleEntity1"}}
        original = {"tag": "application", "function": var("addInt"), "argument": int64(1)}
        renamed = {"tag": "application", "function": {"tag": "primitive", "id": 8, "name": "addInt"}, "argument": int64(1)}
        c._compare_renamed(original, renamed, scope, allocations)

    def test_nested_same_internal_spelling_stays_compiler_local(self):
        internal = "moduleEntity9"
        allocation = {"entity": c.entity("M", "answer", "value"), "allocated": internal}
        parameter, local = {"id": 11, "hint": "x"}, {"id": 12, "hint": internal}
        core = {"tag": "lambda", "name": "x", "body": {"tag": "let", "name": internal, "value": int64(1), "body": var(internal)}}
        typed = {"generation": 0, "form": {"tag": "lambda", "name": parameter, "domain": 1, "edge": EDGE,
                 "body": {"generation": 1, "form": {"tag": "let", "name": local, "edge": EDGE,
                   "value": {"generation": 2, "form": int64(1)},
                   "body": {"generation": 3, "form": {"tag": "var", "name": local, "edge": None}}}}}}
        rows, evidence = c._pair_core(core, typed, {internal: allocation}, [])
        self.assertEqual(rows[0]["path"], ["body"])
        self.assertEqual(rows[0]["bindings"][0]["association"], "compiler_local_or_generated")
        self.assertIsNone(rows[0]["bindings"][0]["resolver_allocation"])
        self.assertEqual(evidence, set())

    def test_checked_pair_and_erasure_replay(self):
        ty = {"tag": "constructor", "name": "Int", "arguments": []}
        core = {"tag": "checked", "type": ty, "expression": int64(7)}
        name = {"id": 10, "hint": "coerce"}
        body = {"generation": 1, "form": {"tag": "application",
                 "function": {"generation": 2, "form": {"tag": "coerce", "name": name, "domain": 1, "codomain": 2}},
                 "argument": {"generation": 3, "form": int64(7)}, "function_edge": EDGE, "argument_edge": EDGE}}
        typed = {"generation": 0, "form": {"tag": "checked", "variables": [], "body": body, "edge": EDGE}}
        self.assertEqual(c._pair_core(core, typed, {}, []), ([], set()))
        self.assertEqual(c._erase_typed(typed, {}), {"tag": "application", "function": {"tag": "lambda", "parameter": name, "body": var(name)}, "argument": int64(7)})
        body["form"]["argument"]["form"]["value"] = 8
        with self.assertRaisesRegex(c.CustodyError, "literal"):
            c._pair_core(core, typed, {}, [])

    def test_pattern_default_identity_and_wildcards(self):
        binder = {"id": 9, "hint": "x"}
        scope = c._pair_pattern({"tag": "default", "binder": "x"}, {"tag": "default", "binder": binder}, {})
        self.assertEqual(scope, {"x": binder})
        with self.assertRaisesRegex(c.CustodyError, "wildcard"):
            c._pair_pattern({"tag": "default", "binder": None}, {"tag": "default", "binder": binder}, {})

    def test_recursive_all_members_scope_and_order(self):
        x, y = {"id": 10, "hint": "x"}, {"id": 11, "hint": "y"}
        core = {"tag": "letrec", "bindings": [
                {"name": "x", "mode": {"tag": "infer"}, "value": var("y")},
                {"name": "y", "mode": {"tag": "infer"}, "value": int64(2)}], "body": var("x")}
        def definition(name, generation, form):
            return {"name": name, "declaration": 1, "value": {"generation": generation, "form": form},
                    "edge": EDGE, "closure": {"group": 1, "copies": []}}
        typed = {"generation": 0, "form": {"tag": "letrec", "edge": EDGE,
                 "bindings": [definition(x, 1, {"tag": "var", "name": y, "edge": None}), definition(y, 2, int64(2))],
                 "body": {"generation": 3, "form": {"tag": "var", "name": x, "edge": None}}}}
        rows, _ = c._pair_core(core, typed, {}, [])
        self.assertEqual([b["source_internal_name"] for b in rows[0]["bindings"]], ["x", "y"])
        typed["form"]["bindings"].reverse()
        with self.assertRaisesRegex(c.CustodyError, "hint mismatch"):
            c._pair_core(core, typed, {}, [])

    def test_all_129_primitive_enums_and_arity_guard(self):
        for code, name in c.PRIMITIVES.items():
            source = {"tag": "primitive", "id": code, "name": name}
            typed = {"generation": 0, "form": {**source, "arguments": [1] * c.PRIMITIVE_ARITIES.get(code, 0)}}
            c.validate_schema(source, "core")
            c.validate_schema(typed, "typed")
            self.assertEqual(c._pair_core(source, typed, {}, []), ([], set()))
            typed["form"]["arguments"].append(2)
            with self.assertRaisesRegex(c.CustodyError, "arity"):
                c._pair_core(source, typed, {}, [])

    def test_known_global_cannot_keep_unallocated_spelling(self):
        self.custody["resolution"]["modules"][3]["renamed"]["body"]["name"] = "Small.answer"
        self.rejects("actual allocation")

    def test_known_primitive_cannot_stay_source_variable(self):
        entity = c.entity("Prelude", "addInt", "primitive", id=8, name="addInt")
        scope = [{"namespace": "terms", "spelling": "addInt", "entities": [entity]}]
        allocations = {c.entity_key(entity): {"entity": entity, "allocated": "moduleEntity1"}}
        with self.assertRaisesRegex(c.CustodyError, "value/method"):
            c._compare_renamed(var("addInt"), var("addInt"), scope, allocations)

    def test_own_scope_omission_is_detected(self):
        self.custody["resolution"]["modules"][2]["scope"].pop()
        self.rejects("own declaration")

    def test_complete_wired_constructor_type_arities(self):
        arities = {"MLFLegacyUnit": 0, "MLFStackFrame": 0, "MLFStackEvidence": 0,
                   "()": 0, "[]": 1, ":": 1,
                   **{"(" + "," * (n - 1) + ")": n for n in range(2, 65)}}
        for name, arity in arities.items():
            core = {"tag": "constructor", "name": name}
            typed = {"generation": 0, "form": {**core, "arguments": [1] * arity}}
            self.assertEqual(c._pair_core(core, typed, {}, []), ([], set()))

    def test_explicit_primitive_metadata_is_not_namespace_renamed(self):
        for code, spelling in c.PRIMITIVES.items():
            e = {"owner": "Prelude", "spelling": spelling, "namespace": "terms",
                 "role": {"tag": "primitive", "id": code, "name": spelling}}
            scope = [{"namespace": "terms", "spelling": spelling, "entities": [e]}]
            allocations = {c.entity_key(e): {"entity": e, "allocated": "moduleEntity" + str(code)}}
            n = {"tag": "primitive", "id": code, "name": spelling}
            c._compare_renamed(n, copy.deepcopy(n), scope, allocations)

    def test_explicit_primitive_enum_change_rejected_even_if_both_known(self):
        n = {"tag": "primitive", "id": 8, "name": "addInt"}
        forged = {"tag": "primitive", "id": 9, "name": "subInt"}
        with self.assertRaisesRegex(c.CustodyError, "explicit primitive identity"):
            c._compare_renamed(n, forged, [], {})

    def test_callsite_display_is_preserved_but_body_resolved(self):
        e = {"owner": "Prelude", "spelling": "addInt", "namespace": "terms",
             "role": {"tag": "primitive", "id": 8, "name": "addInt"}}
        scope = [{"namespace": "terms", "spelling": "addInt", "entities": [e]}]
        allocations = {c.entity_key(e): {"entity": e, "allocated": "moduleEntity42"}}
        original = {"tag": "call_site", "name": "addInt", "location": {}, "body": {"tag": "var", "name": "addInt"}}
        renamed = {**original, "body": {"tag": "primitive", "id": 8, "name": "addInt"}}
        c._compare_renamed(original, renamed, scope, allocations)
        with self.assertRaisesRegex(c.CustodyError, "display metadata"):
            c._compare_renamed(original, {**renamed, "name": "moduleEntity42"}, scope, allocations)
        with self.assertRaises(c.CustodyError):
            c._compare_renamed(original, {**renamed, "body": {"tag": "var", "name": "addInt"}}, scope, allocations)

    def test_unknown_surface_transform_fails_closed(self):
        with self.assertRaisesRegex(c.CustodyError, "outside independently"):
            c._desugar({"tag": "do", "statements": [], "body": int64(0)})


if __name__ == "__main__":
    unittest.main()
