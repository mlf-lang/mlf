#!/usr/bin/env python3
"""Finite symbolic write/origin protocol, NOT a translation of Graph.hs.
No target/model code was executed while preparing this source.
"""
import json
from dataclasses import dataclass
from types import MappingProxyType

SCHEMA = "synthetic-validation-write-origin-model-v1"
MISSING = object()
FIELDS = ("tag", "children", "kind", "name", "binder", "flag")
GLOBAL = ("binding-global", 0)
MUTANTS = ("none", "omit-alias", "omit-global-binding", "same-id", "node-pointer")


class Invalid(Exception):
    """An ordered failure of a toy validation rule."""


class Denied(Exception):
    """Protocol failure; transaction becomes unpublishable."""


class PoisonFault(Exception):
    pass


class Poison:
    """Only an explicit semantic force may inspect this symbolic payload."""
    def __init__(self):
        self.touches = 0

    def force(self):
        self.touches += 1
        raise PoisonFault("forced payload")

    def __eq__(self, other):
        self.touches += 1
        raise PoisonFault("payload equality forbidden")

    def __repr__(self):
        self.touches += 1
        raise PoisonFault("payload repr forbidden")

    def __str__(self):
        self.touches += 1
        raise PoisonFault("payload str forbidden")


@dataclass(frozen=True, eq=False)
class Token:
    epoch: object
    serial: int


@dataclass(frozen=True, eq=False)
class Cell:
    token: Token
    value: object


@dataclass(frozen=True, eq=False)
class Snapshot:
    epoch: object
    mode: str
    cells: object


@dataclass(frozen=True, eq=False)
class Fact:
    key: tuple
    direct: tuple
    subfacts: tuple
    value: object
    pointers: tuple


def node(tag="leaf", children=(), kind="Star", name=None, binder=None, flag="Flexible"):
    return dict(tag=tag, children=children, kind=kind, name=name, binder=binder, flag=flag)


