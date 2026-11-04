#!/usr/bin/env python3
"""Independent schema7/8 open-pair inspection and explicit companion controls.

The frozen wire/typed oracles remain unchanged. This validates complete raw
syntax and reference identity, not proof evidence. Actual public readers plus
retained Open.audit results and their complete rebuilt bytes supply the
separate production-checker evidence.
"""
import hashlib
from artifact_binary_reference import Invalid, Limits, read_document, tree_document, repair_crc
from artifact_binary_typed import (value_node as fields, list_values as items,
    text, validate_type, builtin_datatypes, pack, unpack)


class OpenPairError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise OpenPairError(message)


def node(tag, *children):
    return ('node', tag, tuple(children))

def string(value):
    return ('text', value)

def sequence(values):
    return node(1, *values)

def fingerprint(value):
    return hashlib.sha256(tree_document([value], 6)).hexdigest()

def decoded(raw, schema, family=None):
    require(isinstance(raw, bytes), 'comparison input must be original bytes')
    doc = read_document(raw, schema)
    require(len(doc.roots) == 1, 'exactly one root')
    if family:
        validate_type(doc, doc.roots[0], family)
    values = doc.values()
    require(tree_document(values, schema) == raw, 'canonical whole binary bytes')
    return values[0]

OPEN_ROOT_WORK = 64 * 1024**2
OPEN_PACKAGE_WORK = 256 * 1024**2
OPEN_FORMATS = {7: 'MLF-OPEN-CRATE-1/checker-1', 8: 'MLF-OPEN-CRATE-2/checker-1'}


def open_document(raw):
    """Keep the frozen default codec unchanged; schema8 owns a bounded root sum."""
    require(isinstance(raw, bytes) and len(raw) >= 20, 'complete open binary header')
    schema = int.from_bytes(raw[16:20], 'little')
    require(schema in OPEN_FORMATS, 'unsupported open schema')
    limits = Limits() if schema == 7 else Limits(work=OPEN_PACKAGE_WORK)
    document = read_document(raw, schema, limits)
    if schema == 8:
        require(all(work <= OPEN_ROOT_WORK for work in document.expanded_work),
                'open per-root expanded work cap')
    values = document.values()
    require(tree_document(values, schema) == raw, 'canonical whole open binary bytes')
    if schema == 7:
        require(len(values) == 1, 'exactly one schema7 open root')
        opened = fields(values[0], 430, 6)
    else:
        require(bool(values), 'open header root required')
        header = fields(values[0], 432, 6)
        require(header[5][0] == 'int' and header[5][1] == len(values) - 1,
                'open fragment count mismatch')
        for fragment in values[1:]:
            fields(fragment, 401, 7)
        opened = (*header[:5], sequence(values[1:]))
    return schema, document, opened


def open_bytes(schema, opened, header_tag=None):
    """Fixture writer preserves the selected framing, including mutation cases."""
    require(schema in OPEN_FORMATS, 'unsupported fixture open schema')
    if schema == 7:
        return tree_document([node(430 if header_tag is None else header_tag, *opened)], 7)
    fragments = items(opened[5])
    header = node(432 if header_tag is None else header_tag,
                  *opened[:5], ('int', len(fragments)))
    return tree_document([header, *fragments], 8)


def syntax_equal(left, right):
    """Complete DAG syntax equality, without recursion or hash-only evidence."""
    pending, seen = [(left, right)], set()
    while pending:
        a, b = pending.pop()
        if type(a) is not type(b):
            return False
        if isinstance(a, tuple):
            key = id(a), id(b)
            if key in seen:
                continue
            seen.add(key)
            if len(a) != len(b):
                return False
            pending.extend(zip(a, b))
        elif a != b:
            return False
    return True


def compare_retained_audit(original, audited, dependency_interfaces):
    before = inspect_pair(original, dependency_interfaces)
    after = inspect_pair(audited, dependency_interfaces)
    require(after['schema'] == 8, 'retained audit writer must emit schema8')
    left = fields(before['interface'], 242, 13)
    right = fields(after['interface'], 242, 13)
    require(all(syntax_equal(left[i], right[i]) for i in range(13) if i != 11),
            'retained audit changed complete interface semantics')
    # Only the wire-family marker and paired object digest may change in 7 -> 8.
    # This includes every ordered final field and every verified reference hash.
    require(syntax_equal(before['opened'][1:], after['opened'][1:]),
            'retained audit changed complete fragment semantics')
    exact = tuple(audited) == tuple(original)
    if before['schema'] == 8:
        require(exact, 'retained schema8 audit rebuild changed original pair bytes')
    return {'retained_audit_rebuild_exact': exact,
            'retained_audit_semantics_exact': True,
            'retained_audit_schema_transition': [before['schema'], after['schema']]}


def keyed(values, label):
    result = {}
    for key, value in values:
        require(key not in result, 'duplicate ' + label + ': ' + key)
        result[key] = value
    return result

def name(value):
    identity, hint = fields(value, 31, 2)
    require(identity[0] == 'int', 'XName identity')
    return identity[1], text(hint)

def variable(value):
    identity, = fields(value, 30, 1)
    require(identity[0] == 'int', 'XTyVar identity')
    return identity[1]

