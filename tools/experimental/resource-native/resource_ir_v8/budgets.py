"""Monotonic host creation/work limits and bounded canonical UTF-8 emission.

This module does not import or execute any runtime. Charges precede insertion.
Fixed record fields are covered by row charges; variable members are separate.
"""
from __future__ import annotations

import hashlib
from .program_schema import fail

CREATION_LIMIT = 65_536
ORDER_WORK_LIMIT = 8_388_608
DERIVED_BYTES = 33_554_432
CHUNK_BYTES = 4_096


class Budget:
    __slots__ = ('creation_units', 'order_edge_examinations')

    def __init__(self):
        self.creation_units = 0
        self.order_edge_examinations = 0

    def charge(self, units=1):
        if type(units) is not int or units < 0:
            raise ValueError('invalid creation charge')
        if units > CREATION_LIMIT - self.creation_units:
            fail('analysis.creation_units', 'bounds', 'ANALYSIS_ROWS', 'analysis creation budget exhausted')
        self.creation_units += units

    def examine(self, count=1):
        if type(count) is not int or count < 0:
            raise ValueError('invalid order-work charge')
        if count > ORDER_WORK_LIMIT - self.order_edge_examinations:
            fail('analysis.order_edge_examinations', 'bounds', 'ORDER_WORK', 'order edge-work budget exhausted')
        self.order_edge_examinations += count

    def append(self, target, value):
        self.charge()
        target.append(value)
        return value

    def put(self, target, key, value):
        if key not in target:
            self.charge()
        target[key] = value
        return value

    def add(self, target, value):
        if value not in target:
            self.charge()
            target.add(value)

    def row(self, **fields):
        self.charge()
        return dict(fields)

    def record_append(self, target, **fields):
        """One new fixed record plus its inventory member, one atomic batch."""
        self.charge(2)
        record = dict(fields)
        target.append(record)
        return record

    def listing(self, source):
        self.charge(len(source))
        return list(source)

    def ordered(self, source, *, key=None):
        self.charge(len(source))
        return sorted(source, key=key)

    def tuple(self, source):
        self.charge(len(source))
        return tuple(source)

    def copied_dict(self, source):
        self.charge(len(source))
        return source.copy()

    def copied_set(self, source):
        self.charge(len(source))
        return source.copy()


class CanonicalEncoder:
    """At most 4096-byte append chunks, accounting before every append.

    Traversal is depth-bounded by ingress/finite generated records. Buffers alone
    are excluded from creation units. Long strings are never pre-encoded whole.
    """
    __slots__ = ('limit', 'raw', 'size', 'chunks', 'buffer', 'digest')

    def __init__(self, limit=DERIVED_BYTES, *, raw=False):
        self.limit, self.raw, self.size = limit, raw, 0
        self.chunks = []
        self.buffer = bytearray()
        self.digest = hashlib.sha256()

    def emit(self, data):
        if len(data) > CHUNK_BYTES:
            raise ValueError('encoder append exceeds 4096 bytes')
        if len(data) > self.limit - self.size:
            if self.raw:
                fail('program', 'schema', 'INPUT_BYTES', 'canonical input exceeds 32 MiB')
            fail('analysis.derived_bytes', 'bounds', 'DERIVED_BYTES', 'derived canonical JSON exceeds 32 MiB')
        self.size += len(data)
        if len(self.buffer) + len(data) > CHUNK_BYTES:
            chunk = bytes(self.buffer)
            self.chunks.append(chunk)
            self.digest.update(chunk)
            self.buffer.clear()
        self.buffer.extend(data)

    def string(self, value):
        self.emit(b'"')
        escapes = {'"': b'\\"', '\\': b'\\\\', '\b': b'\\b', '\f': b'\\f',
                   '\n': b'\\n', '\r': b'\\r', '\t': b'\\t'}
        for char in value:
            n = ord(char)
            if char in escapes:
                self.emit(escapes[char])
            elif n < 32:
                self.emit(('\\u%04x' % n).encode('ascii'))
            elif 0xD800 <= n <= 0xDFFF:
                fail('program' if self.raw else 'analysis.derived_bytes',
                     'schema' if self.raw else 'bounds', 'UTF8', 'surrogate in JSON string')
            else:
                self.emit(char.encode('utf-8'))
        self.emit(b'"')

    def value(self, value):
        if value is None:
            self.emit(b'null')
        elif type(value) is bool:
            self.emit(b'true' if value else b'false')
        elif type(value) is int:
            if value.bit_length() > 64:
                fail('program' if self.raw else 'analysis.derived_bytes',
                     'schema' if self.raw else 'bounds', 'INTEGER', 'integer exceeds serialization domain')
            self.emit(str(value).encode('ascii'))
        elif type(value) is str:
            self.string(value)
        elif type(value) in (list, tuple):
            self.emit(b'[')
            for index, item in enumerate(value):
                if index:
                    self.emit(b',')
                self.value(item)
            self.emit(b']')
        elif type(value) is dict:
            self.emit(b'{')
            # This bounded encoder traversal buffer is not semantic analysis.
            for index, key in enumerate(sorted(value)):
                if index:
                    self.emit(b',')
                self.string(key)
                self.emit(b':')
                self.value(value[key])
            self.emit(b'}')
        else:
            raise TypeError('canonical encoder requires plain JSON')

    def finish(self):
        if self.buffer:
            chunk = bytes(self.buffer)
            self.chunks.append(chunk)
            self.digest.update(chunk)
            self.buffer.clear()
        return b''.join(self.chunks).decode('utf-8'), self.digest.hexdigest()


def canonical_encode(value, *, limit=DERIVED_BYTES, raw=False):
    encoder = CanonicalEncoder(limit, raw=raw)
    encoder.value(value)
    return encoder.finish()
