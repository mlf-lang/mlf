"""Bounded, fail-closed replay of captured module and constraint custody.

This is not an MLF parser, namespace resolver, inference engine, or checker.
Same-read text -> SourceModule, class lowering, and the genuine checked receipt
remain obligations of the pinned compiled producer and the snapshot frontend.
All traversals here use explicit worklists; malformed/unknown evidence rejects.
"""
from module_projection import (validate_raw_term, erase_total, exact_equal,
                               PRIMITIVES, ProjectionError)

MAX_NODES = 100_000
MAX_DEPTH = 1024
MAX_SCHEMA_CELLS = MAX_NODES * 32
MAX_SOURCE_BYTES = 8 * 1024 * 1024
BUILTINS = {"Prelude", "MLF.Primitive"}
ORIGINAL_KEYS = {"checked_type", "annotated", "erased", "source_erased",
                 "binder_origins", "ordinary_whole_check_passed",
                 "root_type_alpha_equal", "source_erasure_equal"}


class CustodyError(ValueError):
    pass


def fail(message):
    raise CustodyError(message)


def require(condition, message):
    if not condition:
        fail(message)


def obj(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ": exact keys required")


def equal(left, right, label):
    require(exact_equal(left, right), label + ": structural mismatch")


# A small schema interpreter validates every producer constructor, never an
# untyped "any" payload. ?T and [T] denote optional/list; all other names resolve
# below. Raw XMLF has its own total validator, shared with projection replay.
RECORDS = {
    "name": {"id": "nat", "hint": "str"},
    "parameter": {"name": "str", "kind": "kind"},
    "constructor_decl": {"name": "str", "fields": "[field]"},
    "predicate": {"name": "str", "arguments": "[stype]"},
    "annotation": {"existentials": "[str]", "type": "stype"},
    "source_recursive": {"name": "str", "mode": "mode", "value": "expr"},
    "core_recursive": {"name": "str", "mode": "mode", "value": "core"},
    "source_alt": {"pattern": "spattern", "body": "expr"},
    "core_alt": {"pattern": "spattern", "body": "core"},
    "equation": {"patterns": "[spattern]", "body": "expr"},
    "candidate": {"role": "evidence_role", "name": "str"},
    "span": {"package": "str", "module": "str", "file": "str", "line": "int",
             "column": "int", "end_line": "int", "end_column": "int"},
    "method": {"name": "str", "type": "stype"},
    "instance_method": {"name": "str", "body": "expr"},
    "class": {"name": "str", "parameters": "[parameter]", "supers": "[predicate]", "methods": "[method]"},
    "instance": {"variables": "[parameter]", "context": "[predicate]", "class": "str", "head": "[stype]", "methods": "[instance_method]"},
    "value": {"name": "str", "annotation": "?annotation", "body": "expr"},
    "import": {"module": "str", "qualified": "bool", "alias": "?str", "selection": "selection"},
    "source": {"path": "str", "name": "?str", "exports": "?[export]", "imports": "[import]", "declarations": "[declaration]", "classes": "[class]", "instances": "[instance]", "values": "[value]", "body": "?expr", "syntax": "syntax"},
    "renamed": {"declarations": "[declaration]", "classes": "[class]", "instances": "[instance]", "values": "[value]", "body": "?expr"},
    "entity": {"owner": "str", "spelling": "str", "role": "role", "namespace": "namespace"},
    "allocation": {"entity": "entity", "allocated": "str"},
    "interface_entry": {"namespace": "namespace", "spelling": "str", "entities": "[entity]"},
    "resolved_module": {"source": "source", "compiler_owned": "bool", "renamed": "renamed", "scope": "[interface_entry]"},
    "display": {"allocated": "str", "display": "str"},
    "owned_instance": {"owner": "str", "instance": "instance"},
    "value_scope": {"name": "str", "scope": "[nat]"},
    "reach": {"owner": "str", "modules": "[str]"},
    "resolution": {"entities": "[allocation]", "modules": "[resolved_module]", "display_names": "[display]", "instances": "[owned_instance]", "value_scopes": "[value_scope]", "instance_scopes": "[[nat]]", "reach": "[reach]"},
    "loaded": {"source": "source", "text": "str", "is_root": "bool"},
    "custody": {"policy": "str", "root_file": "str", "prelude": "str", "include_paths": "[str]", "search_paths": "[str]", "loaded": "[loaded]", "resolution": "resolution"},
    "edge": {"from": "nat", "to": "nat"},
    "map_pair": {"key": "nat", "value": "nat"},
    "closure": {"group": "nat", "copies": "[map_pair]"},
    "typed_recursive": {"name": "name", "declaration": "nat", "value": "typed", "edge": "edge", "closure": "?closure"},
    "typed_alt": {"pattern": "pattern", "body": "typed", "edge": "edge"},
    "typed_variable": {"id": "nat", "kind": "kind"},
    "typed": {"generation": "nat", "form": "form"},
    "origin_binding": {"name": "name", "source_internal_name": "str", "association": "association", "resolver_allocation": "?allocation"},
    "origin_row": {"path": "[str]", "generation": "nat", "kind": "binding_kind", "bindings": "[origin_binding]"},
    "erased_row": {"path": "[str]", "kind": "binding_kind", "names": "[name]"},
    "source_program": {"declarations": "[declaration]", "body": "expr"},
    "resolved_evidence": {"generation": "nat", "term": "raw_term"},
    "origins": {"policy": "str", "source_program": "source_program", "lowered_expression": "expr", "source_core": "core", "typed_skeleton": "typed", "resolved_evidence": "[resolved_evidence]", "bindings": "[origin_row]", "erased_bindings": "[erased_row]"},
}
TAGS = {
    "kind": {"star": {}, "arrow": {"from": "kind", "to": "kind"}},
    "field": {"parameter": {"name": "str"}, "function": {"from": "field", "to": "field"}, "applied": {"name": "str", "arguments": "[field]"}, "application": {"function": "field", "argument": "field"}, "quantified": {"name": "str", "kind": "kind", "body": "field"}},
    "declaration": {"data": {"name": "str", "parameters": "[str]", "constructors": "[constructor_decl]"}, "data_kind": {"name": "str", "parameters": "[parameter]", "constructors": "[constructor_decl]"}},
    "rtype": {"var": {"id": "nat"}, "bottom": {}, "bottom_kind": {"kind": "kind"}, "arrow": {"from": "rtype", "to": "rtype"}, "constructor": {"name": "str", "arguments": "[rtype]"}, "apply": {"function": "rtype", "argument": "rtype"}, "forall": {"id": "nat", "bound": "rtype", "body": "rtype"}},
    "stype": {"var": {"name": "str"}, "bottom": {}, "bottom_kind": {"kind": "kind"}, "arrow": {"from": "stype", "to": "stype"}, "constructor": {"name": "str", "arguments": "[stype]"}, "apply": {"function": "stype", "argument": "stype"}, "forall": {"flag": "flag", "name": "str", "bound": "stype", "body": "stype"}, "qualified": {"predicates": "[predicate]", "body": "stype"}},
    "source_string": {"scalar": {"text": "str"}, "chars": {"codes": "[int]"}},
    "spattern": {"constructor": {"name": "str", "fields": "[?str]"}, "default": {"binder": "?str"}, "nested": {"name": "str", "fields": "[spattern]"}, "annotated": {"name": "str", "annotation": "annotation"}, "int64": {"value": "int"}, "string": {"value": "str"}, "overloaded_string": {"value": "source_string", "equality": "str", "conversion": "str"}, "bool": {"value": "bool"}, "as": {"name": "str", "pattern": "spattern"}, "lazy": {"pattern": "spattern"}},
    "pattern": {"constructor": {"constructor": "str", "fields": "[?name]"}, "default": {"binder": "?name"}},
    "mode": {"infer": {}, "check": {"annotation": "annotation"}},
    "members": {"abstract": {}, "all": {}, "members": {"names": "[str]"}},
    "export": {"value": {"name": "str"}, "type": {"name": "str", "members": "members"}, "module": {"name": "str"}},
    "selection": {"everything": {}, "only": {"items": "[export]"}, "hiding": {"items": "[export]"}},
    "role": {"value": {}, "datatype": {}, "class": {}, "constructor": {"datatype": "str"}, "method": {"class": "str"}, "builtin_type": {}, "primitive": {"id": "nat", "name": "str"}, "boolean": {"value": "bool"}, "managed_constraint": {}},
    "statement": {"bind": {"pattern": "spattern", "value": "expr"}, "then": {"value": "expr"}, "let": {"name": "str", "annotation": "?annotation", "value": "expr"}, "letrec": {"bindings": "[source_recursive]"}},
    "evidence_binding": {"inferred": {"role": "evidence_role", "name": "name", "identity": "nat", "polymorphic": "bool"}, "declared": {"role": "evidence_role", "name": "name", "type": "rtype"}},
}
_ATOMS = {"int64": {"value": "int"}, "double": {"bits_i64": "int"}, "bool": {"value": "bool"}, "string": {"value": "str"}, "primitive": {"id": "nat", "name": "str"}}
TAGS["expr"] = dict(_ATOMS, **{
    "var": {"name": "str"}, "constructor": {"name": "str"}, "lambda": {"name": "str", "annotation": "?annotation", "body": "expr"}, "application": {"function": "expr", "argument": "expr"}, "let": {"name": "str", "value": "expr", "body": "expr"}, "annotation": {"value": "expr", "annotation": "annotation"}, "signature": {"value": "expr", "annotation": "annotation"}, "case": {"scrutinee": "expr", "alternatives": "[source_alt]"}, "do": {"statements": "[statement]", "body": "expr"}, "equations": {"rows": "[equation]"}, "letrec": {"bindings": "[source_recursive]", "body": "expr"}, "wanted": {"dictionary": "str", "candidates": "[candidate]"}, "checked": {"type": "stype", "body": "expr"}, "source_definition": {"body": "expr"}, "call_site": {"name": "str", "location": "span", "body": "expr"}, "shared_bind": {"pattern": "spattern", "action": "expr", "body": "expr", "binding": "expr", "failure": "expr"}})
