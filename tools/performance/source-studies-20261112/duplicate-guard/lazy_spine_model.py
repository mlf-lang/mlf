"""Demand-event model of lazy append; NOT a Haskell evaluator or heap model.

It distinguishes Either WHNF, Fragment WHNF, entry-pair WHNF and list-spine
traversal. Source chunks are admitted first. Flattening shares the same entry
pairs, which those first guards already forced; names remain separate thunks.
"""
from dataclasses import dataclass
from itertools import product


class Bottom(Exception):
    pass


class Thunk:
    def __init__(self, label, compute, events):
        self.label, self.compute, self.events = label, compute, events
        self.ready, self.value, self.error = False, None, None

    def force(self):
        if not self.ready:
            self.events.append(("force", self.label))
            try:
                self.value = self.compute()
            except Bottom as error:
                self.error = error
            self.ready = True
        if self.error is not None:
            raise self.error
        return self.value


@dataclass(frozen=True)
class Cons:
    head: Thunk
    tail: Thunk


NIL = None


def poison(message):
    raise Bottom(message)


def source_list(heads, prefix, events, bad_tail=False):
    def at(index):
        def compute():
            if index == len(heads):
                return poison(prefix + ":tail") if bad_tail else NIL
            return Cons(heads[index], at(index + 1))
        return Thunk(prefix + ":" + str(index), compute, events)
    return at(0)


def append(left, right, label, events):
    def compute():
        cell = left.force()
        if cell is NIL:
            events.append(("flatten-empty", label))
            return right.force()
        events.append(("flatten-cons", label))
        return Cons(cell.head, append(cell.tail, right, label + ".tail", events))
    return Thunk("append:" + label, compute, events)


def walk(spine, predicate=None):
    while True:
        cell = spine.force()
        if cell is NIL:
            return True
        if predicate is not None and not predicate(cell.head):
            return False
        spine = cell.tail


def closure(head, phase, events):
    label, name, state = head.force()
    events.append((phase, label))
    if state == "bottom":
        raise Bottom("closure:" + label)
    if state not in ("closed", "open"):
        raise ValueError("bad symbolic closure state")
    return state == "closed"


@dataclass(frozen=True)
class Fragment:
    owned: Thunk


@dataclass(frozen=True)
class Right:
    fragment: Thunk


@dataclass(frozen=True)
class Left:
    error: str


class Session:
    def __init__(self, groups, variant, *, bad_name=False, bad_source_tail=None):
        if variant not in ("original", "delete", "spine", "whnf-only"):
            raise ValueError("unknown variant")
        self.events, self.variant = [], variant
        self.groups = []
        for group_index, states in enumerate(groups):
            heads = []
            for entry_index, state in enumerate(states):
                label = str(group_index) + ":" + str(entry_index)
                name = Thunk("name:" + label,
                             lambda l=label: poison("name:" + l) if bad_name else l,
                             self.events)
                heads.append(Thunk("pair:" + label,
                                   lambda l=label, n=name, s=state: (l, n, s), self.events))
            self.groups.append(source_list(heads, "chunk:" + str(group_index),
                                           self.events, bad_source_tail == group_index))
        self.result = Thunk("either-result", self.check, self.events)

    def admit(self, index=0):
        if index == len(self.groups):
            return Thunk("owned-terminal", lambda: NIL, self.events)
        group = self.groups[index]
        if not walk(group, lambda h: closure(h, "first-closure", self.events)):
            return Left("inference binding has an open type")
        rest = self.admit(index + 1)
        if isinstance(rest, Left):
            return rest
        # As in Right (append entries rest), this does not force the new spine.
        return append(group, rest, str(index), self.events)

    def check(self):
        owned = self.admit()
        if isinstance(owned, Left):
            return owned
        if self.variant == "original":
            if not walk(owned, lambda h: closure(h, "repeat-closure", self.events)):
                return Left("open fragment exports an open type")
        elif self.variant == "spine":
            walk(owned)  # Corresponds only to all (\_ -> True), not deep forcing.
        elif self.variant == "whnf-only":
            owned.force()  # Rejected weak control: seq owned is insufficient.
        return Right(Thunk("fragment", lambda: Fragment(owned), self.events))

    def observe(self, kind):
        try:
            if kind == "none":
                return "unobserved"
            result = self.result.force()
            if isinstance(result, Left):
                return ("left", result.error)
            if kind == "either-whnf":
                return "right-whnf"
            fragment = result.fragment.force()
            if kind == "fragment-whnf":
                return "fragment-whnf"
            if kind == "full-spine":
                walk(fragment.owned)
                return "full-spine"
            cell = fragment.owned.force()
            if cell is NIL:
                return "empty"
            if kind == "owned-whnf":
                return "cons-whnf"
            if kind == "head-pair":
                cell.head.force()
                return "pair-whnf"
            if kind == "head-name":
                return ("name", cell.head.force()[1].force())
            raise ValueError("unknown observation")
        except Bottom as error:
            return ("modeled-bottom", str(error))


def finite_group_protocols():
    shapes = ((), ("closed",), ("open",), ("bottom",),
              ("closed", "open"), ("closed", "closed"))
    for length in range(4):
        yield from product(shapes, repeat=length)
