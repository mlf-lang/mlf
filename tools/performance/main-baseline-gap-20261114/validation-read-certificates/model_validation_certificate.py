#!/usr/bin/env python3
"""Bounded synthetic dependency-certificate model; not a Graph.hs translation."""
import json
import signal
from collections import Counter

ABSENT = ("Absent",)
POISON = ("Poison",)

class Fault(Exception):
    pass

class Engine:
    def __init__(self, cells, mutant=None):
        self.cells = dict(cells)
        self.cache = {}
        self.deps = {}
        self.reverse = {}
        self.stack = []
        self.active = set()
        self.count = Counter()
        self.mutant = mutant
        self.bound()

    def bound(self):
        ids = {k[1] for k in self.cells if len(k) == 3}
        assert len(ids) <= 256 and len(self.cells) <= 2048

    def stock(self):
        # Logical current cardinalities, not Python bytes or a peak-memory measurement.
        assert set(self.cache) == set(self.deps)
        edges = {(fact, dep) for fact, deps in self.deps.items() for dep in deps}
        reverse_edges = {(fact, dep) for dep, facts in self.reverse.items() for fact in facts}
        assert edges == reverse_edges
        return dict(cache_facts=len(self.cache), dependency_edges=len(edges),
                    reverse_edges=len(reverse_edges), reverse_buckets=len(self.reverse))

    def dependency(self, dep):
        if self.stack:
            self.stack[-1][1].add(dep)

    def read(self, key, control=False):
        self.count["reads"] += 1
        value = self.cells.get(key, ABSENT)
        if not ((self.mutant == "absent" and value == ABSENT) or
                (self.mutant == "control" and control)):
            self.dependency(("cell", key))
        if value == POISON:
            raise Fault("poison:" + repr(key))
        return value

    def require(self, key, control=False):
        value = self.read(key, control)
        if value == ABSENT:
            raise Fault("missing:" + repr(key))
        return value

    def forget(self, fact):
        self.cache.pop(fact, None)
        for dep in self.deps.pop(fact, ()):
            parents = self.reverse[dep]
            parents.discard(fact)
            if not parents:
                del self.reverse[dep]

    def call(self, fact):
        if fact in self.active:
            raise Fault("cycle:" + repr(fact))
        if fact in self.cache:
            self.count["hits"] += 1
            if self.mutant != "subfact":
                self.dependency(("fact", fact))
            return self.cache[fact]
        self.count["computes"] += 1
        self.active.add(fact)
        self.stack.append((fact, set()))
        try:
            answer = self.compute(fact)
            deps = self.stack[-1][1]
        except BaseException:
            self.stack.pop()
            self.active.remove(fact)
            raise
        self.stack.pop()
        self.active.remove(fact)
        self.cache[fact] = answer
        self.deps[fact] = deps
        self.count["records"] += 1
        for dep in deps:
            self.reverse.setdefault(dep, set()).add(fact)
            self.count["reverse_edges_added"] += 1
        if self.mutant != "subfact":
            self.dependency(("fact", fact))
        return answer

    def compute(self, fact):
        op, n = fact
        if op == "resolve":
            target = self.read(("link", n, "target"))
            return n if target == ABSENT else self.call(("resolve", target))
        if op == "kind":
            r = self.call(("resolve", n))
            tag = self.require(("node", r, "tag"), control=True)
            if tag in ("Gen", "Leaf"):
                return self.require(("node", r, "kind"))
            if tag == "Arrow":
                children = self.require(("node", r, "children"))
                if len(children) != 2:
                    raise Fault("arity")
                # Deliberately ordered, including both child checks before mismatch.
                a = self.call(("kind", children[0]))
                b = self.call(("kind", children[1]))
                if a != "*" or b != "*":
                    raise Fault("arrow-kind")
                return "*"
            raise Fault("tag")
        if op == "binder":
            r = self.call(("resolve", n))
            parent = self.require(("node", r, "binder"))
            if parent is None:
                if self.require(("node", r, "tag"), control=True) != "Gen":
                    raise Fault("root-not-gen")
                return True
            p = self.call(("resolve", parent))
            tag = self.require(("node", p, "tag"), control=True)
            if tag == "Gen":
                return True
            # Toy direct containment, NOT full Graph structural reachability.
            children = self.require(("node", p, "children"))
            for child in children:
                if self.call(("resolve", child)) == r:
                    return True
            raise Fault("binder-containment")
        raise AssertionError("unknown fact")

    def entry(self):
        # Never cache the ordered entry dispatcher or enumerate absent cells.
        members = self.require(("members",))
        roots = self.require(("roots",))
        if len(roots) != 1 or roots[0] not in members:
            raise Fault("root-set")
        for n in members:
            self.call(("binder", n))
            self.call(("kind", n))
        return "Right"

    def writes(self, changes):
        assert not self.stack and not self.active
        todo = []
        for key, value in changes.items():
            self.count["writes"] += 1
            self.cells[key] = value
            todo.extend(self.reverse.get(("cell", key), ()))
        seen = set()
        while todo:
            fact = todo.pop()
            self.count["invalidation_visits"] += 1
            if fact in seen:
                continue
            seen.add(fact)
            todo.extend(self.reverse.get(("fact", fact), ()))
        for fact in seen:
            self.forget(fact)
        self.count["invalidated"] += len(seen)
        self.bound()