TAGS["core"] = dict(_ATOMS, **{
    "var": {"name": "str"}, "constructor": {"name": "str"}, "lambda": {"name": "str", "body": "core"}, "application": {"function": "core", "argument": "core"}, "let": {"name": "str", "value": "core", "body": "core"}, "coerce": {"annotation": "annotation"}, "case": {"scrutinee": "core", "alternatives": "[core_alt]"}, "letrec": {"bindings": "[core_recursive]", "body": "core"}, "wanted": {"dictionary": "str", "candidates": "[candidate]"}, "checked": {"type": "stype", "expression": "expr"}})
TAGS["form"] = dict(_ATOMS, **{
    "var": {"name": "name", "edge": "?edge"}, "declared_var": {"name": "name", "type": "rtype", "edge": "edge"}, "lambda": {"name": "name", "domain": "nat", "body": "typed", "edge": "edge"}, "application": {"function": "typed", "argument": "typed", "function_edge": "edge", "argument_edge": "edge"}, "let": {"name": "name", "value": "typed", "body": "typed", "edge": "edge"}, "coerce": {"name": "name", "domain": "nat", "codomain": "nat"}, "primitive": {"id": "nat", "name": "str", "arguments": "[nat]"}, "constructor": {"name": "str", "arguments": "[nat]"}, "case": {"scrutinee": "typed", "edge": "edge", "alternatives": "[typed_alt]"}, "letrec": {"bindings": "[typed_recursive]", "body": "typed", "edge": "edge"}, "evidence": {"candidates": "[evidence_binding]"}, "checked": {"variables": "[typed_variable]", "body": "typed", "edge": "edge"}})
ENUMS = {"syntax": {"legacy-emlf-v1", "shared-haskell-v1", "metadata"}, "flag": {"flexible", "rigid"}, "evidence_role": {"given", "superclass", "instance"}, "namespace": {"terms", "types"}, "association": {"resolved_outer_declaration", "compiler_local_or_generated"}, "binding_kind": {"let", "letrec"}}


def validate_schema(value, category):
    pending = [(value, category, 0)]
    count = 0
    while pending:
        node, cat, depth = pending.pop()
        count += 1
        require(count <= MAX_SCHEMA_CELLS and depth <= MAX_DEPTH, "custody schema cell/depth budget exceeded")
        if cat.startswith("?"):
            if node is not None:
                pending.append((node, cat[1:], depth))
            continue
        if cat.startswith("["):
            require(type(node) is list, cat + ": array required")
            require(len(node) <= MAX_SCHEMA_CELLS - len(pending), "custody array budget exceeded")
            pending.extend((x, cat[1:-1], depth + 1) for x in node)
            continue
        if cat in ("str", "bool", "nat", "int"):
            if cat == "str":
                require(type(node) is str, "string required")
                try:
                    size = len(node.encode("utf-8"))
                except UnicodeEncodeError:
                    fail("invalid Unicode scalar text")
                require(size <= MAX_SOURCE_BYTES, "custody string budget exceeded")
            elif cat == "bool":
                require(type(node) is bool, "boolean required")
            else:
                require(type(node) is int and (0 if cat == "nat" else -(1 << 63)) <= node < 1 << 63, "signed integer/identity required")
            continue
        if cat in ENUMS:
            require(type(node) is str and node in ENUMS[cat], "unknown " + cat)
            continue
        if cat == "raw_term":
            validate_raw_term(node)
            continue
        if cat == "rtype":
            validate_raw_term({"tag": "lambda", "parameter": {"id": 0, "hint": "schema"},
                               "parameter_type": node, "body": {"tag": "int64", "value": 0}})
            continue
        if cat in TAGS:
            require(type(node) is dict and type(node.get("tag")) is str and node["tag"] in TAGS[cat], "unknown " + cat + " constructor")
            fields = TAGS[cat][node["tag"]]
            obj(node, {"tag", *fields}, cat)
            if node["tag"] == "primitive":
                require(type(node.get("id")) is int and PRIMITIVES.get(node["id"]) == node.get("name"), "forged primitive enum/name")
        else:
            require(cat in RECORDS, "internal unknown schema")
            fields = RECORDS[cat]
            obj(node, fields, cat)
        pending.extend((node[key], kind, depth + 1) for key, kind in fields.items())
    return count


def identity(source):
    return source["name"] if source["name"] is not None else "Main"


def entity_key(entity):
    role = entity["role"]
    payload = role.get("datatype", role.get("class", role.get("id", role.get("value"))))
    return entity["owner"], entity["spelling"], role["tag"], payload


