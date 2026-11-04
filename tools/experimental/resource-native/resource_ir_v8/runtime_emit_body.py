"""Complete, fixed-template IR8 body planning. This module never runs C.

Every function, including dead Code, is mapped from the fresh owned raw body.
All declarations live in the enclosing C function. No existing emitter is used.
"""
from __future__ import annotations

from .runtime_emit_budget import (LIMITS, Writer, encode, exact, fail,
                                  plain_index, same, text_equal)

ABI_SHA256 = 'c6e3a34ea54b7f7224f94ece8a24a821d74e32d60db0a0fb16933252a2623500'
HELPERS = {
    'new_root': 'rt8_new_root', 'new_below': 'rt8_new_below', 'alloc': 'rt8_alloc',
    'closure': 'rt8_closure', 'thunk': 'rt8_thunk', 'hole': 'rt8_hole',
    'application': 'rt8_application', 'application_borrow': 'rt8_application_borrow',
    'fill': 'rt8_fill', 'borrow': 'rt8_borrow', 'end_borrow': 'rt8_end_borrow',
    'retain': 'rt8_retain', 'drop': 'rt8_drop', 'field': 'rt8_field',
    'force': 'rt8_force', 'return': 'rt8_return', 'finish': 'rt8_finish_entry',
    'scalar': None, 'prim2': 'rt8_prim2', 'finish_scalar': 'rt8_finish_scalar',
    'select_i64': 'rt8_select_i64', 'construct_nullary': 'rt8_construct_nullary',
    'construct_sum': 'rt8_construct_sum', 'case_i64': 'rt8_case_i64',
    'case_fields_i64': 'rt8_case_fields_i64', 'generalize': 'rt8_generic_begin',
    'seal': 'rt8_generic_seal', 'instantiate': 'rt8_instantiate',
}
_ALLOCATIONS = ('alloc', 'closure', 'thunk', 'hole', 'application',
                'application_borrow', 'scalar', 'prim2', 'construct_nullary', 'construct_sum')
_PRIMITIVES = {'addInt': 'RT8_PRIM_ADD_INT', 'subInt': 'RT8_PRIM_SUB_INT',
               'mulInt': 'RT8_PRIM_MUL_INT', 'eqInt': 'RT8_PRIM_EQ_INT', 'ltInt': 'RT8_PRIM_LT_INT'}
_ACCESSORS = {'site': ('const Rt8Site *', 'rt8_site'),
              'code': ('const Rt8Code *', 'rt8_code'),
              'intro': ('const Rt8Intro *', 'rt8_intro'),
              'use': ('const Rt8Instantiation *', 'rt8_instantiation'),
              'family': ('const Rt8Family *', 'rt8_family'),
              'variant': ('const Rt8Variant *', 'rt8_variant'),
              'shape': ('const Rt8Shape *', 'rt8_site_shape'),
              'label': ('const char *', 'rt8_label')}
_FACT_KEYS = ('role', 'capability', 'storage', 'node', 'group', 'kind', 'mode', 'anchor',
              'ticket', 'ready', 'view', 'type', 'scheme', 'projection', 'provenance', 'authority_source')
_AUTH_KEYS = ('capability', 'storage', 'group', 'mode', 'anchor', 'authority_source')
_TRANSFER_KEYS = ('capability', 'storage', 'node', 'group', 'kind', 'mode', 'anchor',
                  'ticket', 'ready', 'provenance', 'authority_source')


def path_key(path, b):
    exact(path, ('root', 'name', 'segments'), b, 'PATH')
    root, name, segments = path['root'], path['name'], path['segments']
    if root not in ('entry', 'function', 'thunk') or type(segments) is not list:
        fail('PATH', 'invalid path domain', schema=True)
    if (root == 'entry' and name is not None) or (root != 'entry' and type(name) is not str):
        fail('PATH', 'path name domain differs', schema=True)
    b.reserve(creation=5 + len(segments), work=1 + len(segments) + (len(name) if name else 0))
    for segment in segments:
        if not (type(segment) is int and segment >= 0) and segment != 'body':
            fail('PATH', 'invalid path segment', schema=True)
    return (root, name, tuple(segments))


def make_path(root, name, segments, b):
    b.scratch(3)
    return b.row(root=root, name=name, segments=b.listing(segments))


def raw_at(raw, path, b):
    path_key(path, b)
    if path['root'] == 'entry':
        value = raw['entry']
    else:
        bank = raw['functions'] if path['root'] == 'function' else raw['codes']
        value = b.get(bank, path['name'], 'PATH')['body']
    for segment in path['segments']:
        b.work()
        if segment == 'body':
            if type(value) is not dict or value.get('op') != 'generalize':
                fail('PATH', 'body segment does not enter a generalize')
            value = value['body']
        else:
            if type(value) is not list:
                fail('PATH', 'instruction index does not enter a body')
            value = value[plain_index(segment, len(value), 'PATH')]
    return value


def operand_name(inst, role, b):
    value = inst
    for segment in role:
        b.key_work(segment)
        if type(value) is dict:
            value = b.get(value, segment, 'OPERAND')
        elif type(value) is list:
            value = value[plain_index(segment, len(value), 'OPERAND')]
        else:
            fail('OPERAND', 'operand role does not resolve in raw')
    if type(value) is not str:
        fail('OPERAND', 'operand is not a raw binding name')
    return value


def expected_roles(inst, codes, raw, b):
    # Conservative fixed scratch covers all fixed role tuples in one branch.
    b.reserve(creation=64, work=64)
    roles = b.listing()
    op = inst['op']
    if 'family' in inst: b.key_work(inst['family'])
    if op == 'new_below': b.append(roles, b.listing(('ceiling',)))
    if op in ('new_root', 'new_below'):
        for index in range(len(inst['imports'])):
            b.creation(3); b.append(roles, b.listing(('imports', index)))
    elif op in _ALLOCATIONS or op in ('select_i64', 'case_i64', 'case_fields_i64', 'generalize'):
        b.append(roles, b.listing(('in',)))
        if op == 'generalize' and 'imports' in inst:
            for name in b.ordered(inst['imports']):
                b.creation(4); b.append(roles, b.listing(('imports', name, 'value')))
        elif op == 'alloc':
            for name in b.ordered(inst['fields']):
                b.creation(3); b.append(roles, b.listing(('fields', name)))
        elif op in ('closure', 'thunk'):
            target = b.get(inst, 'function' if op == 'closure' else 'code', 'OPERAND')
            b.creation(3)
            code = b.get(codes, ('function' if op == 'closure' else 'thunk', target), 'CODE_CENSUS')
            for capture in code['captures']:
                b.creation(3); b.append(roles, b.listing(('captures', capture['name'])))
        elif op in ('application', 'application_borrow'):
            b.append(roles, b.listing(('function',))); b.append(roles, b.listing(('argument',)))
        elif op == 'prim2':
            b.append(roles, b.listing(('left',))); b.append(roles, b.listing(('right',)))
        elif op == 'construct_sum':
            for index in range(len(inst['fields'])):
                b.creation(3); b.append(roles, b.listing(('fields', index)))
        elif op == 'select_i64':
            for name in ('condition', 'then', 'else'):
                b.creation(2); b.append(roles, b.listing((name,)))
        elif op in ('case_i64', 'case_fields_i64'):
            b.append(roles, b.listing(('scrutinee',)))
            for variant in b.get(raw['families'], inst['family'], 'OPERAND')['variants']:
                if op == 'case_i64':
                    b.key_work(variant)
                    b.creation(3); b.append(roles, b.listing(('arms', variant)))
                else:
                    b.key_work(variant)
                    arm = b.get(inst['arms'], variant, 'OPERAND')
                    b.creation(3)
                    code = b.get(codes, ('thunk', arm['code']), 'CODE_CENSUS')
                    for capture in code['captures']:
                        b.key_work(capture['name'])
                        binding = b.get(arm['captures'], capture['name'], 'OPERAND')
                        if binding['kind'] == 'external':
                            b.creation(6)
                            b.append(roles, b.listing(('arms', variant, 'captures', capture['name'], 'value')))
    elif op == 'fill':
        b.append(roles, b.listing(('hole',))); b.append(roles, b.listing(('value',)))
    elif op in ('borrow', 'end_borrow', 'retain', 'drop', 'field', 'force',
                'return', 'finish_scalar', 'seal', 'instantiate'):
        b.append(roles, b.listing(('value',)))
    return roles