class Transaction:
    """Single owner namespace, immutable snapshots, explicit trusted write surface.

    Python privacy is conventional, not a security boundary. Callers may not
    forge Cells/Snapshots or mutate cells behind this surface.
    """
    def __init__(self):
        self.epoch = object()
        self.serial = 0
        self.absent = {}
        self.log = []
        self.read_depth = 0
        self.aborted = False
        self.published = None

    def reject(self, reason):
        self.aborted = True
        raise Denied(reason)

    def ensure(self, state):
        if self.aborted or self.published is not None:
            self.reject("transaction closed")
        if state.epoch is not self.epoch:
            self.reject("foreign epoch")
        if state.mode != "symbolic":
            self.reject("unknown mode")

    def fresh(self, value):
        self.serial += 1
        return Cell(Token(self.epoch, self.serial), value)

    def cell(self, state, key):
        cell = state.cells.get(key)
        if cell is not None:
            return cell
        # Absent lookup gets a stable private origin, without inspecting payloads.
        if key not in self.absent:
            self.absent[key] = self.fresh(MISSING)
        return self.absent[key]

    def write(self, state, operation, assigned=(), copied=(), erased=()):
        self.ensure(state)
        if self.read_depth:
            self.reject("write during rule")
        if operation not in ("assign", "merge", "canonicalize", "dense-final",
                             "sparse-rebuild", "add-node", "remove-alias"):
            self.reject("unknown write")
        assigned, copied, erased = tuple(assigned), tuple(copied), tuple(erased)
        keys = [k for k, _ in assigned] + [k for k, _ in copied] + list(erased)
        if len(keys) != len(set(keys)):
            self.reject("overlapping writes")
        for key in keys:
            if (type(key) is not tuple or len(key) != 2 or type(key[1]) is not int
                    or key[0] not in FIELDS + ("node", "alias")):
                self.reject("unknown field")
        cells = dict(state.cells)
        for key, value in assigned:
            old = self.cell(state, key)
            cells[key] = self.fresh(value)  # Always new, even the identical value/object.
            self.log.append((operation, key, old.token, cells[key].token, "assign"))
        for target, source in copied:
            if (type(source) is not tuple or len(source) != 2 or type(source[1]) is not int
                    or target[0] != source[0]):
                self.reject("copy requires same selector")
            old_target = self.cell(state, target)
            origin = self.cell(state, source)
            cells[target] = origin  # Explicit field copy may transport between IDs.
            self.log.append((operation, target, old_target.token, origin.token, "copy"))
        for key in erased:
            old = self.cell(state, key)
            cells[key] = self.fresh(MISSING)  # Tombstone is a NEW absence version.
            self.log.append((operation, key, old.token, cells[key].token, "erase"))
        # Coarse coverage for all binder/Euler/edge-dependent reads. No value tests.
        changed = keys
        if any(k[0] in ("binder", "alias", "children", "tag", "node") for k in changed):
            old = self.cell(state, GLOBAL)
            cells[GLOBAL] = self.fresh(None)
            self.log.append((operation, GLOBAL, old.token, cells[GLOBAL].token, "global"))
        return Snapshot(self.epoch, state.mode, MappingProxyType(cells))

    def create(self, specs, aliases=()):
        if self.aborted or self.published is not None or self.read_depth:
            self.reject("create in closed/active transaction")
        if len(specs) > 16:
            self.reject("model node cap")
        cells = {GLOBAL: self.fresh(None)}
        for identity, spec in specs.items():
            if type(identity) is not int or set(spec) != set(FIELDS):
                self.reject("bad node specification")
            cells[("node", identity)] = self.fresh(object())
            for field in FIELDS:
                cells[(field, identity)] = self.fresh(spec[field])
        for identity, target in aliases:
            if type(identity) is not int or type(target) is not int:
                self.reject("bad alias specification")
            cells[("alias", identity)] = self.fresh(target)
        return Snapshot(self.epoch, "symbolic", MappingProxyType(cells))

    def clone(self, state):
        self.ensure(state)
        return Snapshot(self.epoch, state.mode, MappingProxyType(dict(state.cells)))

    def assign(self, state, identity, field, value):
        if field not in FIELDS + ("alias",):
            self.reject("unknown field")
        updates = [((field, identity), value)]
        if field != "alias":
            updates.append((("node", identity), object()))
        return self.write(state, "assign", assigned=updates)

    def merge(self, state, a, b, tag_source=None):
        # Total illustrative chosen writes, NOT tagEquations or full unification.
        # The ordered first argument owns binder/flag; winner is numeric min.
        winner, loser = min(a, b), max(a, b)
        if a == b:
            self.reject("toy merge expects distinct IDs")
        if tag_source is None:
            tag_source = a
        if tag_source not in (a, b):
            self.reject("unknown tag selection")
        tag = self.cell(state, ("tag", tag_source)).value
        return self.write(state, "merge",
                          assigned=((("tag", winner), tag), (("node", winner), object()),
                                    (("alias", loser), winner)),
                          copied=tuple(((f, winner), (f, tag_source))
                                       for f in ("children", "kind", "name")) +
                                 tuple(((f, winner), (f, a)) for f in ("binder", "flag")),
                          erased=tuple((f, loser) for f in ("node",) + FIELDS))

    def canonicalize(self, state, identity, mapped_children=None):
        # Constructor expression is rebuilt even for leaves. Payload cells copy.
        ctor = self.cell(state, ("tag", identity)).value
        updates = [(("tag", identity), ctor), (("node", identity), object())]
        preserve = list(f for f in FIELDS if f != "tag")
        if mapped_children is not None:
            updates.append((("children", identity), mapped_children))
            preserve.remove("children")
        return self.write(state, "canonicalize", assigned=updates,
                          copied=tuple(((f, identity), (f, identity)) for f in preserve))

    def dense_final(self, state, identity, parent, flag):
        self.ensure(state)
        old_parent = self.cell(state, ("binder", identity)).value
        old_flag = self.cell(state, ("flag", identity)).value
        # Only this deliberately total toy control domain is compared.
        if not (old_parent is None or type(old_parent) is int):
            self.reject("non-total binder control")
        if not (parent is None or type(parent) is int):
            self.reject("non-total binder control")
        if type(old_flag) is not str or type(flag) is not str:
            self.reject("non-total flag control")
        if old_parent == parent and old_flag == flag:
            return state  # CURRENT skeleton, never an earlier graph with the same ID.
        return self.rebuild_fields(state, identity, parent, flag, "dense-final")

    def rebuild_fields(self, state, identity, parent, flag, operation="sparse-rebuild"):
        return self.write(state, operation,
                          assigned=((("binder", identity), parent), (("flag", identity), flag),
                                    (("node", identity), object())),
                          copied=tuple(((f, identity), (f, identity))
                                       for f in ("tag", "children", "kind", "name")))

    def switch_mode(self, state, mode):
        self.ensure(state)
        self.reject("mode switch unsupported")

    def publish_checked(self, engine, state, root, children):
        # Still run ordered entry checks. No successful partial fact is a commit.
        self.ensure(state)
        try:
            engine.validate_ordered(state, root, children)
        except (Invalid, PoisonFault, Denied):
            self.aborted = True
            raise
        self.published = state
        return "published"