def role_space(role):
    return "types" if role["tag"] in {"datatype", "class", "builtin_type", "managed_constraint"} else "terms"


def unique(values, label):
    require(len(set(values)) == len(values), label + ": duplicates")


def entity(owner, spelling, tag, **payload):
    role = {"tag": tag, **payload}
    return {"owner": owner, "spelling": spelling, "role": role, "namespace": role_space(role)}


def safe_path(path):
    if path.startswith("./"):
        path = path[2:]
    require(path.endswith(".emlf") and "\\" not in path and "\0" not in path and
            all(p not in ("", ".", "..") for p in path.split("/")), "unsafe captured guest path")
    return path

ROLE_ORDER = {x: i for i, x in enumerate(("value", "datatype", "class", "constructor", "method", "builtin_type", "primitive", "boolean", "managed_constraint"))}
PRIMITIVE_ARITIES = {0: 1, 1: 2, 13: 1, 54: 2, 55: 1, 63: 1, 66: 2, 67: 3, 68: 1, 69: 2, 70: 2, 71: 2, 72: 2, 85: 2, 86: 1, 87: 2, 88: 1, 100: 1, 101: 1, 106: 1}
BUILTIN_TYPES = ("Char", "IOError", "AsyncScope", "Completion", "AsyncSubscription", "ST", "STArray", "Int", "Integer", "Double", "Bool", "String", "IO", "IntArray", "DoubleArray", "ByteArray", "IntTable")


def sort_entity(e):
    owner, spelling, tag, payload = entity_key(e)
    return owner, spelling, ROLE_ORDER[tag], "" if payload is None else payload


def expected_entities(modules):
    result = {}

    def add(e):
        result[entity_key(e)] = e

    for code, name in PRIMITIVES.items():
        add(entity("Prelude", name, "primitive", id=code, name=name))
    for name in BUILTIN_TYPES:
        add(entity("Prelude", name, "builtin_type"))
    for value in (False, True):
        add(entity("Prelude", str(value), "boolean", value=value))
    for m in modules:
        s, owner = m["source"], identity(m["source"])
        if owner == "MLF.Primitive":
            add(entity(owner, "HasCallStack", "managed_constraint"))
            add(entity(owner, "CallStack", "builtin_type"))
            add(entity(owner, "callStack", "value"))
        own_keys = []
        for value in s["values"]:
            e = entity(owner, value["name"], "value")
            own_keys.append((e["namespace"], e["spelling"]))
            add(e)
        for d in s["declarations"]:
            e = entity(owner, d["name"], "datatype")
            own_keys.append((e["namespace"], e["spelling"]))
            add(e)
            for c in d["constructors"]:
                e = entity(owner, c["name"], "constructor", datatype=d["name"])
                own_keys.append((e["namespace"], e["spelling"]))
                add(e)
        for c in s["classes"]:
            e = entity(owner, c["name"], "class")
            own_keys.append((e["namespace"], e["spelling"]))
            add(e)
            for method in c["methods"]:
                e = entity(owner, method["name"], "method", **{"class": c["name"]})
                own_keys.append((e["namespace"], e["spelling"]))
                add(e)
        unique(own_keys, "source declaration namespace")
    return result


def _source_pattern_names(pattern):
    result, pending, count = [], [pattern], 0
    while pending:
        p = pending.pop()
        count += 1
        require(count <= MAX_NODES, "source pattern name budget exceeded")
        tag = p["tag"]
        if tag == "constructor":
            result.extend(x for x in p["fields"] if x is not None)
        elif tag == "default":
            if p["binder"] is not None:
                result.append(p["binder"])
        elif tag == "nested":
            pending.extend(p["fields"])
        elif tag == "annotated":
            result.append(p["name"])
        elif tag in {"as", "lazy"}:
            if tag == "as":
                result.append(p["name"])
            pending.append(p["pattern"])
    return result


def _compare_renamed(original, renamed, scope, allocations, *, initial_names=None):
    """Compare recorded ASTs, allowing only witnessed identifier substitutions.

    This checks correspondence, not export selection or name lookup correctness.
    Nontrivial surface rewrites not represented by this grammar fail closed.
    """
    allowed = {("terms", name): set(values) for name, values in (initial_names or {}).items()}
    for row in scope:
        if len(row["entities"]) == 1:
            e = row["entities"][0]
            allocation = allocations[entity_key(e)]
            allowed.setdefault((row["namespace"], row["spelling"]), set()).add(allocation["allocated"])
    pending = [(original, renamed, None, frozenset(), False)]
    seen = 0
    while pending:
        a, b, field, bound, type_context = pending.pop()
        seen += 1
        require(seen <= MAX_NODES, "rename correspondence budget exceeded")
        if type(a) is dict and type(b) is dict:
            at, bt = a.get("tag"), b.get("tag")
            if at == "primitive":
                # An already explicit primitive carries authenticated enum
                # metadata, not a source identifier awaiting namespace lookup.
                # Both schemas are validated above; preserve the ENTIRE node.
                equal(a, b, "explicit primitive identity changed during renaming")
                continue
            if at == "var" and bt == "primitive":
                require(a["name"] not in bound, "lexical source variable changed to primitive")
                candidates = [e for r in scope if r["namespace"] == "terms" and r["spelling"] == a["name"] for e in r["entities"]]
                require(len(candidates) == 1 and candidates[0]["role"] == b, "renamed primitive lacks exact recorded scope entity")
                continue
            if at in {"constructor", "nested"} and bt == "bool":
                candidates = [e for r in scope if r["namespace"] == "terms" and r["spelling"] == a["name"] for e in r["entities"]]
                require(len(candidates) == 1 and candidates[0]["role"] == {"tag": "boolean", "value": b["value"]} and not a.get("fields", []), "renamed Boolean lacks exact recorded entity")
                continue
            require(set(a) == set(b), "renamed AST constructor/keys differ")
            # Local lexical spellings, literal text and provenance are invariant.
            for key in a:
                name_field = key in {"name", "class", "constructor", "equality", "conversion"}
                if name_field and type(a[key]) is str and type(b[key]) is str:
                    x, y = a[key], b[key]
                    lexical = key == "name" and (at in {"lambda", "let", "forall", "parameter", "annotated", "as", "quantified"} or (at == "var" and (x in bound or type_context)) or set(a) == {"name", "kind"} or set(a) == {"name", "mode", "value"})
                    if at == "call_site" and key == "name":
                        # SCallSite display metadata stays unchanged while its
                        # expression body is independently resolved below.
                        require(x == y, "call-site display metadata changed")
                    elif lexical:
                        require(x == y, "renamed lexical binder changed")
                    else:
                        special = [r["allocated"] for r in allocations.values() if r["entity"]["owner"] == "MLF.Primitive" and r["entity"]["role"]["tag"] == "method" and x == "$MLF.Primitive." + r["entity"]["spelling"]]
                        namespace = "types" if (type_context or at == "applied" or key == "class" or (key == "name" and "supers" in a and "parameters" in a)) else "terms"
                        witnessed = allowed.get((namespace, x), set())
                        if at == "var" and not type_context:
                            candidates = [e for row in scope if row["namespace"] == "terms" and row["spelling"] == x for e in row["entities"]]
                            if x == "$MLF.Stack.callStack":
                                require(y == x, "intrinsic stack reference changed")
                            elif special:
                                require(len(special) == 1 and y == special[0], "intrinsic method allocation differs")
                            else:
                                require(len(candidates) == 1 and candidates[0]["role"]["tag"] in {"value", "method"}, "renamed variable lacks exact singleton value/method entity")
                                expected = allocations[entity_key(candidates[0])]["allocated"]
                                if candidates[0]["owner"] == "MLF.Primitive" and candidates[0]["spelling"] == "callStack":
                                    expected = "$MLF.Stack.callStack"
                                require(y == expected, "known global variable did not use actual allocation")
                        elif witnessed:
                            require(y in witnessed, "renamed identifier lacks witnessed namespace allocation")
                        else:
                            require(x == y or (namespace == "terms" and y in special), "renamed identifier lacks witnessed namespace allocation")
                else:
                    child_bound = bound
                    if key == "body" and at in {"lambda", "let", "forall"}:
                        child_bound = bound | {a["name"]}
                    if at == "letrec" and key in {"bindings", "body"}:
                        child_bound = bound | {x["name"] for x in a["bindings"]}
                    if key == "body" and "pattern" in a:
                        child_bound = bound | set(_source_pattern_names(a["pattern"]))
                    child_type = type_context or key in {"type", "annotation", "parameters", "supers", "head", "context"}
                    pending.append((a[key], b[key], key, child_bound, child_type))
        elif type(a) is list and type(b) is list:
            require(len(a) == len(b), "renamed AST list omitted/reordered members")
            pending.extend((a[i], b[i], field, bound, type_context) for i in range(len(a)))
        else:
            equal(a, b, "renamed non-identifier AST")


