"""Strict bounded plain-JSON ingress for the non-executable Stage02 checker."""
from __future__ import annotations

import json

INPUT_BYTES = 33_554_432
INPUT_DEPTH = 32
INSTRUCTION_LIMIT = 10_000
SITE_CODE_LIMIT = 2_048
CAPTURE_LIMIT = 64
DECLARATION_KEYS = ('layouts', 'families', 'signatures', 'types', 'schemes', 'instantiations')
PROGRAM_KEYS = frozenset(('version', 'functions', 'codes', 'entry') + DECLARATION_KEYS)
SCHEMAS = {
    'new_root': ('out', 'imports'), 'new_below': ('out', 'ceiling', 'imports'),
    'alloc': ('out', 'in', 'layout', 'fields'), 'closure': ('out', 'in', 'function', 'captures'),
    'thunk': ('out', 'in', 'code', 'captures'), 'hole': ('out', 'in', 'layout'),
    'application': ('out', 'in', 'function', 'argument'),
    'application_borrow': ('out', 'in', 'function', 'argument'),
    'fill': ('hole', 'value'), 'borrow': ('out', 'value'), 'end_borrow': ('value',),
    'retain': ('out', 'value'), 'drop': ('value',), 'field': ('out', 'value', 'field'),
    'force': ('out', 'value'), 'return': ('value',), 'finish': (),
    'scalar': ('out', 'in', 'kind', 'value'), 'prim2': ('out', 'in', 'primitive', 'left', 'right'),
    'finish_scalar': ('value',), 'select_i64': ('out', 'in', 'condition', 'then', 'else'),
    'construct_nullary': ('out', 'in', 'family', 'variant'),
    'construct_sum': ('out', 'in', 'family', 'variant', 'fields'),
    'case_i64': ('out', 'in', 'family', 'scrutinee', 'arms'),
    'case_fields_i64': ('out', 'in', 'family', 'scrutinee', 'arms'),
    'generalize': ('out', 'in', 'scheme', 'body'),
    'seal': ('value',), 'instantiate': ('out', 'value', 'instantiation'),
}
GENERIC_OPS = frozenset(('new_below', 'scalar', 'closure', 'thunk', 'application',
                         'application_borrow', 'retain', 'drop', 'borrow', 'end_borrow'))
PRIMITIVES = {'addInt': '#i64', 'subInt': '#i64', 'mulInt': '#i64',
              'eqInt': '#bool', 'ltInt': '#bool'}


class ResourceError(ValueError):
    """Stable immutable rejection coordinates; prose is diagnostic only."""
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

    def __setattr__(self, key, value):
        raise AttributeError('ResourceError is immutable')


def fail(path, layer, code, message):
    raise ResourceError(path, layer, code, message)


def exact(value, keys, path):
    if type(value) is not dict or len(value) != len(keys) or any(k not in value for k in keys):
        fail(path, 'schema', 'SCHEMA', 'expected the exact documented object keys')
    return value


def mapping(value, path):
    if type(value) is not dict:
        fail(path, 'schema', 'SCHEMA', 'expected a plain object')
    return value


def sequence(value, path):
    if type(value) is not list:
        fail(path, 'schema', 'SCHEMA', 'expected a plain array')
    return value


def name(value, path, *, binder=False):
    if type(value) is not str or not value or '\0' in value or value.startswith('^'):
        fail(path, 'schema', 'NAME', 'expected a nonempty name outside the reserved ^ namespace')
    if binder and value.startswith('$'):
        fail(path, 'schema', 'NAME', 'user binders cannot use the reserved $ namespace')
    for ch in value:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            fail(path, 'schema', 'NAME', 'identifier contains a surrogate')
    return value


def diagnostic_path(path):
    root = 'entry' if path['root'] == 'entry' else ('functions.' if path['root'] == 'function' else 'codes.') + path['name'] + '.body'
    for segment in path['segments']:
        root += '.body' if segment == 'body' else '[' + str(segment) + ']'
    return root


def _validate_scalar(value):
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if value.bit_length() > 64:
            fail('program', 'schema', 'INTEGER', 'integer exceeds the bounded 64-bit JSON input domain')
        return
    if type(value) is str:
        if len(value) > INPUT_BYTES:
            fail('program', 'schema', 'INPUT_BYTES', 'string exceeds input byte budget')
        for ch in value:
            if 0xD800 <= ord(ch) <= 0xDFFF:
                fail('program', 'schema', 'UTF8', 'unpaired surrogate is not a Unicode scalar')
        return
    fail('program', 'schema', 'JSON', 'only plain JSON objects, arrays and non-floating scalars are admitted')


