"""Offline, lossless source-query-v6 storage prototype; NOT a compiler cache reader.

All legacy semantics remain opaque, including raw vs final. Immutable typed blobs
hold exact UTF-8 fields or scalar-framed references. No AST equivalence is assumed.
"""
import hashlib
import json
import os
from pathlib import Path
import struct

DOMAIN = b"MLF-OFFLINE-QUERY-REPRESENTATION-1\0"
MAGIC = b"MLFREP1\0"
ENTRY = struct.Struct("<32sQQQQB")
MAX_BYTES = 16 * 1024 * 1024
MAX_NODES = 50000
MAX_REFS = 20000
MAX_DEPTH = 32
WRITE_BUDGET = 12 * 1024 * 1024
written_bytes = 0
TEXT, FRAME, CONCAT, RAW_BODY, RAW_OBJECT, QUERY = range(6)
KINDS = {TEXT, FRAME, CONCAT, RAW_BODY, RAW_OBJECT, QUERY}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical_json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def packed(fields):
    return "".join(str(len(x)) + ":" + x for x in fields)


def unpacked(text):
    """Independent scalar-length parser. Only canonical writer output is admitted."""
    fields = []
    pos = 0
    while pos < len(text):
        end = text.find(":", pos, pos + 10)
        require(end > pos, "invalid legacy length")
        digits = text[pos:end]
        require(all("0" <= c <= "9" for c in digits), "non-ASCII legacy length")
        require(digits == str(int(digits)), "noncanonical legacy length")
        size = int(digits)
        require(size <= MAX_BYTES and end + 1 + size <= len(text), "truncated legacy field")
        fields.append(text[end + 1:end + 1 + size])
        require(len(fields) <= MAX_REFS, "legacy field-count limit")
        pos = end + 1 + size
    return fields


def encode_refs(refs):
    require(len(refs) <= MAX_REFS, "reference-count limit")
    return struct.pack("<I", len(refs)) + b"".join(bytes.fromhex(ref) for ref in refs)


def decode_refs(payload):
    require(len(payload) >= 4, "truncated reference list")
    count, = struct.unpack_from("<I", payload)
    require(count <= MAX_REFS and len(payload) == 4 + 32 * count, "invalid reference list")
    return [payload[4 + 32 * n:36 + 32 * n].hex() for n in range(count)]


def content_id(kind, payload):
    require(kind in KINDS, "unknown node kind")
    return sha(DOMAIN + bytes([kind]) + payload)


