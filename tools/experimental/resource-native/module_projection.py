"""Lossless raw XMLF syntax validation and bounded lazy outer-spine replay.

This is NOT the ordinary XMLF type/proof checker. It validates total evidence
syntax and independently replays only the explicit lazy lexical projection.
Runtime admission, original compiler custody and normalization are separate.
Every traversal/comparison here is iterative; no Python recursion-limit changes.
"""

MAX_NODES = 100_000
MAX_DEPTH = 1024
MAX_SPINE = 4096
MAX_BYTES = 32 * 1024 * 1024
MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
PRIMITIVE_SOURCE = "libraries/mlf-language-core/Bootstrap/Primitive.hs"
PRIMITIVE_SOURCE_SHA256 = "f2374f439a11ccd968432b3aab4fede7f43d6340331fcf62d6b9d248e29cb7e5"
# Exact primitiveCode/primitiveName cases from the pinned original source above.
# Evidence may contain any actual enum; this is NOT the strict runtime whitelist.
PRIMITIVES = {
    0: 'ioReturn',
    1: 'ioBind',
    2: 'putStr',
    3: 'putStrLn',
    4: 'getLine',
    5: 'printInt',
    6: 'concatString',
    7: 'showInt',
    8: 'addInt',
    9: 'subInt',
    10: 'eqInt',
    11: 'ltInt',
    12: 'eqString',
    13: 'ifThenElse',
    14: 'mulInt',
    15: 'quotInt',
    16: 'remInt',
    17: 'readInt',
    18: 'addDouble',
    19: 'subDouble',
    20: 'mulDouble',
    21: 'divDouble',
    22: 'sqrtDouble',
    23: 'eqDouble',
    24: 'ltDouble',
    25: 'intToDouble',
    26: 'formatDouble',
    27: 'newIntArray',
    28: 'readIntArray',
    29: 'writeIntArray',
    30: 'lengthIntArray',
    31: 'newDoubleArray',
    32: 'readDoubleArray',
    33: 'writeDoubleArray',
    34: 'lengthDoubleArray',
    35: 'newByteArray',
    36: 'readByteArray',
    37: 'writeByteArray',
    38: 'lengthByteArray',
    39: 'byteArrayFromString',
    40: 'putBytes',
    41: 'getByteLine',
    42: 'newIntTable',
    43: 'readIntTable',
    44: 'writeIntTable',
    45: 'andInt',
    46: 'stringLength',
    47: 'stringCodeAt',
    48: 'stringSlice',
    49: 'stringFromCode',
    50: 'compareString',
    51: 'readDouble',
    52: 'doubleToBits',
    53: 'doubleFromBits',
    54: 'seq',
    55: 'panic',
    56: 'readFile',
    57: 'writeFile',
    58: 'fileExists',
    59: 'canonicalPath',
    60: 'getArgCount',
    61: 'getArg',
    62: 'putErr',
    63: 'exitWith',
    64: 'getExecutablePath',
    65: 'getContents',
    66: 'stReturn',
    67: 'stBind',
    68: 'runST',
    69: 'newSTArray',
    70: 'readSTArray',
    71: 'writeSTArray',
    72: 'lengthSTArray',
    73: 'getEnv',
    74: 'setEnv',
    75: 'unsetEnv',
    76: 'runProcess',
    77: 'listDirectory',
    78: 'directoryExists',
    79: 'fileDigest',
    80: 'acquireFileLock',
    81: 'releaseFileLock',
    82: 'processSupervisor',
    83: 'asyncScopeNew',
    84: 'asyncScopeClose',
    85: 'asyncNewCompletion',
    86: 'asyncResolveCompletion',
    87: 'asyncReadCompletion',
    88: 'asyncSubscribeCompletion',
    89: 'asyncSubscriptionStatus',
    90: 'asyncCancelSubscription',
    91: 'asyncStep',
    92: 'asyncEnqueue',
    93: 'asyncDelay',
    94: 'asyncWait',
    95: 'textToChars',
    96: 'textFromChars',
    97: 'charCode',
    98: 'charFromCode',
    99: 'userError',
    100: 'ioError',
    101: 'catchIOError',
    102: 'ioeGetErrorString',
    103: 'mlfEmptyCallStack',
    104: 'mlfPushCallStack',
    105: 'mlfPrettyCallStack',
    106: 'mlfIOErrorWithStack',
    107: 'concatStringList',
    108: 'orInt',
    109: 'xorInt',
    110: 'shiftLInt',
    111: 'shiftRInt',
    112: 'unsignedShiftRInt',
    113: 'countLeadingZerosInt',
    114: 'countTrailingZerosInt',
    115: 'popCountInt',
    116: 'intToInteger',
    117: 'integerToInt',
    118: 'addInteger',
    119: 'subInteger',
    120: 'mulInteger',
    121: 'quotInteger',
    122: 'remInteger',
    123: 'eqInteger',
    124: 'ltInteger',
    125: 'showInteger',
    126: 'readInteger',
    127: 'integerToDouble',
    128: 'unsignedLtInt',
}


