"""One-level, offline immutable overlay for the query representation prototype.

The codec module is an explicit dependency. Base paths are caller supplied;
manifests cannot choose paths or introduce recursive base chains. No GC or
production transaction semantics are implemented.
"""
import hashlib
import json
from pathlib import Path
import struct

FORMAT = "mlf-offline-query-overlay-1"
SCOPE = "source-v6/CACHE-1/raw-only"
MAX_TOTAL_OVERLAY_WRITES = 256 * 1024
written_bytes = 0
DESCRIPTOR_FIELDS = ("pack_bytes", "pack_sha256", "index_sha256", "node_count")


def descriptor(manifest):
    return {name: manifest[name] for name in DESCRIPTOR_FIELDS}


def write_overlay(codec, directory, base, nodes, records):
    """Publish a new, small overlay; base objects are never copied or modified."""
    global written_bytes
    directory = Path(directory)
    codec.require(set(base) == set(DESCRIPTOR_FIELDS), "invalid base descriptor")
    codec.require(len(nodes) <= codec.MAX_NODES, "delta node-count limit")
    rows = bytearray(codec.MAGIC + struct.pack("<I", len(nodes)))
    digest = hashlib.sha256()
    offset = 0
    for key, (kind, payload, decoded, scalars) in sorted(nodes.items()):
        codec.require(codec.content_id(kind, payload) == key, "invalid delta content identity")
        digest.update(payload)
        rows += codec.ENTRY.pack(bytes.fromhex(key), offset, len(payload), decoded, scalars, kind)
        offset += len(payload)
    records = sorted(records, key=lambda row: row["name"])
    codec.require(len({row["name"] for row in records}) == len(records), "duplicate root name")
    manifest = dict(format=FORMAT, semantic_scope=SCOPE, base=dict(base), records=records,
                    delta=dict(pack_bytes=offset, pack_sha256=digest.hexdigest(),
                               index_sha256=codec.sha(rows), node_count=len(nodes)))
    encoded = codec.canonical_json(manifest)
    total = offset + len(rows) + len(encoded)
    codec.require(total <= MAX_TOTAL_OVERLAY_WRITES and written_bytes + total <= MAX_TOTAL_OVERLAY_WRITES,
                  "overlay write reservation exceeded")
    written_bytes += total
    directory.mkdir(exist_ok=False)
    with (directory / "objects.pack").open("xb") as stream:
        for _, (_, payload, _, _) in sorted(nodes.items()):
            stream.write(payload)
    (directory / "objects.index").write_bytes(rows)
    # Offline manifest-last publication only; not fsync/concurrent-writer safety.
    (directory / "manifest.json").write_bytes(encoded)
    return manifest