class Planner:
    __slots__ = ('raw', 'meta', 'resource', 'b', 'code_names', 'functions', 'code_mapping',
                 'instruction_mapping', 'introductions', 'uses', 'frames', 'records',
                 'by_path', 'intro_start', 'intro_end', 'use_paths', 'families',
                 'variant_ids', 'label_set', 'label_rows', 'label_ids', 'entry_mapping')

    def __new__(cls, raw, meta, resource, budget):
        budget.creation(1 + len(cls.__slots__))
        return object.__new__(cls)

    def __init__(self, raw, meta, resource, budget):
        self.raw, self.meta, self.resource, self.b = raw, meta, resource, budget
        self.code_names, self.by_path = budget.mapping(), budget.mapping()
        self.intro_start, self.intro_end, self.use_paths = budget.mapping(), budget.mapping(), budget.mapping()
        self.families, self.variant_ids = budget.mapping(), budget.mapping()
        self.label_set, self.label_ids = budget.mapping(), budget.mapping()
        self.functions, self.code_mapping, self.instruction_mapping = budget.listing(), budget.listing(), budget.listing()
        self.introductions, self.uses, self.frames = budget.listing(), budget.listing(), budget.listing()
        self.records, self.label_rows = budget.listing(), budget.listing()
        self.entry_mapping = None

    def census(self):
        b, raw, m = self.b, self.raw, self.meta
        if len(m['codes']) != len(raw['functions']) + len(raw['codes']) or len(m['codes']) != len(self.resource['code_typing']):
            fail('CODE_CENSUS', 'complete declared Code census differs')
        b.creation(16)
        entry_path = make_path('entry', None, (), b)
        _, body_hash, _ = encode(raw['entry'], b)
        self.entry_mapping = b.row(body_path=entry_path, body_sha256=body_hash, symbol='rt8_entry')
        self.new_function(None, 'rt8_entry', raw['entry'], entry_path, None)
        for index, row in enumerate(m['codes']):
            b.reserve(creation=32, work=64)
            plain_index(row['id'], len(m['codes']), 'CODE_CENSUS')
            if row['id'] != index or row['kind'] not in ('function', 'thunk'):
                fail('CODE_CENSUS', 'Code ID/order/kind differs')
            bank = b.get(raw, 'functions' if row['kind'] == 'function' else 'codes', 'CODE_CENSUS')
            spec = b.get(bank, row['name'], 'CODE_CENSUS')
            key = (row['kind'], row['name'])
            b.key_work(row['name'])
            if b.contains(self.code_names, key): fail('CODE_CENSUS', 'duplicate Code declaration')
            b.put(self.code_names, key, row)
            body_path = make_path(row['kind'], row['name'], (), b)
            same(row['body_path'], body_path, b, 'PATH')
            same(raw_at(raw, row['body_path'], b), spec['body'], b, 'PATH')
            old = self.resource['code_typing'][index]
            for field in ('id', 'kind', 'name', 'body_path'):
                same(b.get(old, field, 'CODE_CENSUS'), b.get(row, field, 'CODE_CENSUS'), b, 'CODE_CENSUS')
            if row['scope'] is None:
                if spec['type_scope'] is not None: fail('CODE_CENSUS', 'Code scope lost')
            else:
                scope = m['schemes'][plain_index(row['scope'], len(m['schemes']), 'CODE_CENSUS')]
                text_equal(scope['name'], spec['type_scope'], b, 'CODE_CENSUS')
            captures = b.listing()
            names = b.ordered(spec['captures'])
            if len(names) != len(row['captures']): fail('CODE_CENSUS', 'capture census differs')
            for position, name in enumerate(names):
                text_equal(row['captures'][position]['name'], name, b, 'CODE_CENSUS')
                b.append(captures, name)
            symbol = b.symbol('rt8_body_', index)
            _, digest, _ = encode(spec['body'], b)
            b.scratch(9)
            mapping = b.row(id=index, kind=row['kind'], name=row['name'], scope=row['scope'],
                            body_path=row['body_path'], body_sha256=digest, symbol=symbol,
                            parameter=spec['parameter'] if row['kind'] == 'function' else None, captures=captures)
            b.append(self.code_mapping, mapping)
            self.new_function(index, symbol, spec['body'], body_path, mapping)
    def family_census(self):
        b, raw, m = self.b, self.raw, self.meta
        # Family and descriptor-domain variant references never use local variant
        # indices as flattened descriptor IDs. This belongs to the Site phase.
        variant_id = 0
        for family in m['families']:
            b.work()
            b.put(self.families, family['name'], family)
            variants = b.get(raw['families'], family['name'], 'SITE')['variants']
            if len(variants) != len(family['variants']): fail('SITE', 'family variant census differs')
            for index, variant in enumerate(family['variants']):
                b.creation(3)
                if variant['index'] != index: fail('SITE', 'family variant order differs')
                text_equal(variant['name'], variants[index], b, 'SITE')
                b.put(self.variant_ids, (family['id'], index), variant_id)
                variant_id += 1

    def new_function(self, code, symbol, body, path, mapping):
        b = self.b
        b.scratch(12)
        frame = b.row(code=code, symbol=symbol, body=body, path=path, mapping=mapping,
                      records=b.listing(), declarations=b.listing(), statements=b.listing(),
                      handles=0, vectors=0, accessors=0, scopes=0)
        b.append(self.functions, frame)

    def inventory(self):
        b = self.b
        resource_paths = b.mapping()
        for row in self.resource['instructions']:
            key = path_key(row['path'], b)
            if b.contains(resource_paths, key): fail('PATH', 'duplicate fresh resource instruction path')
            b.put(resource_paths, key, row)
        for frame in self.functions:
            b.creation(7)
            stack = [(frame['body'], 0, frame['path']['segments'])]
            while stack:
                body, index, prefix = stack.pop()
                if index == len(body): continue
                b.reserve(creation=5, work=64)
                stack.append((body, index + 1, prefix))
                segments = b.listing(prefix); b.append(segments, index)
                path = make_path(frame['path']['root'], frame['path']['name'], segments, b)
                key = path_key(path, b)
                if b.contains(self.by_path, key): fail('PATH', 'duplicate raw instruction path')
                inst = body[index]
                derived = b.get(resource_paths, key, 'PATH')
                text_equal(inst['op'], derived['op'], b, 'PATH')
                same(raw_at(self.raw, path, b), inst, b, 'PATH')
                roles = expected_roles(inst, self.code_names, self.raw, b)
                if len(roles) != len(derived['inputs']): fail('OPERAND', 'input census differs')
                names = b.listing()
                for pos, role in enumerate(roles):
                    fact = derived['inputs'][pos]
                    exact(fact, _FACT_KEYS, b, 'OPERAND')
                    same(fact['role'], role, b, 'OPERAND')
                    b.append(names, operand_name(inst, role, b))
                outputs = derived['outputs']
                if 'out' in inst:
                    extra = len(inst['imports']) if inst['op'] == 'generalize' and 'imports' in inst else 0
                    if len(outputs) != 1 + extra: fail('OPERAND', 'output census differs')
                    b.creation(2); same(outputs[0]['role'], ['out'], b, 'OPERAND')
                    if extra:
                        for pos, child in enumerate(b.ordered(inst['imports']), 1):
                            old, alias = derived['inputs'][pos], outputs[pos]
                            contract = b.get(inst['imports'], child, 'OPERAND')
                            exact(contract, ('value', 'layout', 'relation'), b, 'OPERAND')
                            reference = contract['layout']
                            if type(reference) is not str or not reference.startswith('^') or len(reference) < 2 or contract['relation'] != 'down':
                                fail('OPERAND', 'import needs an explicit Type and down relation')
                            b.key_work(reference); b.creation()
                            declared = b.get(self.raw['types'], reference[1:], 'OPERAND')
                            exact(declared, ('tag', 'layout'), b, 'OPERAND')
                            actual = self.resource['types'][plain_index(old['type'], len(self.resource['types']), 'OPERAND')]
                            if declared['tag'] != 'closed' or declared['layout'] not in ('#i64', '#bool') or actual['tag'] != 'closed':
                                fail('OPERAND', 'import Type must be an intrinsic scalar')
                            text_equal(declared['layout'], actual['atom'], b, 'OPERAND')
                            exact(alias, _FACT_KEYS, b, 'OPERAND')
                            b.creation(3); same(alias['role'], ['imports', child], b, 'OPERAND')
                            for field in _FACT_KEYS:
                                if field not in ('role', 'capability', 'storage'):
                                    same(old[field], alias[field], b, 'OPERAND')
                            if old['kind'] != 'value' or old['mode'] != 'own' or old['view'] != 'MONO' or old['ticket'] is not False or old['anchor'] is not None:
                                fail('OPERAND', 'import source is not a ticket-free MONO owner')
                            for field in ('capability', 'storage'):
                                if type(alias[field]) is not int or alias[field] < 0 or alias[field] == old[field]:
                                    fail('OPERAND', 'import acquisition needs fresh capability/storage')
                                for prior in derived['inputs']:
                                    b.work()
                                    if alias[field] == prior[field]: fail('OPERAND', 'import alias identity is not fresh')
                                for earlier in range(1, pos):
                                    b.work()
                                    if alias[field] == outputs[earlier][field]: fail('OPERAND', 'import alias identity is not fresh')
                elif inst['op'] == 'fill':
                    if len(outputs) != 1: fail('OPERAND', 'fill update census differs')
                    b.creation(2); same(outputs[0]['role'], ['hole'], b, 'OPERAND')
                elif outputs:
                    fail('OPERAND', 'non-output instruction has output facts')
                b.scratch(9)
                record = b.row(raw=inst, derived=derived, path=path, key=key, frame=frame,
                               roles=roles, names=names, sites=b.listing(), mapping=None)
                b.put(self.by_path, key, record)
                b.append(self.records, record); b.append(frame['records'], record)
                if inst['op'] == 'generalize':
                    child = b.listing(segments); b.append(child, 'body')
                    if len(stack) >= LIMITS['owned_json_depth']:
                        fail('SNAPSHOT_DEPTH', 'raw traversal exceeds depth64')
                    b.creation(5); stack.append((inst['body'], 0, child))
        if len(self.by_path) != len(resource_paths): fail('PATH', 'extra fresh resource instruction')

    def sites(self):
        b, m = self.b, self.meta
        self.family_census()
        seen = b.mapping()
        for record in self.records:
            inst = record['raw']; op = inst['op']
            expected = (len(b.get(self.raw['families'], inst['family'], 'SITE')['variants']) if op == 'case_fields_i64'
                        else 1 if op in _ALLOCATIONS else 0)
            ids = record['derived']['sites']
            if len(ids) != expected: fail('SITE', 'allocation Site/arm census differs')
            for arm, sid in enumerate(ids):
                row = m['sites'][plain_index(sid, len(m['sites']), 'SITE')]
                if type(row['id']) is not int or row['id'] != sid or b.contains(seen, sid):
                    fail('SITE', 'duplicate or misnumbered Site')
                same(row['path'], record['path'], b, 'SITE')
                same(row['arm'], arm if op == 'case_fields_i64' else None, b, 'SITE')
                if op in ('closure', 'thunk', 'case_fields_i64'):
                    if op == 'case_fields_i64':
                        variant = b.get(self.raw['families'], inst['family'], 'SITE')['variants'][arm]
                        target = b.get(inst['arms'], variant, 'OPERAND')['code']; kind = 'thunk'
                    else:
                        target = b.get(inst, 'function' if op == 'closure' else 'code', 'OPERAND')
                        kind = 'function' if op == 'closure' else 'thunk'
                    b.creation(3)
                    expected_code = b.get(self.code_names, (kind, target), 'SITE')['id']
                    same(row['code'], expected_code, b, 'SITE')
                elif row['code'] is not None:
                    fail('SITE', 'non-Code allocation carries Code')
                b.put(seen, sid, True); b.append(record['sites'], sid)
        if len(seen) != len(m['sites']): fail('SITE', 'unmapped Site remains')

    def intro_uses(self):
        b, m = self.b, self.meta
        for index, intro in enumerate(m['introductions']):
            b.reserve(creation=24, work=64)
            if type(intro['id']) is not int or intro['id'] != index: fail('INTRO', 'Intro ID differs')
            start = b.get(self.by_path, path_key(intro['generalize_path'], b), 'INTRO')
            end = b.get(self.by_path, path_key(intro['seal_path'], b), 'INTRO')
            if start['raw']['op'] != 'generalize' or end['raw']['op'] != 'seal':
                fail('INTRO', 'Intro boundary op differs')
            scheme = m['schemes'][plain_index(intro['scheme'], len(m['schemes']), 'INTRO')]
            text_equal(scheme['name'], start['raw']['scheme'], b, 'INTRO')
            prefix = b.listing(start['path']['segments']); b.append(prefix, 'body')
            b.append(prefix, len(start['raw']['body']) - 1)
            expected = make_path(start['path']['root'], start['path']['name'], prefix, b)
            same(expected, end['path'], b, 'INTRO')
            old = self.resource['introductions'][plain_index(index, len(self.resource['introductions']), 'INTRO')]
            same(old['result_sites'], intro['result_sites'], b, 'INTRO')
            same(old['generalize_path'], intro['generalize_path'], b, 'INTRO')
            same(old['seal_path'], intro['seal_path'], b, 'INTRO')
            if b.contains(self.intro_start, start['key']) or b.contains(self.intro_end, end['key']):
                fail('INTRO', 'duplicate Intro boundary')
            mapping = b.row(id=index, scheme=intro['scheme'], generalize_path=intro['generalize_path'],
                            seal_path=intro['seal_path'], result_sites=intro['result_sites'],
                            scope_token=None, export_expression=None)
            b.append(self.introductions, mapping)
            b.put(self.intro_start, start['key'], mapping); b.put(self.intro_end, end['key'], mapping)
        for record in self.records:
            op = record['raw']['op']
            if op == 'generalize' and not b.contains(self.intro_start, record['key']): fail('INTRO', 'unmapped generalize')
            if op == 'seal' and not b.contains(self.intro_end, record['key']): fail('INTRO', 'unmapped seal')
        if len(m['introductions']) != len(self.resource['introductions']): fail('INTRO', 'extra resource Intro')
        for index, use in enumerate(m['uses']):
            b.reserve(creation=24, work=64)
            if type(use['id']) is not int or use['id'] != index: fail('USE', 'Use ID differs')
            raw_use = b.get(self.raw['instantiations'], use['name'], 'USE')
            scheme = m['schemes'][plain_index(use['scheme'], len(m['schemes']), 'USE')]
            text_equal(raw_use['scheme'], scheme['name'], b, 'USE')
            env = m['environments'][plain_index(use['env'], len(m['environments']), 'USE')]
            same(env['arguments'], use['arguments'], b, 'USE')
            same(env['scheme'], use['scheme'], b, 'USE')
            if env['mode'] != 'CLOSED' or len(raw_use['arguments']) != len(use['arguments']):
                fail('USE', 'complete Use environment/vector differs')
            old = self.resource['uses'][plain_index(index, len(self.resource['uses']), 'USE')]
            same(old['occurrences'], use['occurrences'], b, 'USE')
            text_equal(old['name'], use['name'], b, 'USE')
            text_equal(old['scheme'], scheme['name'], b, 'USE')
            if len(old['arguments']) != len(use['arguments']):
                fail('USE', 'complete resource argument vector differs')
            for position, old_type in enumerate(old['arguments']):
                remap = m['type_remap'][plain_index(old_type, len(m['type_remap']), 'USE')]
                same(remap['resource_type'], old_type, b, 'USE')
                same(remap['metadata_type'], use['arguments'][position], b, 'USE')
            remap = m['type_remap'][plain_index(old['result_type'], len(m['type_remap']), 'USE')]
            same(remap['metadata_type'], use['result_type'], b, 'USE')
            mapped_env = None
            for remap in m['environment_remap']:
                b.work(1 + min(len(remap['resource_environment']), len(old['environment'])))
                if remap['resource_environment'] == old['environment']:
                    mapped_env = remap['environment']
            same(mapped_env, use['env'], b, 'USE')
            occurrences = b.listing()
            for path in use['occurrences']:
                key = path_key(path, b); record = b.get(self.by_path, key, 'USE')
                if record['raw']['op'] != 'instantiate': fail('USE', 'Use occurrence op differs')
                text_equal(record['raw']['instantiation'], use['name'], b, 'USE')
                if b.contains(self.use_paths, key): fail('USE', 'duplicate Use occurrence')
                b.put(self.use_paths, key, use)
                b.scratch(3)
                b.append(occurrences, b.row(path=path, source_expression=None, output_expression=None))
            b.scratch(7)
            b.append(self.uses, b.row(id=index, name=use['name'], scheme=use['scheme'],
                arguments=use['arguments'], env=use['env'], result_type=use['result_type'], occurrences=occurrences))
        for record in self.records:
            if record['raw']['op'] == 'instantiate' and not b.contains(self.use_paths, record['key']):
                fail('USE', 'unmapped instantiate')
        if len(m['uses']) != len(self.resource['uses']): fail('USE', 'extra resource Use')

    def helpers(self):
        b = self.b
        for record in self.records:
            inst = record['raw']; op = inst['op']
            helper = b.get(HELPERS, op, 'OPCODE')
            if op == 'scalar':
                if inst['kind'] not in ('i64', 'bool'): fail('OPCODE', 'scalar helper kind differs')
                helper = 'rt8_scalar_i64' if inst['kind'] == 'i64' else 'rt8_scalar_bool'
            b.reserve(creation=13, work=1)
            mapping = b.row(path=record['path'], op=op, code=record['frame']['code'], helper=helper,
                            inputs=b.listing(), output=None, sites=record['sites'], intro=None, use=None)
            if op == 'generalize': mapping['intro'] = b.get(self.intro_start, record['key'], 'INTRO')['id']
            elif op == 'seal': mapping['intro'] = b.get(self.intro_end, record['key'], 'INTRO')['id']
            elif op == 'instantiate': mapping['use'] = b.get(self.use_paths, record['key'], 'USE')['id']
            record['mapping'] = mapping
            b.append(self.instruction_mapping, mapping)

    def declaration(self, frame, ctype, name, count=None, zero=False):
        b = self.b
        b.scratch(4)
        b.append(frame['declarations'], b.row(c_type=ctype, name=name, count=count, zero=zero))

    def handle(self, frame):
        name = self.b.symbol('h', frame['handles'])
        frame['handles'] += 1
        self.declaration(frame, 'Rt8Handle *', name)
        return name

    def scope(self, frame):
        name = self.b.symbol('g', frame['scopes'])
        frame['scopes'] += 1
        self.declaration(frame, 'Rt8GenericScope ', name, zero=True)
        return name

    def call(self, frame, helper, args, target=None, returns=False, terminal=False):
        b = self.b
        b.scratch(6)
        b.append(frame['statements'], b.row(kind='call', helper=helper, arguments=args,
                                          target=target, returns=returns, terminal=terminal))

    def assign(self, frame, target, value):
        b = self.b
        b.scratch(3)
        b.append(frame['statements'], b.row(kind='assign', target=target, value=value))

    def accessor(self, frame, kind, value):
        b = self.b
        name = b.symbol('p', frame['accessors']); frame['accessors'] += 1
        ctype, helper = b.get(_ACCESSORS, kind, 'ABI')
        self.declaration(frame, ctype, name)
        b.creation(2)
        self.call(frame, helper, b.listing((value,)), target=name)
        return name

    def label(self, frame, value):
        b = self.b
        b.key_work(value)
        if not b.contains(self.label_set, value):
            if b.label_count >= LIMITS['label_count']:
                fail('LABEL_COUNT', 'distinct native labels exceed65536')
            if type(value) is not str or not value:
                fail('BINDING', 'native label must be nonempty Unicode text', schema=True)
            size = 1  # terminating NUL
            for char in value:
                b.work()
                n = ord(char)
                if n == 0 or 0xD800 <= n <= 0xDFFF:
                    fail('BINDING', 'invalid native label scalar', schema=True)
                size += 1 if n < 128 else 2 if n < 2048 else 3 if n < 65536 else 4
                if size > LIMITS['label_utf8_bytes'] - b.label_utf8_bytes:
                    fail('LABEL_BYTES', 'native label pool exceeds1MiB')
            b.label_count += 1; b.label_utf8_bytes += size
            b.creation(); data = bytearray()
            for char in value:
                b.reserve(creation=1, work=5)
                data.extend(char.encode('utf-8'))
            b.reserve(creation=1, work=len(data))
            b.put(self.label_set, value, bytes(data))
        b.scratch(1)
        return self.accessor(frame, 'label', b.row(label=value))

    def vector(self, frame, ctype, count, pointer_members):
        if not count: return 'NULL'
        name = self.b.symbol('v', len(frame['declarations']))
        frame['vectors'] += count * pointer_members
        self.declaration(frame, ctype, name, count=count)
        return name

    def element(self, name, index, field=None):
        b = self.b
        b.creation()  # dynamic prefix before passing it to symbol
        result = b.symbol(name + '[', index, ']')
        if field is not None:
            b.reserve(creation=2, work=2 * (len(result) + len(field) + 1))
            result = result + '.' + field
        return result

    def handle_vector(self, frame, values):
        name = self.vector(frame, 'Rt8Handle *', len(values), 1)
        for index, value in enumerate(values):
            self.b.work(); self.assign(frame, self.element(name, index), value)
        return name

    def binding(self, env, name, expression, fact=None, active=True):
        b = self.b
        b.key_work(name)
        if b.contains(env, name): fail('LIVENESS', 'raw binding reused in its lexical scope')
        b.scratch(3)
        b.put(env, name, b.row(expression=expression, fact=fact, active=active))

    def observe(self, env, name, fact):
        b = self.b
        binding = b.get(env, name, 'LIVENESS')
        if not binding['active']: fail('LIVENESS', 'instruction uses retired or unsealed binding')
        prior = binding['fact']
        if prior is not None:
            keys = _AUTH_KEYS if fact['kind'] == 'authority' or prior['kind'] == 'authority' else _FACT_KEYS
            for key in keys:
                if key != 'role': same(b.get(prior, key, 'LIVENESS'), b.get(fact, key, 'LIVENESS'), b, 'LIVENESS')
        if prior is None or (prior['kind'] == 'authority' and fact['kind'] != 'authority'):
            binding['fact'] = fact
        return binding['expression']

    def consume(self, env, name):
        binding = self.b.get(env, name, 'LIVENESS')
        if not binding['active'] or name == '$home':
            fail('LIVENESS', 'binding cannot be consumed')
        binding['active'] = False

    def finish_scope(self, env):
        for name, binding in env.items():
            self.b.key_work(name)
            if name != '$home' and binding['active']:
                fail('LIVENESS', 'live binding escapes its checked terminator')

    def lower(self):
        b = self.b
        for frame in self.functions:
            env, nested = b.mapping(), b.listing()
            mapping = frame['mapping']
            if mapping is not None:
                self.binding(env, '$home', 'home')
                if mapping['parameter'] is not None:
                    self.binding(env, mapping['parameter'], 'argument')
                for index, name in enumerate(mapping['captures']):
                    self.binding(env, name, b.symbol('captures[', index, ']'))
            for record in frame['records']:
                b.reserve(creation=48, work=128)  # fixed branch scratch/operand vectors
                inst, derived, outmap = record['raw'], record['derived'], record['mapping']
                op = inst['op']
                values = b.listing()
                for index, name in enumerate(record['names']):
                    expression = self.observe(env, name, derived['inputs'][index])
                    b.append(values, expression)
                    b.scratch(3)
                    b.append(outmap['inputs'], b.row(role=record['roles'][index], raw_name=name, c_expression=expression))
                target = None
                if 'out' in inst:
                    target = self.handle(frame)
                    b.scratch(2)
                    outmap['output'] = b.row(raw_name=inst['out'], c_expression=target)
                if op == 'generalize':
                    intro = b.get(self.intro_start, record['key'], 'INTRO')
                    token = self.scope(frame)
                    intro['scope_token'], intro['export_expression'] = token, target
                    self.binding(env, inst['out'], target, derived['outputs'][0], active=False)
                    b.creation(5); b.append(nested, (env, record, token))
                    intro_ref = self.accessor(frame, 'intro', intro['id'])
                    b.creation(); address = '&' + token
                    self.call(frame, outmap['helper'], b.listing((address, intro_ref, values[0])))
                    env = b.mapping(); self.binding(env, '$home', values[0])
                    if 'imports' in inst:
                        imports = b.listing()
                        for pos, child in enumerate(b.ordered(inst['imports']), 1):
                            alias = self.handle(frame)
                            self.call(frame, 'rt8_retain', b.listing((values[pos],)), target=alias)
                            self.binding(env, child, alias, derived['outputs'][pos])
                            b.append(imports, b.row(raw_name=child, c_expression=alias, input_index=pos, output_index=pos))
                        b.put(outmap, 'imports', imports)
                    continue
                if op == 'seal':
                    if not nested: fail('INTRO', 'seal has no active introduction')
                    parent, start, token = nested.pop()
                    intro = b.get(self.intro_end, record['key'], 'INTRO')
                    if b.get(self.intro_start, start['key'], 'INTRO') is not intro: fail('INTRO', 'seal closes a different introduction')
                    for key in _TRANSFER_KEYS:
                        same(b.get(derived['inputs'][0], key, 'LIVENESS'), b.get(start['derived']['outputs'][0], key, 'LIVENESS'), b, 'LIVENESS')
                    self.consume(env, inst['value']); self.finish_scope(env)
                    b.creation(); address = '&' + token
                    output_label = self.label(frame, start['raw']['out'])
                    self.call(frame, outmap['helper'], b.listing((address, values[0], output_label)), target=intro['export_expression'])
                    env = parent
                    b.get(env, start['raw']['out'], 'LIVENESS')['active'] = True
                    continue
                if op == 'fill':
                    previous, updated = derived['inputs'][0], derived['outputs'][0]
                    for key in _FACT_KEYS:
                        if key not in ('role', 'ticket'): same(b.get(previous, key, 'LIVENESS'), b.get(updated, key, 'LIVENESS'), b, 'LIVENESS')
                    if previous['ticket'] is not True or updated['ticket'] is not False:
                        fail('LIVENESS', 'fill must update only its original ticket')
                    b.get(env, inst['hole'], 'LIVENESS')['fact'] = updated
                if op == 'instantiate':
                    for key in _TRANSFER_KEYS:
                        same(b.get(derived['inputs'][0], key, 'LIVENESS'), b.get(derived['outputs'][0], key, 'LIVENESS'), b, 'LIVENESS')
                if op in ('drop', 'end_borrow', 'force', 'return', 'finish_scalar', 'instantiate'):
                    self.consume(env, inst['value'])
                elif op == 'select_i64':
                    self.consume(env, inst['then']); self.consume(env, inst['else'])
                elif op == 'case_i64':
                    for variant in b.get(self.raw['families'], inst['family'], 'SITE')['variants']:
                        self.consume(env, b.get(inst['arms'], variant, 'OPERAND'))
                if target is not None:
                    self.binding(env, inst['out'], target, derived['outputs'][0])
                self.operation(frame, record, values, target)
                if op in ('return', 'finish', 'finish_scalar'):
                    if nested: fail('LIVENESS', 'ordinary terminator inside generic scope')
                    self.finish_scope(env)
            if nested: fail('INTRO', 'unclosed generic scope')
        # Preserve the independently checked Use occurrence order, not entry-first
        # rendering order (the resource pass visits Code before entry).
        for use in self.uses:
            for occurrence in use['occurrences']:
                record = b.get(self.by_path, path_key(occurrence['path'], b), 'USE')
                occurrence['source_expression'] = record['mapping']['inputs'][0]['c_expression']
                occurrence['output_expression'] = record['mapping']['output']['c_expression']

    def operation(self, frame, record, values, target):
        b, raw = self.b, self.raw
        inst, mapping = record['raw'], record['mapping']
        op = inst['op']; helper = mapping['helper']
        if 'family' in inst: b.key_work(inst['family'])
        # All variable tuples in a fixed operation branch are covered before
        # construction. Variable-length arms/captures have per-element reserves.
        b.reserve(creation=128, work=128)
        site = self.accessor(frame, 'site', record['sites'][0]) if op in _ALLOCATIONS else None
        shape = self.accessor(frame, 'shape', site) if op in ('alloc', 'hole', 'scalar', 'prim2') else None
        label = self.label(frame, inst['out']) if op in _ALLOCATIONS or op in (
            'field', 'force', 'select_i64', 'case_i64', 'case_fields_i64', 'instantiate') else None
        args = b.listing()
        if op in ('new_root', 'new_below'):
            start = 1 if op == 'new_below' else 0
            b.creation(1 + len(values) - start)
            vector = self.handle_vector(frame, values[start:])
            if start: b.append(args, values[0])
            b.append(args, len(inst['imports'])); b.append(args, vector)
        elif op == 'alloc':
            b.creation(len(values)); vector = self.handle_vector(frame, values[1:])
            args = b.listing((values[0], site, shape, vector, label))
        elif op in ('closure', 'thunk'):
            code = self.accessor(frame, 'code', self.meta['sites'][record['sites'][0]]['code'])
            b.creation(len(values)); vector = self.handle_vector(frame, values[1:])
            args = b.listing((values[0], site, code, vector, label))
        elif op == 'hole': args = b.listing((values[0], site, shape, label))
        elif op in ('application', 'application_borrow'):
            args = b.listing((values[0], site, values[1], values[2], label))
        elif op == 'fill':
            hole_label, value_label = self.label(frame, inst['hole']), self.label(frame, inst['value'])
            args = b.listing((values[0], values[1], hole_label, value_label))
        elif op in ('borrow', 'end_borrow', 'retain', 'drop', 'return', 'finish_scalar'):
            args = b.listing((values[0],))
        elif op == 'field':
            type_id = plain_index(record['derived']['inputs'][0]['type'], len(self.resource['types']), 'OPERAND')
            ty = self.resource['types'][type_id]
            if ty['tag'] != 'closed' or not b.contains(raw['layouts'], ty['atom']):
                fail('OPERAND', 'field source lacks checked DATA type')
            fields = b.ordered(b.get(raw['layouts'], ty['atom'], 'OPERAND'))
            position = None
            for index, name in enumerate(fields):
                b.work(1 + min(len(name), len(inst['field'])))
                if name == inst['field']: position = index
            if position is None: fail('OPERAND', 'field is absent from checked DATA layout')
            source_label = self.label(frame, inst['value'])
            args = b.listing((values[0], position, label, source_label))
        elif op == 'force':
            args = b.listing((values[0], label, self.label(frame, inst['value'])))
        elif op == 'scalar':
            literal = inst['value']
            if inst['kind'] == 'bool':
                if type(literal) is not bool: fail('OPCODE', 'bool literal domain differs')
                literal = int(literal)
            elif type(literal) is not int or not -(1 << 63) <= literal < (1 << 63):
                fail('OPCODE', 'i64 literal domain differs')
            # A tagged integer forces portable INT64_C rendering, including MIN.
            b.scratch(1)
            scalar = b.row(i64=literal) if inst['kind'] == 'i64' else literal
            args = b.listing((values[0], site, shape, scalar, label))
        elif op == 'prim2':
            primitive = b.get(_PRIMITIVES, inst['primitive'], 'OPCODE')
            args = b.listing((values[0], site, primitive, shape, values[1], values[2], label))
        elif op == 'select_i64': args = b.listing((values[0], values[1], values[2], values[3], label))
        elif op in ('construct_nullary', 'construct_sum', 'case_i64', 'case_fields_i64'):
            family = b.get(self.families, inst['family'], 'SITE')
            family_ref = self.accessor(frame, 'family', family['id'])
            if op in ('construct_nullary', 'construct_sum'):
                index = None
                for variant in family['variants']:
                    b.work(1 + min(len(variant['name']), len(inst['variant'])))
                    if variant['name'] == inst['variant']: index = variant['index']
                if index is None: fail('SITE', 'constructor variant is absent')
                b.creation(3)
                variant_ref = self.accessor(frame, 'variant', b.get(self.variant_ids, (family['id'], index), 'SITE'))
                args = b.listing((values[0], site, family_ref, variant_ref))
                if op == 'construct_sum':
                    b.creation(len(values)); vector = self.handle_vector(frame, values[1:])
                    b.append(args, len(inst['fields'])); b.append(args, vector)
                b.append(args, label)
            else:
                vector = self.case_vector(frame, record, values, family)
                args = b.listing((values[0], family_ref, values[1], len(family['variants']), vector, label))
        elif op == 'instantiate':
            use = b.get(self.use_paths, record['key'], 'USE')
            use_ref = self.accessor(frame, 'use', use['id'])
            args = b.listing((values[0], use_ref, label, self.label(frame, inst['value'])))
        elif op != 'finish':
            fail('OPCODE', 'opcode lacks a real lowering template')
        self.call(frame, helper, args, target=target, returns=op == 'return', terminal=op in ('finish', 'finish_scalar'))

    def case_vector(self, frame, record, values, family):
        b = self.b
        inst = record['raw']; factory = inst['op'] == 'case_fields_i64'
        vector = self.vector(frame, 'Rt8FactoryArm ' if factory else 'Rt8CaseArm ',
                             len(family['variants']), 4 if factory else 2)
        external_index = 2
        for index, variant in enumerate(family['variants']):
            b.reserve(creation=32, work=64)
            variant_ref = self.accessor(frame, 'variant', b.get(self.variant_ids, (family['id'], index), 'SITE'))
            self.assign(frame, self.element(vector, index, 'variant'), variant_ref)
            if not factory:
                self.assign(frame, self.element(vector, index, 'value'), values[2 + index])
                continue
            b.key_work(variant['name'])
            arm = b.get(inst['arms'], variant['name'], 'OPERAND')
            sid = record['sites'][index]
            code = self.meta['codes'][self.meta['sites'][sid]['code']]
            site_ref = self.accessor(frame, 'site', sid)
            code_ref = self.accessor(frame, 'code', code['id'])
            captures = self.vector(frame, 'Rt8FactoryCapture ', len(code['captures']), 2)
            for position, capture in enumerate(code['captures']):
                b.reserve(creation=16, work=64)
                b.key_work(capture['name'])
                binding = b.get(arm['captures'], capture['name'], 'OPERAND')
                name_ref = self.label(frame, capture['name'])
                self.assign(frame, self.element(captures, position, 'name'), name_ref)
                self.assign(frame, self.element(captures, position, 'kind'),
                            'RT8_FACTORY_FIELD' if binding['kind'] == 'field' else 'RT8_FACTORY_EXTERNAL')
                self.assign(frame, self.element(captures, position, 'field_index'),
                            binding['index'] if binding['kind'] == 'field' else 0)
                self.assign(frame, self.element(captures, position, 'external'),
                            'NULL' if binding['kind'] == 'field' else values[external_index])
                if binding['kind'] == 'external': external_index += 1
            self.assign(frame, self.element(vector, index, 'site'), site_ref)
            self.assign(frame, self.element(vector, index, 'code'), code_ref)
            self.assign(frame, self.element(vector, index, 'capture_count'), len(code['captures']))
            self.assign(frame, self.element(vector, index, 'captures'), captures)
        if factory and external_index != len(values): fail('OPERAND', 'factory external operand census differs')
        return vector

    def frame_census(self):
        b = self.b
        for frame in self.functions:
            params = 1 if frame['code'] is None else 5
            # GenericScope contributes its four actual pointer members, while
            # full token storage/nonpointer members remain separately measured.
            locals_ = frame['handles'] + 4 * frame['scopes']
            total = params + locals_ + frame['vectors'] + frame['accessors']
            if total > LIMITS['frame_pointer_cells']:
                fail('FRAME_POINTER_CELLS', 'enclosing function exceeds512 pointer cells')
            b.scratch(10)
            b.append(self.frames, b.row(code=frame['code'], symbol=frame['symbol'],
                parameter_pointer_cells=params, local_pointer_cells=locals_,
                vector_pointer_cells=frame['vectors'], accessor_pointer_cells=frame['accessors'],
                pointer_cells=total, scope_token_count=frame['scopes'], handle_struct_cells=0,
                storage_strategy='heap-handles-enclosing-pointer-locals'))

    def labels(self):
        import hashlib
        b = self.b
        by_bytes = b.mapping()
        for text, data in self.label_set.items():
            b.put(by_bytes, data, text)
        offset = 0
        for data in b.ordered(by_bytes):
            b.reserve(creation=2, work=len(data) + 64)
            digest = hashlib.sha256(data).hexdigest()
            text = b.get(by_bytes, data, 'BINDING'); index = len(self.label_rows)
            b.scratch(5)
            b.append(self.label_rows, b.row(id=index, offset=offset, utf8_bytes=len(data), value=text, sha256=digest))
            b.put(self.label_ids, text, index)
            offset += len(data) + 1
        if offset != b.label_utf8_bytes or len(self.label_rows) != b.label_count:
            fail('LABEL_BYTES', 'native pool census differs')