class ProjectionError(ValueError):
    pass


def _fail(message):
    raise ProjectionError(message)


def _integer(value, label, minimum=0, maximum=MAX_I64):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(label + ": canonical integer out of range")


def _text(value, label, nonempty=False):
    if type(value) is not str or (nonempty and not value):
        _fail(label + ": text required")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(label + ": non-scalar Unicode text")


def _object(value, keys, label):
    if type(value) is not dict or set(value) != set(keys):
        _fail(label + ": exact object keys required")


def _list(value, label):
    if type(value) is not list:
        _fail(label + ": array required")


def _budget(value):
    # Count the complete supplied JSON graph before syntax/scoped replay. This
    # also rejects Python-only cycles; shared acyclic objects count per occurrence.
    active = set()
    work = [(False, value, 1)]
    nodes = containers = cells = bytes_used = depth_max = 0
    while work:
        leaving, item, depth = work.pop()
        if leaving:
            active.remove(id(item))
            continue
        depth_max = max(depth_max, depth)
        if depth > MAX_DEPTH:
            _fail("raw JSON depth budget exceeded")
        cells += 1
        if cells > MAX_NODES * 32:
            _fail("raw JSON cell budget exceeded")
        kind = type(item)
        if kind in (dict, list):
            containers += 1
            if containers > MAX_NODES * 8:
                _fail("raw JSON container budget exceeded")
            if id(item) in active:
                _fail("cyclic raw JSON object")
            active.add(id(item))
            work.append((True, item, depth))
            if kind is dict:
                if "tag" in item:
                    nodes += 1
                    if nodes > MAX_NODES:
                        _fail("raw AST node budget exceeded")
                for key, child in item.items():
                    _text(key, "JSON key")
                    bytes_used += len(key.encode("utf-8"))
                    work.append((False, child, depth + 1))
            else:
                work.extend((False, child, depth + 1) for child in item)
        elif kind is str:
            _text(item, "JSON string")
            bytes_used += len(item.encode("utf-8"))
        elif kind is int:
            _integer(item, "JSON number", MIN_I64)
        elif kind not in (bool, type(None)):
            _fail("non-JSON or noncanonical scalar")
        if bytes_used > MAX_BYTES:
            _fail("raw text byte budget exceeded")
    return {"tagged_nodes": nodes, "containers": containers,
            "max_json_depth": depth_max, "text_bytes": bytes_used}


def exact_equal(left, right):
    """Type-sensitive iterative JSON equality (bool is never integer)."""
    _budget(left)
    _budget(right)
    work = [(left, right)]
    while work:
        a, b = work.pop()
        if type(a) is not type(b):
            return False
        if type(a) is dict:
            if set(a) != set(b):
                return False
            work.extend((a[k], b[k]) for k in a)
        elif type(a) is list:
            if len(a) != len(b):
                return False
            work.extend(zip(a, b))
        elif a != b:
            return False
    return True


