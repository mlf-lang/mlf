#!/usr/bin/env python3
"""Strict C4 closed-to-open boundary comparison, not a general equivalence test.

The caller MUST first run the authenticated native helper: public read/link of
both originals (including old object/fragment checksums), Open.audit retaining
its returned fragments, and complete audited rebuild. This module independently
checks content and format-specific metadata. Audit-byte equality is a separate
production-boundary control, not independent codec or checker evidence.
"""
from pathlib import Path
import hashlib

# The C4 oracle predates the additional DeclId array/ST primitives. Keep its
# entire reader/schema triple byte-for-byte: this finite corpus uses the old
# primitive domain. Actual artifacts still pass the current native reader,
# linker and audit before this independent comparison.
from frozen_file_oracles import load_oracles, dependency_oracle

ORACLE_PINS = {
    'artifact_binary_reference.py': 'de312e3415eba178b649d30b6fa2b113fc864455de16603a5902af034d036422',
    'artifact_binary_typed.py': 'b703af43e334733c9ccb49f2a4e5a63a615f6bd065c8c464bdd3841ed54e369d',
    'artifact_structure_contract.json': '20f1df71bc2fc1ebe01247dc986b01029b3e8e0c4a89f7dcc8cc517f756cf5a1',
}
ORACLE_DIRECTORY, _reference, _typed = load_oracles(ORACLE_PINS)
DEPENDENCY_ORACLE_PATH, _dependency_typed = dependency_oracle(
    ORACLE_DIRECTORY, _reference, ORACLE_PINS['artifact_binary_typed.py'])
Invalid, read_document, tree_document = (_reference.Invalid, _reference.read_document,
                                        _reference.tree_document)
fields, items, text = _typed.value_node, _typed.list_values, _typed.text
validate_type, builtin_datatypes, pack = (_typed.validate_type, _typed.builtin_datatypes,
                                         _typed.pack)

class ComparisonError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ComparisonError(message)

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

def dependency_decoded(raw):
    """Validate whole dependency bytes, including the two added primitive exports."""
    doc = read_document(raw, 3)
    require(len(doc.roots) == 1, 'exactly one dependency interface root')
    _dependency_typed.validate_type(doc, doc.roots[0], 'CrateInterfaceFields')
    values = doc.values()
    require(tree_document(values, 3) == raw, 'canonical whole dependency bytes')
    # Module.builtinEntities declares primitive entities in Prelude, including
    # exports reexported through MLF.Primitive. Do not treat 132/133 as generic
    # newly accepted integers or permit an arbitrary renamed primitive export.
    added = {132: ('Prelude', 'freezeSTArray'), 133: ('Prelude', 'stToIO')}
    for module, entities in (fields(row, 2, 2) for row in items(fields(values[0], 242, 13)[3])):
        text(module)
        for entity in items(entities):
            owner, spelling, role = fields(entity, 189, 3)
            if role[1] == 186:
                primitive, = fields(role, 186, 1)
                code, = fields(primitive, 32, 1)
                if code[1] in added:
                    require((text(owner), text(spelling)) == added[code[1]],
                            'exact added dependency primitive identity')
    return values[0]

OPEN_FORMATS = {7: 'MLF-OPEN-CRATE-1/checker-1', 8: 'MLF-OPEN-CRATE-2/checker-1'}

def open_document(raw):
    """C4 same-format view, not a general schema7-to-8 migration checker.

    The frozen independent codec's original 64 Mi-unit summed-work limit
    remains unchanged, including for these small schema8 C4 fixtures. This is
    deliberately narrower than production schema8's package resource class.
    No fragment content, ordering or metadata is normalized by this view.
    """
    require(isinstance(raw, bytes) and len(raw) >= 20, 'complete open binary header')
    schema = int.from_bytes(raw[16:20], 'little')
    require(schema in OPEN_FORMATS, 'unsupported open schema')
    document = read_document(raw, schema)
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
        opened = (*header[:5], sequence(values[1:]))
    require(text(opened[0]) == OPEN_FORMATS[schema], 'wrong open package family')
    for fragment in items(opened[5]):
        fields(fragment, 401, 7)
    return schema, opened