def snapshot(data):
    """Prechecked iterative walk; raw containers may share but may not cycle.

    The traversal itself is under raw input bounds, not the analysis budget.
    Canonical emission charges each repeated reference's bytes independently.
    """
    if type(data) is not dict:
        fail('program', 'schema', 'SCHEMA', 'program must be a plain object')
    active = set()
    stack = []
    current = data
    depth = 1
    raw_bytes = 0
    def charge_bytes(count):
        nonlocal raw_bytes
        if count > INPUT_BYTES - raw_bytes:
            fail('program', 'schema', 'INPUT_BYTES', 'canonical input exceeds 32 MiB')
        raw_bytes += count
    def string_bytes(value):
        charge_bytes(2)  # opening/closing quotes
        for char in value:
            n = ord(char)
            if 0xD800 <= n <= 0xDFFF:
                fail('program', 'schema', 'UTF8', 'unpaired surrogate is not a Unicode scalar')
            if char in ('"', '\\', '\b', '\f', '\n', '\r', '\t'):
                charge_bytes(2)
            elif n < 32:
                charge_bytes(6)
            else:
                charge_bytes(1 if n < 128 else 2 if n < 2048 else 3 if n < 65536 else 4)
    while True:
        if type(current) in (dict, list):
            if depth > INPUT_DEPTH:
                fail('program', 'schema', 'INPUT_DEPTH', 'container depth exceeds 32')
            if id(current) in active:
                fail('program', 'schema', 'JSON', 'cyclic input is not JSON')
            charge_bytes(2 + max(0, len(current) - 1))
            active.add(id(current))
            if type(current) is dict:
                for key in current:
                    if type(key) is not str:
                        fail('program', 'schema', 'JSON', 'JSON keys must be strings')
                    string_bytes(key)
                    charge_bytes(1)  # colon
                iterator = iter(current.values())
            else:
                iterator = iter(current)
            # Iterator frames grow only with container depth, never width.
            stack.append((id(current), iterator, depth))
        elif type(current) is str:
            string_bytes(current)
        else:
            _validate_scalar(current)
            charge_bytes(4 if current is None or current is True else 5 if current is False else len(str(current)))
        while stack:
            container_id, iterator, parent_depth = stack[-1]
            try:
                current = next(iterator)
                depth = parent_depth + 1
                break
            except StopIteration:
                active.remove(container_id)
                stack.pop()
        else:
            break
    from .budgets import canonical_encode
    canonical, _ = canonical_encode(data, limit=INPUT_BYTES, raw=True)
    # json.loads now sees bounded, depth-checked, own canonical text only.
    owned = json.loads(canonical)
    exact(owned, PROGRAM_KEYS, 'program')
    if type(owned['version']) is not int or owned['version'] != 8:
        fail('program.version', 'schema', 'VERSION', 'only exact integer IR version 8 is admitted')
    return owned, canonical


def parse(text):
    if type(text) is not str:
        fail('program', 'schema', 'JSON', 'loads_resources requires text')
    if len(text) > INPUT_BYTES:
        fail('program', 'schema', 'INPUT_BYTES', 'serialized input exceeds 32 MiB')
    size = 0
    depth = 0
    quoted = escaped = False
    for ch in text:
        n = ord(ch)
        if 0xD800 <= n <= 0xDFFF:
            fail('program', 'schema', 'UTF8', 'invalid Unicode scalar')
        size += 1 if n < 128 else 2 if n < 2048 else 3 if n < 65536 else 4
        if size > INPUT_BYTES:
            fail('program', 'schema', 'INPUT_BYTES', 'serialized input exceeds 32 MiB')
        if quoted:
            if escaped:
                escaped = False
            elif ch == '\\':
                escaped = True
            elif ch == '"':
                quoted = False
        elif ch == '"':
            quoted = True
        elif ch in '[{':
            depth += 1
            if depth > INPUT_DEPTH:
                fail('program', 'schema', 'INPUT_DEPTH', 'container depth exceeds 32')
        elif ch in ']}':
            depth -= 1
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail('program', 'schema', 'DUPLICATE_KEY', 'duplicate JSON object key')
            out[key] = value
        return out
    def integer(token):
        if len(token.lstrip('-')) > 20:
            fail('program', 'schema', 'INTEGER', 'integer token exceeds bounded domain')
        result = int(token)
        _validate_scalar(result)
        return result
    def noninteger(token):
        fail('program', 'schema', 'JSON', 'floating and nonfinite numbers are forbidden')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_int=integer,
                          parse_float=noninteger, parse_constant=noninteger)
    except ResourceError:
        raise
    except (ValueError, RecursionError) as error:
        fail('program', 'schema', 'JSON', 'malformed JSON: ' + str(error))


