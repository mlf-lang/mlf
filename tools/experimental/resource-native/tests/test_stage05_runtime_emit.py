"""Finite Stage05 source-only host suite; this file is not an execution approval.

Run only under a separately reviewed supervisor: Python -B -S, unoptimized,
--evidence-root ABSOLUTE_NEW_PATH. No compiler, native callback, model, original
language evaluator or subprocess is invoked. Public calls produce C text only.
The supervisor owns process/time/memory/stream limits and the complete checkout
census. This child owns the finite 168-file, 240-MiB payload budget below.
"""
from __future__ import annotations

# Remove the script directory and all non-standard search entries before loading
# any other stdlib module. The one local package root is inserted after pinning.
import sys
import os
_BOOT_PATH = os.path.abspath(__file__)
_BOOT_PREFIX = os.path.realpath(sys.base_prefix)
sys.path[:] = [p for p in sys.path if p and
               os.path.commonpath((_BOOT_PREFIX, os.path.realpath(p))) == _BOOT_PREFIX]

import argparse
import base64
import ast
import dataclasses
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import time
import unittest
from contextlib import contextmanager

MIB = 1048576
OWNED_CAP = 240 * MIB
FILE_CAP = 168
SOURCE_CAP = 6 * MIB
RECEIPT_CAP = MIB
HOST_CAP = 7 * MIB
JOURNAL_CAP = MIB
INPUTS_CAP = MIB
READ_CAP = 2 * MIB
SOURCE_FIELDS = (
    ('packet_header', 'ir8_packet_generated.h'),
    ('packet_source', 'ir8_packet_generated.c'),
    ('runtime_header', 'ir8_runtime_generated.h'),
    ('runtime_source', 'ir8_runtime_generated.c'),
)
RESULT_FIELDS = ('format', 'canonical_ir_json', 'packet_manifest_json',
                 'metadata_json', 'runtime_header', 'runtime_source',
                 'packet_header', 'packet_source', 'manifest_json',
                 'manifest_sha256', 'statistics')
STAT_KEYS = ('creation_units', 'work_units', 'source_utf8_bytes',
             'manifest_utf8_bytes', 'label_utf8_bytes', 'label_count',
             'packet_public_calls', 'extra_resource_public_calls')
PACKAGE_FILES = (
    '__init__.py', 'body_checker.py', 'budgets.py', 'checker.py',
    'declaration_adapter.py', 'declarations.py', 'metadata.py',
    'metadata_budget.py', 'metadata_edges.py', 'metadata_representations.py',
    'metadata_types.py', 'ownership.py', 'packet.py', 'packet_budget.py',
    'packet_emit.py', 'packet_schema.py', 'program_schema.py', 'provenance.py',
    'runtime_emit.py', 'runtime_emit_body.py', 'runtime_emit_budget.py',
)
PRODUCTION_PINS = {
    'runtime_emit.py': (8606, '1a470b8a1962f0f98f2c6ba29bbe2c12eba22e0a98831e185065745dd1cf4fee'),
    'runtime_emit_body.py': (58938, 'a47424423c55984ca1b64f50d2152f4ea3f271c838b5ff77bc2bc8e9929d7df3'),
    'runtime_emit_budget.py': (20006, 'b214480e3daa9d49cdd1e5ab5e77fdfa1f12433ca692700ad59a98c753653867'),
}
ABI_SHA256 = 'c6e3a34ea54b7f7224f94ece8a24a821d74e32d60db0a0fb16933252a2623500'
EXPECTED_IDS = (tuple('P%02d' % i for i in range(1, 13)) +
                tuple('D%d' % i for i in range(1, 9)) +
                tuple('G%02d' % i for i in range(1, 6)) +
                tuple('L%02d' % i for i in range(1, 25)) +
                tuple('U%02d' % i for i in range(1, 4)) +
                tuple('A%02d' % i for i in range(1, 15)) +
                tuple('M%02d' % i for i in range(1, 45)) +
                tuple('B%02d' % i for i in range(1, 19)))


class CustodyError(RuntimeError):
    """No additional planned operation may start after this failure."""


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def text_pin(text):
    require(type(text) is str, 'artifact must be an exact string')
    data = text.encode('utf-8')
    return {'bytes': len(data), 'sha256': digest(data)}


def typed(value):
    """Preserve tuple/list, bool/int and null distinctions in evidence."""
    if value is None:
        return {'type': 'null', 'value': None}
    if type(value) in (str, int, bool):
        return {'type': type(value).__name__, 'value': value}
    if type(value) in (tuple, list):
        return {'type': type(value).__name__, 'value': [typed(x) for x in value]}
    if type(value) is dict:
        require(all(type(k) is str for k in value), 'typed dictionary keys')
        return {'type': 'dict', 'value': {k: typed(v) for k, v in value.items()}}
    raise AssertionError('unsupported evidence value type: ' + type(value).__name__)


def untyped(value):
    require(type(value) is dict and set(value) == {'type', 'value'}, 'exact typed-value wrapper')
    kind, payload = value['type'], value['value']
    if kind == 'null':
        require(payload is None, 'typed null payload')
        return None
    if kind in ('str', 'int', 'bool'):
        require(type(payload).__name__ == kind, 'typed scalar exact type')
        return payload
    if kind in ('tuple', 'list'):
        require(type(payload) is list, 'typed sequence payload')
        items = [untyped(item) for item in payload]
        return tuple(items) if kind == 'tuple' else items
    if kind == 'dict':
        require(type(payload) is dict and all(type(k) is str for k in payload), 'typed mapping payload')
        return {key: untyped(child) for key, child in payload.items()}
    raise AssertionError('unknown typed-value kind')


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def reconstruct_mutation(base, mutated, recipe):
    """Rebuild the private artifact from its retained predecessor, not claims."""
    before = {key: getattr(base, key) for key in RESULT_FIELDS}
    rebuilt = dict(before)
    image_names = tuple(key for key, _ in SOURCE_FIELDS) + ('manifest_json', 'manifest_sha256', 'statistics')
    def images(values):
        return [{'path': key, **text_pin(canonical_json(typed(values[key]))
                 if key == 'statistics' else values[key])} for key in image_names]
    for image_set in ('pre_images', 'post_images'):
        require(type(recipe[image_set]) is list, 'mutation image list')
        for pin in recipe[image_set]:
            require(type(pin) is dict and set(pin) == {'path', 'bytes', 'sha256'} and
                    type(pin['path']) is str and type(pin['bytes']) is int and pin['bytes'] >= 0 and
                    type(pin['sha256']) is str and re.fullmatch(r'[0-9a-f]{64}', pin['sha256']),
                    'exact typed mutation image pin')
    require(recipe['pre_images'] == images(before), 'mutant complete preimage pins')
    for splice in recipe['source_splices']:
        name = splice['artifact']
        require(name in dict(SOURCE_FIELDS), 'source splice may only edit a fixed source field')
        offset = splice['byte_offset']
        require(type(offset) is int and offset >= 0, 'plain byte offset')
        old = base64.b64decode(splice['remove_bytes_base64'], validate=True)
        new = base64.b64decode(splice['insert_bytes_base64'], validate=True)
        data = rebuilt[name].encode('utf-8')
        require(old and data.count(old) == 1 and data[offset:offset + len(old)] == old,
                'independently unique exact predecessor source selector')
        changed = data[:offset] + new + data[offset + len(old):]
        require(len(changed) <= SOURCE_CAP, 'private reconstructed source custody cap')
        rebuilt[name] = changed.decode('utf-8')
    objects = {'manifest_json': json.loads(before['manifest_json']),
               'manifest_sha256': before['manifest_sha256'], 'statistics': before['statistics']}
    for patch in recipe['typed_json_patches']:
        name = patch['artifact']
        require(name in objects and patch['operation'] == 'replace' and
                patch['serialization'] == 'canonical-json-utf8', 'reviewed typed replacement operation')
        pointer = patch['json_pointer']
        require(type(pointer) is str and (pointer == '' or pointer.startswith('/')), 'JSON pointer domain')
        segments = [part.replace('~1', '/').replace('~0', '~') for part in pointer.split('/')[1:]] if pointer else []
        owner = None
        key = None
        selected = objects[name]
        for segment in segments:
            owner = selected
            if type(owner) is list:
                require(re.fullmatch(r'0|[1-9][0-9]*', segment) is not None, 'canonical list pointer index')
                key = int(segment)
                require(key < len(owner), 'list pointer index in range')
            else:
                require(type(owner) is dict and segment in owner, 'existing dictionary pointer member')
                key = segment
            selected = owner[key]
        predecessor = untyped(patch['old_typed_value'])
        require(typed(selected) == typed(predecessor), 'exact typed patch predecessor')
        replacement = untyped(patch['new_typed_value'])
        if owner is None:
            objects[name] = replacement
        else:
            owner[key] = replacement
    rebuilt['manifest_json'] = canonical_json(objects['manifest_json'])
    rebuilt['manifest_sha256'] = objects['manifest_sha256']
    rebuilt['statistics'] = objects['statistics']
    require(images(rebuilt) == recipe['post_images'], 'independently reconstructed complete postimage pins')
    for key in RESULT_FIELDS:
        require(typed(rebuilt[key]) == typed(getattr(mutated, key)),
                'reconstructed mutant differs from supplied actual artifact: ' + key)
    require(digest(rebuilt['manifest_json'].encode('utf-8')) == rebuilt['manifest_sha256'], 'reconstructed manifest hash')
    manifest = objects['manifest_json']
    require(manifest['outputs'] == {key: text_pin(rebuilt[key]) for key, _ in SOURCE_FIELDS},
            'refreshed actual output hashes are part of reconstructible typed patches')
    return {'source_splices_checked': len(recipe['source_splices']),
            'typed_patches_checked': len(recipe['typed_json_patches']),
            'all_pre_post_images_checked': True, 'all_actual_fields_reconstructed': True}


def diagnostic(error):
    if all(hasattr(error, k) for k in ('path', 'layer', 'code')):
        return {k: getattr(error, k) for k in ('path', 'layer', 'code')}
    return {'kind': type(error).__name__}


def error_record(error):
    return {'type': type(error).__name__, 'diagnostic': diagnostic(error),
            'message': str(error)[:8192]}


