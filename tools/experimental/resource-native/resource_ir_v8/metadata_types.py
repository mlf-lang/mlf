"""Fresh bounded flat Type DAG and complete lexical substitution closure.

Only privately fresh Stage02 artifacts are adapted. No runtime, source bridge,
producer metadata admission or recursive expanded type hashing is involved. The
invocation-local TypeClosure is discarded when the immutable public result is
built; its maps are not an authorization cache and are never retained there.
"""
from __future__ import annotations

from functools import cmp_to_key
import json

from .program_schema import INSTANCE_SCALAR_OPS
from .provenance import CLOSED_ENTRY_POLICY, CALLABLE_ENTRY_POLICY

from .metadata_budget import (fail, TYPE_LIMIT, TYPE_DEPTH, ENVIRONMENT_LIMIT,
                              _compare)

TYPE_FIELDS = ('id', 'tag', 'atom', 'scheme', 'index', 'argument', 'result',
               'protocol', 'result_identity')
TYPE_TABLES = ('type_remap', 'environment_remap', 'types', 'callable_contracts',
               'schemes', 'environments', 'type_resolutions')


def _error(path, code, message):
    fail(path, 'metadata-type', code, message)


def _integer(value, count, path):
    if type(value) is not int or not 0 <= value < count:
        _error(path, 'REFERENCE', 'expected an in-range plain integer reference')
    return value


def _exact(row, keys, path):
    if type(row) is not dict or len(row) != len(keys) or any(key not in row for key in keys):
        _error(path, 'SCHEMA', 'record differs from the exact type schema')


def _registered_nominal_atom(raw, atom, budget):
    """Exact checked physical identity, only after the unchanged scalar path.

    Parameter-free source admission belongs to the source declaration proof.
    These raw IR maps already describe closed DATA/SUM descriptors; neither an
    arbitrary CLOSED tag nor a similarly shaped descriptor is sufficient.
    """
    budget.work()
    if type(atom) is not str:
        return False
    budget.work(len(atom))
    if atom.startswith('%'):
        budget.creation()  # suffix used for the exact family-map lookup
        return atom[1:] in raw['families']
    return atom in raw['layouts']


def _closed_arrow_argument(bank, root, checked, budget):
    """Check a new arrow coordinate through flat IDs, once per reachable node.

    The bank already checked child topology, depth and physical identities.
    This additional admission rule forbids rigids and argument-identity arrows
    at every depth. The local set is allocated only for an arrow-vector path.
    """
    budget.work()
    if root in checked:
        return
    budget.creation()
    pending = []
    budget.add(checked, root)
    budget.append(pending, root)
    while pending:
        value = pending.pop()
        budget.work()
        node = bank.nodes[value]
        if node[0] == 'closed':
            if node[1] not in ('#bool', '#i64') and not _registered_nominal_atom(bank.raw, node[1], budget):
                _error('metadata.uses', 'VECTOR', 'arrow argument leaf has no exact physical declaration')
        elif node[0] == 'arrow' and node[3] == 'repeat' and node[4] == 'unknown' and bank.scopes[value] == 0:
            for offset in range(1, 3):
                budget.work()
                child = node[offset]
                if child not in checked:
                    budget.add(checked, child)
                    budget.append(pending, child)
        else:
            _error('metadata.uses', 'VECTOR', 'arrow arguments require recursively closed Repeat/unknown contracts')


def _verify_arrow_argument(raw, types, root, checked, budget):
    """Independent row-based admission; check each child before dereferencing.

    Do not use the builder's scope/contract facts or its retained flat nodes.
    Strictly earlier child IDs establish acyclicity before the subsequent
    forward pass independently verifies depth, null domains and all equations.
    """
    budget.work()
    if root in checked:
        return
    budget.creation()
    pending = []
    budget.add(checked, root)
    budget.append(pending, root)
    while pending:
        value = pending.pop()
        budget.work()
        row = types[value]
        _exact(row, TYPE_FIELDS, 'metadata.types')
        if type(row['id']) is not int or row['id'] != value:
            _error('metadata.types', 'REFERENCE', 'argument Type ID differs from its position')
        if row['tag'] == 'closed':
            if row['atom'] not in ('#bool', '#i64') and not _registered_nominal_atom(raw, row['atom'], budget):
                _error('metadata.environments', 'VECTOR', 'arrow argument leaf has no exact physical declaration')
        elif row['tag'] == 'arrow' and row['protocol'] == 'repeat' and row['result_identity'] == 'unknown':
            for field in ('argument', 'result'):
                budget.work()
                child = _integer(row[field], value, 'metadata.environments')
                if child not in checked:
                    budget.add(checked, child)
                    budget.append(pending, child)
        else:
            _error('metadata.environments', 'VECTOR', 'arrow arguments require recursively closed Repeat/unknown contracts')


def _node(row, scheme_names, path):
    _exact(row, TYPE_FIELDS, path)
    tag = row['tag']
    if tag == 'closed':
        if type(row['atom']) is not str or any(row[key] is not None for key in
                ('scheme', 'index', 'argument', 'result', 'protocol', 'result_identity')):
            _error(path, 'TYPE', 'closed node has illegal payload/null domains')
        return ('closed', row['atom'])
    if tag == 'rigid':
        if row['scheme'] not in scheme_names or type(row['index']) is not int:
            _error(path, 'SCOPE', 'rigid requires its exact scheme and parameter')
        if any(row[key] is not None for key in ('atom', 'argument', 'result', 'protocol', 'result_identity')):
            _error(path, 'TYPE', 'rigid node has illegal null domains')
        return ('rigid', row['scheme'], row['index'])
    if tag == 'arrow':
        if any(row[key] is not None for key in ('atom', 'scheme', 'index')):
            _error(path, 'TYPE', 'arrow node has illegal null domains')
        if row['protocol'] not in ('repeat', 'once') or row['result_identity'] not in ('unknown', 'argument'):
            _error(path, 'CONTRACT', 'unknown callable contract')
        return ('arrow', row['argument'], row['result'], row['protocol'], row['result_identity'])
    _error(path, 'TYPE', 'unknown Type tag')


class _Bank:
    __slots__ = ('budget', 'nodes', 'lookup', 'depths', 'scopes', 'scheme_map', 'raw')

    def __init__(self, raw, derived, budget, scheme_map):
        self.budget, self.raw, self.scheme_map = budget, raw, scheme_map
        budget.creation(5)
        self.nodes, self.lookup, self.depths, self.scopes = [], {}, [], []
        # Subset precedence is over the COMPLETE checked original inventory.
        for index, row in enumerate(derived['types']):
            budget.work()
            if row['tag'] == 'arrow' and row['protocol'] == 'once':
                fail(f'metadata.types[{index}].protocol', 'metadata-subset', 'ONCE',
                     'the complete metadata target requires Repeat at every arrow')
        for index, row in enumerate(derived['types']):
            path = f'metadata.types[{index}]'
            budget.work()
            if type(row['id']) is not int or row['id'] != index:
                _error(path, 'REFERENCE', 'fresh resource Type IDs must be contiguous')
            budget.creation()  # flat temporary key record
            node = _node(row, scheme_map, path)
            found = self.intern(node, path)
            if found != index:
                _error(path, 'DUPLICATE_TYPE', 'fresh resource Types must be unique and topological')

    def intern(self, node, path):
        b = self.budget
        b.work()  # exact flat-key lookup; never hashes a nested type tree
        found = self.lookup.get(node)
        if found is not None:
            return found
        if len(self.nodes) >= TYPE_LIMIT:
            fail('metadata.types', 'metadata-bounds', 'TYPE_COUNT', 'fresh Type bank exceeds 4096 nodes')
        if node[0] == 'arrow':
            argument = _integer(node[1], len(self.nodes), path)
            result = _integer(node[2], len(self.nodes), path)
            b.work(2)
            depth = 1 + max(self.depths[argument], self.depths[result])
            scope = self.scopes[argument] | self.scopes[result]
            if node[3] != 'repeat':
                fail(path, 'metadata-subset', 'ONCE', 'new arrows must preserve Repeat')
            if node[4] not in ('unknown', 'argument') or (node[4] == 'argument' and argument != result):
                _error(path, 'CONTRACT', 'invalid exact result-identity contract')
        elif node[0] == 'rigid':
            scheme, parameter = node[1], node[2]
            if scheme not in self.scheme_map or type(parameter) is not int or not 0 <= parameter < self.raw['schemes'][scheme]['parameters']:
                _error(path, 'SCOPE', 'rigid outside its complete lexical prefix')
            depth, scope = 1, 1 << self.scheme_map[scheme]
        elif node[0] == 'closed':
            atom = node[1]
            if (atom not in ('#i64', '#bool') and atom not in self.raw['layouts']
                    and not (atom.startswith('%') and atom[1:] in self.raw['families'])):
                _error(path, 'ATOM', 'closed atom is not an exact checked physical identity')
            depth, scope = 1, 0
        else:
            _error(path, 'TYPE', 'unknown flat type constructor')
        if depth > TYPE_DEPTH:
            fail(path, 'metadata-bounds', 'TYPE_DEPTH', 'fresh Type DAG depth exceeds 32')
        b.creation(4)  # node/lookup/depth/scope memberships, key already charged
        found = len(self.nodes)
        self.nodes.append(node)
        self.lookup[node] = found
        self.depths.append(depth)
        self.scopes.append(scope)
        return found


