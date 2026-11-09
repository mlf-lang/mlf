"""Independent reader of declaration-indexed and legacy query generations."""
import hashlib
import re

from artifact_binary_reference import Invalid, Limits, read_document, require, tree_document
from artifact_binary_typed import list_values, n, pack, text, value_node


V1 = "MLF-CRATE-QUERY-GRAPH-1"
V2 = "MLF-CRATE-QUERY-GRAPH-2"
DIGEST = re.compile(r"[0-9a-f]{64}")
KINDS = {415: ("Input", "Binding"), 416: ("Input", "Prepared"),
         417: ("Input", "ScopeInventory"), 418: ("Scope",), 419: ("InferScc",),
         431: ("FinishScc",), 432: ("Evidence",), 433: ("Datatype",),
         434: ("Input", "Datatype")}


def cache_directory(cache):
    for name in ("query-graph-v2", "query-graph-v1"):
        path = cache / name
        if (path / "CURRENT").is_file():
            return path
    raise Invalid("query generation CURRENT absent")


def index(value):
    require(value[0] == "int" and value[1] >= 0, "invalid table index")
    return value[1]


def lookup(values, ref):
    slot = index(ref)
    require(slot < len(values), "table index out of range")
    return values[slot]


def unique(values, message):
    require(len(values) == len(set(values)), message)
    return values


def digest(value):
    key = text(value)
    require(DIGEST.fullmatch(key), "invalid query digest")
    return key


def packed(fields):
    size = sum(len(field) + len(str(len(field))) + 1 for field in fields)
    require(size <= Limits().work, "identity work limit")
    return pack(fields)


def table(values, message):
    result, seen, remaining = [], set(), Limits().work
    for value in values:
        remaining -= len(value)
        require(remaining >= 0, "identity work limit")
        require(value not in seen, message)
        result.append(value)
        seen.add(value)
    return result


def names(value):
    result = [text(item) for item in list_values(value)]
    require(all(result), "empty table key")
    return table(result, "duplicate table key")


