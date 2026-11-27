#!/usr/bin/env python3
"""Independent FinishScc receipt reconstruction and corruption controls."""

import hashlib
import json

from query_generation import Generation, cache_directory
from artifact_binary_reference import Limits, read_document, tree_document, require
from artifact_binary_typed import list_values, text, unpack, value_node
from artifact_binary_open import (open_document, OPEN_FORMATS, type_alpha,
    checked_stamp_syntax, different_content_stamp, expand_application_document, open_bytes, repinned, syntax_equal)
from template_receipts import rebind_template


def n(tag, *fields):
    return ("node", tag, tuple(fields))


def packed(fields):
    return "".join(f"{len(field)}:{field}" for field in fields)


def read(path, schema):
    return read_document(path.read_bytes(), schema).values()[0]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def binder_name(binder):
    return value_node(binder, 31, 2)[1]


def package_fragments(raw):
    """Read committed schema dispatch, preserving each complete final record."""
    # Reuse the independent schema8 aggregate/per-root budget and canonical
    # framing checks already used by the binary-artifact correctness suite.
    return package_bodies(raw)[0]


def package_bodies(raw):
    schema, document, package = open_document(raw)
    fmt, compiler, association, bindings, declarations, finals = package
    require(text(fmt) == OPEN_FORMATS[schema], "open package format")
    finals = list_values(finals)
    objects = {}
    for final in finals:
        fields = value_node(final, 401, 7)
        name = text(fields[0])
        require(name not in objects, "duplicate open package fragment")
        objects[name] = fields
    stored = {}
    if schema == 11:
        for fragment in document.values()[1:]:
            fields = value_node(fragment, 401, 7)
            stored[text(fields[0])] = fields[4]
    return objects, stored


def scope_edge(raw, identity, nodes):
    """Validate current authority: group scope or the exact shared empty scope.

    The Prepared digest still owns current source semantics; this is not an
    independent parser/re-elaborator of the source program.
    """
    prepared = packed(['Input', packed(['Prepared', identity])])
    require(len(raw['reads']) >= 2 and raw['reads'][0] == (prepared, nodes[prepared]['sha']),
            'raw prepared/scope edges')
    key, digest = raw['reads'][1]
    require(key in (packed(['Scope', identity]), packed(['EmptyScope', ''])),
            'raw current scope identity')
    require(nodes[key]['sha'] == digest, 'raw current scope version')
    if key == packed(['EmptyScope', '']):
        inventory = packed(['Input', packed(['EmptyScopeInventory', ''])])
        inventory_hash = sha(packed(['MLF-SCOPE-INVENTORY-TEXT-1', '0']).encode())
        scope_hash = sha(packed(['MLF-SCOPE-READS-TEXT-1', '0', '0']).encode())
        require(inventory in nodes and nodes[inventory] ==
                dict(sha=inventory_hash, reads=[], payload=None), 'empty scope inventory authority')
        require(nodes[key] == dict(sha=scope_hash, reads=[(inventory, inventory_hash)], payload=None),
                'empty scope exact authority')
    return key