class Engine:
    def __init__(self, transaction, mutant="none"):
        if mutant not in MUTANTS:
            raise ValueError("unknown mutant")
        self.tx = transaction
        self.mutant = mutant
        self.cache = {}
        self.frames = []
        self.active = set()

    def read(self, state, key):
        cell = self.tx.cell(state, key)
        omit = ((self.mutant == "omit-alias" and key[0] == "alias") or
                (self.mutant == "omit-global-binding" and key == GLOBAL))
        if not omit:
            self.frames[-1][0][key] = cell.token
        return cell.value

    def valid(self, state, fact):
        if self.mutant == "same-id":
            return True  # Deliberate unsound rule+numeric-ID identity.
        if self.mutant == "node-pointer" and fact.key[0] == "edge":
            return all(self.tx.cell(state, k).token is t for k, t in fact.pointers)
        return (all(self.tx.cell(state, k).token is t for k, t in fact.direct)
                and all(self.valid(state, child) for child in fact.subfacts))

    def query(self, state, rule, *args):
        self.tx.ensure(state)
        if rule not in ("exists", "resolve", "tag", "kind", "euler", "edge"):
            self.tx.reject("unknown rule")
        if any(type(a) is not int for a in args):
            self.tx.reject("non-integer rule parameter")
        arity = 2 if rule == "edge" else 1
        if len(args) != arity:
            self.tx.reject("rule arity")
        key = (rule, args)
        fact = self.cache.get(key)
        if fact is None or not self.valid(state, fact):
            if key in self.active:
                raise Invalid("cycle")
            if len(self.cache) >= 128:
                self.tx.reject("model fact cap")
            self.active.add(key)
            self.frames.append(({}, []))
            self.tx.read_depth += 1
            try:
                value = self.compute(state, rule, args)
                direct, subs = self.frames[-1]
                pointers = tuple((("node", n), self.tx.cell(state, ("node", n)).token)
                                 for n in args)
                fact = Fact(key, tuple(direct.items()), tuple(subs), value, pointers)
                self.cache[key] = fact  # SUCCESS ONLY; errors do not overwrite old facts.
            finally:
                self.tx.read_depth -= 1
                self.frames.pop()
                self.active.remove(key)
        if self.frames:
            self.frames[-1][1].append(fact)
        return fact.value

    def require(self, state, n):
        if self.read(state, ("node", n)) is MISSING:
            raise Invalid("missing node")

    def compute(self, state, rule, args):
        n = args[0]
        if rule == "exists":
            return self.read(state, ("node", n)) is not MISSING
        if rule == "resolve":
            seen = set()
            while True:
                if n in seen:
                    raise Invalid("alias cycle")
                seen.add(n)
                if len(seen) > 16:
                    self.tx.reject("alias cap")
                target = self.read(state, ("alias", n))  # Absence is a dependency too.
                if target is MISSING:
                    self.require(state, n)
                    return n
                if type(target) is not int:
                    self.tx.reject("non-total alias control")
                n = target
        if rule == "tag":
            self.require(state, n)
            return self.read(state, ("tag", n))
        if rule == "kind":
            self.require(state, n)
            ctor = self.read(state, ("tag", n))
            if type(ctor) is not str:
                self.tx.reject("non-total constructor control")
            if ctor == "leaf":
                value = self.read(state, ("kind", n))
                if isinstance(value, Poison):
                    value.force()
                if type(value) is not str or value != "Star":
                    raise Invalid("kind")
                return "Star"
            if ctor == "arrow":
                children = self.read(state, ("children", n))
                if type(children) is not tuple or len(children) != 2:
                    raise Invalid("arity")
                for child in children:
                    self.query(state, "kind", child)
                return "Star"
            raise Invalid("tag")
        if rule == "euler":
            # Not real Euler intervals. Global token covers this toy ancestry scan.
            self.read(state, GLOBAL)
            ancestors = []
            while n is not None:
                if type(n) is not int:
                    self.tx.reject("non-total binder control")
                if n in ancestors:
                    raise Invalid("binding cycle")
                if len(ancestors) >= 16:
                    self.tx.reject("binding cap")
                if self.tx.cell(state, ("node", n)).value is MISSING:
                    raise Invalid("missing binder")
                ancestors.append(n)
                n = self.tx.cell(state, ("binder", n)).value
            return tuple(ancestors)
        if rule == "edge":
            parent, child = args
            self.require(state, parent)
            self.require(state, child)
            self.query(state, "kind", child)  # A cached kind is NOT a cached parent edge.
            self.read(state, GLOBAL)
            binder = self.read(state, ("binder", child))
            lineage = self.query(state, "euler", parent)
            if binder is not None and binder not in lineage:
                raise Invalid("dominance")
            return "edge-ok"
        raise AssertionError("unreachable rule")

    def validate_ordered(self, state, root, children):
        # Entry/ordering deliberately uncached, not a complete Graph validator.
        if self.query(state, "tag", root) != "root":
            raise Invalid("root")
        for child in children:
            self.query(state, "kind", child)
        return "valid"


