"""Independent, monotonic host packet construction and streaming budgets.

The lower checker retains its own accounting. No size here describes a C object.
Container units count headers and memberships; scalar byte strings use explicit
byte ceilings, never a guessed target allocation size. Reservations precede work.
"""
from __future__ import annotations

from functools import cmp_to_key
import hashlib
import json

from .packet_schema import LIMITS, NULL

# Fixed template vocabulary, not per-invocation allocated scratch.
_BYTE_DOMAINS = {
    'source': ('source_utf8_bytes', 'SOURCE_BYTES', 'packet.source_bytes', LIMITS['production_source_bytes']),
    'manifest': ('manifest_utf8_bytes', 'MANIFEST_BYTES', 'packet.manifest_bytes', LIMITS['manifest_bytes']),
    'supplement': ('supplement_utf8_bytes', 'SUPPLEMENT_BYTES', 'packet.supplement_bytes', LIMITS['supplement_bytes']),
    'path': (None, 'SOURCE_BYTES', 'packet.path_bytes', LIMITS['production_source_bytes']),
}


class PacketError(ValueError):
    __slots__ = ('_path', '_layer', '_code', '_message')

    def __init__(self, path, layer, code, message):
        ValueError.__init__(self, f'{path}: {layer}/{code}: {message}')
        object.__setattr__(self, '_path', path)
        object.__setattr__(self, '_layer', layer)
        object.__setattr__(self, '_code', code)
        object.__setattr__(self, '_message', message)

    path = property(lambda self: self._path)
    layer = property(lambda self: self._layer)
    code = property(lambda self: self._code)
    message = property(lambda self: self._message)

    def __setattr__(self, name, value):
        raise AttributeError('PacketError is immutable')


def fail(path, layer, code, message):
    raise PacketError(path, layer, code, message)


def uint(value, path, *, nullable=False):
    if nullable and value is None:
        return NULL
    if type(value) is not int or not 0 <= value <= NULL:
        fail(path, 'packet-schema', 'INTEGER', 'expected a plain uint32 integer')
    if nullable and value == NULL:
        fail(path, 'packet-schema', 'NULL_DOMAIN', 'logical null must be None')
    return value


class Budget:
    __slots__ = ('creation_units', 'work_units', 'source_utf8_bytes',
                 'manifest_utf8_bytes', 'supplement_utf8_bytes', '_frozen')

    def __init__(self):
        self.creation_units = self.work_units = self.source_utf8_bytes = 0
        self.manifest_utf8_bytes = self.supplement_utf8_bytes = 0
        self._frozen = False

    def reserve(self, *, creation=0, work=0):
        if self._frozen:
            raise RuntimeError('packet budget finalized')
        if type(creation) is not int or type(work) is not int or min(creation, work) < 0:
            raise ValueError('invalid packet reservation')
        if creation > LIMITS['host_creation'] - self.creation_units:
            fail('packet.creation_units', 'packet-bounds', 'CREATION_UNITS', 'packet construction quota exhausted')
        if work > LIMITS['host_work'] - self.work_units:
            fail('packet.work_units', 'packet-bounds', 'WORK_UNITS', 'packet examination quota exhausted')
        self.creation_units += creation
        self.work_units += work

    def creation(self, count=1):
        self.reserve(creation=count)

    def work(self, count=1):
        self.reserve(work=count)

    def listing(self, values=()):
        self.creation(1 + len(values))
        return list(values)

    def row(self, **fields):
        # Callers reserve fixed argument-record scratch before constructing it.
        self.creation(1 + len(fields))
        return dict(fields)

    def put(self, target, key, value):
        self.work()
        if key not in target:
            self.creation()
        target[key] = value
        return value

    def append(self, target, value):
        self.creation()
        target.append(value)
        return value

    def pair(self, left, right):
        self.creation(3)
        return (left, right)

    def ordered(self, values):
        n = len(values)
        self.creation(1 + 4 * n)  # result, comparator wrappers and sort scratch
        def compare(left, right):
            self.work()
            if type(left) is str and type(right) is str:
                for a, b in zip(left, right):
                    self.work()
                    if a != b:
                        return -1 if a < b else 1
                self.work()
                return (len(left) > len(right)) - (len(left) < len(right))
            return (left > right) - (left < right)
        return sorted(values, key=cmp_to_key(compare))

    def finalize(self):
        # Five keyed statistics pairs and their tuple are 1 + 5 * 4.
        # PacketEmission has one record header and eleven retained slot members.
        self.reserve(creation=1 + 5 * 4 + 12, work=12)
        self._frozen = True
        return (('creation_units', self.creation_units), ('work_units', self.work_units),
                ('source_utf8_bytes', self.source_utf8_bytes),
                ('manifest_utf8_bytes', self.manifest_utf8_bytes),
                ('supplement_utf8_bytes', self.supplement_utf8_bytes))