def open_bytes(schema, opened):
    """Native-negative fixture writer; retain the original wire family."""
    require(schema in OPEN_FORMATS, 'unsupported fixture open schema')
    if schema == 7:
        return tree_document([node(430, *opened)], 7)
    fragments = items(opened[5])
    header = node(432, *opened[:5], ('int', len(fragments)))
    return tree_document([header, *fragments], 8)

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

def linked_equal(a, b):
    """Same complete typed syntax; only injective, lexically bound XName renaming.

    The four retained positives show no XTyVar or computation changes. Those
    remain exact, as do datatype spelling, hints, primitive codes and IEEE bits.
    """
    forward, reverse, bindings = {}, {}, set()
    occurrences = 0
    def match_name(x, y, scope, binder=False):
        nonlocal occurrences
        ix, hx = name(x)
        iy, hy = name(y)
        require(hx == hy, 'linked name hint changed')
        require(forward.setdefault(ix, iy) == iy and reverse.setdefault(iy, ix) == ix,
                'linked identity renaming is not consistent/injective')
        if binder:
            bindings.add((ix, iy))
        else:
            require(scope.get(ix, ix) == iy, 'linked free/captured/wrong binding reference')
        if ix != iy:
            occurrences += 1
        return ix, iy
    def match_pattern(x, y, scope):
        require(x[1] == y[1], 'linked pattern constructor changed')
        xs, ys = fields(x), fields(y)
        if x[1] == 90:
            require(xs[0] == ys[0], 'linked constructor pattern changed')
            ps, qs = items(xs[1]), items(ys[1])
        else:
            require(x[1] == 91, 'linked pattern syntax')
            ps, qs = [xs[0]], [ys[0]]
        require(len(ps) == len(qs), 'linked pattern arity changed')
        extended = dict(scope)
        for p, q in zip(ps, qs):
            require(p[1] == q[1] and len(fields(p)) == len(fields(q)), 'linked pattern binder changed')
            if p[1] == 5:
                ix, iy = match_name(fields(p, 5, 1)[0], fields(q, 5, 1)[0], scope, True)
                extended[ix] = iy
            else:
                require(p == q == node(4), 'linked absent pattern binder')
        return extended
    def walk(x, y, scope):
        require(x[0] == y[0] == 'node' and x[1] == y[1], 'linked term constructor changed')
        xs, ys = fields(x), fields(y)
        require(len(xs) == len(ys), 'linked term arity changed')
        tag = x[1]
        if tag == 70:
            match_name(xs[0], ys[0], scope)
        elif tag == 71:
            ix, iy = match_name(xs[0], ys[0], scope, True)
            require(xs[1] == ys[1], 'linked parameter type changed')
            walk(xs[2], ys[2], {**scope, ix: iy})
        elif tag == 72:
            walk(xs[0], ys[0], scope)
            walk(xs[1], ys[1], scope)
        elif tag == 73:
            require(xs[:2] == ys[:2], 'linked type binder/bound changed')
            walk(xs[2], ys[2], scope)
        elif tag == 74:
            require(xs[1] == ys[1], 'linked computation changed')
            walk(xs[0], ys[0], scope)
        elif tag == 75:
            ix, iy = match_name(xs[0], ys[0], scope, True)
            walk(xs[1], ys[1], scope)
            walk(xs[2], ys[2], {**scope, ix: iy})
        elif tag == 76:
            left = [fields(z, 3, 3) for z in items(xs[0])]
            right = [fields(z, 3, 3) for z in items(ys[0])]
            require(len(left) == len(right), 'linked recursive binding inventory changed')
            extended = dict(scope)
            for p, q in zip(left, right):
                ix, iy = match_name(p[0], q[0], scope, True)
                extended[ix] = iy
                require(p[1] == q[1], 'linked recursive type changed')
            for p, q in zip(left, right):
                walk(p[2], q[2], extended)
            walk(xs[1], ys[1], extended)
        elif tag == 83:
            walk(xs[0], ys[0], scope)
            require(xs[1] == ys[1], 'linked case result type changed')
            aa, bb = items(xs[2]), items(ys[2])
            require(len(aa) == len(bb), 'linked alternatives changed')
            for p, q in zip(aa, bb):
                pp, pb = fields(p, 92, 2)
                qp, qb = fields(q, 92, 2)
                walk(pb, qb, match_pattern(pp, qp, scope))
        elif tag == 84:
            require(xs[0] == ys[0], 'linked datatype context changed')
            walk(xs[1], ys[1], scope)
        else:
            require(tag in (77, 78, 79, 80, 81, 82), 'unknown linked term')
            require(x == y, 'linked literal/primitive/constructor changed')
    walk(a, b, {})
    changed = [(x, y) for x, y in forward.items() if x != y]
    require(all(pair in bindings for pair in changed), 'linked changed identity has no corresponding binder')
    return {'changed_identity_pairs': changed, 'changed_occurrences': occurrences,
            'all_other_typed_structure_exact': True, 'lexical_binding_correspondence': True}