def _raw_references(raw, bank, budget):
    """Re-resolve the checked raw declaration grammar using flat integer keys.

    This independently binds physical aliases and ^ names to the original fresh
    bank. It never reruns a body or invokes the old executable package.
    """
    budget.creation(4)
    references, definitions, complete, active = {}, {}, {}, set()

    def atom(reference):
        budget.work()
        budget.creation()  # temporary flat atom lookup key
        value = bank.lookup.get(('closed', reference))
        if value is None:
            _error('metadata.references', 'ATOM', 'raw physical atom absent from fresh Type bank')
        return value

    def dependency(reference):
        if reference.startswith('^'):
            return ('type', reference[1:])
        if reference.startswith('@'):
            return ('signature', reference[1:])
        return atom(reference)

    for value in ('#bool', '#i64'):
        budget.put(references, value, atom(value))
    for value in budget.ordered(raw['layouts']):
        budget.put(references, value, atom(value))
    for value in budget.ordered(raw['families']):
        budget.creation()
        name = '%' + value
        budget.put(references, name, atom(name))
    for name in budget.ordered(raw['types']):
        spec = raw['types'][name]
        budget.creation()  # namespace/name key
        key = ('type', name)
        budget.work()
        if spec['tag'] == 'closed':
            budget.put(complete, key, atom(spec['layout']))
        elif spec['tag'] == 'rigid':
            budget.creation()
            value = bank.lookup.get(('rigid', spec['scheme'], spec['index']))
            if value is None:
                _error('types.' + name, 'REFERENCE', 'declared rigid missing from fresh bank')
            budget.put(complete, key, value)
        else:
            budget.creation(3)
            budget.put(definitions, key, (('type', spec['argument']), ('type', spec['result']), spec))
    for name in budget.ordered(raw['signatures']):
        spec = raw['signatures'][name]
        budget.creation(4)  # key, definition, at most two dependency records
        budget.put(definitions, ('signature', name),
                   (dependency(spec['argument']), dependency(spec['result']), spec))
    for root in budget.ordered(definitions):
        budget.creation(3)
        pending = [(root, False)]
        while pending:
            key, leaving = pending.pop()
            budget.work()
            if key in complete:
                continue
            if key not in definitions:
                _error('metadata.references', 'REFERENCE', 'unknown raw declaration dependency')
            left, right, spec = definitions[key]
            if leaving:
                a = left if type(left) is int else complete[left]
                r = right if type(right) is int else complete[right]
                budget.creation()
                value = bank.lookup.get(('arrow', a, r, spec['protocol'], spec['result_identity']))
                if value is None:
                    _error('metadata.references', 'REFERENCE', 'raw callable equation absent from fresh Type bank')
                budget.put(complete, key, value)
                active.remove(key)
            else:
                if key in active:
                    _error('metadata.references', 'CYCLE', 'raw callable declaration cycle')
                budget.add(active, key)
                budget.creation(2)
                pending.append((key, True))
                for child in (right, left):
                    budget.work()
                    if type(child) is not int and child not in complete:
                        budget.creation(2)
                        pending.append((child, False))
    for (kind, name), value in complete.items():
        budget.work()
        budget.creation()
        budget.put(references, ('^' if kind == 'type' else '@') + name, value)
    return references


def _environment_rows(raw, derived, bank, references, scheme_map, budget):
    budget.creation(4)
    rows, remap, neutral, by_scope = [], {}, {}, {}
    budget.record_append(rows, id=0, scheme=None, mode='CONCRETE', arguments=[])
    budget.creation()  # E0 empty argument vector
    budget.put(remap, 'E0', 0)
    checked_arguments = None
    for name in budget.ordered(raw['schemes']):
        scheme = scheme_map[name]
        spec = raw['schemes'][name]
        budget.creation()
        vector = []
        for parameter in range(spec['parameters']):
            budget.work()
            budget.creation()
            value = bank.lookup.get(('rigid', name, parameter))
            if value is None:
                _error('metadata.environments', 'VECTOR', 'complete neutral parameter missing')
            budget.append(vector, value)
        if len(rows) >= ENVIRONMENT_LIMIT:
            fail('metadata.environments', 'metadata-bounds', 'ENVIRONMENT_COUNT', 'complete environment count exceeds 1024')
        env = len(rows)
        budget.record_append(rows, id=env, scheme=scheme, mode='NEUTRAL', arguments=vector)
        budget.put(neutral, scheme, env)
        budget.creation(2)
        budget.put(by_scope, scheme, [env])
        budget.creation()
        budget.put(remap, 'E' + str(env), env)
        budget.creation()
        vectors = set()
        nominal_vectors = False
        arrow_vectors = False
        for use in derived['uses']:
            budget.work()
            if use['scheme'] == name:
                expected = raw['instantiations'].get(use['name'])
                if expected is None or expected['scheme'] != name:
                    _error('metadata.uses', 'USE', 'fresh use differs from raw descriptor')
                budget.reserve(creation=1 + len(expected['arguments']), work=2 * len(expected['arguments']))
                exact = tuple(references['^' + ref] for ref in expected['arguments'])
                if len(exact) != spec['parameters'] or len(exact) != len(use['arguments']) or any(a != b for a, b in zip(exact, use['arguments'])):
                    _error('metadata.uses', 'VECTOR', 'fresh use lost its complete ordered vector')
                for value in exact:
                    budget.work()
                    node = bank.nodes[value]
                    if node[0] == 'arrow':
                        if checked_arguments is None:
                            budget.creation()
                            checked_arguments = set()
                        _closed_arrow_argument(bank, value, checked_arguments, budget)
                        arrow_vectors = True
                        continue
                    if node[0] != 'closed':
                        _error('metadata.uses', 'VECTOR', 'closed vectors require registered intrinsic, DATA or SUM atoms')
                    if node[1] not in ('#bool', '#i64'):
                        if not _registered_nominal_atom(raw, node[1], budget):
                            _error('metadata.uses', 'VECTOR', 'closed vector atom has no exact physical declaration')
                        nominal_vectors = True
                budget.add(vectors, exact)
        if arrow_vectors:
            # These are original freshly checked canonical Type IDs, before
            # substitution appends any nodes. They are whole-Type ranks, not
            # arbitrary child-ID structural keys. Later canonical insertion
            # preserves their relative order and therefore the exact Env IDs.
            ordered = budget.ordered(vectors)
        elif nominal_vectors:
            # Every admitted coordinate is an atomic depth-one closed Type.
            # Canonical Type order compares JSON-encoded atom strings, not raw
            # strings (which disagree for escaped/control names). Cache only
            # scalar encodings, never an expanded type tree or inferred Env.
            budget.creation()
            atom_keys = {}
            for vector in vectors:
                for value in vector:
                    budget.work()
                    if value not in atom_keys:
                        atom = bank.nodes[value][1]
                        budget.reserve(creation=1, work=len(atom))
                        encoded = json.dumps(atom, ensure_ascii=False, separators=(',', ':'))
                        budget.put(atom_keys, value, encoded)
            ordered = budget.ordered(vectors, key=lambda vector: tuple(atom_keys[x] for x in vector),
                                     key_units=lambda vector: 1 + len(vector))
        else:
            # Preserve the scalar-only encoding, comparator and work path.
            ordered = budget.ordered(vectors, key=lambda vector: tuple(bank.nodes[x][1] for x in vector),
                                     key_units=lambda vector: 1 + len(vector))
        for vector in ordered:
            if len(rows) >= ENVIRONMENT_LIMIT:
                fail('metadata.environments', 'metadata-bounds', 'ENVIRONMENT_COUNT', 'complete environment count exceeds 1024')
            env = len(rows)
            budget.record_append(rows, id=env, scheme=scheme, mode='CLOSED', arguments=budget.listing(vector))
            budget.append(by_scope[scheme], env)
            budget.creation()
            budget.put(remap, 'E' + str(env), env)
    if len(rows) != derived['counts']['environments']:
        _error('metadata.environments', 'ENVIRONMENT', 'complete fresh environment inventory differs')
    for use in derived['uses']:
        budget.work()
        env = remap.get(use['environment'])
        budget.work(len(use['arguments']))
        if env is None or rows[env]['scheme'] != scheme_map[use['scheme']] or rows[env]['arguments'] != use['arguments']:
            _error('metadata.environment_remap', 'ENVIRONMENT', 'Stage02 environment identity is not preserved')
    return rows, remap, neutral, by_scope


