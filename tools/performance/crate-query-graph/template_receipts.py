#!/usr/bin/env python3
"""Independent inspection of the canonical inference-template payload contract.

This checks the persisted commitment and ID-preserving reattachment, not source
inference or a checked-term proof. The source-key/read-edge binding and renamed
content stamp are separately exercised by actual warm/ICH/audited reader runs.
No production implementation is imported.
"""
from artifact_binary_reference import require
from artifact_binary_typed import n, s, l, value_node as fields, text, list_values as items, unpack
from artifact_binary_open import name, typed_value, type_alpha, free_names, spine_names

MARKER = 'checked-inference-template-1'
SIGNED_MARKER = 'checked-signed-inference-template-1'


def integer(source):
    require(source and source.lstrip('-').isascii() and source.lstrip('-').isdecimal(),
            'template integer spelling')
    value = int(source)
    require(str(value) == source and -(1 << 63) <= value < (1 << 63),
            'template integer range/spelling')
    return value


def type_key(source, scope=frozenset()):
    """Parse the closed framed XType key, preserving every constructor/binder."""
    row = unpack(source)
    require(bool(row), 'empty template type key')
    tag, *args = row
    if tag == 'variable' and len(args) == 1:
        identity = integer(args[0])
        require(identity in scope, 'open template dependency scheme')
        return n(40, n(30, ('int', identity)))
    if tag == 'bottom' and not args:
        return n(41)
    if tag == 'bottom-kind' and len(args) == 1:
        return n(42, kind_key(args[0]))
    if tag in ('arrow', 'application') and len(args) == 2:
        return n(43 if tag == 'arrow' else 45, *(type_key(x, scope) for x in args))
    if tag == 'constructor' and len(args) == 2:
        return n(44, s(args[0]), l(*(type_key(x, scope) for x in unpack(args[1]))))
    if tag == 'forall' and len(args) == 3:
        identity = integer(args[0])
        require(identity >= 0 and identity not in scope, 'template type binder collision')
        return n(46, n(30, ('int', identity)), type_key(args[1], scope),
                 type_key(args[2], scope | {identity}))
    require(False, 'unsupported template type key')


def kind_key(source):
    row = unpack(source)
    if row == ['star']:
        return n(10)
    require(len(row) == 3 and row[0] == 'kind-arrow', 'template kind key')
    return n(11, kind_key(row[1]), kind_key(row[2]))


def monotype_key(source):
    """Closed surface monotype, including constructor application normalization."""
    row = unpack(source)
    require(bool(row), 'empty template monotype')
    tag, *args = row
    if tag == 'arrow' and len(args) == 2:
        return n(43, *(monotype_key(x) for x in args))
    if tag == 'constructor' and len(args) == 2:
        return n(44, s(args[0]), l(*(monotype_key(x) for x in unpack(args[1]))))
    if tag == 'application' and len(args) == 2:
        function, argument = map(monotype_key, args)
        if function[1] == 44:
            constructor, arguments = fields(function, 44, 2)
            return n(44, constructor, l(*items(arguments), argument))
        return n(45, function, argument)
    require(False, 'template requires closed monotype')


def parse_template_key(source):
    row = unpack(source)
    require(bool(row), 'template structural key')
    signature = None
    if row[0] == SIGNED_MARKER:
        require(len(row) == 5, 'template structural key')
        annotation = unpack(row[1])
        require(len(annotation) == 3 and annotation[0] == 'annotation' and annotation[1] == '',
                'template monomorphic annotation')
        signature = monotype_key(annotation[2])
        row = [row[0], *row[2:]]
    else:
        require(len(row) == 4 and row[0] == MARKER, 'template structural key')
    return signature, row[1], row[2], row[3]