def select_original_linked(term, fragments, entry):
    """Independent step-14 closure over fully compared stored fragments.

    Only outer declarations whose exact stable owner is an unreachable fragment
    are omitted. RHSs and all their lexical binders remain opaque and unchanged.
    The actual entry identity and complete original outer inventory are checked
    before the existing binder-aware comparison sees the projected reference.
    """
    owners, used, ordered = {}, {}, []
    for fragment in fragments:
        fs = fields(fragment, 401, 7)
        group = text(fs[0])
        require(group not in used, 'selection duplicate fragment group')
        ordered.append(group)
        require(list(items(fs[5])) == spine_names(fs[4]), 'selection complete owned binders')
        require(list(items(fs[6])) == free_names(fs[4]), 'selection exact lexical used inventory')
        used[group] = [name(x)[1] for x in items(fs[6])]
        for value in items(fs[5]):
            key = name(value)[1]
            require(key not in owners, 'selection duplicate declaration owner')
            owners[key] = group
    require(entry in owners, 'selection entry has no declaration owner')
    reached, pending = set(), [owners[entry]]
    while pending:
        group = pending.pop()
        if group not in reached:
            reached.add(group)
            pending.extend(owners[key] for key in used[group] if key in owners)
    omitted = {key for key, group in owners.items() if group not in reached}
    seen, identities, dropped_ids = {}, set(), set()

    def declaration(values):
        pairs = [name(value) for value in values]
        require(all(identity not in identities for identity, _ in pairs) and
                len({identity for identity, _ in pairs}) == len(pairs),
                'selection unique outer declaration identities')
        identities.update(identity for identity, _ in pairs)
        owned = [(identity, key) for identity, key in pairs if key in owners]
        require(all(key not in seen for _, key in owned), 'selection unique outer declaration owners')
        seen.update((key, identity) for identity, key in owned)
        if not owned:
            return False
        require(len(owned) == len(pairs) and len({owners[key] for _, key in owned}) == 1,
                'selection outer group has mixed declaration owners')
        remove = all(key in omitted for _, key in owned)
        if remove:
            dropped_ids.update(identity for identity, _ in owned)
        return remove

    def outer(value):
        fs = fields(value)
        if value[1] == 84:
            return node(84, fs[0], outer(fs[1]))
        if value[1] == 75:
            remove = declaration([fs[0]])
            rest = outer(fs[2])
            return rest if remove else node(75, fs[0], fs[1], rest)
        if value[1] == 76:
            remove = declaration([fields(row, 3, 3)[0] for row in items(fs[0])])
            rest = outer(fs[1])
            return rest if remove else node(76, fs[0], rest)
        require(value[1] == 70 and name(fs[0]) == (seen.get(entry), entry),
                'selection terminal variable is the actual declared entry')
        return value

    selected = outer(term)
    require(set(seen) == set(owners), 'selection complete original declaration inventory')
    require(not any(name(value)[0] in dropped_ids for value in free_names(selected)),
            'selection removed a live lexical reference')
    return selected, {'entry': entry, 'selected_groups': [g for g in ordered if g in reached],
                      'omitted_groups': [g for g in ordered if g not in reached],
                      'omitted_declarations': sorted(omitted),
                      'original_stored_fragments_complete': True,
                      'only_unreachable_outer_declarations_omitted': True}


