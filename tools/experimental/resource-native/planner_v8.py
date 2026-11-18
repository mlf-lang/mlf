"""Opt-in coarse-owned lowering of independently replayed shared fragments.

This is not K/source admission. Raw proof/normalization evidence is freshly
replayed at this boundary; the returned IR candidate still requires the unchanged
independent IR8 resource checker and emitter. Old planner/default paths are not
imported or changed. No ordinary lambda cloning, beta reduction, identity-name
recognition, nominal fallback, or per-type RHS expansion is performed. Referenced
closed single-constructor DATA uses exact independently replayed declarations;
constructor payloads and whole cases remain lazy ordinary term graphs.
Closed scalar/self-atom SUM uses selected-only Int-result arm factories, with
all arms checked and their exact declaration/source identities retained. A self
field is the same finite nominal identity, never a recursively expanded type.
One concrete monomorphic recursive function can use an owned, coarse typed
hole. Its complete checked RHS graph remains lazy; no wrapper is contracted.
Closed scalar owners, closed scalar-arrow owners and complete shared-view pairs
may be captured without changing existing support, origin or target Access.
An ordinary callable owner may remain pending; its type predicts no Code.
Top-level direct-lambda generalizations may explicitly import scalar owners;
the independent resource checker must still prove their origin and support.
Closed scalar computations retain this same Scheme scope in every deferred
carrier. Their closed-entry/Instance-only premise is independently checked in IR.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

import module_shared_transport as transport

MAX_WORK = 1_000_000
MAX_INSTRUCTIONS = 10_000
MAX_CODES = 2048
MAX_TYPES = 4096
MAX_TYPE_DEPTH = 32
MAX_CAPTURES = 64
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
SCALARS = {'Int': ('scalar', '#i64'), 'Bool': ('scalar', '#bool')}
PRIMITIVES = {8: ('addInt', SCALARS['Int']), 9: ('subInt', SCALARS['Int']),
              10: ('eqInt', SCALARS['Bool']), 11: ('ltInt', SCALARS['Bool']),
              14: ('mulInt', SCALARS['Int'])}


class PlanningError(ValueError):
    """Explicit unsupported fragment or bounded candidate-generation failure."""


def require(ok, message):
    if not ok:
        raise PlanningError(message)


def address(path):
    return {'stage': 'normalized', 'path': list(path)}


def arrow(a, b):
    # Ordinary source arrows establish this conservative exact contract only.
    # It is part of equality/interning, never inferred from a function's name.
    return ('arrow', a, b, 'repeat', 'unknown')


@dataclass(frozen=True)
class Reference:
    variable: str
    logical: tuple
    carrier: int | None = None
    strict: bool = False  # Actual proof: group < the current invocation home.


@dataclass(frozen=True)
class SchemeReference:
    variable: str
    definition: int
    strict: bool = False


@dataclass
class Block:
    root: str
    name: str | None
    body: list
    prefix: tuple = ()
    scope: str | None = None

    def path(self, index):
        return {'root': self.root, 'name': self.name, 'segments': list(self.prefix + (index,))}


class Planner:
    def __init__(self, fragment, *, data_groups=False, reuse_int_branches=False):
        require(type(data_groups) is bool, 'data_groups must be a boolean')
        self.data_groups = data_groups
        require(type(reuse_int_branches) is bool, 'reuse_int_branches must be a boolean')
        self.reuse_int_branches = reuse_int_branches
        self.branch_owner_reuse = []
        self.group_map = []
        self.knot_map = []
        self.knot_depth = 0
        self.fragment = fragment
        self.root = fragment['raw_normalized']
        # Only the new coordinate domain needs expanded structural-work guards.
        # Keep old scalar/nominal plans, including their work counters, exact.
        self.arrow_coordinates = any(t['tag'] == 'arrow'
            for u in fragment['polymorphism']['uses'] for t in u['arguments'])
        self._type_costs = {}  # id -> (retained object, height, expanded weight)
        recursion = fragment.get('recursion')
        self.recursion_rows = {}
        if recursion is not None:
            require(recursion['policy'] == 'closed-single-function-recursion/1' and
                    len(recursion['bindings']) == 1, 'recursive function evidence differs')
            row = recursion['bindings'][0]
            self.recursion_rows[tuple(row['source']['path'])] = row
        self.work = self.instructions = self.variables = self.code_count = 0
        self.types = {}; self.type_names = {}; self.signatures = {}; self.signature_names = {}
        self.functions = {}; self.codes = {}; self.schemes = {}; self.instantiations = {}
        self.instantiation_names = {}
        self.scopes = {}
        nominal = fragment.get('nominal_data', {})
        self.nominal_rows = {r['index']: r for r in nominal.get('declarations', [])}
        self.nominal_by_name = {r['name']: r for r in self.nominal_rows.values()}
        sums = fragment.get('nominal_sum', {})
        self.sum_rows = {r['index']: r for r in sums.get('declarations', [])}
        self.nominal_by_name.update((r['name'], r) for r in self.sum_rows.values())
        self.sum_constructor_rows = {tuple(r['source']['path']): r for r in sums.get('constructors', [])}
        self.sum_case_rows = {tuple(r['source']['path']): r for r in sums.get('cases', [])}
        self.families = {}; self.sum_families = {}; self.sum_map = []
        self.sum_constructor_map = []; self.sum_case_map = []
        self.constructor_rows = {tuple(r['source']['path']): r for r in nominal.get('constructors', [])}
        self.case_rows = {tuple(r['source']['path']): r for r in nominal.get('cases', [])}
        self.layouts = {}; self.nominal_layouts = {}; self.nominal_map = []
        self.constructor_map = []; self.case_map = []
        for r in self.nominal_rows.values():
            typ = self.logical(r['type'], None); layout = 'D' + str(r['index'])
            self.nominal_layouts[typ] = layout
            fields = [self.logical(t, None) for t in r['field_types']]
            self.layouts[layout] = {'f'+str(i): self.layout(t) for i,t in enumerate(fields)}
            self.nominal_map.append({'declaration': r['index'], 'name': r['name'],
                                     'source': r['source'], 'layout': layout,
                                     'fields': [{'index': i, 'field': 'f'+str(i), 'type': self.type_name(t)}
                                                for i,t in enumerate(fields)]})
        recursive_indices = []
        for r in self.sum_rows.values():
            typ = self.logical(r['type'], None); family = 'F' + str(r['index'])
            self.sum_families[r['index']] = family
            self.nominal_layouts[typ] = '%' + family
            variants = []; fields = {}; variant_map = []
            require(2 <= len(r['variants']) <= 64, 'SUM variant count outside admitted bound')
            for i,v in enumerate(r['variants']):
                self.tick(); require(v['index'] == i, 'SUM declaration variant order differs')
                name = 'V' + str(i); variants.append(name)
                types = [self.logical(t, None) for t in v['field_types']]
                require(len(types) <= 32 and all(t in SCALARS.values() or t == typ for t in types),
                        'SUM fields require intrinsic scalars or the exact self nominal atom')
                if typ in types and r['index'] not in recursive_indices:
                    recursive_indices.append(r['index'])
                fields[name] = [t[1] if t in SCALARS.values() else '%' + family for t in types]
                variant_map.append({'index':i, 'variant':name, 'constructor':v['constructor'],
                                    'constructor_source':v['constructor_source'],
                                    'fields':[self.type_name(t) for t in types]})
            self.families[family] = {'variants':variants, 'fields':fields}
            self.sum_map.append({'declaration':r['index'], 'name':r['name'], 'source':r['source'],
                                 'family':family, 'variants':variant_map})
        if recursive_indices:
            require(sums.get('self_recursive') == {
                'policy': 'closed-self-atom/1', 'declarations': sorted(recursive_indices)},
                'SUM self-atom evidence differs')
        else:
            require('self_recursive' not in sums, 'spurious SUM self-atom evidence')
        self.definitions = fragment['polymorphism']['definitions']
        self.def_by_path = {tuple(d['binding_source']['path']): d for d in self.definitions}
        self.def_by_binder = {d['binding']['id']: d for d in self.definitions}
        self.uses = {tuple(u['source']['path']): u for u in fragment['polymorphism']['uses']}
        self.definition_types = {}; self.use_pairs = {}; self.use_types = {}
        self.term_map = {}; self.scheme_map = []; self.use_map = []; self.carrier_map = []; self.allocation_map = []
        for d in self.definitions:
            scope = 'S' + str(d['id'])
            self.scopes[scope] = {p['id']: ('rigid', scope, p['rigid_index']) for p in d['prefix']}
            logical = self.logical(d['body_type'], scope)
            require(logical[0] == 'arrow', 'Scheme body must remain callable')
            self.definition_types[d['id']] = logical
            self.schemes[scope] = {'parameters': len(d['prefix']), 'body': self.type_name(logical)}
        for path, u in self.uses.items():
            d = self.definitions[u['definition']]
            vector = tuple(self.logical(t, None) for t in u['arguments'])
            require(len(vector) == len(d['prefix']) and
                    (all(t[0] == 'scalar' for t in vector) or
                     all(self.closed_argument(t) for t in vector)),
                    'complete closed intrinsic/admitted nominal/Repeat-unknown arrow vector required')
            pair = (d['binding']['id'], vector)
            self.use_pairs[path] = pair
            typ = self.substitute(self.definition_types[d['id']], 'S' + str(d['id']), vector)
            require(self.same_type(typ, self.logical(u['instantiated_type'], None)), 'replayed use result differs')
            self.use_types[path] = typ

    def tick(self, amount=1):
        require(amount <= MAX_WORK - self.work, 'planner work limit')
        self.work += amount

    def fresh(self, prefix='v'):
        self.tick(); self.variables += 1
        return prefix + str(self.variables)

    def node_at(self, path):
        node = self.root
        for key in path:
            self.tick()
            if type(node) is list:
                require(type(key) is str and key.isascii() and key.isdecimal() and
                        str(int(key)) == key and int(key) < len(node), 'invalid source list address')
                node = node[int(key)]
            else:
                node = node[key]
        return node

    def logical(self, raw, scope, depth=0):
        self.tick(); require(depth < MAX_TYPE_DEPTH, 'logical type depth limit')
        if raw['tag'] == 'constructor':
            require(raw['arguments'] == [], 'parameterized nominal type unsupported')
            if raw['name'] in SCALARS:
                return SCALARS[raw['name']]
            row = self.nominal_by_name.get(raw['name'])
            require(scope is None and row is not None, 'unregistered or generic nominal type')
            return ('nominal', row['index'], row['name'], tuple(row['source']['path']))
        if raw['tag'] == 'var':
            require(scope in self.scopes and raw['id'] in self.scopes[scope], 'foreign/open logical type')
            return self.scopes[scope][raw['id']]
        require(raw['tag'] == 'arrow', 'rank1 monotype required')
        return arrow(self.logical(raw['from'], scope, depth+1), self.logical(raw['to'], scope, depth+1))

    def closed_argument(self, typ):
        self.tick()
        if typ[0] == 'arrow':
            # No registry insertion, nominal unfolding or desired-Code lookup.
            self.structural_work(typ)
            pending = [typ]; seen = set()
            while pending:
                part = pending.pop(); ident = id(part)
                if ident in seen:
                    continue
                seen.add(ident); self.tick()
                if part[0] == 'arrow':
                    require(part[3:] == ('repeat', 'unknown'), 'closed coordinate callable contract')
                    pending.extend(part[1:3])
                elif not (part in SCALARS.values() or
                          (part[0] == 'nominal' and part in self.nominal_layouts)):
                    return False
            return True
        return typ in SCALARS.values() or (typ[0] == 'nominal' and typ in self.nominal_layouts)

    def type_cost(self, typ):
        """Bound a tuple DAG before hashing/equality can expand its sharing.

        Cache keys are object IDs, not structural tuples. Retaining each object
        prevents ID reuse. Weight counts the expanded tuple slots, saturating
        before arithmetic can grow; it is not the canonical Type-row count.
        """
        pending = [(typ, False)]; active = set()
        while pending:
            node, finish = pending.pop(); ident = id(node)
            cached = self._type_costs.get(ident)
            if cached is not None:
                require(cached[0] is node, 'type-cost identity differs')
                continue
            self.tick()
            require(type(node) is tuple and node, 'invalid logical type tuple')
            if not finish:
                require(ident not in active, 'cyclic logical type')
                tag = node[0]
                if tag == 'arrow':
                    require(len(node) == 5 and node[3:] == ('repeat', 'unknown'),
                            'unsupported callable contract')
                    active.add(ident); pending.append((node, True))
                    pending.extend(((node[2], False), (node[1], False)))
                    continue
                require((tag == 'scalar' and len(node) == 2) or
                        (tag == 'rigid' and len(node) == 3) or
                        (tag == 'nominal' and len(node) == 4 and type(node[3]) is tuple),
                        'invalid logical atom')
                height = 1; weight = 1 + len(node)
                if tag == 'nominal':
                    weight += len(node[3])
            else:
                left = self._type_costs[id(node[1])]; right = self._type_costs[id(node[2])]
                height = 1 + max(left[1], right[1])
                weight = min(MAX_WORK + 1, 6 + left[2] + right[2])
                active.remove(ident)
            require(height <= MAX_TYPE_DEPTH, 'logical type depth limit')
            self._type_costs[ident] = (node, height, weight)
        return self._type_costs[id(typ)][1:]

    def structural_work(self, *types, multiplier=1):
        if self.arrow_coordinates:
            weight = sum(self.type_cost(t)[1] for t in types)
            self.tick(min(MAX_WORK + 1, multiplier * weight))

    def same_type(self, left, right):
        self.structural_work(left, right)
        return left == right

    def pair_work(self, pair, multiplier=1):
        if self.arrow_coordinates:
            weight = 3 + sum(self.type_cost(t)[1] for t in pair[1])
            self.tick(min(MAX_WORK + 1, multiplier * weight))

    def sorted_pairs(self, pairs):
        if self.arrow_coordinates:
            # A conservative quadratic comparison allowance, charged before
            # Python's sort sees any nested vector. No abbreviated vector key.
            for pair in pairs:
                self.pair_work(pair, multiplier=max(1, len(pairs)))
        return sorted(pairs)

    def same_pairs(self, left, right):
        if self.arrow_coordinates:
            for pair in list(left) + list(right):
                self.pair_work(pair)
        return left == right

    def substitution_work(self, typ, scope, vector):
        """Measure a result before constructing it or comparing its tuples."""
        metrics = {}; pending = [(typ, False)]
        for argument in vector:
            self.type_cost(argument)
        while pending:
            node, finish = pending.pop(); ident = id(node)
            if ident in metrics:
                continue
            self.tick()
            if node[0] == 'rigid':
                require(node[1] == scope and type(node[2]) is int and 0 <= node[2] < len(vector),
                        'foreign Scheme rigid')
                metrics[ident] = self.type_cost(vector[node[2]])
            elif node[0] != 'arrow':
                metrics[ident] = self.type_cost(node)
            elif not finish:
                pending.append((node, True))
                pending.extend(((node[2], False), (node[1], False)))
            else:
                left, right = metrics[id(node[1])], metrics[id(node[2])]
                height = 1 + max(left[0], right[0])
                require(height <= MAX_TYPE_DEPTH, 'substituted logical type depth limit')
                metrics[ident] = (height, min(MAX_WORK + 1, 6 + left[1] + right[1]))
        self.tick(metrics[id(typ)][1])

    def substitute(self, typ, scope, vector):
        if self.arrow_coordinates:
            self.type_cost(typ)
            self.substitution_work(typ, scope, vector)
        return self._substitute(typ, scope, vector)

    def _substitute(self, typ, scope, vector):
        self.tick()
        if typ[0] == 'rigid':
            require(typ[1] == scope, 'foreign Scheme rigid')
            return vector[typ[2]]
        if typ[0] == 'arrow':
            return ('arrow', self._substitute(typ[1], scope, vector), self._substitute(typ[2], scope, vector), typ[3], typ[4])
        return typ

    def type_name(self, typ):
        self.tick()
        self.structural_work(typ, multiplier=3)
        if typ in self.type_names:
            return self.type_names[typ]
        if typ[0] == 'scalar': row = {'tag': 'closed', 'layout': typ[1]}
        elif typ[0] == 'nominal': row = {'tag': 'closed', 'layout': self.nominal_layouts[typ]}
        elif typ[0] == 'rigid': row = {'tag': 'rigid', 'scheme': typ[1], 'index': typ[2]}
        else:
            require(typ[0] == 'arrow' and typ[3:] == ('repeat', 'unknown'), 'unsupported callable contract')
            row = {'tag': 'arrow', 'argument': self.type_name(typ[1]), 'result': self.type_name(typ[2]),
                   'protocol': typ[3], 'result_identity': typ[4]}
        require(len(self.types) < MAX_TYPES, 'type count limit')
        name = 'T' + str(len(self.types)); self.type_names[typ] = name; self.types[name] = row
        return name

    def layout(self, typ):
        return '^' + self.type_name(typ)

    def signature(self, typ):
        self.tick(); require(typ[0] == 'arrow', 'callable required')
        self.structural_work(typ, multiplier=3)
        if typ not in self.signature_names:
            name = 'A' + str(len(self.signatures)); self.signature_names[typ] = name
            self.signatures[name] = {'argument': self.layout(typ[1]), 'result': self.layout(typ[2]),
                                     'protocol': typ[3], 'result_identity': typ[4]}
        return self.signature_names[typ]

    def add(self, block, source=None, logical=None, **instruction):
        self.tick(); require(self.instructions < MAX_INSTRUCTIONS, 'instruction limit')
        path = block.path(len(block.body)); self.instructions += 1; block.body.append(instruction)
        if instruction['op'] in ('scalar', 'closure', 'application', 'thunk', 'prim2', 'alloc',
                                  'construct_nullary', 'construct_sum', 'hole'):
            require(source is not None and logical is not None, 'allocation correspondence missing')
            require(len(self.allocation_map) + self.code_count < MAX_CODES, 'combined Site/Code limit')
            self.allocation_map.append({'source': address(source), 'instruction': path,
                                        'role': instruction['op'], 'type_scope': block.scope,
                                        'logical_type': self.type_name(logical)})
        return path

    def release(self, ref, block):
        self.add(block, op='drop', value=ref.variable)

    def allocation(self, home, support, block, path, kind, scope, *, eligible=True):
        """Optional separation only above complete, proven-strict supports.

        Generic bodies and captured closures initially stay coarse. A fresh
        group surrounding a closed generalize block still proves its entire
        sealed result strictly below the enclosing home, without cloning it.
        Imports are live owner authorities, not guessed transitive heap edges.
        """
        if not self.data_groups:
            return home, False, None
        self.tick(1 + len(support))
        split = not self.knot_depth and scope is None and eligible and all(r.strict for r in support)
        row = {'source': address(path), 'kind': kind, 'home': home,
               'strategy': 'fresh-below' if split else 'same-home',
               'reason': ('all-support-strict' if split else 'recursive-knot-coarse' if self.knot_depth
                          else 'generic-body-coarse' if scope is not None
                          else 'captured-closure-coarse' if not eligible else 'support-only-down'),
               'support': [{'reference': r.variable, 'strict': r.strict} for r in support]}
        key = home
        if split:
            key = self.fresh('group')
            row['create'] = self.add(block,op='new_below',out=key,ceiling=home,
                                     imports=list(dict.fromkeys(r.variable for r in support)))
        row['allocation_key'] = key
        self.group_map.append(row)
        return key, split, row

    def close_builder(self, key, split, row, block):
        if split:
            row['drop_builder'] = self.add(block,op='drop',value=key)

    def term(self, node, path, role='ordinary'):
        self.tick(); require(path not in self.term_map, 'ordinary source occurrence emitted more than once')
        row = {'source': address(path), 'tag': node['tag'], 'role': role}
        if node['tag'] in ('var', 'let'): row['binder'] = node['name']['id']
        elif node['tag'] == 'lambda': row['binder'] = node['parameter']['id']
        self.term_map[path] = row

    def instantiation(self, pair):
        self.pair_work(pair, multiplier=3)
        if pair not in self.instantiation_names:
            require(len(self.instantiations) < 1024, 'complete-vector instantiation limit')
            d = self.def_by_binder[pair[0]]
            name = 'U' + str(len(self.instantiations)); self.instantiation_names[pair] = name
            self.instantiations[name] = {'scheme': 'S' + str(d['id']),
                                        'arguments': [self.type_name(t) for t in pair[1]]}
        return self.instantiation_names[pair]

    def acquire_view(self, pair, env, views, block):
        self.tick(); paths = []
        self.pair_work(pair)
        source = views.get(pair)
        if source is not None:
            ref = Reference(self.fresh(), source.logical, strict=source.strict)
            paths.append(self.add(block, op='retain', out=ref.variable, value=source.variable))
            require(source.carrier is not None, 'saved view lacks its lexical carrier')
            return ref, paths, {'kind': 'captured', 'carrier': source.carrier, 'capture': source.variable}
        source = env.get(pair[0]); d = self.def_by_binder[pair[0]]
        require(isinstance(source, SchemeReference) and source.definition == d['id'], 'shared view unavailable in lexical scope')
        owned = self.fresh(); result = self.fresh()
        paths.append(self.add(block, op='retain', out=owned, value=source.variable))
        paths.append(self.add(block, op='instantiate', out=result, value=owned, instantiation=self.instantiation(pair)))
        logical = self.substitute(self.definition_types[d['id']], 'S' + str(d['id']), pair[1])
        return Reference(result, logical, strict=source.strict), paths, {'kind': 'scheme', 'definition': d['id']}

    def needed(self, node, path, bound=frozenset()):
        """Transitive free lexical binders AND complete-vector shared views.

        A Scheme introduced inside this carrier is local, not a capture. Closed
        generic RHSs need no traversal; an explicitly imported scalar remains a
        real dependency. Never erase type applications with the old free_vars.
        """
        mono = set(); pairs = {}
        def visit(n, p, local):
            self.tick(); tag = n['tag']
            if tag == 'type_application':
                require(p in self.uses, 'unmapped type application')
                key = self.use_pairs[p]
                if key[0] not in local:
                    self.pair_work(key)
                    pairs.setdefault(key, []).append(self.uses[p]['id'])
                return
            if tag == 'var':
                if n['name']['id'] not in local: mono.add(n['name']['id'])
                return
            if tag == 'lambda':
                visit(n['body'], p+('body',), local | {n['parameter']['id']}); return
            if tag == 'let':
                if p not in self.def_by_path: visit(n['value'], p+('value',), local)
                elif self.def_by_path[p]['free_term_bindings']:
                    rhs = tuple(self.def_by_path[p]['rhs_cursor']['path'])
                    visit(self.node_at(rhs), rhs, local)
                visit(n['body'], p+('body',), local | {n['name']['id']}); return
            if tag == 'letrec':
                require(len(n['bindings']) == 1, 'recursive group must be singleton')
                binding = n['bindings'][0]
                inside = local | {binding['name']['id']}
                visit(binding['value'], p+('bindings','0','value'), inside)
                visit(n['body'], p+('body',), inside); return
            if tag == 'application':
                visit(n['function'], p+('function',), local); visit(n['argument'], p+('argument',), local); return
            if tag == 'case':
                if p in self.sum_case_rows:
                    row = self.sum_case_rows[p]
                    visit(n['scrutinee'], p+('scrutinee',), local)
                    for arm in row['arms']:
                        self.tick()
                        bound_fields = {f['binding']['id'] for f in arm['fields'] if f['binding'] is not None}
                        visit(self.node_at(arm['body']['path']), tuple(arm['body']['path']), local | bound_fields)
                    return
                require(p in self.case_rows, 'unmapped DATA case')
                row = self.case_rows[p]
                visit(n['scrutinee'], p+('scrutinee',), local)
                bound_fields = {f['binding']['id'] for f in row['fields'] if f['binding'] is not None}
                visit(self.node_at(row['body']['path']), tuple(row['body']['path']), local | bound_fields)
                return
            if tag == 'with_data': visit(n['body'], p+('body',), local); return
            require(tag in ('int64', 'bool', 'primitive', 'constructor'), 'unsupported carrier syntax')
        visit(node, path, bound)
        require(len(mono)+len(pairs) <= MAX_CAPTURES, 'carrier capture count exceeds 64')
        return mono, pairs

    def captures(self, node, path, env, views, block, scope, kind, code, bound=frozenset()):
        mono, pairs = self.needed(node, path, bound)
        actual = {}; contracts = {}; inner = {}; saved = {}; temps = []
        carrier = {'carrier': len(self.carrier_map), 'source': address(path), 'kind': kind,
                   'ir_code': code, 'type_scope': scope, 'mono_captures': [], 'view_captures': []}
        self.carrier_map.append(carrier)
        for ident in sorted(mono):
            ref = env.get(ident); require(isinstance(ref, Reference), 'Scheme/bare or unavailable ordinary capture')
            name = self.fresh('capture'); actual[name] = ref.variable
            contracts[name] = {'layout': self.layout(ref.logical),
                               'relation': 'below' if ref.strict else 'down'}
            inner[ident] = Reference(name, ref.logical, strict=ref.strict)
            carrier['mono_captures'].append({'binder': ident, 'capture': name, **contracts[name]})
        for pair in self.sorted_pairs(pairs):
            ref, creation, source = self.acquire_view(pair, env, views, block); temps.append(ref)
            name = self.fresh('view'); actual[name] = ref.variable
            contracts[name] = {'layout': self.layout(ref.logical),
                               'relation': 'below' if ref.strict else 'down'}
            self.pair_work(pair, multiplier=2)
            saved[pair] = Reference(name, ref.logical, carrier['carrier'], ref.strict)
            d = self.def_by_binder[pair[0]]
            carrier['view_captures'].append({'definition': d['id'], 'binder': pair[0],
                'arguments': [self.type_name(t) for t in pair[1]], 'occurrences': pairs[pair],
                'capture': name, 'source_view': source, 'creation': creation, **contracts[name]})
        return actual, contracts, inner, saved, temps, carrier

    def code_name(self, prefix):
        self.tick(); require(self.code_count + len(self.allocation_map) < MAX_CODES, 'combined Site/Code limit')
        self.code_count += 1; return prefix + str(self.code_count)

    def generic_callable_binding(self, definition, row, typ):
        require(transport._closed_scalar_callable(row['type'], self),
                'generic callable source type is not an exact closed scalar arrow')
        require(typ[0] == 'arrow', 'generic callable import needs a root arrow')
        pending = [(typ, 1)]
        while pending:
            self.tick(); item, depth = pending.pop()
            require(depth <= MAX_TYPE_DEPTH, 'generic callable type depth limit')
            if item in SCALARS.values():
                continue
            require(item[0] == 'arrow' and item[3:] == ('repeat', 'unknown'),
                    'generic callable import requires recursive closed scalar-arrow contracts')
            pending.extend(((item[1], depth+1), (item[2], depth+1)))
        node, prefix, binding = self.root, (), None
        for part in definition['binding_source']['path']:
            self.tick()
            require(part == 'body' and node['tag'] in ('let', 'with_data'),
                    'generic callable binding must be on the concrete outer spine')
            if node['tag'] == 'let' and node['name']['id'] == row['binding']:
                binding = (prefix, node)
            node, prefix = node[part], prefix + (part,)
        require(binding is not None and binding[1]['value']['tag'] == 'lambda',
                'generic callable import requires a directly bound ordinary lambda')
        source, value = binding
        require(row['binding_source'] == address(source) and
                row['value_source'] == address(source + ('value',)),
                'generic callable source binding/value address differs')
        require(self.same_type(self.logical(value['value']['parameter_type'], None), typ[1]),
                'generic callable source parameter differs from its full contract')

    def generalized_imports(self, definition, env, block, scope):
        """Declare imports; the checked emitter acquires aliases after begin."""
        free = definition['free_term_bindings']
        if not free:
            require('captures' not in definition, 'spurious generic capture evidence')
            return {}, {}, [], []
        require(scope is None and block.root == 'entry' and not block.prefix and not self.knot_depth,
                'captured generalization requires the concrete top-level spine')
        evidence = definition.get('captures', {})
        callable_rows = evidence.get('callables', [])
        if callable_rows:
            require(set(evidence) == {'policy', 'scalars', 'callables'} and
                    evidence['policy'] == transport.GENERIC_CALLABLE_CAPTURE_POLICY,
                    'generic callable capture policy differs')
            require(type(callable_rows) is list and all(type(r) is dict and
                    set(r) == {'binding', 'type', 'occurrences', 'binding_source', 'value_source'} and
                    type(r['binding']) is int for r in callable_rows), 'generic callable import rows differ')
            self.tick(len(callable_rows))
            require([r['binding'] for r in callable_rows] == sorted({r['binding'] for r in callable_rows}),
                    'generic callable import rows must be unique and ordered')
        else:
            require(set(evidence) == {'policy', 'scalars'} and
                    evidence['policy'] == transport.GENERIC_CAPTURE_POLICY,
                    'generic scalar capture policy differs')
        rows = evidence['scalars']
        require(type(rows) is list and (0 if callable_rows else 1) <= len(rows) <= MAX_CAPTURES and
                all(type(r) is dict and set(r) == {'binding', 'type', 'occurrences'} and
                    type(r['binding']) is int for r in rows), 'generic scalar import rows differ')
        if callable_rows:
            require([r['binding'] for r in rows] == sorted({r['binding'] for r in rows}),
                    'generic scalar import rows must be unique and ordered')
            rows = sorted(rows + callable_rows, key=lambda r:r['binding'])
            self.tick(len(rows))
        require(1 <= len(rows) <= MAX_CAPTURES and
                [r['binding'] for r in rows] == free == sorted(set(free)),
                'generic import binding inventory differs')
        cursor_path = tuple(definition['rhs_cursor']['path'])
        cursor = self.node_at(cursor_path)
        require(cursor['tag'] == 'lambda', 'captured generic RHS must remain a direct lambda')
        mono, pairs = self.needed(cursor, cursor_path)
        require(not pairs and sorted(mono) == free, 'generic scalar free binding partition differs')
        occurrences = {ident: [] for ident in free}
        for suffix, node in transport._walk(cursor):
            self.tick()
            if node['tag'] == 'var' and node['name']['id'] in occurrences:
                occurrences[node['name']['id']].append(address(cursor_path + suffix))
        imports = {}; inner = {}; support = []; mapping = []
        for row in rows:
            self.tick()
            ident = row['binding']; ref = env.get(ident)
            typ = self.logical(row['type'], None)
            if 'binding_source' in row:
                self.generic_callable_binding(definition, row, typ)
                if isinstance(ref, Reference):
                    self.tick(self.type_cost(typ)[1] + self.type_cost(ref.logical)[1])
            else:
                require(set(row) == {'binding', 'type', 'occurrences'} and typ in SCALARS.values(),
                        'generic scalar capture fields/type differ')
            require(isinstance(ref, Reference) and self.same_type(ref.logical, typ),
                    'generic import requires an exact available Reference')
            require(row['occurrences'] == occurrences[ident] and occurrences[ident],
                    'generic scalar capture occurrences differ')
            name = self.fresh('import')
            contract = {'value': ref.variable, 'layout': self.layout(typ), 'relation': 'down'}
            imports[name] = contract
            inner[ident] = Reference(name, typ, strict=ref.strict)
            support.append(ref)
            mapping.append({'binding': ident, 'import': name, **contract,
                            'occurrences': row['occurrences']})
        return dict(sorted(imports.items())), inner, support, mapping

    def emit(self, node, path, env, views, home, block, scope):
        self.tick(); tag = node['tag']
        if tag == 'with_data':
            require(not path, 'only outer evidence declarations supported')
            return self.emit(node['body'], path+('body',), env, views, home, block, scope)
        if tag == 'type_application':
            require(path in self.uses, 'unmapped shared use')
            u = self.uses[path]; basepath = tuple(u['variable']['path'])
            base = self.node_at(basepath)
            self.term(base, basepath, 'shared-use')
            ref, creation, source = self.acquire_view(self.use_pairs[path], env, views, block)
            self.use_map.append({'use': u['id'], 'source': address(path), 'definition': u['definition'],
                                 'arguments': [self.type_name(t) for t in self.use_pairs[path][1]],
                                 'creation': creation, 'source_view': source})
            require(self.same_type(ref.logical, self.use_types[path]), 'captured full-vector view mismatch')
            return ref
        if path in self.constructor_rows:
            return self.constructor(node, path, env, views, home, block, scope)
        if path in self.sum_constructor_rows:
            return self.sum_constructor(node, path, env, views, home, block, scope)
        # Saturated builtin scalar operations remain delayed complete operand
        # graphs. This is checked primitive-ID lowering, never user-code inlining.
        if tag == 'application':
            head = node; hp = path; args = []; spine = []
            while head['tag'] == 'application':
                spine.append((head,hp)); args.append((head['argument'],hp+('argument',)))
                head = head['function']; hp += ('function',)
            if head['tag'] == 'primitive':
                if scope is not None:
                    require(block.root in ('function', 'thunk') and block.scope == scope,
                            'generic scalar computation must remain inside scoped callback Code')
                for n,p in spine: self.term(n,p,'primitive-spine')
                self.term(head,hp,'primitive')
                return self.primitive(node,path,head,list(reversed(args)),env,views,home,block,scope)
        self.term(node,path)
        if tag == 'case':
            if path in self.sum_case_rows:
                return self.sum_case(node, path, env, views, home, block, scope)
            return self.data_case(node, path, env, views, home, block, scope)
        if tag in ('int64','bool'):
            typ = SCALARS['Int' if tag=='int64' else 'Bool']; out = self.fresh()
            key,split,placement = self.allocation(home,[],block,path,'scalar',scope)
            self.add(block,path,typ,op='scalar',out=out,**{'in':key},kind='i64' if tag=='int64' else 'bool',value=node['value'])
            self.close_builder(key,split,placement,block)
            return Reference(out,typ,strict=split)
        if tag == 'var':
            ref = env.get(node['name']['id']); require(isinstance(ref,Reference), 'ordinary variable cannot be Scheme')
            out=self.fresh(); self.add(block,op='retain',out=out,value=ref.variable)
            return Reference(out,ref.logical,strict=ref.strict)
        if tag == 'letrec':
            return self.recursive(node, path, env, views, home, block, scope)
        if tag == 'let':
            d = self.def_by_path.get(path)
            if d is not None:
                require(scope is None, 'nested generic definition')
                imports, inner, support, import_map = self.generalized_imports(d,env,block,scope)
                scheme='S'+str(d['id']); out=self.fresh('shared')
                key,split,placement = self.allocation(home,support,block,path,'shared-rhs',scope)
                child=Block(block.root,block.name,[],block.prefix+(len(block.body),'body'),scheme)
                cursor=self.node_at(d['rhs_cursor']['path'])
                result=self.emit(cursor,tuple(d['rhs_cursor']['path']),inner, {}, '$home',child,scheme)
                require(self.same_type(result.logical, self.definition_types[d['id']]), 'generic RHS actual result type differs')
                for ref in inner.values(): self.release(ref,child)
                seal=self.add(child,op='seal',value=result.variable)
                extra = {'imports': imports} if imports else {}
                intro=self.add(block,op='generalize',out=out,**{'in':key},scheme=scheme,body=child.body,**extra)
                self.close_builder(key,split,placement,block)
                ref=SchemeReference(out,d['id'],strict=split)
                self.scheme_map.append({'definition':d['id'],'binder':d['binding']['id'],'scheme':scheme,
                    'generalize':intro,'seal':seal,'rhs_cursor':d['rhs_cursor'],'result_owner':result.variable})
                if imports:
                    self.scheme_map[-1]['imports'] = import_map
            else:
                ref=self.emit(node['value'],path+('value',),env,views,home,block,scope)
            result=self.emit(node['body'],path+('body',),env|{node['name']['id']:ref},views,home,block,scope)
            self.release(ref,block); return result
        if tag == 'lambda':
            name=self.code_name('F')
            actual,contracts,inner,saved,temps,carrier=self.captures(node,path,env,views,block,scope,'lambda',name)
            parameter=self.fresh('argument'); parameter_type=self.logical(node['parameter_type'],scope)
            inner[node['parameter']['id']]=Reference(parameter,parameter_type)
            callback=Block('function',name,[],scope=scope)
            result=self.emit(node['body'],path+('body',),inner,saved,'$home',callback,scope)
            for ref in list(inner.values())+list(saved.values()): self.release(ref,callback)
            self.add(callback,op='return',value=result.variable)
            typ=arrow(parameter_type,result.logical)
            self.functions[name]={'signature':self.signature(typ),'parameter':parameter,'captures':contracts,
                                  'body':callback.body,'type_scope':scope}
            key,split,placement = self.allocation(home,[],block,path,'closure',scope,eligible=not actual)
            out=self.fresh(); publication=self.add(block,path,typ,op='closure',out=out,**{'in':key},function=name,captures=actual)
            for row in carrier['view_captures']: row['creation'].append(publication)
            for row,ref in zip(carrier['view_captures'],temps):
                release=self.add(block,op='drop',value=ref.variable)
                # One pair temp per view capture, in deterministic pair order.
                row['creation'].append(release)
            self.close_builder(key,split,placement,block)
            return Reference(out,typ,strict=split)
        if tag == 'application':
            fn=self.emit(node['function'],path+('function',),env,views,home,block,scope)
            arg=self.emit(node['argument'],path+('argument',),env,views,home,block,scope)
            require(fn.logical[0]=='arrow' and self.same_type(fn.logical[1], arg.logical), 'complete ordinary callable argument mismatch')
            out=self.fresh(); typ=fn.logical[2]
            key,split,placement = self.allocation(home,[fn,arg],block,path,'application',scope)
            self.add(block,path,typ,op='application',out=out,**{'in':key},function=fn.variable,argument=arg.variable)
            self.release(fn,block); self.release(arg,block)
            self.close_builder(key,split,placement,block)
            return Reference(out,typ,strict=split)
        raise PlanningError('unsupported planning constructor: '+tag)

    def recursive(self, node, path, env, views, home, block, scope):
        """Construct one concrete function knot without demand or code shortcuts.

        Transport independently checks the admitted RHS function spine. Its
        ordinary wrapper applications must still be constructed and filled as
        the actual RHS root, not replaced by the lambda at the spine's end.
        """
        require(scope is None and not self.knot_map and len(node['bindings']) == 1,
                'only one concrete singleton recursive function is supported')
        binding = node['bindings'][0]; ident = binding['name']['id']
        require(ident not in env, 'recursive binder already in lexical scope')
        typ = self.logical(binding['type'], None)
        require(typ[0] == 'arrow' and typ[3:] == ('repeat','unknown'),
                'recursive binding requires a closed Repeat/unknown arrow')
        rhs_path = path+('bindings','0','value')
        evidence = self.recursion_rows.get(path)
        require(evidence is not None and evidence['source'] == address(path) and
                evidence['binding_source'] == address(path+('bindings','0')) and
                evidence['binding'] == binding['name'] and evidence['type'] == binding['type'] and
                evidence['rhs'] == address(rhs_path) and evidence['body'] == address(path+('body',)),
                'recursive source evidence differs')
        mono,pairs = self.needed(binding['value'],rhs_path,frozenset((ident,)))
        inner,saved = self.recursive_captures(evidence,mono,pairs,env,views)
        row = {'source':address(path), 'binding_source':address(path+('bindings','0')),
               'binder':binding['name'], 'logical_type':self.type_name(typ),
               'rhs':address(rhs_path), 'body':address(path+('body',)),
               'function_source':evidence['function_source'], 'wrappers':evidence['wrappers'],
               'self_uses':evidence['self_uses'],
               'home':home, 'type_scope':None}
        if mono or pairs:
            row['captures'] = evidence['captures']
        self.knot_map.append(row)
        hole = self.fresh('hole'); self_owner = self.fresh('self')
        row['hole'] = self.add(block,path,typ,op='hole',out=hole,**{'in':home},layout=self.layout(typ))
        row['retain_self'] = self.add(block,op='retain',out=self_owner,value=hole)
        row['hole_owner'] = hole; row['self_owner'] = self_owner
        # The retained owner carries no fill ticket. The original remains local
        # until exactly one Fill, before any letrec-body demand can be emitted.
        inner[ident] = Reference(self_owner,typ)
        self.knot_depth += 1
        try:
            rhs = self.emit(binding['value'],rhs_path,inner,saved,home,block,None)
        finally:
            self.knot_depth -= 1
        require(self.same_type(rhs.logical, typ), 'recursive RHS differs from its full annotation')
        row['rhs_owner'] = rhs.variable
        row['fill'] = self.add(block,op='fill',hole=hole,value=rhs.variable)
        row['drop_rhs'] = self.add(block,op='drop',value=rhs.variable)
        row['drop_self'] = self.add(block,op='drop',value=self_owner)
        result = self.emit(node['body'],path+('body',),
                           env|{ident:Reference(hole,typ)},views,home,block,None)
        row['body_result'] = result.variable
        row['drop_hole'] = self.add(block,op='drop',value=hole)
        return result

    def recursive_captures(self, evidence, mono, pairs, env, views):
        """Carry existing ordinary owners and saved full-vector views unchanged.

        The knot retains its current home. Incoming strict support facts remain
        valid; capture/Instantiate publication uses the ordinary machinery and
        never relabels a shared target as a concrete/E0 allocation.
        """
        inner = {}; saved = {}
        if not mono and not pairs:
            require(evidence['free_term_bindings'] == [] and 'captures' not in evidence,
                    'spurious recursive capture evidence')
            return inner,saved
        self.tick(len(mono)+len(pairs))
        require(evidence['free_term_bindings'] == sorted(mono|{pair[0] for pair in pairs}),
                'recursive free binding inventory differs')
        require(len(mono)+len(pairs)+bool(evidence['self_uses']) <= MAX_CAPTURES,
                'recursive carrier capture count exceeds 64')
        captures = evidence.get('captures')
        require(captures is not None, 'recursive capture evidence missing')
        callables = captures.get('callables', [])
        nominals = captures.get('nominals', [])
        admitted_callables = captures['policy'] == 'closed-admitted-callable-shared-view-captures/1'
        if captures['policy'] == 'closed-scalar-shared-view-captures/1':
            require('callables' not in captures and 'nominals' not in captures and
                    [row['binding']['id'] for row in captures['scalars']] == sorted(mono),
                    'recursive scalar capture inventory differs')
        elif captures['policy'] == 'closed-scalar-callable-shared-view-captures/1':
            require(callables and 'nominals' not in captures,
                    'recursive capture policy differs')
            self.tick(len(callables)+len(captures['scalars']))
            scalar_ids = [row['binding']['id'] for row in captures['scalars']]
            callable_ids = [row['binding']['id'] for row in callables]
            require(scalar_ids == sorted(set(scalar_ids)) and callable_ids == sorted(set(callable_ids)) and
                    not set(scalar_ids).intersection(callable_ids) and
                    set(scalar_ids)|set(callable_ids) == mono, 'recursive ordinary capture partition differs')
        else:
            require((captures['policy'] == 'closed-scalar-callable-nominal-shared-view-captures/1' and
                     nominals and 'callables' in captures) or
                    (admitted_callables and callables and
                     set(captures) == {'policy','scalars','callables','nominals','views'}),
                    'recursive capture policy differs')
            self.tick(len(captures['scalars'])+len(callables)+len(nominals))
            categories = [[row['binding']['id'] for row in rows]
                          for rows in (captures['scalars'],callables,nominals)]
            ordinary = [ident for ids in categories for ident in ids]
            require(all(ids == sorted(set(ids)) for ids in categories) and
                    len(ordinary) == len(set(ordinary)) and set(ordinary) == mono,
                    'recursive ordinary capture partition differs')
        for row in captures['scalars']:
            ident = row['binding']['id']; typ = self.logical(row['type'],None)
            source = env.get(ident)
            require(typ in SCALARS.values() and isinstance(source,Reference) and self.same_type(source.logical, typ),
                    'recursive ordinary capture must be an available closed scalar owner')
            inner[ident] = source
        nominal_callable = False
        for row in callables:
            ident = row['binding']['id']; typ = self.logical(row['type'],None)
            require(typ[0] == 'arrow', 'recursive callable capture must have an arrow root')
            work = [typ]
            while work:
                self.tick(); part = work.pop()
                if part in SCALARS.values():
                    continue
                if admitted_callables and part[0] == 'nominal':
                    require(part in self.nominal_layouts,
                            'recursive callable nominal leaf lacks a published declaration')
                    nominal_callable = True
                    continue
                require(part[0] == 'arrow' and part[3:] == ('repeat','unknown'),
                        'recursive callable capture requires exact closed scalar-arrow structure')
                work.extend((part[1],part[2]))
            source = env.get(ident)
            require(isinstance(source,Reference) and self.same_type(source.logical, typ),
                    'recursive callable capture must be an available exact ordinary owner')
            # In particular, do not acquire a Scheme view or inspect readiness
            # here. A pending owner may eventually resolve to a shared Instance.
            inner[ident] = source
        require(not admitted_callables or nominal_callable,
                'admitted-callable policy requires a captured arrow with a nominal leaf')
        for row in nominals:
            ident = row['binding']['id']; typ = self.logical(row['type'],None)
            require(typ[0] == 'nominal' and type(row['declaration']) is int and
                    row['declaration'] == typ[1], 'recursive nominal declaration identity differs')
            source = env.get(ident)
            require(isinstance(source,Reference) and self.same_type(source.logical, typ),
                    'recursive nominal capture must be an available exact ordinary owner')
            # The logical atom includes the replayed declaration index, name,
            # and source path. Keep this owner's support and Access untouched;
            # its fields are not captures to reconstruct or eagerly project.
            inner[ident] = source
        keys = []
        for row in captures['views']:
            vector = tuple(self.logical(t,None) for t in row['arguments'])
            require(all(t in SCALARS.values() for t in vector) or
                    all(self.closed_argument(t) for t in vector),
                    'recursive view vector must be closed intrinsic/admitted nominal/Repeat-unknown types')
            pair = (row['binding']['id'],vector); keys.append(pair)
            self.pair_work(pair, multiplier=2)
            definition = self.def_by_binder.get(pair[0])
            require(definition is not None and row['definition'] == definition['id'] and
                    row['binding'] == definition['binding'] and len(vector) == len(definition['prefix']) and
                    pair in pairs and row['uses'] == pairs[pair], 'recursive shared-view inventory differs')
            typ = self.substitute(self.definition_types[definition['id']], 'S'+str(definition['id']),vector)
            require(self.same_type(self.logical(row['instantiated_type'],None), typ), 'recursive shared-view full type differs')
            self.pair_work(pair)
            source = views.get(pair)
            if source is not None:
                require(isinstance(source,Reference) and self.same_type(source.logical, typ) and source.carrier is not None,
                        'recursive saved view is unavailable or has a different type')
                self.pair_work(pair)
                saved[pair] = source
            else:
                source = env.get(pair[0])
                require(isinstance(source,SchemeReference) and source.definition == definition['id'],
                        'recursive shared view lacks its lexical Scheme owner')
                inner[pair[0]] = source
        require(self.same_pairs(keys, self.sorted_pairs(pairs)), 'recursive complete-vector capture inventory differs')
        return inner,saved

    def constructor(self, node, path, env, views, home, block, scope):
        require(scope is None, 'generic DATA construction unsupported')
        row = self.constructor_rows[path]; declaration = self.nominal_rows[row['declaration']]
        head_path = tuple(row['head']['path']); head = self.node_at(head_path)
        require(head['tag'] == 'constructor' and head['name'] == declaration['constructor'] and
                head['arguments'] == [], 'constructor declaration differs')
        for source in row['application_spine']:
            sp = tuple(source['path']); term = self.node_at(sp)
            require(term['tag'] == 'application', 'constructor spine differs')
            self.term(term, sp, 'constructor-spine')
        self.term(head, head_path, 'constructor')
        expected = [self.logical(t, None) for t in declaration['field_types']]
        require(len(row['arguments']) == len(expected), 'constructor must be saturated')
        fields = []
        for source,typ in zip(row['arguments'], expected):
            ap = tuple(source['path']); ref = self.emit(self.node_at(ap), ap, env, views, home, block, None)
            require(self.same_type(ref.logical, typ), 'exact constructor field type differs')
            fields.append(ref)
        typ = self.logical(row['result_type'], None); out = self.fresh('data')
        require(self.same_type(typ, self.logical(declaration['type'], None)), 'constructor nominal identity differs')
        key,split,placement = self.allocation(home,fields,block,path,'data',scope)
        publication = self.add(block, path, typ, op='alloc', out=out, **{'in':key},
                               layout=self.nominal_layouts[typ],
                               fields={'f'+str(i): ref.variable for i,ref in enumerate(fields)})
        for ref in fields: self.release(ref, block)
        self.close_builder(key,split,placement,block)
        self.constructor_map.append({'source': address(path), 'declaration': row['declaration'],
                                     'head': row['head'], 'arguments': row['arguments'],
                                     'allocation': publication})
        return Reference(out, typ, strict=split)

    def sum_constructor(self, node, path, env, views, home, block, scope):
        require(scope is None, 'generic SUM construction unsupported')
        row = self.sum_constructor_rows[path]; declaration = self.sum_rows[row['declaration']]
        variant = declaration['variants'][row['variant']]
        hp = tuple(row['head']['path']); head = self.node_at(hp)
        require(head['tag'] == 'constructor' and head['name'] == variant['constructor'] and
                head['arguments'] == [], 'SUM constructor declaration differs')
        for source in row['application_spine']:
            sp = tuple(source['path']); term = self.node_at(sp)
            require(term['tag'] == 'application', 'SUM constructor spine differs')
            self.term(term, sp, 'constructor-spine')
        self.term(head, hp, 'constructor')
        expected = [self.logical(t, None) for t in variant['field_types']]
        require(len(row['arguments']) == len(expected), 'SUM constructor must be saturated')
        fields = []
        for source,typ in zip(row['arguments'], expected):
            ap = tuple(source['path']); ref = self.emit(self.node_at(ap), ap, env, views, home, block, None)
            require(self.same_type(ref.logical, typ) and (typ in SCALARS.values() or
                    self.same_type(typ, self.logical(declaration['type'], None))),
                    'SUM field exact scalar/self type differs')
            fields.append(ref)
        typ = self.logical(row['result_type'], None)
        require(self.same_type(typ, self.logical(declaration['type'], None)), 'SUM nominal identity differs')
        out = self.fresh('sum'); family = self.sum_families[row['declaration']]
        instruction = {'op':'construct_sum' if fields else 'construct_nullary', 'out':out,
                       'in':home, 'family':family, 'variant':'V'+str(row['variant'])}
        if fields: instruction['fields'] = [r.variable for r in fields]
        publication = self.add(block, path, typ, **instruction)
        for ref in fields: self.release(ref, block)
        self.sum_constructor_map.append({'source':address(path), 'declaration':row['declaration'],
                                         'variant':row['variant'], 'head':row['head'],
                                         'arguments':row['arguments'], 'allocation':publication})
        # SUM placement is intentionally coarse, independently of data_groups.
        return Reference(out, typ)

    def sum_case(self, node, path, env, views, home, block, scope):
        require(scope is None, 'generic SUM case unsupported')
        row = self.sum_case_rows[path]; declaration = self.sum_rows[row['declaration']]
        typ = self.logical(row['result_type'], None)
        require(typ == SCALARS['Int'], 'SUM factory case requires exact Int result')
        name = self.code_name('C')
        actual,contracts,inner,saved,temps,carrier = self.captures(
            node,path,env,views,block,None,'sum-case',name)
        cb = Block('thunk',name,[])
        sp = tuple(row['scrutinee']['path'])
        raw = self.emit(self.node_at(sp),sp,inner,saved,'$home',cb,None)
        require(self.same_type(raw.logical, self.logical(declaration['type'],None)), 'SUM case nominal identity differs')
        ready = self.fresh('sumready'); self.add(cb,op='force',out=ready,value=raw.variable)
        factory = {}; arm_maps = []; arm_temps = []
        require(len(row['arms']) == len(declaration['variants']), 'SUM case must be exhaustive')
        # Compile actual source arms once, retaining their order/identity. The
        # factory table below is joined separately to declaration variant order.
        for arm in row['arms']:
            self.tick(); variant = arm['variant']; v = declaration['variants'][variant]
            key = 'V' + str(variant)
            require(key not in factory and arm['constructor'] == v['constructor'],
                    'SUM arm duplicate or constructor identity differs')
            bp = tuple(arm['body']['path']); body = self.node_at(bp)
            bound = frozenset(f['binding']['id'] for f in arm['fields'] if f['binding'] is not None)
            code = self.code_name('C')
            external,captures,arm_env,arm_views,views_owned,arm_carrier = self.captures(
                body,bp,inner,saved,cb,None,'sum-arm',code,bound)
            require(len(external) <= 32, 'SUM factory external capture count exceeds32')
            bindings = {n:{'kind':'external','value':value} for n,value in external.items()}
            field_map = []
            for f in arm['fields']:
                self.tick()
                if f['binding'] is None: continue
                capture = self.fresh('sumfield'); ft = self.logical(f['type'],None)
                require((ft in SCALARS.values() or ft == self.logical(declaration['type'],None)) and
                        ft == self.logical(v['field_types'][f['index']],None),
                        'SUM pattern field exact scalar/self type differs')
                captures[capture] = {'layout':self.layout(ft),'relation':'down'}
                bindings[capture] = {'kind':'field','index':f['index']}
                arm_env[f['binding']['id']] = Reference(capture,ft)
                field_map.append({'index':f['index'],'binder':f['binding']['id'],'capture':capture,
                                  'type':self.type_name(ft),'relation':'down'})
            require(len(field_map) <= 32 and len(captures) <= MAX_CAPTURES,
                    'SUM factory capture count exceeds field/total bounds')
            arm_carrier['field_captures'] = field_map
            ab = Block('thunk',code,[])
            result = self.emit(body,bp,arm_env,arm_views,'$home',ab,None)
            require(self.same_type(result.logical, typ), 'SUM arm result exact Int type differs')
            for ref in list(arm_env.values())+list(arm_views.values()): self.release(ref,ab)
            self.add(ab,op='return',value=result.variable)
            self.codes[code] = {'result':self.layout(typ),'captures':captures,'body':ab.body,'type_scope':None}
            factory[key] = {'code':code,'captures':bindings}
            arm_maps.append({'index':arm['index'],'variant':variant,'constructor':arm['constructor'],
                             'pattern_source':arm['pattern_source'],'source':arm['body'],
                             'code':code,'captures':bindings,'field_captures':field_map})
            arm_temps.append((arm_carrier,views_owned))
        family = self.sum_families[row['declaration']]
        require(set(factory) == set(self.families[family]['variants']), 'SUM factory variant coverage differs')
        selected = self.fresh('selected')
        selection = self.add(cb,op='case_fields_i64',out=selected,**{'in':'$home'},family=family,
                             scrutinee=ready,arms={v:factory[v] for v in self.families[family]['variants']})
        for arm in arm_maps:
            self.tick(); require(len(self.allocation_map)+self.code_count < MAX_CODES, 'combined Site/Code limit')
            self.allocation_map.append({'source':arm['source'],'instruction':selection,'arm':arm['variant'],
                                        'role':'case_fields_i64','type_scope':None,
                                        'logical_type':self.type_name(typ)})
        # No unselected body was constructed. Temporary views were only retained
        # from already existing full-vector captures, never forced or cloned.
        for arm_carrier,owned in arm_temps:
            for view,ref in zip(arm_carrier['view_captures'],owned):
                view['creation'].append(selection)
                view['creation'].append(self.add(cb,op='drop',value=ref.variable))
        drop_scrutinee = self.add(cb,op='drop',value=ready)
        for ref in list(inner.values())+list(saved.values()): self.release(ref,cb)
        self.add(cb,op='return',value=selected)
        self.codes[name] = {'result':self.layout(typ),'captures':contracts,'body':cb.body,'type_scope':None}
        out = self.fresh('case')
        publication = self.add(block,path,typ,op='thunk',out=out,**{'in':home},code=name,captures=actual)
        for view,ref in zip(carrier['view_captures'],temps):
            view['creation'].append(publication)
            view['creation'].append(self.add(block,op='drop',value=ref.variable))
        self.sum_case_map.append({'source':address(path),'declaration':row['declaration'],'family':family,
                                  'code':name,'result_type':self.type_name(typ),'arms':arm_maps,
                                  'factory':selection,'drop_scrutinee':drop_scrutinee,'allocation':publication})
        return Reference(out,typ)

    def data_case(self, node, path, env, views, home, block, scope):
        require(scope is None and path in self.case_rows, 'unmapped or generic DATA case')
        row = self.case_rows[path]; declaration = self.nominal_rows[row['declaration']]
        typ = self.logical(row['result_type'], None); name = self.code_name('C')
        actual,contracts,inner,saved,temps,carrier = self.captures(
            node,path,env,views,block,None,'data-case',name)
        cb = Block('thunk',name,[])
        sp = tuple(row['scrutinee']['path'])
        raw = self.emit(self.node_at(sp),sp,inner,saved,'$home',cb,None)
        require(self.same_type(raw.logical, self.logical(declaration['type'],None)), 'case nominal identity differs')
        ready = self.fresh('container'); self.add(cb,op='force',out=ready,value=raw.variable)
        fields = {}; projections = []
        for f in row['fields']:
            self.tick()
            if f['binding'] is None: continue
            loan = self.fresh('fieldloan'); owned = self.fresh('field')
            acquire = self.add(cb,op='field',out=loan,value=ready,field='f'+str(f['index']))
            retain = self.add(cb,op='retain',out=owned,value=loan)
            end = self.add(cb,op='end_borrow',value=loan)
            fields[f['binding']['id']] = Reference(owned,self.logical(f['type'],None),strict=raw.strict)
            projections.append({'index':f['index'],'binder':f['binding']['id'],
                                'loan':acquire,'retain':retain,'end_borrow':end})
        drop_container = self.add(cb,op='drop',value=ready)
        bp = tuple(row['body']['path'])
        early_releases = []
        if self.data_groups:
            # A capture used only to reach the scrutinee need not remain an
            # owner during arm construction. Keep every transitive arm use,
            # including nested lambdas and complete-vector view occurrences.
            needed_mono,needed_pairs = self.needed(self.node_at(bp),bp,frozenset(fields))
            for ident,ref in list(inner.items()):
                self.tick()
                if ident not in needed_mono:
                    early_releases.append(self.add(cb,op='drop',value=ref.variable))
                    del inner[ident]
            for pair,ref in list(saved.items()):
                self.pair_work(pair, multiplier=2)
                self.tick()
                if pair not in needed_pairs:
                    early_releases.append(self.add(cb,op='drop',value=ref.variable))
                    del saved[pair]
        result = self.emit(self.node_at(bp),bp,inner|fields,saved,'$home',cb,None)
        require(self.same_type(result.logical, typ), 'case result full type differs')
        for ref in list(inner.values())+list(saved.values())+list(fields.values()): self.release(ref,cb)
        self.add(cb,op='return',value=result.variable)
        self.codes[name] = {'result':self.layout(typ),'captures':contracts,'body':cb.body,'type_scope':None}
        out = self.fresh('case')
        publication = self.add(block,path,typ,op='thunk',out=out,**{'in':home},code=name,captures=actual)
        for capture,ref in zip(carrier['view_captures'],temps):
            capture['creation'].append(publication)
            capture['creation'].append(self.add(block,op='drop',value=ref.variable))
        self.case_map.append({'source':address(path),'declaration':row['declaration'],
                              'code':name,'result_type':self.type_name(typ),
                              'projections':projections,'drop_container':drop_container,
                              'allocation':publication})
        if self.data_groups:
            self.case_map[-1]['early_capture_releases'] = early_releases
        return Reference(out,typ)

    def delayed(self,node,path,env,views,home,block,kind,scope=None):
        # Opt-in only: a plain Int variable already denotes an owned lazy value.
        # Retain its complete original owner/Access instead of wrapping it in
        # another thunk. Never force, substitute, clone or inline its RHS.
        if self.reuse_int_branches and node['tag'] == 'var':
            self.tick()
            ref = env.get(node['name']['id'])
            if isinstance(ref, Reference) and ref.logical == SCALARS['Int']:
                require(kind in ('conditional-then', 'conditional-else'),
                        'branch owner reuse requires a conditional branch')
                index = len(block.body)
                result = self.emit(node,path,env,views,home,block,scope)
                require(len(block.body) == index + 1 and
                        block.body[index] == {'op':'retain','out':result.variable,'value':ref.variable},
                        'branch owner reuse must emit exactly one original-owner retain')
                self.branch_owner_reuse.append({'source':address(path), 'branch':kind,
                    'binding':node['name']['id'], 'type_scope':scope,
                    'logical_type':self.type_name(result.logical), 'source_owner':ref.variable,
                    'retained_owner':result.variable, 'retain':block.path(index)})
                return result
        name=self.code_name('C')
        actual,contracts,inner,saved,temps,carrier=self.captures(node,path,env,views,block,scope,kind,name)
        if scope is not None:
            require(not saved and all(ref.logical in SCALARS.values() for ref in inner.values()),
                    'generic scalar branch requires closed scalar dependencies')
        cb=Block('thunk',name,[],scope=scope); result=self.emit(node,path,inner,saved,'$home',cb,scope)
        require(result.logical==SCALARS['Int'], 'conditional branches require Int')
        for ref in list(inner.values())+list(saved.values()): self.release(ref,cb)
        self.add(cb,op='return',value=result.variable)
        self.codes[name]={'result':self.layout(result.logical),'captures':contracts,'body':cb.body,'type_scope':scope}
        out=self.fresh(); publication=self.add(block,path,result.logical,op='thunk',out=out,**{'in':home},code=name,captures=actual)
        for row,ref in zip(carrier['view_captures'],temps):
            row['creation'].append(publication); row['creation'].append(self.add(block,op='drop',value=ref.variable))
        return Reference(out,result.logical)

    def primitive(self,node,path,head,args,env,views,home,block,scope=None):
        conditional=head['id']==13
        require((conditional and head['name']=='ifThenElse' and len(args)==3) or
                (head['id'] in PRIMITIVES and head['name']==PRIMITIVES[head['id']][0] and len(args)==2),
                'primitive must be directly and fully saturated')
        name=self.code_name('C'); typ=SCALARS['Int'] if conditional else PRIMITIVES[head['id']][1]
        actual,contracts,inner,saved,temps,carrier=self.captures(node,path,env,views,block,scope,'conditional' if conditional else 'primitive',name)
        if scope is not None:
            require(not saved and all(ref.logical in SCALARS.values() for ref in inner.values()),
                    'generic scalar computation requires closed scalar dependencies')
        cb=Block('thunk',name,[],scope=scope)
        left=self.emit(*args[0],inner,saved,'$home',cb,scope); ready=self.fresh()
        require(left.logical==(SCALARS['Bool'] if conditional else SCALARS['Int']), 'primitive left type')
        self.add(cb,op='force',out=ready,value=left.variable)
        result=self.fresh()
        if conditional:
            yes=self.delayed(*args[1],inner,saved,'$home',cb,'conditional-then',scope)
            no=self.delayed(*args[2],inner,saved,'$home',cb,'conditional-else',scope)
            self.add(cb,op='select_i64',out=result,**{'in':'$home'},condition=ready,**{'then':yes.variable,'else':no.variable})
        else:
            right=self.emit(*args[1],inner,saved,'$home',cb,scope); ready_right=self.fresh()
            require(right.logical==SCALARS['Int'], 'primitive right type')
            self.add(cb,op='force',out=ready_right,value=right.variable)
            self.add(cb,path,typ,op='prim2',out=result,**{'in':'$home'},primitive=head['name'],left=ready,right=ready_right)
            self.add(cb,op='drop',value=ready_right)
        self.add(cb,op='drop',value=ready)
        for ref in list(inner.values())+list(saved.values()): self.release(ref,cb)
        self.add(cb,op='return',value=result)
        self.codes[name]={'result':self.layout(typ),'captures':contracts,'body':cb.body,'type_scope':scope}
        out=self.fresh(); publication=self.add(block,path,typ,op='thunk',out=out,**{'in':home},code=name,captures=actual)
        for row,ref in zip(carrier['view_captures'],temps):
            row['creation'].append(publication); row['creation'].append(self.add(block,op='drop',value=ref.variable))
        return Reference(out,typ)

    def finish(self):
        block=Block('entry',None,[]); self.add(block,op='new_root',out='root',imports=[])
        result=self.emit(self.root,(),{}, {},'root',block,None)
        require(result.logical in SCALARS.values(), 'entry requires closed scalar result')
        require(self.same_type(result.logical, self.logical(self.fragment['checked_type'],None)), 'fragment root result differs')
        ready=self.fresh(); self.add(block,op='force',out=ready,value=result.variable)
        self.add(block,op='drop',value='root'); self.add(block,op='finish_scalar',value=ready)
        expected={tuple(r['normalized']['path']):r['tag'] for r in self.fragment['term_correspondence']}
        require({p:r['tag'] for p,r in self.term_map.items()}==expected, 'ordinary node coverage differs from independent correspondence')
        require(sorted(r['use'] for r in self.use_map)==list(range(len(self.uses))), 'missing/repeated lowered shared occurrence')
        require(len(self.knot_map) == len(self.recursion_rows), 'missing/repeated recursive source occurrence')
        program={'version':8,'layouts':self.layouts,'families':self.families,'signatures':self.signatures,'types':self.types,
                 'schemes':self.schemes,'instantiations':self.instantiations,'functions':self.functions,
                 'codes':self.codes,'entry':block.body}
        source_map={'scheme_map':self.scheme_map,'use_map':self.use_map,'carrier_map':self.carrier_map,
                    'allocation_map':self.allocation_map,'term_map':list(self.term_map.values())}
        if self.nominal_rows:
            require(len(self.constructor_map)==len(self.constructor_rows) and len(self.case_map)==len(self.case_rows),
                    'missing/repeated nominal source occurrence')
            source_map.update(nominal_map=self.nominal_map, constructor_map=self.constructor_map, case_map=self.case_map)
        if self.sum_rows:
            require(len(self.sum_constructor_map)==len(self.sum_constructor_rows) and
                    len(self.sum_case_map)==len(self.sum_case_rows), 'missing/repeated SUM source occurrence')
            source_map.update(sum_map=self.sum_map, sum_constructor_map=self.sum_constructor_map,
                              sum_case_map=self.sum_case_map)
        if self.data_groups:
            source_map['group_map'] = self.group_map
        if self.knot_map:
            source_map['knot_map'] = self.knot_map
        if self.reuse_int_branches:
            source_map['branch_owner_reuse'] = self.branch_owner_reuse
        encoded=json.dumps(program,sort_keys=True,separators=(',',':'),ensure_ascii=False)
        result={'program':program,'binding':{'status':'candidate-not-resource-checked','fragment_only':True,
                'source_admitted':False,'ordinary_K_checked':False,
                'mode':'data-groups-prototype' if self.data_groups else 'coarse-owned',
                'input_sha256':hashlib.sha256(json.dumps(self.fragment['input_annotated'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),
                'candidate_sha256':hashlib.sha256(encoded.encode()).hexdigest(),'source_map':source_map,
                'work':self.work,'instructions':self.instructions}}
        if self.reuse_int_branches:
            result['binding']['optimizations'] = {'int_branch_owner_reuse': {
                'policy':'plain-int-variable-branch-owner-reuse/1',
                'reused_branches':len(self.branch_owner_reuse)}}
        require(len(json.dumps(result,ensure_ascii=False).encode('utf-8'))<=MAX_OUTPUT_BYTES, 'planner output byte limit')
        return result


def plan_fragment(projected_annotated, *, fragment=None, data_groups=False, reuse_int_branches=False):
    """Fresh proof replay, then isolated candidate lowering, never source custody.

    Supplying a fragment is not an authority shortcut: all fields are recomputed
    and compared by validate_shared_fragment. Caller objects are not mutated.
    Every execution caller must independently resource-check the returned raw IR.
    reuse_int_branches opts into retaining plain Int branch variables directly;
    the default plan and source-admission boundary remain unchanged.
    """
    checked = (transport.derive_shared_fragment(projected_annotated) if fragment is None else
               transport.validate_shared_fragment(projected_annotated, fragment))
    return Planner(checked,data_groups=data_groups,reuse_int_branches=reuse_int_branches).finish()