def check_receipts(prefix, cache, nodes):
    """Rebuild the fragment commitment from the emitted object and actual dependency versions."""
    results = cache_directory(cache) / "results"
    groups = json.loads(prefix.with_suffix(".queries").read_text())["groups"]
    objects, stored_bodies = package_bodies(prefix.with_suffix(".mlfco").read_bytes())
    interface = value_node(read(prefix.with_suffix(".mlfci"), 3), 242, 13)
    types = {text(name): ty for name, ty in (value_node(b, 2, 2) for b in list_values(interface[9]))}
    retained = rewritten = 0
    template_groups = []
    require(len(groups) == len(objects) and {g['id'] for g in groups} == set(objects),
            "finish receipt group inventory")
    expected_finishes = {packed(['FinishScc', packed(sorted(g['members']))]) for g in groups}
    require({k for k in nodes if unpack(k)[0] == 'FinishScc'} <= expected_finishes,
            'unexpected finish receipt group')
    for g in groups:
        members = sorted(g["members"])
        identity = packed(members)
        key = packed(["FinishScc", identity])
        finish = nodes.get(key)
        direct = finish is None
        require(not direct or len(members) == 1, 'direct binding requires singleton')
        raw_key = packed(["InferScc", identity])
        raw = nodes[raw_key]
        scope = scope_edge(raw, identity, nodes)
        leading = [(k, nodes[k]['sha']) for k in
                   (raw_key, packed(['Input', packed(['Prepared', identity])]), scope)]
        raw_refs = raw['reads'][2:]
        require(all(nodes[k]["sha"] == digest for k, digest in raw_refs), 'raw dependency versions')
        owner = ("text", g["id"])
        contracts = [(name, nodes[packed(["Binding", name])]["sha"]) for name in members]
        receipt_node = nodes[packed(['Binding', members[0]])] if direct else finish
        require(receipt_node['reads'][:3] == leading, 'finish receipt leading edges')
        require(receipt_node['payload'] is None, 'finish receipt has payload')
        if not direct:
            for name, digest in contracts:
                binding = nodes[packed(["Binding", name])]
                require(binding["reads"] == [(key, finish["sha"])] and binding["payload"] is None,
                        "finish binding receipt")

        # Object tag 401 references parameter and export types by identity. Query
        # tag 400 stores the export types, including the raw type's binder IDs.
        _, stamp, ds, ps, body, owned, uses = objects[g["id"]]
        payload = (results / (raw["sha"] + ".mlfqr")).read_bytes()
        require(raw['payload'] == raw['sha'] == sha(payload), 'raw payload commitment')
        document = read_document(payload, 6)
        values = document.values()
        require(len(values) == 1 and tree_document(values, 6) == payload, 'canonical raw payload')
        original_refs, original = value_node(values[0], 425, 2)
        compressed = original[:2] == ('node', 442)
        logical = original
        if compressed:
            require(any(row.kind == 3 and row.data[0] == 88 and len(row.data[1]) == 3 for row in document.nodes),
                    'repeated application query has no spine')
            expanded, _ = expand_application_document(document, Limits().work, allow_ground=True, allow_spines=True)
            _, logical = value_node(expanded[0], 425, 2)
        stage, raw_owner, raw_stamp, raw_ps, raw_body, raw_owned, raw_uses = value_node(logical, 442 if compressed else 400, 7)
        template = text(raw_owner) == 'template'
        require(not (compressed and template), 'inference template storage version')
        actual_raw_refs = n(1, *(n(2, ('text', k), ('text', h)) for k, h in raw_refs))
        if template:
            raw_ps, raw_body, raw_owned, raw_uses = rebind_template(
                original_refs, original, raw_refs, members, types)
            template_groups.append(g['id'])
            checked_stamp_syntax(text(raw_stamp))
            checked_stamp_syntax(text(stamp))
        else:
            require(text(stage) == 'raw' and raw_owner == owner, 'raw stage/owner')
            require(original_refs == actual_raw_refs, 'raw dependency references')
        params = n(1, *(n(2, b, binder_name(b)) for b in list_values(ps)))
        keys = [packed(["Binding", text(binder_name(b))]) for b in list_values(ps)]
        keys += [packed(["Datatype", text(t)]) for t in list_values(ds)]
        refs = n(1, *(n(2, ("text", k), ("text", nodes[k]["sha"])) for k in keys))
        require(receipt_node["reads"][3:] == [edge for edge in receipt_node["reads"][3:] if unpack(edge[0])[0] == "Evidence"] + [
            (k, nodes[k]["sha"]) for k in keys if unpack(k)[0] == "Binding"], "finish binding reads")
        raw_binders = n(1, *(value_node(v, 2, 2)[0] for v in list_values(raw_owned)))
        same_body = syntax_equal((params, body, owned, uses), (raw_ps, raw_body, raw_binders, raw_uses))
        if not template:
            same_body = same_body and stamp == raw_stamp
        if same_body:
            final_types = raw_owned
            for binder, ty in (value_node(v, 2, 2) for v in list_values(raw_owned)):
                require(type_alpha(ty, types[text(binder_name(binder))]), 'retained export type')
        else:
            # The rewritten fixtures have closed concrete result types. Their
            # exact final types are independently available from the interface.
            final_types = n(1, *(n(2, b, types[text(binder_name(b))]) for b in list_values(owned)))
        same = same_body and refs == actual_raw_refs
        if template and same:
            # The real retained commitment is the authenticated canonical
            # template, not the concrete-owner package fragment. Reattachment
            # was compared in full above. withNameHints recomputes its stamp;
            # its content validity is checked by mandatory actual audited links
            # and the targeted repinned wrong-stamp control in verify.py.
            content = sha(tree_document([n(425, original_refs, original)], schema=6))
        elif compressed and same:
            # The content hash binds the stored bytes. The full decoded term,
            # types, references and stamp above bind those bytes to the final
            # object. A compact final package supplies its own physical body.
            stored = original[2][4]
            if g['id'] in stored_bodies:
                require(syntax_equal(stored_bodies[g['id']], stored), 'retained application storage')
                stored = stored_bodies[g['id']]
            content = sha(tree_document([n(425, refs, n(442, ('text', 'raw'), owner, stamp,
                params, stored, final_types, uses))], schema=6))
        else:
            content = sha(tree_document([n(425, refs, n(400, ("text", "raw"), owner, stamp,
                params, body, final_types, uses))], schema=6))
        if direct:
            require(same and content == raw['sha'], 'direct binding must retain exact raw content and references')
            require(receipt_node['reads'][3:] == [(k, nodes[k]['sha']) for k in keys
                    if unpack(k)[0] == 'Binding'], 'direct binding cannot carry evidence')
            # This row commits to the current SourceContract, not a FinishScc
            # hash. Explicit overload metadata is not fully exported by the
            # interface, so do not invent it from dictionary-arrow types.
            # Exact provider edges, raw content and final reattachment are
            # independent checks; actual cold/warm/audit controls qualify the
            # source contract and metadata-only invalidation separately.
        receipt = packed(["MLF-FINISH-RECEIPT-TEXT-1", g["id"], content,
                          str(len(contracts)), *(field for pair in contracts for field in pair)])
        if not direct:
            require(sha(receipt.encode("utf-8")) == finish["sha"], "finish receipt commitment")
        if same:
            retained += 1
            require(content == raw["sha"], "retained raw commitment")
        else:
            rewritten += 1
    return {"retained": retained, "rewritten": rewritten, 'template_groups': template_groups}