def _path_key(path, budget):
    budget.work()
    budget.creation(2 + len(path['segments']))
    return path['root'], path['name'], tuple(path['segments'])


class TypeClosure:
    """Private mutable construction context, not a public acceptance object."""
    __slots__ = ('tables', 'type_map', 'env_map', 'scheme_map', 'references',
                 'contracts', 'contract_by_type', 'scopes', 'resolution_ids',
                 'resolution_results', '_budget', '_raw', '_derived', '_neutral',
                 '_by_scope', '_path_contexts', '_roots', '_nodes', '_depths', '_closed_entries')

    def old_type(self, source):
        self._budget.work()
        return self.type_map[_integer(source, len(self.type_map), 'metadata.type_remap')]

    old = old_type

    def reference(self, reference, scope=None):
        self._budget.work()
        value = self.references.get(reference)
        if value is None:
            _error('metadata.references', 'REFERENCE', 'unknown checked raw type reference')
        scheme = self._scheme(scope)
        allowed = 0 if scheme is None else 1 << scheme
        if self.scopes[value] & ~allowed:
            _error('metadata.references', 'SCOPE', 'raw reference has foreign rigid scope')
        return value

    def _scheme(self, scope):
        if scope is None:
            return None
        if type(scope) is str:
            if scope not in self.scheme_map:
                _error('metadata.schemes', 'SCOPE', 'unknown scheme name')
            return self.scheme_map[scope]
        return _integer(scope, len(self.scheme_map), 'metadata.schemes')

    def closed(self, type_id):
        self._budget.work()
        return self.scopes[_integer(type_id, len(self.scopes), 'metadata.types')] == 0

    def envs_for_scope(self, scope):
        self._budget.work()
        scheme = self._scheme(scope)
        return (0,) if scheme is None else self._by_scope[scheme]

    def neutral_env(self, scope):
        self._budget.work()
        return self._neutral[self._scheme(scope)]

    def closed_envs(self, scope):
        environments = self.envs_for_scope(scope)
        self._budget.creation(1 + max(0, len(environments) - 1))
        return environments[1:]

    def resolve(self, type_id, env):
        self._budget.work()
        _integer(type_id, len(self.scopes), 'metadata.type_resolutions')
        _integer(env, len(self.tables['environments']), 'metadata.type_resolutions')
        self._budget.creation()
        result = self.resolution_results.get((type_id, env))
        if result is None:
            _error('metadata.type_resolutions', 'MISSING_RESOLUTION', 'required lexical substitution is absent')
        return result

    def dependencies(self, type_id, env):
        """Exact recursively included principal and resolved-E0 dependencies."""
        b = self._budget
        b.creation(4)
        visited, pending = set(), [(type_id, env)]
        while pending:
            key = pending.pop()
            b.work()
            if key in visited:
                continue
            if key not in self.resolution_ids:
                _error('metadata.type_resolutions', 'MISSING_RESOLUTION', 'missing recursive dependency')
            b.add(visited, key)
            node = self._nodes[key[0]]
            if node[0] == 'arrow':
                for child in (node[1], node[2]):
                    b.work()
                    b.creation(2)
                    # A resolved closed arrow is visited at E0 below. Its
                    # children inherit that popped key's environment, never
                    # the environment of the original principal request.
                    pending.append((child, key[1]))
            result = self.resolution_results[key]
            if not self.scopes[result] and (result, 0) != key:
                b.creation(2)
                pending.append((result, 0))
        ordered = b.ordered(visited, key=lambda item: self.resolution_ids[item], key_units=0)
        b.creation(1 + len(ordered))
        return tuple(self.resolution_ids[item] for item in ordered)

    def context_for_path(self, path):
        """Re-resolve the actual raw path, then bind exact enclosing context."""
        b = self._budget
        key = _path_key(path, b)
        context = self._path_contexts.get(key)
        if context is None:
            fail('metadata.path', 'metadata-origin', 'PATH', 'path is not a freshly checked instruction/body')
        return b.row(**context)

    def execution_envs(self, path):
        """Invocation premises only; lawful_envs retains complete typing rows."""
        if self._closed_entries is None:
            return self.lawful_envs(path)
        context = self.context_for_path(path)
        if context['kind'] == 'execution' and context['scheme'] in self._closed_entries:
            return self.closed_envs(context['scheme'])
        return self.lawful_envs(path)

    def instance_only_code(self, code):
        if self._closed_entries is None:
            return False
        self._budget.work()
        return code['scope'] in self._closed_entries

    def executable_site_env(self, site, env):
        if self._closed_entries is None:
            return True
        self._budget.work()
        return not (site['context']['kind'] == 'execution'
                    and site['scope'] in self._closed_entries
                    and self.tables['environments'][env]['mode'] == 'NEUTRAL')

    def lawful_envs(self, path):
        context = self.context_for_path(path)
        if context['kind'] == 'introduction':
            intro = self._derived['introductions'][context['intro']]
            self._budget.creation(2)
            return (self.neutral_env(intro['scheme']),)
        if context['kind'] == 'execution':
            return self.envs_for_scope(context['scheme'])
        return (0,)


def scalar_arrow_rows(types, root, b):
    """Independent bounded canonical-row proof, not a root tag shortcut."""
    if type(root) is not int or not 0 <= root < len(types) or types[root]['tag'] != 'arrow': return False
    b.creation(2); stack, depths = [(root, False)], {}
    while stack:
        b.work(); value, done = stack.pop()
        if value in depths: continue
        row = types[_integer(value, len(types), 'metadata.imports')]
        if row['tag'] == 'closed':
            if row['atom'] not in ('#i64', '#bool'): return False
            b.put(depths, value, 1)
        elif row['tag'] == 'arrow' and row['protocol'] == 'repeat' and row['result_identity'] == 'unknown':
            a, z = row['argument'], row['result']
            if type(a) is not int or type(z) is not int or not 0 <= a < value or not 0 <= z < value: return False
            if done:
                depth = 1 + max(depths[a], depths[z])
                if depth > TYPE_DEPTH: return False
                b.put(depths, value, depth)
            else:
                b.append(stack, (value, True)); b.append(stack, (z, False)); b.append(stack, (a, False))
        else: return False
        if len(depths) > TYPE_LIMIT: return False
    return True