class Builder:
    def __init__(self, split_lists=True):
        self.nodes = {}
        self.split_lists = split_lists
        self.role_refs = {}

    def add(self, kind, payload, text, role):
        encoded = text.encode("utf-8", "strict")
        require(len(encoded) <= MAX_BYTES, "node decoded-size limit")
        key = content_id(kind, payload)
        value = (kind, payload, len(encoded), len(text))
        if key in self.nodes:
            require(self.nodes[key] == value, "content-id collision")
        else:
            require(len(self.nodes) < MAX_NODES, "node-count limit")
            self.nodes[key] = value
        self.role_refs.setdefault(role, []).append(key)
        return key

    def text(self, text, role="text", kind=TEXT):
        return self.add(kind, text.encode("utf-8", "strict"), text, role)

    def frame(self, refs, text, role="frame", kind=FRAME):
        return self.add(kind, encode_refs(refs), text, role)

    def field(self, text, role, split=False):
        if split and self.split_lists:
            children = unpacked(text)
            refs = [self.text(child, role + "/item") for child in children]
            return self.frame(refs, text, role)
        return self.text(text, role)

    def query(self, raw):
        require(len(raw) <= MAX_BYTES, "input-size limit")
        text = raw.decode("utf-8", "strict")
        outer = unpacked(text)
        require(len(outer) == 4 and outer[0] == "MLF-QUERY-CACHE-1", "only self-contained CACHE-1 supported")
        key, meta, obj = map(unpacked, outer[1:])
        require(len(key) == 9 and key[0] == "MLF-SOURCE-CRATE-QUERY-6", "only source-query-v6 supported")
        require(len(meta) == 8 and meta[0] == "MLFI-4", "unsupported interface")
        require(len(obj) == 4 and obj[0] == "MLFO-1", "unsupported raw object")
        # Crucial: never discard an alleged context unless exact prefix equality holds.
        require(obj[3].startswith(meta[4]), "header context is not the exact body prefix")
        key_refs = [self.field(s, "key/" + str(i), i in (3, 4, 5, 7, 8)) for i, s in enumerate(key)]
        key_ref = self.frame(key_refs, outer[1], "query-key")
        meta_refs = [self.field(s, "metadata/" + str(i), i in (2, 3, 5, 6)) for i, s in enumerate(meta)]
        meta_ref = self.frame(meta_refs, outer[2], "metadata")
        body_ref = self.text(obj[3][len(meta[4]):], "raw-body", RAW_BODY)
        term_ref = self.add(CONCAT, encode_refs([meta_refs[4], body_ref]), obj[3], "context-plus-raw-body")
        obj_refs = [self.text(s, "raw-object/" + str(i)) for i, s in enumerate(obj[:3])] + [term_ref]
        obj_ref = self.frame(obj_refs, outer[3], "raw-object", RAW_OBJECT)
        root = self.frame([self.text(outer[0], "cache-tag"), key_ref, meta_ref, obj_ref], text, "query-root", QUERY)
        return root

    def write(self, directory, records):
        """Create one immutable experimental bundle. Never overwrite an existing path."""
        global written_bytes
        directory = Path(directory)
        index = bytearray(MAGIC + struct.pack("<I", len(self.nodes)))
        pack_hash = hashlib.sha256()
        offset = 0
        for key, (kind, payload, decoded, scalars) in sorted(self.nodes.items()):
            pack_hash.update(payload)
            index += ENTRY.pack(bytes.fromhex(key), offset, len(payload), decoded, scalars, kind)
            offset += len(payload)
        records = sorted(records, key=lambda record: record["name"])
        require(len({r["name"] for r in records}) == len(records), "duplicate root name")
        manifest = dict(format="mlf-offline-query-representation-1", semantic_scope="source-v6/CACHE-1/raw-only",
                        strategy="component-lists" if self.split_lists else "whole-fields", node_count=len(self.nodes),
                        pack_bytes=offset, pack_sha256=pack_hash.hexdigest(), index_sha256=sha(index), records=records)
        manifest_bytes = canonical_json(manifest)
        size = offset + len(index) + len(manifest_bytes)
        require(size <= MAX_BYTES and written_bytes + size <= WRITE_BUDGET, "bundle/write-size limit")
        # Reserve before creating any payload file. Failed writes keep the reservation.
        written_bytes += size
        directory.mkdir(exist_ok=False)
        with (directory / "objects.pack").open("xb") as stream:
            for key, (_, payload, _, _) in sorted(self.nodes.items()):
                stream.write(payload)
        (directory / "objects.index").write_bytes(index)
        # Manifest is published last. This is offline write-once, not production crash-safe CAS.
        (directory / "manifest.json").write_bytes(manifest_bytes)
        return manifest


