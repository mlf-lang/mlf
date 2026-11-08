#!/usr/bin/env python3
"""Independent MLFBIN v1 reader. Written from wire/WIRE.md, not target output.

No production imports; stdlib only. Tables remain a DAG, so verification does
not expand sharing. CRC is corruption checking, never an authenticity claim.
The caller separately checks SHA256 content addresses and typed admission.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import struct
import zlib

MAGIC = b'MLFBIN\r\n'
MAX_I = (1 << 63) - 1
MIN_I = -(1 << 63)
MAX_CAP = (1 << 31) - 1

class Invalid(ValueError):
    pass

def require(condition, reason):
    if not condition:
        raise Invalid(reason)

@dataclass(frozen=True)
class Limits:
    bytes: int = 256 * 1024**2
    symbols: int = 1048576
    symbol_bytes: int = 16 * 1024**2
    total_symbol_bytes: int = 128 * 1024**2
    nodes: int = 4194304
    edges: int = 16777216
    depth: int = 16384
    work: int = 67108864

    def validate(self):
        values = (self.bytes, self.symbols, self.symbol_bytes, self.total_symbol_bytes,
                  self.nodes, self.edges, self.depth, self.work)
        require(all(isinstance(x, int) and 0 <= x <= MAX_CAP for x in values), 'invalid limits')
        require(self.bytes >= 80 and 1 <= self.depth <= 65536 and
                self.symbol_bytes <= self.total_symbol_bytes <= self.bytes, 'invalid limits relationships')

@dataclass(frozen=True)
class Node:
    kind: int
    data: object

@dataclass(frozen=True)
class Document:
    schema: int
    symbols: tuple[str, ...]
    symbol_sizes: tuple[int, ...]
    nodes: tuple[Node, ...]
    roots: tuple[int, ...]
    depths: tuple[int, ...]
    expanded_work: tuple[int, ...]
    edges: int
    raw_size: int

    def values(self):
        """Build shared Python tuples, not a recursively duplicated JSON tree."""
        out = []
        for node in self.nodes:
            if node.kind == 2:
                out.append(('text', self.symbols[node.data]))
            elif node.kind == 3:
                tag, refs = node.data
                out.append(('node', tag, tuple(out[i] for i in refs)))
            else:
                out.append(('int' if node.kind == 0 else 'bits', node.data))
        return tuple(out[i] for i in self.roots)

    def accounting(self):
        return dict(schema=self.schema, physical_bytes=self.raw_size, symbols=len(self.symbols),
                    symbol_utf8_bytes=sum(self.symbol_sizes), nodes=len(self.nodes), edges=self.edges,
                    roots=len(self.roots), depth=max(self.depths, default=0),
                    root_expanded_work=sum(self.expanded_work[i] for i in self.roots),
                    shared_node_references=self.edges + len(self.roots) - len(self.nodes))

def width(count):
    return max(1, (count - 1).bit_length()) if count else 1

class Bits:
    def __init__(self, data):
        self.data, self.position = data, 0
    def take(self, count):
        require(0 <= count and self.position + count <= 8 * len(self.data), 'truncated bit field')
        value = 0
        for i in range(count):
            absolute = self.position + i
            value |= ((self.data[absolute // 8] >> (absolute % 8)) & 1) << i
        self.position += count
        return value
    def varuint(self):
        value = 0
        for group in range(10):
            byte = self.take(8)
            payload = byte & 127
            require(group < 9 or byte <= 1, 'varint exceeds 64 bits')
            value |= payload << (7 * group)
            if not byte & 128:
                require(group == 0 or payload != 0, 'noncanonical varint')
                return value
        raise Invalid('unterminated varint')
    def finish(self):
        remaining = len(self.data) * 8 - self.position
        require(0 <= remaining < 8, 'extra section padding byte')
        require(self.take(remaining) == 0, 'nonzero section padding')

def read_document(raw: bytes, schema: int, limits=Limits()):
    limits.validate()
    require(isinstance(raw, bytes), 'immutable bytes input required')
    require(0 <= schema <= MAX_CAP, 'invalid expected schema')
    require(80 <= len(raw) <= limits.bytes, 'file length cap/header')
    require(raw[:8] == MAGIC, 'binary magic')
    (version, flags, actual_schema, header, total, ns, so, sl, nn, no, nl,
     edge_count, nr, ro, rl, nw, sw, crc) = struct.unpack_from('<18I', raw, 8)
    require(version == 1 and flags == 0 and header == 80, 'version/flags/header')
    require(actual_schema == schema, 'schema mismatch')
    require(total == len(raw) and so == 80 and no == so + sl and ro == no + nl
            and ro + rl == total, 'section framing/trailing bytes')
    require(ns <= limits.symbols and nn <= limits.nodes and edge_count <= limits.edges
            and nr <= limits.edges, 'count cap')
    require(nw == width(nn) and sw == width(ns), 'noncanonical reference width')
    require(rl == (nr * nw + 7) // 8, 'root section length')
    require(zlib.crc32(raw[:76] + b'\0\0\0\0' + raw[80:]) == crc, 'CRC32 mismatch')
    # No count-based preallocation occurs until bounds and checksum pass.
    symbols, sizes, seen_symbols, total_symbols = [], [], set(), 0
    sb = Bits(raw[so:no])
    for _ in range(ns):
        size = sb.varuint()
        require(size <= limits.symbol_bytes and size <= limits.total_symbol_bytes - total_symbols,
                'symbol byte cap')
        require(sb.position % 8 == 0 and size <= (len(sb.data) * 8 - sb.position) // 8,
                'truncated symbol')
        start = sb.position // 8
        encoded = sb.data[start:start + size]
        sb.position += size * 8
        try:
            symbol = encoded.decode('utf-8', errors='strict')
        except UnicodeDecodeError as error:
            raise Invalid('noncanonical UTF-8') from error
        require(symbol not in seen_symbols, 'duplicate symbol')
        seen_symbols.add(symbol)
        symbols.append(symbol); sizes.append(size); total_symbols += size
    require(sb.position == len(sb.data) * 8, 'symbol section trailing bytes')
    nodes, seen_nodes, depths, work = [], set(), [], []
    nb, actual_edges, used_symbols = Bits(raw[no:ro]), 0, set()
    for index in range(nn):
        kind = nb.take(2)
        depth, cost = 1, 1
        if kind == 0:
            unsigned = nb.varuint()
            data = (unsigned >> 1) ^ -(unsigned & 1)
        elif kind == 1:
            unsigned = nb.take(64)
            data = unsigned - (1 << 64) if unsigned > MAX_I else unsigned
        elif kind == 2:
            data = nb.take(sw)
            require(data < ns, 'symbol index')
            if data not in used_symbols:
                require(data == len(used_symbols), 'symbol first-use order')
                used_symbols.add(data)
            cost += sizes[data]
        else:
            tag, arity = nb.varuint(), nb.varuint()
            require(tag <= MAX_CAP, 'tag range')
            require(arity <= limits.edges - actual_edges, 'child-edge cap')
            require(arity <= (len(nb.data) * 8 - nb.position) // nw, 'truncated children')
            refs = []
            for _ in range(arity):
                child = nb.take(nw)
                require(child < index, 'nonbackwards/cyclic child index')
                refs.append(child)
                depth = max(depth, depths[child] + 1)
                require(work[child] <= limits.work - cost, 'expanded work cap')
                cost += work[child]
            data = tag, tuple(refs)
            actual_edges += arity
        require(depth <= limits.depth and cost <= limits.work, 'depth/expanded work cap')
        key = kind, data
        require(key not in seen_nodes, 'duplicate structural node')
        seen_nodes.add(key); nodes.append(Node(kind, data)); depths.append(depth); work.append(cost)
    nb.finish()
    require(actual_edges == edge_count and len(used_symbols) == ns, 'edge count/unused symbols')
    rb, roots, total_work = Bits(raw[ro:]), [], 0
    for _ in range(nr):
        root = rb.take(nw)
        require(root < nn, 'root index')
        require(work[root] <= limits.work - total_work, 'ordered root work cap')
        total_work += work[root]; roots.append(root)
    rb.finish()
    visited, next_id = set(), 0
    stack = [(r, False) for r in reversed(roots)]
    while stack:
        index, complete = stack.pop()
        if index in visited:
            continue
        if complete:
            require(index == next_id, 'noncanonical postorder')
            visited.add(index); next_id += 1
        else:
            stack.append((index, True))
            node = nodes[index]
            if node.kind == 3:
                stack.extend((child, False) for child in reversed(node.data[1]))
    require(next_id == nn, 'unreachable node')
    return Document(schema, tuple(symbols), tuple(sizes), tuple(nodes), tuple(roots),
                    tuple(depths), tuple(work), actual_edges, len(raw))

# Independent fixture-only writer. It intentionally accepts an explicit table,
# so malformed cases do not depend on finding a production-encoder loophole.
class Writer:
    def __init__(self):
        self._buffer = bytearray()
        self._count = 0
        self._legacy_bits = None
        self._legacy = False

    @property
    def bits(self):
        # Preserve the original mutable-list attribute when explicitly observed.
        # Normal encoder callers never request it and retain packed storage.
        if not self._legacy:
            self._legacy_bits = [(self._buffer[i // 8] >> (i % 8)) & 1
                                 for i in range(self._count)]
            self._legacy = True
        return self._legacy_bits

    @bits.setter
    def bits(self, value):
        self._legacy_bits = value
        self._legacy = True

    def put(self, value, count):
        require(0 <= value < 1 << count, 'fixture bit range')
        if self._legacy:
            self._legacy_bits.extend((value >> i) & 1 for i in range(count))
            return
        # A zero-width write has no data operation, just as range(0) did.
        if count == 0:
            return
        offset = self._count & 7
        if offset:
            take = min(8 - offset, count)
            self._buffer[-1] |= (value & ((1 << take) - 1)) << offset
            value >>= take
            count -= take
            self._count += take
        whole, tail = divmod(count, 8)
        if whole:
            self._buffer.extend((value & ((1 << (whole * 8)) - 1)).to_bytes(whole, 'little'))
            value >>= whole * 8
            self._count += whole * 8
        if tail:
            self._buffer.append(value & ((1 << tail) - 1))
            self._count += tail

    def varuint(self, value):
        require(0 <= value < 1 << 64, 'fixture unsigned range')
        while value >= 128:
            self.put((value & 127) | 128, 8); value >>= 7
        self.put(value, 8)

    def bytes(self):
        if self._legacy:
            result = bytearray((len(self._legacy_bits) + 7) // 8)
            for i, bit in enumerate(self._legacy_bits): result[i // 8] |= bit << (i % 8)
            return bytes(result)
        return bytes(self._buffer)

def repair_crc(raw):
    value = bytearray(raw); value[76:80] = b'\0' * 4
    struct.pack_into('<I', value, 76, zlib.crc32(value))
    return bytes(value)

def explicit_document(symbols, nodes, roots, schema=7, *, node_width=None, symbol_width=None):
    nw = width(len(nodes)) if node_width is None else node_width
    sw = width(len(symbols)) if symbol_width is None else symbol_width
    sb, nb, rb = Writer(), Writer(), Writer()
    for symbol in symbols:
        encoded = symbol.encode('utf-8') if isinstance(symbol, str) else symbol
        sb.varuint(len(encoded))
        for byte in encoded: sb.put(byte, 8)
    edges = 0
    for kind, data in nodes:
        nb.put(kind, 2)
        if kind == 0: nb.varuint(((data << 1) ^ (data >> 63)) & ((1 << 64) - 1))
        elif kind == 1: nb.put(data & ((1 << 64) - 1), 64)
        elif kind == 2: nb.put(data, sw)
        else:
            tag, refs = data; nb.varuint(tag); nb.varuint(len(refs)); edges += len(refs)
            for child in refs: nb.put(child, nw)
    for root in roots: rb.put(root, nw)
    s, n, r = sb.bytes(), nb.bytes(), rb.bytes()
    header = MAGIC + struct.pack('<18I', 1, 0, schema, 80, 80 + len(s+n+r), len(symbols),
        80, len(s), len(nodes), 80 + len(s), len(n), edges, len(roots), 80 + len(s+n),
        len(r), nw, sw, 0)
    return repair_crc(header + s + n + r)

def tree_document(roots, schema=7):
    """Reference encoder over ('int',n)/('bits',n)/('text',s)/('node',tag,children)."""
    symbols, symbol_ids, nodes, node_ids, indices = [], {}, [], {}, {}
    tasks = [(value, False) for value in reversed(roots)]
    while tasks:
        value, complete = tasks.pop()
        identity = id(value)
        if identity in indices: continue
        kind = value[0]
        if kind == 'node' and not complete:
            tasks.append((value, True)); tasks.extend((x, False) for x in reversed(value[2])); continue
        if kind == 'text':
            if value[1] not in symbol_ids:
                symbol_ids[value[1]] = len(symbols); symbols.append(value[1])
            key = 2, symbol_ids[value[1]]
        elif kind == 'node': key = 3, (value[1], tuple(indices[id(x)] for x in value[2]))
        else: key = (0 if kind == 'int' else 1), value[1]
        if key not in node_ids:
            node_ids[key] = len(nodes); nodes.append(key)
        indices[identity] = node_ids[key]
    return explicit_document(symbols, nodes, [indices[id(x)] for x in roots], schema)

def physical_inventory(root):
    """Full pathname-conservative disk accounting; no reachable-only shortcut."""
    import stat
    rows, total, allocated, directories = {}, 0, 0, 0
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), 'nonregular artifact tree')
        allocated += info.st_blocks * 512
        require(allocated <= 16 * 1024**2, 'original complete allocated tree cap')
        if stat.S_ISDIR(info.st_mode):
            if path != root: directories += 1
        else:
            require(info.st_nlink == 1, 'hardlinked artifact')
            require(info.st_size <= 16 * 1024**2 - total, 'original complete logical tree cap')
            # POSIX record locks are dropped on closing *any* descriptor for
            # their inode. A canonical zero-byte .lock needs no reopen/close.
            if path.name == '.lock':
                require(info.st_size == 0, 'nonempty lock sentinel'); raw = b''
            else: raw = path.read_bytes()
            total += len(raw)
            rows[str(path.relative_to(root))] = dict(bytes=len(raw), allocated=info.st_blocks * 512,
                sha256=hashlib.sha256(raw).hexdigest(), mtime_ns=info.st_mtime_ns, ctime_ns=info.st_ctime_ns)
    return dict(files=rows, directories_excluding_root=directories, all_logical_bytes=total, all_pathname_conservative_allocated_bytes=allocated,
                no_gc_performed=True)
