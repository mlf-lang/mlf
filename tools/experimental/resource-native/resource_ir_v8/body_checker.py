"""All-body IR8 resource checking, without any evaluation or emitter route.

The ownership rules are a deliberately local port of resource_ir/checker.py,
operation ledger lines 388-744. Type equality is always canonical full Type-ID
identity, and Scheme VALUE admission is separate from group authority.
"""
from __future__ import annotations

from .program_schema import (fail, exact, mapping, sequence, name, diagnostic_path,
    SCHEMAS, GENERIC_OPS, PRIMITIVES, INSTRUCTION_LIMIT, SITE_CODE_LIMIT, CAPTURE_LIMIT)
from .ownership import Symbols, State
from .provenance import Analysis

CATEGORIES = {'alloc': 'DATA', 'closure': 'CLOSURE', 'thunk': 'THUNK', 'hole': 'HOLE',
              'application': 'APPLICATION', 'application_borrow': 'APPLICATION',
              'scalar': 'SCALAR', 'prim2': 'SCALAR', 'construct_nullary': 'SUM', 'construct_sum': 'SUM'}


class BodyChecker:
    def __init__(self, program, declarations, budget):
        self.program, self.d, self.b = program, declarations, budget
        self.a, self.symbols = Analysis(budget, declarations), Symbols(budget)
        budget.charge()  # checker context header
        self.code_lookup, self.code_sources, self.instruction_lookup = {}, [], {}
        self.instruction_meta, self.intro_lookup, self.use_lookup = [], {}, {}
        self.int_type, self.bool_type = self.resolve('#i64', None, 'program'), self.resolve('#bool', None, 'program')
        self.concrete_context = budget.row(kind='concrete')

    def resolve(self, reference, scope, path):
        # The adapter performs unchanged lexical declaration checks, including
        # recursive generic protocol/atom restrictions. Preserve its exact errors.
        return self.d.resolve_id(reference, scope)

    def once(self, type_id):
        row = self.d.row(type_id)
        return row[0] == 'arrow' and row[3] == 'once'

    def require_type(self, value, expected, path):
        if value.view != 'MONO':
            fail(path, 'type', 'SCHEME_VALUE', 'Scheme is not an ordinary value')
        if value.type != expected:
            fail(path, 'type', 'TYPE', 'complete canonical type/arrow contract differs')

    def scope(self, value, path):
        if value is not None:
            name(value, path)
            self.d.scheme(value)
        return value

    def family(self, family, path):
        name(family, path)
        if family not in self.program['families']:
            fail(path, 'schema', 'FAMILY', 'unknown declared family')
        return self.program['families'][family]

    def prepare_codes(self):
        for kind, map_name in (('function', 'functions'), ('thunk', 'codes')):
            definitions = mapping(self.program[map_name], map_name)
            if len(self.a.codes) + len(definitions) > SITE_CODE_LIMIT:
                fail('program.sites_and_codes', 'schema', 'SITE_CODE_COUNT', 'combined code/site inventory exceeds 2048')
            for code_name in self.b.ordered(definitions):
                name(code_name, map_name)
                spec = definitions[code_name]
                p = map_name + '.' + code_name
                fields = ('signature', 'parameter', 'captures', 'body', 'type_scope') if kind == 'function' else ('result', 'captures', 'body', 'type_scope')
                exact(spec, fields, p)
                scope = self.scope(spec['type_scope'], p + '.type_scope')
                captures = mapping(spec['captures'], p + '.captures')
                if len(captures) > CAPTURE_LIMIT:
                    fail(p + '.captures', 'schema', 'CAPTURE_COUNT', 'code captures exceed 64')
                if kind == 'function':
                    signature = name(spec['signature'], p + '.signature')
                    if signature not in self.program['signatures']:
                        fail(p + '.signature', 'schema', 'SIGNATURE', 'unknown signature name')
                    callable_type = self.resolve('@' + signature, scope, p + '.signature')
                    arrow = self.d.row(callable_type)
                    argument, result = arrow[1], arrow[2]
                    parameter = name(spec['parameter'], p + '.parameter', binder=True)
                    if parameter in captures:
                        fail(p + '.captures', 'schema', 'SCHEMA', 'capture cannot shadow parameter')
                else:
                    callable_type = argument = None
                    result = self.resolve(spec['result'], scope, p + '.result')
                capture_rows = []
                for capture in self.b.ordered(captures):
                    name(capture, p + '.captures', binder=True)
                    contract = exact(captures[capture], ('layout', 'relation'), p + '.captures.' + capture)
                    if contract['relation'] not in ('same', 'down', 'below'):
                        fail(p + '.captures.' + capture, 'schema', 'SCHEMA', 'unknown capture relation')
                    target = self.resolve(contract['layout'], scope, p + '.captures.' + capture + '.layout')
                    self.b.record_append(capture_rows, name=capture, type=target, relation=contract['relation'])
                sequence(spec['body'], p + '.body')
                code_id = len(self.a.codes)
                row = self.b.record_append(self.a.codes, id=code_id, kind=kind, name=code_name, type_scope=scope,
                    callable_type=callable_type, argument=argument, result=result, captures=capture_rows,
                    body_path=self.a.path(kind, code_name, ()))
                self.b.append(self.code_sources, spec)
                self.b.put(self.code_lookup, (kind, code_name), code_id)
                self.a.counts['functions' if kind == 'function' else 'thunks'] += 1

    def target_code(self, kind, value, scope, path):
        name(value, path)
        key = (kind, value)
        if key not in self.code_lookup:
            fail(path, 'schema', 'UNKNOWN_CODE', 'all callbacks must be declared')
        code = self.code_lookup[key]
        return code

    def site(self, record, scope, category, code, principal, physical, *, arm=None, container=None):
        if len(self.a.codes) + len(self.a.sites) >= SITE_CODE_LIMIT:
            fail('program.sites_and_codes', 'schema', 'SITE_CODE_COUNT', 'combined code/site inventory exceeds 2048')
        site_id = len(self.a.sites)
        if physical is not None and physical.startswith('^'):
            physical = None
        row = self.b.record_append(self.a.sites, id=site_id, path=record['path'], arm=arm, type_scope=scope,
            principal_type=principal, category=category, code=code, legacy_physical=physical)
        self.b.append(record['sites'], site_id)
        if code is not None:
            self.b.record_append(self.a.edges, from_code=container, to_code=code, site=site_id)
        self.a.counts['allocations'] += 1
        return site_id

    def scan_factory(self, instruction, record, scope, container, path):
        family = self.family(instruction['family'], path + '.family')
        arms = exact(instruction['arms'], family['variants'], path + '.arms')
        for arm_index, variant in enumerate(family['variants']):
            ap = path + '.arms.' + variant
            arm = exact(arms[variant], ('code', 'captures'), ap)
            code_id = self.target_code('thunk', arm['code'], scope, ap)
            code = self.a.codes[code_id]
            if code['result'] != self.int_type:
                fail(ap, 'type', 'FACTORY', 'factory requires an exact Int-result thunk')
            captures = mapping(arm['captures'], ap + '.captures')
            if len(captures) > 64:
                fail(ap + '.captures', 'schema', 'CAPTURE_COUNT', 'factory captures exceed 64')
            if len(captures) != len(code['captures']) or any(c['name'] not in captures for c in code['captures']):
                fail(ap + '.captures', 'schema', 'CAPTURES', 'factory capture inventory differs')
            field_count = external_count = 0
            for capture in code['captures']:
                binding = captures[capture['name']]
                cp = ap + '.captures.' + capture['name']
                if type(binding) is not dict:
                    fail(cp, 'schema', 'CAPTURE_BINDING', 'expected tagged capture binding')
                if binding.get('kind') == 'field':
                    exact(binding, ('kind', 'index'), cp)
                    index = binding['index']
                    if type(index) is not int or not 0 <= index < len(family['fields'][variant]):
                        fail(cp, 'schema', 'FIELD_INDEX', 'field index outside declared variant vector')
                    field_count += 1
                elif binding.get('kind') == 'external':
                    exact(binding, ('kind', 'value'), cp)
                    name(binding['value'], cp + '.value')
                    external_count += 1
                else:
                    fail(cp, 'schema', 'CAPTURE_BINDING', 'unknown factory capture tag')
            if field_count > 32 or external_count > 32:
                fail(ap + '.captures', 'schema', 'FACTORY_CAPTURE_COUNT', 'factory field/external category exceeds 32')
            self.site(record, scope, 'THUNK', code_id, self.int_type, '#i64', arm=arm_index, container=container)
            self.a.counts['checked_factory_arms'] += 1

    def scan_block(self, body, root, root_name, prefix, scope, container, intro=None):
        sequence(body, 'entry' if root == 'entry' else root + '.' + str(root_name) + '.body')
        if not body:
            fail('entry' if root == 'entry' else root + '.' + str(root_name) + '.body', 'schema', 'TERMINAL', 'body must end with its exact terminator')
        for index, instruction in enumerate(body):
            if len(self.a.instructions) >= INSTRUCTION_LIMIT:
                fail('program.instructions', 'schema', 'INSTRUCTION_COUNT', 'instruction count exceeds 10000')
            segments = self.b.listing(prefix)
            self.b.append(segments, index)
            path_record = self.a.path(root, root_name, segments)
            p = diagnostic_path(path_record)
            if type(instruction) is not dict or type(instruction.get('op')) is not str:
                fail(p, 'schema', 'SCHEMA', 'instruction requires string op')
            op = instruction['op']
            if op not in SCHEMAS:
                fail(p, 'schema', 'OPCODE', 'operation is outside Stage02 public vocabulary')
            exact(instruction, ('op',) + SCHEMAS[op], p)
            if intro is not None:
                allowed = op in GENERIC_OPS or op == 'seal'
                terminal = op == 'seal'
            elif scope is not None:
                allowed = op in GENERIC_OPS or op == 'return'
                terminal = op == 'return'
            else:
                allowed = op != 'seal' and (op != 'return' if root == 'entry' else op not in ('finish', 'finish_scalar'))
                terminal = op in ('return', 'finish', 'finish_scalar')
            if not allowed:
                fail(p, 'schema', 'OPCODE', 'operation is forbidden in this lexical context')
            if terminal != (index == len(body) - 1):
                if terminal or index == len(body) - 1:
                    fail(p, 'schema', 'TERMINAL', 'body needs exactly one final context terminator')
            if 'out' in instruction:
                name(instruction['out'], p + '.out', binder=True)
            # Operand identifier shape is checked here, before coverage/graph work.
            for field in ('in', 'ceiling', 'argument', 'left', 'right', 'condition', 'then', 'else', 'scrutinee', 'hole'):
                if field in instruction:
                    name(instruction[field], p + '.' + field)
            if op != 'scalar' and 'value' in instruction:
                name(instruction['value'], p + '.value')
            if op in ('new_root', 'new_below'):
                for variable in sequence(instruction['imports'], p + '.imports'):
                    name(variable, p + '.imports')
            if op in ('application', 'application_borrow'):
                name(instruction['function'], p + '.function')
            ir_index = len(self.a.instructions)
            record = self.b.record_append(self.a.instructions, path=path_record, op=op, type_scope=scope, inputs=[], outputs=[], sites=[])
            self.b.put(self.instruction_lookup, id(instruction), ir_index)
            self.b.record_append(self.instruction_meta, container=container, intro=intro)
            self.a.counts['instructions'] += 1
            if op == 'generalize':
                scheme = name(instruction['scheme'], p + '.scheme')
                _, body_type, _ = self.d.scheme(scheme)
                intro_id = len(self.a.intros)
                row = self.b.record_append(self.a.intros, id=intro_id, scheme=scheme, container=container, generalize_path=path_record,
                                seal_path=None, body_type=body_type, result_sites=[])
                self.b.put(self.intro_lookup, scheme, None if scheme in self.intro_lookup else intro_id)
                self.a.counts['introductions'] += 1
                child_prefix = self.b.listing(segments)
                self.b.append(child_prefix, 'body')
                self.scan_block(instruction['body'], root, root_name, child_prefix, scheme, container, intro_id)
            elif op == 'seal':
                self.a.intros[intro]['seal_path'] = path_record
            elif op == 'instantiate':
                use = name(instruction['instantiation'], p + '.instantiation')
                self.d.instantiation(use)
                if use not in self.use_lookup:
                    self.b.put(self.use_lookup, use, [])
                self.b.append(self.use_lookup[use], path_record)
                self.a.counts['instantiate_occurrences'] += 1
            elif op == 'case_fields_i64':
                self.scan_factory(instruction, record, scope, container, p)
            elif op in CATEGORIES:
                code = principal = physical = None
                if op in ('alloc', 'hole'):
                    physical = instruction['layout']
                    principal = self.resolve(physical, scope, p + '.layout')
                elif op == 'closure':
                    code = self.target_code('function', instruction['function'], scope, p)
                    principal = self.a.codes[code]['callable_type']
                    physical = '@' + self.code_sources[code]['signature']
                elif op == 'thunk':
                    code = self.target_code('thunk', instruction['code'], scope, p)
                    principal = self.a.codes[code]['result']
                    physical = self.code_sources[code]['result']
                elif op == 'scalar':
                    if instruction['kind'] not in ('i64', 'bool'):
                        fail(p, 'schema', 'SCALAR_KIND', 'unsupported scalar kind')
                    literal = instruction['value']
                    if (instruction['kind'] == 'i64' and (type(literal) is not int or not -(1 << 63) <= literal < (1 << 63))) or (instruction['kind'] == 'bool' and type(literal) is not bool):
                        fail(p, 'schema', 'SCALAR_VALUE', 'scalar literal has wrong kind/range')
                    physical = '#' + instruction['kind']
                    principal = self.resolve(physical, scope, p)
                elif op == 'prim2':
                    name(instruction['primitive'], p + '.primitive')
                    if instruction['primitive'] not in PRIMITIVES:
                        fail(p, 'schema', 'PRIMITIVE', 'primitive outside exact five-operation contract')
                    physical = PRIMITIVES[instruction['primitive']]
                    principal = self.resolve(physical, scope, p)
                elif op in ('construct_nullary', 'construct_sum'):
                    family = self.family(instruction['family'], p + '.family')
                    if instruction['variant'] not in family['variants']:
                        fail(p, 'schema', 'VARIANT', 'unknown family variant')
                    physical = '%' + instruction['family']
                    principal = self.resolve(physical, scope, p)
                self.site(record, scope, CATEGORIES[op], code, principal, physical, container=container)
            if op in ('alloc', 'closure', 'thunk'):
                slots = mapping(instruction['fields'] if op == 'alloc' else instruction['captures'], p + ('.fields' if op == 'alloc' else '.captures'))
                for key, variable in slots.items():
                    name(key, p)
                    name(variable, p)
            if op == 'construct_sum':
                for variable in sequence(instruction['fields'], p + '.fields'):
                    name(variable, p + '.fields')
            if op == 'case_i64':
                family = self.family(instruction['family'], p + '.family')
                arms = exact(instruction['arms'], family['variants'], p + '.arms')
                for variant in family['variants']:
                    name(arms[variant], p + '.arms.' + variant)
            if op == 'field':
                name(instruction['field'], p + '.field')

    def prepare(self):
        self.prepare_codes()
        for code in self.a.codes:
            self.scan_block(self.code_sources[code['id']]['body'], code['kind'], code['name'], (), code['type_scope'], code['id'])
        self.scan_block(self.program['entry'], 'entry', None, (), None, None)
        for scheme, _ in self.d.schemes:
            if scheme not in self.intro_lookup or self.intro_lookup[scheme] is None:
                fail('schemes.' + scheme, 'coverage', 'INTRODUCTION_COVERAGE', 'declared scheme lacks its one introduction')
        for use, declaration in self.d.instantiations:
            if use not in self.use_lookup:
                fail('instantiations.' + use, 'coverage', 'USE_COVERAGE', 'declared use has no instantiate occurrence')
            scheme, arguments, result, environment = declaration
            row = self.b.record_append(self.a.uses, name=use, scheme=scheme, arguments=self.b.listing(arguments), environment=environment,
                             result_type=result, occurrences=self.b.listing(self.use_lookup[use]))
        self.a.counts['declared_uses'] = len(self.a.uses)
        self.a.check_graph(self.program)

    def authority(self, state, instruction, variable, role, path):
        value = state.authority(variable, path)
        index = self.a.operand(instruction, value, role, authority=True)
        return value, index

    def value(self, state, instruction, variable, role, path, *, own=True, mono=True, expected=None):
        value = state.get(variable, path, kind='value', mono=mono, validate_anchor=False)
        if expected is not None:
            self.require_type(value, expected, path)
        if own and value.mode != 'own':
            fail(path, 'resource', 'OWNERSHIP', 'operand requires an independent owner')
        state.check_anchor(value, path)
        index = self.a.operand(instruction, value, role)
        return value, index

    def down(self, state, value, group, path, *, code='UPWARD_SUPPORT'):
        if not state.order.below(value.group, group):
            fail(path, 'resource', code, 'operand is not proven Down(required authority)')

    def relation(self, state, value, group, relation, path):
        self.down(state, value, group, path)
        if relation == 'same' and value.group != group:
            fail(path, 'resource', 'CAPTURE_RELATION', 'same capture requires exact group identity')
        if relation == 'below' and not state.order.below(value.group, group, strict=True):
            fail(path, 'resource', 'CAPTURE_RELATION', 'below capture requires strict path proof')

    def rules(self, scope, *, relation='down', no_once=True, anchor=False, force=False):
        # Each output member is charged; constant vocabulary tables are free.
        rules = []
        for rule in ('exact_mono_type', 'down_support'):
            self.b.append(rules, rule)
        if relation == 'same':
            self.b.append(rules, 'same_group')
        elif relation == 'below':
            self.b.append(rules, 'strict_below')
        if no_once:
            self.b.append(rules, 'no_once_copy')
        if anchor:
            self.b.append(rules, 'live_exact_anchor')
        if scope is not None:
            self.b.append(rules, 'neutral_same_capsule')
        self.b.append(rules, 'closed_preserve_target_access')
        if force:
            self.b.append(rules, 'principal_force_result')
        return rules

    def publication(self, ir_index, role, site, source_index, expected, scope, *, relation='down', no_once=True, anchor=False):
        self.a.obligation(ir_index, role, 'publish', site,
                          (('inputs', 0), ('inputs', source_index)), expected, scope,
                          self.rules(scope, relation=relation, no_once=no_once, anchor=anchor))

    def allocated(self, site, context, group, type_id, *, ready=False, ticket=False):
        self.a.sites[site]['principal_type'] = type_id
        prov = self.a.term('allocated', site=site, context=context)
        return self.symbols.value(group, type_id, prov, ready=ready, ticket=ticket)

    def output(self, state, ir_index, name_, value, path, *, reserved=False, role=('out',)):
        state.bind(name_, value, path + '.out', reserved=reserved)
        self.a.operand(ir_index, value, role, side='outputs')

    def check_block(self, body, state, context, *, code=None, intro=None):
        for instruction in body:
            ir_index = self.instruction_lookup[id(instruction)]
            record = self.a.instructions[ir_index]
            p, op, scope = diagnostic_path(record['path']), instruction['op'], record['type_scope']
            i = instruction
            site = record['sites'][0] if record['sites'] else None
            if op in ('new_root', 'new_below'):
                ceiling = None
                if op == 'new_below':
                    ceiling, _ = self.authority(state, ir_index, i['ceiling'], ('ceiling',), p + '.ceiling')
                imported = []
                for index, variable in enumerate(i['imports']):
                    value, _ = self.authority(state, ir_index, variable, ('imports', index), p + '.imports[' + str(index) + ']')
                    self.b.append(imported, value)
                if ceiling is not None:
                    for value in imported:
                        if not state.order.below(value.group, ceiling.group, strict=True):
                            fail(p, 'resource', 'STRICT_IMPORT', 'each imported group must be strictly below ceiling')
                group = self.symbols.fresh('groups')
                if ceiling is not None:
                    state.order.add(ceiling.group, group, True)
                for value in imported:
                    state.order.add(group, value.group, True)
                self.output(state, ir_index, i['out'], self.symbols.key(group), p)
            elif op == 'scalar':
                authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
                result = self.allocated(site, context, authority.group, self.a.sites[site]['principal_type'], ready=True)
                self.output(state, ir_index, i['out'], result, p)
            elif op == 'prim2':
                authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
                for field in ('left', 'right'):
                    operand, _ = self.value(state, ir_index, i[field], (field,), p + '.' + field, expected=self.int_type)
                    self.require_type(operand, self.int_type, p + '.' + field)
                    if not operand.ready:
                        fail(p, 'resource', 'DEMAND', 'primitive operands must be explicitly ready')
                self.output(state, ir_index, i['out'], self.allocated(site, context, authority.group, self.a.sites[site]['principal_type'], ready=True), p)
            elif op in ('alloc', 'closure', 'thunk', 'hole'):
                authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
                target = self.a.sites[site]['principal_type']
                if op == 'hole':
                    if self.once(target):
                        fail(p, 'resource', 'ONCE_CARRIER', 'Once holes are unsupported')
                elif op == 'alloc':
                    row = self.d.row(target)
                    if row[0] != 'closed' or row[1] not in self.program['layouts']:
                        fail(p, 'resource', 'KIND', 'alloc requires legitimate physical DATA carrier')
                    expected = self.program['layouts'][row[1]]
                    exact(i['fields'], expected, p + '.fields')
                    for field in self.b.ordered(expected):
                        field_type = self.resolve(expected[field], scope, p)
                        value, index = self.value(state, ir_index, i['fields'][field], ('fields', field), p + '.fields.' + field, expected=field_type)
                        self.require_type(value, field_type, p + '.fields.' + field)
                        if self.once(value.type):
                            fail(p, 'resource', 'ONCE_CARRIER', 'DATA field cannot duplicate Once')
                        self.down(state, value, authority.group, p)
                        self.publication(ir_index, ('fields', field), site, index, field_type, scope)
                else:
                    code_id = self.a.sites[site]['code']
                    expected = self.a.codes[code_id]['captures']
                    supplied = i['captures']
                    if len(supplied) != len(expected) or any(c['name'] not in supplied for c in expected):
                        fail(p + '.captures', 'schema', 'CAPTURES', 'capture inventory must exactly match code')
                    affine = []
                    for capture in expected:
                        variable = supplied[capture['name']]
                        cp = p + '.captures.' + capture['name']
                        value, index = self.value(state, ir_index, variable, ('captures', capture['name']), cp, expected=capture['type'])
                        self.require_type(value, capture['type'], cp)
                        if self.once(value.type):
                            if op != 'closure' or not self.once(target):
                                fail(p, 'resource', 'ONCE_CARRIER', 'carrier cannot duplicate Once capture')
                            if variable in affine:
                                fail(p, 'resource', 'OWNERSHIP', 'one Once owner cannot fill two capture slots')
                            self.b.append(affine, variable)
                        self.relation(state, value, authority.group, capture['relation'], cp)
                        self.publication(ir_index, ('captures', capture['name']), site, index, capture['type'], scope,
                                         relation=capture['relation'], no_once=not self.once(value.type))
                    for variable in affine:
                        state.consume(variable, p)
                result = self.allocated(site, context, authority.group, target, ready=op in ('alloc', 'closure'), ticket=op == 'hole')
                self.output(state, ir_index, i['out'], result, p)
            elif op in ('application', 'application_borrow'):
                authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
                borrowed = op == 'application_borrow'
                callee = state.get(i['function'], p + '.function', kind='value', mono=True, validate_anchor=False)
                fi = self.a.operand(ir_index, callee, ('function',))
                arrow = self.d.row(callee.type)
                if arrow[0] != 'arrow':
                    fail(p, 'type', 'CALLABLE', 'application requires a full arrow contract')
                argument, ai = self.value(state, ir_index, i['argument'], ('argument',), p + '.argument', own=False, expected=arrow[1])
                state.check_anchor(callee, p + '.function')
                self.require_type(argument, arrow[1], p + '.argument')
                if not borrowed and (callee.mode != 'own' or argument.mode != 'own'):
                    fail(p, 'resource', 'OWNERSHIP', 'application requires independently owned inputs')
                if borrowed and (arrow[3] != 'repeat' or self.once(argument.type) or self.once(arrow[2])):
                    fail(p, 'resource', 'BORROW_PROTOCOL', 'borrowed publication requires Repeat/shareable values')
                if self.once(arrow[2]):
                    fail(p, 'resource', 'ONCE_CARRIER', 'shared application cannot memoize Once result')
                self.down(state, callee, authority.group, p, code='CALL_CEILING')
                self.down(state, argument, authority.group, p, code='CALL_CEILING')
                self.publication(ir_index, ('function',), site, fi, callee.type, scope, no_once=not self.once(callee.type), anchor=callee.mode == 'loan')
                self.publication(ir_index, ('argument',), site, ai, argument.type, scope, no_once=not self.once(argument.type), anchor=argument.mode == 'loan')
                self.a.obligation(ir_index, ('argument',), 'application_argument', site,
                    (('inputs', 0), ('inputs', fi), ('inputs', ai)), arrow[1], scope,
                    self.rules(scope, no_once=not self.once(argument.type), anchor=callee.mode == 'loan' or argument.mode == 'loan'))
                if self.once(callee.type) and i['function'] == i['argument']:
                    fail(p, 'resource', 'OWNERSHIP', 'one Once owner cannot fill both application slots')
                if self.once(callee.type):
                    state.consume(i['function'], p)
                if self.once(argument.type):
                    state.consume(i['argument'], p)
                self.output(state, ir_index, i['out'], self.allocated(site, context, authority.group, arrow[2]), p)
            elif op in ('construct_nullary', 'construct_sum'):
                authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
                fields = self.program['families'][i['family']]['fields'][i['variant']]
                supplied = i['fields'] if op == 'construct_sum' else ()
                if len(supplied) != len(fields):
                    fail(p, 'schema', 'ARITY', 'constructor requires complete field vector')
                for index, reference in enumerate(fields):
                    expected = self.resolve(reference, scope, p)
                    value, fact = self.value(state, ir_index, supplied[index], ('fields', index), p + '.fields[' + str(index) + ']', expected=expected)
                    self.require_type(value, expected, p)
                    self.down(state, value, authority.group, p)
                    self.publication(ir_index, ('fields', index), site, fact, expected, scope)
                self.output(state, ir_index, i['out'], self.allocated(site, context, authority.group, self.a.sites[site]['principal_type'], ready=True), p)
            elif op in ('select_i64', 'case_i64', 'case_fields_i64'):
                self.check_selection(i, ir_index, state, context, p)
            elif op == 'fill':
                hole, hi = self.value(state, ir_index, i['hole'], ('hole',), p + '.hole')
                target, vi = self.value(state, ir_index, i['value'], ('value',), p + '.value', expected=hole.type)
                self.require_type(target, hole.type, p + '.value')
                if not hole.ticket:
                    fail(p, 'resource', 'FILL_TICKET', 'fill needs original unspent hole ticket')
                self.down(state, target, hole.group, p, code='UPWARD_FILL')
                updated = self.symbols.changed(hole, ticket=False)
                state.values[i['hole']] = updated
                self.a.operand(ir_index, updated, ('hole',), side='outputs')
                self.a.obligation(ir_index, ('hole',), 'fill', self.a.exact_site(hole.provenance),
                    (('inputs', hi), ('inputs', vi), ('outputs', 0)), hole.type, scope, self.rules(scope))
            elif op in ('borrow', 'retain'):
                value, _ = self.value(state, ir_index, i['value'], ('value',), p + '.value', own=op == 'borrow', mono=False)
                if op == 'retain' and self.once(value.type):
                    fail(p, 'resource', 'ONCE_DUP', 'retain cannot copy Once permission')
                anchor = self.b.row(kind='owner', capability=value.capability) if op == 'borrow' else None
                result = self.symbols.copied_handle(value, mode='loan' if op == 'borrow' else 'own', anchor=anchor)
                self.output(state, ir_index, i['out'], result, p)
            elif op == 'end_borrow':
                value = state.get(i['value'], p + '.value')
                self.a.operand(ir_index, value, ('value',))
                if value.mode != 'loan' or i['value'] == '$home':
                    fail(p, 'resource', 'BORROW', 'end_borrow requires local loan')
                del state.values[i['value']]
            elif op == 'drop':
                value = state.get(i['value'], p + '.value', own=True)
                self.a.operand(ir_index, value, ('value',))
                state.consume(i['value'], p)
            elif op == 'field':
                value, vi = self.value(state, ir_index, i['value'], ('value',), p + '.value')
                row = self.d.row(value.type)
                if row[0] != 'closed' or row[1] not in self.program['layouts']:
                    fail(p, 'resource', 'KIND', 'field requires DATA host')
                fields = self.program['layouts'][row[1]]
                if i['field'] not in fields:
                    fail(p, 'schema', 'FIELDS', 'unknown DATA field')
                if not value.ready:
                    fail(p, 'resource', 'DEMAND', 'field host must be ready')
                field_type = self.resolve(fields[i['field']], scope, p)
                group = self.symbols.fresh('groups')
                state.order.add(value.group, group)
                prov = self.a.term('field', host=value.provenance, field=i['field'])
                anchor = self.b.row(kind='owner', capability=value.capability)
                result = self.symbols.value(group, field_type, prov, mode='loan', anchor=anchor)
                self.output(state, ir_index, i['out'], result, p)
                self.a.obligation(ir_index, ('field',), 'field_acquire', self.a.exact_site(value.provenance),
                    (('inputs', vi), ('outputs', 0)), field_type, scope, self.rules(scope, anchor=True))
            elif op == 'force':
                value, vi = self.value(state, ir_index, i['value'], ('value',), p + '.value')
                if self.once(value.type):
                    fail(p, 'resource', 'ONCE_CARRIER', 'Once cannot be forced/memoized')
                state.consume(i['value'], p)
                group = self.symbols.fresh('groups')
                state.order.add(value.group, group)
                prov = self.a.term('forced', cursor=value.provenance)
                result = self.symbols.value(group, value.type, prov, ready=True)
                self.output(state, ir_index, i['out'], result, p)
                self.a.obligation(ir_index, ('out',), 'force_result', self.a.exact_site(value.provenance),
                    (('inputs', vi), ('outputs', 0)), value.type, scope, self.rules(scope, force=True))
            elif op == 'generalize':
                authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
                state.reserve(i['out'], p + '.out')
                intro_id = self.intro_lookup[i['scheme']]
                child = State(self.b, order=state.order.copy(), home=authority.group)
                source = self.b.row(kind='parent', generalize_path=record['path'], binding=i['in'])
                child.bind('$home', self.symbols.alias(authority.group, source), p, internal=True)
                child_context = self.b.row(kind='introduction', intro=intro_id)
                sealed = self.check_block(i['body'], child, child_context, code=code, intro=intro_id)
                state.order.merge(child.order)
                self.output(state, ir_index, i['out'], sealed, p, reserved=True)
            elif op == 'seal':
                row = self.a.intros[intro]
                result, _ = self.value(state, ir_index, i['value'], ('value',), p + '.value', expected=row['body_type'])
                self.require_type(result, row['body_type'], p + '.value')
                state.movable(i['value'], p)
                result_site = self.a.exact_site(result.provenance)
                if result_site is None:
                    fail(p, 'resource', 'SEAL', 'seal must trace to an actual unforced local allocation')
                term = self.a.provenance[result.provenance]['value']
                if term['context']['kind'] != 'introduction' or term['context']['intro'] != intro or self.a.sites[result_site]['category'] == 'HOLE':
                    fail(p, 'resource', 'SEAL', 'seal cannot export foreign origin or raw HOLE')
                self.down(state, result, state.home, p, code='UPWARD_RETURN')
                state.consume(i['value'], p)
                state.finish(p)
                self.b.append(row['result_sites'], result_site)
                return self.symbols.changed(result, view='SCHEME', scheme=row['scheme'], projection=None)
            elif op == 'instantiate':
                value = state.get(i['value'], p + '.value', kind='value', validate_anchor=False)
                self.a.operand(ir_index, value, ('value',))
                scheme, arguments, target, environment = self.d.instantiation(i['instantiation'])
                if value.view != 'SCHEME' or value.scheme != scheme:
                    fail(p + '.value', 'type', 'SCHEME', 'instantiate requires exact declared Scheme handle')
                state.reserve(i['out'], p + '.out')
                state.move(i['value'], p)
                projection = self.b.row(scheme=scheme, environment=environment,
                    arguments=self.b.listing(arguments), use=i['instantiation'])
                result = self.symbols.changed(value, view='MONO', scheme=None, type=target, projection=projection)
                self.output(state, ir_index, i['out'], result, p, reserved=True)
            elif op == 'return':
                result, vi = self.value(state, ir_index, i['value'], ('value',), p + '.value', expected=state.result_type)
                self.require_type(result, state.result_type, p + '.value')
                self.down(state, result, state.home, p, code='UPWARD_RETURN')
                if state.require_ready and not result.ready:
                    fail(p, 'resource', 'DEMAND', 'callback result requires ready Once cursor')
                proof = None
                if state.result_identity is not None:
                    if result.node != state.result_identity:
                        fail(p, 'resource', 'IDENTITY', 'declared argument identity is not preserved')
                    proof = self.b.row(parameter=state.parameter, node=result.node)
                state.consume(i['value'], p)
                state.finish(p)
                rules = self.rules(scope, no_once=not self.once(result.type))
                if proof is not None:
                    self.b.append(rules, 'argument_identity')
                self.a.obligation(ir_index, ('value',), 'callback_return', None,
                    (('inputs', vi),), result.type, scope, rules)
                summary = self.a.returns[code]
                self.b.record_append(summary['return_paths'], path=record['path'], value=result.capability,
                    node=result.node, group=result.group, provenance=result.provenance, ready=result.ready,
                    required_ready=state.require_ready, support='down_home', identity_proof=proof)
                return None
            elif op == 'finish_scalar':
                result, _ = self.value(state, ir_index, i['value'], ('value',), p + '.value')
                if result.type not in (self.int_type, self.bool_type):
                    fail(p, 'type', 'TYPE', 'finish_scalar requires intrinsic scalar')
                if not result.ready:
                    fail(p, 'resource', 'DEMAND', 'finish_scalar requires ready result')
                state.consume(i['value'], p)
                state.finish(p)
                return None
            elif op == 'finish':
                state.finish(p)
                return None
        raise AssertionError('pre-scanned body lost terminator')

    def check_selection(self, i, ir_index, state, context, p):
        record = self.a.instructions[ir_index]
        scope, op = record['type_scope'], i['op']
        authority, _ = self.authority(state, ir_index, i['in'], ('in',), p + '.in')
        alternatives = []
        if op == 'select_i64':
            condition, _ = self.value(state, ir_index, i['condition'], ('condition',), p + '.condition', expected=self.bool_type)
            self.require_type(condition, self.bool_type, p + '.condition')
            if not condition.ready:
                fail(p, 'resource', 'DEMAND', 'selection condition must be ready')
            variables = []
            for key in ('then', 'else'):
                self.b.append(variables, i[key])
            if i['then'] == i['else'] or i['in'] in variables:
                fail(p, 'resource', 'OWNERSHIP', 'selection consumes distinct branch owners, not authority')
            for key in ('then', 'else'):
                value, _ = self.value(state, ir_index, i[key], (key,), p + '.' + key, expected=self.int_type)
                self.require_type(value, self.int_type, p + '.' + key)
                self.down(state, value, authority.group, p)
                state.movable(i[key], p)
                self.b.append(alternatives, value.provenance)
            for variable in variables:
                state.consume(variable, p)
        else:
            family = self.program['families'][i['family']]
            scrutinee, si = self.value(state, ir_index, i['scrutinee'], ('scrutinee',), p + '.scrutinee', expected=self.resolve('%' + i['family'], scope, p))
            self.require_type(scrutinee, self.resolve('%' + i['family'], scope, p), p + '.scrutinee')
            if not scrutinee.ready:
                fail(p, 'resource', 'DEMAND', 'case scrutinee must be ready')
            if op == 'case_i64':
                if any(family['fields'][v] for v in family['variants']):
                    fail(p, 'schema', 'FACTORY', 'field-bearing family requires case_fields_i64')
                variables = []
                seen = set()
                for variant in family['variants']:
                    variable = i['arms'][variant]
                    if variable == i['in'] or variable in seen:
                        fail(p, 'resource', 'OWNERSHIP', 'case requires independent owners, not authority')
                    self.b.add(seen, variable)
                    self.b.append(variables, variable)
                    value, _ = self.value(state, ir_index, variable, ('arms', variant), p + '.arms.' + variant, expected=self.int_type)
                    self.require_type(value, self.int_type, p + '.arms.' + variant)
                    self.down(state, value, authority.group, p)
                    state.movable(variable, p)
                    self.b.append(alternatives, value.provenance)
                for variable in variables:
                    state.consume(variable, p)
            else:
                self.down(state, scrutinee, authority.group, p)
                for variant_index, variant in enumerate(family['variants']):
                    arm = i['arms'][variant]
                    site = record['sites'][variant_index]
                    code = self.a.codes[self.a.sites[site]['code']]
                    for capture in code['captures']:
                        capture_name = capture['name']
                        binding = arm['captures'][capture_name]
                        role = ('arms', variant, 'captures', capture_name)
                        cp = p + '.arms.' + variant + '.captures.' + capture_name
                        if binding['kind'] == 'field':
                            actual = self.resolve(family['fields'][variant][binding['index']], scope, cp)
                            if actual != capture['type']:
                                fail(cp, 'type', 'TYPE', 'factory field contract differs from thunk capture')
                            if capture['relation'] != 'down':
                                fail(cp, 'resource', 'CAPTURE_RELATION', 'field acquisition proves only Down')
                            source_index = si
                        else:
                            value, source_index = self.value(state, ir_index, binding['value'],
                                ('arms', variant, 'captures', capture_name, 'value'), cp + '.value', expected=capture['type'])
                            self.require_type(value, capture['type'], cp + '.value')
                            if self.once(value.type):
                                fail(cp, 'resource', 'ONCE_CARRIER', 'factory thunk cannot duplicate Once')
                            self.relation(state, value, authority.group, capture['relation'], cp)
                        self.publication(ir_index, role, site, source_index, capture['type'], scope,
                                         relation=capture['relation'])
                    self.b.append(alternatives, self.a.term('allocated', site=site, context=context))
        group = self.symbols.fresh('groups')
        state.order.add(authority.group, group)
        provenance = self.a.choice(alternatives)
        result = self.symbols.value(group, self.int_type, provenance)
        self.output(state, ir_index, i['out'], result, p)

    def check(self):
        self.prepare()
        for layout in self.b.ordered(self.program['layouts']):
            for reference in self.program['layouts'][layout].values():
                if self.once(self.resolve(reference, None, 'layouts.' + layout)):
                    fail('layouts.' + layout, 'resource', 'ONCE_CARRIER', 'shared DATA cannot store Once permission')
        for code in self.a.codes:
            p = ('functions.' if code['kind'] == 'function' else 'codes.') + code['name']
            if code['kind'] == 'thunk' and self.once(code['result']):
                fail(p, 'resource', 'ONCE_CARRIER', 'shared thunk cannot memoize Once result')
            for capture in code['captures']:
                if self.once(capture['type']) and (code['kind'] == 'thunk' or not self.once(code['callable_type'])):
                    fail(p, 'resource', 'ONCE_CARRIER', 'shared carrier cannot duplicate Once capture')
            code_id = code['id']
            spec = self.code_sources[code_id]
            scope = code['type_scope']
            context = self.concrete_context if scope is None else self.b.row(kind='execution', code=code_id, scheme=scope)
            home = self.symbols.fresh('groups')
            state = State(self.b, home=home, result_type=code['result'],
                          require_ready=self.once(code['result']))
            source = self.b.row(kind='activation', code=code_id)
            state.bind('$home', self.symbols.alias(home, source), 'callback', internal=True)
            identity_contract = 'unknown'
            if code['kind'] == 'function':
                closure_group = self.symbols.fresh('groups')
                argument_group = self.symbols.fresh('groups')
                state.order.add(home, closure_group)
                state.order.add(home, argument_group)
                parameter_provenance = self.a.term('parameter', code=code_id)
                parameter = self.symbols.value(argument_group, code['argument'], parameter_provenance,
                                                ready=self.once(code['argument']))
                state.bind(spec['parameter'], parameter, 'functions.' + code['name'] + '.parameter')
                state.parameter = parameter.capability
                identity_contract = self.d.row(code['callable_type'])[4]
                if identity_contract == 'argument':
                    state.result_identity = parameter.node
            else:
                closure_group = home
            for capture in code['captures']:
                group = closure_group if capture['relation'] == 'same' else self.symbols.fresh('groups')
                if group != closure_group:
                    state.order.add(closure_group, group, capture['relation'] == 'below')
                provenance = self.a.term('capture', code=code_id, name=capture['name'])
                value = self.symbols.value(group, capture['type'], provenance,
                    ready=code['kind'] == 'function' and self.once(capture['type']))
                state.bind(capture['name'], value, 'callback.captures.' + capture['name'])
            summary = self.b.record_append(self.a.returns, code=code_id, type_scope=scope, result_type=code['result'],
                                 result_identity=identity_contract, return_paths=[])
            self.check_block(spec['body'], state, context, code=code_id)
        entry = State(self.b, finish_allowed=True)
        self.check_block(self.program['entry'], entry, self.concrete_context)
        return self.a
