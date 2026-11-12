"""Small structural specification model, NOT an MLF checker or Haskell runner.

Premise: finite declaration spines with already-validated RHSs, annotations,
and contexts. Types carry separate alpha-class and exact-syntax tokens. This
models root extraction and lazy inventory access, not type inference, Haskell
bottoms/retention, artifact encoding, or production performance.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    ident: int
    hint: str
    alpha: str = "Int"
    syntax: str = "Int"


@dataclass(frozen=True)
class Term:
    tag: str
    entries: tuple = ()
    body: object = None


UNIT = Term("unit")
INTEGER = Term("integer")
SHAPE = "invalid inference fragment: expected declarations ending in ()"
ORDER = "inference parameter order mismatch"
MISSING = "inference did not retain external parameters"


class Rejected(Exception):
    def __init__(self, seam, message):
        self.seam, self.message = seam, message
        super().__init__(seam, message)


def fail(seam, message):
    raise Rejected(seam, message)


def result(operation):
    try:
        return ("right", operation())
    except Rejected as error:
        return ("left", error.seam, error.message)


def peel_data(term):
    return (term.entries, term.body) if term.tag == "data" else ((), term)


def declaration_inventory(term):
    if term.tag == "unit":
        return ()
    if term.tag in ("let", "rec"):
        return term.entries + declaration_inventory(term.body)
    fail("open", SHAPE)


class ModeledReceipt:
    """Synthetic receipt, never used to authorize an actual compiler action."""
    def __init__(self, term, inventory_override=None):
        self.term = term
        self.inventory_calls = 0
        self.inventory_override = inventory_override

    def inventory(self):
        self.inventory_calls += 1
        if self.inventory_override is not None:
            return self.inventory_override()
        _, core = peel_data(self.term)
        while core.tag == "lambda":
            core = core.body
        return declaration_inventory(core)


@dataclass(frozen=True)
class Projection:
    receipt: ModeledReceipt
    context: tuple
    parameters: tuple
    body: Term
    cut: object


def baseline_extract(term, expected):
    context, core = peel_data(term)
    if not expected:
        return context, (), core
    if core.tag != "rec":
        fail("wrapper", MISSING)
    if tuple(x.hint for x in core.entries) != tuple(k for k, _ in expected):
        fail("wrapper", ORDER)
    for actual, (_, wanted) in zip(core.entries, expected):
        if actual.alpha != wanted:
            fail("wrapper", "dependency scheme changed during inference: " + actual.hint)
    return context, core.entries, core.body


def baseline(receipt, expected):
    context, parameters, body = baseline_extract(receipt.term, expected)
    return context, parameters, body, declaration_inventory(body)


def project(receipt, expected):
    # Independent implementation, deliberately not using baseline_extract.
    term = receipt.term
    if term.tag == "data":
        context, core = term.entries, term.body
    else:
        context, core = (), term
    if not expected:
        return Projection(receipt, context, (), core,
                          "reject-lambda" if core.tag == "lambda" else None)
    if core.tag != "rec":
        fail("wrapper", MISSING)
    if [x.hint for x in core.entries] != [k for k, _ in expected]:
        fail("wrapper", ORDER)
    for index, binding in enumerate(core.entries):
        if binding.alpha != expected[index][1]:
            fail("wrapper", "dependency scheme changed during inference: " + binding.hint)
    return Projection(receipt, context, core.entries, core.body, len(core.entries))


def projected_inventory(projection):
    if projection.cut == "reject-lambda":
        fail("open", SHAPE)
    whole = projection.receipt.inventory()
    if projection.cut is None:
        return whole
    count = projection.cut
    if count < 0 or len(whole) < count:
        fail("lemma", "checked inventory is shorter than its exact root prefix")
    prefix, suffix = whole[:count], whole[count:]
    if prefix != projection.parameters:
        fail("lemma", "exact root inventory prefix changed IDs/hints/type syntax")
    return suffix


def candidate(receipt, expected):
    projection = project(receipt, expected)
    return (projection.context, projection.parameters, projection.body,
            projected_inventory(projection))


def safe_adapter(projection):
    # The body is independently checked, never replaced by receipt inventory.
    return (projection.context, projection.parameters, projection.body,
            declaration_inventory(projection.body))


def fixture_inputs():
    """810 finite symbolic cases; not real Checked.check receipt generation."""
    tails = [UNIT, INTEGER, Term("lambda", (Binding(900, "lambda"),), UNIT)]
    spines = []
    for tail in tails:
        spines.append(tail)
        for depth in range(1, 4):
            for mask in range(2 ** depth):
                body = tail
                for i in reversed(range(depth)):
                    item = Binding(100 + i, "owned" + str(i), "Int", "Int")
                    body = Term("let" if mask & (1 << i) else "rec", (item,), body)
                spines.append(body)
    # 45 bodies; each is tried without externals and with 1/2 parameters,
    # with/without exact data context. Empty and own rec roots also retained.
    for body in spines + [Term("rec", (), x) for x in spines]:
        for count in range(3):
            imports = tuple(Binding(i, "import" + str(i)) for i in range(count))
            source = Term("rec", imports, body) if imports else body
            expected = tuple((x.hint, x.alpha) for x in imports)
            for context in [None, (), ("exact-unused-data-declaration",)]:
                yield (Term("data", context, source) if context is not None else source), expected