def outcome(call):
    try:
        call()
        return "Right"
    except Invalid as exc:
        return "Left " + str(exc)


def rejected(call):
    try:
        call()
    except Denied as exc:
        return "Denied " + str(exc)
    raise AssertionError("protocol violation was accepted")


def chain(tx):
    return tx.create({1: node(), 2: node(binder=1), 3: node(binder=2),
                      4: node(binder=1), 5: node()})



def tree_intervals(parents):
    """Independent TOTAL tree relation control; no certificates or token reuse."""
    if not 1 <= len(parents) <= 16 or any(type(n) is not int for n in parents):
        raise Invalid("toy tree cap/domain")
    roots = [n for n, p in parents.items() if p is None]
    if len(roots) != 1:
        raise Invalid("toy tree root")
    children = {n: [] for n in parents}
    for n, p in parents.items():
        if p is not None:
            if type(p) is not int or p not in parents:
                raise Invalid("toy tree parent")
            children[p].append(n)
    intervals, active = {}, set()
    clock = [0]

    def visit(n):
        if n in active or n in intervals:
            raise Invalid("toy tree cycle")
        active.add(n)
        start = clock[0]
        clock[0] += 1
        for c in sorted(children[n], reverse=True):
            visit(c)
        intervals[n] = (start, clock[0])
        active.remove(n)

    visit(roots[0])
    if len(intervals) != len(parents):
        raise Invalid("toy tree disconnected")
    return intervals


def relation_record(parents, ancestor, child):
    iv = tree_intervals(parents)
    start, end = iv[ancestor]
    return {"intervals": [[n, *iv[n]] for n in sorted(iv)],
            "answer": start <= iv[child][0] < end}