def validate_raw_term(term, *, erased=False, require_closed=False,
                      allow_evidence_holes=False):
    """Validate total syntax, boundedness and fresh term-ID consistency only.

    Actual compiler-generated term binders are globally fresh. Textual shadowing
    with DISTINCT IDs is valid; duplicate binder IDs and inconsistent hints reject.
    Type-variable binders may recur in separate type/proof annotations as normal.
    """
    if type(erased) is not bool or type(require_closed) is not bool or type(allow_evidence_holes) is not bool:
        _fail("validator options must be booleans")
    stats = _budget(term)
    work = [("term", term)]
    hints = {}
    binders = set()

    def name(n, binder=False):
        _object(n, {"id", "hint"}, "term name")
        _integer(n["id"], "term name ID")
        _text(n["hint"], "term hint")
        if n["id"] in hints and hints[n["id"]] != n["hint"]:
            _fail("one term ID has inconsistent hints")
        hints[n["id"]] = n["hint"]
        if binder:
            if n["id"] in binders:
                _fail("duplicate/rebinding term ID")
            binders.add(n["id"])

    def array(value, category, label):
        _list(value, label)
        work.extend((category, child) for child in value)

    while work:
        category, node = work.pop()
        if type(node) is not dict or type(node.get("tag")) is not str:
            _fail(category + ": tagged object required")
        tag = node["tag"]
        if category == "kind":
            if tag == "star":
                _object(node, {"tag"}, "kind star")
            elif tag == "arrow":
                _object(node, {"tag", "from", "to"}, "kind arrow")
                work.extend(("kind", node[k]) for k in ("from", "to"))
            else:
                _fail("unknown kind tag")
        elif category == "type":
            if tag == "var":
                _object(node, {"tag", "id"}, "type var"); _integer(node["id"], "type ID")
            elif tag == "bottom":
                _object(node, {"tag"}, "type bottom")
            elif tag == "bottom_kind":
                _object(node, {"tag", "kind"}, "type bottom-kind"); work.append(("kind", node["kind"]))
            elif tag == "arrow":
                _object(node, {"tag", "from", "to"}, "type arrow")
                work.extend(("type", node[k]) for k in ("from", "to"))
            elif tag == "constructor":
                _object(node, {"tag", "name", "arguments"}, "type constructor")
                _text(node["name"], "type constructor", True); array(node["arguments"], "type", "type arguments")
            elif tag == "apply":
                _object(node, {"tag", "function", "argument"}, "type apply")
                work.extend(("type", node[k]) for k in ("function", "argument"))
            elif tag == "forall":
                _object(node, {"tag", "id", "bound", "body"}, "type forall"); _integer(node["id"], "forall ID")
                work.extend(("type", node[k]) for k in ("bound", "body"))
            else:
                _fail("unknown type tag")
        elif category == "proof":
            if tag in ("refl", "elim"):
                _object(node, {"tag"}, "proof " + tag)
            elif tag == "bottom":
                _object(node, {"tag", "type"}, "proof bottom"); work.append(("type", node["type"]))
            elif tag in ("hyp", "intro"):
                _object(node, {"tag", "id"}, "proof " + tag); _integer(node["id"], "proof type ID")
            elif tag == "inner":
                _object(node, {"tag", "witness"}, "proof inner"); work.append(("proof", node["witness"]))
            elif tag == "outer":
                _object(node, {"tag", "id", "witness"}, "proof outer"); _integer(node["id"], "proof type ID"); work.append(("proof", node["witness"]))
            elif tag == "intro_kind":
                _object(node, {"tag", "id", "kind"}, "proof intro kind"); _integer(node["id"], "proof type ID"); work.append(("kind", node["kind"]))
            elif tag == "then":
                _object(node, {"tag", "first", "second"}, "proof then")
                work.extend(("proof", node[k]) for k in ("first", "second"))
            else:
                _fail("unknown computation/proof tag")
        elif category == "field":
            if tag == "parameter":
                _object(node, {"tag", "name"}, "field parameter"); _text(node["name"], "field parameter", True)
            elif tag == "function":
                _object(node, {"tag", "from", "to"}, "field function")
                work.extend(("field", node[k]) for k in ("from", "to"))
            elif tag == "applied":
                _object(node, {"tag", "name", "arguments"}, "field applied")
                _text(node["name"], "field constructor", True); array(node["arguments"], "field", "field arguments")
            elif tag == "application":
                _object(node, {"tag", "function", "argument"}, "field application")
                work.extend(("field", node[k]) for k in ("function", "argument"))
            elif tag == "quantified":
                _object(node, {"tag", "name", "kind", "body"}, "field quantified")
                _text(node["name"], "quantified field name", True)
                work.extend((("kind", node["kind"]), ("field", node["body"])))
            else:
                _fail("unknown field tag")
        elif category == "declaration":
            if tag not in ("data", "data_kind"):
                _fail("unknown declaration tag")
            _object(node, {"tag", "name", "parameters", "constructors"}, "declaration")
            _text(node["name"], "datatype name", True)
            _list(node["parameters"], "datatype parameters"); params = []
            for p in node["parameters"]:
                if tag == "data":
                    _text(p, "datatype parameter", True); params.append(p)
                else:
                    _object(p, {"name", "kind"}, "kinded datatype parameter")
                    _text(p["name"], "datatype parameter", True); params.append(p["name"]); work.append(("kind", p["kind"]))
            if len(params) != len(set(params)):
                _fail("duplicate datatype parameter")
            _list(node["constructors"], "datatype constructors"); cs = []
            for c in node["constructors"]:
                _object(c, {"name", "fields"}, "constructor declaration")
                _text(c["name"], "constructor name", True); cs.append(c["name"]); array(c["fields"], "field", "constructor fields")
            if len(cs) != len(set(cs)):
                _fail("duplicate constructor within declaration")
        elif category == "pattern":
            if tag == "constructor":
                _object(node, {"tag", "constructor", "fields"}, "constructor pattern")
                _text(node["constructor"], "pattern constructor", True); _list(node["fields"], "pattern fields")
                for n in node["fields"]:
                    if n is not None: name(n, True)
            elif tag == "default":
                _object(node, {"tag", "binder"}, "default pattern")
                if node["binder"] is not None: name(node["binder"], True)
            else:
                _fail("unknown pattern tag")
        elif category == "term":
            if tag == "var":
                _object(node, {"tag", "name"}, "var"); name(node["name"])
            elif tag == "lambda":
                keys = {"tag", "parameter", "body"} | (set() if erased else {"parameter_type"})
                _object(node, keys, "lambda"); name(node["parameter"], True); work.append(("term", node["body"]))
                if not erased: work.append(("type", node["parameter_type"]))
            elif tag == "application":
                _object(node, {"tag", "function", "argument"}, "application")
                work.extend(("term", node[k]) for k in ("function", "argument"))
            elif tag == "type_lambda" and not erased:
                _object(node, {"tag", "id", "bound", "body"}, "type lambda"); _integer(node["id"], "term type-binder ID")
                work.extend((("type", node["bound"]), ("term", node["body"])))
            elif tag == "type_application" and not erased:
                _object(node, {"tag", "value", "witness"}, "type application")
                work.extend((("term", node["value"]), ("proof", node["witness"])))
            elif tag == "let":
                _object(node, {"tag", "name", "value", "body"}, "let"); name(node["name"], True)
                work.extend(("term", node[k]) for k in ("value", "body"))
            elif tag == "letrec":
                _object(node, {"tag", "bindings", "body"}, "letrec"); _list(node["bindings"], "recursive bindings")
                for b in node["bindings"]:
                    _object(b, {"name", "value"} | (set() if erased else {"type"}), "recursive binding")
                    name(b["name"], True); work.append(("term", b["value"]))
                    if not erased: work.append(("type", b["type"]))
                work.append(("term", node["body"]))
            elif tag == "int64":
                _object(node, {"tag", "value"}, "Int64 literal"); _integer(node["value"], "Int64 literal", MIN_I64)
            elif tag == "double":
                _object(node, {"tag", "bits_i64"}, "Double literal"); _integer(node["bits_i64"], "Double bits", MIN_I64)
            elif tag == "bool":
                _object(node, {"tag", "value"}, "Bool literal")
                if type(node["value"]) is not bool: _fail("Bool literal must be bool")
            elif tag == "string":
                _object(node, {"tag", "value"}, "String literal"); _text(node["value"], "String literal")
            elif tag == "primitive":
                _object(node, {"tag", "id", "name"} | (set() if erased else {"arguments"}), "primitive")
                _integer(node["id"], "primitive ID"); _text(node["name"], "primitive name", True)
                if PRIMITIVES.get(node["id"]) != node["name"]: _fail("unknown or mismatched primitive identity")
                if not erased: array(node["arguments"], "type", "primitive type arguments")
            elif tag == "constructor":
                _object(node, {"tag", "name"} | (set() if erased else {"arguments"}), "constructor")
                _text(node["name"], "constructor name", True)
                if not erased: array(node["arguments"], "type", "constructor type arguments")
            elif tag == "case":
                _object(node, {"tag", "scrutinee", "alternatives"} | (set() if erased else {"result_type"}), "case")
                work.append(("term", node["scrutinee"]))
                if not erased: work.append(("type", node["result_type"]))
                _list(node["alternatives"], "case alternatives")
                for a in node["alternatives"]:
                    _object(a, {"pattern", "body"}, "case alternative")
                    work.extend((("pattern", a["pattern"]), ("term", a["body"])))
            elif tag == "with_data" and not erased:
                _object(node, {"tag", "declarations", "body"}, "with_data")
                array(node["declarations"], "declaration", "declarations"); work.append(("term", node["body"]))
            elif tag == "evidence_hole" and erased:
                _object(node, {"tag", "id"}, "evidence hole"); _integer(node["id"], "evidence hole ID")
                if not allow_evidence_holes: _fail("unresolved evidence hole in checked erasure")
            else:
                _fail("unknown or context-invalid term tag: " + tag)
        else:
            _fail("internal unknown syntax category")
    if require_closed and erased and _free_erased(term):
        _fail("open checked erased term")
    if require_closed and not erased and _free_typed(term):
        _fail("open checked annotated term")
    stats["term_binders"] = len(binders)
    return stats


