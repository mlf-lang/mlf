"""Independent reader of current declaration-indexed query generations."""
import hashlib
import re

from artifact_binary_reference import Invalid, Limits, read_document, require, tree_document
from artifact_binary_typed import list_values, n, pack, text, value_node


CACHE_DIRECTORY = "query-graph-v3"
V3 = "MLF-CRATE-QUERY-GRAPH-3"
CONSTANTS = {435: ("Input", "EmptyScopeInventory"), 436: ("EmptyScope",)}
DIGEST = re.compile(r"[0-9a-f]{64}")
KINDS = {415: ("Input", "Binding"), 416: ("Input", "Prepared"),
         417: ("Input", "ScopeInventory"), 418: ("Scope",), 419: ("InferScc",),
         431: ("FinishScc",), 432: ("Evidence",), 433: ("Datatype",),
         434: ("Input", "Datatype")}


def cache_directory(cache):
    path = cache / CACHE_DIRECTORY
    require((path / "CURRENT").is_file(), "query generation CURRENT absent")
    return path


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
    """Resolve each descriptor and its observed hash in this generation's tables."""

    def __init__(self, raw, *, expected_hash=None, configuration=None):
        if expected_hash is not None:
            require(hashlib.sha256(raw).hexdigest() == expected_hash, "generation address")
        doc = read_document(raw, 6)
        roots = doc.values()
        require(len(roots) == 1, "expected one query index")
        root = roots[0]
        fields = value_node(root, 412, 11)
        require(text(fields[0]) == V3, "generation format")
        self.version = 3
        self.config = fields[1]
        require(text(self.config) and (configuration is None or text(self.config) == configuration),
                "generation configuration")
        self.tables = fields[2:6]
        self.refs = {}
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

        keys, results, lengths, targets, locations = map(list_values, fields[6:])
        require(len(keys) == len(results) == len(lengths), "query column lengths")
        payloads = [index(value) for value in locations]
        require(payloads == sorted(set(payloads)), "query payload row order")
        require(all(row < len(keys) for row in payloads), "query payload row range")
        payloads = set(payloads)
        hashes, descriptors, budget = {}, {}, Limits().work
        for key, result in zip(keys, results):
            logical = self.key(key)
            require(logical not in hashes, "unique query graph keys")
            budget -= len(logical)
            require(budget >= 0, "identity work limit")
            descriptors[key] = logical
            hashes[logical] = digest(result)
            self.refs[logical] = key

        self.nodes, self.rows = {}, []
        cursor = 0
        for row, (key, result, length) in enumerate(zip(keys, results, lengths)):
            logical = descriptors[key]
            count = index(length)
            require(count <= len(targets) - cursor, "query read column length")
            edges = []
            for target in targets[cursor:cursor + count]:
                require(target in descriptors, "dangling query read")
                name = descriptors[target]
                edges.append((name, hashes[name]))
            cursor += count
            address = hashes[logical] if row in payloads else None
            self.nodes[logical] = dict(sha=hashes[logical], reads=edges, payload=address)
            self.rows.append(n(410, ("text", logical), result,
                               n(1, *(n(2, ("text", k), ("text", h)) for k, h in edges)),
                               n(5, result) if row in payloads else n(4)))
        require(cursor == len(targets), "query read column trailing targets")
        self.check_cycles()

    def key(self, ref):
        if ref[0] == "int":
            return packed(["Binding", lookup(self.declarations, ref)])
        if ref[0] == "node" and ref[1] in CONSTANTS:
            value_node(ref, ref[1], 0)
            key = ""
            for part in reversed(CONSTANTS[ref[1]]):
                key = packed([part, key])
            return key
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
        done, visiting = set(), set()
        for root in self.nodes:
            if root in done:
                continue
            visiting.add(root)
            stack = [(root, iter(self.nodes[root]["reads"]))]
            while stack:
                key, reads = stack[-1]
                dependency = next(reads, None)
                if dependency is None:
                    stack.pop()
                    visiting.remove(key)
                    done.add(key)
                    continue
                child, _ = dependency
                require(child not in visiting, "cyclic query graph")
                if child not in done:
                    visiting.add(child)
                    stack.append((child, iter(self.nodes[child]["reads"])))

    def encode_rows(self, rows, config=None):
        """Rebuild with this generation's tables, including intentionally dangling test edges."""
        config = self.config if config is None else config
        keys, results, counts, targets, locations = [], [], [], [], []
        for ordinal, row in enumerate(rows):
            key, result, reads, payload = value_node(row, 410, 4)
            edges = list_values(reads)
            keys.append(self.refs[text(key)])
            results.append(result)
            counts.append(("int", len(edges)))
            for edge in edges:
                target, _ = value_node(edge, 2, 2)
                targets.append(self.refs.get(text(target), ("int", len(self.declarations))))
            if payload != n(4):
                require(value_node(payload, 5, 1)[0] == result, "query graph payload matches result hash")
                locations.append(("int", ordinal))
        columns = [keys, results, counts, targets, locations]
        return tree_document([n(412, ("text", V3), config, *self.tables,
                               *(n(1, *column) for column in columns))], schema=6)