def _json_bytes(value, limit):
    """Count exact ensure_ascii JSON bytes before allocating encoded output."""
    size = 1  # final newline
    pending = [(value, 0)]
    nodes = 0
    def string_size(text):
        amount = 2
        for char in text:
            code = ord(char)
            amount += (2 if char in '\\"\b\f\n\r\t' else
                       6 if code < 32 or 126 < code <= 65535 else
                       12 if code > 65535 else 1)
            if amount > limit:
                raise CustodyError('JSON string exceeds evidence cap')
        return amount
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > 1000000 or depth > 128:
            raise CustodyError('evidence structure exceeds finite serializer census')
        if type(item) is dict:
            require(all(type(k) is str for k in item), 'evidence dictionary key')
            size += 2 + max(0, len(item) - 1) + len(item)
            for key, child in item.items():
                size += string_size(key)
                pending.append((child, depth + 1))
        elif type(item) is list:
            size += 2 + max(0, len(item) - 1)
            pending.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            size += string_size(item)
        elif item is None:
            size += 4
        elif type(item) is bool:
            size += 4 if item else 5
        elif type(item) is int:
            require(item.bit_length() <= 256, 'bounded evidence integer')
            size += len(str(item))
        else:
            raise CustodyError('non-JSON evidence type ' + type(item).__name__)
        if size > limit:
            raise CustodyError('serialized evidence exceeds byte cap')
    data = (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       ensure_ascii=True, allow_nan=False) + '\n').encode('ascii')
    require(len(data) == size, 'JSON reservation differs from serialization')
    return data


def no_symlinks(path, *, absent_leaf=False):
    path = Path(path)
    require(path.is_absolute(), 'path must be absolute')
    require('..' not in path.parts, 'parent path traversal is forbidden')
    current = Path(path.anchor)
    for index, part in enumerate(path.parts[1:]):
        current /= part
        leaf = index == len(path.parts) - 2
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if leaf and absent_leaf:
                return
            raise CustodyError('missing path component: ' + str(current))
        if stat.S_ISLNK(info.st_mode):
            raise CustodyError('symlink component: ' + str(current))
        if not leaf and not stat.S_ISDIR(info.st_mode):
            raise CustodyError('non-directory path component')
        if leaf and absent_leaf:
            raise CustodyError('evidence root already exists')