def type_alpha(a, b, left=None, right=None, depth=0):
    """Only external parameter schemes use this binder-aware comparison."""
    left = {} if left is None else left
    right = {} if right is None else right
    require(a[0] == b[0] == 'node', 'external type syntax')
    if a[1] != b[1]:
        return False
    xs, ys = fields(a), fields(b)
    if len(xs) != len(ys):
        return False
    tag = a[1]
    if tag == 40:
        x, y = variable(xs[0]), variable(ys[0])
        return ((x in left) == (y in right) and
                (left[x] == right[y] if x in left else x == y))
    if tag == 46:
        x, y = variable(xs[0]), variable(ys[0])
        return (type_alpha(xs[1], ys[1], left, right, depth) and
                type_alpha(xs[2], ys[2], {**left, x: depth},
                           {**right, y: depth}, depth + 1))
    if tag in (43, 45):
        return all(type_alpha(x, y, left, right, depth) for x, y in zip(xs, ys))
    if tag == 44:
        ax, bx = items(xs[1]), items(ys[1])
        return xs[0] == ys[0] and len(ax) == len(bx) and all(
            type_alpha(x, y, left, right, depth) for x, y in zip(ax, bx))
    require(tag in (41, 42), 'unknown external type constructor')
    return a == b

def same_declaration(a, b):
    if a == b:
        return False
    require({a[1], b[1]} == {26, 27}, 'datatype structure changed')
    simple, explicit = (a, b) if a[1] == 26 else (b, a)
    sn, sp, sc = fields(simple, 26, 3)
    en, ep, ec = fields(explicit, 27, 3)
    pairs = [fields(p, 2, 2) for p in items(ep)]
    require(sn == en and sc == ec, 'datatype name/constructor/field changed')
    require(tuple(p[0] for p in pairs) == items(sp), 'datatype parameter spelling/order changed')
    require(all(p[1] == node(10) for p in pairs), 'non-Star datatype kind changed')
    return True

def declaration_hash_value(value):
    """The declared reference-hash format, NEVER a content equality transform."""
    key, parameters, constructors = fields(value, arity=3)
    require(value[1] in (26, 27), 'datatype reference syntax')
    binders = ([(text(p), node(10)) for p in items(parameters)] if value[1] == 26
               else [(text(p), k) for p, k in (fields(x, 2, 2) for x in items(parameters))])
    scope = {p: 'type:' + str(i) for i, (p, _) in enumerate(binders)}
    def field(v, env, depth):
        xs = fields(v)
        if v[1] == 20:
            return node(20, string(env.get(text(xs[0]), text(xs[0]))))
        if v[1] in (21, 23):
            a, b = (field(x, env, depth) for x in xs)
            if v[1] == 23 and a[1] == 22:
                return node(22, a[2][0], sequence([*items(a[2][1]), b]))
            return node(v[1], a, b)
        if v[1] == 22:
            return node(22, xs[0], sequence(field(x, env, depth) for x in items(xs[1])))
        require(v[1] == 24, 'unknown datatype field')
        fresh = 'type:' + str(depth)
        return node(24, string(fresh), xs[1],
                    field(xs[2], {**env, text(xs[0]): fresh}, depth + 1))
    return node(27, key,
        sequence(node(2, string('type:' + str(i)), k) for i, (_, k) in enumerate(binders)),
        sequence(node(25, fields(c, 25, 2)[0],
            sequence(field(x, scope, len(binders)) for x in items(fields(c, 25, 2)[1])))
            for c in items(constructors)))

def interface_association(iface):
    fs = list(fields(iface, 242, 13))
    fs[1] = sequence(node(3, fields(d, 3, 3)[0], string(''), fields(d, 3, 3)[2])
                     for d in items(fs[1]))
    fs[11] = string('open-object')
    return fingerprint(node(242, *fs))

def compatibility_identity():
    return fingerprint(node(431, string('MLF/shared-haskell-v1'),
        string('MLF-OPEN-CRATE-1/checker-1'), sequence(builtin_datatypes())))

def pattern_names(pattern):
    fs = fields(pattern)
    if pattern[1] == 90:
        possible = items(fs[1])
    else:
        require(pattern[1] == 91, 'unknown pattern')
        possible = [fs[0]]
    result = []
    for item in possible:
        require(item[1] in (4, 5), 'pattern Maybe')
        if item[1] == 5:
            value, = fields(item, 5, 1)
            name(value)
            result.append(value)
        else:
            fields(item, 4, 0)
    return result

def free_names(term):
    """Ordered, lexical free-name occurrences, then first-occurrence uniqueness."""
    def walk(value, bound):
        xs = fields(value)
        tag = value[1]
        if tag == 70:
            return [] if name(xs[0])[0] in bound else [xs[0]]
        if tag == 71:
            return walk(xs[2], bound | {name(xs[0])[0]})
        if tag == 72:
            return walk(xs[0], bound) + walk(xs[1], bound)
        if tag == 73:
            return walk(xs[2], bound)
        if tag == 74:
            return walk(xs[0], bound)
        if tag == 75:
            return walk(xs[1], bound) + walk(xs[2], bound | {name(xs[0])[0]})
        if tag == 76:
            bindings = [fields(x, 3, 3) for x in items(xs[0])]
            extended = bound | {name(x[0])[0] for x in bindings}
            return [n for _, _, body in bindings for n in walk(body, extended)] + walk(xs[1], extended)
        if tag == 83:
            result = walk(xs[0], bound)
            for alternative in items(xs[2]):
                pattern, body = fields(alternative, 92, 2)
                result += walk(body, bound | {name(n)[0] for n in pattern_names(pattern)})
            return result
        if tag == 84:
            return walk(xs[1], bound)
        require(tag in (77, 78, 79, 80, 81, 82), 'unknown term in free-name inventory')
        return []
    seen, result = set(), []
    for value in walk(term, set()):
        identity = name(value)[0]
        if identity not in seen:
            result.append(value)
            seen.add(identity)
    return result

