"""Host-only metadata limits; no native sizeof or execution qualification.

Every helper reserves its owned records/members before construction. Flat byte
buffers have a header/member charge and the independent streaming byte ceiling;
bytes inside one immutable scalar byte string are not Python container members.
The final JSON object census is deliberately distinct from monotonic creation.
"""
from __future__ import annotations

from contextlib import contextmanager
from functools import cmp_to_key
import hashlib

TYPE_LIMIT = 4_096
TYPE_DEPTH = 32
ENVIRONMENT_LIMIT = 1_024
ROW_LIMIT = 65_536
RECORD_LIMIT = 262_144
CREATION_LIMIT = 2_097_152
WORK_LIMIT = 16_777_216
OUTPUT_BYTES = 33_554_432
CHUNK_BYTES = 4_096
NATIVE_BYTES = 4_194_304  # A pending ABI limit, never measured by this module.
LAYERS = ('metadata-schema', 'metadata-type', 'metadata-origin',
          'metadata-representation', 'metadata-closure', 'metadata-bounds',
          'metadata-subset')


class MetadataError(ValueError):
    """Immutable new-stage coordinates; lower-stage errors pass through intact."""
    __slots__ = ('_path', '_layer', '_code', '_message')

    def __init__(self, path, layer, code, message):
        if layer not in LAYERS:
            raise ValueError('invalid metadata error layer')
        ValueError.__init__(self, f'{path}: {layer}/{code}: {message}')
        object.__setattr__(self, '_path', path)
        object.__setattr__(self, '_layer', layer)
        object.__setattr__(self, '_code', code)
        object.__setattr__(self, '_message', message)

    path = property(lambda self: self._path)
    layer = property(lambda self: self._layer)
    code = property(lambda self: self._code)
    message = property(lambda self: self._message)

    def __setattr__(self, key, value):
        raise AttributeError('MetadataError is immutable')


def fail(path, layer, code, message):
    raise MetadataError(path, layer, code, message)


def _units(value):
    if type(value) is not int or value < 0:
        raise ValueError('budget charges must be nonnegative plain integers')