def derive_plan(raw, metadata, resource, budget):
    result = Planner(raw, metadata, resource, budget)
    result.census()
    result.inventory()
    result.sites()
    result.intro_uses()
    result.helpers()
    result.lower()
    result.frame_census()
    result.labels()
    return result


def _expression(writer, value, plan):
    if type(value) is int:
        writer.number(value)
    elif type(value) is str:
        # Only private generated numeric/template expressions reach this branch.
        writer.ascii(value)
    elif type(value) is dict and len(value) == 1 and 'label' in value:
        writer.number(plan.b.get(plan.label_ids, value['label'], 'BINDING'))
    elif type(value) is dict and len(value) == 1 and 'i64' in value:
        number = value['i64']
        if number == -(1 << 63):
            writer.ascii('(-INT64_C(9223372036854775807) - INT64_C(1))')
        elif number < 0:
            writer.ascii('(-INT64_C('); writer.number(-number); writer.ascii('))')
        else:
            writer.ascii('INT64_C('); writer.number(number); writer.ascii(')')
    else:
        fail('ABI', 'invalid private source expression')


def _function(writer, frame, plan):
    writer.ascii('static void ' if frame['code'] is None else 'static Rt8Handle *')
    writer.ascii(frame['symbol'])
    if frame['code'] is None:
        writer.ascii('(Rt8Context *ctx)\n{\n')
    else:
        writer.ascii('(Rt8Context *ctx, Rt8Handle *home, Rt8Handle **captures, Rt8Handle *argument, const Rt8Env *env)\n{\n')
    for declaration in frame['declarations']:
        writer.ascii('    '); writer.ascii(declaration['c_type']); writer.ascii(declaration['name'])
        if declaration['count'] is not None:
            writer.ascii('['); writer.number(declaration['count']); writer.ascii(']')
        if declaration['zero']: writer.ascii(' = {0}')
        writer.ascii(';\n')
    if frame['code'] is not None:
        writer.ascii('    (void)home;\n    (void)captures;\n    (void)argument;\n    (void)env;\n')
    for statement in frame['statements']:
        plan.b.work()
        writer.ascii('    ')
        if statement['kind'] == 'assign':
            writer.ascii(statement['target']); writer.ascii(' = ')
            _expression(writer, statement['value'], plan); writer.ascii(';\n')
            continue
        if statement['returns']: writer.ascii('return ')
        elif statement['target'] is not None:
            writer.ascii(statement['target']); writer.ascii(' = ')
        writer.ascii(statement['helper']); writer.ascii('(ctx')
        for value in statement['arguments']:
            writer.ascii(', '); _expression(writer, value, plan)
        writer.ascii(');\n')
        if statement['terminal']: writer.ascii('    return;\n')
    writer.ascii('}\n\n')