def spine_names(term):
    result = []
    while term[1] in (75, 76):
        fs = fields(term)
        if term[1] == 75:
            result.append(fs[0])
            term = fs[2]
        else:
            result.extend(fields(x, 3, 3)[0] for x in items(fs[0]))
            term = fs[1]
    require(term == node(82, string('()'), sequence([])), 'unexpected declaration-spine tail')
    return result


def typed_value(value, family):
    raw = tree_document([value], 6)
    document = read_document(raw, 6)
    validate_type(document, document.roots[0], family)


def inspect_pair(pair, dependency_interfaces):
    """Inspect an original open pair and its exact complete dependency closure."""
    try:
        return _inspect_pair(pair, dependency_interfaces)
    except Invalid as error:
        raise OpenPairError(str(error)) from error


def _inspect_pair(pair, dependency_interfaces):
    require(type(pair) is tuple and len(pair) == 2, 'complete open artifact pair')
    interface = decoded(pair[0], 3, 'CrateInterfaceFields')
    header = fields(interface, 242, 13)
    schema, document, opened = open_document(pair[1])
    require(text(header[11]) == hashlib.sha256(pair[1]).hexdigest(), 'open object SHA mismatch')
    require(text(opened[0]) == OPEN_FORMATS[schema], 'wrong open package family')
    require(text(opened[1]) == compatibility_identity(), 'wrong open compatibility identity')
    dependencies = [decoded(raw, 3, 'CrateInterfaceFields') for raw in dependency_interfaces]
    by_name = keyed([(text(fields(value, 242, 13)[0]), value) for value in dependencies],
                    'dependency interface identity')
    root = text(header[0])
    require(root not in by_name, 'open root included among dependencies')
    reached, visiting = set(), set()
    def visit(identity):
        require(identity in by_name, 'missing dependency interface')
        require(identity not in visiting and identity != root, 'cyclic dependency interface')
        if identity in reached:
            return
        visiting.add(identity)
        for row in items(fields(by_name[identity], 242, 13)[1]):
            visit(text(fields(row, 3, 3)[0]))
        visiting.remove(identity)
        reached.add(identity)
    for row in items(header[1]):
        visit(text(fields(row, 3, 3)[0]))
    require(reached == set(by_name), 'extra dependency interface')
    expected_association = pack([interface_association(interface)] +
                               [interface_association(by_name[key]) for key in sorted(by_name)])
    require(text(opened[2]) == expected_association, 'open complete interface association')
    interfaces = [interface, *dependencies]
    types = keyed([(text(key), value) for iface in interfaces for key, value in
                   (fields(row, 2, 2) for row in items(fields(iface, 242, 13)[9]))],
                  'binding ownership')
    declarations = keyed([(text(fields(value, arity=3)[0]), value) for iface in interfaces
                          for value in items(fields(iface, 242, 13)[8])], 'datatype ownership')
    wire_work = sum(document.expanded_work[index] for index in document.roots)
    reference_work = 0
    def references(value, available, encode, label):
        nonlocal reference_work
        rows = [fields(row, 2, 2) for row in items(value)]
        keys = [text(row[0]) for row in rows]
        require(keys == sorted(set(keys)), label + ' reference order or duplicate')
        for key, digest in rows:
            key = text(key)
            require(key in available, label + ' reference out of scope')
            value = encode(available[key])
            if schema == 8:
                raw = tree_document([value], 6)
                hashed = read_document(raw, 6)
                used = sum(hashed.expanded_work[index] for index in hashed.roots)
                require(used <= OPEN_PACKAGE_WORK - wire_work - reference_work,
                        'open combined reference and wire work cap')
                reference_work += used
                actual = hashlib.sha256(raw).hexdigest()
            else:
                actual = fingerprint(value)
            require(text(digest) == actual, label + ' reference hash')
        return keys
    binding_refs = references(opened[3], types, lambda value: value, 'binding')
    data_refs = references(opened[4], declarations, declaration_hash_value, 'datatype')
    groups, used_bindings, used_data, exports = set(), set(), set(), []
    fragments = list(items(opened[5]))
    require(bool(fragments), 'nonempty seed fragment inventory')
    for fragment in fragments:
        group, receipt, data_names, parameters, body, owned, used = fields(fragment, 401, 7)
        group = text(group)
        require(group and group not in groups, 'duplicate or empty fragment group')
        groups.add(group)
        require(bool(text(receipt)), 'empty checked receipt')
        typed_value(body, 'XTerm')
        for value in (*items(parameters), *items(owned), *items(used)):
            typed_value(value, 'XName')
            require(name(value)[0] >= 0, 'negative fragment binder identity')
        params, owners, uses = list(items(parameters)), list(items(owned)), list(items(used))
        require(len({name(value)[0] for value in params}) == len(params), 'duplicate parameter identity')
        require(len({name(value)[0] for value in owners}) == len(owners), 'duplicate owned identity')
        require(owners == spine_names(body), 'complete ordered owned binder inventory')
        require(uses == free_names(body) and all(value in params for value in uses),
                'complete exact used-reference inventory')
        for value in params + owners:
            key = name(value)[1]
            require(key in types, 'missing fragment binding type')
            used_bindings.add(key)
        exports.extend((name(value)[1], types[name(value)[1]]) for value in owners)
        names = [text(value) for value in items(data_names)]
        require(len(names) == len(set(names)), 'duplicate fragment datatype')
        require(all(key in declarations for key in names), 'missing fragment datatype')
        used_data.update(names)
    require(binding_refs == sorted(used_bindings), 'complete binding reference inventory')
    require(data_refs == sorted(used_data), 'complete datatype reference inventory')
    require(keyed(exports, 'owned fragment binding') ==
            keyed([(text(key), value) for key, value in
                   (fields(row, 2, 2) for row in items(header[9]))], 'interface binding'),
            'complete crate ownership and type inventory')
    return {'schema': schema, 'interface': interface, 'opened': opened, 'types': types, 'declarations': declarations,
            'summary': {'identity': root,
                        'dependencies': [tuple(text(x) for x in fields(row, 3, 3)) for row in items(header[1])],
                        'modules': [text(value) for value in items(header[2])], 'entry': text(header[10])},
            'accounting': {'schema': schema, 'wire_expanded_work': wire_work,
                           'reference_hash_expanded_work': reference_work if schema == 8 else None,
                           'combined_expanded_work': wire_work + reference_work if schema == 8 else None,
                           'fragment_count': len(fragments), 'binding_references': len(binding_refs),
                           'datatype_references': len(data_refs),
                           'metadata_sha256': hashlib.sha256(pair[0]).hexdigest(),
                           'object_sha256': hashlib.sha256(pair[1]).hexdigest()}}