class Budget:
    __slots__ = ('creation_units', 'work_units', 'row_units', 'metadata_records',
                 'metadata_utf8_bytes', 'retained_records', '_verifying', '_finalized')

    def __init__(self):
        self.creation_units = self.work_units = self.row_units = 0
        self.metadata_records = self.metadata_utf8_bytes = self.retained_records = 0
        self._verifying = 0
        self._finalized = False

    def reserve(self, *, creation=0, work=0, rows=0, records=0):
        _units(creation)
        _units(work)
        _units(rows)
        _units(records)
        if self._finalized:
            raise RuntimeError('metadata accounting is finalized')
        effective_rows = 0 if self._verifying else rows
        effective_records = 0 if self._verifying else records
        # Reserve the complete batch before any counter or destination changes.
        if effective_rows > ROW_LIMIT - self.row_units:
            fail('metadata.access_transport_resolution_rows', 'metadata-bounds',
                 'ROW_COUNT', 'planned resolution/Access/transport row quota exhausted')
        if effective_records > RECORD_LIMIT - self.retained_records:
            fail('metadata.records', 'metadata-bounds', 'RECORD_COUNT',
                 'canonical output JSON object quota exhausted')
        if creation > CREATION_LIMIT - self.creation_units:
            fail('metadata.creation_units', 'metadata-bounds', 'CREATION_UNITS',
                 'metadata construction budget exhausted')
        if work > WORK_LIMIT - self.work_units:
            fail('metadata.work_units', 'metadata-bounds', 'WORK_UNITS',
                 'metadata examination budget exhausted')
        self.creation_units += creation
        self.work_units += work
        self.row_units += effective_rows
        self.retained_records += effective_records

    def creation(self, units=1):
        self.reserve(creation=units)

    charge = creation

    def work(self, units=1):
        self.reserve(work=units)

    examine = work

    def rows(self, units=1):
        self.reserve(rows=units)

    def records(self, units=1):
        self.reserve(records=units)

    def retain_json(self, value):
        """Reserve serialized object occurrences BEFORE canonical attachment.

        Provisional tables already pay construction/work budgets but are not yet
        canonical output. After this call the caller must not structurally mutate
        the retained subtree. The fixed counts.metadata_records integer may be
        filled after independent census because that does not alter tree shape.
        Shared host objects are counted at EVERY serialized occurrence. Expected
        verifier copies suppress output ownership only, never scan/copy/work.
        """
        remaining = RECORD_LIMIT if self._verifying else RECORD_LIMIT - self.retained_records
        count = _record_occurrences(value, self, remaining)
        self.reserve(records=count)
        return value

    def row(self, **fields):
        self.creation()
        return dict(fields)

    def append(self, target, value):
        self.creation()
        target.append(value)
        return value

    def record_append(self, target, **fields):
        self.creation(2)
        result = dict(fields)
        target.append(result)
        return result

    def put(self, target, key, value):
        self.work()
        if key not in target:
            self.creation()
        target[key] = value
        return value

    def add(self, target, value):
        self.work()
        if value not in target:
            self.creation()
            target.add(value)
        return value

    def listing(self, source):
        self.creation(1 + len(source))
        return list(source)

    def tuple(self, source):
        self.creation(1 + len(source))
        return tuple(source)

    def copied_dict(self, source):
        self.creation(1 + len(source))
        return dict(source)

    def copied_set(self, source):
        self.creation(1 + len(source))
        return set(source)

    def ordered(self, source, *, key=None, key_units=None):
        """Charged stable sort, including keys BEFORE their construction.

        A key function requires an explicit scalar reservation or a cost function
        over the existing input. The cost includes key container headers/members;
        scalar keys reused from input require zero. Cost functions must not build
        a key themselves. Their fixed read is part of each input examination.
        """
        if key is not None and key_units is None:
            raise ValueError('key construction requires explicit precharged key_units')
        decorated = []
        self.creation()
        for value in source:
            self.work()
            if key is None:
                order_key = value
            else:
                units = key_units(value) if callable(key_units) else key_units
                self.creation(units)
                order_key = key(value)
                if _key_cost(order_key, self) > units:
                    raise ValueError('sort key exceeded its pre-reserved container cost')
            self.creation(2)  # fixed decoration and its membership
            decorated.append((order_key, value))
        # Timsort temporary members and comparator wrapper per input are charged
        # before sorted() can allocate them. No expanded type tree is a key.
        self.creation(1 + 3 * len(decorated))
        decorated = sorted(decorated, key=cmp_to_key(
            lambda a, b: _compare(a[0], b[0], self)))
        self.creation(1 + len(decorated))
        return [entry[1] for entry in decorated]

    def clone(self, value):
        return clone_json(value, self)

    @contextmanager
    def verification(self):
        """Verifier copies pay host budgets, not a second emitted R/object quota."""
        self._verifying += 1
        try:
            yield
        finally:
            self._verifying -= 1

    def finalize(self, *, creation, work):
        """Precharge the fixed immutable report/result batch, then freeze.

        The caller must calculate the complete fixed report record/container/member
        and comparison/read batch before calling; constructing that batch afterward
        must do no variable lookup or unreserved traversal. Repeated report() is free.
        """
        if self._verifying:
            raise RuntimeError('cannot finalize inside verification')
        self.reserve(creation=creation, work=work)
        self._finalized = True


def _key_cost(value, budget):
    # This verifies a previously reserved key cost; it never postcharges key
    # allocation. Nested keys are finite scalar records, not expanded Type trees.
    budget.work()
    if type(value) in (tuple, list):
        cost = 1 + len(value)
        for child in value:
            budget.work()
            if type(child) in (tuple, list):
                cost += _key_cost(child, budget)
            elif child is not None and type(child) not in (str, int, bool):
                raise TypeError('metadata ordering requires scalar or flat tuple keys')
        return cost
    if value is None or type(value) in (str, int, bool):
        return 0
    raise TypeError('metadata ordering requires scalar or flat tuple keys')


