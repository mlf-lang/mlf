"""Exact finite Access, transport, boundary, and coverage equations.

Guard rows are derived predicates, never observations of executed native checks.
Opaque values keep their actual Access; no null provenance becomes E0.
"""
from __future__ import annotations

from .metadata_budget import fail
from .metadata_representations import fact_at, instruction_at, path_key, key2, key3, access_key

GUARDS = ('registered-membership', 'exact-site-origin', 'physical-origin',
          'exact-mono-contract', 'symbolic-before-projection', 'same-neutral-capsule',
          'preserve-foreign-access', 'live-exact-anchor', 'acquire-before-release',
          'existing-support', 'code-association', 'return-identity', 'no-scheme-value',
          'pending-all-before-publish', 'scope-token', 'complete-vector',
          'same-handle-view-move', 'owner-mode', 'ticket-free', 'no-dependent-loans',
          'child-discharge', 'scheme-input', 'view-move-mode', 'return-linear-contract',
          'fill-linear-contract', 'state-category', 'application-slots')


def _mask(names):
    # Fixed schema constants only. Bitwise union avoids allocating intermediate
    # variable guard vectors. The final 27-position equation pass is charged.
    value = 0
    for name in names:
        value |= 1 << GUARDS.index(name)
    return value

A = _mask(('registered-membership', 'exact-site-origin', 'physical-origin'))
M = A | _mask(('exact-mono-contract', 'no-scheme-value'))
N = _mask(('symbolic-before-projection', 'same-neutral-capsule'))
C = _mask(('preserve-foreign-access',))
L = _mask(('live-exact-anchor', 'existing-support'))
Q = _mask(('acquire-before-release',))
RETURN = _mask(('owner-mode', 'ticket-free', 'no-dependent-loans', 'return-linear-contract'))
PHASES = ('hole-demand', 'busy-demand', 'fill', 'indirect-dispatch', 'thunk-dispatch',
          'application-dispatch', 'cursor-return', 'reverse-pending', 'memo-publish', 'memo-read')
DEFERRED = {
    'THUNK': ('busy-demand', 'thunk-dispatch', 'cursor-return', 'reverse-pending', 'memo-publish', 'memo-read'),
    'APPLICATION': ('busy-demand', 'application-dispatch', 'cursor-return', 'reverse-pending', 'memo-publish', 'memo-read'),
    'HOLE': ('hole-demand', 'busy-demand', 'fill', 'indirect-dispatch', 'cursor-return', 'reverse-pending', 'memo-publish', 'memo-read'),
}
INSTRUCTION_OPS = ('generalize', 'seal', 'instantiate', 'retain', 'borrow', 'drop',
                   'end_borrow', 'select_i64', 'case_i64', 'case_fields_i64')
TABLES = ('slots', 'accesses', 'transports', 'boundaries', 'coverage')


