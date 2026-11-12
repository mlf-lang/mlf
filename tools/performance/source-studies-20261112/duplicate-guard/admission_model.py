"""Small pure admission-protocol model, NOT the real MLF checker.

It models order and invariant flow: declaration inference completes before
inventory admission; first closure guards are outer-to-inner; a successful
inventory is then redundantly checked by the original Open.check. Closure
probes are immutable/idempotent symbolic results, never an actual type checker.
"""
from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Entry:
    name: str
    closure: str  # closed, open or bottom
    ignored_payload: object = None


@dataclass(frozen=True)
class Decl:
    kind: str  # let or rec
    entries: tuple
    inference_error: str = ""


@dataclass(frozen=True)
class Program:
    declarations: tuple = ()
    terminal: str = "unit"  # unit or other-valid-term
    terminal_inference_error: str = ""
    precheck_error: str = ""


@dataclass(frozen=True)
class Outcome:
    status: str
    detail: str = ""
    exports: tuple = ()


class ModeledBottom(Exception):
    pass


@dataclass(frozen=True)
class Inventory:
    entries: tuple = ()
    rest: object = None
    shape_error: str = ""


def infer_inventory(program, trace):
    """RHS/body checking happens before ANY delayed inventory guard."""
    def visit(index):
        if index == len(program.declarations):
            trace.append(("infer-terminal", program.terminal))
            if program.terminal_inference_error:
                return Outcome("left", program.terminal_inference_error)
            error = ("" if program.terminal == "unit" else
                     "invalid inference fragment: expected declarations ending in ()")
            return Inventory(shape_error=error)
        decl = program.declarations[index]
        if decl.kind not in ("let", "rec"):
            raise ValueError("unknown declaration")
        if decl.kind == "let" and len(decl.entries) != 1:
            raise ValueError("let requires one entry")
        trace.append(("infer-declaration", index, decl.kind))
        if decl.inference_error:
            return Outcome("left", decl.inference_error)
        child = visit(index + 1)
        if isinstance(child, Outcome):
            return child
        return Inventory(decl.entries, child)
    return visit(0)


def is_closed(entry, phase, trace):
    trace.append((phase, entry.name))
    if entry.closure == "bottom":
        raise ModeledBottom(entry.name)
    if entry.closure not in ("open", "closed"):
        raise ValueError("unknown closure result")
    return entry.closure == "closed"


def admit(inventory, trace, skip_first_guards=False):
    # skip_first_guards is fault injection for tests, NEVER a proposed change.
    if not skip_first_guards:
        for entry in inventory.entries:
            if not is_closed(entry, "first-closure", trace):
                return Outcome("left", "inference binding has an open type")
    if inventory.shape_error:
        return Outcome("left", inventory.shape_error)
    if inventory.rest is None:
        return ()
    rest = admit(inventory.rest, trace, skip_first_guards)
    if isinstance(rest, Outcome):
        return rest
    return inventory.entries + rest


def run(program, repeat_guard, *, skip_first_guards=False, forged_exports=()):
    trace = []
    try:
        trace.append(("precheck",))
        if program.precheck_error:
            return Outcome("left", program.precheck_error), trace
        inventory = infer_inventory(program, trace)
        if isinstance(inventory, Outcome):
            return inventory, trace
        owned = admit(inventory, trace, skip_first_guards)
        if isinstance(owned, Outcome):
            return owned, trace
        # forged_exports is another mutation, absent from the real data path.
        owned = owned + forged_exports
        if repeat_guard:
            for entry in owned:
                if not is_closed(entry, "repeated-closure", trace):
                    return Outcome("left", "open fragment exports an open type"), trace
        return Outcome("right", exports=owned), trace
    except ModeledBottom as error:
        return Outcome("modeled-bottom", str(error)), trace


def finite_programs():
    """6,342 small protocols, not source programs or full xMLF ASTs."""
    states = ("closed", "open", "bottom")
    declarations = []
    for kind, arity in (("let", 1), ("rec", 0), ("rec", 1), ("rec", 2)):
        for values in product(states, repeat=arity):
            entries = tuple(Entry(str(i), value) for i, value in enumerate(values))
            for fail in (False, True):
                declarations.append(Decl(kind, entries, "declaration type error" if fail else ""))
    terminals = (("unit", ""), ("other-valid-term", ""), ("unit", "terminal type error"))
    for length in range(3):
        for ds in product(declarations, repeat=length):
            for terminal, term_error in terminals:
                for precheck in ("", "parameter validation error"):
                    yield Program(ds, terminal, term_error, precheck)