def _compare(left, right, budget):
    """Lexicographic scalar/tuple comparator with charged examined components."""
    budget.work()
    if left is right:
        return 0
    if type(left) in (tuple, list) and type(right) in (tuple, list):
        for a, b in zip(left, right):
            comparison = _compare(a, b, budget)
            if comparison:
                return comparison
        budget.work()
        return (len(left) > len(right)) - (len(left) < len(right))
    if left is None or right is None:
        return -1 if left is None else 1
    if type(left) is str and type(right) is str:
        for a, b in zip(left, right):
            budget.work()
            if a != b:
                return -1 if a < b else 1
        budget.work()
        return (len(left) > len(right)) - (len(left) < len(right))
    if type(left) not in (int, bool) or type(right) not in (int, bool):
        raise TypeError('incomparable metadata sort keys')
    return (left > right) - (left < right)


def clone_json(value, budget):
    """Iteratively snapshot a bounded plain tree, charging every copied member.

    Repeated shared containers are copied by occurrence, as in JSON. Cycles and
    overdeep internal trees reject instead of expanding without a bound.
    """
    budget.creation(2)  # result-cell header/member
    result = [None]
    budget.creation(3)  # worklist, task, worklist membership
    pending = [(value, result, 0, 0)]
    while pending:
        current, parent, index, depth = pending.pop()
        budget.work()
        if depth > 64:
            fail('metadata.snapshot', 'metadata-schema', 'DEPTH', 'internal JSON tree exceeds depth 64')
        if current is None or type(current) in (bool, int, str):
            if type(current) is int and current.bit_length() > 64:
                fail('metadata.snapshot', 'metadata-schema', 'INTEGER', 'integer outside bounded encoding')
            if type(current) is str:
                for char in current:
                    budget.work()
                    if 0xD800 <= ord(char) <= 0xDFFF:
                        fail('metadata.snapshot', 'metadata-schema', 'UTF8', 'surrogate in JSON string')
            parent[index] = current
        elif type(current) in (list, tuple):
            budget.creation(1 + len(current))
            copied = [None] * len(current)
            parent[index] = copied
            for child_index in range(len(current) - 1, -1, -1):
                budget.creation(2)
                pending.append((current[child_index], copied, child_index, depth + 1))
        elif type(current) is dict:
            budget.creation(1 + len(current))
            copied = {}
            parent[index] = copied
            for name, child in current.items():
                budget.work()
                if type(name) is not str:
                    fail('metadata.snapshot', 'metadata-schema', 'KEY', 'JSON object key must be a plain string')
                copied[name] = None
                budget.creation(2)
                pending.append((child, copied, name, depth + 1))
        else:
            fail('metadata.snapshot', 'metadata-schema', 'JSON', 'expected a plain JSON tree')
    return result[0]


def _record_occurrences(value, budget, limit):
    budget.creation(2)
    pending = [value]
    count = 0
    while pending:
        current = pending.pop()
        budget.work()
        if type(current) is dict:
            if count >= limit:
                fail('metadata.records', 'metadata-bounds', 'RECORD_COUNT', 'canonical output JSON object quota exhausted')
            count += 1
            for child in current.values():
                budget.append(pending, child)
        elif type(current) in (list, tuple):
            for child in current:
                budget.append(pending, child)
        elif current is not None and type(current) not in (str, int, bool):
            fail('metadata.records', 'metadata-schema', 'JSON', 'object census requires plain JSON')
    return count


def census_records(value, budget):
    """Independent final occurrence census, not the output admission guard.

    Budget.retain_json must reserve each subtree before canonical attachment;
    orchestration checks this census equals budget.retained_records before return.
    Provisional allocation is creation/work bounded, never claimed RECORD_LIMIT
    bounded. Repeated shared objects count once per occurrence in either pass.
    """
    count = _record_occurrences(value, budget, RECORD_LIMIT)
    if not budget._verifying:
        budget.metadata_records = count
    return count


