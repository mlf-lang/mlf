"""Flat, immutable IDs over a freshly checked Stage01 declaration DAG.

The pinned declaration checker owns canonicalization and lexical resolution.
This adapter never hashes or compares its recursively shared canonical tuples.
Only integer object identities are temporary map keys, and every canonical tuple
remains strongly referenced by the private checked index for the adapter lifetime.
There is deliberately no from_index admission API and no runtime import.
"""
from __future__ import annotations

from dataclasses import dataclass

from .declarations import DeclarationError, check_declarations
from .program_schema import fail


def _declaration_error(error):
    fail(error.path, "declarations", error.code, error.message)


def _invariant(message):
    fail("declarations", "declarations", "ADAPTER_INVARIANT", message)


def _name(value, path):
    if type(value) is not str or not value or "\0" in value:
        fail(path, "declarations", "NAME", "expected a nonempty NUL-free plain string")
    if value.startswith("^"):
        fail(path, "declarations", "NAMESPACE", "declaration names cannot begin with ^")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        fail(path, "declarations", "NAME", "name must be valid UTF-8")
    return value


def _lookup(rows, key):
    """Binary search scalar keys, never canonical type tuple keys."""
    low, high = 0, len(rows)
    while low < high:
        middle = (low + high) // 2
        if rows[middle][0] < key:
            low = middle + 1
        else:
            high = middle
    if low < len(rows) and rows[low][0] == key:
        return rows[low][1]
    return None


@dataclass(frozen=True, slots=True, eq=False, repr=False)
class DeclarationIds:
    """Declaration-only flat ID view, not a resource or executable acceptance.

    Public collections are keyed tuples except rows, which is positional.
    environments: (ID, (scheme-or-null, mode, argument-IDs)).
    schemes: (name, (parameter-count, body-ID, neutral-environment-ID)).
    instantiations: (name, (scheme, argument-IDs, body-ID, closed-environment-ID)).
    Construction itself is not a security boundary against hostile Python.
    """

    canonical_json: str
    sha256: str
    rows: tuple
    environments: tuple
    schemes: tuple
    instantiations: tuple
    _index: object
    _identities: tuple

    def __repr__(self):
        return (f"DeclarationIds(declarations-only, sha256={self.sha256!r}, "
                f"types={len(self.rows)}, environments={len(self.environments)})")

    def resolve_id(self, reference, scope=None):
        """Preserve Stage01 scope checks before consulting the identity map."""
        try:
            canonical = self._index.resolve(reference, scope)
        except DeclarationError as error:
            _declaration_error(error)
        result = _lookup(self._identities, id(canonical))
        if result is None:
            _invariant("resolved canonical object is absent from the checked DAG")
        return result

    def row(self, type_id):
        if type(type_id) is not int or not 0 <= type_id < len(self.rows):
            fail("query.type_id", "declarations", "TYPE_ID", "expected an in-range non-boolean Type ID")
        return self.rows[type_id]

    def scheme(self, name):
        _name(name, "query.scheme")
        result = _lookup(self.schemes, name)
        if result is None:
            fail("query.scheme", "declarations", "SCHEME", "unknown declared scheme")
        return result

    def instantiation(self, name):
        _name(name, "query.instantiation")
        result = _lookup(self.instantiations, name)
        if result is None:
            fail("query.instantiation", "declarations", "USE", "unknown declared instantiation")
        return result

    def environment(self, env_id):
        # Environments retain Stage01 numeric order E0,E1,..., not lexical order.
        if type(env_id) is not str:
            fail("query.environment", "declarations", "ENVIRONMENT", "expected a checked environment ID")
        # This bounded linear scan avoids integer conversion of untrusted strings.
        for key, value in self.environments:
            if key == env_id:
                return value
        fail("query.environment", "declarations", "ENVIRONMENT", "unknown checked environment ID")


