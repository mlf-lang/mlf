"""Finite-AST predicate model; not the real Haskell checker or benchmark."""
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Ty:
    tag: str
    payload: object = None
    children: tuple = ()


def tick(counts, key):
    if counts is not None:
        counts[key] = counts.get(key, 0) + 1


def free_vars(ty, counts=None):
    """Independent transcription of the seven Type.freeVars cases."""
    tick(counts, "node")
    if ty.tag == "var":
        tick(counts, "singleton")
        return frozenset((ty.payload,))
    if ty.tag in ("bot", "bot-kind"):
        return frozenset()
    if ty.tag in ("arrow", "apply"):
        left = free_vars(ty.children[0], counts)
        right = free_vars(ty.children[1], counts)
        tick(counts, "union")
        return left | right
    if ty.tag == "con":
        answer = frozenset()
        for child in reversed(ty.children):
            answer = free_vars(child, counts) | answer
            tick(counts, "union")
        return answer
    if ty.tag == "forall":
        bound = free_vars(ty.children[0], counts)
        body = free_vars(ty.children[1], counts)
        tick(counts, "delete")
        tick(counts, "union")
        return bound | (body - {ty.payload})
    raise ValueError("unknown type tag")


def closed_in(scope, ty, counts=None):
    """Proposed finite predicate: FV(ty) is a subset of immutable scope."""
    tick(counts, "node")
    if ty.tag == "var":
        tick(counts, "member")
        return ty.payload in scope
    if ty.tag in ("bot", "bot-kind"):
        return True
    if ty.tag in ("arrow", "apply", "con"):
        return all(closed_in(scope, child, counts) for child in ty.children)
    if ty.tag == "forall":
        # The new binder is NOT in scope in its own bound.
        if not closed_in(scope, ty.children[0], counts):
            return False
        tick(counts, "scope-insert")
        return closed_in(scope | {ty.payload}, ty.children[1], counts)
    raise ValueError("unknown type tag")


def bounded_types():
    """888 finite trees of at most 4 nodes in a specified small grammar.

    Includes all seven type constructors and deliberately does not impose kind
    validity. Variable IDs/binders are -1,0,1; constructor name is opaque C;
    constructor arity is 0,1,2. Not an enumeration of all real MLF types.
    """
    by_size = {1: [Ty("bot"), Ty("bot-kind", "* -> *"),
                   Ty("var", -1), Ty("var", 0), Ty("var", 1), Ty("con", "C")]}
    for size in range(2, 5):
        values = [Ty("con", "C", (child,)) for child in by_size[size - 1]]
        for left_size in range(1, size - 1):
            right_size = size - 1 - left_size
            for left, right in product(by_size[left_size], by_size[right_size]):
                values.extend([Ty("arrow", None, (left, right)),
                               Ty("apply", None, (left, right)),
                               Ty("con", "C", (left, right))])
                values.extend(Ty("forall", name, (left, right)) for name in (-1, 0, 1))
        by_size[size] = values
    return [item for size in sorted(by_size) for item in by_size[size]]


def balanced_repeated_variable(depth, name=0):
    if depth == 0:
        return Ty("var", name)
    child = balanced_repeated_variable(depth - 1, name)
    return Ty("arrow", None, (child, child))