def _pattern_ids(pattern):
    fields = pattern["fields"] if pattern["tag"] == "constructor" else [pattern["binder"]]
    return [n["id"] for n in fields if n is not None]


def _free_typed(root):
    """Typed lexical traversal, with mutable scope + explicit enter/leave events."""
    bound = set(); found = set(); work = [("visit", root)]
    while work:
        action, item = work.pop()
        if action == "enter": bound.update(item); continue
        if action == "leave": bound.difference_update(item); continue
        tag = item["tag"]
        if tag == "var":
            n = item["name"]["id"]
            if n not in bound: found.add(n)
        elif tag == "lambda":
            ns = [item["parameter"]["id"]]
            work.extend((("leave", ns), ("visit", item["body"]), ("enter", ns)))
        elif tag == "application":
            work.extend((("visit", item["function"]), ("visit", item["argument"])))
        elif tag in ("type_lambda", "with_data"):
            work.append(("visit", item["body"]))
        elif tag == "type_application": work.append(("visit", item["value"]))
        elif tag == "let":
            ns = [item["name"]["id"]]
            work.extend((("leave", ns), ("visit", item["body"]), ("enter", ns), ("visit", item["value"])))
        elif tag == "letrec":
            ns = [b["name"]["id"] for b in item["bindings"]]
            work.extend((("leave", ns), ("visit", item["body"])))
            work.extend(("visit", b["value"]) for b in item["bindings"])
            work.append(("enter", ns))
        elif tag == "case":
            for a in item["alternatives"]:
                ns = _pattern_ids(a["pattern"])
                work.extend((("leave", ns), ("visit", a["body"]), ("enter", ns)))
            work.append(("visit", item["scrutinee"]))
    return found