def _contexts(raw, derived, scheme_map, budget, closure):
    """Validate raw paths independently of the type/free-variable appearance."""
    budget.creation(4)
    code_lookup, intros, result, instruction_paths = {}, {}, {}, set()
    effects = None
    claimed = False
    for code in derived['code_typing']:
        budget.work()
        budget.creation()
        budget.put(code_lookup, (code['kind'], code['name']), code)
    for intro in derived['introductions']:
        budget.work()
        claimed = claimed or 'closed_entry' in intro
        budget.put(intros, _path_key(intro['generalize_path'], budget), intro)
    # Explicit traversal checks every actual instruction path, including generalize
    # and its body. No printed SSA name is used as an allocation origin.
    budget.creation()
    roots = [(raw['entry'], 'entry', None, None)]
    budget.creation(2)
    for code in derived['code_typing']:
        mapping = raw['functions'] if code['kind'] == 'function' else raw['codes']
        spec = mapping.get(code['name'])
        if spec is None or spec['type_scope'] != code['type_scope']:
            fail('metadata.codes', 'metadata-origin', 'CODE_SCOPE', 'code scope differs from fresh raw declaration')
        budget.creation(2)
        roots.append((spec['body'], code['kind'], code['name'], code))
    for body, kind, name, code in roots:
        if code is not None and code['type_scope'] is not None:
            context = budget.row(kind='execution', code=code['id'], scheme=scheme_map[code['type_scope']])
        else:
            context = budget.row(kind='concrete')
        body_path = budget.row(root=kind, name=name, segments=[])
        budget.creation()
        budget.put(result, _path_key(body_path, budget), context)
        budget.creation(3)
        pending = [(body, (), context)]
        while pending:
            block, prefix, active_context = pending.pop()
            for index, instruction in enumerate(block):
                budget.work()
                budget.creation(2 + len(prefix))
                segments = prefix + (index,)
                key = (kind, name, segments)
                budget.put(result, key, active_context)
                budget.add(instruction_paths, key)
                if active_context['kind'] == 'execution' and instruction['op'] in INSTANCE_SCALAR_OPS:
                    if effects is None:
                        budget.creation(); effects = {}
                    scope = active_context['scheme']
                    if scope not in effects: budget.put(effects, scope, budget.listing(()))
                    budget.append(effects[scope], key)
                if instruction['op'] == 'generalize':
                    intro = intros.get(key)
                    if intro is None or intro['scheme'] != instruction['scheme'] or active_context['kind'] != 'concrete':
                        fail('metadata.introductions', 'metadata-origin', 'INTRO_CONTEXT', 'introduction differs from raw lexical context')
                    expected_container = None if code is None else code['id']
                    if intro['container'] != expected_container:
                        fail('metadata.introductions', 'metadata-origin', 'INTRO_CONTEXT', 'introduction container differs')
                    for contract in instruction.get('imports', {}).values():
                        reference = contract['layout']
                        if raw['types'][reference[1:]]['tag'] == 'arrow':
                            ty = closure.reference(reference)
                            if not scalar_arrow_rows(closure.tables['types'], ty, budget):
                                _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import full scalar-arrow contract differs')
                            if effects is None: budget.creation(); effects = {}
                            scope = scheme_map[intro['scheme']]
                            if scope not in effects: budget.put(effects, scope, budget.listing(()))
                    nested = budget.row(kind='introduction', intro=intro['id'])
                    budget.creation(3 + len(segments))
                    pending.append((instruction['body'], segments + ('body',), nested))
    if len(instruction_paths) != len(derived['instructions']):
        fail('metadata.instructions', 'metadata-origin', 'PATH', 'fresh instruction path count differs from raw syntax')
    for instruction in derived['instructions']:
        key = _path_key(instruction['path'], budget)
        budget.work()
        if key not in instruction_paths:
            fail('metadata.instructions', 'metadata-origin', 'PATH', 'fresh instruction absent from raw syntax')
        context = result[key]
        scope = None if context['kind'] == 'concrete' else (derived['introductions'][context['intro']]['scheme']
                    if context['kind'] == 'introduction' else derived['code_typing'][context['code']]['type_scope'])
        if instruction['type_scope'] != scope:
            fail('metadata.instructions', 'metadata-origin', 'SCOPE', 'instruction lexical scope differs from actual raw body')
    if effects is None and claimed:
        _error('metadata.closed_entry', 'CLOSED_ENTRY', 'unexpected effect proof on an old scope')
    closure._closed_entries = effects
    return result


def _callable_import_rows(raw, derived, closure, current, parent, b):
    """Bind new imports to raw closure allocation, complete Type and alias facts."""
    result = None
    for position, name in enumerate(sorted(current.get('imports', {})), 1):
        contract = current['imports'][name]
        if raw['types'][contract['layout'][1:]]['tag'] != 'arrow': continue
        if result is None: result = b.listing(())
        b.work(32 + len(name)); b.creation(3)
        old, alias = parent['inputs'][position], parent['outputs'][position]
        if (old['role'] != ['imports', name, 'value'] or alias['role'] != ['imports', name]
                or old['kind'] != 'value' or old['mode'] != 'own' or old['view'] != 'MONO'
                or old['projection'] is not None or old['scheme'] is not None or old['anchor'] is not None
                or old['ticket'] is not False or old['ready'] is not True):
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import requires a ready unprojected MONO owner')
        for key in old:
            b.work()
            if key not in ('role', 'capability', 'storage'):
                _equal_tree(old[key], alias[key], b, 'metadata.closed_entry')
        for key in ('capability', 'storage'):
            if type(alias[key]) is not int or alias[key] < 0 or alias[key] == old[key]:
                _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import alias is not fresh')
        ty = closure.reference(contract['layout'])
        if ty != closure.old(old['type']) or not scalar_arrow_rows(closure.tables['types'], ty, b):
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import exact full Type mismatch')
        prov = derived['provenance'][_integer(old['provenance'], len(derived['provenance']), 'metadata.closed_entry')]['value']
        if prov.get('kind') != 'allocated' or prov.get('context') != {'kind':'concrete'}:
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import is not a concrete allocation')
        site = derived['sites'][_integer(prov.get('site'), len(derived['sites']), 'metadata.closed_entry')]
        if site['type_scope'] is not None or site['category'] != 'CLOSURE' or site['principal_type'] != old['type']:
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import has wrong Site/category/Type')
        code = derived['code_typing'][_integer(site['code'], len(derived['code_typing']), 'metadata.closed_entry')]
        if code['kind'] != 'function' or code['type_scope'] is not None or code['callable_type'] != old['type']:
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import has wrong registered Code')
        spec = raw['functions'][code['name']]
        if spec['type_scope'] is not None or closure.reference('@' + spec['signature']) != ty:
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'raw concrete Code full contract differs')
        path = site['path']
        inst = raw['entry'] if path['root'] == 'entry' else raw['functions' if path['root'] == 'function' else 'codes'][path['name']]['body']
        for part in path['segments']: b.work(); inst = inst[part]
        if inst['op'] != 'closure' or inst['function'] != code['name']:
            _error('metadata.closed_entry', 'CLOSED_ENTRY', 'callable import raw allocation differs')
        b.append(result, b.row(binding=name, input=position, output=position, type=old['type'], site=site['id'], code=code['id']))
    return result