def legacy_fingerprint(source):
    """Separate.fingerprint's two residues over Unicode scalars, not UTF-8 bytes."""
    a, b = 0, 1
    for scalar in source:
        a = (a * 65599 + ord(scalar)) % 2147483647
        b = (b * 131 + ord(scalar)) % 2147483629
    return str(a) + '-' + str(b)


def legacy_fields(source, count=None):
    values = unpack(source)
    require(pack(values) == source, 'canonical legacy scalar framing')
    require(count is None or len(values) == count, 'complete legacy field count')
    return values


def legacy_fingerprint_values(legacy_pair):
    """Validate actual old-format text framing and every declared text digest.

    This is not a text-to-AST oracle. Actual public readers must rebuild the
    complete closed pair byte-for-byte; compare_companion requires that receipt.
    The independent parsed comparison still handles complete open/closed bodies.
    """
    require(len(legacy_pair) == 2 and all(isinstance(raw, bytes) for raw in legacy_pair),
            'actual complete legacy pair bytes')
    metadata, object_text = (raw.decode('utf-8') for raw in legacy_pair)
    mf = legacy_fields(metadata, 14)
    require(mf[0] == 'MLFCI-5', 'genuine legacy metadata family')
    require(mf[13] == legacy_fingerprint(pack(mf[:13])), 'legacy metadata fingerprint mismatch')
    obj = legacy_fields(object_text, 4)
    require(obj[0] == 'MLFCO-2', 'genuine complete legacy pooled object family')
    require(obj[1] == mf[1], 'legacy object identity mismatch')
    require(obj[2] == legacy_fingerprint(metadata), 'legacy interface fingerprint mismatch')
    payload = obj[3]
    digest = legacy_fingerprint(payload)
    require(mf[11] == digest, 'legacy pooled fingerprint mismatch')
    declarations, record_text = legacy_fields(payload, 2)
    pool = legacy_fields(declarations)
    require(pool == sorted(set(pool)), 'canonical complete legacy datatype pool')
    referenced = set()
    def references(source):
        indices = []
        for index in legacy_fields(source):
            require(index.isascii() and index.isdecimal() and str(int(index)) == index,
                    'canonical legacy datatype index')
            number = int(index)
            require(number < len(pool), 'legacy datatype index range')
            indices.append(number)
            referenced.add(number)
        return indices
    units = []
    for record in legacy_fields(record_text):
        header_refs, body_refs, contents = legacy_fields(record, 3)
        header_indices, body_indices = references(header_refs), references(body_refs)
        family, header, body = legacy_fields(contents, 3)
        require(family == 'MLFF-2', 'genuine contextual legacy fragment family')
        hf = legacy_fields(header, 8)
        require(hf[0] == 'MLFI-4', 'genuine legacy unit metadata family')
        require(all(hf[i] == '' for i in (2, 3, 4, 5)),
                'unrepresented legacy companion metadata')
        for binding in legacy_fields(hf[6]):
            legacy_fields(binding, 2)
        require(hf[7] == legacy_fingerprint(body), 'legacy contextual body fingerprint mismatch')
        complete = ''.join(pool[i] + '\n' for i in body_indices) + body
        units.append({'name': hf[1], 'fingerprint': legacy_fingerprint(complete),
                      'header_data_count': len(header_indices), 'body_data_count': len(body_indices)})
    require(referenced == set(range(len(pool))), 'complete legacy datatype pool reference inventory')
    return {'identity': mf[1], 'crate_fingerprint': digest, 'units': units}