def _free_erased(root):
    """Separate erased lexical implementation, not typed-AST reconstruction."""
    pending = [(root, None)]; scope = set(); uses = set()
    while pending:
        expr, scope_change = pending.pop()
        if expr is None:
            adding, ids = scope_change
            if adding: scope.update(ids)
            else: scope.difference_update(ids)
            continue
        tag = expr["tag"]
        if tag == "var":
            identity = expr["name"]["id"]
            if identity not in scope: uses.add(identity)
        elif tag == "lambda":
            ids = (expr["parameter"]["id"],)
            pending += [(None, (False, ids)), (expr["body"], None), (None, (True, ids))]
        elif tag == "application": pending += [(expr["argument"], None), (expr["function"], None)]
        elif tag == "let":
            ids = (expr["name"]["id"],)
            pending += [(None, (False, ids)), (expr["body"], None), (None, (True, ids)), (expr["value"], None)]
        elif tag == "letrec":
            ids = tuple(b["name"]["id"] for b in expr["bindings"])
            pending += [(None, (False, ids)), (expr["body"], None)]
            pending += [(b["value"], None) for b in reversed(expr["bindings"])]
            pending += [(None, (True, ids))]
        elif tag == "case":
            pending.append((expr["scrutinee"], None))
            for alt in reversed(expr["alternatives"]):
                p = alt["pattern"]
                ns = p["fields"] if p["tag"] == "constructor" else [p["binder"]]
                ids = tuple(n["id"] for n in ns if n is not None)
                pending += [(None, (False, ids)), (alt["body"], None), (None, (True, ids))]
    return uses


