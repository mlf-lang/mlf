"""Finite symbolic cost study, NOT Haskell execution or allocation measurement.

Insertion/balance equations follow pinned Bootstrap.Map. Lazy scope recipes
separate extension expressions from materialized sets; only membership forces
them. Python integers, object costs, stack use and forcing are not host costs.
"""
from dataclasses import dataclass
from closedness_model import Ty, free_vars, tick


@dataclass(frozen=True)
class Node:
    key: int
    left: object = None
    right: object = None
    size: int = 1


def size(tree):
    return 0 if tree is None else tree.size


def node(key, left, right, counts):
    tick(counts, "tree-node-equation")
    return Node(key, left, right, 1 + size(left) + size(right))


def balance(key, left, right, counts):
    sl, sr = size(left), size(right)
    if sl + sr <= 1:
        return node(key, left, right, counts)
    if sr > 3 * sl:
        r = right
        if size(r.left) < 2 * size(r.right):
            return node(r.key, node(key, left, r.left, counts), r.right, counts)
        m = r.left
        if m is None:
            return node(r.key, node(key, left, None, counts), r.right, counts)
        return node(m.key, node(key, left, m.left, counts),
                    node(r.key, m.right, r.right, counts), counts)
    if sl > 3 * sr:
        l = left
        if size(l.right) < 2 * size(l.left):
            return node(l.key, l.left, node(key, l.right, right, counts), counts)
        m = l.right
        if m is None:
            return node(l.key, l.left, node(key, None, right, counts), counts)
        return node(m.key, node(l.key, l.left, m.left, counts),
                    node(key, m.right, right, counts), counts)
    return node(key, left, right, counts)


def insert(key, tree, counts):
    if tree is None:
        return node(key, None, None, counts)
    tick(counts, "insert-key-compare")
    if key < tree.key:
        return balance(tree.key, insert(key, tree.left, counts), tree.right, counts)
    if key > tree.key:
        return balance(tree.key, tree.left, insert(key, tree.right, counts), counts)
    return node(key, tree.left, tree.right, counts)


def member(key, tree, counts):
    while tree is not None:
        tick(counts, "member-key-compare")
        if key == tree.key:
            return True
        tree = tree.left if key < tree.key else tree.right
    return False


class Scope:
    """Memoized recipe graph; not a general Haskell evaluator."""
    def __init__(self, parent=None, key=None):
        self.parent, self.key = parent, key
        self.ready = parent is None
        self.tree = None

    def extend(self, key, counts):
        tick(counts, "scope-extension-expression")
        return Scope(self, key)

    def force(self, counts):
        if not self.ready:
            parent_tree = self.parent.force(counts)
            tick(counts, "scope-materialized-insert")
            self.tree = insert(self.key, parent_tree, counts)
            self.ready = True
        return self.tree


def closed_with_recipe(scope, ty, counts):
    tick(counts, "visited-type-node")
    if ty.tag == "var":
        return member(ty.payload, scope.force(counts), counts)
    if ty.tag in ("bot", "bot-kind"):
        return True
    if ty.tag in ("arrow", "apply", "con"):
        return all(closed_with_recipe(scope, child, counts) for child in ty.children)
    if ty.tag == "forall":
        return (closed_with_recipe(scope, ty.children[0], counts) and
                closed_with_recipe(scope.extend(ty.payload, counts), ty.children[1], counts))
    raise ValueError("unknown type tag")


def closed_with_list(scope, ty, counts):
    """Rejected linear-list alternative; counted only for the adverse family."""
    if ty.tag == "var":
        for binder in scope:
            tick(counts, "list-key-compare")
            if binder == ty.payload:
                return True
        return False
    if ty.tag in ("bot", "bot-kind"):
        return True
    if ty.tag in ("arrow", "apply", "con"):
        return all(closed_with_list(scope, child, counts) for child in ty.children)
    if ty.tag == "forall":
        return (closed_with_list(scope, ty.children[0], counts) and
                closed_with_list((ty.payload,) + scope, ty.children[1], counts))
    raise ValueError("unknown type tag")


def nested(depth, body):
    for key in reversed(range(depth)):
        body = Ty("forall", key, (Ty("bot"), body))
    return body


def family(depth, kind):
    if depth < 1:
        raise ValueError("positive depth required")
    if kind == "unused":
        body = Ty("bot")
    elif kind == "innermost-once":
        body = Ty("var", depth - 1)
    elif kind == "outer-repeated":
        # An opaque constructor with D arguments, not a claim of kind validity.
        body = Ty("con", "C", (Ty("var", 0),) * depth)
    else:
        raise ValueError("unknown family")
    return nested(depth, body)


def measure(depth, kind):
    ty = family(depth, kind)
    old, tree, linear = {}, {}, {}
    assert not free_vars(ty, old)
    assert closed_with_recipe(Scope(), ty, tree)
    assert closed_with_list((), ty, linear)
    return {"depth": depth, "family": kind, "reference_symbolic_events": old,
            "set_recipe_events": tree, "list_events": linear}


if __name__ == "__main__":
    import json
    print(json.dumps([measure(d, k) for d in (1, 2, 4, 8, 16, 32, 64)
                      for k in ("unused", "innermost-once", "outer-repeated")], indent=2))
