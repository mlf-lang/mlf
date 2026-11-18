"""Host-only physical descriptor plans and lawful allocation classes.

Everything here is derived from the invocation's fresh Stage02 artifact and raw
snapshot. OPEN is an origin policy, not a free-variable-count optimization.
"""
from __future__ import annotations

from .metadata_budget import fail

TABLES = ('codes', 'code_executions', 'shapes', 'shape_typing', 'representations',
          'nominal_fields', 'families', 'representation_resolutions', 'sites',
          'site_executions', 'introductions', 'uses')
_KIND_READY = {'I64': 'scalar', 'BOOL': 'scalar', 'DATA': 'data', 'SUM': 'sum', 'REPEAT': 'function'}
_CATEGORY_READY = {'DATA': 'data', 'SUM': 'sum', 'SCALAR': 'scalar', 'CLOSURE': 'function'}
_MODE_ORIGIN = {'CONCRETE': 'CONCRETE', 'NEUTRAL': 'GENERIC', 'CLOSED': 'INSTANCE'}


def key2(budget, first, second):
    budget.creation()  # fixed-arity lookup record
    return (first, second)


def key3(budget, first, second, third):
    budget.creation()
    return (first, second, third)


def access_key(budget, site, origin, mode, use, scheme):
    budget.creation()
    return (site, origin, mode, use, scheme)


def path_key(path, budget):
    budget.work(1 + len(path['segments']))
    budget.creation()  # fixed root/name/segments record
    return (path['root'], path['name'], budget.tuple(path['segments']))


def instruction_at(raw, path, budget):
    """Resolve a checked path again, never an SSA display-name guess."""
    budget.work()
    root = path['root']
    if root == 'entry' and path['name'] is None:
        current = raw['entry']
    elif root in ('function', 'thunk'):
        bank = raw['functions' if root == 'function' else 'codes']
        if path['name'] not in bank:
            fail('metadata.sites', 'metadata-origin', 'PATH', 'unknown callback path')
        current = bank[path['name']]['body']
    else:
        fail('metadata.sites', 'metadata-origin', 'PATH', 'invalid path root')
    for segment in path['segments']:
        budget.work()
        if type(segment) is int and type(current) is list and 0 <= segment < len(current):
            current = current[segment]
        elif segment == 'body' and type(current) is dict and current.get('op') == 'generalize':
            current = current['body']
        else:
            fail('metadata.sites', 'metadata-origin', 'PATH', 'path does not resolve in raw syntax')
    if type(current) is not dict or 'op' not in current:
        fail('metadata.sites', 'metadata-origin', 'PATH', 'instruction path required')
    return current


def fact_at(instruction, role, budget, side='inputs'):
    found = None
    for fact in instruction[side]:
        budget.work()
        matches = (len(fact['role']) == 1 and fact['role'][0] == role) if type(role) is str else fact['role'] == role
        if matches:
            if found is not None:
                fail('metadata.sites', 'metadata-origin', 'FACT', 'duplicate checked operand role')
            found = fact
    if found is None:
        fail('metadata.sites', 'metadata-origin', 'FACT', 'missing checked operand role')
    return found


