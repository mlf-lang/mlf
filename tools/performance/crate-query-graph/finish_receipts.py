#!/usr/bin/env python3
"""Independent FinishScc receipt reconstruction and corruption controls."""

import hashlib
import json

from query_generation import Generation, cache_directory
from artifact_binary_reference import read_document, tree_document, require
from artifact_binary_typed import list_values, text, unpack, value_node
from artifact_binary_open import open_document, OPEN_FORMATS


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
    schema, _, package = open_document(raw)
    fmt, compiler, association, bindings, declarations, finals = package
    require(text(fmt) == OPEN_FORMATS[schema], "open package format")
    finals = list_values(finals)
    objects = {}
    for final in finals:
        fields = value_node(final, 401, 7)
        name = text(fields[0])
        require(name not in objects, "duplicate open package fragment")
        objects[name] = fields
    return objects


def check_receipts(prefix, cache, nodes):
    """Rebuild the fragment commitment from the emitted object and actual dependency versions."""
    results = cache_directory(cache) / "results"
    groups = json.loads(prefix.with_suffix(".queries").read_text())["groups"]
    objects = package_fragments(prefix.with_suffix(".mlfco").read_bytes())
    interface = value_node(read(prefix.with_suffix(".mlfci"), 3), 242, 13)
    types = {text(name): ty for name, ty in (value_node(b, 2, 2) for b in list_values(interface[9]))}
    retained = rewritten = 0
    assert len(groups) == len(objects) == sum(unpack(k)[0] == "FinishScc" for k in nodes)
    for g in groups:
        members = sorted(g["members"])
        identity = packed(members)
        key = packed(["FinishScc", identity])
        finish = nodes[key]
        raw_key = packed(["InferScc", identity])
        raw = nodes[raw_key]
        assert finish["reads"][:3] == [(k, nodes[k]["sha"]) for k in
            (raw_key, packed(["Input", packed(["Prepared", identity])]), packed(["Scope", identity]))]
        owner = ("text", g["id"])
        assert finish["payload"] is None
        contracts = [(name, nodes[packed(["Binding", name])]["sha"]) for name in members]
        for name, digest in contracts:
            binding = nodes[packed(["Binding", name])]
            assert binding["reads"] == [(key, finish["sha"])] and binding["payload"] is None

        # Object tag 401 references parameter and export types by identity. Query
        # tag 400 stores the export types, including the raw type's binder IDs.
        _, stamp, ds, ps, body, owned, uses = objects[g["id"]]
        original_refs, original = value_node(read(results / (raw["sha"] + ".mlfqr"), 6), 425, 2)
        stage, raw_owner, raw_stamp, raw_ps, raw_body, raw_owned, raw_uses = value_node(original, 400, 7)
        assert text(stage) == "raw" and raw_owner == owner
        params = n(1, *(n(2, b, binder_name(b)) for b in list_values(ps)))
        keys = [packed(["Binding", text(binder_name(b))]) for b in list_values(ps)]
        keys += [packed(["Datatype", text(t)]) for t in list_values(ds)]
        refs = n(1, *(n(2, ("text", k), ("text", nodes[k]["sha"])) for k in keys))
        assert finish["reads"][3:] == [edge for edge in finish["reads"][3:] if unpack(edge[0])[0] == "Evidence"] + [
            (k, nodes[k]["sha"]) for k in keys if unpack(k)[0] == "Binding"]
        raw_binders = n(1, *(value_node(v, 2, 2)[0] for v in list_values(raw_owned)))
        same_body = (stamp, params, body, owned, uses) == (raw_stamp, raw_ps, raw_body, raw_binders, raw_uses)
        if same_body:
            final_types = raw_owned
        else:
            # The rewritten fixtures have closed concrete result types. Their
            # exact final types are independently available from the interface.
            final_types = n(1, *(n(2, b, types[text(binder_name(b))]) for b in list_values(owned)))
        content = sha(tree_document([n(425, refs, n(400, ("text", "raw"), owner, stamp,
            params, body, final_types, uses))], schema=6))
        receipt = packed(["MLF-FINISH-RECEIPT-TEXT-1", g["id"], content,
                          str(len(contracts)), *(field for pair in contracts for field in pair)])
        assert sha(receipt.encode("utf-8")) == finish["sha"]
        if same_body and refs == original_refs:
            retained += 1
            assert content == raw["sha"]
        else:
            rewritten += 1
    return {"retained": retained, "rewritten": rewritten}


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
        owner = text(value_node(fragment, 400, 7)[1])
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
        elif mode == "wrong-address" and k == key:
            payload = n(5, donor)
        changed.append(n(410, k, h, edges, payload))
    raw = wire.encode_rows(changed, config)
    digest = sha(raw)
    assert digest != current
    (directory / "generations" / (digest + ".mlfqg")).write_bytes(raw)
    (directory / "CURRENT").write_bytes(tree_document([("text", digest)], schema=6))
    return digest