def free_names(term, *, erased=False):
    validate_raw_term(term, erased=erased)
    return _free_erased(term) if erased else _free_typed(term)


def _term_children(term):
    tag = term["tag"]
    if tag in ("lambda", "type_lambda", "with_data"): return [term["body"]]
    if tag == "type_application": return [term["value"]]
    if tag == "application": return [term["function"], term["argument"]]
    if tag == "let": return [term["value"], term["body"]]
    if tag == "letrec": return [b["value"] for b in term["bindings"]] + [term["body"]]
    if tag == "case": return [term["scrutinee"]] + [a["body"] for a in term["alternatives"]]
    return []


def erase_total(term):
    """Exact total X.erase shape, including unsupported evidence-only forms."""
    validate_raw_term(term)
    outputs = {}; pending = [(False, term)]
    while pending:
        ready, node = pending.pop()
        if not ready:
            pending.append((True, node)); pending.extend((False, c) for c in _term_children(node)); continue
        tag = node["tag"]; child = lambda n: outputs[id(n)]
        if tag in ("type_lambda", "with_data"): result = child(node["body"])
        elif tag == "type_application": result = child(node["value"])
        elif tag == "lambda": result = {"tag":tag, "parameter":node["parameter"], "body":child(node["body"])}
        elif tag == "application": result = {"tag":tag, "function":child(node["function"]), "argument":child(node["argument"])}
        elif tag == "let": result = {"tag":tag, "name":node["name"], "value":child(node["value"]), "body":child(node["body"])}
        elif tag == "letrec": result = {"tag":tag, "bindings":[{"name":b["name"], "value":child(b["value"])}for b in node["bindings"]], "body":child(node["body"])}
        elif tag == "case": result = {"tag":tag, "scrutinee":child(node["scrutinee"]), "alternatives":[{"pattern":a["pattern"],"body":child(a["body"])}for a in node["alternatives"]]}
        elif tag in ("primitive", "constructor"): result = {k:v for k,v in node.items() if k != "arguments"}
        else: result = dict(node)
        outputs[id(node)] = result
    result = outputs[id(term)]
    validate_raw_term(result, erased=True)
    return result


def project_typed(term):
    validate_raw_term(term, require_closed=True)
    wrapper = term if term["tag"] == "with_data" else None
    current = term["body"] if wrapper is not None else term
    spine = []
    while current["tag"] in ("let", "letrec"):
        if len(spine) == MAX_SPINE: _fail("outer typed spine budget exceeded")
        spine.append(current); current = current["body"]
    if current["tag"] == "with_data": _fail("nested with_data on projection spine")
    needed = _free_typed(current); result = current; reverse_steps = []
    for index in range(len(spine)-1, -1, -1):
        node = spine[index]
        if node["tag"] == "let":
            ids = [node["name"]["id"]]; deps = _free_typed(node["value"])
        else:
            ids = [b["name"]["id"] for b in node["bindings"]]; deps = set()
            for b in node["bindings"]: deps.update(_free_typed(b["value"]))
            deps.difference_update(ids)
        demand = needed.intersection(ids); keep = bool(demand); before = sorted(needed)
        if keep:
            needed = (needed - set(ids)) | deps
            result = dict(node, body=result)
        reverse_steps.append({"index":index,"kind":node["tag"],"binding_ids":ids,"rhs_free_ids":sorted(deps),"demanded_ids":sorted(demand),"keep":keep,"need_before":before,"need_after":sorted(needed)})
    if needed: _fail("typed projection leaves external dependencies")
    if wrapper is not None: result = dict(wrapper, body=result)
    return result, list(reversed(reverse_steps))


