"""Independent reserve-before-construction accounting for Stage05 source only.

Units are abstract headers/memberships, not guessed Python or target C bytes.
The unchanged public packet and resource admissions retain their own budgets.
"""
from __future__ import annotations

from functools import cmp_to_key
import hashlib
import json

LIMITS = {
    'creation_units': 2097152, 'work_units': 16777216,
    'source_utf8_bytes': 33554432, 'manifest_utf8_bytes': 8388608,
    'label_utf8_bytes': 1048576, 'label_count': 65536,
    'source_chunk_bytes': 4096, 'frame_pointer_cells': 512,
    'typed_static_bytes': 4194304, 'owned_json_depth': 64,
}
_PATHS = {
    'BINDING': 'runtime.bindings', 'CODE_CENSUS': 'runtime.code_mapping',
    'PATH': 'runtime.paths', 'SITE': 'runtime.sites', 'INTRO': 'runtime.introductions',
    'USE': 'runtime.uses', 'OPERAND': 'runtime.operands', 'OPCODE': 'runtime.helpers',
    'LIVENESS': 'runtime.liveness', 'FRAME_POINTER_CELLS': 'runtime.frames',
    'SNAPSHOT_DEPTH': 'runtime.snapshot_depth', 'LABEL_COUNT': 'runtime.labels_count',
    'LABEL_BYTES': 'runtime.label_bytes', 'SOURCE_BYTES': 'runtime.source_bytes',
    'MANIFEST_BYTES': 'runtime.manifest_bytes', 'CREATION_UNITS': 'runtime.creation_units',
    'WORK_UNITS': 'runtime.work_units', 'ABI': 'runtime.abi',
}
_BOUNDS = ('FRAME_POINTER_CELLS', 'SNAPSHOT_DEPTH', 'LABEL_COUNT', 'LABEL_BYTES',
           'SOURCE_BYTES', 'MANIFEST_BYTES', 'CREATION_UNITS', 'WORK_UNITS')


class RuntimeEmissionError(ValueError):
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
        raise AttributeError('RuntimeEmissionError is immutable')


def fail(code, message, *, schema=False):
    layer = ('runtime-emitter-bounds' if code in _BOUNDS else
             'runtime-emitter-schema' if schema else
             'runtime-emitter-liveness' if code == 'LIVENESS' else
             'runtime-emitter-mapping')
    raise RuntimeEmissionError(_PATHS[code], layer, code, message)