class RepresentationClosure:
    """Invocation-local mutable construction state; never returned to a caller."""
    __slots__ = ('raw', 'derived', 'types', 'budget', 'tables', 'legacy', 'canonical',
                 'opened', 'code_execution', 'site_executions', 'instruction_ids',
                 'site_instruction', 'intro_instructions', 'use_instructions')

    def __init__(self, raw, derived, types, budget):
        self.raw, self.derived, self.types, self.budget = raw, derived, types, budget
        budget.creation(1 + 2 * len(TABLES))  # temporary table-map and empty arrays
        self.tables = budget.row(**{name: [] for name in TABLES})
        budget.creation(9)  # invocation-local map headers
        self.legacy, self.canonical, self.opened = {}, {}, {}
        self.code_execution, self.site_executions = {}, {}
        self.instruction_ids, self.site_instruction = {}, {}
        self.intro_instructions, self.use_instructions = {}, {}
        for index, instruction in enumerate(derived['instructions']):
            budget.work()
            actual = instruction_at(raw, instruction['path'], budget)
            if actual['op'] != instruction['op']:
                fail('metadata.sites', 'metadata-origin', 'PATH', 'raw opcode differs from checked path')
            budget.put(self.instruction_ids, path_key(instruction['path'], budget), index)
            for site in instruction['sites']:
                budget.work()
                if type(site) is not int or not 0 <= site < len(derived['sites']) or site in self.site_instruction:
                    fail('metadata.sites', 'metadata-origin', 'SITE', 'site membership is not a bijection')
                budget.put(self.site_instruction, site, index)
        if len(self.site_instruction) != len(derived['sites']):
            fail('metadata.sites', 'metadata-origin', 'SITE', 'allocation site has no actual instruction')

    def add(self, table, **fields):
        rows = self.tables[table]
        return self.budget.record_append(rows, id=len(rows), **fields)

    def code_rows(self):
        b, t = self.budget, self.types
        for old in self.derived['code_typing']:
            b.work()
            kind, name = old['kind'], old['name']
            spec = self.raw['functions' if kind == 'function' else 'codes'][name]
            scope = None if spec['type_scope'] is None else t.scheme_map[spec['type_scope']]
            callable_type = t.reference('@' + spec['signature'], scope) if kind == 'function' else None
            arrow = t.tables['types'][callable_type] if callable_type is not None else None
            argument = arrow['argument'] if arrow is not None else None
            result = arrow['result'] if arrow is not None else t.reference(spec['result'], scope)
            if (old['id'] != len(self.tables['codes']) or old['type_scope'] != spec['type_scope']
                    or (None if old['callable_type'] is None else t.old(old['callable_type'])) != callable_type
                    or (None if old['argument'] is None else t.old(old['argument'])) != argument
                    or t.old(old['result']) != result):
                fail('metadata.codes', 'metadata-origin', 'CODE', 'fresh code interface differs from raw declaration')
            b.creation()
            captures = []
            for capture in b.ordered(spec['captures']):
                b.work()
                contract = spec['captures'][capture]
                b.record_append(captures, name=capture, type=t.reference(contract['layout'], scope), relation=contract['relation'])
            b.work(len(captures))
            if len(old['captures']) != len(captures) or any(
                    x['name'] != y['name'] or t.old(x['type']) != y['type'] or x['relation'] != y['relation']
                    for x, y in zip(old['captures'], captures)):
                fail('metadata.codes', 'metadata-origin', 'CODE', 'capture interface differs from fresh declaration')
            row = self.add('codes', kind=kind, name=name, scope=scope,
                           callable_type=callable_type, argument=argument, result=result,
                           captures=captures, body_path=b.clone(old['body_path']),
                           expected_protocol=None if arrow is None else arrow['protocol'],
                           expected_identity_flag=int(arrow is not None and arrow['result_identity'] == 'argument'))
            if row['body_path'] != b.row(root=kind, name=name, segments=b.listing(())):
                fail('metadata.codes', 'metadata-origin', 'PATH', 'callback body path differs')
            for env in t.envs_for_scope(scope):
                b.work()
                b.creation()
                resolved_captures = []
                for capture in captures:
                    b.work()
                    b.record_append(resolved_captures, name=capture['name'],
                                    type=t.resolve(capture['type'], env), relation=capture['relation'])
                execution = self.add('code_executions', code=row['id'], env=env,
                    callable_type=None if callable_type is None else t.resolve(callable_type, env),
                    argument=None if argument is None else t.resolve(argument, env),
                    result=t.resolve(result, env), captures=resolved_captures)
                b.put(self.code_execution, key2(b, row['id'], env), execution['id'])

    def intro_use_rows(self):
        b, t, d = self.budget, self.types, self.derived
        for old in d['introductions']:
            b.work()
            scheme = t.scheme_map[old['scheme']]
            start = self.instruction_ids[path_key(old['generalize_path'], b)]
            end = self.instruction_ids[path_key(old['seal_path'], b)]
            generalize = instruction_at(self.raw, old['generalize_path'], b)
            seal = instruction_at(self.raw, old['seal_path'], b)
            if generalize['op'] != 'generalize' or generalize['scheme'] != old['scheme'] or seal['op'] != 'seal':
                fail('metadata.introductions', 'metadata-origin', 'INTRO', 'incorrect introduction instruction association')
            fact = fact_at(d['instructions'][end], 'value', b)
            provenance = fact['provenance']
            if type(provenance) is not int or not 0 <= provenance < len(d['provenance']):
                fail('metadata.introductions', 'metadata-origin', 'INTRO', 'seal lacks allocated provenance')
            value = d['provenance'][provenance]['value']
            if value['kind'] != 'allocated' or value['context'] != b.row(kind='introduction', intro=old['id']):
                fail('metadata.introductions', 'metadata-origin', 'INTRO', 'seal is not its own neutral allocated result')
            b.creation()
            result_sites = b.listing((value['site'],))
            if old['result_sites'] != result_sites or t.old(fact['type']) != t.tables['schemes'][scheme]['body']:
                fail('metadata.introductions', 'metadata-origin', 'INTRO', 'seal result-site or complete body equation differs')
            if old['container'] is None:
                container = b.row(kind='entry')
                if old['generalize_path']['root'] != 'entry':
                    fail('metadata.introductions', 'metadata-origin', 'INTRO', 'entry introduction has a callback path')
            else:
                code = self.tables['codes'][old['container']]
                container = b.row(kind='code', code=code['id'])
                if (code['scope'] is not None or old['generalize_path']['root'] != code['kind']
                        or old['generalize_path']['name'] != code['name']):
                    fail('metadata.introductions', 'metadata-origin', 'INTRO', 'introduction needs its enclosing concrete callback')
            row = self.add('introductions', scheme=scheme, container=container,
                generalize_path=b.clone(old['generalize_path']), seal_path=b.clone(old['seal_path']),
                body_type=t.tables['schemes'][scheme]['body'], result_sites=result_sites)
            if row['id'] != old['id'] or t.tables['schemes'][scheme]['intro'] != row['id']:
                fail('metadata.introductions', 'metadata-origin', 'INTRO', 'scheme introduction identity differs')
            b.creation()  # source pair for immutable membership copy
            b.put(self.intro_instructions, row['id'], b.tuple((start, end)))
        for old in d['uses']:
            b.work()
            spec = self.raw['instantiations'][old['name']]
            scheme = t.scheme_map[spec['scheme']]
            env = t.env_map[old['environment']]
            actual_env = t.tables['environments'][env]
            b.creation()
            arguments = []
            for name in spec['arguments']:
                b.work()
                b.append(arguments, t.reference('^' + name))
            if (actual_env['scheme'] != scheme or actual_env['mode'] != 'CLOSED'
                    or actual_env['arguments'] != arguments):
                fail('metadata.uses', 'metadata-origin', 'USE', 'use lost its exact complete vector')
            body = t.tables['schemes'][scheme]['body']
            result = t.resolve(body, env)
            if result != t.old(old['result_type']):
                fail('metadata.uses', 'metadata-type', 'USE', 'use result equation differs')
            b.creation(2)
            occurrences, indices = [], []
            for index, inst in enumerate(d['instructions']):
                b.work()
                if inst['op'] == 'instantiate':
                    actual = instruction_at(self.raw, inst['path'], b)
                    if actual['instantiation'] == old['name']:
                        b.append(occurrences, b.clone(inst['path']))
                        b.append(indices, index)
            if occurrences != old['occurrences'] or not occurrences:
                fail('metadata.uses', 'metadata-origin', 'USE', 'use occurrences differ from raw instructions')
            row = self.add('uses', name=old['name'], scheme=scheme,
                           arguments=b.listing(arguments), env=env, result_type=result, occurrences=occurrences)
            b.put(self.use_instructions, row['id'], b.tuple(indices))

    def shape_rows(self):
        b, t, raw = self.budget, self.types, self.raw
        legacy_refs = b.listing(('#i64', '#bool'))
        for name in raw['layouts']:
            b.work(); b.append(legacy_refs, name)
        for name in raw['families']:
            b.work(); b.append(legacy_refs, '%' + name)
        for name in raw['signatures']:
            b.work()
            ty = t.references['@' + name]
            if t.closed(ty):
                b.append(legacy_refs, '@' + name)
        for reference in b.ordered(legacy_refs):
            b.work()
            ty = t.reference(reference)
            if reference == '#i64': kind = 'I64'
            elif reference == '#bool': kind = 'BOOL'
            elif reference.startswith('@'): kind = 'REPEAT'
            elif reference.startswith('%'): kind = 'SUM'
            else: kind = 'DATA'
            row = self.add('shapes', source=b.row(kind='legacy', reference=reference),
                           kind=kind, argument_rep=None, result_rep=None)
            b.put(self.legacy, reference, row['id'])
        for ty in t.tables['types']:
            b.work()
            if ty['tag'] == 'arrow' and t.closed(ty['id']):
                row = self.add('shapes', source=b.row(kind='canonical-arrow', type=ty['id']),
                               kind='REPEAT', argument_rep=None, result_rep=None)
                b.put(self.canonical, ty['id'], row['id'])
            elif ty['tag'] == 'closed':
                b.put(self.canonical, ty['id'], self.legacy[ty['atom']])
        b.creation()
        open_keys = set()
        for resolution in t.tables['type_resolutions']:
            b.work()
            env = t.tables['environments'][resolution['env']]
            ty = t.tables['types'][resolution['type']]
            if env['mode'] == 'NEUTRAL' and ty['tag'] in ('arrow', 'rigid'):
                b.add(open_keys, key2(b, env['scheme'], ty['id']))
        for scheme, ty in b.ordered(open_keys):
            b.work()
            row = self.add('shapes', source=b.row(kind='scoped-open', scheme=scheme, type=ty),
                           kind='OPEN', argument_rep=None, result_rep=None)
            b.put(self.opened, key2(b, scheme, ty), row['id'])
        for shape in self.tables['shapes']:
            b.work()
            source = shape['source']
            scope = source['scheme'] if source['kind'] == 'scoped-open' else None
            ty = t.reference(source['reference']) if source['kind'] == 'legacy' else source['type']
            type_row = t.tables['types'][ty]
            if shape['kind'] == 'REPEAT':
                if type_row['tag'] != 'arrow' or type_row['protocol'] != 'repeat' or not t.closed(ty):
                    fail('metadata.shapes', 'metadata-representation', 'SHAPE', 'Repeat needs its complete closed Repeat contract')
                if source['kind'] == 'legacy':
                    spec = raw['signatures'][source['reference'][1:]]
                    shape['argument_rep'] = self.declared_rep(spec['argument'])
                    shape['result_rep'] = self.declared_rep(spec['result'])
                else:
                    shape['argument_rep'] = self.canonical[type_row['argument']]
                    shape['result_rep'] = self.canonical[type_row['result']]
            contract = t.contracts[ty] if type_row['tag'] == 'arrow' else None
            self.add('shape_typing', shape=shape['id'], type=ty, scope=scope, contract=contract)
            ready = _KIND_READY.get(shape['kind'])
            if shape['kind'] == 'OPEN':
                ready = 'function' if type_row['tag'] == 'arrow' else 'none'
                if type_row['tag'] not in ('arrow', 'rigid') or scope is None:
                    fail('metadata.shapes', 'metadata-representation', 'OPEN', 'OPEN must be a scoped arrow or rigid')
            self.add('representations', shape=shape['id'], typing=shape['id'], ready_kind=ready)
        for old in t.tables['type_resolutions']:
            b.work(); b.rows()
            env = t.tables['environments'][old['env']]
            ty = t.tables['types'][old['type']]
            if env['mode'] == 'NEUTRAL' and ty['tag'] in ('arrow', 'rigid'):
                representation = self.opened[key2(b, env['scheme'], old['type'])]
            else:
                representation = self.canonical[old['result']]
            self.add('representation_resolutions', type=old['type'], env=old['env'], representation=representation)
        for layout in b.ordered(raw['layouts']):
            b.work()
            shape = self.legacy[layout]
            for position, name in enumerate(b.ordered(raw['layouts'][layout])):
                b.work()
                reference = raw['layouts'][layout][name]
                self.add('nominal_fields', shape=shape, variant=None, position=position, name=name,
                         type=t.reference(reference), declared_rep=self.declared_rep(reference))
        # Shape order, rather than declaration category, owns field ordering.
        for family in b.ordered(raw['families']):
            b.work()
            shape = self.legacy['%' + family]
            for variant, name in enumerate(raw['families'][family]['variants']):
                b.work()
                for position, reference in enumerate(raw['families'][family]['fields'][name]):
                    b.work()
                    self.add('nominal_fields', shape=shape, variant=variant, position=position, name=str(position),
                             type=t.reference(reference), declared_rep=self.declared_rep(reference))
        fields = b.ordered(self.tables['nominal_fields'], key=lambda f: (f['shape'], -1 if f['variant'] is None else f['variant'], f['position']), key_units=4)
        self.tables['nominal_fields'] = fields
        for index, field in enumerate(fields):
            b.work(); field['id'] = index
        for name in b.ordered(raw['families']):
            b.work()
            shape = self.legacy['%' + name]
            b.creation()
            variants = []
            for index, variant in enumerate(raw['families'][name]['variants']):
                b.work()
                b.creation()
                ids = []
                for field in fields:
                    b.work()
                    if field['shape'] == shape and field['variant'] == index:
                        b.append(ids, field['id'])
                b.record_append(variants, name=variant, index=index, fields=ids)
            self.add('families', name=name, shape=shape, variants=variants)

    def declared_rep(self, reference):
        self.budget.work()
        ty = self.types.reference(reference)
        if reference in self.legacy:
            return self.legacy[reference]
        return self.canonical[ty]

    def default_rep(self, ty, env):
        self.budget.work()
        erow = self.types.tables['environments'][env]
        if erow['mode'] == 'NEUTRAL' and self.types.tables['types'][ty]['tag'] in ('arrow', 'rigid'):
            return self.opened[key2(self.budget, erow['scheme'], ty)]
        return self.canonical[self.types.resolve(ty, env)]

    def site_rows(self):
        b, t, d = self.budget, self.types, self.derived
        b.creation()
        contexts = {}
        for item in d['provenance']:
            b.work()
            value = item['value']
            if value['kind'] == 'allocated':
                site = value['site']
                context = b.clone(value['context'])
                if context['kind'] == 'execution':
                    context['scheme'] = t.scheme_map[context['scheme']]
                if site in contexts and contexts[site] != context:
                    fail('metadata.sites', 'metadata-origin', 'CONTEXT', 'allocation has inconsistent lexical contexts')
                b.put(contexts, site, context)
        for old in d['sites']:
            b.work()
            index = self.site_instruction[old['id']]
            record = d['instructions'][index]
            inst = instruction_at(self.raw, old['path'], b)
            scope = None if old['type_scope'] is None else t.scheme_map[old['type_scope']]
            context = t.context_for_path(old['path'])
            if contexts.get(old['id']) != context or old['path'] != record['path']:
                fail('metadata.sites', 'metadata-origin', 'CONTEXT', 'actual allocation provenance differs from lexical context')
            op, code, physical, arm = inst['op'], None, None, old['arm']
            if op == 'case_fields_i64':
                variants = self.raw['families'][inst['family']]['variants']
                if type(arm) is not int or not 0 <= arm < len(variants):
                    fail('metadata.sites', 'metadata-origin', 'FACTORY', 'factory site lacks its exact declared arm')
                target = inst['arms'][variants[arm]]['code']
                code = self.tables['codes'][old['code']]
                if code['kind'] != 'thunk' or code['name'] != target:
                    fail('metadata.sites', 'metadata-origin', 'FACTORY', 'factory arm callback association differs')
                category, principal, physical = 'THUNK', t.reference('#i64'), '#i64'
            else:
                if arm is not None:
                    fail('metadata.sites', 'metadata-origin', 'SITE', 'non-factory allocation has an arm')
                if op in ('closure', 'thunk'):
                    code = self.tables['codes'][old['code']]
                    kind = 'function' if op == 'closure' else 'thunk'
                    target = inst['function' if op == 'closure' else 'code']
                    if code['kind'] != kind or code['name'] != target:
                        fail('metadata.sites', 'metadata-origin', 'CODE', 'allocation targets different callback')
                    spec = self.raw['functions' if op == 'closure' else 'codes'][target]
                    principal = code['callable_type'] if op == 'closure' else code['result']
                    physical = '@' + spec['signature'] if op == 'closure' else spec['result']
                    category = 'CLOSURE' if op == 'closure' else 'THUNK'
                elif op in ('application', 'application_borrow'):
                    function_type = t.old(fact_at(record, 'function', b)['type'])
                    principal = t.tables['types'][function_type]['result']
                    category = 'APPLICATION'
                elif op in ('alloc', 'hole'):
                    physical = inst['layout']; principal = t.reference(physical, scope)
                    category = 'DATA' if op == 'alloc' else 'HOLE'
                elif op in ('construct_nullary', 'construct_sum'):
                    physical = '%' + inst['family']; principal = t.reference(physical)
                    category = 'SUM'
                elif op in ('scalar', 'prim2'):
                    if op == 'scalar':
                        physical = '#' + inst['kind']
                    else:
                        physical = '#bool' if inst['primitive'] in ('eqInt', 'ltInt') else '#i64'
                    principal = t.reference(physical); category = 'SCALAR'
                else:
                    fail('metadata.sites', 'metadata-origin', 'SITE', 'instruction does not allocate')
            if physical is not None and physical.startswith('^'):
                physical = None
            code_id = None if code is None else code['id']
            if (old['category'] != category or t.old(old['principal_type']) != principal
                    or old['code'] != code_id or old['legacy_physical'] != physical
                    or (code is not None and code['scope'] != scope)):
                fail('metadata.sites', 'metadata-origin', 'SITE', 'allocation equation differs from actual instruction')
            site = self.add('sites', path=b.clone(old['path']), arm=arm, scope=scope,
                           principal_type=principal, category=category, code=code_id,
                           legacy_physical=physical, context=b.clone(context))
            b.creation()
            executions = []
            for env in t.lawful_envs(old['path']):
                b.work()
                mode = t.tables['environments'][env]['mode']
                origin = _MODE_ORIGIN[mode]
                rep = self.default_rep(principal, env)
                if origin == 'CONCRETE' and physical in self.legacy:
                    rep = self.legacy[physical]
                resolved = t.resolve(principal, env)
                typing = self.tables['shape_typing'][rep]
                if typing['type'] != resolved:
                    fail('metadata.site_executions', 'metadata-representation', 'REPRESENTATION', 'allocation representation has a different full contract')
                ready = self.tables['representations'][rep]['ready_kind']
                if category in _CATEGORY_READY and ready != _CATEGORY_READY[category]:
                    fail('metadata.site_executions', 'metadata-representation', 'READY_KIND', 'allocation category cannot use this ready representation')
                execution = self.add('site_executions', site=site['id'], env=env,
                    origin_kind=origin, principal_type=resolved, representation=rep,
                    code_execution=None if code_id is None else self.code_execution[key2(b, code_id, env)])
                b.append(executions, execution['id'])
            b.put(self.site_executions, site['id'], b.tuple(executions))
        for intro in self.tables['introductions']:
            for site_id in intro['result_sites']:
                b.work()
                site = self.tables['sites'][site_id]
                if site['context'] != b.row(kind='introduction', intro=intro['id']) or site['scope'] != intro['scheme']:
                    fail('metadata.introductions', 'metadata-origin', 'INTRO', 'result site belongs to a different introduction')


def build_representations(raw, derived, types, budget):
    result = RepresentationClosure(raw, derived, types, budget)
    result.code_rows()
    result.intro_use_rows()
    result.shape_rows()
    result.site_rows()
    return result