def project_erased(term):
    validate_raw_term(term, erased=True, require_closed=True)
    entries = []; cursor = term
    while cursor["tag"] == "let" or cursor["tag"] == "letrec":
        if len(entries) >= MAX_SPINE: _fail("outer erased spine budget exceeded")
        entries.append(cursor); cursor = cursor["body"]
    live = _free_erased(cursor); answer = cursor; rows = [None] * len(entries)
    pos = len(entries)
    while pos:
        pos -= 1; entry = entries[pos]; before = sorted(live)
        if entry["tag"] == "letrec":
            group = [binding["name"]["id"] for binding in entry["bindings"]]
            dependencies = set()
            for binding in entry["bindings"]: dependencies |= _free_erased(binding["value"])
            dependencies -= set(group)
        else:
            group = [entry["name"]["id"]]; dependencies = _free_erased(entry["value"])
        demanded = sorted(identity for identity in group if identity in live)
        chosen = len(demanded) != 0
        if chosen:
            live.difference_update(group); live.update(dependencies)
            answer = {k:(answer if k == "body" else v) for k,v in entry.items()}
        rows[pos] = {"index":pos,"kind":entry["tag"],"binding_ids":group,"rhs_free_ids":sorted(dependencies),"demanded_ids":demanded,"keep":chosen,"need_before":before,"need_after":sorted(live)}
    if live: _fail("erased projection leaves external dependencies")
    return answer, rows


def _validate_steps(steps):
    _budget(steps); _list(steps, "projection steps")
    if len(steps) > MAX_SPINE: _fail("projection step budget exceeded")
    keys = {"index","kind","binding_ids","rhs_free_ids","demanded_ids","keep","need_before","need_after"}
    for index, row in enumerate(steps):
        _object(row, keys, "projection row"); _integer(row["index"], "projection index")
        if row["index"] != index or row["kind"] not in ("let", "letrec") or type(row["keep"]) is not bool:
            _fail("projection row index/kind/keep malformed")
        for key in ("binding_ids","rhs_free_ids","demanded_ids","need_before","need_after"):
            values = row[key]; _list(values, key)
            for identity in values: _integer(identity, key)
            if len(set(values)) != len(values): _fail(key + ": duplicate IDs")
            if key != "binding_ids" and values != sorted(values): _fail(key + ": canonical sorted set required")
        if row["kind"] == "let" and len(row["binding_ids"]) != 1: _fail("let must bind one identity")


def replay_projection(original_typed, original_erased, projected_typed, projected_erased, steps):
    """Reconstruct both projections independently and verify exact supplied bytes.

    A type wrapper that erases to expose extra outer lets is conservatively
    rejected: typed/erased eligible spine identity vectors must match. No commuting.
    """
    _validate_steps(steps)
    validate_raw_term(projected_typed, require_closed=True)
    validate_raw_term(projected_erased, erased=True, require_closed=True)
    actual_typed, typed_rows = project_typed(original_typed)
    actual_erased, erased_rows = project_erased(original_erased)
    if not exact_equal(erase_total(original_typed), original_erased):
        _fail("original typed/erased projection differs")
    if not exact_equal(typed_rows, erased_rows):
        _fail("typed/erased eligible spines differ; no wrapper commuting")
    if not exact_equal(steps, typed_rows): _fail("projection witness differs from lexical replay")
    if not exact_equal(projected_typed, actual_typed): _fail("projected annotated term differs from replay")
    if not exact_equal(projected_erased, actual_erased): _fail("projected erased term differs from independent replay")
    if not exact_equal(erase_total(actual_typed), actual_erased): _fail("erased-projection relation differs")
    return {"policy":"outer-lazy-spine/1","spine_entries":len(steps),
            "kept_entries":sum(row["keep"] for row in steps),
            "dropped_entries":sum(not row["keep"] for row in steps),
            "kept_binding_ids":[n for row in steps if row["keep"] for n in row["binding_ids"]],
            "closed":True}