def check_type_ids(six_maps):
    """Check raw six-map declarations afresh, then flatten their canonical DAG.

    Stage01 declaration creation/limits are already independently bounded. These
    adopted records are not Stage02 body-analysis creation units. Stage02 still
    charges any new derived output rows or copied memberships it constructs.
    """
    try:
        index = check_declarations(six_maps)
    except DeclarationError as error:
        _declaration_error(error)

    identities = {}
    rows = []
    for position, canonical in enumerate(index.type_rows):
        if type(canonical) is not tuple or not canonical:
            _invariant("canonical node must be a nonempty tuple")
        object_id = id(canonical)
        if object_id in identities:
            _invariant("canonical type row repeats an object identity")
        tag = canonical[0]
        if tag == "closed" and len(canonical) == 2 and type(canonical[1]) is str:
            row = ("closed", canonical[1])
        elif (tag == "rigid" and len(canonical) == 3
              and type(canonical[1]) is str and type(canonical[2]) is int):
            row = ("rigid", canonical[1], canonical[2])
        elif tag == "arrow" and len(canonical) == 5:
            argument = identities.get(id(canonical[1]))
            result = identities.get(id(canonical[2]))
            if argument is None or result is None:
                _invariant("arrow children must be exact already-indexed canonical objects")
            if canonical[3] not in ("repeat", "once") or canonical[4] not in ("argument", "unknown"):
                _invariant("invalid canonical arrow contract")
            row = ("arrow", argument, result, canonical[3], canonical[4])
        else:
            _invariant("unknown canonical node shape")
        identities[object_id] = position
        rows.append(row)

    def type_id(canonical):
        result = identities.get(id(canonical))
        if result is None:
            _invariant("metadata reference must be an exact checked canonical object")
        return result

    environments = []
    neutral = {}
    closed = {}
    for keyed_record in index.environments:
        record = dict(keyed_record)
        arguments = tuple(type_id(item) for item in record["arguments"])
        # Compare only flat integer references, never the canonical source tuples.
        if arguments != record["argument_type_ids"]:
            _invariant("environment canonical objects disagree with its checked IDs")
        env_id, scheme, mode = record["id"], record["scheme"], record["mode"]
        if env_id != "E" + str(len(environments)):
            _invariant("environment IDs must preserve Stage01 contiguous order")
        environments.append((env_id, (scheme, mode, arguments)))
        if mode == "NEUTRAL":
            if scheme in neutral:
                _invariant("duplicate neutral environment")
            neutral[scheme] = env_id
        elif mode == "CLOSED":
            key = (scheme, arguments)
            if key in closed:
                _invariant("duplicate closed environment vector")
            closed[key] = env_id
        elif mode != "CONCRETE" or scheme is not None or arguments or env_id != "E0":
            _invariant("invalid concrete environment")

    schemes = []
    for scheme, keyed_record in index.schemes:
        record = dict(keyed_record)
        body = type_id(record["body"])
        if body != record["body_type_id"] or scheme not in neutral:
            _invariant("scheme body or neutral environment mismatch")
        schemes.append((scheme, (record["parameters"], body, neutral[scheme])))

    instantiations = []
    for name, keyed_record in index.instantiations:
        record = dict(keyed_record)
        scheme = record["scheme"]
        arguments = tuple(type_id(item) for item in record["arguments"])
        body = type_id(record["body"])
        env_id = closed.get((scheme, arguments))
        if body != record["body_type_id"] or env_id is None:
            _invariant("instantiation body or complete environment mismatch")
        # Pin instantiated()'s object identity contract as well as its metadata.
        actual_scheme, actual_arguments, actual_body = index.instantiated(name)
        if actual_scheme != scheme or type_id(actual_body) != body:
            _invariant("instantiated query disagrees with checked metadata")
        if tuple(type_id(item) for item in actual_arguments) != arguments:
            _invariant("instantiated query lost the complete argument vector")
        instantiations.append((name, (scheme, arguments, body, env_id)))

    return DeclarationIds(index.canonical_json, index.sha256, tuple(rows),
                          tuple(environments), tuple(schemes), tuple(instantiations),
                          index, tuple(sorted(identities.items())))