def _source_used(modules):
    used, pending = set(), []
    for module in modules:
        source = module["source"]
        for d in source["declarations"]:
            used.add(d["name"])
            used.update(c["name"] for c in d["constructors"])
        for c in source["classes"]:
            used.add(c["name"])
            used.update(m["name"] for m in c["methods"])
        for value in source["values"]:
            used.add(value["name"])
            pending.append(value["body"])
        for instance in source["instances"]:
            for method in instance["methods"]:
                used.add(method["name"])
                pending.append(method["body"])
        if source["body"] is not None:
            pending.append(source["body"])
    count = 0
    while pending:
        e = pending.pop()
        count += 1
        require(count <= MAX_NODES, "source used-name budget exceeded")
        tag = e["tag"]
        if tag in {"var", "constructor", "lambda", "let"}:
            used.add(e["name"])
        if tag in {"lambda", "checked", "source_definition", "call_site"}:
            pending.append(e["body"])
        elif tag in {"annotation", "signature"}:
            pending.append(e["value"])
        elif tag == "application":
            pending.extend([e["function"], e["argument"]])
        elif tag == "let":
            pending.extend([e["value"], e["body"]])
        elif tag == "letrec":
            used.update(x["name"] for x in e["bindings"])
            pending.extend([x["value"] for x in e["bindings"]] + [e["body"]])
        elif tag == "case":
            pending.append(e["scrutinee"])
            for branch in e["alternatives"]:
                used.update(_source_pattern_names(branch["pattern"]))
                pending.append(branch["body"])
        elif tag == "equations":
            for row in e["rows"]:
                for pattern in row["patterns"]:
                    used.update(_source_pattern_names(pattern))
                pending.append(row["body"])
        elif tag == "wanted":
            used.add(e["dictionary"])
            used.update(x["name"] for x in e["candidates"])
        elif tag == "shared_bind":
            used.update(_source_pattern_names(e["pattern"]))
            pending.extend(e[k] for k in ("action", "body", "binding", "failure"))
        elif tag == "do":
            pending.append(e["body"])
            for statement in e["statements"]:
                st = statement["tag"]
                if st == "bind":
                    used.update(_source_pattern_names(statement["pattern"]))
                elif st == "let":
                    used.add(statement["name"])
                if st == "letrec":
                    used.update(x["name"] for x in statement["bindings"])
                    pending.extend(x["value"] for x in statement["bindings"])
                else:
                    pending.append(statement["value"])
    return used


def _validate_load_order(loaded):
    sources = {identity(x["source"]): x["source"] for x in loaded}
    seen, order, pending = set(), [], [(False, "Main")]
    while pending:
        leaving, name = pending.pop()
        if leaving:
            order.append(name)
        elif name not in seen and name not in BUILTINS:
            require(name in sources, "import edge points to absent guest")
            seen.add(name)
            source = sources[name]
            if name != "Main":
                require(source["name"] == name and source["body"] is None, "imported module header/body mismatch")
            pending.append((True, name))
            pending.extend((False, x["module"]) for x in reversed(source["imports"]))
    require(order == [identity(x["source"]) for x in loaded], "loaded DFS closure order/omission differs")