def _member(writer, ctype, name, count):
    writer.ascii('    '); writer.ascii(ctype); writer.ascii(' '); writer.ascii(name)
    if count is not None:
        writer.ascii('['); writer.number(count); writer.ascii(']')
    writer.ascii(';\n')


def _offset(writer, name, present):
    if not present: writer.ascii('UINT32_MAX')
    else:
        writer.ascii('(uint32_t)offsetof(struct Ir8Runtime_generated_v1, ')
        writer.ascii(name); writer.ascii(')')


def _digest(writer, digest, b):
    if type(digest) is not str or len(digest) != 64:
        fail('BINDING', 'digest is not lowercase SHA256')
    for char in digest:
        b.work()
        if char not in '0123456789abcdef': fail('BINDING', 'digest is not lowercase SHA256')
    writer.ascii('{ .bytes = {')
    for index in range(0, 64, 2):
        if index: writer.ascii(',')
        b.reserve(creation=1, work=2)
        writer.number(int(digest[index:index + 2], 16))
    writer.ascii('} }')


def render_sources(plan, bindings):
    b = plan.b
    header, source = Writer(b, 'source'), Writer(b, 'source')
    code_count, label_count, pool_bytes = len(plan.code_mapping), len(plan.label_rows), b.label_utf8_bytes
    header.ascii('#ifndef IR8_RUNTIME_GENERATED_H\n#define IR8_RUNTIME_GENERATED_H\n')
    header.ascii('#include "rir8_runtime.h"\n#include "ir8_packet_generated.h"\n\n')
    header.ascii('struct Ir8Runtime_generated_v1 {\n')
    _member(header, 'Rt8BindingHeader', 'header', None)
    if code_count: _member(header, 'Rt8Code', 'codes', code_count)
    if label_count: _member(header, 'uint32_t', 'label_offsets', label_count)
    if pool_bytes: _member(header, 'unsigned char', 'label_bytes', pool_bytes)
    header.ascii('};\n\nRt8Program ir8_runtime_generated_program(void);\n')
    header.ascii('const Ir8PacketExpectedBindings *ir8_runtime_generated_expected_bindings(void);\n#endif\n')
    source.ascii('#include "ir8_runtime_generated.h"\n#include <stddef.h>\n#include <stdint.h>\n\n')
    source.ascii('_Static_assert(sizeof(struct Ir8Runtime_generated_v1) <= UINT32_MAX, "binding size");\n')
    source.ascii('_Static_assert(_Alignof(struct Ir8Runtime_generated_v1) <= UINT32_MAX, "binding alignment");\n')
    source.ascii('_Static_assert(sizeof(struct Ir8Packet_generated_v1) <= UINT32_MAX, "packet size");\n')
    source.ascii('_Static_assert(_Alignof(struct Ir8Packet_generated_v1) <= UINT32_MAX, "packet alignment");\n')
    source.ascii('_Static_assert(sizeof(struct Ir8Runtime_generated_v1) <= RT8_MAX_STATIC_BYTES && sizeof(struct Ir8Packet_generated_v1) <= RT8_MAX_STATIC_BYTES - sizeof(struct Ir8Runtime_generated_v1), "complete two-root static budget");\n')
    b.creation(13)  # outer tuple and three variable-containing pair tuples
    for name, present in (('codes', code_count), ('label_offsets', label_count), ('label_bytes', pool_bytes)):
        if present:
            source.ascii('_Static_assert(offsetof(struct Ir8Runtime_generated_v1, ')
            source.ascii(name); source.ascii(') <= UINT32_MAX, "member offset");\n')
    source.ascii('\n')
    for frame in plan.functions:
        _function(source, frame, plan)
    source.ascii('static const struct Ir8Runtime_generated_v1 ir8_runtime_generated_root = {\n    .header = {\n')
    source.ascii('        .magic = {73,82,56,66,73,78,68,0},\n        .abi_revision = 1,\n        .purpose = 1,\n')
    source.ascii('        .binding_bytes = (uint32_t)sizeof(struct Ir8Runtime_generated_v1),\n')
    source.ascii('        .binding_alignment = (uint32_t)_Alignof(struct Ir8Runtime_generated_v1),\n')
    source.ascii('        .packet_bytes = (uint32_t)sizeof(struct Ir8Packet_generated_v1),\n')
    source.ascii('        .packet_alignment = (uint32_t)_Alignof(struct Ir8Packet_generated_v1),\n')
    source.ascii('        .code_offset = '); _offset(source, 'codes', code_count); source.ascii(',\n')
    source.ascii('        .code_count = '); source.number(code_count); source.ascii(',\n')
    source.ascii('        .label_index_offset = '); _offset(source, 'label_offsets', label_count); source.ascii(',\n')
    source.ascii('        .label_count = '); source.number(label_count); source.ascii(',\n')
    source.ascii('        .label_bytes_offset = '); _offset(source, 'label_bytes', pool_bytes); source.ascii(',\n')
    source.ascii('        .label_bytes = '); source.number(pool_bytes); source.ascii(',\n')
    source.ascii('        .runtime_total_static_bytes = (uint32_t)(sizeof(struct Ir8Packet_generated_v1) + sizeof(struct Ir8Runtime_generated_v1)),\n')
    source.ascii('        .expected = { .digests = {')
    for index, digest in enumerate(bindings):
        if index: source.ascii(',')
        _digest(source, digest, b)
    source.ascii('} },\n        .entry = rt8_entry\n    }')
    if code_count:
        source.ascii(',\n    .codes = {\n')
        for index, row in enumerate(plan.code_mapping):
            if index: source.ascii(',\n')
            source.ascii('        { .code_id = '); source.number(index)
            source.ascii(', .body = '); source.ascii(row['symbol']); source.ascii(' }')
        source.ascii('\n    }')
    if label_count:
        source.ascii(',\n    .label_offsets = {')
        for index, row in enumerate(plan.label_rows):
            if index: source.ascii(',')
            source.number(row['offset'])
        source.ascii('}')
    if pool_bytes:
        source.ascii(',\n    .label_bytes = {')
        first = True
        for row in plan.label_rows:
            data = b.get(plan.label_set, row['value'], 'BINDING')
            for value in data:
                if not first: source.ascii(',')
                source.number(value); first = False
            if not first: source.ascii(',')
            source.number(0); first = False
        source.ascii('}')
    source.ascii('\n};\n\n')
    # Fixed getter census: the wrapper has two pointers and two size_t fields;
    # no static object and no entry/Code frames row is created for this getter.
    source.ascii('Rt8Program ir8_runtime_generated_program(void)\n{\n    Rt8Program program;\n')
    source.ascii('    program.packet = ir8_packet_generated_data();\n    program.packet_bytes = ir8_packet_generated_size();\n')
    source.ascii('    program.binding = &ir8_runtime_generated_root;\n    program.binding_bytes = sizeof(ir8_runtime_generated_root);\n    return program;\n}\n\n')
    source.ascii('const Ir8PacketExpectedBindings *ir8_runtime_generated_expected_bindings(void)\n{\n    return &ir8_runtime_generated_root.header.expected;\n}\n')
    htext, hhash, hsize = header.finish()
    ctext, chash, csize = source.finish()
    b.creation(7)
    return htext, ctext, hhash, chash, hsize, csize