class Generation:
    """Project wire slots into old logical rows; use the generation's own tables."""

    def __init__(self, raw, *, expected_hash=None, configuration=None):
        if expected_hash is not None:
            require(hashlib.sha256(raw).hexdigest() == expected_hash, "generation address")
        doc = read_document(raw, 6)
        roots = doc.values()
        require(len(roots) == 1, "expected one query index")
        root = roots[0]
        require(root[0] == "node" and root[1] in (411, 412), "unknown query generation")
        # Main's dictionary v2 predates the seven-field declaration snapshot.
        # Preserve its independent full-use, hash, UTF-8/work and depth checks.
        self.dictionary_format = root[1] == 412 and len(root[2]) == 4
        if self.dictionary_format:
            from test_query_index import read_index
            fields = value_node(root, 412, 4)
            self.version, self.config = 2, fields[1]
            require(configuration is None or text(self.config) == configuration,
                    "generation configuration")
            records, _ = read_index(raw, text(self.config), expected=expected_hash)
            self.nodes = {k: dict(sha=h, reads=reads, payload=payload)
                          for k, (h, reads, payload) in records.items()}
            self.rows = [n(410, ("text", k), ("text", h),
                           n(1, *(n(2, ("text", target), ("text", observed))
                                  for target, observed in reads)),
                           n(4) if payload is None else n(5, ("text", payload)))
                         for k, (h, reads, payload) in records.items()]
            self.refs = {}
            return
        self.version = 1 if root[1] == 411 else 2
        fields = value_node(root, root[1], 3 if self.version == 1 else 7)
        require(text(fields[0]) == (V1 if self.version == 1 else V2), "generation format")
        self.config = fields[1]
        require(text(self.config) and (configuration is None or text(self.config) == configuration),
                "generation configuration")
        self.tables = fields[2:-1]
        self.refs = {}
        if self.version == 2:
            declarations, members, requests, datatypes = self.tables
            self.declarations = names(declarations)
            self.datatypes = names(datatypes)
            def group_key(group):
                ids = unique([lookup(self.declarations, ref) for ref in list_values(group)],
                             "repeated group member")
                require(ids, "empty query group")
                return packed(ids)
            self.groups = table(map(group_key, list_values(members)), "duplicate group")

            def evidence_key(request):
                group, site, goal = value_node(request, 414, 3)
                require(text(goal), "empty evidence goal")
                return packed([lookup(self.groups, group), str(index(site)), text(goal)])
            self.evidence = table(map(evidence_key, list_values(requests)), "duplicate evidence")

        entries = list_values(fields[-1])
        rows = []
        hashes, descriptors, budget = {}, {}, Limits().work
        for entry in entries:
            key, result, reads, location = value_node(entry, 410 if self.version == 1 else 413, 4)
            logical = self.key(key)
            require(logical not in hashes, "unique query graph keys")
            if self.version == 2:
                budget -= len(logical)
                require(budget >= 0, "identity work limit")
                descriptors[key] = logical
            hashes[logical] = digest(result)
            self.refs[logical] = key
            rows.append((logical, result, list_values(reads), location))

        self.nodes = {}
        self.rows = []
        for key, result, reads, location in rows:
            if self.version == 1:
                edges = [(text(k), digest(h)) for k, h in (value_node(e, 2, 2) for e in reads)]
            else:
                edges = []
                for ref in reads:
                    require(ref[0] == "int" or (ref[0] == "node" and len(ref[2]) == 1 and ref[2][0][0] == "int"),
                            "invalid read descriptor")
                    name = descriptors.get(ref)
                    require(name is not None, "dangling query read")
                    edges.append((name, hashes[name]))
            for name, observed in edges:
                require(hashes.get(name) == observed, "missing/stale dependency")
            require(location[0] == "node" and location[1] in (4, 5), "payload location")
            children = value_node(location, location[1], location[1] - 4)
            address = digest(children[0]) if children else None
            require(address is None or address == hashes[key], "query graph payload matches result hash")
            self.nodes[key] = dict(sha=hashes[key], reads=edges, payload=address)
            self.rows.append(n(410, ("text", key), result,
                               n(1, *(n(2, ("text", k), ("text", h)) for k, h in edges)), location))
        self.check_cycles()

    def key(self, ref):
        if self.version == 1:
            return text(ref)
        if ref[0] == "int":
            return packed(["Binding", lookup(self.declarations, ref)])
        require(ref[0] == "node" and ref[1] in KINDS, "unknown query descriptor")
        kind = KINDS[ref[1]]
        slot, = value_node(ref, ref[1], 1)
        table = (self.declarations if kind[-1] == "Binding" else
                 self.datatypes if kind[-1] == "Datatype" else
                 self.evidence if kind[-1] == "Evidence" else self.groups)
        key = lookup(table, slot)
        for part in reversed(kind):
            key = packed([part, key])
        return key

    def check_cycles(self):
        heights = {}
        for key in self.nodes:
            pending, visiting = [(key, False)], set()
            while pending:
                name, leaving = pending.pop()
                if leaving:
                    visiting.remove(name)
                    height = 1 + max((heights[k] for k, _ in self.nodes[name]["reads"]), default=0)
                    require(height <= 4096, "cyclic/deep query graph")
                    heights[name] = height
                elif name not in heights:
                    require(name not in visiting and len(visiting) < 4096, "cyclic/deep query graph")
                    visiting.add(name)
                    pending.append((name, True))
                    pending.extend((k, False) for k, _ in reversed(self.nodes[name]["reads"]))

    def legacy_bytes(self):
        return tree_document([n(411, ("text", V1), self.config, n(1, *self.rows))], schema=6)

    def encode_rows(self, rows, config=None):
        """Rebuild using this generation's tables (also used to forge corrupt test data)."""
        config = self.config if config is None else config
        if self.version == 1:
            return tree_document([n(411, ("text", V1), config, n(1, *rows))], schema=6)
        if self.dictionary_format:
            logical = []
            for row in rows:
                key, result, reads, payload = value_node(row, 410, 4)
                logical.append((text(key), text(result),
                    [(text(k), text(h)) for k, h in
                     (value_node(edge, 2, 2) for edge in list_values(reads))],
                    None if payload == n(4) else text(value_node(payload, 5, 1)[0])))
            strings = sorted({v for k, h, edges, payload in logical
                              for v in [k, h, *(x for edge in edges for x in edge),
                                        *([] if payload is None else [payload])]})
            ids = {value: i for i, value in enumerate(strings)}
            ref = lambda value: ("int", ids[value])
            encoded = [n(413, ref(k), ref(h), n(1, *(n(2, ref(a), ref(b)) for a, b in edges)),
                         n(4) if payload is None else n(5, ref(payload)))
                       for k, h, edges, payload in sorted(logical)]
            return tree_document([n(412, ("text", V2), config,
                                      n(1, *(("text", value) for value in strings)),
                                      n(1, *encoded))], schema=6)
        encoded = []
        for row in rows:
            key, result, reads, payload = value_node(row, 410, 4)
            refs = []
            for edge in list_values(reads):
                target, _ = value_node(edge, 2, 2)
                # Negative fixtures deliberately encode an unknown target.
                refs.append(self.refs.get(text(target), ("int", len(self.declarations))))
            encoded.append(n(413, self.refs[text(key)], result, n(1, *refs), payload))
        return tree_document([n(412, ("text", V2), config, *self.tables, n(1, *encoded))], schema=6)