def _closed_entry_proofs(raw, derived, closure, effects, b):
    """Independently rebuild raw lexical allocation reachability and owner flow.

    Resource proof fields are compared only after this derivation. They do not
    authorize operations. Native typing tables remain complete, including rows
    that this static proof excludes from executable invocation coverage.
    """
    if effects is None:
        return None
    b.creation(4)
    result, records, lookup, raw_codes = {}, {}, {}, {}
    for i, rec in enumerate(derived['instructions']):
        b.work(); b.put(records, _path_key(rec['path'], b), (i, rec))
    for code in derived['code_typing']:
        b.work(); b.put(lookup, (code['kind'], code['name']), code['id'])
        b.put(raw_codes, code['id'], raw['functions' if code['kind'] == 'function' else 'codes'][code['name']])
    # Do not let a forged lower inventory hide an unused raw declaration.
    b.work(len(raw['functions']) + len(raw['codes']))
    if len(lookup) != len(raw['functions']) + len(raw['codes']):
        _error('metadata.closed_entry', 'CLOSED_ENTRY', 'raw and derived Code census differ')
    for kind, bank in (('function', raw['functions']), ('thunk', raw['codes'])):
        for name, spec in bank.items():
            b.reserve(creation=1, work=1)
            code_id = lookup.get((kind, name))
            if code_id is None:
                _error('metadata.closed_entry', 'CLOSED_ENTRY', 'raw Code declaration omitted')
            row = derived['code_typing'][_integer(code_id, len(derived['code_typing']), 'metadata.closed_entry')]
            if row['type_scope'] != spec['type_scope']:
                _error('metadata.closed_entry', 'CLOSED_ENTRY', 'raw Code scope differs from proof inventory')
    for intro in derived['introductions']:
        b.work()
        scope = closure.scheme_map[intro['scheme']]
        if scope not in effects:
            if 'closed_entry' in intro: _error('metadata.closed_entry', 'CLOSED_ENTRY', 'proof on effect-free scope')
            continue
        p = 'metadata.closed_entry'
        path = intro['generalize_path']
        current = raw['entry'] if path['root'] == 'entry' else raw['functions' if path['root'] == 'function' else 'codes'][path['name']]['body']
        for part in path['segments']:
            b.work(); current = current[part]
        if current['op'] != 'generalize' or current['scheme'] != intro['scheme']:
            _error(p, 'CLOSED_ENTRY', 'raw introduction identity differs')
        callable_imports = _callable_import_rows(raw, derived, closure, current, records[_path_key(path, b)][1], b) if any(raw['types'][c['layout'][1:]]['tag'] == 'arrow' for c in current.get('imports', {}).values()) else None
        b.creation(5)
        owners, edges, scoped, root_site, root_code = {}, {}, [], None, None
        if callable_imports is None:
            for name in current.get('imports', {}):
                b.work(); b.put(owners, name, 'import')
        else:
            for position, name in enumerate(b.ordered(current['imports']), 1):
                b.work(); b.creation(); b.put(owners, name, ('import', position))
        for index, inst in enumerate(current['body']):
            b.work()
            b.creation(2 + len(path['segments']))
            key = (path['root'], path['name'], tuple(path['segments']) + ('body', index))
            _, rec = records[key]
            op = inst['op']
            if op in ('retain', 'borrow'):
                if inst['value'] not in owners: _error(p, 'CLOSED_ENTRY', 'owner lifetime source is not imported/root')
                b.put(owners, inst['out'], owners[inst['value']])
            elif op in ('drop', 'end_borrow'):
                if inst['value'] not in owners: _error(p, 'CLOSED_ENTRY', 'owner lifetime target is not imported/root')
                del owners[inst['value']]
            elif op == 'closure':
                if root_site is not None or len(rec['sites']) != 1:
                    _error(p, 'CLOSED_ENTRY', 'more than one neutral root allocation')
                root_site = rec['sites'][0]
                root_code = lookup[('function', inst['function'])]
                if raw_codes[root_code]['type_scope'] != intro['scheme']:
                    _error(p, 'CLOSED_ENTRY', 'root code crosses Scheme scope')
                if derived['sites'][root_site]['code'] != root_code:
                    _error(p, 'CLOSED_ENTRY', 'root allocation Code identity differs')
                for name, value in inst['captures'].items():
                    b.work()
                    token = owners.get(value)
                    if callable_imports is None:
                        if token != 'import': _error(p, 'CLOSED_ENTRY', 'root capture is not an actual import alias')
                    else:
                        if type(token) is not tuple or token[0] != 'import':
                            _error(p, 'CLOSED_ENTRY', 'root capture is not an actual checked import binding')
                        parent = records[_path_key(path, b)][1]
                        expected = parent['outputs'][token[1]]
                        actual = None
                        for fact in rec['inputs']:
                            b.work()
                            if fact['role'] == ['captures', name]: actual = fact
                        if actual is None: _error(p, 'CLOSED_ENTRY', 'root capture operand role is absent')
                        for field in ('kind','group','node','mode','type','ready','ticket','view','scheme','projection','provenance'):
                            b.work(); _equal_tree(actual[field], expected[field], b, p)
                    ty = closure.reference(raw_codes[root_code]['captures'][name]['layout'], scope)
                    row = closure.tables['types'][ty]
                    if not ((row['tag'] == 'closed' and row['atom'] in ('#i64', '#bool'))
                            or (callable_imports is not None and scalar_arrow_rows(closure.tables['types'], ty, b))):
                        _error(p, 'CLOSED_ENTRY', 'root capture must preserve checked scalar or concrete callable import')
                b.put(owners, inst['out'], 'root')
            elif op == 'seal':
                if root_site is None or owners.get(inst['value']) != 'root' or intro['result_sites'] != [root_site]:
                    _error(p, 'CLOSED_ENTRY', 'seal is not the exact direct root owner')
                # Bind actual checked owner/provenance, not only the raw name.
                fact = rec['inputs'][0]
                prov = derived['provenance'][fact['provenance']]['value']
                b.reserve(creation=2, work=8)
                if prov != {'kind':'allocated', 'site':root_site, 'context':{'kind':'introduction','intro':intro['id']}}:
                    _error(p, 'CLOSED_ENTRY', 'sealed actual allocation provenance differs')
            else:
                _error(p, 'CLOSED_ENTRY', 'neutral allocation or computation outside direct closure discipline')
        for code in derived['code_typing']:
            b.work()
            spec = raw_codes[code['id']]
            if spec['type_scope'] != intro['scheme']: continue
            b.append(scoped, code['id']); b.put(edges, code['id'], b.listing(()))
            for inst in spec['body']:
                b.work()
                if inst['op'] in ('closure', 'thunk'):
                    kind = 'function' if inst['op'] == 'closure' else 'thunk'
                    target = lookup[(kind, inst['function' if kind == 'function' else 'code'])]
                    if raw_codes[target]['type_scope'] != intro['scheme']:
                        _error(p, 'CLOSED_ENTRY', 'raw allocation edge crosses Scheme scope')
                    b.append(edges[code['id']], target)
        b.creation(2); reached, pending = set(), b.listing((root_code,))
        while pending:
            b.work(); code = pending.pop()
            if code in reached: continue
            if code not in edges: _error(p, 'CLOSED_ENTRY', 'unregistered scoped root/edge')
            b.add(reached, code)
            for target in edges[code]: b.work(); b.append(pending, target)
        b.work(len(scoped))
        if len(scoped) != len(reached) or any(code not in reached for code in scoped):
            _error(p, 'CLOSED_ENTRY', 'unreachable same-S Code, including dead declarations')
        ids = b.listing(())
        for key in effects[scope]:
            b.work(); b.append(ids, records[key][0])
        proof = b.row(policy=CLOSED_ENTRY_POLICY, root_site=root_site, root_code=root_code,
                      codes=scoped, effects=b.ordered(ids))
        if callable_imports is not None:
            proof['policy'] = CALLABLE_ENTRY_POLICY
            b.put(proof, 'callable_imports', callable_imports)
        if 'closed_entry' not in intro: _error(p, 'CLOSED_ENTRY', 'missing independently derived effect proof')
        _equal_tree(intro['closed_entry'], proof, b, p)
        b.put(result, scope, proof)
    if len(result) != len(effects): _error('metadata.closed_entry', 'CLOSED_ENTRY', 'effectful Scheme has no unique proof')
    return result


def _roots(raw, derived, bank, environments, references, scheme_map, by_scope, neutral, budget):
    budget.creation(3)
    roots, seen, requests = [], set(), set()

    def add(type_id, scope, path):
        _integer(type_id, len(bank.nodes), path)
        sid = scope if type(scope) is int else scheme_map.get(scope)
        if scope is not None and sid is None:
            _error(path, 'SCOPE', 'unknown root lexical scheme')
        allowed = 0 if sid is None else 1 << sid
        if bank.scopes[type_id] & ~allowed:
            _error(path, 'SCOPE', 'root contains rigid variables outside its lexical context')
        # Validate EVERY occurrence above, then expand its fixed lexical vector
        # inventory only once. Keep the first dependency path and all per-env
        # checks below; this is local scheduling, not a cached proof bypass.
        budget.reserve(creation=1, work=1)
        request = (type_id, sid)
        if request in requests:
            return
        budget.add(requests, request)
        for env in ((0,) if sid is None else by_scope[sid]):
            budget.work()
            budget.creation()
            key = (type_id, env)
            if key not in seen:
                budget.add(seen, key)
                budget.creation(2)
                roots.append((type_id, env, path))

    for value in range(len(bank.nodes)):
        budget.work()
        scope = bank.scopes[value]
        if scope == 0:
            add(value, None, 'metadata.types[' + str(value) + ']')
        elif scope & (scope - 1) == 0:
            add(value, scope.bit_length() - 1, 'metadata.types[' + str(value) + ']')
        # Multi-S unused abstract declarations remain Types without a false Env.
    for code in derived['code_typing']:
        for key in ('callable_type', 'argument', 'result'):
            budget.work()
            if code[key] is not None:
                add(code[key], code['type_scope'], 'metadata.codes[' + str(code['id']) + '].' + key)
        for capture in code['captures']:
            budget.work()
            add(capture['type'], code['type_scope'], 'metadata.codes[' + str(code['id']) + '].captures')
    for site in derived['sites']:
        budget.work()
        add(site['principal_type'], site['type_scope'], 'metadata.sites[' + str(site['id']) + ']')
    for index, obligation in enumerate(derived['obligations']):
        budget.work()
        add(obligation['expected_type'], obligation['scope'], 'metadata.obligations[' + str(index) + ']')
    for index, instruction in enumerate(derived['instructions']):
        for side in ('inputs', 'outputs'):
            for fact in instruction[side]:
                budget.work()
                if fact['kind'] != 'value':
                    continue
                if fact['view'] == 'SCHEME':
                    # A Scheme in a concrete context is still its OWN neutral body,
                    # never an attempt to resolve its open body at E0.
                    sid = scheme_map.get(fact['scheme'])
                    if sid is None:
                        _error('metadata.instructions', 'SCOPE', 'Scheme fact requires exact own scope')
                    body = references['^' + raw['schemes'][fact['scheme']]['body']]
                    if fact['type'] != body:
                        _error('metadata.instructions', 'SCHEME', 'Scheme fact body disagrees with its prefix')
                    add(body, sid, 'metadata.instructions[' + str(index) + '].' + side)
                elif fact['view'] == 'MONO':
                    add(fact['type'], instruction['type_scope'], 'metadata.instructions[' + str(index) + '].' + side)
                else:
                    _error('metadata.instructions', 'VIEW', 'value fact has unknown view')
    for intro in derived['introductions']:
        budget.work()
        add(intro['body_type'], intro['scheme'], 'metadata.introductions[' + str(intro['id']) + ']')
    for use in derived['uses']:
        for value in use['arguments']:
            budget.work()
            add(value, None, 'metadata.uses.' + use['name'])
        add(use['result_type'], None, 'metadata.uses.' + use['name'])
    for summary in derived['return_summaries']:
        budget.work()
        add(summary['result_type'], summary['type_scope'], 'metadata.returns')
    for name in budget.ordered(raw['layouts']):
        for field in budget.ordered(raw['layouts'][name]):
            budget.work()
            add(references[raw['layouts'][name][field]], None, 'layouts.' + name + '.' + field)
    for family in budget.ordered(raw['families']):
        for variant in raw['families'][family]['variants']:
            for reference in raw['families'][family]['fields'][variant]:
                budget.work()
                add(references[reference], None, 'families.' + family + '.fields.' + variant)
    return roots