class Reader:
    def __init__(self, directory):
        self.directory = Path(directory)
        require(not self.directory.is_symlink(), "symlink bundle")
        self.manifest = json.loads(self._file("manifest.json", 1024 * 1024))
        m = self.manifest
        require(m["format"] == "mlf-offline-query-representation-1" and m["semantic_scope"] == "source-v6/CACHE-1/raw-only", "unsupported storage schema")
        data = self._file("objects.index", MAX_BYTES)
        require(sha(data) == m["index_sha256"], "index digest mismatch")
        require(data[:8] == MAGIC and len(data) >= 12, "bad index magic")
        count, = struct.unpack_from("<I", data, 8)
        require(count <= MAX_NODES and count == m["node_count"] and len(data) == 12 + count * ENTRY.size, "invalid index size")
        self.entries = {}
        end = 0
        previous = None
        for pos in range(12, len(data), ENTRY.size):
            key, offset, size, decoded, scalars, kind = ENTRY.unpack_from(data, pos)
            require(previous is None or previous < key, "duplicate or unsorted node identity")
            require(offset == end and size <= MAX_BYTES and decoded <= MAX_BYTES and scalars <= decoded and kind in KINDS, "invalid node bounds")
            end = offset + size
            require(end <= MAX_BYTES, "pack-size limit")
            self.entries[key.hex()] = (offset, size, decoded, scalars, kind)
            previous = key
        require(end == m["pack_bytes"], "pack length mismatch")
        pack = self._file("objects.pack", MAX_BYTES)
        require(len(pack) == end and sha(pack) == m["pack_sha256"], "pack digest mismatch")
        del pack
        self._validate_references()

    def _file(self, name, limit):
        p = self.directory / name
        require(p.is_file() and not p.is_symlink() and p.stat().st_size <= limit, "invalid bundle file")
        return p.read_bytes()

    def node(self, key):
        require(key in self.entries, "dangling node reference")
        offset, size, decoded, scalars, kind = self.entries[key]
        p = self.directory / "objects.pack"
        require(not p.is_symlink(), "symlink pack")
        with p.open("rb") as stream:
            stream.seek(offset)
            payload = stream.read(size)
        require(len(payload) == size and content_id(kind, payload) == key, "node digest mismatch")
        return kind, payload, decoded, scalars

    def _validate_references(self):
        for key in self.entries:
            kind, payload, _, _ = self.node(key)
            if kind not in (TEXT, RAW_BODY):
                refs = decode_refs(payload)
                require(all(ref in self.entries for ref in refs), "dangling node reference")
                if kind == CONCAT:
                    require(len(refs) == 2 and self.entries[refs[0]][4] == TEXT and self.entries[refs[1]][4] == RAW_BODY, "invalid raw context concatenation")
                if kind == RAW_OBJECT:
                    require(len(refs) == 4 and self.entries[refs[3]][4] == CONCAT, "invalid raw object structure")
                if kind == QUERY:
                    require(len(refs) == 4 and self.entries[refs[3]][4] == RAW_OBJECT, "invalid query root structure")

    def decode(self, root):
        require(root in self.entries and self.entries[root][4] == QUERY, "not a raw-query root")
        memo = {}
        visiting = set()
        materialized = 0

        def walk(key, depth):
            nonlocal materialized
            require(depth <= MAX_DEPTH and key not in visiting, "cyclic or over-depth reference")
            if key in memo:
                return memo[key]
            visiting.add(key)
            kind, payload, decoded, scalars = self.node(key)
            if kind in (TEXT, RAW_BODY):
                text = payload.decode("utf-8", "strict")
            else:
                refs = decode_refs(payload)
                # Check predicted lengths before allocating a repeated expansion.
                sizes = [self.entries[ref] for ref in refs]
                predicted_scalars = sum(s[3] for s in sizes)
                predicted_bytes = sum(s[2] for s in sizes)
                if kind != CONCAT:
                    overhead = sum(len(str(s[3])) + 1 for s in sizes)
                    predicted_scalars += overhead
                    predicted_bytes += overhead
                require(predicted_scalars == scalars and predicted_bytes == decoded, "declared expansion mismatch")
                require(materialized + predicted_bytes <= MAX_BYTES * 8, "aggregate decode limit")
                children = [walk(ref, depth + 1) for ref in refs]
                require(materialized + predicted_bytes <= MAX_BYTES * 8, "aggregate decode limit")
                text = "".join(children) if kind == CONCAT else packed(children)
            require(len(text) == scalars and len(text.encode("utf-8")) == decoded, "decoded length mismatch")
            materialized += decoded
            require(materialized <= MAX_BYTES * 8, "aggregate decode limit")
            memo[key] = text
            visiting.remove(key)
            return text

        return walk(root, 0).encode("utf-8")

    def restore(self, name):
        matches = [record for record in self.manifest["records"] if record["name"] == name]
        require(len(matches) == 1, "missing or duplicate record")
        record = matches[0]
        raw = self.decode(record["root"])
        require(len(raw) == record["legacy_bytes"] and sha(raw) == record["legacy_sha256"], "legacy record digest mismatch")
        return raw

    def reachable(self, roots):
        seen = set()
        pending = list(roots)
        while pending:
            key = pending.pop()
            require(key in self.entries, "dangling root")
            if key in seen:
                continue
            seen.add(key)
            kind, payload, _, _ = self.node(key)
            if kind not in (TEXT, RAW_BODY):
                pending.extend(decode_refs(payload))
        return seen

    def accounting(self):
        files = {name: (self.directory / name).stat().st_size for name in ("objects.pack", "objects.index", "manifest.json")}
        roots = [r["root"] for r in self.manifest["records"]]
        reachable = self.reachable(roots)
        require(reachable == set(self.entries), "bundle contains unreachable nodes")
        return dict(files=files, complete_reachable_bytes=sum(files.values()), reachable_nodes=len(reachable),
                    orphan_nodes=0, padding_bytes=0, external_dependencies=0,
                    allocated_file_bytes=sum((self.directory / name).stat().st_blocks * 512 for name in files),
                    allocated_directory_bytes=self.directory.stat().st_blocks * 512,
                    note="All payloads, reference hashes, index entries and manifest counted; no compression or external dictionary.")