def read_stable(path, limit):
    no_symlinks(path)
    named_before = os.lstat(path)
    if not stat.S_ISREG(named_before.st_mode) or named_before.st_nlink != 1 or named_before.st_size > limit:
        raise CustodyError('input preflight is not one bounded regular file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if (before.st_dev, before.st_ino) != (named_before.st_dev, named_before.st_ino):
            raise CustodyError('input pathname changed before open')
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > limit:
            raise CustodyError('input is not one bounded regular file: ' + str(path))
        chunks = []
        remaining = before.st_size
        while remaining:
            block = os.read(fd, min(65536, remaining))
            if not block:
                raise CustodyError('short input read')
            chunks.append(block)
            remaining -= len(block)
        if os.read(fd, 1):
            raise CustodyError('input grew during read')
        after = os.fstat(fd)
        named = os.lstat(path)
        signature = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_nlink,
                               s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if signature(before) != signature(after) or signature(after) != signature(named):
            raise CustodyError('input changed during read')
        return b''.join(chunks)
    finally:
        os.close(fd)


class Evidence:
    def __init__(self, root):
        self.root = root
        self.reserved_bytes = 0
        self.reserved_files = 0
        self.pins = {}
        self.sequence = 0
        self.operations = []
        self.journal_bytes = 0
        self.journal_digest = hashlib.sha256()
        self.broken = False
        self.journal = None
        self.reserve(0, 1)
        fd = os.open(root / 'ATTEMPTS.jsonl', os.O_WRONLY | os.O_CREAT |
                     os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        self.journal = os.fdopen(fd, 'wb', buffering=0)
        fsync_directory(root)

    def reserve(self, size, files=0):
        if type(size) is not int or size < 0 or type(files) is not int or files < 0:
            raise CustodyError('invalid custody reservation')
        if size > OWNED_CAP - self.reserved_bytes or files > FILE_CAP - self.reserved_files:
            raise CustodyError('owned evidence reservation exhausted')
        self.reserved_bytes += size
        self.reserved_files += files

    def event(self, test_id, operation_id, kind, event, details):
        if self.broken:
            raise CustodyError('journal is already uncertain; no retry')
        row = {'format': 'ir8-stage05-host-attempt/1', 'sequence': self.sequence,
               'test_id': test_id, 'operation_id': operation_id,
               'operation_kind': kind, 'event': event,
               'monotonic_ns': time.monotonic_ns(), 'details': details}
        data = _json_bytes(row, JOURNAL_CAP - self.journal_bytes)
        self.reserve(len(data))
        expected_digest = self.journal_digest.copy()
        expected_digest.update(data)
        try:
            require(self.journal.write(data) == len(data), 'short journal write')
            self.journal.flush()
            os.fsync(self.journal.fileno())
            # Reopen bounded readback also verifies pathname identity and size.
            actual = read_stable(self.root / 'ATTEMPTS.jsonl', JOURNAL_CAP)
            require(len(actual) == self.journal_bytes + len(data), 'journal length mismatch')
            require(actual[self.journal_bytes:] == data, 'journal append readback mismatch')
            require(digest(actual) == expected_digest.hexdigest(), 'earlier journal prefix changed')
        except BaseException:
            self.broken = True
            raise
        self.journal_bytes += len(data)
        self.journal_digest = expected_digest
        self.sequence += 1

    def operation(self, test_id, kind, name, recipe, thunk, summarize=None):
        op = {'id': len(self.operations), 'test_id': test_id, 'kind': kind,
              'callable': name, 'recipe': recipe, 'state': 'intent-pending',
              'returned': None, 'error': None, 'persistence': 'not-started'}
        self.operations.append(op)
        self.event(test_id, op['id'], kind, 'attempt-intended',
                   {'callable': name, 'recipe': recipe})
        op['state'] = 'known-started'
        try:
            value = thunk()
        except BaseException as error:
            # Actual outcome is assigned before error formatting or I/O.
            op['state'] = 'known-raised'
            op['returned'] = False
            op['_exception'] = error
            op['error'] = error_record(error)
            self.event(test_id, op['id'], kind, 'action-returned',
                       {'outcome': 'raised', 'error': op['error']})
            raise
        op['state'] = 'known-returned'
        op['returned'] = True
        op['_value'] = value
        # Summary can itself fail, but cannot erase the known return above.
        op['summary'] = summarize(value) if summarize else {'returned_type': type(value).__name__}
        self.event(test_id, op['id'], kind, 'action-returned',
                   {'outcome': 'returned', 'summary': op['summary']})
        return value, op

    def write(self, relative, data, cap, test_id, operation_id=None):
        if type(data) is not bytes or len(data) > cap:
            raise CustodyError('file payload exceeds cap')
        require(relative not in self.pins, 'file may only be created once')
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
                'relative evidence path required')
        self.reserve(len(data), 1)
        pin = {'path': relative, 'bytes': len(data), 'sha256': digest(data)}
        self.event(test_id, operation_id, 'artifact-persistence', 'save-intended', pin)
        path = self.root / relative
        no_symlinks(path, absent_leaf=True)
        state = {'pin': pin, 'state': 'creation-pending'}
        self.pins[relative] = state
        stream = None
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            state['state'] = 'created-outcome-uncertain'
            stream = os.fdopen(fd, 'wb', buffering=0)
            require(stream.write(data) == len(data), 'short evidence write')
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            stream = None
            fsync_directory(path.parent)
            require(read_stable(path, cap) == data, 'evidence readback mismatch')
            state['state'] = 'readback-complete'
            self.event(test_id, operation_id, 'artifact-persistence', 'saved', pin)
            state['state'] = 'durably-journaled'
        except BaseException as error:
            state['error'] = error_record(error)
            if stream is not None:
                try:
                    stream.close()
                except BaseException as close_error:
                    state['close_error'] = error_record(close_error)
            raise
        return pin

    def close(self):
        if self.journal is not None:
            stream, self.journal = self.journal, None
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()


@contextmanager
def patched(owner, name, replacement):
    original = getattr(owner, name)
    setattr(owner, name, replacement)
    try:
        yield original
    finally:
        setattr(owner, name, original)


class HostState:
    def __init__(self, root, package, data, pins, source_bytes):
        self.root, self.package, self.data = root, package, data
        self.input_pins, self.source_bytes = pins, source_bytes
        self.evidence = Evidence(root)
        self.inventory = data['inventory']['tests']
        self.test_rows = []
        self.emissions = []
        self.primary = {}
        self.raws = {}
        self.current_id = None
        self.module_origins = []
        self.runtime_pins = []
        self.runtime_metadata = None
        self.lower_prerequisites = 0
        self.oracle_successes = self.oracle_mutants = 0
        self.target_attempts = self.target_returns = self.target_rejections = 0
        # No cached local bytecode may be a second, unpinned code authority.
        require(not (package / 'resource_ir_v8/__pycache__').exists() and
                not (package / 'tests/__pycache__').exists(), 'local bytecode cache forbidden')
        self.runtime = importlib.import_module('resource_ir_v8.runtime_emit')
        self.budget = importlib.import_module('resource_ir_v8.runtime_emit_budget')
        self.body = importlib.import_module('resource_ir_v8.runtime_emit_body')
        self.schema = importlib.import_module('resource_ir_v8.program_schema')
        self.checker = importlib.import_module('resource_ir_v8.checker')
        self.metadata = importlib.import_module('resource_ir_v8.metadata')
        self.packet = importlib.import_module('resource_ir_v8.packet')
        name = 'stage05_runtime_oracle'
        spec = importlib.util.spec_from_file_location(name, package / 'tests' / (name + '.py'))
        require(spec is not None and spec.loader is not None, 'oracle source loader absent')
        self.oracle = importlib.util.module_from_spec(spec)
        sys.modules[name] = self.oracle
        spec.loader.exec_module(self.oracle)
        self.verify_origins()
        self.load_cases()
        self.capture_runtime_inputs()
        self.recheck_inputs()
        inputs = {'format': 'ir8-stage05-host-inputs/1',
                  'scope': 'exact consumed subset; not complete checkout custody',
                  'files': self.input_pins, 'local_module_origins': self.module_origins,
                  'raw_selections': self.data['cases'],
                  'runtime': self.runtime_metadata,
                  'planned_ids': list(EXPECTED_IDS),
                  'counts': {'tests': 128, 'target_attempts': 67, 'emissions': 33,
                             'expected_rejections': 34, 'owned_files': 168}}
        self.evidence.write('INPUTS.json', _json_bytes(inputs, INPUTS_CAP), INPUTS_CAP, None)
        os.mkdir(root / 'emissions', 0o700)
        fsync_directory(root)

    def verify_origins(self):
        expected = {'resource_ir_v8' + ('' if f == '__init__.py' else '.' + f[:-3]):
                    self.package / 'resource_ir_v8' / f for f in PACKAGE_FILES}
        expected['stage05_runtime_oracle'] = self.package / 'tests/stage05_runtime_oracle.py'
        observed = []
        for name, module in tuple(sys.modules.items()):
            file = getattr(module, '__file__', None)
            if not file:
                continue
            path = Path(os.path.abspath(file))
            if name in expected:
                require(path == expected[name], 'unexpected local module origin ' + name)
                no_symlinks(path)
                require(getattr(module.__spec__, 'origin', None) == str(path), 'module spec origin')
                observed.append({'name': name, 'path': str(path.relative_to(self.package))})
            elif path.is_relative_to(self.package.parents[2]):
                require(path == Path(_BOOT_PATH) and name == '__main__', 'unallowlisted project import ' + name)
            elif not path.is_relative_to(Path(_BOOT_PREFIX)):
                raise CustodyError('nonstandard import origin: ' + name)
        require(all(name in sys.modules for name in expected), 'missing reviewed package module')
        self.module_origins = sorted(observed, key=lambda x: x['name'])

    def capture_runtime_inputs(self):
        module_rows, paths = [], set()
        for name, module in sorted(sys.modules.items()):
            file = getattr(module, '__file__', None)
            cached = getattr(module, '__cached__', None)
            origin = getattr(getattr(module, '__spec__', None), 'origin', None)
            row = {'name': name, 'spec_origin': origin, 'declared_file': file,
                   'declared_cached_file': cached, 'cached_file_present': False}
            if file:
                paths.add(os.path.abspath(file))
            if cached and Path(cached).exists():
                require(not Path(cached).is_relative_to(self.package), 'local cached bytecode forbidden')
                paths.add(os.path.abspath(cached))
                row['cached_file_present'] = True
            module_rows.append(row)
        require(len(module_rows) <= 512 and len(paths) <= 1024, 'bounded imported runtime file census')
        executable = os.path.realpath(sys.executable)
        paths.add(executable)
        for name in sorted(paths):
            data = read_stable(Path(name), 64 * MIB)
            self.runtime_pins.append({'path': name, 'bytes': len(data), 'sha256': digest(data)})
        self.runtime_metadata = {
            'executable': sys.executable, 'resolved_executable': executable,
            'version': sys.version, 'cache_tag': sys.implementation.cache_tag,
            'base_prefix': sys.base_prefix, 'prefix': sys.prefix,
            'exec_prefix': sys.exec_prefix, 'base_exec_prefix': sys.base_exec_prefix,
            'actual_sys_path': list(sys.path),
            'flags': {'dont_write_bytecode': sys.dont_write_bytecode,
                      'no_site': sys.flags.no_site, 'optimize': sys.flags.optimize},
            'imported_modules': module_rows, 'imported_module_file_pins': self.runtime_pins,
            'scope': 'declared module files/cache files present plus interpreter; '
                     'frozen implementation and loader/shared-library custody belong to supervisor',
        }

    def load_cases(self):
        fixture = json.loads(self.source_bytes[self.data['source_fixture_file']['path']])
        for case in self.data['cases']:
            if case['storage'] == 'embedded-exact-raw-text':
                raw = case['text']
            else:
                require(case['storage'] == 'repository-json-extraction', 'unknown case storage')
                require(case['source_file'] == self.data['source_fixture_file']['path'], 'fixture origin')
                item = fixture
                for segment in case['source_json_pointer'].split('/')[1:]:
                    segment = segment.replace('~1', '/').replace('~0', '~')
                    item = item[int(segment)] if type(item) is list else item[segment]
                raw = item
            pin = text_pin(raw)
            require(pin == {'bytes': case['raw_utf8_bytes'], 'sha256': case['raw_sha256']}, 'raw pin ' + case['id'])
            require(case['id'] not in self.raws, 'duplicate raw case')
            self.raws[case['id']] = raw

    def observer(self, kind, callable_name, input_recipe, thunk):
        require(kind == 'oracle-lower-api', 'unexpected oracle operation kind')
        return self.evidence.operation(self.current_id, kind, callable_name, input_recipe, thunk)[0]

    def verify(self, raw_text, emission, *, mutant=False):
        before = len(self.evidence.operations)
        try:
            report, _ = self.evidence.operation(
                self.current_id, 'oracle-verification', 'stage05_runtime_oracle.verify',
                {'raw': text_pin(raw_text), 'mutant': mutant},
                lambda: self.oracle.verify(raw_text, emission, observer=self.observer))
        except BaseException as error:
            calls = [x for x in self.evidence.operations[before:] if x['kind'] == 'oracle-lower-api']
            # Preserve the actual first lower/custody exception and partial
            # topology. No padding calls and no assertion in a finally block.
            complete = len(calls) == 3 and all(x['returned'] is True for x in calls)
            self.test_rows[-1]['observations'].append({
                'oracle_first_error': error_record(error),
                'fresh_lower_operation_ids': [x['id'] for x in calls],
                'fresh_lower_calls_complete': complete})
            if isinstance(error, self.oracle.OracleError) and complete:
                require([x['callable'].rsplit('.', 1)[-1] for x in calls] ==
                        ['check_resources', 'check_metadata', 'emit_packet'], 'oracle public call topology')
            raise
        calls = [x for x in self.evidence.operations[before:] if x['kind'] == 'oracle-lower-api']
        require(len(calls) == 3 and all(x['returned'] is True for x in calls),
                'successful oracle verification requires three fresh public authorities')
        require([x['callable'].rsplit('.', 1)[-1] for x in calls] ==
                ['check_resources', 'check_metadata', 'emit_packet'], 'oracle public call topology')
        if not mutant:
            self.oracle_successes += 1
        return report

    def emission_summary(self, emission):
        return {'result_type': type(emission).__name__,
                'outputs': {key: text_pin(getattr(emission, key)) for key, _ in SOURCE_FIELDS},
                'manifest': text_pin(emission.manifest_json),
                'manifest_sha256': emission.manifest_sha256}

    def target(self, raw_text, *, api='emit_runtime', argument=None, kwargs=None,
               expected=None, recipe=None):
        if argument is None:
            argument = raw_text if api == 'loads_runtime' else json.loads(raw_text)
        recipe = recipe or {'kind': 'exact-case-raw', 'raw': text_pin(raw_text), 'api': api}
        kwargs = {} if kwargs is None else kwargs
        call = getattr(self.runtime, api)
        before = len(self.evidence.operations)
        try:
            emission, op = self.evidence.operation(
                self.current_id, 'target-api', 'resource_ir_v8.runtime_emit.' + api,
                recipe, lambda: call(argument, **kwargs), self.emission_summary)
        except BaseException as error:
            matching = [x for x in self.evidence.operations[before:] if x['kind'] == 'target-api']
            if matching and matching[0]['state'] != 'intent-pending':
                self.target_attempts += 1
            if matching and matching[0]['state'] == 'known-raised':
                self.target_rejections += 1
            if isinstance(error, CustodyError) or self.evidence.broken:
                raise
            if expected is None:
                raise
            if expected.get('kind') == 'TypeError':
                require(type(error) is TypeError, 'exact public signature TypeError required')
            else:
                require(diagnostic(error) == expected,
                        'expected diagnostic %r, observed %r' % (expected, diagnostic(error)))
            self.test_rows[-1]['observations'].append({'expected': expected, 'actual': diagnostic(error), 'recipe': recipe})
            return None
        self.target_attempts += 1
        self.target_returns += 1
        row = self.retain(raw_text, emission, op)
        require(expected is None, 'expected rejection returned a retained emission instead')
        return emission, row

    def retain(self, raw_text, emission, op):
        ordinal = len(self.emissions) + 1
        require(ordinal <= 33, 'unexpected extra successful emission')
        eid = '%03d' % ordinal
        planned = self.data['evidence_schema']['success_emission_sets'][ordinal - 1]
        planned_match = planned['emission_id'] == eid and planned['test_id'] == self.current_id
        relative_dir = 'emissions/' + eid
        os.mkdir(self.root / relative_dir, 0o700)
        fsync_directory(self.root / 'emissions')
        row = {'emission_id': eid, 'test_id': self.current_id, 'target_call_id': op['id'],
               'files': [], 'oracle': 'not-started', 'persistence': 'started',
               'matches_planned_ordinal': planned_match}
        self.emissions.append(row)
        op['persistence'] = 'started'
        aggregate = sum(text_pin(getattr(emission, field))['bytes'] for field, _ in SOURCE_FIELDS)
        require(aggregate <= SOURCE_CAP, 'four-source custody cap exceeded')
        for field, filename in SOURCE_FIELDS:
            data = getattr(emission, field).encode('utf-8')
            row['files'].append(self.evidence.write(relative_dir + '/' + filename, data,
                                                   SOURCE_CAP, self.current_id, op['id']))
        require(planned_match, 'unexpected emission sources retained; planned successful order differs')
        report = self.verify(raw_text, emission)
        row['oracle'] = 'verified'
        required = ('resource_derived_json', 'metadata_json', 'packet_manifest_json',
                    'bindings', 'lower_reports_typed', 'independent_expected',
                    'independent_source_census', 'lower_byte_equivalence_associations')
        require(all(k in report for k in required), 'oracle report receipt fields missing')
        require(report['metadata_json'] == emission.metadata_json and
                report['packet_manifest_json'] == emission.packet_manifest_json,
                'receipt authorities differ from actual output')
        receipt = {'format': 'ir8-stage05-host-emission/1', 'emission_id': eid,
                   'test_id': self.current_id, 'target_call_id': op['id'],
                   'input_raw_text': raw_text, 'canonical_ir_json': emission.canonical_ir_json,
                   'runtime_manifest_json': emission.manifest_json,
                   'runtime_manifest_sha256': emission.manifest_sha256,
                   'final_statistics_typed': typed(emission.statistics),
                   'source_files': list(row['files'])}
        receipt.update({key: report[key] for key in required})
        require(set(receipt) == set(self.data['evidence_schema']['receipt_fields']), 'exact receipt schema')
        pin = self.evidence.write(relative_dir + '/receipt.json', _json_bytes(receipt, RECEIPT_CAP),
                                  RECEIPT_CAP, self.current_id, op['id'])
        row['files'].append(pin)
        row['persistence'] = op['persistence'] = 'complete'
        self.test_rows[-1]['emission_ids'].append(eid)
        if self.current_id in self.raws:
            self.primary[self.current_id] = (emission, row, report)
        return row

    def run_case(self, spec):
        self.current_id = spec['id']
        row = {'test_id': spec['id'], 'declared': spec, 'status': 'started',
               'observations': [], 'emission_ids': []}
        self.test_rows.append(row)
        before = (self.target_attempts, self.target_returns)
        try:
            group = spec['group']
            if group == 'formal-positive':
                self.target(self.raws[spec['input']])
            elif group == 'lower-rejection':
                self.target(self.raws[spec['input']], api='loads_runtime', expected=spec['diagnostic'])
            elif group == 'separate-naming-control':
                self.target(self.raws[spec['input']], api='loads_runtime', expected=spec['diagnostic'])
            elif group == 'api-custody':
                self.api_case(spec)
            elif group == 'private-independent-oracle-mutation':
                self.mutant_case(spec)
            elif group == 'private-budget-or-source-accounting':
                result, _ = self.evidence.operation(spec['id'], 'private-budget-control',
                    spec['name'], {'synthetic': True, 'inventory': spec}, lambda: self.budget_case(spec))
                row['observations'].append(result)
            else:
                raise AssertionError('unknown finite test group')
            require(self.target_attempts - before[0] == spec['public_attempts'], 'per-test target attempt count')
            require(self.target_returns - before[1] == spec['successful_emissions'], 'per-test successful return count')
        except BaseException as error:
            row['status'] = 'failed'
            row['error'] = error_record(error)
            raise
        row['status'] = 'passed'

    def api_case(self, spec):
        cid = spec['id']
        observations = self.test_rows[-1]['observations']
        if cid == 'A01':
            first, _ = self.target(self.raws['P05'], api='loads_runtime')
            second, _ = self.target(self.raws['P05'])
            for field in ('canonical_ir_json',) + tuple(k for k, _ in SOURCE_FIELDS):
                require(getattr(first, field) == getattr(second, field), 'loads/emit byte equality ' + field)
        elif cid == 'A02':
            def reverse(value):
                if type(value) is dict:
                    return {key: reverse(value[key]) for key in reversed(value)}
                if type(value) is list:
                    return [reverse(x) for x in value]
                return value
            raw = json.loads(self.raws['D7'])
            reversed_raw = reverse(raw)
            first, _ = self.target(self.raws['D7'], argument=raw)
            alternate = json.dumps(reversed_raw, ensure_ascii=False, separators=(',', ':'))
            second, _ = self.target(alternate, argument=reversed_raw,
                recipe={'kind': 'recursive-dict-insertion-order-reversal', 'base_case': 'D7',
                        'arrays_and_scalars_unchanged': True, 'actual_input_raw_text': alternate})
            for field in ('canonical_ir_json',) + tuple(k for k, _ in SOURCE_FIELDS):
                require(getattr(first, field) == getattr(second, field), 'dict-order byte equality ' + field)
        elif cid == 'A03':
            value = self.primary['P05'][0]
            require(tuple(f.name for f in dataclasses.fields(value)) == RESULT_FIELDS, 'exact result fields')
            require(type(value) is self.runtime.RuntimeEmission, 'exact public result type')
            require(not hasattr(value, '__dict__'), 'result has mutable instance dictionary')
            for field in RESULT_FIELDS:
                old = getattr(value, field)
                try:
                    setattr(value, field, old)
                except AttributeError:
                    pass
                else:
                    raise AssertionError('mutable result field ' + field)
            require(type(value.statistics) is tuple, 'statistics not tuple')
            for pair in value.statistics:
                require(type(pair) is tuple and len(pair) == 2 and type(pair[0]) is str and
                        type(pair[1]) is int, 'statistics pair types')
                try:
                    pair[1] = 0
                except TypeError:
                    pass
                else:
                    raise AssertionError('mutable statistics pair')
            for field in RESULT_FIELDS[:-1]:
                require(type(getattr(value, field)) is str, 'mutable nonstatistics result field')
            require(repr(value) == 'RuntimeEmission(emitted-uncompiled-runtime-source, '
                    'manifest_sha256=%r)' % value.manifest_sha256, 'exact source-only repr')
            observations.append({'fields': list(RESULT_FIELDS), 'nested_statistics_immutable': True})
        elif cid == 'A04':
            raw = json.loads(self.raws['P02'])
            require(type(raw['entry'][1]['value']) is int and raw['entry'][1]['value'] == 42,
                    'A04 exact mutation selector')
            first, _ = self.target(self.raws['P02'], argument=raw)
            frozen = tuple(getattr(first, field) for field in RESULT_FIELDS)
            raw['entry'][1]['value'] = True
            alternate = json.dumps(raw, ensure_ascii=False, separators=(',', ':'))
            self.target(alternate, argument=raw, expected=spec['diagnostic'],
                recipe={'kind': 'same-object-reuse', 'base_case': 'P02',
                        'json_pointer': '/entry/1/value', 'old_typed_value': typed(42),
                        'new_typed_value': typed(True), 'actual_input_raw_text': alternate})
            require(tuple(getattr(first, field) for field in RESULT_FIELDS) == frozen,
                    'prior immutable result changed after caller mutation')
        elif cid == 'A05':
            original_budget = self.runtime.Budget
            histories = []
            topology = []
            original_packet = self.runtime.emit_packet
            original_resource = self.runtime.check_resources
            class RecordingBudget(original_budget):
                def __init__(inner):
                    super().__init__()
                    inner.history = {'ordinal': len(histories), 'reserve_calls': 0,
                                     'first': None, 'last': None, 'monotonic': True}
                    histories.append((inner, inner.history))
                def reserve(inner, *, creation=0, work=0):
                    before = (inner.creation_units, inner.work_units)
                    result = super().reserve(creation=creation, work=work)
                    after = (inner.creation_units, inner.work_units)
                    require(after == (before[0] + creation, before[1] + work),
                            'Budget reserve must delegate exact monotonic increments')
                    h = inner.history
                    h['reserve_calls'] += 1
                    row = {'before': list(before), 'creation': creation, 'work': work, 'after': list(after)}
                    if h['first'] is None:
                        h['first'] = row
                    h['last'] = row
                    return result
            def packet(raw):
                topology.append({'call': 'emit_packet', 'budget_ordinal': len(histories) - 1})
                return original_packet(raw)
            def resource(raw):
                topology.append({'call': 'check_resources_extra', 'budget_ordinal': len(histories) - 1})
                return original_resource(raw)
            with patched(self.runtime, 'Budget', RecordingBudget), \
                 patched(self.runtime, 'emit_packet', packet), \
                 patched(self.runtime, 'check_resources', resource):
                self.target(self.raws['P01'])
                self.target(self.raws['P02'])
            require(len(histories) == 2 and histories[0][0] is not histories[1][0], 'one fresh Budget per call')
            require(topology == [{'call': 'emit_packet', 'budget_ordinal': 0},
                                 {'call': 'check_resources_extra', 'budget_ordinal': 0},
                                 {'call': 'emit_packet', 'budget_ordinal': 1},
                                 {'call': 'check_resources_extra', 'budget_ordinal': 1}], 'exact direct lower topology')
            observations.append({'direct_public_topology': topology,
                                 'budget_reservations': [item[1] for item in histories],
                                 'hidden_lower_admissions': 'unchanged and not counted as absent'})
        elif cid in ('A06', 'A07', 'A08'):
            function = {'A06': self.checker.check_resources, 'A07': self.metadata.check_metadata,
                        'A08': self.packet.emit_packet}[cid]
            opaque, _ = self.evidence.operation(cid, 'opaque-construction-lower-api',
                function.__module__ + '.' + function.__name__, {'base_case': 'P01'},
                lambda: function(json.loads(self.raws['P01'])))
            self.lower_prerequisites += 1
            self.target(self.raws['P01'], argument=opaque, expected=spec['diagnostic'],
                recipe={'kind': 'actual-fresh-public-opaque-object', 'constructor': function.__name__,
                        'constructor_raw_case': 'P01'})
        elif cid == 'A09':
            self.target(self.raws['P05'], argument=self.primary['P05'][0], expected=spec['diagnostic'],
                recipe={'kind': 'retained-RuntimeEmission-object', 'emission_id': self.primary['P05'][1]['emission_id']})
        elif cid == 'A10':
            actual = self.primary['P01'][0]
            class FakeChecked:
                pass
            fake = FakeChecked()
            fake.verified = True
            fake.canonical_ir_json = actual.canonical_ir_json
            fake.metadata_json = actual.metadata_json
            fake.manifest_sha256 = actual.manifest_sha256
            fake.bindings = dict(json.loads(actual.manifest_json)['bindings'])
            for name, value in fake.bindings.items():
                setattr(fake, name + '_sha256', value)
            self.target(self.raws['P01'], argument=fake, expected=spec['diagnostic'],
                recipe={'kind': 'test-only-nondict-FakeChecked', 'verified': True,
                        'copied_from_emission': self.primary['P01'][1]['emission_id'],
                        'attributes': sorted(fake.__dict__)})
        elif cid == 'A11':
            self.target(self.raws['P01'], kwargs={'metadata': {}}, expected=spec['diagnostic'],
                        recipe={'kind': 'public-signature-keyword', 'base_case': 'P01', 'metadata': {}})
        elif cid == 'A12':
            raw = json.loads(self.raws['P01'])
            require('metadata' not in raw, 'extra-member selector')
            raw['metadata'] = {}
            text = json.dumps(raw, separators=(',', ':'), ensure_ascii=False)
            self.target(text, argument=raw, expected=spec['diagnostic'],
                recipe={'kind': 'top-level-extra-member', 'base_case': 'P01', 'metadata': {},
                        'actual_input_raw_text': text})
        elif cid == 'A13':
            self.no_execution_source_check()
        elif cid == 'A14':
            artifact = self.primary['P01'][0]
            manifest = json.loads(artifact.manifest_json)
            require(manifest['code_mapping'] == [] and manifest['labels'] == [], 'genuine empty census')
            require(manifest['storage_plan']['binding']['members'] ==
                    [{'name': 'header', 'c_type': 'Rt8BindingHeader', 'count': 1}], 'header-only binding')
            require(manifest['frames'][0]['code'] is None and len(manifest['frames']) == 1, 'entry-only frames')
            for field in ('runtime_header', 'runtime_source'):
                source = getattr(artifact, field)
                require(not re.search(r'\[\s*0\s*\]', source), 'zero-sized array forbidden')
                require(not re.search(r'\b(?:codes|label_offsets|label_bytes)\s*\[', source), 'empty arrays must be absent')
            require('rt8_entry(' in artifact.runtime_source, 'real entry required')
            observations.append({'code_count': 0, 'label_count': 0, 'binding_members': ['header']})
        else:
            raise AssertionError('unknown API case')

    def no_execution_source_check(self):
        allowed = {
            'runtime_emit.py': {('__future__', 0), ('dataclasses', 0), ('packet', 1),
                ('checker', 1), ('program_schema', 1), ('runtime_emit_budget', 1), ('runtime_emit_body', 1)},
            'runtime_emit_body.py': {('__future__', 0), ('runtime_emit_budget', 1), ('hashlib', 0)},
            'runtime_emit_budget.py': {('__future__', 0), ('functools', 0), ('hashlib', 0), ('json', 0)},
        }
        denied = {'eval', 'exec', 'compile', '__import__', 'open', 'breakpoint'}
        inspections = []
        for filename, imports in allowed.items():
            raw = self.source_bytes['resource_ir_v8/' + filename]
            tree = ast.parse(raw, filename=filename)
            actual = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    actual.update((alias.name, 0) for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    actual.add((node.module, node.level))
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        require(node.func.id not in denied, 'execution/file call ' + node.func.id)
                    elif isinstance(node.func, ast.Attribute):
                        require(node.func.attr not in {'system', 'popen', 'Popen', 'run', 'execv', 'spawn', 'CDLL'},
                                'execution attribute call ' + node.func.attr)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    require(node.name not in {'main', 'run', 'run_native', 'evaluate'}, 'execution entrypoint')
            require(actual == imports, 'exact production import allowlist ' + filename)
            inspections.append({'path': 'resource_ir_v8/' + filename,
                                'imports': [{'module': x, 'level': y} for x, y in sorted(actual)]})
        init_tree = ast.parse(self.source_bytes['resource_ir_v8/__init__.py'])
        require(all('runtime_emit' not in ast.dump(node) for node in init_tree.body), 'default package wiring')
        allowed_headers = {'ir8_packet.h', 'ir8_packet_generated.h', 'rir8_runtime.h',
                           'ir8_runtime_generated.h', 'stddef.h', 'stdint.h'}
        for emission in self.emissions:
            for pin in emission['files']:
                if not pin['path'].endswith(('.c', '.h')):
                    continue
                source = read_stable(self.root / pin['path'], SOURCE_CAP).decode('utf-8')
                includes = re.findall(r'^#include\s+[<"]([^>"]+)[>"]$', source, re.MULTILINE)
                require(set(includes) <= allowed_headers, 'unreviewed C include')
                require(not re.search(r'\b(?:main|system|popen|fork|execve)\s*\(', source), 'generated execution entrypoint')
                require(not re.search(r'\brt8_body_\d+\([^)]*\)\s*\{\s*(?:return NULL;)?\s*\}', source),
                        'placeholder callback body')
        self.test_rows[-1]['observations'].append({'production_ast': inspections,
             'generated_sets_inspected': len(self.emissions), 'compiled_or_invoked': False})

    def mutant_case(self, spec):
        base, saved, _ = self.primary[spec['input']]
        mutated, recipe = self.oracle.mutate(spec['id'], self.raws[spec['input']], base)
        require(type(recipe) is dict, 'mutation receipt required')
        record = dict(recipe)
        record.update(test_id=spec['id'], base_emission_id=saved['emission_id'],
                      expected_diagnostic=spec['diagnostic'], actual_diagnostic=None)
        required = self.data['evidence_schema']['mutant_record_required']
        require(set(required) <= set(record), 'mutation reconstruction receipt fields')
        for splice in record['source_splices']:
            require(set(splice) == set(self.data['evidence_schema']['source_splice_keys']), 'source splice schema')
            require(type(splice['exact_match_count']) is int and splice['exact_match_count'] == 1,
                    'mutant selector must be unique')
        for patch in record['typed_json_patches']:
            require(set(patch) == set(self.data['evidence_schema']['typed_json_patch_keys']), 'typed patch schema')
        reconstruction = reconstruct_mutation(base, mutated, record)
        self.test_rows[-1]['observations'].append(record)
        self.test_rows[-1]['observations'].append({'independent_mutant_reconstruction': reconstruction})
        lower_before = len(self.evidence.operations)
        try:
            self.verify(self.raws[spec['input']], mutated, mutant=True)
        except BaseException as error:
            if isinstance(error, CustodyError) or self.evidence.broken:
                raise
            record['actual_diagnostic'] = diagnostic(error)
            require(record['actual_diagnostic'] == spec['diagnostic'], 'exact unmasked mutant diagnostic')
            lower = [op for op in self.evidence.operations[lower_before:] if op['kind'] == 'oracle-lower-api']
            require(len(lower) == 3 and all(op['returned'] is True for op in lower),
                    'mutant expected diagnostic cannot replace fresh lower authority calls')
            self.oracle_mutants += 1
        else:
            raise AssertionError('independent source oracle accepted mutated artifact')

    def budget_case(self, spec):
        """Synthetic hooks only; none is a valid maximum-capacity raw program."""
        mod, body, cid = self.budget, self.body, spec['id']
        observed = {'synthetic': True, 'public_admission': False, 'case_id': cid,
                    'seed': {}, 'arguments': [], 'observations': []}
        def counters(b):
            return {key: getattr(b, key) for key in STAT_KEYS[:6]}
        def reject(thunk, expected=spec['diagnostic']):
            try:
                thunk()
            except mod.RuntimeEmissionError as error:
                require(diagnostic(error) == expected, 'private control exact diagnostic')
                observed['observations'].append({'rejection': error_record(error)})
                return error
            raise AssertionError('private control did not reject')
        def planner(b):
            plan = body.Planner({}, {}, {}, b)
            plan.new_function(None, 'rt8_entry', [], {'root': 'entry', 'name': None, 'segments': []}, None)
            return plan, plan.functions[0]
        class TraceBudget(mod.Budget):
            def __init__(inner):
                super().__init__()
                inner.events = []
            def reserve(inner, *, creation=0, work=0):
                before = counters(inner)
                event = {'creation': creation, 'work': work, 'before': before, 'after': None, 'error': None}
                try:
                    result = super().reserve(creation=creation, work=work)
                except BaseException as error:
                    event['error'] = diagnostic(error)
                    inner.events.append(event)
                    raise
                event['after'] = counters(inner)
                inner.events.append(event)
                require(len(inner.events) <= 20000, 'finite instrumentation event limit')
                return result
        if cid in ('B01', 'B02'):
            b = mod.Budget()
            field, keyword = ('creation_units', 'creation') if cid == 'B01' else ('work_units', 'work')
            limit = mod.LIMITS[field]
            setattr(b, field, limit - 1)
            observed['seed'] = counters(b)
            observed['arguments'] = [{keyword: 1}, {keyword: 1}]
            b.reserve(**{keyword: 1})
            require(getattr(b, field) == limit, 'exact-bound reservation')
            before = counters(b)
            reject(lambda: b.reserve(**{keyword: 1}))
            require(counters(b) == before, 'failed reserve must not change counters')
            observed['observations'].append({'at_bound': before, 'after_rejection': counters(b)})
        elif cid == 'B03':
            b = mod.Budget()
            # Represent four sources with four small real strings and a seeded
            # aggregate. No giant text or public program is manufactured.
            b.source_utf8_bytes = mod.LIMITS['source_utf8_bytes'] - 4
            observed['seed'] = counters(b)
            for field, _ in SOURCE_FIELDS:
                old = b.source_utf8_bytes
                pair = mod.hash_text('x', b, source=True)
                require(pair == (digest(b'x'), 1) and b.source_utf8_bytes == old + 1,
                        'reused/new source must consume shared aggregate')
                observed['arguments'].append({'field': field, 'text': 'x', 'source': True})
            require(b.source_utf8_bytes == mod.LIMITS['source_utf8_bytes'], 'exact four-source bound')
            reject(lambda: mod.hash_text('y', b, source=True))
            require(b.source_utf8_bytes == mod.LIMITS['source_utf8_bytes'], 'failed byte reservation unchanged')
            observed['observations'].append({'final': counters(b), 'retained_packet_fields_included': True})
        elif cid == 'B04':
            b = mod.Budget()
            writer = mod.Writer(b, 'manifest')
            b.manifest_utf8_bytes = mod.LIMITS['manifest_utf8_bytes'] - 1
            observed['seed'] = counters(b)
            writer.emit(b'x')
            before = (writer.size, bytes(writer.buffer), len(writer.chunks), b.manifest_utf8_bytes)
            reject(lambda: writer.emit(b'y'))
            require((writer.size, bytes(writer.buffer), len(writer.chunks), b.manifest_utf8_bytes) == before,
                    'manifest failure before append')
            observed['arguments'] = [{'emit_bytes_hex': '78'}, {'emit_bytes_hex': '79'}]
            observed['observations'].append({'writer_size': writer.size, 'buffer_hex': bytes(writer.buffer).hex(),
                                             'final': counters(b)})
        elif cid == 'B05':
            b = mod.Budget()
            plan, frame = planner(b)
            b.label_utf8_bytes = mod.LIMITS['label_utf8_bytes'] - 2
            success_seed = counters(b)
            plan.label(frame, 'x')
            require(b.label_utf8_bytes == mod.LIMITS['label_utf8_bytes'], 'label includes NUL')
            # The smallest legal label is two bytes with its terminator. A
            # separate seed limit-1 therefore reaches exact FIRST-over total.
            failed = mod.Budget()
            failed_plan, failed_frame = planner(failed)
            failed.label_utf8_bytes = mod.LIMITS['label_utf8_bytes'] - 1
            reject_seed = counters(failed)
            previous = (dict(failed_plan.label_set), failed.label_count, failed.label_utf8_bytes,
                        len(failed_frame['declarations']), len(failed_frame['statements']))
            reject(lambda: failed_plan.label(failed_frame, 'y'))
            require(previous == (dict(failed_plan.label_set), failed.label_count, failed.label_utf8_bytes,
                                  len(failed_frame['declarations']), len(failed_frame['statements'])),
                    'first-over label failure before pool/declaration/statement creation')
            require(failed.work_units > reject_seed['work_units'], 'already inspected work remains charged')
            observed['seed'] = {'exact_bound': success_seed, 'first_over': reject_seed}
            observed['arguments'] = [{'label': 'x', 'utf8_plus_terminator': 2, 'prospective_total': 1048576},
                                     {'label': 'y', 'utf8_plus_terminator': 2, 'prospective_total': 1048577}]
            observed['observations'].append({'successful_label_set': {k: v.hex() for k, v in plan.label_set.items()},
                'exact_bound_final': counters(b), 'rejected_label_set': {}, 'first_over_final': counters(failed),
                'failed_reservation_unchanged_scope': ['label_count', 'label_utf8_bytes', 'label_set'],
                'previously_charged_key_character_work_preserved': True})
        elif cid == 'B06':
            b = mod.Budget()
            plan, frame = planner(b)
            plan.label(frame, 'existing')
            b.label_count = mod.LIMITS['label_count']
            observed['seed'] = counters(b)
            old = (b.label_count, b.label_utf8_bytes, dict(plan.label_set))
            plan.label(frame, 'existing')
            require((b.label_count, b.label_utf8_bytes, dict(plan.label_set)) == old, 'label reuse must not grow pool')
            before = (len(frame['declarations']), len(frame['statements']))
            reject(lambda: plan.label(frame, 'new'))
            require((b.label_count, b.label_utf8_bytes, dict(plan.label_set)) == old and
                    before == (len(frame['declarations']), len(frame['statements'])), 'distinct label before insert')
            observed['arguments'] = [{'label': 'existing'}, {'label': 'new'}]
            observed['observations'].append({'final': counters(b), 'physical_dictionary_entries': len(plan.label_set)})
        elif cid == 'B07':
            b = mod.Budget()
            writer = mod.Writer(b, 'source')
            writer.emit(b'x' * 4096)
            before = (writer.size, bytes(writer.buffer), len(writer.chunks), counters(b))
            reject(lambda: writer.emit(b'x' * 4097))
            require(before == (writer.size, bytes(writer.buffer), len(writer.chunks), counters(b)), 'chunk rejection before append')
            observed['arguments'] = [{'byte': 120, 'repeat': 4096}, {'byte': 120, 'repeat': 4097}]
            observed['observations'].append({'writer_size': writer.size, 'final': counters(b)})
        elif cid == 'B08':
            b = mod.Budget()
            plan, frame = planner(b)
            # 5 parameters + 100 handles + 4*2 scopes + 200 vector pointers
            # + 199 accessors = 512. Entry then differs only in parameter count.
            frame.update(code=0, symbol='rt8_body_0', handles=100, scopes=2, vectors=200, accessors=199)
            observed['seed'] = {'frame': {k: frame[k] for k in
                               ('code', 'symbol', 'handles', 'scopes', 'vectors', 'accessors')}}
            plan.frame_census()
            require(len(plan.frames) == 1 and plan.frames[0]['pointer_cells'] == 512 and
                    plan.frames[0]['parameter_pointer_cells'] == 5 and
                    plan.frames[0]['local_pointer_cells'] == 108, 'complete Body pointer census')
            observed['observations'].append({'body_at_bound': dict(plan.frames[0])})
            before = list(plan.frames)
            frame['accessors'] += 1
            reject(plan.frame_census)
            require(plan.frames == before, '513 rejected before frame append')
            entry_plan, entry = planner(mod.Budget())
            entry.update(handles=100, scopes=2, vectors=200, accessors=203)
            entry_plan.frame_census()
            require(entry_plan.frames[0]['pointer_cells'] == 512 and
                    entry_plan.frames[0]['parameter_pointer_cells'] == 1, 'complete Entry pointer census')
            observed['observations'].append({'entry_at_bound': dict(entry_plan.frames[0])})
            observed['arguments'] = [{'operation': 'frame_census', 'total': 512},
                                     {'operation': 'frame_census', 'total': 513},
                                     {'operation': 'entry_frame_census', 'total': 512}]
        elif cid == 'B09':
            b = TraceBudget()
            calls = []
            original = mod.json.loads
            def decode(text, *args, **kwargs):
                calls.append({'text': text, 'counters_at_decode': counters(b)})
                return original(text, *args, **kwargs)
            exact_text = '[' * 64 + '0' + ']' * 64
            over_text = '[' * 65 + '0' + ']' * 65
            with patched(mod.json, 'loads', decode):
                value = mod.decode_fresh(exact_text, b)
                require(len(calls) == 1, '64-depth reaches genuine decoder exactly once')
                for _ in range(64):
                    require(type(value) is list and len(value) == 1, 'exact nested decode')
                    value = value[0]
                require(value == 0 and type(value) is int, 'nested decode leaf')
                at = len(calls)
                reject(lambda: mod.decode_fresh(over_text, b))
                require(len(calls) == at, '65-depth must reject before json.loads')
            observed['arguments'] = [exact_text, over_text]
            observed['observations'] = [{'decoder_calls': calls, 'reservations': b.events,
                                         'final': counters(b)}] + observed['observations']
        elif cid == 'B10':
            calls = []
            original = self.schema.json.loads
            def decode(text, *args, **kwargs):
                calls.append({'text': text})
                return original(text, *args, **kwargs)
            exact_text = '[' * 32 + '0' + ']' * 32
            over_text = '[' * 33 + '0' + ']' * 33
            with patched(self.schema.json, 'loads', decode):
                value = self.schema.parse(exact_text)
                require(type(value) is list and len(calls) == 1, '32 raw text containers decode')
                try:
                    self.schema.parse(over_text)
                except self.schema.ResourceError as error:
                    require(diagnostic(error) == spec['diagnostic'], 'raw depth exact unchanged lower diagnostic')
                    observed['observations'].append({'rejection': error_record(error)})
                else:
                    raise AssertionError('33 raw text containers accepted')
                require(len(calls) == 1, '33 raw text containers reject before decode')
            observed['arguments'] = [exact_text, over_text]
            observed['observations'].append({'decoder_calls': calls, 'valid_raw_program_claim': False})
        elif cid in ('B11', 'B12', 'B13'):
            value = {'B11': False, 'B12': -1, 'B13': 4294967296}[cid]
            # Reviewed clarification: the helper's count itself is uint32, so
            # use its largest legal count to reach the VALUE rejection branch.
            count = 4294967295
            observed['arguments'] = [{'value': typed(value), 'count': count, 'code': 'CODE_CENSUS'}]
            reject(lambda: mod.plain_index(value, count, 'CODE_CENSUS'))
        elif cid == 'B14':
            b = TraceBudget()
            plan, frame = planner(b)
            b.events.clear()
            before = counters(b)
            plan.label(frame, '\U0001f98a')
            require(plan.label_set == {'\U0001f98a': bytes.fromhex('f09fa68a')}, 'exact four-byte scalar label')
            require(b.label_count == 1 and b.label_utf8_bytes == 5, 'four UTF-8 bytes plus terminator')
            conversions = [event for event in b.events if event['creation'] == 1 and event['work'] == 5]
            require(len(conversions) == 1 and conversions[0]['before']['label_utf8_bytes'] == 5,
                    'label bytes+terminator reserved before scalar conversion')
            fail_b = TraceBudget()
            fail_plan, fail_frame = planner(fail_b)
            fail_b.label_utf8_bytes = mod.LIMITS['label_utf8_bytes'] - 4
            fail_b.events.clear()
            expected = {'path': 'runtime.label_bytes', 'layer': 'runtime-emitter-bounds', 'code': 'LABEL_BYTES'}
            reject(lambda: fail_plan.label(fail_frame, '\U0001f98a'), expected)
            require(fail_plan.label_set == {} and not any(event['creation'] == 1 and event['work'] == 5
                                                          for event in fail_b.events), 'overbound label must not convert')
            observed['seed'] = {'success_before': before, 'reject_available_label_bytes': 4}
            observed['arguments'] = [{'hook': 'Planner.label', 'text': '\U0001f98a'}]
            observed['observations'].append({'scope': 'native label writer, not generic Encoder.string',
                'success_reservations': b.events, 'reject_reservations': fail_b.events, 'final': counters(b)})
        elif cid == 'B15':
            b = TraceBudget()
            values = ['a' * 4095 + 'b', 'a' * 4095 + 'c']
            actual = b.ordered(values)
            require(actual == values, 'fixed long-prefix sort')
            comparisons = [event for event in b.events if event['creation'] == 2 and event['work'] == 1]
            require(len(comparisons) == 4096, 'every compared character precharged')
            require(all(event['after']['work_units'] == event['before']['work_units'] + 1
                        for event in comparisons), 'monotonic character comparison work')
            fail_b = TraceBudget()
            fail_b.work_units = mod.LIMITS['work_units']
            expected = {'path': 'runtime.work_units', 'layer': 'runtime-emitter-bounds', 'code': 'WORK_UNITS'}
            reject(lambda: fail_b.ordered(values), expected)
            require(not any(event['creation'] == 2 and event['work'] == 1 for event in fail_b.events),
                    'failed comparator reservation precedes character indexing')
            raw = {'entry': [{'op': 'generalize', 'body': [{'op': 'finish'}]}]}
            path = {'root': 'entry', 'name': None, 'segments': [0, 'body', 0]}
            walk_b = TraceBudget()
            require(body.raw_at(raw, path, walk_b) is raw['entry'][0]['body'][0], 'structured path resolves actual object')
            touched = []
            class GuardRaw(dict):
                def __getitem__(inner, key):
                    touched.append(key)
                    return super().__getitem__(key)
            blocked = TraceBudget()
            blocked.work_units = mod.LIMITS['work_units']
            reject(lambda: body.raw_at(GuardRaw(raw), path, blocked), expected)
            require(touched == [], 'failed path preflight before raw access')
            observed['arguments'] = [{'comparison_strings': values}, {'raw': raw, 'structured_path': path}]
            observed['observations'].append({'comparison_character_reservations': len(comparisons),
                'comparison_first': b.events[0], 'comparison_last': b.events[-1],
                'comparison_totals': counters(b), 'failed_comparison_reservations': fail_b.events,
                'path_reservations': walk_b.events, 'blocked_path_reservations': blocked.events,
                'blocked_raw_accesses': touched})
        elif cid == 'B16':
            text = '{"a":[1,2]}'
            b = TraceBudget()
            calls = []
            original = mod.json.loads
            def decode(value, *args, **kwargs):
                calls.append({'text': value, 'counters': counters(b), 'reservations': list(b.events)})
                return original(value, *args, **kwargs)
            with patched(mod.json, 'loads', decode):
                result = mod.decode_fresh(text, b)
            require(result == {'a': [1, 2]} and len(calls) == 1, 'genuine decode exactly once')
            # Scanner: two headers, one key string, two numbers, one object
            # membership, two array memberships = 8 owned creation units.
            require(calls[0]['reservations'][-1]['creation'] == 8 and
                    calls[0]['reservations'][-1]['work'] == 2 * len(text) + 8 + 1,
                    'complete owned tree reserved before decode')
            fail_b = TraceBudget()
            fail_b.creation_units = mod.LIMITS['creation_units'] - 1
            fail_calls = []
            def blocked_decode(value, *args, **kwargs):
                fail_calls.append(value)
                return original(value, *args, **kwargs)
            expected = {'path': 'runtime.creation_units', 'layer': 'runtime-emitter-bounds', 'code': 'CREATION_UNITS'}
            with patched(mod.json, 'loads', blocked_decode):
                reject(lambda: mod.decode_fresh(text, fail_b), expected)
            require(fail_calls == [], 'failed container reservation before decoder')
            observed['arguments'] = [text]
            observed['observations'].append({'decoder_calls': calls, 'failed_decoder_calls': fail_calls,
                                             'failed_reservations': fail_b.events})
        elif cid == 'B17':
            artifact = self.primary['P05'][0]
            manifest = json.loads(artifact.manifest_json)
            statistics = dict(artifact.statistics)
            require(tuple(key for key, _ in artifact.statistics) == STAT_KEYS, 'exact final statistics order')
            phase = manifest['statistics']
            require(phase['phase'] == 'pre-manifest-serialization', 'explicit finite phase')
            require(statistics['creation_units'] >= phase['creation_units'] and
                    statistics['work_units'] >= phase['work_units'], 'final counters after snapshot')
            source_bytes = sum(text_pin(getattr(artifact, field))['bytes'] for field, _ in SOURCE_FIELDS)
            label_bytes = sum(len(row['value'].encode('utf-8')) + 1 for row in manifest['labels'])
            require(statistics['source_utf8_bytes'] == phase['source_utf8_bytes'] == source_bytes,
                    'four-source final exact bytes')
            require(statistics['manifest_utf8_bytes'] == len(artifact.manifest_json.encode('utf-8')),
                    'manifest final exact bytes')
            require(statistics['label_utf8_bytes'] == phase['label_utf8_bytes'] == label_bytes and
                    statistics['label_count'] == phase['label_count'] == len(manifest['labels']),
                    'label final exact bytes/count')
            require('manifest_utf8_bytes' not in phase, 'no serialization fixed point')
            # Source-only sequencing check complements the retained actual
            # observation without introducing a 68th public target attempt.
            tree = ast.parse(self.source_bytes['resource_ir_v8/runtime_emit.py'])
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_manifest')
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and
                     isinstance(node.func, ast.Attribute) and node.func.attr == 'reserve_result']
            require(len(calls) == 1, 'one final result reservation')
            assignments = [node for node in ast.walk(function) if isinstance(node, ast.Assign) and
                           any('creation_units' in ast.dump(target) for target in node.targets)]
            require(assignments and all(calls[0].lineno < node.lineno for node in assignments),
                    'result/container reservation precedes pre-manifest counters')
            observed['arguments'] = [{'retained_emission_id': self.primary['P05'][1]['emission_id']}]
            observed['observations'].append({'pre_manifest': phase, 'final_statistics_typed': typed(artifact.statistics),
                                             'result_reservation_source_line': calls[0].lineno})
        elif cid == 'B18':
            b = mod.Budget()
            writer = mod.Writer(b, 'source')
            b.source_utf8_bytes = mod.LIMITS['source_utf8_bytes']
            observed['seed'] = counters(b)
            before = (writer.size, bytes(writer.buffer), list(writer.chunks), counters(b))
            error = reject(lambda: writer.emit(b'x'))
            require(before == (writer.size, bytes(writer.buffer), list(writer.chunks), counters(b)),
                    'failed private writer append is atomic')
            for name in ('path', 'layer', 'code', 'message', '_path', '_layer', '_code', '_message'):
                value = getattr(error, name)
                try:
                    setattr(error, name, value)
                except AttributeError:
                    pass
                else:
                    raise AssertionError('mutable error field ' + name)
            require(type(error) is mod.RuntimeEmissionError and not isinstance(writer, self.runtime.RuntimeEmission),
                    'private failure is not public emission')
            observed['arguments'] = [{'emit_bytes_hex': '78'}]
            observed['observations'].append({'private_snapshot_nonadmitting': True, 'writer_size': writer.size,
                                             'buffer_hex': bytes(writer.buffer).hex(), 'final': counters(b)})
        else:
            raise AssertionError('unknown private budget case')
        return observed

    def recheck_inputs(self):
        names = sorted(path.name for path in (self.package / 'resource_ir_v8').iterdir()
                       if path.suffix == '.py')
        require(names == sorted(PACKAGE_FILES), 'local package source census changed')
        require(not (self.package / 'resource_ir_v8/__pycache__').exists() and
                not (self.package / 'tests/__pycache__').exists(), 'unexpected local bytecode cache')
        for pin in self.input_pins:
            data = read_stable(self.package / pin['path'], READ_CAP)
            require(len(data) == pin['bytes'] and digest(data) == pin['sha256'],
                    'consumed source changed: ' + pin['path'])
        for pin in self.runtime_pins:
            data = read_stable(Path(pin['path']), 64 * MIB)
            require(len(data) == pin['bytes'] and digest(data) == pin['sha256'],
                    'imported runtime file changed: ' + pin['path'])
        if self.runtime_metadata is not None:
            require(list(sys.path) == self.runtime_metadata['actual_sys_path'], 'runtime import path changed')
        self.verify_origins()

    def public_counts(self):
        ops = [op for op in self.evidence.operations if op['kind'] == 'target-api']
        # Authoritative counts derive from immediate actual-call state, including
        # a return whose subsequent summary, oracle or persistence failed.
        return {'attempts': sum(op['state'] != 'intent-pending' for op in ops),
                'returns': sum(op['returned'] is True for op in ops),
                'rejections_or_signature_errors': sum(op['returned'] is False for op in ops),
                'unknown_started': sum(op['state'] == 'known-started' for op in ops),
                'intent_not_started': sum(op['state'] == 'intent-pending' for op in ops)}

    def final_report(self, result):
        successful = result.wasSuccessful() and result.testsRun == 128 and not result.skipped
        first_failure = None
        try:
            self.recheck_inputs()
            if successful:
                require(self.public_counts() == {'attempts': 67, 'returns': 33,
                    'rejections_or_signature_errors': 34, 'unknown_started': 0,
                    'intent_not_started': 0}, 'exact final public count')
                require(len(self.emissions) == 33 and all(row['persistence'] == 'complete' for row in self.emissions),
                        'all 33 successful emissions retained')
                require(self.oracle_successes == 33 and self.oracle_mutants == 44,
                        'exact independent oracle verification counts')
                lower_calls = [op for op in self.evidence.operations if op['kind'] == 'oracle-lower-api']
                require(len(lower_calls) == 231 and all(op['returned'] is True for op in lower_calls),
                        'three fresh public authorities per 77 oracle verifications')
                require(self.lower_prerequisites == 3, 'exact opaque lower prerequisite calls')
                require([row['test_id'] for row in self.test_rows] == list(EXPECTED_IDS) and
                        all(row['status'] == 'passed' for row in self.test_rows), 'exact finite test enumeration')
        except BaseException as error:
            successful = False
            first_failure = error_record(error)
        operations = [{key: value for key, value in op.items() if not key.startswith('_')}
                      for op in self.evidence.operations]
        report = {'format': 'ir8-stage05-host-results/1',
                  'status': ('expected-results-observed' if successful else 'failed'),
                  'completion_rule': 'Success additionally requires zero process exit, final stopped journal, '
                                     'closed/readback-complete files and supervisor full-root census.',
                  'tests_planned': 128, 'tests_run': result.testsRun,
                  'tests_unstarted': 128 - result.testsRun,
                  'failures': len(result.failures), 'errors': len(result.errors),
                  'skips': len(result.skipped), 'post_test_custody_failure': first_failure,
                  'public_counts': self.public_counts(), 'oracle_success_verifications': self.oracle_successes,
                  'oracle_mutant_rejections': self.oracle_mutants,
                  'direct_opaque_lower_prerequisites': self.lower_prerequisites,
                  'tests': self.test_rows, 'operations': operations, 'emissions': self.emissions,
                  'consumed_inputs_rechecked': first_failure is None,
                  'input_scope': 'consumed pinned subset only, not complete checkout',
                  'retained_before_report': list(self.evidence.pins.values()),
                  'journal_prefix': {'path': 'ATTEMPTS.jsonl', 'bytes': self.evidence.journal_bytes,
                                     'records': self.evidence.sequence},
                  'limits': {'owned_bytes': OWNED_CAP, 'owned_files': FILE_CAP,
                             'source_set_bytes': SOURCE_CAP, 'receipt_bytes': RECEIPT_CAP,
                             'host_results_bytes': HOST_CAP, 'journal_bytes': JOURNAL_CAP,
                             'inputs_bytes': INPUTS_CAP},
                  'native_compiler_model_original_execution': False,
                  'supervisor_responsibilities': ['process-time-memory-stream limits',
                      'full checkout custody', 'full retained-root census including supervisor files',
                      'interpret missing terminal record as uncertain, never retry automatically']}
        self.evidence.write('HOST_RESULTS.json', _json_bytes(report, HOST_CAP), HOST_CAP, None)
        self.evidence.event(None, None, 'artifact-persistence', 'stopped',
            {'status': 'tests-and-persistence-observed' if successful else 'failed',
             'public_counts': self.public_counts(), 'tests_run': result.testsRun,
             'planned_unstarted': 128 - result.testsRun,
             'incomplete_operations': [op['id'] for op in operations
                                      if op['state'] in ('intent-pending', 'known-started')],
             'reserved_bytes': self.evidence.reserved_bytes,
             'reserved_files': self.evidence.reserved_files,
             'close_and_final_readback': 'pending; zero exit required'})
        self.evidence.close()
        # No writes after terminal close. Any error now is a nonzero process
        # outcome, even if HOST_RESULTS has already recorded expected test data.
        self.verify_output_census(successful)
        if first_failure:
            raise CustodyError('post-test custody failure: ' + first_failure['message'])
        return successful

    def verify_output_census(self, successful):
        found = []
        total = 0
        for directory, names, files in os.walk(self.root, followlinks=False):
            for name in names:
                path = Path(directory) / name
                require(not path.is_symlink(), 'symlink output directory')
                relative = path.relative_to(self.root).as_posix()
                require(relative == 'emissions' or re.fullmatch(r'emissions/[0-9]{3}', relative),
                        'unexpected output directory')
            for name in files:
                path = Path(directory) / name
                relative = path.relative_to(self.root).as_posix()
                cap = JOURNAL_CAP if relative == 'ATTEMPTS.jsonl' else (
                    HOST_CAP if relative == 'HOST_RESULTS.json' else SOURCE_CAP)
                actual = read_stable(path, cap)
                found.append(relative)
                total += len(actual)
                if relative == 'ATTEMPTS.jsonl':
                    require(len(actual) == self.evidence.journal_bytes and
                            digest(actual) == self.evidence.journal_digest.hexdigest(), 'final complete journal pin')
                    rows = [json.loads(line) for line in actual.splitlines()]
                    require([row['sequence'] for row in rows] == list(range(len(rows))), 'contiguous journal sequence')
                    require(rows and rows[-1]['event'] == 'stopped', 'durable terminal journal missing')
                else:
                    state = self.evidence.pins[relative]
                    pin = state['pin']
                    require(state['state'] == 'durably-journaled' and len(actual) == pin['bytes'] and
                            digest(actual) == pin['sha256'], 'output pin/readback mismatch')
        require(set(found) == set(self.evidence.pins) | {'ATTEMPTS.jsonl'}, 'exact owned output file census')
        require(len(found) <= FILE_CAP and total <= OWNED_CAP, 'owned final census exceeds limits')
        require(total == self.evidence.reserved_bytes and len(found) == self.evidence.reserved_files,
                'reservation/actual complete-file census mismatch')
        if successful:
            require(len(found) == 168, 'successful child must retain exactly 168 files')


class InventoryCase(unittest.TestCase):
    def __init__(self, state, spec):
        super().__init__('runTest')
        self.state, self.spec = state, spec
    def id(self):
        return 'stage05.' + self.spec['id']
    def __str__(self):
        return 'test_%s (%s)' % (self.spec['id'], self.id())
    def shortDescription(self):
        return None
    def runTest(self):
        self.state.run_case(self.spec)


class CustodyCase(unittest.TestCase):
    def runTest(self):
        raise AssertionError('diagnostic-only identity; never enumerated or run')
    def id(self):
        return 'stage05.custody'
    def shortDescription(self):
        return 'Stage05 bootstrap or post-test custody failure'


def bootstrap():
    require(sys.flags.no_site == 1 and sys.flags.optimize == 0 and sys.dont_write_bytecode,
            'exact unoptimized Python -B -S is required')
    require(os.path.isabs(sys.argv[0]) and os.path.abspath(sys.argv[0]) == _BOOT_PATH,
            'script must be supplied by absolute path')
    expected_environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                            'TZ': 'UTC', 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONHASHSEED': '0'}
    require(set(os.environ) == set(expected_environment) | {'HOME', 'TMPDIR'},
            'sanitized exact environment required; no PYTHONPATH, credentials, proxy or network inheritance')
    require(all(os.environ[k] == value for k, value in expected_environment.items()), 'environment value mismatch')
    class StrictParser(argparse.ArgumentParser):
        def error(self, message):
            raise CustodyError('argument error: ' + message)
    parser = StrictParser(add_help=False, allow_abbrev=False)
    parser.add_argument('--evidence-root', required=True)
    args = parser.parse_args()
    script = Path(_BOOT_PATH)
    no_symlinks(script)
    package = script.parent.parent
    candidate = package.parents[2]
    require(script.name == 'test_stage05_runtime_emit.py' and script.parent.name == 'tests' and
            package.name == 'resource-native' and package.parent.name == 'experimental' and
            package.parent.parent.name == 'tools', 'verified repository-relative script location')
    root = Path(args.evidence_root)
    require(root.is_absolute() and str(root) == args.evidence_root and '..' not in root.parts,
            'absolute normalized evidence path required')
    require(not root.is_relative_to(candidate), 'evidence root must be outside candidate source tree')
    no_symlinks(root, absent_leaf=True)
    for key in ('HOME', 'TMPDIR'):
        path = Path(os.environ[key])
        no_symlinks(path)
        require(path.is_dir() and not path.is_relative_to(candidate) and not path.is_relative_to(root),
                key + ' must be a separate external support directory')
    actual_package = sorted(p.name for p in (package / 'resource_ir_v8').iterdir() if p.suffix == '.py')
    require(actual_package == sorted(PACKAGE_FILES), 'exact reviewed local package source census')
    files = ['resource_ir_v8/' + name for name in PACKAGE_FILES] + [
        'tests/test_stage05_runtime_emit.py', 'tests/stage05_runtime_oracle.py',
        'tests/stage05_runtime_cases.json', 'tests/fixtures/ir8-runtime-abi-stage05a.json',
        'tests/fixtures/ir8-metadata.json']
    source_bytes, pins = {}, []
    for relative in sorted(files):
        data = read_stable(package / relative, READ_CAP)
        source_bytes[relative] = data
        pin = {'path': relative, 'bytes': len(data), 'sha256': digest(data)}
        pins.append(pin)
        if Path(relative).name in PRODUCTION_PINS:
            expected = PRODUCTION_PINS[Path(relative).name]
            require((pin['bytes'], pin['sha256']) == expected, 'production source freeze changed: ' + relative)
    data = json.loads(source_bytes['tests/stage05_runtime_cases.json'])
    require(data['abi_schema']['sha256'] == ABI_SHA256 and
            data['abi_schema']['path'] == 'tests/fixtures/ir8-runtime-abi-stage05a.json', 'ABI identity')
    for expected in (data['abi_schema'], data['source_fixture_file']):
        actual = next(pin for pin in pins if pin['path'] == expected['path'])
        require(actual == expected, 'portable input full-file pin mismatch')
    inventory = data['inventory']
    require(tuple(row['id'] for row in inventory['tests']) == EXPECTED_IDS, 'exact 128-test inventory order')
    require(sum(row['public_attempts'] for row in inventory['tests']) == 67 and
            sum(row['successful_emissions'] for row in inventory['tests']) == 33,
            'finite target counts')
    require(inventory['expected_success_tests'] == 128 and inventory['skips_allowed'] == 0 and
            inventory['failfast'] is True, 'inventory test lifecycle')
    require(data['evidence_schema']['success_file_count'] == 168 and
            len(data['evidence_schema']['success_emission_sets']) == 33, 'evidence set census')
    os.mkdir(root, 0o700)  # exclusive absent leaf, never reuse or overwrite
    fsync_directory(root.parent)
    sys.path.insert(0, str(package))
    return HostState(root, package, data, pins, source_bytes)


def main():
    state = None
    runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=2, failfast=True)
    result = None
    try:
        state = bootstrap()
        suite = unittest.TestSuite(InventoryCase(state, spec) for spec in state.inventory)
        require(suite.countTestCases() == 128, 'exact unittest enumeration')
        result = runner.run(suite)
        return 0 if state.final_report(result) else 1
    except BaseException:
        # Do not retry any API, write or unknown append. unittest owns stderr
        # diagnostics; no raw fixture or generated text is sent to stdout.
        failure = sys.exc_info()
        if state is not None:
            # Keep the last known actual-call facts visible in unittest's
            # bounded exception diagnostic even if durable custody is broken.
            try:
                note = {'known_in_memory_public_counts': state.public_counts(),
                        'journal_uncertain': state.evidence.broken,
                        'last_operations': [{key: op.get(key) for key in
                            ('id', 'test_id', 'kind', 'state', 'returned', 'summary', 'error', 'persistence')}
                            for op in state.evidence.operations[-3:]],
                        'interpretation': 'Only recorded facts are known; missing terminal durable state is uncertain.'}
                failure[1].add_note(_json_bytes(note, 16384).decode('ascii').rstrip())
            except BaseException:
                pass
        if result is None:
            result = runner._makeResult()
        result.addError(CustodyCase(), failure)
        result.printErrors()
        runner.stream.writeln('FAILED (Stage05 custody; no retry; incomplete durable state is uncertain)')
        if state is not None:
            try:
                state.evidence.close()
            except BaseException:
                result.addError(CustodyCase(), sys.exc_info())
                result.printErrors()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