def outcome(engine):
    try:
        return engine.entry()
    except Fault as exc:
        return "Left:" + str(exc)

def graph():
    c = {("members",): (0, 1, 2, 3), ("roots",): (0,)}
    for n in range(4):
        c[("node", n, "tag")] = "Gen" if n == 0 else "Leaf"
        c[("node", n, "kind")] = "*"
        c[("node", n, "binder")] = None if n == 0 else 0
    c[("node", 1, "tag")] = "Arrow"
    c[("node", 1, "children")] = (2, 3)
    return c

def balanced_graph():
    # 63-node perfect binary tree plus Gen0: 64 synthetic nodes, not a real MLF graph.
    c = {("members",): tuple(range(64)), ("roots",): (0,)}
    for n in range(64):
        c[("node", n, "binder")] = None if n == 0 else 0
        if n == 0 or n >= 32:
            c[("node", n, "tag")] = "Gen" if n == 0 else "Leaf"
            c[("node", n, "kind")] = "*"
        else:
            c[("node", n, "tag")] = "Arrow"
            c[("node", n, "children")] = (2 * n, 2 * n + 1)
    return c

def run_tests():
    reports = []
    cases = 0
    def compare(label, changes, expected, initial=None, mutant=None):
        nonlocal cases
        cases += 1
        assert cases <= 4096
        e = Engine(graph() if initial is None else initial, mutant)
        cold = outcome(e)
        assert cold == "Right", (label, cold)
        cold_counts = dict(e.count)
        cold_stock = e.stock()
        e.count.clear()
        e.writes(changes)
        transition = dict(e.count)
        transition_stock = e.stock()
        e.count.clear()
        warm = outcome(e)
        warm_stock = e.stock()
        fresh_engine = Engine(e.cells)
        fresh = outcome(fresh_engine)
        fresh_counts = dict(fresh_engine.count)
        fresh_stock = fresh_engine.stock()
        if mutant:
            assert warm != fresh, (label, "mutant escaped", warm, fresh)
        else:
            assert warm == fresh == expected, (label, warm, fresh, expected)
        reports.append(dict(case=label, cold=cold_counts, transition=transition,
                            warm=dict(e.count), outcome=warm, fresh=fresh,
                            fresh_counts=fresh_counts, cold_stock=cold_stock,
                            transition_stock=transition_stock, warm_stock=warm_stock,
                            fresh_stock=fresh_stock, mutant_caught=bool(mutant)))
        return e

    compare("unchanged", {}, "Right")
    assert reports[-1]["warm"].get("computes", 0) == 0
    assert reports[-1]["warm_stock"] == reports[-1]["cold_stock"]
    compare("balanced-single-leaf-kind-write", {("node", 63, "kind"): "K"},
            "Left:arrow-kind", balanced_graph())

    compare("child-kind", {("node", 2, "kind"): "K"}, "Left:arrow-kind")
    compare("absent-link-becomes-present",
            {("link", 2, "target"): 3, ("node", 3, "kind"): "K"}, "Left:arrow-kind")
    base = graph()
    base[("link", 2, "target")] = 3
    compare("alias-chain-change", {("link", 3, "target"): 2},
            "Left:cycle:('resolve', 2)", base)
    compare("gen-control-branch", {("node", 0, "tag"): "Leaf"},
            "Left:root-not-gen")
    compare("delete-node", {("node", 2, "tag"): ABSENT},
            "Left:missing:('node', 2, 'tag')")
    compare("root-set-change", {("roots",): ()}, "Left:root-set")
    compare("earlier-error-hides-poison",
            {("node", 0, "tag"): "Leaf", ("node", 3, "kind"): POISON},
            "Left:root-not-gen")
    e = Engine(graph())
    e.writes({("node", 2, "kind"): "K"})
    assert outcome(e) == "Left:arrow-kind"
    assert ("kind", 1) not in e.cache
    e.writes({("node", 2, "kind"): "*"})
    assert outcome(e) == "Right"
    reports.append(dict(case="failed-fact-not-cached-and-repaired", counts=dict(e.count)))
    cases += 1
    e = compare("dependency-rebuild-alias", {("link", 2, "target"): 3}, "Right")
    assert ("resolve", 2) in e.reverse[("fact", ("resolve", 3))]
    e.writes({("link", 2, "target"): ABSENT})
    assert ("resolve", 2) not in e.reverse.get(("fact", ("resolve", 3)), set())
    assert outcome(e) == "Right"
    assert ("fact", ("resolve", 3)) not in e.deps[("resolve", 2)]
    assert ("resolve", 2) not in e.reverse.get(("fact", ("resolve", 3)), set())
    e.stock()
    e.writes({("node", 2, "kind"): "K"})
    assert outcome(e) == "Left:arrow-kind"
    reports.append(dict(case="dependency-rebuilt-after-redirect", counts=dict(e.count)))
    cases += 1
    # Force a complete invalidation using the full explicit cell-write set.
    all_cells = graph()
    all_cells.update({("link", n, "target"): ABSENT for n in range(4)})
    e = compare("all-fields-written-worst-case", all_cells, "Right")
    assert reports[-1]["transition"]["invalidated"] == reports[-1]["cold"]["records"]

    compare("mutant-missing-subfact", {("node", 2, "kind"): "K"}, None,
            mutant="subfact")
    # A new link changes a formerly successful kind without touching other fields.
    base = graph()
    base[("members",)] = (0, 1, 2)
    base[("node", 1, "children")] = (2, 2)
    base[("node", 3, "kind")] = "K"  # Present but previously unvisited.
    compare("mutant-missing-absent", {("link", 2, "target"): 3}, None,
            base, "absent")
    # Root tag is also read by kind, so isolate the binder fact to expose control omission.
    e = Engine(graph(), "control")
    assert e.call(("binder", 2)) is True
    e.writes({("node", 0, "tag"): "Arrow", ("node", 0, "children"): ()})
    assert e.call(("binder", 2)) is True
    f = Engine(e.cells)
    try:
        f.call(("binder", 2))
    except Fault as exc:
        assert str(exc) == "binder-containment"
    else:
        raise AssertionError("control mutant escaped")
    reports.append(dict(case="mutant-missing-control", mutant_caught=True,
                        counts=dict(e.count)))
    cases += 1
    # Cyclic structural fact is not published; repair permits a new successful record.
    e = Engine(graph())
    e.writes({("node", 1, "children"): (1, 3)})
    assert outcome(e) == "Left:cycle:('kind', 1)"
    assert ("kind", 1) not in e.cache
    e.writes({("node", 1, "children"): (2, 3)})
    assert outcome(e) == "Right"
    reports.append(dict(case="structural-cycle-and-repair", counts=dict(e.count)))
    cases += 1
    return dict(status="PASS_SYNTHETIC_MODEL_ONLY", cases=cases, reports=reports,
                production_equivalence=False, timing_or_benefit_claim=False)

def main():
    def timeout(signum, frame):
        raise TimeoutError("30-second model limit")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(30)
    try:
        result = run_tests()
        print(json.dumps(result, sort_keys=True))
    finally:
        signal.alarm(0)

if __name__ == "__main__":
    main()