def wrong_template_stamp(pair, group):
    """Repin outer hashes: only the real content-stamp check may reject this."""
    schema, _, original = open_document(pair[1])
    opened = list(original)
    finals = list(list_values(opened[5]))
    matches = [i for i, final in enumerate(finals) if text(value_node(final, 401, 7)[0]) == group]
    require(len(matches) == 1, 'template stamp target')
    index = matches[0]
    final = list(value_node(finals[index], 401, 7))
    final[1] = ('text', different_content_stamp(text(final[1])))
    finals[index] = n(401, *final)
    opened[5] = n(1, *finals)
    return repinned(pair, open_bytes(schema, opened))


def forge_template_generation(cache, current, raw_key, mode):
    """Checksum-consistent attacks requiring actual current-source admission."""
    directory = cache_directory(cache)
    wire = Generation((directory / 'generations' / (current + '.mlfqg')).read_bytes(), expected_hash=current)
    raw_node = wire.nodes[raw_key]
    references, original = value_node(read(directory / 'results' / (raw_node['payload'] + '.mlfqr'), 6), 425, 2)
    original = list(value_node(original, 400, 7))
    require(text(original[1]) == 'template', 'template corruption target')
    if mode == 'owner':
        original[1] = ('text', 'wrong-template-owner')
    elif mode == 'member':
        binder, ty = value_node(list_values(original[5])[0], 2, 2)
        identity, _ = value_node(binder, 31, 2)
        original[5] = n(1, n(2, n(31, identity, ('text', 'wrongTemplateOwner')), ty))
    elif mode in ('source-key', 'scheme-key', 'signature-key'):
        marker, key = value_node(list_values(references)[0], 2, 2)
        fields = unpack(text(key))
        offset = int(fields[0] == 'checked-signed-inference-template-1')
        if mode == 'source-key':
            fields[3 + offset] = packed(['integer', '987654321'])
        elif mode == 'scheme-key':
            fields[2 + offset] = packed([packed(['constructor', 'Int', ''])])
        else:
            require(offset == 1, 'signature corruption requires signed template')
            fields[1] = packed(['annotation', '', packed(['constructor', 'Bool', ''])])
        references = n(1, n(2, marker, ('text', packed(fields))))
    else:
        require(False, 'unknown template corruption mode')
    payload = tree_document([n(425, references, n(400, *original))], 6)
    digest = sha(payload)
    require(digest != raw_node['sha'], 'template corruption must change payload')
    (directory / 'results' / (digest + '.mlfqr')).write_bytes(payload)
    rows = []
    for row in wire.rows:
        key, result, reads, location = value_node(row, 410, 4)
        if text(key) == raw_key:
            result, location = ('text', digest), n(5, ('text', digest))
        reads = n(1, *(n(2, dependency, ('text', digest) if text(dependency) == raw_key else expected)
                       for dependency, expected in (value_node(edge, 2, 2) for edge in list_values(reads))))
        rows.append(n(410, key, result, reads, location))
    encoded = wire.encode_rows(rows)
    forged = sha(encoded)
    (directory / 'generations' / (forged + '.mlfqg')).write_bytes(encoded)
    (directory / 'CURRENT').write_bytes(tree_document([('text', forged)], 6))
    return forged