def _validate_resolution(custody):
    loaded, resolution = custody["loaded"], custody["resolution"]
    require(1 <= len(loaded) <= 33, "loaded closure module count outside budget")
    require(loaded[-1]["is_root"] and sum(x["is_root"] for x in loaded) == 1, "loaded order/root marker invalid")
    total, paths, sources = 0, [], []
    for row in loaded:
        s = row["source"]
        require(s["syntax"] == "legacy-emlf-v1", "guest source syntax not admitted")
        require(identity(s) not in BUILTINS, "guest cannot impersonate compiler module")
        require(row["is_root"] == (s["path"] == "<stdin>"), "root path/marker disagreement")
        if row["is_root"]:
            require(s["name"] is None and bool(s["imports"]), "root must be headerless with actual imports")
            path = "<stdin>"
        else:
            require(s["name"] is not None, "imported source must be named")
            path = safe_path(s["path"])
        paths.append(path)
        size = len(row["text"].encode("utf-8"))
        require(size <= 1024 * 1024, "loaded text exceeds file budget")
        total += size
        sources.append({"path": s["path"], "text": row["text"], "is_root": row["is_root"], "module_identity": identity(s), "syntax": s["syntax"]})
    require(total <= MAX_SOURCE_BYTES, "loaded source byte budget exceeded")
    unique(paths, "loaded logical paths")
    unique([identity(r["source"]) for r in loaded], "loaded module identities")
    _validate_load_order(loaded)
    modules = resolution["modules"]
    require(len(modules) == len(loaded) + 2, "resolution must contain both injected modules and every loaded source")
    require([identity(m["source"]) for m in modules[:2]] == ["Prelude", "MLF.Primitive"], "compiler injection order/identity differs")
    for i, m in enumerate(modules):
        own = identity(m["source"])
        require(m["compiler_owned"] == (own in BUILTINS), "compiler-owned classification forged")
        if i < 2:
            require(m["source"]["path"] == "<" + own + ">" and m["source"]["syntax"] == "legacy-emlf-v1", "compiler source identity/path differs")
        else:
            equal(m["source"], loaded[i - 2]["source"], "same-read loaded/resolved source")
    prelude = {"path": "<Prelude>", "name": "Prelude", "exports": [{"tag": "module", "name": "MLF.Primitive"}], "imports": [{"module": "MLF.Primitive", "qualified": False, "alias": None, "selection": {"tag": "everything"}}], "declarations": [], "classes": [], "instances": [], "values": [], "body": None, "syntax": "legacy-emlf-v1"}
    equal(modules[0]["source"], prelude, "compiler Prelude source")
    expected = expected_entities(modules)
    entries = resolution["entities"]
    require(len(entries) == len(expected), "resolver entity inventory count differs")
    unique([entity_key(r["entity"]) for r in entries], "resolver entities")
    unique([r["allocated"] for r in entries], "allocated names")
    require([sort_entity(r["entity"]) for r in entries] == sorted(sort_entity(e) for e in expected.values()), "resolver entity order/inventory differs")
    allocations = {}
    next_index = 0
    used_names = _source_used(modules)
    for row in entries:
        e, name = row["entity"], row["allocated"]
        equal(e, expected[entity_key(e)], "resolver entity role/namespace")
        role, owner, spelling = e["role"]["tag"], e["owner"], e["spelling"]
        special = {("HasCallStack", "managed_constraint"): "MLFHasCallStack", ("CallStack", "builtin_type"): "MLFCallStack", ("callStack", "value"): "mlfCallStack"}
        if owner == "MLF.Primitive" and (spelling, role) in special:
            require(name == special[spelling, role], "intrinsic allocation differs")
        elif role == "builtin_type":
            require(name == spelling, "builtin type allocation differs")
        else:
            prefix = "ModuleEntity" if e["namespace"] == "types" or role == "constructor" else "moduleEntity"
            suffix = name[len(prefix):]
            require(name.startswith(prefix) and len(suffix) <= 20 and suffix.isascii() and suffix.isdigit() and suffix == str(int(suffix)), "allocated name encoding differs")
            while prefix + str(next_index) in used_names:
                next_index += 1
                require(next_index <= MAX_NODES, "allocation skip budget exceeded")
            require(name == prefix + str(next_index), "allocated fresh index/skip sequence differs")
            next_index += 1
        allocations[entity_key(e)] = row
    display = [{"allocated": r["allocated"], "display": r["entity"]["spelling"] if r["entity"]["owner"] == "Prelude" else r["entity"]["owner"] + "." + r["entity"]["spelling"]} for r in entries]
    display.sort(key=lambda x: x["allocated"])
    equal(resolution["display_names"], display, "resolver display names")
    owners = [identity(m["source"]) for m in modules]
    graph = {identity(m["source"]): {x["module"] for x in m["source"]["imports"]} | (set() if m["compiler_owned"] else {"MLF.Primitive"}) for m in modules}
    require(all(deps <= set(owners) for deps in graph.values()), "dependency edge names unloaded module")
    reaches = {}
    for owner in owners:
        seen, pending = set(), [owner]
        while pending:
            current = pending.pop()
            if current not in seen:
                seen.add(current)
                pending.extend(graph[current] - seen)
        reaches[owner] = seen
    equal(resolution["reach"], [{"owner": o, "modules": sorted(reaches[o])} for o in sorted(owners)], "module dependency reach")
    outer = {}
    instances = []
    declaration_inventory = []
    for m in modules:
        s, renamed, scope = m["source"], m["renamed"], m["scope"]
        owner = identity(s)
        keys = [(0 if r["namespace"] == "terms" else 1, r["spelling"]) for r in scope]
        require(keys == sorted(set(keys)), "scope key order/duplicates")
        for row in scope:
            es = row["entities"]
            require(bool(es) and [sort_entity(e) for e in es] == sorted(set(sort_entity(e) for e in es)), "scope entity order/duplicates")
            for e in es:
                require(entity_key(e) in allocations, "scope has unallocated entity")
                equal(e, allocations[entity_key(e)]["entity"], "scope entity metadata")
                require(e["namespace"] == row["namespace"], "scope namespace mismatch")
                require(e["owner"] in reaches[owner] or e["owner"] == "Prelude", "scope owner is not reachable")
        if not m["compiler_owned"]:
            by_key = {(row["namespace"], row["spelling"]): row["entities"] for row in scope}
            for e in expected.values():
                if e["owner"] == owner:
                    equal(by_key.get((e["namespace"], e["spelling"])), [e], "own declaration unqualified scope")
                    equal(by_key.get((e["namespace"], owner + "." + e["spelling"])), [e], "own declaration qualified scope")
        for category in ("declarations", "classes", "values"):
            require(len(s[category]) == len(renamed[category]), "renamed declaration/value count differs")
        own_names = {}
        for value in s["values"]:
            allocation = allocations[entity_key(entity(owner, value["name"], "value"))]
            own_names.setdefault(value["name"], set()).add(allocation["allocated"])
        for i, value in enumerate(s["values"]):
            renamed_value = renamed["values"][i]
            allocation = allocations[entity_key(entity(owner, value["name"], "value"))]
            require(renamed_value["name"] == allocation["allocated"], "renamed value owner/order mismatch")
            require(renamed_value["name"] not in outer, "duplicate renamed outer value")
            outer[renamed_value["name"]] = allocation
            _compare_renamed(value, renamed_value, scope, allocations, initial_names=own_names)
        for i, declaration in enumerate(s["declarations"]):
            d = renamed["declarations"][i]
            require(d["tag"] == "data_kind", "renamed datatype must preserve explicit kinds")
            expected_name = allocations[entity_key(entity(owner, declaration["name"], "datatype"))]["allocated"]
            require(d["name"] == expected_name, "renamed datatype owner/order differs")
            params = declaration["parameters"] if declaration["tag"] == "data_kind" else [{"name": x, "kind": {"tag": "star"}} for x in declaration["parameters"]]
            equal(params, d["parameters"], "datatype parameters/kinds")
            require(len(declaration["constructors"]) == len(d["constructors"]), "renamed constructors omitted")
            for j, c in enumerate(declaration["constructors"]):
                rc = d["constructors"][j]
                require(rc["name"] == allocations[entity_key(entity(owner, c["name"], "constructor", datatype=declaration["name"]))]["allocated"], "renamed constructor owner/order differs")
                _compare_renamed(c["fields"], rc["fields"], scope, allocations)
            declaration_inventory.append(d)
        for i, klass in enumerate(s["classes"]):
            renamed_class = renamed["classes"][i]
            require(renamed_class["name"] == allocations[entity_key(entity(owner, klass["name"], "class"))]["allocated"], "renamed class owner/order differs")
            require(len(klass["methods"]) == len(renamed_class["methods"]), "renamed methods omitted")
            for j, method in enumerate(klass["methods"]):
                require(renamed_class["methods"][j]["name"] == allocations[entity_key(entity(owner, method["name"], "method", **{"class": klass["name"]}))]["allocated"], "renamed method owner differs")
            _compare_renamed(klass, renamed_class, scope, allocations)
        # Standard default methods may be inserted into instances by the genuine
        # resolver. Their full ASTs are schema checked and preserved below; that
        # transformation remains a pinned compiler obligation, not a Python guess.
        require(len(s["instances"]) == len(renamed["instances"]), "renamed instance count differs")
        _compare_renamed(s["body"], renamed["body"], scope, allocations)
        instances.extend({"owner": owner, "instance": x} for x in renamed["instances"])
    equal(resolution["instances"], instances, "complete ordered owned instances")
    candidate = {o: [i for i, x in enumerate(instances) if x["owner"] in reaches[o]] for o in owners}
    value_scopes = sorted(({"name": v["name"], "scope": candidate[identity(m["source"])]} for m in modules for v in m["renamed"]["values"]), key=lambda x: x["name"])
    equal(resolution["value_scopes"], value_scopes, "value instance visibility scopes")
    equal(resolution["instance_scopes"], [candidate[x["owner"]] for x in instances], "instance visibility scopes")
    return sources, outer, declaration_inventory