def exact(value, keys, path, budget):
    budget.work(1 + len(keys))
    if type(value) is not dict or len(value) != len(keys):
        fail(path, 'packet-schema', 'SCHEMA', 'expected the exact record fields')
    for key in keys:
        if key not in value:
            fail(path, 'packet-schema', 'SCHEMA', 'missing exact record field')


def same(actual, expected, path, budget):
    """Bounded type-exact tree comparison. False is never integer zero."""
    budget.creation(5)
    tasks = [(actual, expected)]
    while tasks:
        left, right = tasks.pop()
        budget.work()
        if type(left) is not type(right):
            fail(path, 'packet-mapping', 'EQUATION', 'packet value has a different plain type')
        if type(right) is dict:
            exact(left, right, path, budget)
            for key in right:
                budget.creation(4)
                tasks.append((left[key], right[key]))
        elif type(right) in (tuple, list):
            if len(left) != len(right):
                fail(path, 'packet-mapping', 'EQUATION', 'packet sequence length differs')
            for index in range(len(right)):
                budget.creation(4)
                tasks.append((left[index], right[index]))
        elif type(right) is str:
            budget.work(min(len(left), len(right)) + 1)
            if left != right:
                fail(path, 'packet-mapping', 'EQUATION', 'packet text differs')
        elif right is None or type(right) in (int, bool):
            if left != right:
                fail(path, 'packet-mapping', 'EQUATION', 'packet scalar differs')
        else:
            fail(path, 'packet-schema', 'SCHEMA', 'non-plain packet comparison value')


def decode_fresh(text, budget):
    """Only invocation-owned fresh checker strings, never a public ingress."""
    if type(text) is not str:
        fail('packet.snapshot', 'packet-schema', 'SCHEMA', 'fresh serialization must be text')
    budget.creation()
    stack = []
    in_string = escaped = False
    creation = size = 0
    for char in text:
        budget.work()
        n = ord(char)
        if 0xD800 <= n <= 0xDFFF:
            fail('packet.snapshot', 'packet-schema', 'SCHEMA', 'surrogate in fresh serialization')
        size += 1 if n < 128 else 2 if n < 2048 else 3 if n < 65536 else 4
        if size > LIMITS['production_source_bytes']:
            fail('packet.snapshot', 'packet-bounds', 'SOURCE_BYTES', 'fresh snapshot exceeds 32 MiB')
        if in_string:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char in ' \t\n\r':
            continue
        if char == ':':
            creation += 1
            continue
        if char == ',':
            if stack and stack[-1][0] == '[':
                stack[-1][1] = True
            continue
        if char in ']}':
            if not stack or stack[-1][0] != ('[' if char == ']' else '{'):
                fail('packet.snapshot', 'packet-schema', 'SCHEMA', 'malformed fresh serialization')
            stack.pop()
            continue
        if stack and stack[-1][0] == '[' and stack[-1][1]:
            creation += 1
            stack[-1][1] = False
        if char == '"':
            creation += 1  # decoded immutable string, including keys
            in_string = True
        elif char in '[{':
            if len(stack) >= 64:
                fail('packet.snapshot', 'packet-schema', 'SCHEMA', 'fresh snapshot depth exceeds 64')
            creation += 1
            budget.creation(4)
            stack.append([char, char == '['])
    if in_string or stack:
        fail('packet.snapshot', 'packet-schema', 'SCHEMA', 'incomplete fresh serialization')
    budget.reserve(creation=creation, work=2 * len(text) + creation + 1)
    try:
        return json.loads(text)
    except (TypeError, ValueError, RecursionError):
        fail('packet.snapshot', 'packet-schema', 'SCHEMA', 'malformed checker serialization')