def expression_key(source, depth):
    row = unpack(source)
    require(bool(row), 'empty template expression key')
    tag, *args = row
    if tag == 'variable' and len(args) == 1:
        require(0 <= integer(args[0]) < depth, 'template variable slot')
    elif tag == 'lambda' and len(args) == 2:
        expression_key(args[1], depth + 1)
    elif tag == 'application' and len(args) == 2:
        for child in args:
            expression_key(child, depth)
    elif tag == 'checked' and len(args) == 2:
        monotype_key(args[0])
        expression_key(args[1], depth)
    elif tag == 'integer' and len(args) == 1:
        integer(args[0])
    elif tag == 'boolean' and len(args) == 1:
        require(args[0] in ('true', 'false'), 'template boolean spelling')
    elif tag in ('string', 'primitive') and len(args) == 1:
        require(tag != 'primitive' or bool(args[0]), 'empty template primitive')
    else:
        require(False, 'unsupported template expression key')


def rebind_template(references, original, raw_refs, members, types):
    """Recover real names from query edges, never from the claimed final body."""
    stage, owner, stamp, params, body, owned, uses = fields(original, 400, 7)
    require(text(stage) == 'raw' and text(owner) == 'template', 'template stage/owner')
    refs = list(items(references))
    require(len(refs) == 1, 'template reference inventory')
    marker, key = fields(refs[0], 2, 2)
    require(text(marker) == MARKER, 'template reference marker')
    signature, context, scheme_keys, expression = parse_template_key(text(key))
    bindings, datatypes = [], []
    for query_key, digest in raw_refs:
        parts = unpack(query_key)
        require(len(parts) == 2, 'template dependency key')
        kind, identity = parts
        require(kind in ('Binding', 'Datatype'), 'template dependency kind')
        require(kind != 'Binding' or not datatypes, 'template dependency order')
        (bindings if kind == 'Binding' else datatypes).append((identity, digest))
    require(len({x for x, _ in bindings}) == len(bindings), 'template duplicate binding edge')
    require(len({x for x, _ in datatypes}) == len(datatypes), 'template duplicate datatype edge')
    require(unpack(context) == [h for _, h in datatypes], 'template datatype context')
    schemes = [type_key(x) for x in unpack(scheme_keys)]
    require(len(schemes) == len(bindings) and bool(bindings),
            'template dependency scheme inventory')
    expression_key(expression, len(bindings))
    for (hint, _), scheme in zip(bindings, schemes):
        # An imported dependency is not necessarily exported by this interface.
        # Its actual source admission is covered by the warm/ICH controls, not
        # by treating the template's own scheme as independent evidence.
        if hint in types:
            require(type_alpha(scheme, types[hint]), 'template dependency scheme mismatch')
    parameters = [fields(x, 2, 2) for x in items(params)]
    exports = [fields(x, 2, 2) for x in items(owned)]
    require(len(parameters) == len(bindings) and len(exports) == len(members) == 1,
            'template parameter/owner inventory')
    mapping = {}
    for index, ((binder, ref), (hint, _)) in enumerate(zip(parameters, bindings)):
        identity, old_hint = name(binder)
        require(old_hint == text(ref) == 'templateParameter' + str(index),
                'template canonical parameter')
        require(identity >= 0 and identity not in mapping, 'template binder collision')
        mapping[identity] = (old_hint, hint)
    binder, export_type = exports[0]
    identity, old_hint = name(binder)
    require(old_hint == 'templateOwner', 'template canonical owner')
    require(identity >= 0 and identity not in mapping, 'template binder collision')
    mapping[identity] = (old_hint, members[0])
    typed_value(body, 'XTerm')
    typed_value(export_type, 'XType')
    if signature is not None:
        require(type_alpha(signature, export_type), 'template declaration signature mismatch')
    require(list(spine_names(body)) == [binder], 'template owned spine')
    require(list(free_names(body)) == list(items(uses)), 'template use inventory')
    require(all(x in [b for b, _ in parameters] for x in items(uses)), 'template unknown use')
    # Traverse all syntax, not a textual substitution or only top-level fields.
    def rename(value):
        if value[0] != 'node':
            return value
        if value[1] == 31:
            identity, hint = name(value)
            if identity in mapping:
                previous, current = mapping[identity]
                require(hint == previous, 'template inconsistent binder hint')
                return n(31, ('int', identity), s(current))
        return n(value[1], *(rename(child) for child in value[2]))
    rebound_params = l(*(n(2, rename(b), s(hint))
                        for (b, _), (hint, _) in zip(parameters, bindings)))
    return rebound_params, rename(body), rename(owned), rename(uses)