def preflight(program, budget):
    """Bounded raw-schema pass before constructing any analysis inventory.

    This walks only the already owned snapshot. Ordinary recursion is bounded by
    its container depth32; it creates no instruction/code/site inventory. Thus a
    10001st syntax occurrence cannot be masked by analysis-creation exhaustion.
    Declaration lexical resolution remains the subsequent scoped scan's job.
    """
    total_codes = len(mapping(program['functions'], 'functions')) + len(mapping(program['codes'], 'codes'))
    if total_codes > SITE_CODE_LIMIT:
        fail('program.sites_and_codes', 'schema', 'SITE_CODE_COUNT', 'combined code/site count exceeds 2048')
    instruction_count = site_count = 0
    allocating = frozenset(('alloc', 'closure', 'thunk', 'hole', 'application', 'application_borrow',
                           'scalar', 'prim2', 'construct_nullary', 'construct_sum'))
    def block(body, path, *, generic=False, introduction=False, entry=False):
        nonlocal instruction_count, site_count
        sequence(body, path)
        if not body:
            fail(path, 'schema', 'TERMINAL', 'empty body has no terminator')
        for index, instruction in enumerate(body):
            p = path + '[' + str(index) + ']'
            instruction_count += 1
            if instruction_count > INSTRUCTION_LIMIT:
                fail('program.instructions', 'schema', 'INSTRUCTION_COUNT', 'instruction count exceeds 10000')
            if type(instruction) is not dict or type(instruction.get('op')) is not str:
                fail(p, 'schema', 'SCHEMA', 'instruction requires string op')
            op = instruction['op']
            if op not in SCHEMAS:
                fail(p, 'schema', 'OPCODE', 'unknown Stage02 opcode')
            exact(instruction, ('op',) + SCHEMAS[op], p)
            if introduction:
                permitted, terminal = op in GENERIC_OPS or op == 'seal', op == 'seal'
            elif generic:
                permitted, terminal = op in GENERIC_OPS or op == 'return', op == 'return'
            else:
                permitted = op != 'seal' and (op != 'return' if entry else op not in ('finish', 'finish_scalar'))
                terminal = op in ('return', 'finish', 'finish_scalar')
            if not permitted:
                fail(p, 'schema', 'OPCODE', 'operation forbidden in lexical context')
            if terminal != (index == len(body) - 1):
                if terminal or index == len(body) - 1:
                    fail(p, 'schema', 'TERMINAL', 'one exact final terminator required')
            if 'out' in instruction:
                name(instruction['out'], p + '.out', binder=True)
            for field in ('in', 'ceiling', 'argument', 'left', 'right', 'condition', 'then', 'else', 'scrutinee', 'hole'):
                if field in instruction:
                    name(instruction[field], p + '.' + field)
            if 'value' in instruction and op != 'scalar':
                name(instruction['value'], p + '.value')
            if op in ('new_root', 'new_below'):
                for variable in sequence(instruction['imports'], p + '.imports'):
                    name(variable, p + '.imports')
            if op in ('application', 'application_borrow'):
                name(instruction['function'], p + '.function')
            if op == 'prim2':
                name(instruction['primitive'], p + '.primitive')
                if instruction['primitive'] not in PRIMITIVES:
                    fail(p, 'schema', 'PRIMITIVE', 'unknown primitive')
            if op == 'scalar':
                if instruction['kind'] not in ('i64', 'bool'):
                    fail(p, 'schema', 'SCALAR_KIND', 'unknown scalar kind')
                literal = instruction['value']
                if (instruction['kind'] == 'i64' and (type(literal) is not int or not -(1 << 63) <= literal < (1 << 63))) or (instruction['kind'] == 'bool' and type(literal) is not bool):
                    fail(p, 'schema', 'SCALAR_VALUE', 'wrong scalar value kind/range')
            if op in ('alloc', 'closure', 'thunk'):
                key = 'fields' if op == 'alloc' else 'captures'
                for slot, variable in mapping(instruction[key], p + '.' + key).items():
                    name(slot, p + '.' + key)
                    name(variable, p + '.' + key)
                if op != 'alloc':
                    name(instruction['function' if op == 'closure' else 'code'], p)
            if op == 'construct_sum':
                for variable in sequence(instruction['fields'], p + '.fields'):
                    name(variable, p + '.fields')
            if op in ('construct_sum', 'construct_nullary', 'case_i64', 'case_fields_i64'):
                family_name = name(instruction['family'], p + '.family')
                if family_name not in program['families']:
                    fail(p + '.family', 'schema', 'FAMILY', 'unknown declared family')
                family = program['families'][family_name]
                if op in ('construct_sum', 'construct_nullary'):
                    name(instruction['variant'], p + '.variant')
                    if instruction['variant'] not in family['variants']:
                        fail(p, 'schema', 'VARIANT', 'unknown declared variant')
                else:
                    arms = exact(instruction['arms'], family['variants'], p + '.arms')
                    for variant in family['variants']:
                        ap = p + '.arms.' + variant
                        if op == 'case_i64':
                            name(arms[variant], ap)
                            continue
                        arm = exact(arms[variant], ('code', 'captures'), ap)
                        name(arm['code'], ap + '.code')
                        captures = mapping(arm['captures'], ap + '.captures')
                        if len(captures) > CAPTURE_LIMIT:
                            fail(ap + '.captures', 'schema', 'CAPTURE_COUNT', 'factory captures exceed 64')
                        fields = externals = 0
                        for capture, binding in captures.items():
                            name(capture, ap + '.captures')
                            cp = ap + '.captures.' + capture
                            if type(binding) is not dict:
                                fail(cp, 'schema', 'CAPTURE_BINDING', 'expected tagged binding')
                            if binding.get('kind') == 'field':
                                exact(binding, ('kind', 'index'), cp)
                                field_index = binding['index']
                                if type(field_index) is not int or not 0 <= field_index < len(family['fields'][variant]):
                                    fail(cp, 'schema', 'FIELD_INDEX', 'field index outside variant')
                                fields += 1
                            elif binding.get('kind') == 'external':
                                exact(binding, ('kind', 'value'), cp)
                                name(binding['value'], cp + '.value')
                                externals += 1
                            else:
                                fail(cp, 'schema', 'CAPTURE_BINDING', 'unknown capture binding')
                        if fields > 32 or externals > 32:
                            fail(ap + '.captures', 'schema', 'FACTORY_CAPTURE_COUNT', 'field/external category exceeds 32')
                    if op == 'case_fields_i64':
                        site_count += len(family['variants'])
            if op == 'field':
                name(instruction['field'], p + '.field')
            if op in allocating:
                site_count += 1
            if total_codes + site_count > SITE_CODE_LIMIT:
                fail('program.sites_and_codes', 'schema', 'SITE_CODE_COUNT', 'combined code/site count exceeds 2048')
            if op == 'generalize':
                name(instruction['scheme'], p + '.scheme')
                block(instruction['body'], p + '.body', generic=True, introduction=True)
            if op == 'instantiate':
                name(instruction['instantiation'], p + '.instantiation')
    # Unicode ordering is deterministic; these are raw-schema cursors, not saved
    # analysis indexes. The bounded source maps already exist in the snapshot.
    for map_name in ('functions', 'codes'):
        for code_name in budget.ordered(program[map_name]):
            p = map_name + '.' + name(code_name, map_name)
            spec = program[map_name][code_name]
            fields = ('signature', 'parameter', 'captures', 'body', 'type_scope') if map_name == 'functions' else ('result', 'captures', 'body', 'type_scope')
            exact(spec, fields, p)
            if spec['type_scope'] is not None:
                name(spec['type_scope'], p + '.type_scope')
            captures = mapping(spec['captures'], p + '.captures')
            if len(captures) > CAPTURE_LIMIT:
                fail(p + '.captures', 'schema', 'CAPTURE_COUNT', 'code captures exceed 64')
            if map_name == 'functions':
                name(spec['signature'], p + '.signature')
                name(spec['parameter'], p + '.parameter', binder=True)
                if spec['parameter'] in captures:
                    fail(p + '.captures', 'schema', 'SCHEMA', 'capture shadows parameter')
            for capture, contract in captures.items():
                name(capture, p + '.captures', binder=True)
                exact(contract, ('layout', 'relation'), p + '.captures.' + capture)
                if contract['relation'] not in ('same', 'down', 'below'):
                    fail(p + '.captures.' + capture, 'schema', 'SCHEMA', 'unknown relation')
            block(spec['body'], p + '.body', generic=spec['type_scope'] is not None)
    block(program['entry'], 'entry', entry=True)