def closed_fingerprint_mutations(closed_pair, legacy_pair):
    """Only stored checksum fields change; paired/embedded metadata and CRC agree."""
    ci = decoded(closed_pair[0], 3, 'CrateInterfaceFields')
    closed = fields(decoded(closed_pair[1], 4, 'CrateObjectFields'), 243, 3)
    require(closed[0] == node(6) and closed[1] == ci, 'ordinary paired closed mutation input')
    units = list(items(closed[2]))
    require(bool(units), 'nonempty closed unit fingerprint controls')
    expected = legacy_fingerprint_values(legacy_pair)
    digest = expected['crate_fingerprint']
    def changed_pair(changed_units, crate_digest):
        cf = list(fields(ci, 242, 13))
        cf[11] = string(crate_digest)
        metadata = node(242, *cf)
        return (tree_document([metadata], 3),
                tree_document([node(243, closed[0], metadata, sequence(changed_units))], 4))
    cases = [('closed-crate-fingerprint',
              changed_pair(units, '0-0' if digest != '0-0' else '0-1'),
              'closed crate fingerprint mismatch')]
    for index, unit in enumerate(units):
        header, term = fields(unit, 241, 2)
        hf = list(fields(header, 240, 8))
        hf[7] = string('0-0' if text(hf[7]) != '0-0' else '0-1')
        changed_units = list(units)
        changed_units[index] = node(241, node(240, *hf), term)
        # encodeContextualObject replaces stored hf[7] with the body digest.
        # Recomputing the canonical outer payload digest therefore leaves it
        # unchanged, so rejection must reach the separate unit-fingerprint check.
        recomputed = legacy_fingerprint_values(legacy_pair)['crate_fingerprint']
        cases.append(('closed-unit-fingerprint-' + str(index),
                      changed_pair(changed_units, recomputed),
                      'closed unit fingerprint mismatch: ' + str(index)))
    return cases


def legacy_fingerprint_mutations(legacy_pair):
    """Checksum-only text damage, with enclosing checksum/framing recomputation."""
    metadata, object_text = (raw.decode('utf-8') for raw in legacy_pair)
    original_mf, original_obj = legacy_fields(metadata, 14), legacy_fields(object_text, 4)
    def different(value):
        return '0-0' if value != '0-0' else '0-1'
    def rebuilt(mf, obj):
        return pack(mf).encode('utf-8'), pack(obj).encode('utf-8')
    mf, obj = list(original_mf), list(original_obj)
    mf[13] = different(mf[13])
    # Bind the object to the changed metadata so only its self-checksum fails.
    obj[2] = legacy_fingerprint(pack(mf))
    cases = [('legacy-metadata-fingerprint', rebuilt(mf, obj),
              'legacy metadata fingerprint mismatch')]
    obj = list(original_obj)
    obj[2] = different(obj[2])
    cases.append(('legacy-interface-fingerprint', rebuilt(original_mf, obj),
                  'legacy interface fingerprint mismatch'))
    mf, obj = list(original_mf), list(original_obj)
    mf[11] = different(mf[11])
    mf[13] = legacy_fingerprint(pack(mf[:13]))
    obj[2] = legacy_fingerprint(pack(mf))
    cases.append(('legacy-pooled-fingerprint', rebuilt(mf, obj),
                  'legacy pooled fingerprint mismatch'))
    pool, record_text = legacy_fields(original_obj[3], 2)
    records = legacy_fields(record_text)
    require(bool(records), 'nonempty legacy contextual fingerprint control')
    for index, record in enumerate(records):
        rf = legacy_fields(record, 3)
        fragment = legacy_fields(rf[2], 3)
        hf = legacy_fields(fragment[1], 8)
        hf[7] = different(hf[7])
        fragment[1] = pack(hf)
        rf[2] = pack(fragment)
        changed_records = list(records)
        changed_records[index] = pack(rf)
        mf, obj = list(original_mf), list(original_obj)
        obj[3] = pack([pool, pack(changed_records)])
        mf[11] = legacy_fingerprint(obj[3])
        mf[13] = legacy_fingerprint(pack(mf[:13]))
        obj[2] = legacy_fingerprint(pack(mf))
        cases.append(('legacy-contextual-body-fingerprint-' + str(index), rebuilt(mf, obj),
                      'legacy contextual body fingerprint mismatch'))
    return cases