def tests():
    actual = {}

    tx = Transaction()
    p = Poison()
    s = tx.create({1: node(name=p)})
    copied = tx.clone(s)
    changed = tx.assign(copied, 1, "name", p)
    actual["copy-origin-equal-assignment"] = {
        "copy_same": tx.cell(s, ("name", 1)).token is tx.cell(copied, ("name", 1)).token,
        "assignment_new": tx.cell(copied, ("name", 1)).token is not tx.cell(changed, ("name", 1)).token,
        "poison_touches": p.touches}

    tx = Transaction()
    e = Engine(tx)
    s = tx.create({1: node(), 2: node()})
    old = e.query(s, "resolve", 2)
    merged = tx.merge(s, 1, 2)
    actual["merge-winner-loser-alias"] = {
        "before_resolve": old, "after_resolve": e.query(merged, "resolve", 2),
        "loser_present": e.query(merged, "exists", 2),
        "winner_ctor_new": tx.cell(s, ("tag", 1)).token is not tx.cell(merged, ("tag", 1)).token,
        "winner_payload_copy": tx.cell(s, ("kind", 1)).token is tx.cell(merged, ("kind", 1)).token}

    tx = Transaction()
    p = Poison()
    s = tx.create({1: node(kind=p, name=p)})
    c = tx.canonicalize(s, 1)
    actual["canonical-leaf-rebuilds-constructor"] = {
        "ctor_new": tx.cell(s, ("tag", 1)).token is not tx.cell(c, ("tag", 1)).token,
        "kind_copy": tx.cell(s, ("kind", 1)).token is tx.cell(c, ("kind", 1)).token,
        "name_copy": tx.cell(s, ("name", 1)).token is tx.cell(c, ("name", 1)).token,
        "poison_touches": p.touches}

    tx = Transaction()
    s = tx.create({1: node(tag="arrow", children=(2, 3)), 2: node(), 3: node()})
    c = tx.canonicalize(s, 1, (2, 2))
    actual["canonical-structural-rewrite"] = {
        "ctor_new": tx.cell(s, ("tag", 1)).token is not tx.cell(c, ("tag", 1)).token,
        "children_new": tx.cell(s, ("children", 1)).token is not tx.cell(c, ("children", 1)).token,
        "children": list(tx.cell(c, ("children", 1)).value)}

    tx = Transaction()
    e = Engine(tx)
    before = tx.create({1: node()})
    skeleton = tx.assign(before, 1, "kind", "Bad")
    final = tx.dense_final(skeleton, 1, None, "Flexible")
    actual["dense-final-current-not-before"] = {
        "current_retained": final is skeleton, "before_retained": final is before,
        "outcome": outcome(lambda: e.query(final, "kind", 1))}

    tx = Transaction()
    s = tx.create({1: node(), 2: node()})
    final = tx.dense_final(s, 2, 1, "Rigid")
    actual["dense-final-changed-control"] = {
        "tag_copy": tx.cell(s, ("tag", 2)).token is tx.cell(final, ("tag", 2)).token,
        "binder_new": tx.cell(s, ("binder", 2)).token is not tx.cell(final, ("binder", 2)).token,
        "flag_new": tx.cell(s, ("flag", 2)).token is not tx.cell(final, ("flag", 2)).token,
        "global_new": tx.cell(s, GLOBAL).token is not tx.cell(final, GLOBAL).token}

    tx = Transaction()
    s = tx.create({1: node()})
    final = tx.rebuild_fields(s, 1, None, "Flexible")
    actual["sparse-rebuild-even-equal-controls"] = {
        "tag_copy": tx.cell(s, ("tag", 1)).token is tx.cell(final, ("tag", 1)).token,
        "binder_new": tx.cell(s, ("binder", 1)).token is not tx.cell(final, ("binder", 1)).token,
        "flag_new": tx.cell(s, ("flag", 1)).token is not tx.cell(final, ("flag", 1)).token,
        "global_new": tx.cell(s, GLOBAL).token is not tx.cell(final, GLOBAL).token}

    tx = Transaction()
    e = Engine(tx)
    s = chain(tx)
    old = outcome(lambda: e.query(s, "edge", 3, 4))
    old_edge = e.cache[("edge", (3, 4))]
    old_euler = e.cache[("euler", (3,))]
    changed = tx.assign(s, 2, "binder", 5)
    actual["nonowner-binder-invalidates-euler-and-edge"] = {
        "before": old, "edge_valid": e.valid(changed, old_edge),
        "euler_valid": e.valid(changed, old_euler),
        "after": outcome(lambda: e.query(changed, "edge", 3, 4)),
        "parent_pointer_unchanged": tx.cell(s, ("node", 3)).token is tx.cell(changed, ("node", 3)).token}

    tx = Transaction()
    e = Engine(tx)
    s = tx.create({1: node()}, ((10, 11), (11, 1)))
    missing = e.query(s, "exists", 99)
    updates = [(("node", 99), object())] + [((f, 99), v) for f, v in node().items()]
    added = tx.write(s, "add-node", assigned=updates)
    actual["alias-chain-and-missing-cell"] = {
        "resolved": e.query(s, "resolve", 10), "missing_before": missing,
        "present_after": e.query(added, "exists", 99),
        "missing_error": outcome(lambda: e.query(s, "resolve", 99))}

    tx = Transaction()
    e = Engine(tx)
    s = tx.create({1: node(), 2: node()})
    original = tx.cell(s, ("alias", 1)).token
    e.query(s, "resolve", 1)
    changed = tx.assign(s, 1, "alias", 2)
    removed = tx.write(changed, "remove-alias", erased=(("alias", 1),))
    actual["alias-absence-aba-is-new-version"] = {
        "after_insert": e.query(changed, "resolve", 1),
        "after_remove": e.query(removed, "resolve", 1),
        "new_absence": tx.cell(removed, ("alias", 1)).token is not original}

    a, b = Transaction(), Transaction()
    sa = a.create({1: node()})
    actual["epoch-crossing-rejected"] = rejected(lambda: Engine(b).query(sa, "kind", 1))

    tx = Transaction()
    e = Engine(tx)
    s = chain(tx)
    good = outcome(lambda: e.query(s, "kind", 4))
    actual["successful-subfact-does-not-prove-new-edge"] = {
        "kind": good, "new_parent_edge": outcome(lambda: e.query(s, "edge", 5, 4)),
        "kind_fact_retained": ("kind", (4,)) in e.cache,
        "failed_edge_not_cached": ("edge", (5, 4)) not in e.cache}

    tx = Transaction()
    e = Engine(tx)
    p = Poison()
    s = tx.create({1: node(), 2: node(kind=p)})
    actual["early-root-error-masks-later-poison"] = {
        "outcome": outcome(lambda: e.validate_ordered(s, 1, (2,))),
        "poison_touches": p.touches, "later_fact_absent": ("kind", (2,)) not in e.cache}

    tx = Transaction()
    s = tx.create({1: node()})
    unknown = rejected(lambda: tx.write(s, "unlogged-rewrite"))
    actual["unknown-write-fails-closed"] = {"error": unknown, "published": tx.published is not None}

    tx = Transaction()
    s = tx.create({1: node()})
    actual["mode-switch-fails-closed"] = rejected(lambda: tx.switch_mode(s, "sparse"))

    tx = Transaction()
    e = Engine(tx)
    s = tx.create({1: node(tag="root"), 2: node(), 3: node(kind="Bad")})
    failure = outcome(lambda: tx.publish_checked(e, s, 1, (2, 3)))
    actual["failed-transaction-not-published"] = {
        "outcome": failure, "published": tx.published is not None,
        "successful_subfact_retained": ("kind", (2,)) in e.cache,
        "postfailure_write": rejected(lambda: tx.assign(s, 2, "kind", "Star"))}

    tx = Transaction()
    e = Engine(tx)
    s = tx.create({1: node(tag="root"), 2: node()})
    published = tx.publish_checked(e, s, 1, (2,))
    actual["success-publishes-once"] = {
        "result": published, "same_snapshot": tx.published is s,
        "late_write": rejected(lambda: tx.assign(s, 2, "kind", "Bad"))}


    tx = Transaction()
    s = tx.create({2: node(name="low", binder=None, flag="Flexible"),
                   9: node(name="high", binder=7, flag="Rigid"), 7: node()})
    merged = tx.merge(s, 9, 2, tag_source=2)
    actual["ordered-merge-high-source-low-winner"] = {
        "winner": 2, "loser_resolves": Engine(tx).query(merged, "resolve", 9),
        "binder": tx.cell(merged, ("binder", 2)).value,
        "flag": tx.cell(merged, ("flag", 2)).value,
        "binder_origin_high": tx.cell(merged, ("binder", 2)).token is tx.cell(s, ("binder", 9)).token,
        "payload_origin_low": tx.cell(merged, ("name", 2)).token is tx.cell(s, ("name", 2)).token,
        "ctor_new": tx.cell(merged, ("tag", 2)).token is not tx.cell(s, ("tag", 2)).token}

    # Independent relation controls: recompute COMPLETE intervals on each tree.
    # These do not change the conservative global invalidation protocol above.
    parents = {0: None, 1: 0, 2: 1, 3: 0, 4: 3, 5: 3, 6: 0, 7: 1, 8: 1}
    after = dict(parents)
    del after[5]
    actual["tree-sibling-delete-coordinate-drift"] = {
        "before": relation_record(parents, 1, 2),
        "after": relation_record(after, 1, 2)}
    parents = {0: None, 1: 0, 2: 1, 3: 2, 4: 0, 5: 1, 6: 2, 7: 4,
               8: 0, 9: 1, 10: 1}
    after = dict(parents)
    after[2] = 4
    actual["tree-nonendpoint-move-flips-relation"] = {
        "before": relation_record(parents, 1, 3),
        "after": relation_record(after, 1, 3)}

    # Each mutant is compared with an uncached evaluator on the SAME current
    # symbolic snapshot. This is not Graph.hs, not a separate semantic oracle.
    tx = Transaction()
    bad, correct = Engine(tx, "omit-alias"), Engine(tx)
    s = tx.create({1: node(), 2: node()})
    bad.query(s, "resolve", 1)
    correct.query(s, "resolve", 1)
    changed = tx.assign(s, 1, "alias", 2)
    actual["mutant-omit-alias"] = {
        "mutant": bad.query(changed, "resolve", 1),
        "correct": correct.query(changed, "resolve", 1),
        "fresh": Engine(tx).query(changed, "resolve", 1)}

    tx = Transaction()
    bad, correct = Engine(tx, "omit-global-binding"), Engine(tx)
    s = chain(tx)
    bad.query(s, "edge", 3, 4)
    correct.query(s, "edge", 3, 4)
    changed = tx.assign(s, 2, "binder", 5)
    actual["mutant-omit-global-binding"] = {
        "mutant": outcome(lambda: bad.query(changed, "edge", 3, 4)),
        "correct": outcome(lambda: correct.query(changed, "edge", 3, 4)),
        "fresh": outcome(lambda: Engine(tx).query(changed, "edge", 3, 4))}

    tx = Transaction()
    bad, correct = Engine(tx, "same-id"), Engine(tx)
    first = tx.create({1: node()})
    bad.query(first, "kind", 1)
    correct.query(first, "kind", 1)
    second = tx.create({1: node(kind="Bad")})
    actual["mutant-same-id-cross-graph"] = {
        "mutant": outcome(lambda: bad.query(second, "kind", 1)),
        "correct": outcome(lambda: correct.query(second, "kind", 1)),
        "fresh": outcome(lambda: Engine(tx).query(second, "kind", 1))}

    tx = Transaction()
    bad, correct = Engine(tx, "node-pointer"), Engine(tx)
    s = chain(tx)
    bad.query(s, "edge", 3, 4)
    correct.query(s, "edge", 3, 4)
    changed = tx.assign(s, 2, "binder", 5)
    actual["mutant-node-pointer"] = {
        "mutant": outcome(lambda: bad.query(changed, "edge", 3, 4)),
        "correct": outcome(lambda: correct.query(changed, "edge", 3, 4)),
        "fresh": outcome(lambda: Engine(tx).query(changed, "edge", 3, 4))}

    return actual


def main():
    actual = tests()
    if len(actual) != 24:
        raise AssertionError("case count")
    for name in ("mutant-omit-alias", "mutant-omit-global-binding",
                 "mutant-same-id-cross-graph", "mutant-node-pointer"):
        if actual[name]["mutant"] == actual[name]["fresh"]:
            raise AssertionError("mutant not exposed: " + name)
        if actual[name]["correct"] != actual[name]["fresh"]:
            raise AssertionError("correct protocol differs: " + name)
    # Independent literal expected.json is pinned and consumed by the wrapper.
    # This result status alone does NOT mean that its literal comparison passed.
    print(json.dumps({"schema": SCHEMA, "status": "FINITE_SYMBOLIC_WRITE_MODEL_RESULTS",
                      "checks": actual, "check_count": len(actual), "mutants_caught": 4,
                      "production_equivalence": False, "performance_result": False},
                     sort_keys=True))


if __name__ == "__main__":
    main()