class CanonicalEncoder:
    """Nonrecursive UTF-8 stream; byte quota checked before buffering each chunk."""
    __slots__ = ('budget', 'limit', 'size', 'chunks', 'buffer', 'digest')

    def __init__(self, budget, limit=OUTPUT_BYTES):
        _units(limit)
        if limit > OUTPUT_BYTES:
            raise ValueError('encoder cannot raise the metadata byte ceiling')
        budget.creation(4)  # encoder, chunks, buffer, digest
        self.budget, self.limit, self.size = budget, limit, 0
        self.chunks, self.buffer = [], bytearray()
        self.digest = hashlib.sha256()

    def _flush(self):
        if self.buffer:
            self.budget.creation(2)  # immutable chunk plus retained membership
            chunk = bytes(self.buffer)
            self.chunks.append(chunk)
            self.digest.update(chunk)
            self.buffer.clear()

    def emit(self, data):
        if len(data) > CHUNK_BYTES:
            raise ValueError('serialization chunk exceeds 4096 bytes')
        if len(data) > self.limit - self.size:
            fail('metadata.bytes', 'metadata-bounds', 'OUTPUT_BYTES', 'canonical metadata exceeds 32 MiB')
        self.size += len(data)
        if len(self.buffer) + len(data) > CHUNK_BYTES:
            self._flush()
        self.buffer.extend(data)

    def string(self, value):
        self.emit(b'"')
        for char in value:
            self.budget.work()
            n = ord(char)
            if char == '"':
                self.emit(b'\\"')
            elif char == '\\':
                self.emit(b'\\\\')
            elif char == '\b':
                self.emit(b'\\b')
            elif char == '\f':
                self.emit(b'\\f')
            elif char == '\n':
                self.emit(b'\\n')
            elif char == '\r':
                self.emit(b'\\r')
            elif char == '\t':
                self.emit(b'\\t')
            elif n < 32:
                self.budget.creation(2)
                self.emit(('\\u%04x' % n).encode('ascii'))
            elif 0xD800 <= n <= 0xDFFF:
                fail('metadata.bytes', 'metadata-schema', 'UTF8', 'surrogate in canonical string')
            else:
                self.budget.creation()
                self.emit(char.encode('utf-8'))
        self.emit(b'"')

    def value(self, value):
        self.budget.creation(3)
        tasks = [('value', value)]
        while tasks:
            action, current = tasks.pop()
            self.budget.work()
            if action == 'literal':
                self.emit(current)
            elif action == 'string':
                self.string(current)
            elif current is None:
                self.emit(b'null')
            elif type(current) is bool:
                self.emit(b'true' if current else b'false')
            elif type(current) is int:
                if current.bit_length() > 64:
                    fail('metadata.bytes', 'metadata-schema', 'INTEGER', 'integer exceeds encoding domain')
                self.budget.creation(2)
                self.emit(str(current).encode('ascii'))
            elif type(current) is str:
                self.string(current)
            elif type(current) in (tuple, list):
                self.emit(b'[')
                self._task(tasks, 'literal', b']')
                for index in range(len(current) - 1, -1, -1):
                    self._task(tasks, 'value', current[index])
                    if index:
                        self._task(tasks, 'literal', b',')
            elif type(current) is dict:
                self.emit(b'{')
                names = self.budget.ordered(current)
                self._task(tasks, 'literal', b'}')
                for index in range(len(names) - 1, -1, -1):
                    name = names[index]
                    if type(name) is not str:
                        fail('metadata.bytes', 'metadata-schema', 'KEY', 'object keys must be strings')
                    self._task(tasks, 'value', current[name])
                    self._task(tasks, 'literal', b':')
                    self._task(tasks, 'string', name)
                    if index:
                        self._task(tasks, 'literal', b',')
            else:
                fail('metadata.bytes', 'metadata-schema', 'JSON', 'expected plain JSON')

    def _task(self, tasks, action, value):
        self.budget.creation(2)
        tasks.append((action, value))

    def finish(self):
        self._flush()
        self.budget.creation(3)  # joined bytes, decoded string, digest text
        text = b''.join(self.chunks).decode('utf-8')
        self.budget.metadata_utf8_bytes = self.size
        return text, self.digest.hexdigest(), self.size