def forge_generation(cache, current, mode):
    """Rehash the modified index and incoming edges so checksum checks alone cannot detect it."""
    directory = cache_directory(cache)
    wire = Generation((directory / "generations" / (current + ".mlfqg")).read_bytes(), expected_hash=current)
    config = wire.config
    rows = [value_node(row, 410, 4) for row in wire.rows]
    finishes = [(key, h, payload) for key, h, _, payload in rows if unpack(text(key))[0] == "FinishScc"]
    (key, original, _), (_, donor, donor_payload) = finishes[:2]
    assert original != donor
    if mode == "finish-as-raw":
        key = next(k for k, _, _, _ in rows if unpack(text(k))[0] == "InferScc")
    if mode == "previous-format":
        fields = unpack(text(config))
        assert fields[3] == "open-fragment-checker-1/finish-receipt-1"
        fields[3] = "open-fragment-checker-1"
        config = ("text", packed(fields))
    if mode == "stale":
        identity = unpack(text(key))[1]
        members = unpack(identity)
        raw_node = wire.nodes[packed(["InferScc", identity])]
        raw_record = read(directory / "results" / (raw_node["payload"] + ".mlfqr"), 6)
        _, fragment = value_node(raw_record, 425, 2)
        owner = text(value_node(fragment, 442 if fragment[:2] == ('node', 442) else 400, 7)[1])
        contracts = [(name, wire.nodes[packed(["Binding", name])]["sha"]) for name in members]
        stale = packed(["MLF-FINISH-RECEIPT-TEXT-1", owner, text(donor), str(len(contracts)),
                        *(field for pair in contracts for field in pair)])
        donor = ("text", sha(stale.encode("utf-8")))
        donor_payload = n(4)
    changed = []
    for k, h, edges, payload in rows:
        if mode in ("swapped", "stale", "finish-as-raw"):
            if k == key:
                h, payload = donor, donor_payload
            edges = n(1, *(n(2, owner, donor if owner == key else digest)
                           for owner, digest in (value_node(edge, 2, 2) for edge in list_values(edges))))
        elif mode == "reordered" and k == key:
            edges = n(1, *reversed(list_values(edges)))
        changed.append(n(410, k, h, edges, payload))
    raw = wire.encode_rows(changed, config)
    if mode == "payload-row-range":
        # v3 addresses payloads by row, not by a separately editable digest.
        # Preserve every normal column and append exactly one out-of-range row.
        root = read_document(raw, 6).values()[0]
        columns = list(value_node(root, 412, 11))
        columns[10] = n(1, *list_values(columns[10]),
                        ("int", len(list_values(columns[6]))))
        raw = tree_document([n(412, *columns)], 6)
    digest = sha(raw)
    assert digest != current
    (directory / "generations" / (digest + ".mlfqg")).write_bytes(raw)
    (directory / "CURRENT").write_bytes(tree_document([("text", digest)], schema=6))
    return digest


def forge_direct_binding_generation(cache, current, mode):
    """Corrupt a rebuilt direct provider without invalidating wire closure."""
    directory = cache_directory(cache)
    wire = Generation((directory / 'generations' / (current + '.mlfqg')).read_bytes(), expected_hash=current)
    candidates = [(key, row) for key, row in wire.nodes.items()
                  if unpack(key)[0] == 'Binding' and row['reads']
                  and unpack(row['reads'][0][0])[0] == 'InferScc']
    require(bool(candidates), 'direct binding attack target')
    consumed = {key for row in wire.nodes.values() for key, _ in row['reads']}
    leaves = [(key, row) for key, row in candidates if key not in consumed]
    require(bool(leaves), 'direct binding attack needs unconsumed target')
    target, original = leaves[0]
    replacement = original['sha']
    if mode == 'swapped-result':
        donors = [row['sha'] for key, row in candidates if row['sha'] != replacement]
        require(bool(donors), 'direct binding attack needs distinct contract donor')
        replacement = donors[0]
    else:
        require(mode in ('reordered', 'missing-prepared'), 'unknown direct binding corruption')
    rows = []
    for row in wire.rows:
        key, result, reads, location = value_node(row, 410, 4)
        edges = list(list_values(reads))
        if text(key) == target:
            require(len(edges) >= 3, 'direct provider leading edge count')
            result = ('text', replacement)
            if mode == 'reordered':
                edges[0], edges[1] = edges[1], edges[0]
            elif mode == 'missing-prepared':
                del edges[1]
        edges = [n(2, dependency, ('text', replacement) if text(dependency) == target else expected)
                 for dependency, expected in (value_node(edge, 2, 2) for edge in edges)]
        rows.append(n(410, key, result, n(1, *edges), location))
    encoded = wire.encode_rows(rows)
    forged = sha(encoded)
    require(forged != current, 'direct binding corruption must change generation')
    (directory / 'generations' / (forged + '.mlfqg')).write_bytes(encoded)
    (directory / 'CURRENT').write_bytes(tree_document([('text', forged)], 6))
    return forged