def compare_open_file(closed_files, open_files, dependency_interfaces,
                      audited_open_files, closed_linked_bytes, open_linked_bytes,
                      entry_selection=False):
    try:
        return _compare(closed_files, open_files, dependency_interfaces,
                        audited_open_files, closed_linked_bytes, open_linked_bytes, entry_selection)
    except Invalid as error:
        raise ComparisonError(str(error)) from error

def _compare(closed_files, open_files, dependency_interfaces,
             audited_open_files, closed_linked_bytes, open_linked_bytes, entry_selection):
    suffixes = {'.mlfci', '.mlfco'}
    for values in (closed_files, open_files, audited_open_files):
        require(set(values) == suffixes, 'complete exact artifact file inventory')
    ci = decoded(closed_files['.mlfci'], 3, 'CrateInterfaceFields')
    oi = decoded(open_files['.mlfci'], 3, 'CrateInterfaceFields')
    closed = fields(decoded(closed_files['.mlfco'], 4, 'CrateObjectFields'), 243, 3)
    open_schema, opened = open_document(open_files['.mlfco'])
    cf, of = fields(ci, 242, 13), fields(oi, 242, 13)
    require(closed[0] == node(6), 'expected ordinary nonlegacy closed family')
    require(closed[1] == ci, 'closed embedded/paired interface mismatch')
    require(all(cf[i] == of[i] for i in range(13) if i != 11), 'complete interface content changed')
    require(text(of[11]) == hashlib.sha256(open_files['.mlfco']).hexdigest(), 'actual open object SHA mismatch')
    require(text(opened[0]) == OPEN_FORMATS[open_schema], 'wrong open package family')
    compatibility = compatibility_identity()
    require(text(opened[1]) == compatibility, 'wrong checker/compiler compatibility identity')
    dependencies = [dependency_decoded(raw) for raw in dependency_interfaces]
    depmap = keyed([(text(fields(i, 242, 13)[0]), i) for i in dependencies], 'dependency interface identity')
    rootid = text(of[0])
    require(rootid not in depmap, 'root included in imported interface closure')
    pending = [text(fields(x, 3, 3)[0]) for x in items(of[1])]
    reached = set()
    while pending:
        key = pending.pop()
        require(key in depmap, 'missing complete dependency interface: ' + key)
        if key in reached:
            continue
        reached.add(key)
        pending.extend(text(fields(x, 3, 3)[0]) for x in items(fields(depmap[key], 242, 13)[1]))
    require(reached == set(depmap), 'extra dependency interface outside closure')
    association = pack([interface_association(oi)] +
        [interface_association(depmap[key]) for key in sorted(depmap)])
    require(text(opened[2]) == association, 'complete interface association mismatch')
    interfaces = [oi, *dependencies]
    types = keyed([(text(k), v) for i in interfaces for k, v in
                   (fields(x, 2, 2) for x in items(fields(i, 242, 13)[9]))], 'binding ownership')
    declarations = keyed([(text(fields(d, arity=3)[0]), d) for i in interfaces
                          for d in items(fields(i, 242, 13)[8])], 'datatype ownership')
    binding_refs = [fields(x, 2, 2) for x in items(opened[3])]
    data_refs = [fields(x, 2, 2) for x in items(opened[4])]
    def references(refs, available, encode, label):
        keys = [text(x[0]) for x in refs]
        require(keys == sorted(set(keys)), label + ' reference order/duplicate')
        for key, expected in refs:
            key = text(key)
            require(key in available, label + ' reference out of scope')
            require(text(expected) == fingerprint(encode(available[key])), label + ' reference hash mismatch')
        return keys
    br = references(binding_refs, types, lambda x: x, 'binding')
    dr = references(data_refs, declarations, declaration_hash_value, 'datatype')
    units, fragments = items(closed[2]), items(opened[5])
    require(len(units) == len(fragments) and len(units) > 0, 'fragment inventory changed')
    groups, used_bindings, used_data, exports = [], set(), set(), []
    group_reports = []
    for unit, fragment in zip(units, fragments):
        header, term = fields(unit, 241, 2)
        hf = fields(header, 240, 8)
        group, receipt, data_names, parameters, body, owned, used = fields(fragment, 401, 7)
        require(group == hf[0], 'ordered fragment identity changed')
        group_name = text(group)
        require(group_name not in groups, 'duplicate fragment group')
        groups.append(group_name)
        require(text(receipt) != '', 'empty checked receipt')
        require(all(hf[i] == sequence([]) for i in (1, 2, 4, 5)),
                'closed fragment contains unrepresented dependency/visibility/class/instance metadata')
        ds, term = fields(term, 84, 2)
        require(ds == hf[3], 'closed header/body datatype context mismatch')
        ps = []
        while term[0] == 'node' and term[1] == 71:
            parameter, ty, term = fields(term, 71, 3)
            ps.append((parameter, ty))
        require(term == body, 'complete original fragment body changed')
        raw_parameters, raw_owned = list(items(parameters)), list(items(owned))
        require(raw_parameters == [p for p, _ in ps], 'ordered parameter names changed')
        require(len({name(p)[0] for p in raw_parameters}) == len(raw_parameters), 'duplicate parameter identity')
        external_alpha = 0
        for parameter, ty in ps:
            key = name(parameter)[1]
            require(key in types, 'external parameter type missing')
            require(type_alpha(ty, types[key]), 'external parameter scheme changed')
            external_alpha += ty != types[key]
            used_bindings.add(key)
        require(raw_owned == spine_names(body), 'complete ordered owned binder inventory changed')
        require(len({name(p)[0] for p in raw_owned}) == len(raw_owned), 'duplicate owned identity')
        actual_exports = []
        for value in raw_owned:
            key = name(value)[1]
            require(key in types, 'owned binding type missing')
            actual_exports.append(node(2, string(key), types[key]))
            exports.append((key, types[key]))
            used_bindings.add(key)
        require(tuple(actual_exports) == items(hf[6]), 'complete fragment export/type inventory changed')
        require(list(items(used)) == free_names(body), 'complete ordered used-name inventory changed')
        require(all(x in raw_parameters for x in items(used)), 'used reference not an exact parameter')
        names = [text(x) for x in items(data_names)]
        require(names == [text(fields(x, arity=3)[0]) for x in items(ds)],
                'ordered fragment datatype references changed')
        require(len(names) == len(set(names)), 'duplicate fragment datatype reference')
        star_pairs = 0
        for key, declaration in zip(names, items(ds)):
            require(key in declarations, 'fragment datatype missing')
            star_pairs += same_declaration(declaration, declarations[key])
            used_data.add(key)
        group_reports.append({'group': group_name, 'body_exact': True,
            'external_alpha_schemes': external_alpha, 'all_star_representation_pairs': star_pairs})
    require(br == sorted(used_bindings), 'binding reference inventory is not complete/exact')
    require(dr == sorted(used_data), 'datatype reference inventory is not complete/exact')
    ownership = keyed(exports, 'owned fragment binding')
    expected = keyed([(text(k), v) for k, v in (fields(x, 2, 2) for x in items(of[9]))],
                     'interface binding')
    require(ownership == expected, 'complete crate ownership/type inventory changed')
    # This checks an actual helper output, not a reconstructed/modified expected
    # interface. The helper must retain Open.audit's returned checked fragments.
    require(all(audited_open_files[k] == open_files[k] for k in suffixes),
            'native audited rebuild differs from original complete open bytes')
    old_linked = decoded(closed_linked_bytes, 6, 'XTerm')
    new_linked = decoded(open_linked_bytes, 6, 'XTerm')
    selection = None
    if entry_selection:
        old_linked, selection = select_original_linked(old_linked, fragments, text(of[10]))
    linked = linked_equal(old_linked, new_linked)
    return {'comparison': 'explicit-schema-4-to-' + str(open_schema), 'open_wire_schema': open_schema,
            'audit_scope': 'exact same-format pair; not schema7-to-8 migration', 'groups': group_reports,
            'fragment_count': len(groups), 'group_count': len(groups), 'binding_reference_count': len(br),
            'datatype_reference_count': len(dr), 'compatibility_identity': compatibility,
            'interface_content_exact': True, 'all_original_fragment_bodies_exact': True,
            'audited_rebuild_original_bytes_equal': True, 'linked': linked,
            'entry_selection': selection,
            'native_validation_required': 'Public read/link of both originals, old checksums and Open.audit with returned fragments.'}