def compare_companion(closed_pair, open_pair, dependency_interfaces, audited_pair,
                      legacy_pair, legacy_rebuilt_pair):
    """Complete parsed bodies plus actual-reader-bound legacy text fingerprints.

    The independent text checks do not claim to parse text semantics. The caller
    supplies the actual public legacy reader/writer output as a byte receipt.
    """
    observed = inspect_pair(open_pair, dependency_interfaces)
    ci = decoded(closed_pair[0], 3, 'CrateInterfaceFields')
    closed = fields(decoded(closed_pair[1], 4, 'CrateObjectFields'), 243, 3)
    cf, of = fields(ci, 242, 13), fields(observed['interface'], 242, 13)
    require(closed[0] == node(6), 'ordinary closed companion required')
    require(closed[1] == ci, 'closed embedded interface differs from paired interface')
    require(all(cf[index] == of[index] for index in range(13) if index != 11),
            'complete companion interface content changed')
    legacy = legacy_fingerprint_values(legacy_pair)
    require(legacy['identity'] == text(cf[0]), 'closed/legacy crate identity')
    require(text(cf[11]) == legacy['crate_fingerprint'], 'closed crate fingerprint mismatch')
    units, fragments = items(closed[2]), items(observed['opened'][5])
    require(len(units) == len(legacy['units']), 'complete legacy companion fragment count')
    require(len(units) == len(fragments), 'complete companion fragment count')
    for index, (unit, fragment, legacy_unit) in enumerate(zip(units, fragments, legacy['units'])):
        header, term = fields(unit, 241, 2)
        hf = fields(header, 240, 8)
        require(text(hf[0]) == legacy_unit['name'], 'ordered closed/legacy unit identity')
        require(text(hf[7]) == legacy_unit['fingerprint'],
                'closed unit fingerprint mismatch: ' + str(index))
        group, receipt, data_names, parameters, body, owned, used = fields(fragment, 401, 7)
        require(group == hf[0], 'ordered companion fragment identity')
        require(all(hf[index] == sequence([]) for index in (1, 2, 4, 5)),
                'unrepresented closed fragment metadata')
        ds, term = fields(term, 84, 2)
        require(ds == hf[3], 'closed header and body datatype context')
        require(len(items(hf[3])) == legacy_unit['header_data_count'] and
                len(items(ds)) == legacy_unit['body_data_count'], 'complete legacy datatype context count')
        params = []
        while term[0] == 'node' and term[1] == 71:
            parameter, ty, term = fields(term, 71, 3)
            params.append((parameter, ty))
        require(term == body, 'complete original fragment body changed')
        require(list(items(parameters)) == [value for value, _ in params], 'ordered parameter names')
        for parameter, ty in params:
            require(type_alpha(ty, observed['types'][name(parameter)[1]]), 'external parameter scheme')
        exports = tuple(node(2, string(name(value)[1]), observed['types'][name(value)[1]])
                        for value in items(owned))
        require(exports == items(hf[6]), 'complete closed fragment export schemes')
        names = [text(value) for value in items(data_names)]
        require(names == [text(fields(value, arity=3)[0]) for value in items(ds)],
                'ordered datatype context')
        for key, declaration in zip(names, items(ds)):
            same_declaration(declaration, observed['declarations'][key])
    require(tuple(legacy_rebuilt_pair) == closed_pair,
            'actual public legacy reader/writer differs from complete closed pair')
    audit = compare_retained_audit(open_pair, audited_pair, dependency_interfaces)
    return {**observed['accounting'], 'complete_companion_content': True,
            **audit, 'legacy_public_rebuild_exact': True,
            'closed_crate_fingerprint_exact': True, 'closed_unit_fingerprints_exact': len(units),
            'fingerprint_evidence': 'independent framed text digests, actual public text-to-binary receipt'}


def repinned(pair, body):
    values = list(fields(decoded(pair[0], 3, 'CrateInterfaceFields'), 242, 13))
    values[11] = string(hashlib.sha256(body).hexdigest())
    return tree_document([node(242, *values)], 3), body


def mutation_cases(pair):
    """Authored invalid variants. Expected public errors do not come from execution."""
    schema, document, original = open_document(pair[1])
    opened = list(original)
    def change(index, value):
        fields_ = list(opened)
        fields_[index] = value
        return open_bytes(schema, fields_)
    cases = []
    wrong_format = change(0, string('MLF-OPEN-CRATE-999/checker-1'))
    cases.append(('wrong-open-family', repinned(pair, wrong_format),
                  'open crate checker/compiler version mismatch; rebuild object'))
    cases.append(('open-checksum-priority', (pair[0], wrong_format), 'open crate SHA mismatch'))
    bad_crc = bytearray(pair[1])
    bad_crc[76] ^= 1
    bad_crc = bytes(bad_crc)
    cases.append(('open-sha-before-crc', (pair[0], bad_crc), 'open crate SHA mismatch'))
    cases.append(('open-crc-with-matching-sha', repinned(pair, bad_crc), 'binary checksum mismatch'))
    cases.append(('wrong-open-compatibility', repinned(pair, change(1, string('0' * 64))),
                  'open crate checker/compiler version mismatch; rebuild object'))
    cases.append(('wrong-open-association', repinned(pair, change(2, string('wrong-association'))),
                  'open crate interface mismatch'))
    wrong_header = open_bytes(schema, opened, header_tag=429)
    cases.append(('wrong-open-header', repinned(pair, wrong_header), 'invalid open crate header'))
    version = bytearray(pair[1])
    version[8:12] = (2).to_bytes(4, 'little')
    version = repair_crc(version)
    cases.append(('wrong-open-wire-version', repinned(pair, version), 'unsupported binary format version'))
    rows = list(items(opened[3]))
    require(bool(rows), 'nonempty source binding reference mutation')
    key, _ = fields(rows[0], 2, 2)
    rows[0] = node(2, key, string('0' * 64))
    cases.append(('wrong-open-reference', repinned(pair, change(3, sequence(rows))),
                  'open crate dependency changed: ' + text(key)))
    if schema == 8:
        roots = list(document.values())
        header = list(fields(roots[0], 432, 6))
        def new_header(count):
            return tree_document([node(432, *header[:5], count), *roots[1:]], 8)
        cases.append(('open-empty-roots', repinned(pair, tree_document([], 8)),
                      'open crate root count'))
        cases.append(('open-wrong-fragment-count',
                      repinned(pair, new_header(('int', len(roots)))),
                      'open crate fragment count mismatch'))
        cases.append(('open-noninteger-fragment-count',
                      repinned(pair, new_header(('bits', len(roots) - 1))),
                      'invalid open crate fragment count'))
        require(len(roots) > 1, 'nonempty root mutation seed')
        reordered = tree_document([roots[1], roots[0], *roots[2:]], 8)
        cases.append(('open-header-after-final', repinned(pair, reordered),
                      'invalid open crate header'))
        duplicate = list(opened)
        duplicate[5] = sequence([*items(opened[5]), items(opened[5])[0]])
        cases.append(('open-duplicate-final', repinned(pair, open_bytes(schema, duplicate)),
                      'duplicate open crate fragment'))
        invalid = list(opened)
        fragments = list(items(opened[5]))
        fragments[0] = node(400, *fields(fragments[0], 401, 7))
        invalid[5] = sequence(fragments)
        cases.append(('open-wrong-final-envelope', repinned(pair, open_bytes(schema, invalid)),
                      'invalid final open crate fragment'))
    return cases