class Budget:
    # Fixed control counters are not recursively charged to themselves.
    __slots__ = ('creation_units', 'work_units', 'source_utf8_bytes',
                 'manifest_utf8_bytes', 'label_utf8_bytes', 'label_count', '_reserved', '_frozen')

    def __init__(self):
        self.creation_units = self.work_units = self.source_utf8_bytes = 0
        self.manifest_utf8_bytes = self.label_utf8_bytes = self.label_count = 0
        self._reserved = self._frozen = False

    def reserve(self, *, creation=0, work=0):
        if self._frozen:
            raise RuntimeError('runtime emission budget finalized')
        if type(creation) is not int or type(work) is not int or creation < 0 or work < 0:
            raise ValueError('invalid runtime emission reservation')
        if creation > LIMITS['creation_units'] - self.creation_units:
            fail('CREATION_UNITS', 'construction allowance exhausted')
        if work > LIMITS['work_units'] - self.work_units:
            fail('WORK_UNITS', 'examination allowance exhausted')
        self.creation_units += creation
        self.work_units += work

    def creation(self, count=1):
        self.reserve(creation=count)

    def work(self, count=1):
        self.reserve(work=count)

    def scratch(self, fields):
        # Must precede caller construction of variable-containing kwargs/tuples.
        self.creation(1 + fields)

    def row(self, **fields):
        self.creation(1 + len(fields))
        return dict(fields)

    def mapping(self):
        self.creation()
        return {}

    def listing(self, values=()):
        self.creation(1 + len(values))
        return list(values)

    def contains(self, target, key):
        """Charge this mapping/set membership, even after a prior key use."""
        self.key_work(key)
        return key in target

    def put(self, target, key, value):
        if not self.contains(target, key):
            self.creation()
        self.key_work(key)  # insertion/replacement is a second examination
        target[key] = value
        return value

    def get(self, target, key, code):
        if not self.contains(target, key):
            fail(code, 'required checked reference is absent')
        self.key_work(key)  # lookup is separate from the membership test
        return target[key]

    def key_work(self, key):
        # Composite path/name keys include long strings. Charge their complete
        # bounded tuple tree before hashing or dictionary comparison.
        self.creation(6)
        pending = [(key, 0)]
        while pending:
            item, depth = pending.pop()
            self.work()
            if type(item) in (str, bytes):
                self.work(len(item))
            elif type(item) is tuple:
                if depth >= LIMITS['owned_json_depth']:
                    fail('SNAPSHOT_DEPTH', 'composite key exceeds depth64')
                for child in item:
                    self.creation(4)
                    pending.append((child, depth + 1))

    def append(self, target, value):
        self.creation()
        target.append(value)
        return value

    def symbol(self, prefix, index, suffix=''):
        if type(index) is not int or not 0 <= index <= 4294967295:
            fail('ABI', 'numeric identifier is outside uint32')
        self.reserve(creation=3, work=3 * (len(prefix) + len(suffix) + 12))
        return prefix + str(index) + suffix

    def ordered(self, values):
        # Header, sort storage and comparator wrapper records/memberships.
        self.reserve(creation=8 + 6 * len(values), work=len(values))
        def compare(left, right):
            self.reserve(creation=3, work=1)
            if type(left) is not type(right) or type(left) not in (str, bytes):
                fail('BINDING', 'sort domain must be uniform text or byte strings', schema=True)
            for index in range(min(len(left), len(right))):
                self.reserve(creation=2, work=1)
                a, b = left[index], right[index]
                if a != b:
                    return -1 if a < b else 1
            self.work()
            return (len(left) > len(right)) - (len(left) < len(right))
        return sorted(values, key=cmp_to_key(compare))

    def reserve_result(self):
        if self._reserved:
            raise RuntimeError('result reservation repeated')
        # Outer statistics tuple and 8 (header+2 members+outer membership)
        # pairs, plus RuntimeEmission header and its eleven retained fields.
        self.reserve(creation=1 + 8 * 4 + 12, work=20)
        self._reserved = True

    def finalize(self):
        if not self._reserved or self._frozen:
            raise RuntimeError('missing or repeated finalization')
        self._frozen = True
        return (('creation_units', self.creation_units), ('work_units', self.work_units),
                ('source_utf8_bytes', self.source_utf8_bytes),
                ('manifest_utf8_bytes', self.manifest_utf8_bytes),
                ('label_utf8_bytes', self.label_utf8_bytes), ('label_count', self.label_count),
                ('packet_public_calls', 1), ('extra_resource_public_calls', 1))


def exact(value, keys, budget, code='BINDING'):
    budget.work(1 + len(keys))
    if type(value) is not dict or len(value) != len(keys):
        fail(code, 'record does not have the exact fields', schema=True)
    for key in keys:
        budget.key_work(key)
        if key not in value:
            fail(code, 'required record field missing', schema=True)


def plain_index(value, count, code):
    if type(count) is not int or not 0 <= count <= 4294967295:
        fail(code, 'reference count is not a plain uint32', schema=True)
    if type(value) is not int or not 0 <= value < count:
        fail(code, 'reference is not a plain in-domain index', schema=True)
    return value


def text_equal(left, right, budget, code='BINDING'):
    if type(left) is not str or type(right) is not str:
        fail(code, 'expected exact text', schema=True)
    budget.work(1 + min(len(left), len(right)))
    if left != right:
        fail(code, 'fresh text differs')


