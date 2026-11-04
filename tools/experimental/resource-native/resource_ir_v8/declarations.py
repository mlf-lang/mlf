"""Bounded, immutable logical declarations for the isolated IR8 prerequisite.

This module never imports the existing checker/runtime, evaluates a body, or
establishes source, ownership, allocation-site, native, or ABI acceptance.
Canonical nodes are hash-consed using *integer child IDs*. Neither validation nor
canonical ordering expands a shared type DAG into an exponential syntax tree.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
import hashlib
import json


MAX_INPUT_BYTES = 4 * 1024 * 1024
# No legal declaration object nests containers this deeply. This syntactic guard
# is independent of the logical type DAG's depth and precedes JSON decoding.
MAX_CONTAINER_DEPTH = 8
MAX_TYPES = 4096
MAX_TYPE_DEPTH = 32
MAX_SCHEMES = 16
MAX_PARAMETERS = 8
MAX_USES = 1024
MAX_ENVIRONMENTS = 1024
MAX_FAMILIES = 64
MAX_VARIANTS = 64
MAX_FIELDS = 32
_RESERVED = ("@", "#", "%", "^")
_INTRINSICS = ("#bool", "#i64")
_TOP_KEYS = {"layouts", "families", "signatures", "types", "schemes", "instantiations"}


class DeclarationError(ValueError):
    """A declaration-only rejection, with an explicit input/query location."""

    def __init__(self, path: str, code: str, message: str):
        self.path, self.code, self.message = path, code, message
        super().__init__(f"{path}: {code}: {message}")


def _fail(path, code, message):
    raise DeclarationError(path, code, message)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _name(value, path, *, physical=False, declaration=False):
    if type(value) is not str or not value or "\0" in value:
        _fail(path, "NAME", "expected a nonempty, NUL-free string")
    if len(value) > MAX_INPUT_BYTES:
        _fail(path, "INPUT_SIZE", "name exceeds the serialized-input guard")
    # Surrogate code points cannot be serialized as valid UTF-8.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(path, "NAME", "name must be valid UTF-8")
    if declaration and value.startswith("^"):
        _fail(path, "NAMESPACE", "user-declared names cannot occupy the ^ namespace")
    if physical and value.startswith(_RESERVED):
        _fail(path, "NAMESPACE", "physical declaration names cannot occupy @/#/%/^ namespaces")
    return value


def _keys(value, expected, path):
    if type(value) is not dict or set(value) != expected:
        _fail(path, "SCHEMA", "expected exactly these keys: " + ", ".join(sorted(expected)))
    return value


def _map(value, limit, path):
    if type(value) is not dict:
        _fail(path, "SCHEMA", "expected an object")
    if len(value) > limit:
        _fail(path, "COUNT", f"at most {limit} entries are permitted")
    return value


def _list(value, limit, path):
    if type(value) is not list:
        _fail(path, "SCHEMA", "expected an array")
    if len(value) > limit:
        _fail(path, "COUNT", f"at most {limit} elements are permitted")
    return value


def _count(value, lower, upper, path):
    if type(value) is not int or not lower <= value <= upper:
        _fail(path, "COUNT", f"expected an integer in {lower}..{upper}, not a boolean")
    return value


def _snapshot(data):
    """Copy plain JSON values with a prior bounded-depth/size/cycle check.

    Recursion here is explicitly limited to eight container levels. Active-path
    identities distinguish a Python cycle from harmless shared input containers.
    Each occurrence is copied and charged, so input sharing cannot evade size.
    """
    active = set()
    remaining = MAX_INPUT_BYTES

    def charge(amount, path):
        nonlocal remaining
        remaining -= amount
        if remaining < 0:
            _fail(path, "INPUT_SIZE", "canonical declaration input exceeds 4 MiB UTF-8")

    def string(value, path):
        if len(value) > MAX_INPUT_BYTES:
            _fail(path, "INPUT_SIZE", "string exceeds the serialized-input guard")
        try:
            encoded = _json(value).encode("utf-8")
        except UnicodeEncodeError:
            _fail(path, "INPUT_VALUE", "strings must be valid UTF-8")
        charge(len(encoded), path)
        return value

    def copy(value, path, depth):
        kind = type(value)
        if kind is str:
            return string(value, path)
        if value is None or kind is bool:
            charge(4 if value is None or value is True else 5, path)
            return value
        if kind is int:
            # Declaration integers are small counts/indices. Reject enormous
            # Python integers before decimal conversion can allocate/work freely.
            if value.bit_length() > 64:
                _fail(path, "INPUT_VALUE", "declaration integer exceeds count representation")
            charge(len(str(value)), path)
            return value
        if kind not in (dict, list):
            _fail(path, "INPUT_VALUE", "only plain JSON objects, arrays, strings, integers, booleans and null are allowed")
        if depth >= MAX_CONTAINER_DEPTH:
            _fail(path, "INPUT_DEPTH", "declaration container nesting exceeds the schema guard")
        if len(value) > MAX_TYPES:
            _fail(path, "COUNT", "no declaration map or array may exceed 4096 entries")
        identity = id(value)
        if identity in active:
            _fail(path, "INPUT_CYCLE", "cyclic Python declaration input")
        active.add(identity)
        charge(2 + max(0, len(value) - 1), path)
        if kind is dict:
            result = {}
            for key, item in value.items():
                if type(key) is not str:
                    _fail(path, "INPUT_VALUE", "object keys must be plain strings")
                string(key, path)
                charge(1, path)
                result[key] = copy(item, path + "[" + _json(key) + "]", depth + 1)
        else:
            result = [copy(item, f"{path}[{index}]", depth + 1)
                      for index, item in enumerate(value)]
        active.remove(identity)
        return result

    copied = copy(data, "declarations", 0)
    return copied, _json(copied)


def _prescan_json(text):
    if type(text) is not str:
        _fail("declarations", "INPUT_VALUE", "loads_declarations expects a plain string")
    if len(text) > MAX_INPUT_BYTES:
        _fail("declarations", "INPUT_SIZE", "serialized input exceeds 4 MiB UTF-8")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        _fail("declarations", "INPUT_VALUE", "serialized input must be valid UTF-8")
    if size > MAX_INPUT_BYTES:
        _fail("declarations", "INPUT_SIZE", "serialized input exceeds 4 MiB UTF-8")
    depth, quoted, escaped = 0, False, False
    for char in text:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "[{":
            depth += 1
            if depth > MAX_CONTAINER_DEPTH:
                _fail("declarations", "INPUT_DEPTH", "declaration container nesting exceeds the schema guard")
        elif char in "]}":
            depth -= 1
            if depth < 0:
                _fail("declarations", "JSON", "unbalanced JSON containers")


def loads_declarations(text: str) -> DeclarationIndex:
    """Decode strict duplicate-free JSON, then check declarations only."""
    _prescan_json(text)

    def object_pairs(pairs):
        if len(pairs) > MAX_TYPES:
            _fail("declarations", "COUNT", "no declaration object may exceed 4096 entries")
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("declarations[" + _json(key) + "]", "DUPLICATE_KEY", "duplicate JSON object key")
            result[key] = value
        return result

    def nonfinite(_):
        _fail("declarations", "JSON", "nonfinite JSON constants are forbidden")

    try:
        data = json.loads(text, object_pairs_hook=object_pairs, parse_constant=nonfinite)
    except DeclarationError:
        raise
    except (ValueError, RecursionError) as error:
        _fail("declarations", "JSON", "malformed JSON: " + str(error))
    return check_declarations(data)


def _lookup(rows, key):
    """Binary search immutable (name, value) rows; no persistent lookup cache."""
    low, high = 0, len(rows)
    while low < high:
        middle = (low + high) // 2
        if rows[middle][0] < key:
            low = middle + 1
        else:
            high = middle
    return rows[low][1] if low < len(rows) and rows[low][0] == key else None


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class DeclarationIndex:
    """An immutable declaration snapshot, deliberately not a CheckedProgram.

    Row indices in type_rows are deterministic type IDs. Every record, including
    report(), is an immutable tuple. Only the checking functions construct valid
    indexes; this data class is not a security boundary against hostile Python.
    """

    canonical_json: str
    sha256: str
    type_rows: tuple
    environments: tuple
    schemes: tuple
    instantiations: tuple
    _references: tuple
    _row_scopes: tuple
    _row_generic_atoms: tuple
    _row_generic_contracts: tuple
    _scheme_names: tuple
    _uses: tuple

    def __repr__(self):
        return (f"DeclarationIndex(declarations-only, sha256={self.sha256!r}, "
                f"types={len(self.type_rows)}, environments={len(self.environments)})")

    def _resolve_id(self, reference, scope):
        path = "query.reference"
        reference = _name(reference, path)
        if scope is not None:
            _name(scope, "query.scope", declaration=True)
            if scope not in self._scheme_names:
                _fail("query.scope", "SCOPE", "unknown declared scheme")
        row = _lookup(self._references, reference)
        if row is None:
            _fail(path, "REFERENCE", "unknown physical or ^type reference")
        if any(owner != scope for owner in self._row_scopes[row]):
            _fail(path, "SCOPE", "free rigid variables require their exact explicit scheme scope")
        if scope is not None and not self._row_generic_atoms[row]:
            _fail(path, "GENERIC_ATOM", "generic scope admits only Int, Bool, own rigids and arrows")
        if scope is not None and not self._row_generic_contracts[row]:
            _fail(path, "GENERIC_CONTRACT", "generic scope admits only recursively repeat/unknown arrows")
        return row

    def resolve(self, reference, scope=None):
        return self.type_rows[self._resolve_id(reference, scope)]

    def same(self, left, right, scope=None):
        # Comparing interned IDs avoids exponential Python tuple equality on a DAG.
        return self._resolve_id(left, scope) == self._resolve_id(right, scope)

    def instantiated(self, use_name):
        _name(use_name, "query.instantiation", declaration=True)
        result = _lookup(self._uses, use_name)
        if result is None:
            _fail("query.instantiation", "USE", "unknown declared instantiation")
        return result

    def report(self):
        return (("status", "declarations-only"),
                ("scope", "No body, resource/all-path, native, or source acceptance; no execution route."),
                ("sha256", self.sha256),
                ("canonical_type_count", len(self.type_rows)),
                ("scheme_count", len(self.schemes)),
                ("instantiation_count", len(self.instantiations)),
                ("environment_count", len(self.environments)))


class _Builder:
    """Disposable checker state, never retained in the returned index."""

    def __init__(self, data, canonical_json):
        self.data = data
        self.canonical_json = canonical_json
        self.nodes = []
        self.node_ids = {}
        self.depths = []
        self.scopes = []
        self.generic_atoms = []
        self.generic_contracts = []
        self.definitions = {}
        self.normalized = {}
        self.references = {}
        self.scheme_bodies = {}
        self.vectors = {}
        self.uses = {}

    def intern(self, node, path):
        existing = self.node_ids.get(node)
        if existing is not None:
            return existing
        if len(self.nodes) >= MAX_TYPES:
            _fail(path, "TYPE_COUNT", "declared and derived canonical types exceed 4096")
        tag = node[0]
        if tag == "arrow":
            _, argument, result, protocol, identity = node
            depth = 1 + max(self.depths[argument], self.depths[result])
            scopes = self.scopes[argument] | self.scopes[result]
            atoms = self.generic_atoms[argument] and self.generic_atoms[result]
            contracts = (protocol == "repeat" and identity == "unknown"
                         and self.generic_contracts[argument] and self.generic_contracts[result])
            if identity == "argument" and argument != result:
                _fail(path, "IDENTITY", "argument identity requires exact canonical argument/result equality")
        else:
            depth = 1
            scopes = frozenset((node[1],)) if tag == "rigid" else frozenset()
            atoms = tag == "rigid" or node[1] in _INTRINSICS
            contracts = True
        if scopes and not atoms:
            _fail(path, "GENERIC_ATOM", "open types and signatures cannot contain nominal DATA/SUM atoms")
        if scopes and not contracts:
            _fail(path, "GENERIC_CONTRACT", "open types and signatures admit only recursively repeat/unknown arrows")
        if depth > MAX_TYPE_DEPTH:
            _fail(path, "TYPE_DEPTH", "canonical type depth exceeds 32")
        result = len(self.nodes)
        self.nodes.append(node)
        self.node_ids[node] = result
        self.depths.append(depth)
        self.scopes.append(scopes)
        self.generic_atoms.append(atoms)
        self.generic_contracts.append(contracts)
        return result

    def type_id(self, name, path):
        _name(name, path, declaration=True)
        if name not in self.data["types"]:
            _fail(path, "TYPE_REFERENCE", "unknown declared type ID")
        return ("type", name)

    def physical(self, reference, path, *, atom_only=False):
        reference = _name(reference, path)
        if reference.startswith("^"):
            if atom_only:
                _fail(path, "CLOSED_ATOM", "closed entries cannot alias ^type references")
            return self.type_id(reference[1:], path)
        if reference.startswith("@"):
            if atom_only:
                _fail(path, "CLOSED_ATOM", "closed entries cannot hide callable contracts")
            target = reference[1:]
            if target not in self.data["signatures"]:
                _fail(path, "SIGNATURE", "unknown callable signature")
            return ("signature", target)
        if reference.startswith("#"):
            if reference not in _INTRINSICS:
                _fail(path, "CLOSED_ATOM", "unknown intrinsic scalar")
        elif reference.startswith("%"):
            if reference[1:] not in self.data["families"]:
                _fail(path, "FAMILY", "unknown nominal family")
        elif reference not in self.data["layouts"]:
            _fail(path, "LAYOUT", "unknown physical DATA layout")
        return self.intern(("closed", reference), path)

    @staticmethod
    def contract(spec, path):
        if spec["protocol"] not in ("repeat", "once"):
            _fail(path + ".protocol", "CONTRACT", "protocol must be repeat or once")
        if spec["result_identity"] not in ("unknown", "argument"):
            _fail(path + ".result_identity", "CONTRACT", "result identity must be unknown or argument")

    def schemas(self):
        d = _keys(self.data, _TOP_KEYS, "declarations")
        for key, limit in (("layouts", MAX_TYPES), ("families", MAX_FAMILIES),
                           ("signatures", MAX_TYPES), ("types", MAX_TYPES),
                           ("schemes", MAX_SCHEMES), ("instantiations", MAX_USES)):
            _map(d[key], limit, key)
            for name in d[key]:
                _name(name, key, physical=key in ("layouts", "families", "signatures"), declaration=True)
        for scheme, spec in d["schemes"].items():
            path = "schemes." + scheme
            _keys(spec, {"parameters", "body"}, path)
            _count(spec["parameters"], 1, MAX_PARAMETERS, path + ".parameters")
            self.type_id(spec["body"], path + ".body")
        for family, spec in d["families"].items():
            path = "families." + family
            _keys(spec, {"variants", "fields"}, path)
            variants = _list(spec["variants"], MAX_VARIANTS, path + ".variants")
            if not variants:
                _fail(path + ".variants", "COUNT", "a nominal family needs at least one variant")
            for variant in variants:
                _name(variant, path + ".variants", declaration=True)
            if len(set(variants)) != len(variants):
                _fail(path + ".variants", "VARIANT", "duplicate nominal variant")
            _keys(spec["fields"], set(variants), path + ".fields")
            for variant in variants:
                fields = _list(spec["fields"][variant], MAX_FIELDS, path + ".fields." + variant)
                for index, reference in enumerate(fields):
                    field_path = f"{path}.fields.{variant}[{index}]"
                    _name(reference, field_path)
                    if reference not in _INTRINSICS and not reference.startswith("%"):
                        _fail(field_path, "FIELD_SHAPE", "family fields require an intrinsic scalar or nominal family reference")
                    self.physical(reference, field_path, atom_only=True)
        for layout, fields in d["layouts"].items():
            path = "layouts." + layout
            _map(fields, MAX_TYPES, path)
            for field, reference in fields.items():
                _name(field, path, declaration=True)
                self.physical(reference, path + "." + field)
        for signature, spec in d["signatures"].items():
            path = "signatures." + signature
            _keys(spec, {"argument", "result", "protocol", "result_identity"}, path)
            self.contract(spec, path)
            children = (self.physical(spec["argument"], path + ".argument"),
                        self.physical(spec["result"], path + ".result"))
            self.definitions[("signature", signature)] = (path, "arrow", children, spec)
        for name, spec in d["types"].items():
            path = "types." + name
            if type(spec) is not dict or "tag" not in spec:
                _fail(path, "SCHEMA", "type declaration requires a tag")
            tag = spec["tag"]
            if tag == "closed":
                _keys(spec, {"tag", "layout"}, path)
                value = self.physical(spec["layout"], path + ".layout", atom_only=True)
                self.normalized[("type", name)] = value
            elif tag == "rigid":
                _keys(spec, {"tag", "scheme", "index"}, path)
                scheme = _name(spec["scheme"], path + ".scheme", declaration=True)
                if scheme not in d["schemes"]:
                    _fail(path + ".scheme", "SCOPE", "rigid names an undeclared scheme")
                _count(spec["index"], 0, d["schemes"][scheme]["parameters"] - 1, path + ".index")
                self.normalized[("type", name)] = self.intern(("rigid", scheme, spec["index"]), path)
            elif tag == "arrow":
                _keys(spec, {"tag", "argument", "result", "protocol", "result_identity"}, path)
                self.contract(spec, path)
                children = (self.type_id(spec["argument"], path + ".argument"),
                            self.type_id(spec["result"], path + ".result"))
                self.definitions[("type", name)] = (path, "arrow", children, spec)
            else:
                _fail(path + ".tag", "SCHEMA", "type tag must be closed, rigid or arrow")
        for use, spec in d["instantiations"].items():
            path = "instantiations." + use
            _keys(spec, {"scheme", "arguments"}, path)
            scheme = _name(spec["scheme"], path + ".scheme", declaration=True)
            if scheme not in d["schemes"]:
                _fail(path + ".scheme", "SCOPE", "instantiation names an undeclared scheme")
            arguments = _list(spec["arguments"], MAX_PARAMETERS, path + ".arguments")
            if len(arguments) != d["schemes"][scheme]["parameters"]:
                _fail(path + ".arguments", "ARITY", "complete ordered parameter vector required, including dead parameters")
            for index, name in enumerate(arguments):
                self.type_id(name, f"{path}.arguments[{index}]")

    def normalize(self, root):
        if type(root) is int:
            return root
        if root in self.normalized:
            return self.normalized[root]
        active = set()
        stack = [(root, False)]
        while stack:
            key, closing = stack.pop()
            if key in self.normalized:
                continue
            path, _, children, spec = self.definitions[key]
            if closing:
                values = tuple(child if type(child) is int else self.normalized[child]
                               for child in children)
                self.normalized[key] = self.intern(
                    ("arrow", values[0], values[1], spec["protocol"], spec["result_identity"]), path)
                active.remove(key)
                continue
            if key in active:
                _fail(path, "TYPE_CYCLE", "callable/type reference cycle cannot normalize into a finite DAG")
            if len(active) >= MAX_TYPE_DEPTH:
                _fail(path, "TYPE_DEPTH", "type reference path exceeds the depth-32 bound")
            active.add(key)
            stack.append((key, True))
            for child in reversed(children):
                if type(child) is not int and child not in self.normalized:
                    stack.append((child, False))
        return self.normalized[root]

    def check_normalized(self):
        d = self.data
        # Intrinsics exist even in an empty declaration set.
        for atom in _INTRINSICS:
            self.references[atom] = self.intern(("closed", atom), "types")
        for layout in sorted(d["layouts"]):
            self.references[layout] = self.intern(("closed", layout), "layouts." + layout)
        for family in sorted(d["families"]):
            self.references["%" + family] = self.intern(("closed", "%" + family), "families." + family)
        for name in sorted(d["types"]):
            self.references["^" + name] = self.normalize(("type", name))
        for name in sorted(d["signatures"]):
            self.references["@" + name] = self.normalize(("signature", name))
        for layout, fields in d["layouts"].items():
            for field, reference in fields.items():
                path = "layouts." + layout + "." + field
                row = self.references[reference]
                if self.scopes[row]:
                    _fail(path, "OPEN_FIELD", "physical DATA fields must be fully closed")
                if self.nodes[row][0] == "arrow" and self.nodes[row][3] != "repeat":
                    _fail(path, "ONCE_FIELD", "shared physical DATA cannot carry a Once callable")
        for scheme, spec in d["schemes"].items():
            path = "schemes." + scheme + ".body"
            body = self.normalized[("type", spec["body"])]
            if self.nodes[body][0] != "arrow":
                _fail(path, "SCHEME_BODY", "rank-1 scheme body must be an arrow")
            if self.scopes[body] - {scheme}:
                _fail(path, "SCOPE", "scheme body contains a foreign rigid variable")
            if not self.generic_atoms[body]:
                _fail(path, "GENERIC_ATOM", "generic body admits only Int, Bool, own rigids and arrows")
            if not self.generic_contracts[body]:
                _fail(path, "GENERIC_CONTRACT", "every generic arrow must be repeat/unknown")
            self.scheme_bodies[scheme] = body
            # The complete neutral vector is retained even for dead parameters.
            for index in range(spec["parameters"]):
                self.intern(("rigid", scheme, index), "schemes." + scheme)
        environments = set()
        for use, spec in d["instantiations"].items():
            path = "instantiations." + use
            vector = tuple(self.normalized[("type", name)] for name in spec["arguments"])
            # A closed tag alone is not an admission rule. Nominal atoms must
            # name these exact checked physical declarations, never an arrow,
            # a structural-layout equivalent, or an unregistered family name.
            if any(self.nodes[row][0] != "closed" or
                   (self.nodes[row][1] not in _INTRINSICS and
                    self.nodes[row][1] not in d["layouts"] and
                    not (self.nodes[row][1].startswith("%") and
                         self.nodes[row][1][1:] in d["families"])) for row in vector):
                _fail(path + ".arguments", "USE_ARGUMENT", "every complete vector entry must name a registered closed intrinsic, DATA or SUM atom")
            key = (spec["scheme"], vector)
            environments.add(key)
            if 1 + len(d["schemes"]) + len(environments) > MAX_ENVIRONMENTS:
                _fail(path, "ENVIRONMENT_COUNT", "concrete, neutral and distinct closed environments exceed 1024")
            self.uses[use] = key
        # At most 1024 environments * 4096 reachable canonical nodes. This is a
        # build-time closure, not a returned or runtime substitution cache.
        for scheme, vector in sorted(environments):
            root = self.scheme_bodies[scheme]
            reachable, pending = set(), [root]
            while pending:
                row = pending.pop()
                if row in reachable:
                    continue
                reachable.add(row)
                if self.nodes[row][0] == "arrow":
                    pending.extend(self.nodes[row][1:3])
            substituted = {}
            for row in sorted(reachable):
                node = self.nodes[row]
                if node[0] == "rigid":
                    result = vector[node[2]]
                elif node[0] == "closed":
                    result = row
                else:
                    result = self.intern(("arrow", substituted[node[1]], substituted[node[2]], node[3], node[4]),
                                         "instantiations[" + _json(scheme) + "]")
                substituted[row] = result
            self.vectors[(scheme, vector)] = substituted[root]

    def finish(self):
        # JSON strings are pre-encoded once. The comparison follows the first
        # unequal DAG child, at most depth32; equal interned subtrees are skipped.
        # It never materializes the exponentially expanded canonical JSON tree.
        scalars = {value: _json(value) for node in self.nodes for value in node if type(value) is str}

        def json_compare(left, right):
            while left != right:
                a, b = self.nodes[left], self.nodes[right]
                if a[0] != b[0]:
                    return -1 if scalars[a[0]] < scalars[b[0]] else 1
                if a[0] == "arrow":
                    if a[1] != b[1]:
                        left, right = a[1], b[1]
                        continue
                    if a[2] != b[2]:
                        left, right = a[2], b[2]
                        continue
                    for index in (3, 4):
                        if a[index] != b[index]:
                            return -1 if scalars[a[index]] < scalars[b[index]] else 1
                else:
                    for x, y in zip(a[1:], b[1:]):
                        if x != y:
                            sx = scalars[x] if type(x) is str else str(x)
                            sy = scalars[y] if type(y) is str else str(y)
                            return -1 if sx < sy else 1
                # Canonical interning makes distinct equal nodes impossible.
                raise AssertionError("internal canonical type interning invariant")
            return 0

        def compare(left, right):
            if self.depths[left] != self.depths[right]:
                return -1 if self.depths[left] < self.depths[right] else 1
            return json_compare(left, right)

        order = sorted(range(len(self.nodes)), key=cmp_to_key(compare))
        ids = {old: new for new, old in enumerate(order)}
        expanded = {}
        for old in order:
            node = self.nodes[old]
            expanded[old] = (("arrow", expanded[node[1]], expanded[node[2]], node[3], node[4])
                             if node[0] == "arrow" else node)
        type_rows = tuple(expanded[old] for old in order)
        schemes, environments = [], []

        def environment(scheme, mode, vector):
            environments.append((("id", "E" + str(len(environments))),
                                 ("scheme", scheme), ("mode", mode),
                                 ("arguments", tuple(expanded[row] for row in vector)),
                                 ("argument_type_ids", tuple(ids[row] for row in vector))))

        environment(None, "CONCRETE", ())
        for scheme in sorted(self.data["schemes"]):
            spec = self.data["schemes"][scheme]
            body = self.scheme_bodies[scheme]
            schemes.append((scheme, (("parameters", spec["parameters"]),
                                     ("body", expanded[body]), ("body_type_id", ids[body]))))
            neutral = tuple(self.node_ids[("rigid", scheme, index)] for index in range(spec["parameters"]))
            environment(scheme, "NEUTRAL", neutral)
            vectors = [vector for owner, vector in self.vectors if owner == scheme]
            for vector in sorted(vectors, key=lambda values: tuple(ids[row] for row in values)):
                environment(scheme, "CLOSED", vector)
        instantiations, uses = [], []
        for use in sorted(self.uses):
            scheme, vector = self.uses[use]
            body = self.vectors[(scheme, vector)]
            arguments = tuple(expanded[row] for row in vector)
            uses.append((use, (scheme, arguments, expanded[body])))
            instantiations.append((use, (("scheme", scheme), ("arguments", arguments),
                                         ("body", expanded[body]), ("body_type_id", ids[body]))))
        return DeclarationIndex(
            self.canonical_json, hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest(),
            type_rows, tuple(environments), tuple(schemes), tuple(instantiations),
            tuple(sorted((reference, ids[row]) for reference, row in self.references.items())),
            tuple(tuple(sorted(self.scopes[old])) for old in order),
            tuple(self.generic_atoms[old] for old in order),
            tuple(self.generic_contracts[old] for old in order),
            tuple(sorted(self.data["schemes"])), tuple(uses))


def check_declarations(data) -> DeclarationIndex:
    """Check the exact six-map declaration schema and return a deep snapshot."""
    copied, canonical = _snapshot(data)
    builder = _Builder(copied, canonical)
    builder.schemas()
    builder.check_normalized()
    return builder.finish()