def _resolve_all(bank, environments, roots, budget):
    """One depth-first, deduplicated need at a time; never re-enqueue a key."""
    budget.creation(3)
    resolved, scheduled, pending = {}, set(), []

    def schedule(type_id, env_id, path):
        budget.work()  # every substitution-key attempt, including duplicates
        budget.creation()
        key = (type_id, env_id)
        if key in scheduled:
            return False
        budget.reserve(creation=3)  # visited membership, frame, worklist member
        scheduled.add(key)
        pending.append([type_id, env_id, 0, path])
        return True

    for root_type, root_env, root_path in roots:
        schedule(root_type, root_env, root_path)
        while pending:
            frame = pending[-1]
            type_id, env_id, child_index, path = frame
            node, env = bank.nodes[type_id], environments[env_id]
            budget.work()
            allowed = 0 if env['scheme'] is None else 1 << env['scheme']
            if bank.scopes[type_id] & ~allowed:
                _error(path, 'SCOPE', 'cannot substitute a foreign rigid or an open type at E0')
            if node[0] == 'arrow' and child_index < 2:
                child = node[1 + child_index]
                frame[2] += 1
                budget.work()  # examined DAG child/dependency edge
                fresh = schedule(child, env_id, path)
                if not fresh:
                    budget.creation()  # repeated flat dependency lookup key
                if not fresh and (child, env_id) not in resolved:
                    _error(path, 'CYCLE', 'substitution dependency has an unfinished ancestor')
                continue
            pending.pop()
            if node[0] == 'closed':
                result = type_id
            elif node[0] == 'rigid':
                if env['scheme'] != bank.scheme_map[node[1]]:
                    _error(path, 'SCOPE', 'rigid/environment scheme mismatch')
                result = env['arguments'][node[2]]
            else:
                budget.work(2)
                budget.creation(3)  # child lookup keys and new flat arrow key
                left, right = resolved[(node[1], env_id)], resolved[(node[2], env_id)]
                dependency_path = f'metadata.type_resolutions[{type_id},{env_id}]'
                result = bank.intern(('arrow', left, right, node[3], node[4]), dependency_path)
            if env['mode'] == 'NEUTRAL' and result != type_id:
                _error(path, 'SUBSTITUTION', 'complete own-rigid substitution must be identity')
            if env['mode'] != 'NEUTRAL' and bank.scopes[result]:
                _error(path, 'SUBSTITUTION', 'concrete/closed substitution retained a rigid')
            budget.creation()
            key = (type_id, env_id)
            # The second resolution array is charged separately by representations.
            budget.reserve(creation=1, rows=1)
            resolved[key] = result
            if bank.scopes[result] == 0:
                schedule(result, 0, path)
    return resolved


def _canonical_order(bank, budget):
    budget.creation()
    scalars = {}
    for node in bank.nodes:
        for value in node:
            budget.work()
            if type(value) is str and value not in scalars:
                # One encoded scalar string plus its lookup membership. Its
                # bounded scalar payload is never an expanded Type tree.
                budget.reserve(creation=2, work=len(value))
                scalars[value] = json.dumps(value, ensure_ascii=False, separators=(',', ':'))

    def structural(left, right):
        while left != right:
            budget.work()  # one DAG node comparison, equal shared nodes skipped
            a, b = bank.nodes[left], bank.nodes[right]
            if a[0] != b[0]:
                return _compare(scalars[a[0]], scalars[b[0]], budget)
            if a[0] == 'arrow':
                budget.work()
                if a[1] != b[1]:
                    left, right = a[1], b[1]
                    continue
                budget.work()
                if a[2] != b[2]:
                    left, right = a[2], b[2]
                    continue
                for index in (3, 4):
                    budget.work()
                    if a[index] != b[index]:
                        return _compare(scalars[a[index]], scalars[b[index]], budget)
            else:
                for index in range(1, len(a)):
                    budget.work()
                    if a[index] != b[index]:
                        if type(a[index]) is not str:
                            budget.creation(2)  # bounded parameter-index decimal strings
                        left_scalar = scalars[a[index]] if type(a[index]) is str else str(a[index])
                        right_scalar = scalars[b[index]] if type(b[index]) is str else str(b[index])
                        return _compare(left_scalar, right_scalar, budget)
            _error('metadata.types', 'INTERNING', 'distinct flat IDs have identical structural equation')
        budget.work()
        return 0

    def compare(left, right):
        budget.work()
        if bank.depths[left] != bank.depths[right]:
            return -1 if bank.depths[left] < bank.depths[right] else 1
        return structural(left, right)

    budget.creation(2 + 4 * len(bank.nodes))  # source/result/sort/wrapper members
    order = sorted(range(len(bank.nodes)), key=cmp_to_key(compare))
    # A second ordering pass independently checks every adjacent result equation.
    for index in range(1, len(order)):
        left, right = order[index - 1], order[index]
        budget.work()
        if compare(left, right) >= 0:
            _error('metadata.types', 'ORDER', 'canonical type order is not strictly increasing')
    return order


def build_types(raw, derived, budget):
    """Build all scoped roots from a freshly resource-checked raw program only."""
    budget.creation(3)
    closure = TypeClosure()
    closure._budget, closure._raw, closure._derived = budget, raw, derived
    scheme_map = {}
    for name in budget.ordered(raw['schemes']):
        budget.put(scheme_map, name, len(scheme_map))
    closure.scheme_map = scheme_map
    bank = _Bank(raw, derived, budget, scheme_map)
    old_count = len(bank.nodes)
    references = _raw_references(raw, bank, budget)
    environments, env_map, neutral, by_scope = _environment_rows(
        raw, derived, bank, references, scheme_map, budget)
    roots = _roots(raw, derived, bank, environments, references, scheme_map, by_scope, neutral, budget)
    resolved = _resolve_all(bank, environments, roots, budget)
    order = _canonical_order(bank, budget)
    budget.creation(1 + len(order))
    remap = [None] * len(order)
    for new, old in enumerate(order):
        budget.work()
        remap[old] = new
    budget.creation(1 + old_count)
    closure.type_map = tuple(remap[old] for old in range(old_count))
    closure.env_map, closure._neutral = env_map, neutral
    budget.creation()
    closure._by_scope = {}
    for scope, envs in by_scope.items():
        budget.put(closure._by_scope, scope, budget.tuple(envs))
    budget.creation()
    closure.references = {}
    for reference, old in references.items():
        budget.work()
        budget.put(closure.references, reference, remap[old])
    budget.creation(4)
    types, contracts, type_remap, environment_remap = [], [], [], []
    budget.creation(3)
    final_nodes, final_scopes, final_depths = [], [], []
    budget.creation()
    contract_map = {}
    for new, old in enumerate(order):
        budget.work()
        node = bank.nodes[old]
        row = budget.record_append(types, id=new, tag=node[0], atom=None, scheme=None,
            index=None, argument=None, result=None, protocol=None, result_identity=None)
        budget.creation()
        if node[0] == 'closed':
            row['atom'] = node[1]
            final_node = ('closed', node[1])
        elif node[0] == 'rigid':
            row['scheme'], row['index'] = scheme_map[node[1]], node[2]
            final_node = ('rigid', node[1], node[2])
        else:
            a, r = remap[node[1]], remap[node[2]]
            row['argument'], row['result'] = a, r
            row['protocol'], row['result_identity'] = node[3], node[4]
            if a >= new or r >= new:
                _error('metadata.types', 'ORDER', 'canonical remap did not preserve forward child equations')
            final_node = ('arrow', a, r, node[3], node[4])
            budget.put(contract_map, new, len(contracts))
            budget.record_append(contracts, id=len(contracts), type=new, argument=a,
                result=r, protocol=node[3], result_identity=node[4])
        budget.append(final_nodes, final_node)
        budget.append(final_scopes, bank.scopes[old])
        budget.append(final_depths, bank.depths[old])
    for old in range(old_count):
        budget.record_append(type_remap, resource_type=old, metadata_type=remap[old])
    for index in range(len(environments)):
        budget.record_append(environment_remap, resource_environment='E' + str(index), environment=env_map['E' + str(index)])
    for env in environments:
        for index, old in enumerate(env['arguments']):
            budget.work()
            env['arguments'][index] = remap[old]
    budget.creation(2)
    schemes, intro_map = [], {}
    for intro in derived['introductions']:
        budget.work()
        if intro['scheme'] in intro_map:
            _error('metadata.schemes', 'INTRODUCTION', 'scheme has more than one introduction')
        budget.put(intro_map, intro['scheme'], intro['id'])
    for name in budget.ordered(raw['schemes']):
        if name not in intro_map:
            _error('metadata.schemes', 'INTRODUCTION', 'scheme lacks exact introduction')
        sid, spec = scheme_map[name], raw['schemes'][name]
        body = closure.references['^' + spec['body']]
        intro = derived['introductions'][intro_map[name]]
        if remap[intro['body_type']] != body:
            _error('metadata.schemes', 'BODY', 'scheme introduction body differs from raw prefix')
        budget.record_append(schemes, id=sid, name=name, parameters=spec['parameters'],
            body=body, neutral_env=neutral[sid], intro=intro_map[name])
    budget.creation(3)
    resolutions, resolution_ids, resolution_results = [], {}, {}
    ordered_keys = budget.ordered(resolved, key=lambda key: (remap[key[0]], key[1]), key_units=3)
    for old_type, env in ordered_keys:
        budget.work()
        budget.creation()
        key, result = (remap[old_type], env), remap[resolved[(old_type, env)]]
        index = len(resolutions)
        budget.record_append(resolutions, id=index, type=key[0], env=env, result=result)
        budget.put(resolution_ids, key, index)
        budget.put(resolution_results, key, result)
    closure.tables = budget.row(type_remap=type_remap, environment_remap=environment_remap,
        types=types, callable_contracts=contracts, schemes=schemes,
        environments=environments, type_resolutions=resolutions)
    closure.contracts = closure.contract_by_type = contract_map
    closure.scopes = budget.tuple(final_scopes)
    closure._nodes, closure._depths = budget.tuple(final_nodes), budget.tuple(final_depths)
    closure.resolution_ids, closure.resolution_results = resolution_ids, resolution_results
    closure._path_contexts = _contexts(raw, derived, scheme_map, budget, closure)
    closure._closed_entries = _closed_entry_proofs(raw, derived, closure, closure._closed_entries, budget)
    budget.creation(1 + 2 * len(roots))
    closure._roots = tuple((remap[type_id], env) for type_id, env, _ in roots)
    # Required forward pass is not replaced by success of the builder worklist.
    _verify_forward(raw, derived, closure, budget)
    return closure