class OverlayReader:
    """Restore from exactly base(pack,index) + delta(pack,index,manifest).

    No old manifest or preloaded Reader object is needed. File-audit counters
    report actual bytes returned by logical reads, not physical disk traffic.
    """
    def __init__(self, codec, base_directory, directory, ledger=None):
        self.codec = codec
        self.base_directory = Path(base_directory).absolute()
        self.directory = Path(directory).absolute()
        self.ledger = ledger
        self.io = {}
        codec.require(self.base_directory.resolve() == self.base_directory and
                      self.directory.resolve() == self.directory, "symlink directory")
        self.manifest = json.loads(self._read(self.directory / "manifest.json", 1024 * 1024))
        m = self.manifest
        codec.require(m["format"] == FORMAT and m["semantic_scope"] == SCOPE, "unsupported overlay schema")
        codec.require(set(m["base"]) == set(DESCRIPTOR_FIELDS) and set(m["delta"]) == set(DESCRIPTOR_FIELDS),
                      "invalid layer descriptor")
        codec.require(type(m["base"]["node_count"]) is int and type(m["delta"]["node_count"]) is int,
                      "invalid layer count")
        codec.require(m["base"]["node_count"] + m["delta"]["node_count"] <= codec.MAX_NODES,
                      "combined node-count limit")
        codec.require(type(m["base"]["pack_bytes"]) is int and type(m["delta"]["pack_bytes"]) is int,
                      "invalid layer length")
        codec.require(0 <= m["base"]["pack_bytes"] + m["delta"]["pack_bytes"] <= codec.MAX_BYTES,
                      "combined pack-size limit")
        base = self._load_layer(self.base_directory, m["base"])
        delta = self._load_layer(self.directory, m["delta"])
        codec.require(not set(base).intersection(delta), "duplicate identity across base and delta")
        self.entries = {**base, **delta}
        self.sources = {key: self.base_directory / "objects.pack" for key in base}
        self.sources.update({key: self.directory / "objects.pack" for key in delta})
        self.base_ids = set(base)
        self.delta_ids = set(delta)
        codec.Reader._validate_references(self)

    def _note(self, path, size, operation):
        key = str(path)
        row = self.io.setdefault(key, dict(bytes=0, calls=0, file_calls=0, node_calls=0))
        row["bytes"] += size
        row["calls"] += 1
        row[operation + "_calls"] += 1
        if self.ledger is not None:
            self.ledger(key, size, operation)

    def _read(self, path, limit):
        c = self.codec
        c.require(path.is_file() and not path.is_symlink() and path.stat().st_size <= limit, "invalid layer file")
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
        self._note(path, len(data), "file")
        c.require(len(data) <= limit, "layer file-size limit")
        return data

    def _load_layer(self, directory, expected):
        c = self.codec
        index = self._read(directory / "objects.index", c.MAX_BYTES)
        c.require(c.sha(index) == expected["index_sha256"], "layer index digest mismatch")
        c.require(len(index) >= 12 and index[:8] == c.MAGIC, "invalid layer index magic")
        count, = struct.unpack_from("<I", index, 8)
        c.require(count == expected["node_count"] and count <= c.MAX_NODES and len(index) == 12 + count * c.ENTRY.size,
                  "invalid layer index length")
        entries, previous, end = {}, None, 0
        for pos in range(12, len(index), c.ENTRY.size):
            key, offset, size, decoded, scalars, kind = c.ENTRY.unpack_from(index, pos)
            c.require(previous is None or previous < key, "duplicate or unsorted layer identity")
            c.require(offset == end and size <= c.MAX_BYTES and decoded <= c.MAX_BYTES and
                      scalars <= decoded and kind in c.KINDS, "invalid layer node bounds")
            end = offset + size
            c.require(end <= c.MAX_BYTES, "layer pack-size limit")
            entries[key.hex()] = (offset, size, decoded, scalars, kind)
            previous = key
        c.require(end == expected["pack_bytes"], "layer pack length mismatch")
        pack = self._read(directory / "objects.pack", c.MAX_BYTES)
        c.require(len(pack) == end and c.sha(pack) == expected["pack_sha256"], "layer pack digest mismatch")
        return entries

    def node(self, key):
        c = self.codec
        c.require(key in self.entries, "dangling node reference")
        offset, size, decoded, scalars, kind = self.entries[key]
        path = self.sources[key]
        c.require(not path.is_symlink(), "symlink pack")
        with path.open("rb") as stream:
            stream.seek(offset)
            payload = stream.read(size)
        self._note(path, len(payload), "node")
        c.require(len(payload) == size and c.content_id(kind, payload) == key, "layer node digest mismatch")
        return kind, payload, decoded, scalars

    def decode(self, root):
        return self.codec.Reader.decode(self, root)

    def restore(self, name):
        return self.codec.Reader.restore(self, name)

    def reachable(self, roots):
        return self.codec.Reader.reachable(self, roots)

    def physical_accounting(self, pinned_old_manifest=None):
        paths = [self.base_directory / name for name in ("objects.pack", "objects.index")]
        paths += [self.directory / name for name in ("objects.pack", "objects.index", "manifest.json")]
        if pinned_old_manifest is not None:
            paths.append(Path(pinned_old_manifest))
        self.codec.require(len({str(p) for p in paths}) == len(paths), "duplicate physical path")
        return dict(files={str(p): p.stat().st_size for p in paths},
                    complete_physical_bytes=sum(p.stat().st_size for p in paths),
                    allocated_file_bytes=sum(p.stat().st_blocks * 512 for p in paths),
                    allocated_directory_bytes=sum(p.stat().st_blocks * 512 for p in {self.base_directory, self.directory}),
                    external_file_dependencies=2,
                    note="Counts whole base pack/index, including dead nodes that cannot be removed without rewriting a pack.")