class EdgeClosure:
    __slots__ = ('r', 't', 'b', 'raw', 'd', 'tables', 'slots_by_site', 'slot_lookup',
                 'access_lookup', 'accesses_by_origin', 'obligation_slots', 'obligation_boundaries',
                 'instruction_boundaries', 'code_boundaries', 'site_boundaries')

    def __init__(self, representations):
        self.r = representations
        self.t, self.b = representations.types, representations.budget
        self.raw, self.d = representations.raw, representations.derived
        b = self.b
        b.creation(1 + 2 * len(TABLES))  # temporary map/members and empty arrays
        self.tables = b.row(**{name: [] for name in TABLES})
        b.creation(9)
        self.slots_by_site, self.slot_lookup, self.access_lookup = {}, {}, {}
        self.accesses_by_origin, self.obligation_slots, self.obligation_boundaries = {}, {}, {}
        self.instruction_boundaries, self.code_boundaries, self.site_boundaries = {}, {}, {}

    def add(self, table, **fields):
        rows = self.tables[table]
        if table in ('accesses', 'transports'):
            self.b.rows()
        return self.b.record_append(rows, id=len(rows), **fields)

    def slot(self, site, role, type_id, relation='down'):
        row = self.add('slots', site=site, role=role, type=type_id, relation=relation)
        self.b.append(self.slots_by_site[site], row['id'])
        return row

    def dependency(self, target, type_id, env):
        self.b.creation(2)  # fixed pair record plus its list membership
        target.append((type_id, env))

    def slot_rows(self):
        b, r, t = self.b, self.r, self.t
        for site in r.tables['sites']:
            b.work()
            sid, category = site['id'], site['category']
            b.put(self.slots_by_site, sid, b.listing(()))
            inst = instruction_at(self.raw, site['path'], b)
            if category in ('CLOSURE', 'THUNK'):
                for capture in r.tables['codes'][site['code']]['captures']:
                    b.work()
                    row = self.slot(sid, b.row(kind='capture', name=capture['name']), capture['type'], capture['relation'])
                    b.put(self.slot_lookup, key3(b, sid, 'capture', capture['name']), row['id'])
            elif category in ('DATA', 'SUM'):
                shape = r.canonical[site['principal_type']]
                variant = None
                if category == 'SUM':
                    if inst['op'] not in ('construct_nullary', 'construct_sum'):
                        fail('metadata.slots', 'metadata-origin', 'VARIANT', 'SUM site must be an actual constructor')
                    variants = self.raw['families'][inst['family']]['variants']
                    b.work(len(variants))
                    variant = variants.index(inst['variant'])
                for field in r.tables['nominal_fields']:
                    b.work()
                    if field['shape'] != shape or field['variant'] != variant:
                        continue
                    if category == 'DATA':
                        role = b.row(kind='field', field=field['id'])
                        lookup = key3(b, sid, 'field', field['name'])
                    else:
                        role = b.row(kind='variant-field', variant=variant, field=field['id'])
                        lookup = key3(b, sid, 'variant-field', field['position'])
                    row = self.slot(sid, role, field['type'])
                    b.put(self.slot_lookup, lookup, row['id'])
            elif category == 'APPLICATION':
                checked = self.d['instructions'][r.site_instruction[sid]]
                for role in ('function', 'argument'):
                    b.work()
                    fact = fact_at(checked, role, b)
                    row = self.slot(sid, b.row(kind=role), t.old(fact['type']))
                    b.put(self.slot_lookup, key2(b, sid, role), row['id'])
            if category in DEFERRED:
                row = self.slot(sid, b.row(kind='memo'), site['principal_type'])
                b.put(self.slot_lookup, key2(b, sid, 'memo'), row['id'])

    def access_rows(self):
        b, r, t = self.b, self.r, self.t
        b.creation()
        result_schemes = {}
        for intro in r.tables['introductions']:
            for site in intro['result_sites']:
                b.work()
                if site in result_schemes:
                    fail('metadata.accesses', 'metadata-origin', 'SCHEME', 'site belongs to multiple introductions')
                b.put(result_schemes, site, intro['scheme'])
        b.creation()
        pending = []
        for execution in r.tables['site_executions']:
            b.work()
            site = r.tables['sites'][execution['site']]
            env, origin = execution['env'], execution['origin_kind']
            if origin == 'GENERIC':
                environments = t.envs_for_scope(site['scope'])
            else:
                b.creation(2)
                environments = (env,)
            for use_env in environments:
                b.work()
                b.record_append(pending, site=site['id'], origin_env=env, mode='MONO',
                    use_env=use_env, type=t.resolve(site['principal_type'], use_env), scheme=None)
            if origin == 'GENERIC' and site['id'] in result_schemes:
                scheme = result_schemes[site['id']]
                if site['context'] != b.row(kind='introduction', intro=t.tables['schemes'][scheme]['intro']):
                    fail('metadata.accesses', 'metadata-origin', 'SCHEME', 'Scheme access requires its actual introduction result')
                b.record_append(pending, site=site['id'], origin_env=env, mode='SCHEME',
                    use_env=None, type=t.tables['schemes'][scheme]['body'], scheme=scheme)
        ordered = b.ordered(pending, key=lambda a: (a['site'], a['origin_env'],
            0 if a['mode'] == 'MONO' else 1, -1 if a['use_env'] is None else a['use_env'],
            -1 if a['scheme'] is None else a['scheme']), key_units=6)
        for fields in ordered:
            b.work()
            row = self.add('accesses', **fields)
            key = access_key(b, row['site'], row['origin_env'], row['mode'], row['use_env'], row['scheme'])
            if key in self.access_lookup:
                fail('metadata.accesses', 'metadata-closure', 'ACCESS', 'duplicate Access key')
            b.put(self.access_lookup, key, row['id'])
            origin = key2(b, row['site'], row['origin_env'])
            if origin not in self.accesses_by_origin:
                b.put(self.accesses_by_origin, origin, b.listing(()))
            b.append(self.accesses_by_origin[origin], row['id'])
        for access in self.tables['accesses']:
            b.work()
            if access['mode'] != 'MONO':
                continue
            self.add('transports', source_access=access['id'], projection_env=None,
                     result_access=access['id'], kind='identity')
            env = t.tables['environments'][access['origin_env']]
            if env['mode'] != 'NEUTRAL' or access['use_env'] != access['origin_env']:
                continue
            for projection in t.closed_envs(env['scheme']):
                b.work()
                key = access_key(b, access['site'], access['origin_env'], 'MONO', projection, None)
                target = self.access_lookup.get(key)
                if target is None:
                    fail('metadata.transports', 'metadata-closure', 'TRANSPORT', 'missing exact same-site/full-vector projection')
                self.add('transports', source_access=access['id'], projection_env=projection,
                         result_access=target, kind='project')

    def origin_guards(self, env):
        self.b.work()
        mode = self.t.tables['environments'][env]['mode']
        if mode == 'NEUTRAL':
            return N
        if mode in ('CONCRETE', 'CLOSED'):
            return C
        fail('metadata.boundaries', 'metadata-origin', 'ENVIRONMENT', 'unknown execution-origin mode')

    def identity_guards(self, code):
        self.b.work()
        return _mask(('return-identity',)) if code['kind'] == 'function' and code['expected_identity_flag'] == 1 else 0

    def boundary(self, key, ty, env, rule, guards):
        b = self.b
        b.creation()
        ordered = []
        for index, guard in enumerate(GUARDS):
            b.work()
            if guards & (1 << index):
                b.append(ordered, guard)
        if ty is not None:
            self.t.resolve(ty, env)  # required key, never guessed from a closed result
        return self.add('boundaries', key=key, principal_type=ty, resolution_env=env,
                        access_rule=rule, guards=ordered)['id']

    def associated_slots(self, obligation):
        """Resolve exact checked operand roles, with no fabricated opaque target."""
        b, r = self.b, self.r
        site, kind, role = obligation['host_site'], obligation['kind'], obligation['role']
        if site is None:
            return b.listing(())
        if type(site) is not int or not 0 <= site < len(r.tables['sites']):
            fail('metadata.coverage', 'metadata-closure', 'COVERAGE', 'obligation has a dangling host site')
        key = None
        if kind == 'publish':
            if role[0] == 'captures': key = key3(b, site, 'capture', role[1])
            elif role[0] == 'arms': key = key3(b, site, 'capture', role[3])
            elif role[0] in ('function', 'argument'): key = key2(b, site, role[0])
            elif role[0] == 'fields':
                key = key3(b, site, 'field' if r.tables['sites'][site]['category'] == 'DATA' else 'variant-field', role[1])
        elif kind == 'application_argument':
            key = key2(b, site, 'argument')
        elif kind == 'fill':
            key = key2(b, site, 'memo')
        elif kind == 'field_acquire':
            inst = instruction_at(self.raw, obligation['path'], b)
            key = key3(b, site, 'field', inst['field'])
        elif kind == 'force_result' and r.tables['sites'][site]['category'] in DEFERRED:
            key = key2(b, site, 'memo')
        if key is None:
            return b.listing(())
        if key not in self.slot_lookup:
            fail('metadata.coverage', 'metadata-closure', 'COVERAGE', 'actual host role has no exact slot')
        b.creation()  # singleton source record for the copied variable vector
        return b.listing((self.slot_lookup[key],))

    def obligation_rows(self):
        b, r, t = self.b, self.r, self.t
        for index, obligation in enumerate(self.d['obligations']):
            b.work()
            instruction_index = r.instruction_ids[path_key(obligation['path'], b)]
            checked = self.d['instructions'][instruction_index]
            for ref in obligation['operands']:
                b.work()
                if ref['instruction'] != instruction_index or ref['side'] not in ('inputs', 'outputs') or type(ref['index']) is not int or not 0 <= ref['index'] < len(checked[ref['side']]):
                    fail('metadata.boundaries', 'metadata-closure', 'FACT', 'obligation references a different checked operand')
            ty = t.old(obligation['expected_type'])
            slots = self.associated_slots(obligation)
            b.put(self.obligation_slots, index, slots)
            b.creation()
            ids = []
            for env in t.lawful_envs(obligation['path']):
                b.work()
                kind = obligation['kind']
                if kind == 'publish':
                    rule, guards = 'publish-by-host-origin', M | self.origin_guards(env) | L | Q
                    site = r.tables['sites'][obligation['host_site']]
                    if env not in t.lawful_envs(site['path']):
                        fail('metadata.boundaries', 'metadata-origin', 'CONTEXT', 'publication environment cannot allocate its host')
                elif kind == 'application_argument':
                    rule, guards = 'invoke-callee-origin', M | L | _mask(('code-association', 'application-slots'))
                elif kind == 'callback_return':
                    path = obligation['path']
                    code = None
                    for candidate in r.tables['codes']:
                        b.work()
                        if candidate['kind'] == path['root'] and candidate['name'] == path['name']:
                            code = candidate
                            break
                    if code is None:
                        fail('metadata.boundaries', 'metadata-origin', 'CODE', 'callback return has no enclosing code')
                    rule, guards = 'return-by-execution-origin', M | self.origin_guards(env) | L | RETURN | self.identity_guards(code)
                elif kind == 'fill':
                    # The sole conditional O(actual-host): N and C are mutually
                    # exclusive dynamic branches, not a simultaneous demand.
                    rule, guards = 'publish-by-host-origin', M | N | C | L | Q | _mask(('fill-linear-contract', 'state-category'))
                elif kind == 'field_acquire':
                    rule, guards = 'copy-actual', M | C | L | Q
                elif kind == 'force_result':
                    rule, guards = 'principal-dispatch', M | L | _mask(('state-category',))
                else:
                    fail('metadata.boundaries', 'metadata-closure', 'OBLIGATION', 'unknown checked obligation kind')
                key = b.row(kind='obligation', index=index, execution_env=env)
                b.append(ids, self.boundary(key, ty, env, rule, guards))
            b.put(self.obligation_boundaries, index, ids)

    def instruction_rows(self):
        b, r, t = self.b, self.r, self.t
        b.creation(2)
        intros_by_instruction, uses_by_instruction = {}, {}
        for intro, indices in r.intro_instructions.items():
            for index in indices:
                b.work(); b.put(intros_by_instruction, index, intro)
        for use, indices in r.use_instructions.items():
            for index in indices:
                b.work(); b.put(uses_by_instruction, index, use)
        for index, checked in enumerate(self.d['instructions']):
            b.work()
            op = checked['op']
            if op not in INSTRUCTION_OPS:
                continue
            if op == 'drop' and fact_at(checked, 'value', b)['kind'] != 'value':
                continue
            ty = env = None
            if op in ('generalize', 'seal'):
                intro = r.tables['introductions'][intros_by_instruction[index]]
                ty, env = intro['body_type'], t.neutral_env(intro['scheme'])
                if op == 'generalize':
                    rule, guards = 'begin-scope', _mask(('registered-membership', 'scope-token'))
                else:
                    rule, guards = 'seal-scheme', M | N | L | _mask(('scope-token', 'same-handle-view-move', 'owner-mode', 'ticket-free', 'no-dependent-loans', 'child-discharge'))
            elif op == 'instantiate':
                use = r.tables['uses'][uses_by_instruction[index]]
                ty, env = t.tables['schemes'][use['scheme']]['body'], use['env']
                rule, guards = 'instantiate-full-vector', A | _mask(('live-exact-anchor', 'complete-vector', 'same-handle-view-move', 'ticket-free', 'no-dependent-loans', 'scheme-input', 'view-move-mode'))
            elif op == 'retain':
                rule, guards = 'copy-actual', A | _mask(('live-exact-anchor', 'acquire-before-release'))
            elif op == 'borrow':
                rule, guards = 'copy-actual', A | _mask(('owner-mode', 'live-exact-anchor'))
            elif op == 'drop':
                rule, guards = 'release-actual', A | _mask(('owner-mode', 'no-dependent-loans'))
            elif op == 'end_borrow':
                rule, guards = 'release-actual', A | _mask(('live-exact-anchor',))
            elif op in ('select_i64', 'case_i64'):
                rule, guards = 'copy-actual', M | C | L | _mask(('owner-mode', 'no-dependent-loans'))
            else:
                rule, guards = 'copy-actual', M | C | L | Q
            boundary = self.boundary(b.row(kind='instruction', index=index), ty, env, rule, guards)
            b.put(self.instruction_boundaries, index, boundary)

    def slot_boundaries(self):
        b, r = self.b, self.r
        for site in r.tables['sites']:
            b.put(self.site_boundaries, site['id'], b.listing(()))
        for slot in self.tables['slots']:
            b.work()
            for execution_id in r.site_executions[slot['site']]:
                b.work()
                execution = r.tables['site_executions'][execution_id]
                env = execution['env']
                boundary = self.boundary(b.row(kind='slot', slot=slot['id'], site_execution=execution_id),
                    slot['type'], env, 'publish-by-host-origin', M | self.origin_guards(env) | L | Q)
                b.append(self.site_boundaries[slot['site']], boundary)

    def entry_return_rows(self):
        b, r, t = self.b, self.r, self.t
        for code in r.tables['codes']:
            b.put(self.code_boundaries, code['id'], b.listing(()))
        for execution in r.tables['code_executions']:
            b.work()
            code, env = r.tables['codes'][execution['code']], execution['env']
            mode = t.tables['environments'][env]['mode']
            cases = ('CONCRETE',) if mode == 'CONCRETE' else ('GENERIC_NEUTRAL',) if mode == 'NEUTRAL' else ('GENERIC_PROJECTED', 'INSTANCE') if code['kind'] == 'function' else ('INSTANCE',)
            for origin in cases:
                b.work()
                if code['kind'] == 'function':
                    guards = M | (N if origin == 'GENERIC_NEUTRAL' else C) | L | _mask(('code-association',))
                    if origin == 'GENERIC_PROJECTED':
                        guards |= _mask(('complete-vector',))
                    key = b.row(kind='entry', code_execution=execution['id'], origin_case=origin, role='argument', name=None)
                    boundary = self.boundary(key, code['argument'], env, 'invoke-callee-origin', guards)
                    b.append(self.code_boundaries[code['id']], boundary)
                for capture in code['captures']:
                    b.work()
                    guards = M | (N if origin in ('GENERIC_NEUTRAL', 'GENERIC_PROJECTED') else C) | L | Q | _mask(('code-association',))
                    rule = 'copy-actual'
                    if origin == 'GENERIC_PROJECTED':
                        guards |= _mask(('complete-vector',))
                        rule = 'transport-by-request'
                    key = b.row(kind='entry', code_execution=execution['id'], origin_case=origin, role='capture', name=capture['name'])
                    boundary = self.boundary(key, capture['type'], env, rule, guards)
                    b.append(self.code_boundaries[code['id']], boundary)
        for execution in r.tables['code_executions']:
            b.work()
            code, env = r.tables['codes'][execution['code']], execution['env']
            boundary = self.boundary(b.row(kind='return', code_execution=execution['id']), code['result'], env,
                'return-by-execution-origin', M | self.origin_guards(env) | L | RETURN | self.identity_guards(code))
            b.append(self.code_boundaries[code['id']], boundary)

    def deferred_rows(self):
        b, r, t = self.b, self.r, self.t
        for execution in r.tables['site_executions']:
            b.work()
            site, env = r.tables['sites'][execution['site']], execution['env']
            if site['category'] not in DEFERRED:
                continue
            for access_id in self.accesses_by_origin[key2(b, site['id'], env)]:
                b.work()
                access = self.tables['accesses'][access_id]
                if access['mode'] != 'MONO':
                    continue
                if access['type'] != t.resolve(site['principal_type'], access['use_env']):
                    fail('metadata.boundaries', 'metadata-closure', 'REQUEST', 'deferred request equation differs')
                for phase in DEFERRED[site['category']]:
                    b.work()
                    if phase in ('hole-demand', 'busy-demand'):
                        rule, guards = ('reject-hole' if phase == 'hole-demand' else 'reject-busy'), M | _mask(('state-category',))
                    elif phase == 'fill':
                        rule, guards = 'publish-by-host-origin', M | self.origin_guards(env) | L | Q | _mask(('fill-linear-contract', 'state-category'))
                    elif phase in ('indirect-dispatch', 'thunk-dispatch', 'application-dispatch'):
                        rule, guards = 'principal-dispatch', M | self.origin_guards(env) | L | Q | _mask(('state-category',))
                        if phase == 'thunk-dispatch': guards |= _mask(('code-association',))
                        if phase == 'application-dispatch': guards |= _mask(('application-slots',))
                    elif phase == 'cursor-return':
                        rule, guards = 'publish-by-host-origin', M | self.origin_guards(env) | L
                    elif phase == 'reverse-pending':
                        rule, guards = 'validate-principal-before-project', M | self.origin_guards(env) | L | _mask(('pending-all-before-publish',))
                    elif phase == 'memo-publish':
                        rule, guards = 'preserve-principal-memo', M | self.origin_guards(env) | L | Q | _mask(('pending-all-before-publish',))
                    else:
                        rule, guards = 'transport-by-request', M | self.origin_guards(env) | L | Q | _mask(('state-category',))
                    key = b.row(kind='deferred', site_execution=execution['id'], request_access=access_id, phase=phase)
                    boundary = self.boundary(key, site['principal_type'], env, rule, guards)
                    b.append(self.site_boundaries[site['id']], boundary)

    def coverage(self, source, boundaries, dependencies, slots):
        b, t = self.b, self.t
        b.creation(2)
        resolutions, seen_dependencies = set(), set()
        # Inputs are existing fixed pairs. Expand each exact type/environment
        # dependency only once, retaining first-seen traversal order. This is a
        # per-source temporary set, not a persistent cache or inferred Env.
        for dependency in dependencies:
            b.work()
            if dependency in seen_dependencies:
                continue
            b.add(seen_dependencies, dependency)
            ty, env = dependency
            for resolution in t.dependencies(ty, env):
                b.work(); b.add(resolutions, resolution)
        b.creation(2)
        unique_boundaries, unique_slots = set(), set()
        for row in boundaries:
            b.work(); b.add(unique_boundaries, row)
        for row in slots:
            b.work(); b.add(unique_slots, row)
        self.add('coverage', source=source, boundaries=b.ordered(unique_boundaries),
                 resolutions=b.ordered(resolutions), slots=b.ordered(unique_slots))

    def coverage_rows(self):
        b, r, t = self.b, self.r, self.t
        for index, obligation in enumerate(self.d['obligations']):
            b.work()
            b.creation()
            dependencies = []
            for env in t.lawful_envs(obligation['path']):
                self.dependency(dependencies, t.old(obligation['expected_type']), env)
            self.coverage(b.row(kind='obligation', index=index), self.obligation_boundaries[index], dependencies, self.obligation_slots[index])
        for index, boundary_id in self.instruction_boundaries.items():
            b.work()
            boundary = self.tables['boundaries'][boundary_id]
            b.creation()
            dependencies = []
            if boundary['principal_type'] is not None:
                self.dependency(dependencies, boundary['principal_type'], boundary['resolution_env'])
            b.creation(2)  # singleton boundary vector
            self.coverage(b.row(kind='instruction', index=index), (boundary_id,), dependencies, ())
        for code in r.tables['codes']:
            b.work()
            b.creation(2)
            dependencies, slots = [], []
            b.creation()
            principal = b.listing((code['result'],))
            if code['callable_type'] is not None:
                b.append(principal, code['callable_type']); b.append(principal, code['argument'])
            for capture in code['captures']:
                b.work(); b.append(principal, capture['type'])
            for env in t.envs_for_scope(code['scope']):
                for ty in principal:
                    b.work(); self.dependency(dependencies, ty, env)
                    resolved = t.resolve(ty, env)
                    self.dependency(dependencies, resolved, 0 if t.closed(resolved) else env)
            for site in r.tables['sites']:
                b.work()
                if site['code'] == code['id']:
                    for slot in self.slots_by_site[site['id']]:
                        b.append(slots, slot)
            self.coverage(b.row(kind='code', code=code['id']), self.code_boundaries[code['id']], dependencies, slots)
        for site in r.tables['sites']:
            b.work()
            b.creation()
            dependencies = []
            boundaries = b.listing(self.site_boundaries[site['id']])
            for execution_id in r.site_executions[site['id']]:
                execution = r.tables['site_executions'][execution_id]
                env = execution['env']
                self.dependency(dependencies, site['principal_type'], env)
                for slot_id in self.slots_by_site[site['id']]:
                    b.work(); self.dependency(dependencies, self.tables['slots'][slot_id]['type'], env)
            for access in self.tables['accesses']:
                b.work()
                if access['site'] == site['id'] and access['mode'] == 'MONO':
                    self.dependency(dependencies, site['principal_type'], access['use_env'])
            for index, obligation in enumerate(self.d['obligations']):
                b.work()
                if obligation['host_site'] == site['id'] and obligation['kind'] in ('publish', 'application_argument'):
                    for boundary in self.obligation_boundaries[index]:
                        b.append(boundaries, boundary)
            self.coverage(b.row(kind='site', site=site['id']), boundaries, dependencies, self.slots_by_site[site['id']])
        for intro in r.tables['introductions']:
            b.work()
            env = t.neutral_env(intro['scheme'])
            b.creation(2)
            dependencies, boundaries = [], []
            self.dependency(dependencies, intro['body_type'], env)
            for ty in t.tables['environments'][env]['arguments']:
                b.work(); self.dependency(dependencies, ty, env)
            for index in r.intro_instructions[intro['id']]:
                b.append(boundaries, self.instruction_boundaries[index])
            for access in self.tables['accesses']:
                b.work()
                if access['site'] in intro['result_sites']:
                    site = r.tables['sites'][access['site']]
                    self.dependency(dependencies, site['principal_type'], env if access['mode'] == 'SCHEME' else access['use_env'])
            self.coverage(b.row(kind='intro', intro=intro['id']), boundaries, dependencies, ())
        for use in r.tables['uses']:
            b.work()
            b.creation(2)
            dependencies, boundaries = [], []
            self.dependency(dependencies, t.tables['schemes'][use['scheme']]['body'], use['env'])
            for ty in use['arguments']:
                b.work(); self.dependency(dependencies, ty, 0)
            for index in r.use_instructions[use['id']]:
                b.append(boundaries, self.instruction_boundaries[index])
            self.coverage(b.row(kind='use', use=use['id']), boundaries, dependencies, ())


def build_edges(representations):
    result = EdgeClosure(representations)
    result.slot_rows()
    result.access_rows()
    result.obligation_rows()
    result.instruction_rows()
    result.slot_boundaries()
    result.entry_return_rows()
    result.deferred_rows()
    result.coverage_rows()
    return result