def resource_mutation_cases(pair, dependency_interfaces):
    """Tiny physical DAGs exercise the actual reader's early resource gates.

    No expanded syntax is materialized and no production writer is called.
    Original finals, binding references, metadata and ownership are retained.
    Added finals have no exports, parameters or free references. Their datatype
    contexts and SHA references come from the authenticated dependency closure.
    """
    observed = inspect_pair(pair, dependency_interfaces)
    schema, document, opened = open_document(pair[1])
    require(schema == 8, 'resource controls require the actual schema8 seed')
    data_names = sorted(observed['declarations'])
    require(bool(data_names), 'authenticated seed closure needs datatype definitions')
    context = sequence([string(key) for key in data_names])
    context_work = 1 + sum(1 + len(key.encode('utf-8')) for key in data_names)
    augmented = list(opened)
    augmented[4] = sequence([
        node(2, string(key), string(fingerprint(declaration_hash_value(
            observed['declarations'][key])))) for key in data_names])
    opened = tuple(augmented)
    baseline_document = read_document(open_bytes(8, opened), 8)
    baseline = sum(baseline_document.expanded_work[index]
                   for index in baseline_document.roots)
    require(baseline < OPEN_ROOT_WORK, 'small resource-control seed required')
    bindings = list(items(opened[3]))
    declarations = list(items(opened[4]))
    require(bool(bindings) and bool(declarations),
            'resource seed must exercise both actual reference hash paths')
    def measured_hash(value):
        raw = tree_document([value], 6)
        hashed = read_document(raw, 6)
        return sum(hashed.expanded_work[index] for index in hashed.roots)
    binding_work = sum(measured_hash(observed['types'][text(fields(row, 2, 2)[0])])
                       for row in bindings)
    declaration_work = sum(measured_hash(declaration_hash_value(
        observed['declarations'][text(fields(row, 2, 2)[0])])) for row in declarations)
    first_binding = observed['types'][text(fields(bindings[0], 2, 2)[0])]
    first_declaration = declaration_hash_value(
        observed['declarations'][text(fields(declarations[0], 2, 2)[0])])
    # With remainder 1, a nonempty constructor reaches the bounded arity gate;
    # with remainder 0, even its one-root plan reaches the bounded count gate.
    require(first_binding[0] == first_declaration[0] == 'node' and
            bool(fields(first_binding)) and bool(fields(first_declaration)),
            'reference remainder diagnostics need nonempty constructor roots')

    memo = {}
    def term_with_work(work):
        require(work >= 2, 'minimum resource-control term work')
        if work not in memo:
            if work <= 4:
                memo[work] = node(80, string('x' * (work - 2)))
            else:
                left = (work - 1) // 2
                memo[work] = node(72, term_with_work(left),
                                  term_with_work(work - 1 - left))
        return memo[work]

    def final_with_work(index, work):
        name = 'resource-final-' + str(index)
        receipt = 'resource-rejection-before-audit'
        # 401, two texts, the real datatype context, three empty lists, then body.
        overhead = 6 + len(name.encode('utf-8')) + len(receipt.encode('utf-8')) + context_work
        return node(401, string(name), string(receipt), context, sequence([]),
                    term_with_work(work - overhead), sequence([]), sequence([]))

    cases, witnesses = [], {}
    def save(label, extra, expected, target):
        changed = list(opened)
        changed[5] = sequence([*items(opened[5]), *extra])
        raw = open_bytes(8, changed)
        # The explicit wider sum here measures a deliberately invalid fixture.
        # It does not alter any default reader or permit per-root overflows.
        measured = read_document(raw, 8, Limits(work=(1 << 31) - 1))
        root_work = [measured.expanded_work[index] for index in measured.roots]
        require(all(work <= OPEN_ROOT_WORK for work in measured.expanded_work),
                'resource negative accidentally exceeded a per-node/root cap')
        require(sum(root_work) == target, 'resource negative exact wire-work witness')
        require(len(raw) <= len(pair[1]) + 65536,
                'resource negative must remain a tiny physical DAG')
        require(changed[:5] == list(opened[:5]),
                'resource negative changed legitimate metadata/references')
        pinned = repinned(pair, raw)
        cases.append((label, pinned, expected))
        witnesses[label] = {
            'physical_bytes': len(raw), 'physical_nodes': len(measured.nodes),
            'wire_work': target, 'root_work': root_work,
            'actual_binding_hash_work': binding_work,
            'actual_declaration_hash_work': declaration_work,
            'remaining_before_references': OPEN_PACKAGE_WORK - target,
            'remaining_after_binding_hashes': OPEN_PACKAGE_WORK - target - binding_work,
            'metadata_and_binding_references_unchanged': True,
            'datatype_references_from_authenticated_interfaces': data_names,
            'original_finals_retained': True}

    def at_work(label, target, expected):
        remaining = target - baseline
        quotient, remainder = divmod(remaining, 4)
        weights = [quotient + (index < remainder) for index in range(4)]
        require(min(weights) > 128 and max(weights) <= OPEN_ROOT_WORK,
                'resource negative root distribution')
        save(label, [final_with_work(index, work) for index, work in enumerate(weights)],
             expected, target)

    at_work('open-aggregate-unique-finals', OPEN_PACKAGE_WORK + 1,
            'binary expanded root-work limit exceeded')
    repeated = final_with_work(0, OPEN_ROOT_WORK)
    save('open-aggregate-repeated-root', [repeated] * 4,
         'binary expanded root-work limit exceeded', baseline + 4 * OPEN_ROOT_WORK)
    for remaining in (1, 0):
        at_work('open-combined-binding-remainder-' + str(remaining),
                OPEN_PACKAGE_WORK - remaining, 'binary list count limit exceeded')
        at_work('open-combined-declaration-remainder-' + str(remaining),
                OPEN_PACKAGE_WORK - binding_work - remaining,
                'binary list count limit exceeded')
    return cases, witnesses