def make_native_negatives(closed_files, open_files):
    """Three actual-helper controls; each retains valid outer wire framing.

    Receipt and old-checksum cases must fail the native helper. The used-name
    deletion must finish native audit/rebuild, then fail this comparator. The
    caller must retain logs and run these controls in CI, not just unit tests.
    """
    open_schema, opened = open_document(open_files['.mlfco'])
    iface = decoded(open_files['.mlfci'], 3, 'CrateInterfaceFields')
    def changed_open(value):
        raw = open_bytes(open_schema, value)
        fs = list(fields(iface, 242, 13))
        fs[11] = string(hashlib.sha256(raw).hexdigest())
        return {'.mlfci': tree_document([node(242, *fs)], 3), '.mlfco': raw}
    fs = list(opened)
    entries = list(items(fs[5]))
    require(entries, 'native negative requires a positive artifact')
    first = list(fields(entries[0], 401, 7))
    first[1] = string(text(first[1]) + ':c4-corrupt-receipt')
    receipt_entries = [node(401, *first), *entries[1:]]
    receipt_fields = list(fs)
    receipt_fields[5] = sequence(receipt_entries)
    receipt = changed_open(receipt_fields)
    used_entries = list(entries)
    found = False
    for index, entry in enumerate(used_entries):
        current = list(fields(entry, 401, 7))
        original = list(items(current[6]))
        if original:
            current[6] = sequence(original[1:])
            used_entries[index] = node(401, *current)
            found = True
            break
    require(found, 'native used-name control requires an actually used parameter')
    used_fields = list(fs)
    used_fields[5] = sequence(used_entries)
    used = changed_open(used_fields)
    ci = decoded(closed_files['.mlfci'], 3, 'CrateInterfaceFields')
    co = list(fields(decoded(closed_files['.mlfco'], 4, 'CrateObjectFields'), 243, 3))
    cif = list(fields(ci, 242, 13))
    cif[11] = string(text(cif[11]) + ':c4-corrupt-checksum')
    corrupt_interface = node(242, *cif)
    co[1] = corrupt_interface
    checksum = {'.mlfci': tree_document([corrupt_interface], 3),
                '.mlfco': tree_document([node(243, *co)], 4)}
    return [
        {'name': 'receipt-sha-recomputed', 'closed_files': dict(closed_files),
         'open_files': receipt, 'expected_helper_exit': 1,
         'expected_compare_rejection': False,
         'required_error_fragment': 'open crate fragment fingerprint mismatch'},
        {'name': 'used-inventory-sha-recomputed', 'closed_files': dict(closed_files),
         'open_files': used, 'expected_helper_exit': 0,
         'expected_compare_rejection': True, 'required_error_fragment': None},
        {'name': 'old-object-checksum', 'closed_files': checksum,
         'open_files': dict(open_files), 'expected_helper_exit': 1,
         'expected_compare_rejection': False,
         'required_error_fragment': 'crate object checksum mismatch'}]