def same(left, right, budget, code='BINDING'):
    """Depth-first exact comparison; at most64 open container frames."""
    budget.creation()
    stack = []
    a, other = left, right
    while True:
        budget.work()
        if type(a) is not type(other):
            fail(code, 'correspondence has a different plain type')
        if type(a) in (dict, list, tuple):
            if len(stack) >= LIMITS['owned_json_depth']:
                fail('SNAPSHOT_DEPTH', 'owned correspondence exceeds depth64')
            if len(a) != len(other):
                fail(code, 'correspondence length differs')
            keys = None
            if type(a) is dict:
                exact(a, other, budget, code)
                keys = budget.listing(other)
            if a:
                budget.creation(6)
                stack.append([a, other, keys, 0])
                key = keys[0] if keys is not None else 0
                budget.key_work(key)
                budget.key_work(key)  # both correspondence operands are read
                a, other = a[key], other[key]
                continue
        elif type(a) is str:
            text_equal(a, other, budget, code)
        elif a is None or type(a) in (int, bool):
            if a != other:
                fail(code, 'correspondence scalar differs')
        else:
            fail(code, 'non-plain correspondence value', schema=True)
        while stack:
            frame = stack[-1]
            frame[3] += 1
            budget.work()
            if frame[3] < len(frame[0]):
                key = frame[2][frame[3]] if frame[2] is not None else frame[3]
                budget.key_work(key)
                budget.key_work(key)  # both correspondence operands are read
                a, other = frame[0][key], frame[1][key]
                break
            stack.pop()
        else:
            return


def decode_fresh(text, budget):
    """Reserve the complete owned JSON tree before json.loads, never raw ingress."""
    if type(text) is not str:
        fail('BINDING', 'owned snapshot is not text', schema=True)
    budget.creation()
    stack = []
    quoted = escaped = scalar = False
    units = size = 0
    for char in text:
        budget.work()
        value = ord(char)
        if 0xD800 <= value <= 0xDFFF:
            fail('BINDING', 'invalid Unicode scalar in owned JSON', schema=True)
        size += 1 if value < 128 else 2 if value < 2048 else 3 if value < 65536 else 4
        if size > LIMITS['source_utf8_bytes']:
            fail('SOURCE_BYTES', 'owned snapshot exceeds32MiB')
        if quoted:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == '"': quoted = False
            continue
        if char in ' \t\n\r,:]}':
            scalar = False
        if char in ' \t\n\r':
            continue
        if char == ':':
            units += 1  # object membership
            continue
        if char == ',':
            if stack and stack[-1][0] == '[':
                stack[-1][1] = True
            continue
        if char in ']}':
            if not stack or stack[-1][0] != ('[' if char == ']' else '{'):
                fail('BINDING', 'malformed owned JSON', schema=True)
            stack.pop()
            continue
        if stack and stack[-1][0] == '[' and stack[-1][1]:
            units += 1
            stack[-1][1] = False
        if char == '"':
            units += 1
            quoted = True
        elif char in '[{':
            if len(stack) >= LIMITS['owned_json_depth']:
                fail('SNAPSHOT_DEPTH', 'owned JSON exceeds depth64')
            units += 1
            budget.creation(4)
            stack.append([char, char == '['])
        elif not scalar:
            units += 1
            scalar = True
    if quoted or stack:
        fail('BINDING', 'incomplete owned JSON', schema=True)
    budget.reserve(creation=units, work=2 * len(text) + units + 1)
    try:
        return json.loads(text)
    except (TypeError, ValueError, RecursionError):
        fail('BINDING', 'malformed owned JSON', schema=True)