def _verify_forward(raw, derived, closure, budget):
    """Independent forward equations, complete dependency keys, and ID domains."""
    tables, types = closure.tables, closure.tables['types']
    _verify_domains(raw, derived, closure, budget)
    budget.creation(3)
    flat, depths, scope_masks = {}, [], []
    for index, row in enumerate(types):
        path = f'metadata.types[{index}]'
        budget.work()
        _exact(row, TYPE_FIELDS, path)
        if type(row['id']) is not int or row['id'] != index:
            _error(path, 'REFERENCE', 'type row ID is not its position')
        tag = row['tag']
        budget.creation()
        if tag == 'closed':
            node = ('closed', row['atom'])
            depth, scope = 1, 0
            if any(row[key] is not None for key in ('scheme', 'index', 'argument', 'result', 'protocol', 'result_identity')):
                _error(path, 'TYPE', 'closed row null domains differ')
        elif tag == 'rigid':
            sid = _integer(row['scheme'], len(tables['schemes']), path)
            scheme = tables['schemes'][sid]
            _integer(row['index'], scheme['parameters'], path)
            node = ('rigid', scheme['name'], row['index'])
            depth, scope = 1, 1 << sid
            if any(row[key] is not None for key in ('atom', 'argument', 'result', 'protocol', 'result_identity')):
                _error(path, 'TYPE', 'rigid row null domains differ')
        elif tag == 'arrow':
            a = _integer(row['argument'], index, path)
            r = _integer(row['result'], index, path)
            budget.work(2)
            if row['protocol'] != 'repeat' or row['result_identity'] not in ('argument', 'unknown'):
                _error(path, 'CONTRACT', 'arrow contract differs from Repeat subset')
            if row['result_identity'] == 'argument' and a != r:
                _error(path, 'CONTRACT', 'argument identity requires exact equal children')
            if any(row[key] is not None for key in ('atom', 'scheme', 'index')):
                _error(path, 'TYPE', 'arrow null domains differ')
            node = ('arrow', a, r, row['protocol'], row['result_identity'])
            depth, scope = 1 + max(depths[a], depths[r]), scope_masks[a] | scope_masks[r]
        else:
            _error(path, 'TYPE', 'unknown type tag')
        if node in flat or depth > TYPE_DEPTH:
            _error(path, 'TYPE_EQUATION', 'duplicate node or excessive derived depth')
        budget.put(flat, node, index)
        budget.append(depths, depth)
        budget.append(scope_masks, scope)
        if node != closure._nodes[index] or scope != closure.scopes[index]:
            _error(path, 'TYPE_EQUATION', 'remapped row differs from independently retained flat equation')
    if len(tables['type_remap']) != len(derived['types']):
        _error('metadata.type_remap', 'REMAP', 'original remap is not total')
    for old, source in enumerate(derived['types']):
        budget.work()
        remap = tables['type_remap'][old]
        _exact(remap, ('resource_type', 'metadata_type'), 'metadata.type_remap')
        if type(remap['resource_type']) is not int or remap['resource_type'] != old:
            _error('metadata.type_remap', 'REMAP', 'original source ID differs')
        target = _integer(remap['metadata_type'], len(types), 'metadata.type_remap')
        row = types[target]
        for key in TYPE_FIELDS[1:]:
            budget.work()
            expected = source[key]
            if expected is not None and key in ('argument', 'result'):
                expected = tables['type_remap'][expected]['metadata_type']
            elif expected is not None and key == 'scheme':
                expected = closure.scheme_map[expected]
            if row[key] != expected:
                _error('metadata.type_remap', 'REMAP', 'original Type equation was not preserved')
    contract_index = 0
    for type_row in types:
        budget.work()
        if type_row['tag'] == 'arrow':
            if contract_index >= len(tables['callable_contracts']):
                _error('metadata.callable_contracts', 'CONTRACT', 'missing recursive callable contract')
            row = tables['callable_contracts'][contract_index]
            _exact(row, ('id', 'type', 'argument', 'result', 'protocol', 'result_identity'), 'metadata.callable_contracts')
            for key in ('argument', 'result', 'protocol', 'result_identity'):
                budget.work()
                if row[key] != type_row[key]:
                    _error('metadata.callable_contracts', 'CONTRACT', 'contract differs from exact Type')
            if type(row['id']) is not int or row['id'] != contract_index or type(row['type']) is not int or row['type'] != type_row['id']:
                _error('metadata.callable_contracts', 'CONTRACT', 'contract identity/order differs')
            contract_index += 1
    if contract_index != len(tables['callable_contracts']):
        _error('metadata.callable_contracts', 'CONTRACT', 'extra callable contract')
    budget.creation()
    actual = {}
    previous = None
    for index, row in enumerate(tables['type_resolutions']):
        budget.work()
        _exact(row, ('id', 'type', 'env', 'result'), 'metadata.type_resolutions')
        if type(row['id']) is not int or row['id'] != index:
            _error('metadata.type_resolutions', 'REFERENCE', 'resolution ID differs from position')
        type_id = _integer(row['type'], len(types), 'metadata.type_resolutions')
        env_id = _integer(row['env'], len(tables['environments']), 'metadata.type_resolutions')
        _integer(row['result'], len(types), 'metadata.type_resolutions')
        budget.creation()
        key = (type_id, env_id)
        if previous is not None and key <= previous:
            _error('metadata.type_resolutions', 'ORDER', 'resolution keys duplicate or out of order')
        budget.put(actual, key, row['result'])
        previous = key
    for row in tables['type_resolutions']:
        budget.work()
        type_id, env_id = row['type'], row['env']
        node, env = types[type_id], tables['environments'][env_id]
        if scope_masks[type_id] & ~(0 if env['scheme'] is None else 1 << env['scheme']):
            _error('metadata.type_resolutions', 'SCOPE', 'foreign-scope resolution')
        if node['tag'] == 'closed':
            expected = type_id
        elif node['tag'] == 'rigid':
            if node['scheme'] != env['scheme']:
                _error('metadata.type_resolutions', 'SCOPE', 'rigid does not belong to environment')
            expected = env['arguments'][node['index']]
        else:
            budget.work(2)
            a, r = actual.get((node['argument'], env_id)), actual.get((node['result'], env_id))
            if a is None or r is None:
                _error('metadata.type_resolutions', 'MISSING_RESOLUTION', 'arrow child resolution omitted')
            budget.creation()
            expected = flat.get(('arrow', a, r, node['protocol'], node['result_identity']))
        if expected is None or row['result'] != expected:
            _error('metadata.type_resolutions', 'SUBSTITUTION', 'forward substitution equation differs')
        if env['mode'] == 'NEUTRAL' and expected != type_id:
            _error('metadata.type_resolutions', 'SUBSTITUTION', 'neutral substitution is not identity')
        if env['mode'] != 'NEUTRAL' and scope_masks[expected]:
            _error('metadata.type_resolutions', 'SUBSTITUTION', 'closed substitution retained rigids')
    # Independently derive the exact finite dependency key set from saved fresh
    # root associations. Missing rows and plausible-but-unrequested extras fail.
    budget.creation(2)
    needed, pending = set(), budget.listing(closure._roots)
    while pending:
        key = pending.pop()
        budget.work()
        if key in needed:
            continue
        if key not in actual:
            _error('metadata.type_resolutions', 'MISSING_RESOLUTION', 'required root/dependency omitted')
        budget.add(needed, key)
        row = types[key[0]]
        if row['tag'] == 'arrow':
            for child in (row['argument'], row['result']):
                budget.work()
                budget.creation(2)
                pending.append((child, key[1]))
        result = actual[key]
        if scope_masks[result] == 0:
            budget.creation(2)
            pending.append((result, 0))
    if len(needed) != len(actual):
        _error('metadata.type_resolutions', 'EXTRA_RESOLUTION', 'unjustified type/environment pair')