def independent_controls(pair, closed_pair, dependency_interfaces, audited_pair,
                         legacy_pair, legacy_rebuilt_pair):
    """Run exact parser negatives against the real seed, without a target-derived oracle."""
    good = compare_companion(closed_pair, pair, dependency_interfaces, audited_pair,
                             legacy_pair, legacy_rebuilt_pair)
    rejected = []
    for label, damaged, expected in closed_fingerprint_mutations(closed_pair, legacy_pair):
        try:
            compare_companion(damaged, pair, dependency_interfaces, audited_pair,
                              legacy_pair, legacy_rebuilt_pair)
        except OpenPairError as error:
            require(str(error) == expected, 'closed fingerprint negative stopped at wrong check: ' + label)
            rejected.append(label)
        else:
            raise OpenPairError('closed fingerprint negative accepted: ' + label)
    for label, damaged, expected in legacy_fingerprint_mutations(legacy_pair):
        try:
            compare_companion(closed_pair, pair, dependency_interfaces, audited_pair,
                              damaged, legacy_rebuilt_pair)
        except OpenPairError as error:
            require(str(error) == expected, 'legacy fingerprint negative stopped at wrong check: ' + label)
            rejected.append(label)
        else:
            raise OpenPairError('legacy fingerprint negative accepted: ' + label)
    for label, damaged, _ in mutation_cases(pair):
        try:
            inspect_pair(damaged, dependency_interfaces)
        except (OpenPairError, Invalid):
            rejected.append(label)
        else:
            raise OpenPairError('independent open negative accepted: ' + label)
    # Shape/context negatives have no production error-string dependency.
    require(bool(dependency_interfaces), 'real seed must include its canonical builtin')
    extra_fields = list(fields(decoded(dependency_interfaces[0], 3, 'CrateInterfaceFields'), 242, 13))
    extra_fields[0] = string('independent-unreachable-crate')
    extra_fields[1] = sequence([])
    extra = tree_document([node(242, *extra_fields)], 3)
    variants = [('missing-dependencies', []),
                ('duplicate-dependencies', list(dependency_interfaces) * 2),
                ('root-as-dependency', [*dependency_interfaces, pair[0]]),
                ('unreachable-dependency', [*dependency_interfaces, extra])]
    for label, dependencies in variants:
        try:
            inspect_pair(pair, dependencies)
        except (OpenPairError, Invalid):
            rejected.append(label)
        else:
            raise OpenPairError('independent context negative accepted: ' + label)
    schema, _, original = open_document(pair[1])
    source = list(original)
    structural = []
    for label, index, value in (
            ('missing-binding-references', 3, sequence([])),
            ('duplicate-binding-reference', 3, sequence([*items(source[3]), items(source[3])[0]])),
            ('missing-fragments', 5, sequence([]))):
        changed = list(source)
        changed[index] = value
        structural.append((label, repinned(pair, open_bytes(schema, changed))))
    fragments = list(items(source[5]))
    fragment = list(fields(fragments[0], 401, 7))
    fragment[4] = ('bits', 0)
    fragments[0] = node(401, *fragment)
    changed = list(source)
    changed[5] = sequence(fragments)
    structural.append(('wrong-typed-body', repinned(pair, open_bytes(schema, changed))))
    for label, damaged in structural:
        try:
            inspect_pair(damaged, dependency_interfaces)
        except (OpenPairError, Invalid):
            rejected.append(label)
        else:
            raise OpenPairError('independent structure negative accepted: ' + label)
    wrong_audit = (audited_pair[0], audited_pair[1] + b'\0')
    try:
        compare_companion(closed_pair, pair, dependency_interfaces, wrong_audit,
                          legacy_pair, legacy_rebuilt_pair)
    except OpenPairError:
        rejected.append('changed-audit-bytes')
    else:
        raise OpenPairError('changed audit output accepted')
    return {'positive': good, 'negative_cases': rejected}

def audit_mutation_cases(pair):
    """A changed receipt must fail the actual checker audit, not just a byte hash."""
    schema, document, original = open_document(pair[1])
    opened = list(original)
    fragments = list(items(opened[5]))
    first = list(fields(fragments[0], 401, 7))
    first[1] = string('deliberately-wrong-checked-receipt')
    fragments[0] = node(401, *first)
    opened[5] = sequence(fragments)
    changed = repinned(pair, open_bytes(schema, opened))
    return [('wrong-checked-receipt', changed, 'open fragment audit mismatch')]