def _bounded_json(value):
    active, pending = set(), [(False, value, 0)]
    cells = text_bytes = 0
    while pending:
        leave, node, depth = pending.pop()
        if leave:
            active.remove(id(node))
            continue
        cells += 1
        require(cells <= MAX_SCHEMA_CELLS and depth <= MAX_DEPTH, "custody JSON budget exceeded")
        if type(node) in (dict, list):
            require(id(node) not in active, "cyclic custody JSON")
            active.add(id(node))
            pending.append((True, node, depth))
            if type(node) is dict:
                require(all(type(k) is str for k in node), "non-string JSON key")
                children = list(node.keys()) + list(node.values())
            else:
                children = node
            require(len(children) <= MAX_SCHEMA_CELLS - len(pending), "custody JSON work budget exceeded")
            pending.extend((False, x, depth + 1) for x in children)
        elif type(node) is str:
            try:
                text_bytes += len(node.encode("utf-8"))
            except UnicodeEncodeError:
                fail("invalid Unicode scalar text")
            require(text_bytes <= 32 * 1024 * 1024, "custody JSON byte budget exceeded")
        else:
            require(type(node) in (int, bool, type(None)), "non-JSON custody scalar")


def _expr_children(expr):
    tag = expr["tag"]
    if tag in {"lambda", "checked"}:
        return [expr["body"]]
    if tag in {"annotation", "signature"}:
        return [expr["value"]]
    if tag == "application":
        return [expr["function"], expr["argument"]]
    if tag == "let":
        return [expr["value"], expr["body"]]
    if tag == "letrec":
        return [x["value"] for x in expr["bindings"]] + [expr["body"]]
    if tag == "case":
        return [expr["scrutinee"]] + [x["body"] for x in expr["alternatives"]]
    if tag in {"do", "equations", "source_definition", "call_site", "shared_bind"}:
        fail("surface lowering outside independently replayed custody subset: " + tag)
    return []


def _recursive_core(mode, source, desugared):
    if mode["tag"] == "check" and not mode["annotation"]["existentials"]:
        ty = mode["annotation"]["type"]
        if source["tag"] == "checked" and exact_equal(source["type"], ty):
            return desugared
        return {"tag": "checked", "type": ty, "expression": source}
    return desugared


def _desugar(expression):
    """Replay only the finite recorded SourceExpr -> Core shape equations.

    No parser, inference or general surface-pattern lowering is implemented.
    Unknown surface transformations reject rather than inventing a skeleton.
    """
    pending, result, count = [(False, expression)], {}, 0
    while pending:
        done, e = pending.pop()
        if not done:
            count += 1
            require(count <= MAX_NODES, "source desugar budget exceeded")
            pending.append((True, e))
            pending.extend((False, x) for x in reversed(_expr_children(e)))
            continue
        tag = e["tag"]
        get = lambda x: result[id(x)]
        if tag in {"var", "constructor", "int64", "double", "bool", "string", "primitive", "wanted"}:
            out = e
        elif tag == "lambda":
            body = get(e["body"])
            if e["annotation"] is not None:
                body = {"tag": "let", "name": e["name"], "value": {"tag": "application", "function": {"tag": "coerce", "annotation": e["annotation"]}, "argument": {"tag": "var", "name": e["name"]}}, "body": body}
            out = {"tag": "lambda", "name": e["name"], "body": body}
        elif tag == "application":
            out = {"tag": tag, "function": get(e["function"]), "argument": get(e["argument"])}
        elif tag == "let":
            out = {"tag": tag, "name": e["name"], "value": get(e["value"]), "body": get(e["body"])}
        elif tag in {"annotation", "signature"}:
            if tag == "signature" and not e["annotation"]["existentials"]:
                out = _recursive_core({"tag": "check", "annotation": e["annotation"]}, e["value"], get(e["value"]))
            else:
                out = {"tag": "application", "function": {"tag": "coerce", "annotation": e["annotation"]}, "argument": get(e["value"])}
        elif tag == "case":
            require(all(x["pattern"]["tag"] in {"constructor", "default"} for x in e["alternatives"]), "non-flat lowered pattern outside custody replay")
            out = {"tag": tag, "scrutinee": get(e["scrutinee"]), "alternatives": [{"pattern": x["pattern"], "body": get(x["body"])} for x in e["alternatives"]]}
        elif tag == "letrec":
            out = {"tag": tag, "bindings": [{"name": x["name"], "mode": x["mode"], "value": _recursive_core(x["mode"], x["value"], get(x["value"]))} for x in e["bindings"]], "body": get(e["body"])}
        elif tag == "checked":
            out = {"tag": tag, "type": e["type"], "expression": e["body"]}
        else:
            fail("unsupported source/Core correspondence")
        result[id(e)] = out
    return result[id(expression)]


def _directed(expected, expression):
    # Constraint.directed follows only lambda/let continuations.
    spine, ty, e = [], expected, expression
    while True:
        require(len(spine) <= MAX_DEPTH, "directed source depth exceeded")
        if e["tag"] == "lambda" and ty["tag"] == "arrow":
            spine.append((e, e["annotation"] if e["annotation"] is not None else {"existentials": [], "type": ty["from"]}))
            ty, e = ty["to"], e["body"]
        elif e["tag"] == "let":
            spine.append((e, None))
            e = e["body"]
        else:
            break
    out = e
    for e, annotation in reversed(spine):
        out = {**e, "body": out}
        if e["tag"] == "lambda":
            out["annotation"] = annotation
    return out


def _fresh_hint(source, name):
    # The original compiler uses its own Unicode tables. ASCII is the finite
    # replay domain here; no host Unicode-version equivalence is assumed.
    require(source.isascii(), "non-ASCII source binding hint outside custody replay")
    plain = bool(source) and source[0].isalpha() and all(c.isalnum() or c in "_'" for c in source[1:])
    expected = source if plain else "mlfInternal" + "".join("_" + str(ord(c)) for c in source)
    require(name["hint"] == expected, "source/Typed fresh-name hint mismatch")


def _pair_pattern(source, actual, env):
    if source["tag"] == "constructor" and actual["tag"] == "constructor":
        require(source["name"] == actual["constructor"], "source/Typed constructor pattern mismatch")
        sources, actuals = source["fields"], actual["fields"]
    elif source["tag"] == "default" and actual["tag"] == "default":
        sources, actuals = [source["binder"]], [actual["binder"]]
    else:
        fail("source/Typed pattern constructor mismatch")
    require(len(sources) == len(actuals), "source/Typed pattern field count mismatch")
    names = [x for x in sources if x is not None]
    unique(names, "source pattern binders")
    scope = dict(env)
    for i, source in enumerate(sources):
        actual = actuals[i]
        require((source is None) == (actual is None), "source/Typed pattern wildcard mismatch")
        if source is not None:
            _fresh_hint(source, actual)
            scope[source] = actual
    return scope