class Writer:
    __slots__ = ('budget', 'kind', 'size', 'chunks', 'buffer', 'digest')

    def __new__(cls, budget, kind):
        if kind not in ('source', 'manifest', 'scratch'):
            raise ValueError('invalid writer domain')
        # Instance header+six slots+list/bytearray/hash headers, before allocation.
        budget.creation(10)
        return object.__new__(cls)

    def __init__(self, budget, kind):
        self.budget, self.kind, self.size = budget, kind, 0
        self.chunks, self.buffer, self.digest = [], bytearray(), hashlib.sha256()

    def emit(self, data):
        if type(data) is not bytes or len(data) > LIMITS['source_chunk_bytes']:
            fail('ABI', 'output token is not a bounded byte chunk', schema=True)
        if self.kind == 'manifest':
            used, limit, code = self.budget.manifest_utf8_bytes, LIMITS['manifest_utf8_bytes'], 'MANIFEST_BYTES'
        elif self.kind == 'source':
            used, limit, code = self.budget.source_utf8_bytes, LIMITS['source_utf8_bytes'], 'SOURCE_BYTES'
        else:
            used, limit, code = self.size, LIMITS['source_utf8_bytes'], 'SOURCE_BYTES'
        if len(data) > limit - used:
            fail(code, 'output byte allowance exhausted')
        self.budget.work(len(data))
        if len(self.buffer) + len(data) > LIMITS['source_chunk_bytes']:
            self.flush()
        if self.kind == 'manifest': self.budget.manifest_utf8_bytes += len(data)
        elif self.kind == 'source': self.budget.source_utf8_bytes += len(data)
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
        if type(text) is not str or len(text) > LIMITS['source_chunk_bytes']:
            fail('ABI', 'unbounded source template', schema=True)
        self.budget.reserve(creation=1, work=2 * len(text))
        for char in text:
            if ord(char) > 127:
                fail('ABI', 'non-ASCII source template', schema=True)
        self.emit(text.encode('ascii'))

    def number(self, value):
        if type(value) is not int or not -(1 << 63) <= value < (1 << 64):
            fail('ABI', 'integer outside bounded source domain', schema=True)
        self.budget.reserve(creation=2, work=42)
        self.emit(str(value).encode('ascii'))

    def finish(self):
        self.flush()
        self.budget.reserve(creation=7, work=2 * self.size + 64)
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
                fail('BINDING', 'invalid Unicode scalar', schema=True)
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

    def value(self, value):
        self.budget.creation()
        stack = []
        item = value
        while True:
            self.budget.work()
            if item is None: self.emit(b'null')
            elif type(item) is bool: self.emit(b'true' if item else b'false')
            elif type(item) is int: self.number(item)
            elif type(item) is str: self.string(item)
            elif type(item) in (list, tuple, dict):
                if len(stack) >= LIMITS['owned_json_depth']:
                    fail('SNAPSHOT_DEPTH', 'owned serialization exceeds depth64')
                keys = self.budget.ordered(item) if type(item) is dict else None
                self.emit(b'{' if keys is not None else b'[')
                if item:
                    self.budget.creation(5)
                    stack.append([item, keys, 0])
                    if keys is not None:
                        self.string(keys[0]); self.emit(b':')
                        self.budget.key_work(keys[0])
                        item = item[keys[0]]
                    else:
                        item = item[0]
                    continue
                self.emit(b'}' if keys is not None else b']')
            else:
                fail('BINDING', 'non-plain JSON value', schema=True)
            while stack:
                frame = stack[-1]
                frame[2] += 1
                self.budget.work()
                if frame[2] < len(frame[0]):
                    self.emit(b',')
                    if frame[1] is not None:
                        key = frame[1][frame[2]]
                        self.string(key); self.emit(b':')
                        self.budget.key_work(key)
                        item = frame[0][key]
                    else:
                        item = frame[0][frame[2]]
                    break
                self.emit(b'}' if frame[1] is not None else b']')
                stack.pop()
            else:
                return


def encode(value, budget, kind='scratch'):
    writer = Encoder(budget, kind)
    writer.value(value)
    return writer.finish()


def hash_text(text, budget, *, source=False):
    """Scan/reuse text with UTF-8 scratch of at most4096 bytes per conversion."""
    if type(text) is not str:
        fail('BINDING', 'hash input is not text', schema=True)
    budget.creation()
    digest = hashlib.sha256()
    size = 0
    for start in range(0, len(text), 1024):
        # A1024-scalar slice encodes to at most4096 bytes. Both buffers are
        # precharged; exact byte counts and the aggregate cap precede encoding.
        count = min(1024, len(text) - start)
        budget.reserve(creation=2, work=count)
        chunk = text[start:start + count]
        byte_count = 0
        for char in chunk:
            budget.work()
            value = ord(char)
            if 0xD800 <= value <= 0xDFFF:
                fail('BINDING', 'invalid Unicode scalar', schema=True)
            byte_count += 1 if value < 128 else 2 if value < 2048 else 3 if value < 65536 else 4
        if byte_count > LIMITS['source_utf8_bytes'] - size:
            fail('SOURCE_BYTES', 'text exceeds32MiB')
        if source and byte_count > LIMITS['source_utf8_bytes'] - budget.source_utf8_bytes:
            fail('SOURCE_BYTES', 'four-source aggregate exceeds32MiB')
        budget.work(2 * byte_count)  # UTF-8 conversion and hash examination
        digest.update(chunk.encode('utf-8'))
        size += byte_count
        if source: budget.source_utf8_bytes += byte_count
    budget.reserve(creation=4, work=64)
    return digest.hexdigest(), size