class Writer:
    """One streaming byte ceiling shared by generated header and C source."""
    __slots__ = ('budget', 'kind', 'limit', 'size', 'chunks', 'buffer', 'digest',
                 'counter', 'error_code', 'error_path')

    def __new__(cls, budget, kind, limit):
        if kind not in _BYTE_DOMAINS or type(limit) is not int or not 0 <= limit <= _BYTE_DOMAINS[kind][3]:
            raise ValueError('packet writer cannot raise a frozen byte ceiling')
        # Instance header, ten retained slots, and list/bytearray/hash headers.
        # Encoder has no additional instance dictionary or retained fields.
        budget.creation(14)
        return object.__new__(cls)

    def __init__(self, budget, kind, limit):
        self.budget, self.kind, self.limit, self.size = budget, kind, limit, 0
        self.counter, self.error_code, self.error_path, _ = _BYTE_DOMAINS[kind]
        self.chunks, self.buffer, self.digest = [], bytearray(), hashlib.sha256()

    def emit(self, data):
        if type(data) is not bytes or len(data) > LIMITS['source_chunk_bytes']:
            fail('packet.source', 'packet-source', 'SOURCE_GRAMMAR', 'invalid bounded output token')
        used = getattr(self.budget, self.counter) if self.counter is not None else self.size
        if len(data) > self.limit - used:
            fail(self.error_path, 'packet-bounds', self.error_code, 'packet output byte quota exhausted')
        self.budget.work(len(data))
        if len(self.buffer) + len(data) > LIMITS['source_chunk_bytes']:
            self.flush()
        if self.counter is not None:
            setattr(self.budget, self.counter, used + len(data))
        self.size += len(data)
        self.buffer.extend(data)

    def flush(self):
        if self.buffer:
            self.budget.reserve(creation=2, work=len(self.buffer))
            chunk = bytes(self.buffer)
            self.chunks.append(chunk)
            self.digest.update(chunk)
            self.buffer.clear()

    def ascii(self, text):
        self.budget.creation()
        self.emit(text.encode('ascii'))

    def number(self, value):
        uint(value, 'packet.source.integer')
        self.budget.creation(2)
        self.emit(str(value).encode('ascii'))

    def finish(self):
        self.flush()
        self.budget.reserve(creation=7, work=2 * self.size + 64)  # bytes/text/digest and return tuple
        data = b''.join(self.chunks)
        return data.decode('utf-8'), self.digest.hexdigest(), self.size


class Encoder(Writer):
    __slots__ = ()

    def string(self, text):
        self.emit(b'"')
        for char in text:
            self.budget.work()
            value = ord(char)
            if 0xD800 <= value <= 0xDFFF:
                fail('packet.json', 'packet-schema', 'SCHEMA', 'surrogate in JSON')
            if char == '"': self.emit(b'\\"')
            elif char == '\\': self.emit(b'\\\\')
            elif char == '\b': self.emit(b'\\b')
            elif char == '\f': self.emit(b'\\f')
            elif char == '\n': self.emit(b'\\n')
            elif char == '\r': self.emit(b'\\r')
            elif char == '\t': self.emit(b'\\t')
            elif value < 32:
                self.budget.creation(2)
                self.emit(('\\u%04x' % value).encode('ascii'))
            else:
                self.budget.creation()
                self.emit(char.encode('utf-8'))
        self.emit(b'"')

    def task(self, tasks, action, value):
        self.budget.creation(4)
        tasks.append((action, value))

    def value(self, value):
        self.budget.creation(5)
        tasks = [('value', value)]
        while tasks:
            action, item = tasks.pop()
            self.budget.work()
            if action == 'literal': self.emit(item)
            elif action == 'string': self.string(item)
            elif item is None: self.emit(b'null')
            elif type(item) is bool: self.emit(b'true' if item else b'false')
            elif type(item) is int: self.number(item)
            elif type(item) is str: self.string(item)
            elif type(item) in (tuple, list):
                self.emit(b'[')
                self.task(tasks, 'literal', b']')
                for index in range(len(item) - 1, -1, -1):
                    self.task(tasks, 'value', item[index])
                    if index: self.task(tasks, 'literal', b',')
            elif type(item) is dict:
                names = self.budget.ordered(item)
                self.emit(b'{')
                self.task(tasks, 'literal', b'}')
                for index in range(len(names) - 1, -1, -1):
                    name = names[index]
                    if type(name) is not str:
                        fail('packet.json', 'packet-schema', 'SCHEMA', 'non-string JSON key')
                    self.task(tasks, 'value', item[name])
                    self.task(tasks, 'literal', b':')
                    self.task(tasks, 'string', name)
                    if index: self.task(tasks, 'literal', b',')
            else:
                fail('packet.json', 'packet-schema', 'SCHEMA', 'non-plain JSON value')


def encode(value, budget, kind, limit):
    result = Encoder(budget, kind, limit)
    result.value(value)
    return result.finish()