def _pair_core(core, typed, outer_allocations, declarations):
    rows, pending, count = [], [(core, typed, {}, True, [])], 0
    constructors = {}
    # Builtin declaration constructors from the original DataEnv. User generated
    # nominal constructors are inventoried by their complete declarations below.
    builtin_constructor_arity = {"MLFLegacyUnit": 0, "MLFStackFrame": 0, "MLFStackEvidence": 0, "()": 0, "[]": 1, ":": 1, **{"(" + "," * (n - 1) + ")": n for n in range(2, 65)}}
    for d in declarations:
        for c in d["constructors"]:
            require(c["name"] not in constructors, "duplicate constructor identity")
            constructors[c["name"]] = len(d["parameters"])
    constructors = {**builtin_constructor_arity, **constructors}
    generations, evidence_generations = set(), set()
    while pending:
        s, t, env, outer, path = pending.pop()
        count += 1
        require(count <= MAX_NODES and len(path) <= MAX_DEPTH, "Core/Typed association budget exceeded")
        generation, a = t["generation"], t["form"]
        require(generation not in generations, "duplicate Typed generation")
        generations.add(generation)
        st, at = s["tag"], a["tag"]

        def lookup(source, actual):
            require(source in env, "source variable has no lexical binding")
            equal(env[source], actual, "lexical source/Typed identity")

        def binding(source, name):
            _fresh_hint(source, name)
            allocation = outer_allocations.get(source) if outer else None
            return {"name": name, "source_internal_name": source, "association": "resolved_outer_declaration" if allocation is not None else "compiler_local_or_generated", "resolver_allocation": allocation}

        if st == "var" and at in {"var", "declared_var"}:
            lookup(s["name"], a["name"])
        elif st == "var" and at == "primitive":
            require(s["name"] not in env, "lexical variable replaced by primitive")
            names = {name: code for code, name in PRIMITIVES.items()}
            names.update({"return": 0, "pure": 0, "bind": 1})
            require(names.get(s["name"]) == a["id"] and len(a["arguments"]) == PRIMITIVE_ARITIES.get(a["id"], 0), "source primitive resolution/arity differs")
        elif st == "lambda" and at == "lambda":
            _fresh_hint(s["name"], a["name"])
            scope = {**env, s["name"]: a["name"]}
            pending.append((s["body"], a["body"], scope, False, path + ["body"]))
        elif st == "application" and at == "application":
            pending.extend([(s["argument"], a["argument"], env, False, path + ["argument"]), (s["function"], a["function"], env, False, path + ["function"])])
        elif st == "let" and at == "let":
            rows.append({"path": path, "generation": generation, "kind": "let", "bindings": [binding(s["name"], a["name"])]})
            scope = {**env, s["name"]: a["name"]}
            pending.extend([(s["body"], a["body"], scope, outer, path + ["body"]), (s["value"], a["value"], env, False, path + ["value"])])
        elif st == "letrec" and at == "letrec":
            ss, aa = s["bindings"], a["bindings"]
            require(len(ss) == len(aa) and bool(ss), "recursive source/Typed group count differs")
            unique([b["name"] for b in ss], "source recursive group")
            bs, scope = [], dict(env)
            for i, b in enumerate(ss):
                actual = aa[i]
                mode = b["mode"]
                require((mode["tag"] == "infer" and actual["closure"] is not None) or
                        (mode["tag"] == "check" and not mode["annotation"]["existentials"] and actual["closure"] is None), "recursive source/Typed inference mode mismatch")
                bs.append(binding(b["name"], actual["name"]))
                scope[b["name"]] = actual["name"]
                if actual["closure"] is not None:
                    keys = [x["key"] for x in actual["closure"]["copies"]]
                    require(keys == sorted(set(keys)), "recursive closure map order/duplicates")
            rows.append({"path": path, "generation": generation, "kind": "letrec", "bindings": bs})
            pending.append((s["body"], a["body"], scope, outer, path + ["body"]))
            for i in reversed(range(len(ss))):
                pending.append((ss[i]["value"], aa[i]["value"], scope, False, path + ["bindings", str(i), "value"]))
        elif st == "coerce" and at == "coerce":
            _fresh_hint("coerce", a["name"])
        elif st in {"int64", "double", "bool", "string"} and st == at:
            equal(s, a, "source/Typed literal")
        elif st == "primitive" and at == "primitive":
            require(s["id"] == a["id"] and s["name"] == a["name"] and len(a["arguments"]) == PRIMITIVE_ARITIES.get(a["id"], 0), "source/Typed primitive identity/arity mismatch")
        elif st == "constructor" and at == "constructor":
            require(s["name"] == a["name"] and s["name"] in constructors and len(a["arguments"]) == constructors[s["name"]], "source/Typed constructor identity/arity mismatch")
        elif st == "case" and at == "case":
            ss, aa = s["alternatives"], a["alternatives"]
            require(len(ss) == len(aa), "case source/Typed branch count mismatch")
            for i in reversed(range(len(ss))):
                scope = _pair_pattern(ss[i]["pattern"], aa[i]["pattern"], env)
                pending.append((ss[i]["body"], aa[i]["body"], scope, False, path + ["alternatives", str(i), "body"]))
            pending.append((s["scrutinee"], a["scrutinee"], env, False, path + ["scrutinee"]))
        elif st == "wanted" and at == "evidence":
            ss, aa = s["candidates"], a["candidates"]
            require(len(ss) == len(aa), "source/Typed evidence candidate count mismatch")
            for i, candidate in enumerate(ss):
                require(candidate["role"] == aa[i]["role"], "dictionary evidence role mismatch")
                lookup(candidate["name"], aa[i]["name"])
            evidence_generations.add(generation)
        elif st == "checked" and at == "checked":
            expected, kinds = s["type"], []
            while expected["tag"] == "forall" and expected["flag"] == "flexible" and expected["bound"]["tag"] in {"bottom", "bottom_kind"}:
                kinds.append({"tag": "star"} if expected["bound"]["tag"] == "bottom" else expected["bound"]["kind"])
                expected = expected["body"]
            equal(kinds, [v["kind"] for v in a["variables"]], "checked scoped variable kinds")
            unique([v["id"] for v in a["variables"]], "checked type variables")
            expression = {"tag": "annotation", "value": _directed(expected, s["expression"]), "annotation": {"existentials": [], "type": expected}}
            expanded = _desugar(expression)
            pending.append((expanded, a["body"], env, False, path))
        else:
            fail("source Core/actual Typed constructor mismatch: " + st + "/" + at)
    return rows, evidence_generations


def _typed_children(t):
    a = t["form"]
    tag = a["tag"]
    if tag in {"lambda", "checked"}:
        return [a["body"]]
    if tag == "application":
        return [a["function"], a["argument"]]
    if tag == "let":
        return [a["value"], a["body"]]
    if tag == "letrec":
        return [b["value"] for b in a["bindings"]] + [a["body"]]
    if tag == "case":
        return [a["scrutinee"]] + [b["body"] for b in a["alternatives"]]
    return []