def _verify_domains(raw, derived, closure, budget):
    """Check finite table/null/reference domains before dereferencing any row."""
    tables = closure.tables
    for table in TYPE_TABLES:
        budget.work()
        if table not in tables or type(tables[table]) is not list:
            _error('metadata.' + table, 'SCHEMA', 'expected exact table array')
    if not 1 <= len(tables['types']) <= TYPE_LIMIT or len(tables['schemes']) != len(raw['schemes']):
        _error('metadata.types', 'COUNT', 'type/scheme inventory count differs')
    for index, row in enumerate(tables['schemes']):
        budget.work()
        _exact(row, ('id', 'name', 'parameters', 'body', 'neutral_env', 'intro'), 'metadata.schemes')
        if type(row['id']) is not int or row['id'] != index or type(row['name']) is not str:
            _error('metadata.schemes', 'REFERENCE', 'scheme identity differs')
        if row['name'] not in raw['schemes'] or closure.scheme_map.get(row['name']) != index:
            _error('metadata.schemes', 'SCOPE', 'scheme name/order differs')
        parameters = row['parameters']
        if type(parameters) is not int or parameters != raw['schemes'][row['name']]['parameters'] or not 1 <= parameters <= 8:
            _error('metadata.schemes', 'VECTOR', 'complete parameter arity differs')
        _integer(row['body'], len(tables['types']), 'metadata.schemes')
        _integer(row['neutral_env'], len(tables['environments']), 'metadata.schemes')
        _integer(row['intro'], len(derived['introductions']), 'metadata.schemes')
        if derived['introductions'][row['intro']]['scheme'] != row['name']:
            _error('metadata.schemes', 'INTRODUCTION', 'scheme introduction association differs')
    if not 1 <= len(tables['environments']) <= ENVIRONMENT_LIMIT:
        _error('metadata.environments', 'COUNT', 'environment count outside bounds')
    checked_arguments = None
    arrow_schemes = 0
    for index, env in enumerate(tables['environments']):
        budget.work()
        _exact(env, ('id', 'scheme', 'mode', 'arguments'), 'metadata.environments')
        if type(env['id']) is not int or env['id'] != index or type(env['arguments']) is not list:
            _error('metadata.environments', 'REFERENCE', 'environment ID/vector domain differs')
        if index == 0:
            if env['scheme'] is not None or env['mode'] != 'CONCRETE' or env['arguments']:
                _error('metadata.environments', 'ENVIRONMENT', 'E0 must be the exact empty concrete environment')
            continue
        sid = _integer(env['scheme'], len(tables['schemes']), 'metadata.environments')
        scheme = tables['schemes'][sid]
        if env['mode'] not in ('NEUTRAL', 'CLOSED') or len(env['arguments']) != scheme['parameters']:
            _error('metadata.environments', 'VECTOR', 'environment requires its entire registered vector')
        if env['mode'] == 'NEUTRAL' and scheme['neutral_env'] != index:
            _error('metadata.environments', 'ENVIRONMENT', 'neutral environment association differs')
        for position, type_id in enumerate(env['arguments']):
            budget.work()
            _integer(type_id, len(tables['types']), 'metadata.environments')
            node = tables['types'][type_id]
            _exact(node, TYPE_FIELDS, 'metadata.types')
            if env['mode'] == 'NEUTRAL':
                if node['tag'] != 'rigid' or type(node['scheme']) is not int or node['scheme'] != sid or type(node['index']) is not int or node['index'] != position:
                    _error('metadata.environments', 'VECTOR', 'neutral vector is not the exact ordered own-rigid prefix')
            elif node['tag'] == 'arrow':
                if checked_arguments is None:
                    budget.creation()
                    checked_arguments = set()
                _verify_arrow_argument(raw, tables['types'], type_id, checked_arguments, budget)
                arrow_schemes |= 1 << sid
            elif (node['tag'] != 'closed' or
                  (node['atom'] not in ('#bool', '#i64') and
                   not _registered_nominal_atom(raw, node['atom'], budget))):
                _error('metadata.environments', 'VECTOR', 'closed vector requires an exact registered intrinsic, DATA or SUM atom')
    if arrow_schemes:
        # Check the WHOLE ordered vector inventory for each newly admitted
        # scheme, including atomic and dead coordinates, after Type-ID remap.
        # Scalar/nominal-only invocations retain their exact prior work path.
        budget.creation()
        previous = {}
        for env in tables['environments']:
            budget.work()
            if env['mode'] == 'CLOSED' and arrow_schemes & (1 << env['scheme']):
                before = previous.get(env['scheme'])
                if before is not None and _compare(before, env['arguments'], budget) >= 0:
                    _error('metadata.environments', 'ORDER', 'complete closed vectors are not in strict canonical Type-ID order')
                budget.put(previous, env['scheme'], env['arguments'])
    if len(tables['environment_remap']) != len(tables['environments']):
        _error('metadata.environment_remap', 'REMAP', 'environment remap is not total')
    for index, row in enumerate(tables['environment_remap']):
        budget.work()
        _exact(row, ('resource_environment', 'environment'), 'metadata.environment_remap')
        if row['resource_environment'] != 'E' + str(index) or type(row['environment']) is not int or row['environment'] != index:
            _error('metadata.environment_remap', 'REMAP', 'environment remap changed exact complete-vector identity')

def verify_types(raw, derived, closure, budget):
    """Rebuild the expected seven tables from fresh raw/lower-stage evidence.

    This private mutation-control verifier has no public producer-table route.
    Rebuilding charges every examination/copy but not a second emitted-row quota.
    Actual candidate cardinalities are independently checked by the total verifier.
    """
    _verify_forward(raw, derived, closure, budget)
    with budget.verification():
        expected = build_types(raw, derived, budget)
    for table in TYPE_TABLES:
        budget.work()
        left, right = closure.tables[table], expected.tables[table]
        # Explicit flat/tree traversal avoids uncharged recursive dataclass/tuple
        # equality, and counts each candidate row/equation examination.
        _equal_tree(left, right, budget, 'metadata.' + table)
    return None


_verify_types = verify_types


def _equal_tree(left, right, budget, path):
    budget.creation(3)
    pending = [(left, right)]
    while pending:
        a, b = pending.pop()
        budget.work()
        if type(a) is not type(b):
            _error(path, 'EQUATION', 'derived table value type differs')
        if type(a) is dict:
            if len(a) != len(b) or any(key not in b for key in a):
                _error(path, 'EQUATION', 'derived table record keys differ')
            for key in a:
                budget.creation(2)
                pending.append((a[key], b[key]))
        elif type(a) in (tuple, list):
            if len(a) != len(b):
                _error(path, 'EQUATION', 'derived table sequence length differs')
            for i in range(len(a)):
                budget.creation(2)
                pending.append((a[i], b[i]))
        elif a != b:
            _error(path, 'EQUATION', 'derived table equation differs')
