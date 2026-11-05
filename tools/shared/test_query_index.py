#!/usr/bin/env python3
"""Independent v1/v2 QueryGraph schema/closure oracle over the frozen wire reader.

Run with tools/shared on PYTHONPATH when this file lives in an overlay.
No production implementation imports and no native compiler execution.
An optional --index FILE --configuration TEXT checks an actual generation.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import unittest
from artifact_binary_reference import read_document, tree_document, Invalid, require

M64 = 64 * 1024**2
M256 = 256 * 1024**2
H1, H2 = "a" * 64, "b" * 64
MARKER = "MLF-CRATE-QUERY-GRAPH-2"

def node(tag, *children):
    return ("node", tag, tuple(children))

def text(value):
    return ("text", value)

def integer(value):
    return ("int", value)

def listing(values):
    return node(1, *values)

def fields(value, tag, arity=None):
    require(type(value) is tuple and len(value) == 3 and value[0] == "node"
            and value[1] == tag, "constructor")
    require(arity is None or len(value[2]) == arity, "arity")
    return value[2]

def scalar(value, kind):
    require(type(value) is tuple and len(value) == 2 and value[0] == kind, kind)
    return value[1]

def row(k, h, reads=(), location=None):
    return node(413, integer(k), integer(h),
                listing(node(2, integer(a), integer(b)) for a, b in reads),
                node(4) if location is None else node(5, integer(location)))

def index(strings, rows, configuration="config"):
    return node(412, text(MARKER), text(configuration), listing(map(text, strings)), listing(rows))

def binary(value):
    return tree_document([value], schema=6)

def read_index(raw, configuration, *, node_limit=M64, total_limit=M256, expected=None):
    if expected is not None:
        require(hashlib.sha256(raw).hexdigest() == expected, "SHA256")
    document = read_document(raw, 6)
    values = document.values()
    require(len(values) == 1, "root count")
    value = values[0]
    if value[1] == 411:
        marker, config, entries = fields(value, 411, 3)
        require(scalar(marker, "text") == "MLF-CRATE-QUERY-GRAPH-1"
                and scalar(config, "text") == configuration, "version/config")
        result = {}
        for item in fields(entries, 1):
            k, h, reads, location = fields(item, 410, 4)
            key, digest = scalar(k, "text"), scalar(h, "text")
            edges = [(scalar(a, "text"), scalar(b, "text"))
                     for a, b in (fields(pair, 2, 2) for pair in fields(reads, 1))]
            loc = None if location == node(4) else scalar(fields(location, 5, 1)[0], "text")
            require(key not in result, "duplicate")
            require(all(re.fullmatch("[0-9a-f]{64}", s) for s in
                        [digest] + [h for _, h in edges] + ([] if loc is None else [loc])), "hash")
            result[key] = (digest, edges, loc)
        # Preserve the old wire limit and verify ordinary legacy closure.
        for digest, edges, loc in result.values():
            for k, h in edges:
                require(k in result and result[k][0] == h, "closure")
        # Match the v1 reader's historical completed-before-depth traversal,
        # including its dependency-first shortcut. Do not impose v2 semantics.
        done, visiting = set(), set()
        for root in sorted(result):
            stack = [(root, 0, False)]
            while stack:
                key, depth, exiting = stack.pop()
                if exiting:
                    visiting.remove(key)
                    done.add(key)
                elif key not in done:
                    require(depth < 4096 and key not in visiting, "legacy cycle/depth")
                    visiting.add(key)
                    stack.append((key, depth, True))
                    stack.extend((dependency, depth+1, False)
                                 for dependency, _ in reversed(result[key][1]))
        return result, document.accounting()

    marker, config, dictionary, entries = fields(value, 412, 4)
    require(scalar(marker, "text") == MARKER and scalar(config, "text") == configuration, "version/config")
    strings = [scalar(item, "text") for item in fields(dictionary, 1)]
    require(all(a < b for a, b in zip(strings, strings[1:])), "dictionary canonicality")
    sizes = [len(s.encode("utf-8")) for s in strings]
    hashes = [bool(re.fullmatch("[0-9a-f]{64}", s)) for s in strings]
    used, records = set(), {}
    previous = -1
    projected = 4 + len(MARKER.encode()) + len(configuration.encode())
    require(projected <= total_limit, "total referenced work")

    def ref(value, is_hash=False):
        number = scalar(value, "int")
        require(type(number) is int and 0 <= number < len(strings), "ID range")
        require(not is_hash or hashes[number], "hash")
        used.add(number)
        return number

    for item in fields(entries, 1):
        key, digest, reads, location = fields(item, 413, 4)
        k, h = ref(key), ref(digest, True)
        require(k > previous, "row canonicality")
        previous = k
        edges = [(ref(a), ref(b, True))
                 for a, b in (fields(pair, 2, 2) for pair in fields(reads, 1))]
        loc = None if location == node(4) else ref(fields(location, 5, 1)[0], True)
        work = 5 + sizes[k] + sizes[h]
        work += sum(3 + sizes[a] + sizes[b] for a, b in edges)
        if loc is not None:
            work += 1 + sizes[loc]
        require(work <= node_limit, "node referenced work")
        projected += work
        require(projected <= total_limit, "total referenced work")
        records[k] = (h, edges, loc)
    require(len(used) == len(strings), "unused dictionary")
    for h, edges, loc in records.values():
        for k, expected_hash in edges:
            require(k in records, "missing dependency")
            require(expected_hash == records[k][0], "stale dependency")

    # Independent iterative longest-path calculation, with an active DFS set.
    heights, visiting = {}, set()
    for root in records:
        stack = [(root, False)]
        while stack:
            k, exiting = stack.pop()
            if k in heights:
                continue
            if exiting:
                height = 1 + max((heights[d] for d, _ in records[k][1]), default=0)
                require(height <= 4096, "depth")
                heights[k] = height
                visiting.remove(k)
            else:
                require(k not in visiting, "cycle")
                visiting.add(k)
                require(len(visiting) <= 4096, "depth")
                stack.append((k, True))
                stack.extend((d, False) for d, _ in reversed(records[k][1]) if d not in heights)
    result = {strings[k]: (strings[h], [(strings[d], strings[e]) for d, e in edges],
                           None if loc is None else strings[loc])
              for k, (h, edges, loc) in records.items()}
    return result, dict(document.accounting(), projected_inline_work=projected)

class QueryIndexTests(unittest.TestCase):
    def setUp(self):
        self.strings = [H1, H2, "leaf", "root"]
        self.rows = [row(2, 0), row(3, 1, [(2, 0), (2, 0)], 0)]
        self.value = index(self.strings, self.rows)

    def read(self, value=None, **kw):
        return read_index(binary(self.value if value is None else value), "config", **kw)

    def bad(self, value, **kw):
        with self.assertRaises(Invalid):
            self.read(value, **kw)

    def test_exact_fields_and_wire_hash(self):
        raw = binary(self.value)
        actual, stats = read_index(raw, "config", expected=hashlib.sha256(raw).hexdigest())
        self.assertEqual(actual, {"leaf": (H1, [], None), "root": (H2, [("leaf", H1)] * 2, H1)})
        self.assertEqual(stats["projected_inline_work"], 386)
        with self.assertRaises(Invalid):
            read_index(raw, "config", expected=H1)
        damaged = bytearray(raw)
        damaged[76] ^= 1
        with self.assertRaises(Invalid):
            read_index(bytes(damaged), "config")

    def test_legacy_and_empty(self):
        old = node(411, text("MLF-CRATE-QUERY-GRAPH-1"), text("config"), listing([
            node(410, text("leaf"), text(H1), listing([]), node(4)),
            node(410, text("root"), text(H2), listing([node(2, text("leaf"), text(H1))]*2), node(5, text(H1)))]))
        self.assertEqual(self.read(old)[0], self.read()[0])
        self.assertEqual(self.read(index([], []))[0], {})
        cyclic = node(411, text("MLF-CRATE-QUERY-GRAPH-1"), text("config"), listing([
            node(410, text("leaf"), text(H1), listing([node(2, text("leaf"), text(H1))]), node(4))]))
        self.bad(cyclic)
        for dependency_first in [False, True]:
            records = []
            for i in range(4097):
                leaf = i == (0 if dependency_first else 4096)
                dependency = i-1 if dependency_first else i+1
                reads = [] if leaf else [node(2, text("chain/%05d" % dependency), text(H1))]
                records.append(node(410, text("chain/%05d" % i), text(H1), listing(reads), node(4)))
            deep = node(411, text("MLF-CRATE-QUERY-GRAPH-1"), text("config"), listing(records))
            if dependency_first:
                self.assertEqual(len(self.read(deep)[0]), 4097)
            else:
                self.bad(deep)

    def test_types_ranges_and_hashes(self):
        for wrong in [-1, 4, (1 << 63)-1]:
            self.bad(index(self.strings, [row(2, wrong), self.rows[1]]))
        for wrong in [("bits", 0), text("0"), node(1)]:
            fields0 = list(self.rows[0][2])
            fields0[1] = wrong
            self.bad(index(self.strings, [node(413, *fields0), self.rows[1]]))
        for records in [[row(2, 2), self.rows[1]],
                        [self.rows[0], row(3, 1, [(2, 2)], 0)],
                        [self.rows[0], row(3, 1, [(2, 0)], 2)],
                        [self.rows[0], row(3, 1, [(-1, 0)], 0)],
                        [self.rows[0], row(3, 1, [(2, 4)], 0)]]:
            self.bad(index(self.strings, records))

    def test_canonicality_and_closure(self):
        for strings in [[H1, H1, "leaf", "root"], [H2, H1, "leaf", "root"], self.strings + ["unused"]]:
            self.bad(index(strings, self.rows))
        for records in [self.rows[::-1], [self.rows[0]] + self.rows, [self.rows[1]],
                        [self.rows[0], row(3, 1, [(2, 1)], 0)],
                        [row(2, 0, [(3, 1)]), self.rows[1]],
                        [self.rows[0], row(3, 1, [(3, 1)], 0)]]:
            self.bad(index(self.strings, records))

    def test_small_exact_budgets(self):
        self.read(node_limit=280, total_limit=386)
        self.bad(self.value, node_limit=279, total_limit=386)
        self.bad(self.value, node_limit=280, total_limit=385)
        self.read(index([], []), node_limit=0, total_limit=33)
        self.bad(index([], []), node_limit=0, total_limit=32)
        unicode_value = index([H1, "λ😀"], [row(1, 0)])
        self.read(unicode_value, node_limit=75, total_limit=108)
        self.bad(unicode_value, node_limit=74, total_limit=108)

    def test_actual_row_64_mi_boundary_tiny_wire(self):
        def value(length):
            return index([H1, "r"*length, "z"*32700],
                         [row(1, 0, [(2, 0)]*2048), row(2, 0)])
        self.assertLess(len(binary(value(1979))), 100000)
        actual, _ = self.read(value(1979))
        self.assertEqual(len(actual["r"*1979][1]), 2048)
        self.bad(value(1980))

    def test_actual_total_256_mi_boundary_tiny_wire(self):
        def value(extra):
            strings = [H1, "b"*1979, "c"*1979, "d"*1979, "e"*(1944+extra), "z"*32700]
            return index(strings, [row(i, 0, [(5,0)]*(2047 if i == 4 else 2048))
                                   for i in range(1,5)] + [row(5,0)])
        actual, stats = self.read(value(0))
        self.assertEqual(stats["projected_inline_work"], M256)
        self.assertLess(len(binary(value(0))), 100000)
        self.bad(value(1))

    def test_alternating_long_prefix_attack(self):
        def key(identity):
            return "7:Compute" + str(len(identity)) + ":" + identity
        keys = [key("q"*512+"a"), key("q"*512+"b"), key("root")]
        strings = sorted([H1, *keys])
        a, b, r = [strings.index(k) for k in keys]
        h = strings.index(H1)
        rows = [row(a,h), row(b,h), row(r,h, [(a,h),(b,h)]*16)]
        rows.sort(key=lambda value: value[2][0][1])
        value = index(strings, rows)
        self.bad(value, node_limit=1024, total_limit=65536)

    def test_depth_both_key_orders(self):
        for dependency_first in [False, True]:
            for count in [4096,4097]:
                strings = [H1] + ["chain/%05d" % i for i in range(count)]
                rows = []
                for i in range(count):
                    leaf = i == (0 if dependency_first else count-1)
                    dependency = i-1 if dependency_first else i+1
                    rows.append(row(i+1,0, [] if leaf else [(dependency+1,0)]))
                value = index(strings, rows)
                if count == 4096:
                    self.assertEqual(len(self.read(value)[0]), count)
                else:
                    self.bad(value)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path)
    parser.add_argument("--configuration", default="config")
    args, rest = parser.parse_known_args()
    if args.index:
        raw = args.index.read_bytes()
        nodes, stats = read_index(raw, args.configuration, expected=args.index.stem)
        print(json.dumps(dict(stats, query_nodes=len(nodes)), sort_keys=True))
    else:
        unittest.main(argv=[__file__, *rest])
