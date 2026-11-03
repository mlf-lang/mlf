"""Budgeted source port of resource_ir/checker.py's ownership/order rules.

Provenance: old helpers at lines 48-101 and 288-342. This port does not import
that package (its __init__ loads runtime), and is not its version ladder.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from .program_schema import fail, name


@dataclass(frozen=True, slots=True, eq=False)
class Value:
    group: int
    kind: str
    capability: int | None = None
    storage: int | None = None
    node: int | None = None
    mode: str | None = 'own'
    type: int | None = None
    ready: bool | None = False
    anchor: object = None
    ticket: bool | None = False
    view: str | None = 'MONO'
    scheme: str | None = None
    projection: object = None
    provenance: int | None = None
    authority_source: object = None


class Symbols:
    __slots__ = ('budget', 'groups', 'nodes', 'capabilities', 'storages')

    def __init__(self, budget):
        self.budget = budget
        self.groups = self.nodes = self.capabilities = self.storages = 0

    def fresh(self, namespace):
        self.budget.charge()
        result = getattr(self, namespace)
        setattr(self, namespace, result + 1)
        return result

    def value(self, group, type_id, provenance, *, ready=False, ticket=False,
              mode='own', anchor=None):
        self.budget.charge(4)  # row plus three identities; group already exists
        capability, storage, node = self.capabilities, self.storages, self.nodes
        self.capabilities += 1
        self.storages += 1
        self.nodes += 1
        return Value(group, 'value', capability, storage, node, mode, type_id,
                     ready, anchor, ticket, provenance=provenance)

    def key(self, group):
        self.budget.charge(3)
        capability, storage = self.capabilities, self.storages
        self.capabilities += 1
        self.storages += 1
        return Value(group, 'key', capability, storage, ready=None, ticket=None, view=None)

    def alias(self, group, source):
        self.budget.charge()
        return Value(group, 'authority', mode=None, ready=None, ticket=None,
                     view=None, authority_source=source)

    def changed(self, value, **changes):
        self.budget.charge()
        return replace(value, **changes)

    def copied_handle(self, value, *, mode='own', anchor=None):
        self.budget.charge(3)
        capability, storage = self.capabilities, self.storages
        self.capabilities += 1
        self.storages += 1
        return replace(value, capability=capability, storage=storage, mode=mode,
                       anchor=anchor, ticket=False)


class Order:
    """An upper->lower edge proves Down; strictness needs a strict path edge."""
    __slots__ = ('budget', 'edges', 'adjacency')

    def __init__(self, budget):
        self.budget = budget
        budget.charge()  # scope/order snapshot header
        self.edges = []
        self.adjacency = {}

    def add(self, upper, lower, strict=False):
        # One edge row, edge inventory member, adjacency member; maybe bucket.
        self.budget.charge(3 + (upper not in self.adjacency))
        edge = (upper, lower, strict)
        self.edges.append(edge)
        if upper not in self.adjacency:
            self.adjacency[upper] = []
        self.adjacency[upper].append(edge)

    def copy(self):
        # Charge the complete operation before any distinct semantic container.
        count = 1 + len(self.edges) + len(self.adjacency)
        for members in self.adjacency.values():
            count += len(members)
        self.budget.charge(count)
        other = object.__new__(Order)
        other.budget = self.budget
        other.edges = self.edges.copy()
        other.adjacency = {}
        for upper, members in self.adjacency.items():
            other.adjacency[upper] = members.copy()
        return other

    def merge(self, other):
        # Child starts with the exact copied prefix, then only appends facts.
        if len(other.edges) < len(self.edges):
            raise ValueError('order merge lost parent prefix')
        for index in range(len(self.edges), len(other.edges)):
            upper, lower, strict = other.edges[index]
            self.add(upper, lower, strict)

    def below(self, lower, upper, *, strict=False):
        self.budget.charge()
        todo = [(upper, False)]
        seen = set()
        while todo:
            current, has_strict = todo.pop()
            pair = (current, has_strict)
            if pair in seen:
                continue
            self.budget.add(seen, pair)
            if current == lower and (has_strict or not strict):
                return True
            for _, target, edge_strict in self.adjacency.get(current, ()):
                self.budget.examine()
                self.budget.charge()
                todo.append((target, has_strict or edge_strict))
        return False


class State:
    __slots__ = ('budget', 'values', 'used', 'order', 'home', 'result_type',
                 'require_ready', 'finish_allowed', 'result_identity', 'parameter')

    def __init__(self, budget, *, order=None, home=None, result_type=None,
                 require_ready=False, finish_allowed=False):
        budget.charge()
        self.budget, self.values, self.used = budget, {}, set()
        self.order = Order(budget) if order is None else order
        self.home, self.result_type = home, result_type
        self.require_ready, self.finish_allowed = require_ready, finish_allowed
        self.result_identity, self.parameter = None, None

    def copy(self):
        # Public only as a private-helper control: generalize does not copy names.
        count = 1 + len(self.values) + len(self.used) + 1 + len(self.order.edges) + len(self.order.adjacency)
        for members in self.order.adjacency.values():
            count += len(members)
        self.budget.charge(count)
        other = object.__new__(State)
        other.budget = self.budget
        other.values, other.used = self.values.copy(), self.used.copy()
        order = object.__new__(Order)
        order.budget = self.budget
        order.edges, order.adjacency = self.order.edges.copy(), {}
        for upper, members in self.order.adjacency.items():
            order.adjacency[upper] = members.copy()
        other.order = order
        other.home, other.result_type = self.home, self.result_type
        other.require_ready, other.finish_allowed = self.require_ready, self.finish_allowed
        other.result_identity, other.parameter = self.result_identity, self.parameter
        return other

    def reserve(self, variable, path):
        name(variable, path, binder=True)
        if variable in self.used:
            fail(path, 'resource', 'SSA', 'a previously used name cannot be rebound')
        self.budget.add(self.used, variable)

    def bind(self, variable, value, path, *, reserved=False, internal=False):
        if not reserved:
            if internal:
                if variable in self.used:
                    fail(path, 'resource', 'SSA', 'internal binder collision')
                self.budget.add(self.used, variable)
            else:
                self.reserve(variable, path)
        self.budget.put(self.values, variable, value)

    def get(self, variable, path, *, kind=None, own=False, mono=False, validate_anchor=True):
        name(variable, path)
        if variable not in self.values:
            fail(path, 'resource', 'NOT_LIVE', 'binding has no live capability')
        value = self.values[variable]
        if kind is not None and value.kind != kind:
            fail(path, 'resource', 'KIND', 'operand has the wrong capability kind')
        if mono and value.view != 'MONO':
            fail(path, 'type', 'SCHEME_VALUE', 'a Scheme handle is not a Mono value')
        if own and value.mode != 'own':
            fail(path, 'resource', 'OWNERSHIP', 'operand requires an independent owner')
        if validate_anchor:
            self.check_anchor(value, path)
        return value

    def check_anchor(self, value, path):
        if value.mode == 'loan':
            anchor = value.anchor
            if anchor is None:
                fail(path, 'resource', 'ANCHOR', 'loan has no exact anchor')
            if anchor['kind'] == 'owner':
                found = False
                for owner in self.values.values():
                    if owner.capability == anchor['capability'] and owner.mode == 'own':
                        found = True
                        break
                if not found:
                    fail(path, 'resource', 'ANCHOR', 'loan exact owner anchor is not live')
            elif anchor['kind'] != 'activation':
                fail(path, 'resource', 'ANCHOR', 'invalid loan anchor')

    def authority(self, variable, path):
        value = self.get(variable, path)
        if value.kind == 'authority' and variable == '$home':
            return value
        if value.mode != 'own':
            fail(path, 'resource', 'AUTHORITY', 'authority requires an owner or the imported/activation home')
        return value

    def movable(self, variable, path, *, allow_ticket=False, own=True):
        value = self.get(variable, path, own=own)
        for other in self.values.values():
            if other.mode == 'loan' and other.anchor is not None and other.anchor['kind'] == 'owner' and other.anchor['capability'] == value.capability:
                fail(path, 'resource', 'LIVE_LOAN', 'exact capability still anchors a live loan')
        if value.ticket and not allow_ticket:
            fail(path, 'resource', 'UNFILLED_HOLE', 'unfilled construction ticket cannot be consumed')
        return value

    def consume(self, variable, path, *, allow_ticket=False):
        value = self.movable(variable, path, allow_ticket=allow_ticket)
        del self.values[variable]
        return value

    def move(self, variable, path):
        # Unlike consume, this preserves and removes an anchored loan legally.
        value = self.movable(variable, path, own=False)
        del self.values[variable]
        return value

    def finish(self, path):
        for variable in self.values:
            if variable != '$home':
                fail(path, 'resource', 'UNDISCHARGED', 'all local owners, loans and tickets must be discharged')