def canonical_encode(value, budget, *, limit=OUTPUT_BYTES):
    encoder = CanonicalEncoder(budget, limit)
    encoder.value(value)
    return encoder.finish()


def decode_fresh(text, budget):
    """Precharged decode of THIS invocation's immutable lower-stage JSON only.

    Not a raw ingress parser or a checked-object admission API. The orchestrator
    must call the unchanged checker first and pass only its own canonical/derived
    strings. The lexical prepass ignores escaped punctuation inside strings,
    counts every prospective object/list header and object/list membership, and
    reserves the ENTIRE imported-tree construction before json.loads allocates it.
    Prepass worklist headers/members and each examined character are charged too.
    Imported object counts do not affect metadata_records, which is final-output
    JSON census only. The lower checker already owns duplicate/nonfinite/schema
    rejection; this helper cannot be used to replace that checking.
    """
    import json

    if type(text) is not str:
        fail('metadata.snapshot', 'metadata-schema', 'JSON', 'fresh serialized input must be a plain string')
    budget.creation()  # prepass stack header
    stack = []
    in_string = escaped = False
    creation = size = 0
    for char in text:
        budget.work()
        codepoint = ord(char)
        if 0xD800 <= codepoint <= 0xDFFF:
            fail('metadata.snapshot', 'metadata-schema', 'UTF8', 'surrogate in fresh JSON')
        size += 1 if codepoint < 0x80 else 2 if codepoint < 0x800 else 3 if codepoint < 0x10000 else 4
        if size > OUTPUT_BYTES:
            fail('metadata.snapshot', 'metadata-schema', 'INPUT_BYTES', 'fresh lower-stage snapshot exceeds 32 MiB')
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
            if not stack or stack[-1][0] != '{':
                fail('metadata.snapshot', 'metadata-schema', 'JSON', 'invalid fresh object separator')
            creation += 1  # dictionary field membership
            continue
        if char == ',':
            if not stack:
                fail('metadata.snapshot', 'metadata-schema', 'JSON', 'invalid fresh separator')
            if stack[-1][0] == '[':
                stack[-1][1] = True
            continue
        if char in ']}':
            expected = '[' if char == ']' else '{'
            if not stack or stack[-1][0] != expected:
                fail('metadata.snapshot', 'metadata-schema', 'JSON', 'fresh JSON delimiters disagree')
            stack.pop()
            continue
        # Every first lexical byte of an array element consumes its membership;
        # later bytes of a numeric/keyword token cannot count that element twice.
        if stack and stack[-1][0] == '[' and stack[-1][1]:
            creation += 1
            stack[-1][1] = False
        if char == '"':
            in_string = True
        elif char in '[{':
            if len(stack) >= 32:
                fail('metadata.snapshot', 'metadata-schema', 'DEPTH', 'fresh JSON nesting exceeds inherited depth 32')
            creation += 1  # prospective imported object/list header
            budget.creation(2)  # prepass frame plus worklist membership
            stack.append([char, char == '['])
    if in_string or stack:
        fail('metadata.snapshot', 'metadata-schema', 'JSON', 'incomplete fresh JSON')
    # No imported container allocation occurs before this atomic reservation.
    # Decoder budget: one syntax pass and at most one unescape/scalar pass
    # over each character, plus each container/member attachment and dispatch.
    # This is an explicit conservative charged model, not measured C CPU work.
    budget.reserve(creation=creation, work=2 * len(text) + creation + 1)
    try:
        return json.loads(text)
    except (TypeError, ValueError, RecursionError) as error:
        fail('metadata.snapshot', 'metadata-schema', 'JSON', 'fresh checker serialization is malformed')