def _erase_typed(skeleton, evidence):
    pending, values, count = [(False, skeleton)], {}, 0
    while pending:
        done, t = pending.pop()
        if not done:
            count += 1
            require(count <= MAX_NODES, "Typed erasure budget exceeded")
            pending.append((True, t))
            pending.extend((False, child) for child in reversed(_typed_children(t)))
            continue
        a = t["form"]
        tag = a["tag"]
        get = lambda x: values[id(x)]
        if tag in {"var", "declared_var"}:
            out = {"tag": "var", "name": a["name"]}
        elif tag == "lambda":
            out = {"tag": tag, "parameter": a["name"], "body": get(a["body"])}
        elif tag == "coerce":
            out = {"tag": "lambda", "parameter": a["name"], "body": {"tag": "var", "name": a["name"]}}
        elif tag == "application":
            out = {"tag": tag, "function": get(a["function"]), "argument": get(a["argument"])}
        elif tag == "let":
            out = {"tag": tag, "name": a["name"], "value": get(a["value"]), "body": get(a["body"])}
        elif tag == "letrec":
            out = {"tag": tag, "bindings": [{"name": x["name"], "value": get(x["value"])} for x in a["bindings"]], "body": get(a["body"])}
        elif tag in {"int64", "double", "bool", "string"}:
            out = a
        elif tag in {"primitive", "constructor"}:
            out = {k: v for k, v in a.items() if k != "arguments"}
        elif tag == "case":
            out = {"tag": tag, "scrutinee": get(a["scrutinee"]), "alternatives": [{"pattern": b["pattern"], "body": get(b["body"])} for b in a["alternatives"]]}
        elif tag == "evidence":
            require(t["generation"] in evidence, "unresolved typed evidence hole")
            out = erase_total(evidence[t["generation"]])
        elif tag == "checked":
            out = get(a["body"])
        else:
            fail("unknown Typed erasure form")
        values[id(t)] = out
    return values[id(skeleton)]


def _erased_rows(root):
    rows, pending, count = [], [(root, [])], 0
    while pending:
        e, path = pending.pop()
        count += 1
        require(count <= MAX_NODES, "erased binding graph budget exceeded")
        tag = e["tag"]
        if tag == "let":
            rows.append({"path": path, "kind": tag, "names": [e["name"]]})
            pending.extend([(e["body"], path + ["body"]), (e["value"], path + ["value"])])
        elif tag == "letrec":
            rows.append({"path": path, "kind": tag, "names": [b["name"] for b in e["bindings"]]})
            pending.append((e["body"], path + ["body"]))
            pending.extend((e["bindings"][i]["value"], path + ["bindings", str(i), "value"]) for i in reversed(range(len(e["bindings"]))))
        elif tag == "lambda":
            pending.append((e["body"], path + ["body"]))
        elif tag == "application":
            pending.extend([(e["argument"], path + ["argument"]), (e["function"], path + ["function"])])
        elif tag == "case":
            pending.extend((e["alternatives"][i]["body"], path + ["alternatives", str(i), "body"]) for i in reversed(range(len(e["alternatives"]))))
            pending.append((e["scrutinee"], path + ["scrutinee"]))
    return rows


def validate_custody(module_custody, original_object):
    """Return serializable replay facts, or raise CustodyError/ProjectionError.

    Acceptance here is one obligation, NOT authorization to run a candidate.
    The caller must authenticate pinned producer bytes and all returned loaded
    path/text rows against its same-read, live-rechecked immutable snapshot.
    """
    _bounded_json(module_custody)
    obj(original_object, ORIGINAL_KEYS, "original")
    for guard in ("ordinary_whole_check_passed", "root_type_alpha_equal", "source_erasure_equal"):
        require(original_object[guard] is True, "original ordinary-check guard is not True: " + guard)
    validate_schema(module_custody, "custody")
    require(module_custody["policy"] == "legacy-single-root/1" and module_custody["root_file"] == "<stdin>" and module_custody["prelude"] == "NoImplicitPrelude", "unknown source custody policy")
    equal(module_custody["include_paths"], [], "include path admission")
    equal(module_custody["search_paths"], ["."], "source search path admission")
    validate_raw_term(original_object["annotated"], require_closed=True)
    validate_raw_term(original_object["erased"], erased=True, require_closed=True)
    validate_raw_term(original_object["source_erased"], erased=True, require_closed=True)
    validate_raw_term({"tag": "lambda", "parameter": {"id": 0, "hint": "schema"},
                       "parameter_type": original_object["checked_type"], "body": {"tag": "int64", "value": 0}})
    equal(erase_total(original_object["annotated"]), original_object["erased"], "whole original typed erasure")
    equal(original_object["erased"], original_object["source_erased"], "ordinary whole source erasure")
    loaded_sources, outer, renamed_declarations = _validate_resolution(module_custody)
    origins = original_object["binder_origins"]
    _bounded_json(origins)
    validate_schema(origins, "origins")
    require(origins["policy"] == "constraint-core-association/1", "unknown binder association policy")
    declarations = origins["source_program"]["declarations"]
    annotated = original_object["annotated"]
    original_declarations = annotated["declarations"] if annotated["tag"] == "with_data" else []
    equal(original_declarations, declarations, "original/source program complete declarations")
    # Class lowering may append generated dictionary declarations; every actual
    # renamed nominal declaration must survive unchanged in original order.
    index = 0
    for declaration in declarations:
        if index < len(renamed_declarations) and exact_equal(declaration, renamed_declarations[index]):
            index += 1
    require(index == len(renamed_declarations), "renamed nominal declaration omitted/changed by source program")
    equal(origins["source_program"]["body"], origins["lowered_expression"], "supported identity surface lowering")
    replayed_core = _desugar(origins["lowered_expression"])
    equal(replayed_core, origins["source_core"], "lowered expression/Core correspondence")
    rows, wanted_generations = _pair_core(origins["source_core"], origins["typed_skeleton"], outer, declarations)
    equal(rows, origins["bindings"], "actual generated binder origin rows")
    resolved_members = [b for row in rows for b in row["bindings"] if b["association"] == "resolved_outer_declaration"]
    names = [b["source_internal_name"] for b in resolved_members]
    require(len(names) == len(outer) and set(names) == set(outer), "resolved outer declaration association missing/duplicated")
    evidence_rows = origins["resolved_evidence"]
    evidence_ids = [row["generation"] for row in evidence_rows]
    require(evidence_ids == sorted(wanted_generations), "resolved evidence generation inventory differs")
    evidence = {row["generation"]: row["term"] for row in evidence_rows}
    source_erased = _erase_typed(origins["typed_skeleton"], evidence)
    validate_raw_term(source_erased, erased=True, require_closed=True)
    equal(source_erased, original_object["source_erased"], "actual Typed/evidence source erasure")
    binding_rows = _erased_rows(original_object["erased"])
    equal(binding_rows, _erased_rows(original_object["source_erased"]), "checked/source erased binding graph")
    equal(binding_rows, origins["erased_bindings"], "recorded erased binding rows")
    row_view = [{"path": r["path"], "kind": r["kind"], "names": [b["name"] for b in r["bindings"]]} for r in rows]
    equal(binding_rows, row_view, "paired origin/actual erased binding graph")
    return {
        "policy": module_custody["policy"],
        "guest_module_count": len(loaded_sources),
        "source_binding_count": sum(len(r["bindings"]) for r in rows),
        "resolved_outer_binding_count": len(resolved_members),
        "bindings": rows,
        "loaded_sources": loaded_sources,
        "trust_boundaries": [
            "Pinned compiled producer and snapshot link authenticate source text -> parsed AST; Python does not parse source text.",
            "Recorded namespace visibility/export selection, builtin facade AST, class lowering and standard instance default insertion remain pinned compiler obligations.",
            "Core/Typed graph edges, types and resolved dictionary proof validity require the genuine ordinary checker; Python only replays schema, lexical identity, binder rows and exact erasure.",
        ],
        "replay_limits": {"schema_cells": MAX_SCHEMA_CELLS, "source_replay_nodes": MAX_NODES, "json_depth": MAX_DEPTH,
                          "source_bindings": "ASCII hint encoding only",
                          "surface_lowering": "identity subset only; unknown transforms reject"},
    }
