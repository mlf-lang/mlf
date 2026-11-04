"""Finite derived records, symbolic provenance, and scoped allocation graph.

These are proof premises and pending runtime equations, never runtime Access.
"""
from __future__ import annotations

from .program_schema import fail

FORMAT = 'resource-ir-v8-resource-analysis/1'
CLOSED_ENTRY_POLICY = 'instance-only-scoped-scalars/1'
CAPTURE_ORIGIN_CASES = ('same-neutral-capsule/project', 'concrete-E0-intrinsic-scalar/identity')
RULES = ('exact_mono_type', 'down_support', 'same_group', 'strict_below',
         'argument_identity', 'no_once_copy', 'live_exact_anchor',
         'neutral_same_capsule', 'closed_preserve_target_access', 'principal_force_result')
KINDS = ('publish', 'application_argument', 'callback_return', 'fill', 'field_acquire', 'force_result', 'generic_import')
COUNTS = ('functions', 'thunks', 'instructions', 'checked_factory_arms', 'allocations',
          'introductions', 'instantiate_occurrences', 'declared_uses', 'types', 'environments')
PENDING_GATES = ('runtime-table-closure', 'physical-representation-and-Access',
                 'model-and-native-ABI', 'source-proof-and-lowering', 'single-code-emission',
                 'allocator-and-terminal-requalification', 'GC-replacement', 'performance')


class Analysis:
    __slots__ = ('budget', 'codes', 'sites', 'intros', 'uses', 'instructions',
                 'provenance', 'returns', 'edges', 'obligations', 'types', 'counts')

    def __init__(self, budget, declarations):
        self.budget = budget
        budget.charge()
        self.codes, self.sites, self.intros, self.uses = [], [], [], []
        self.instructions, self.provenance, self.returns = [], [], []
        self.edges, self.obligations, self.types = [], [], []
        budget.charge()  # derived counts record
        self.counts = {}
        for key in COUNTS:
            budget.put(self.counts, key, 0)
        for index, row in enumerate(declarations.rows):
            fields = budget.record_append(self.types, id=index, tag=row[0], atom=None, scheme=None, index=None,
                                argument=None, result=None, protocol=None, result_identity=None)
            if row[0] == 'closed':
                fields['atom'] = row[1]
            elif row[0] == 'rigid':
                fields['scheme'], fields['index'] = row[1], row[2]
            else:
                fields['argument'], fields['result'], fields['protocol'], fields['result_identity'] = row[1:]
        self.counts['types'], self.counts['environments'] = len(self.types), len(declarations.environments)

    def path(self, root, name, segments):
        return self.budget.row(root=root, name=name, segments=self.budget.listing(segments))

    def term(self, kind, **payload):
        self.budget.charge(3)  # value record, indexed row, inventory membership
        index = len(self.provenance)
        value = dict(payload)
        value['kind'] = kind
        self.provenance.append({'id': index, 'value': value})
        return index

    def choice(self, alternatives):
        # Charge row + nested row + membership + alternatives atomically.
        self.budget.charge(3 + len(alternatives))
        index = len(self.provenance)
        self.provenance.append({'id': index, 'value': {'kind': 'choice', 'alternatives': list(alternatives)}})
        return index

    def exact_site(self, provenance):
        if provenance is None:
            return None
        term = self.provenance[provenance]['value']
        return term['site'] if term['kind'] == 'allocated' else None

    def _fact(self, value, role, authority):
        # Caller has atomically charged the record and role members.
        fields = dict(role=list(role), capability=value.capability,
            storage=value.storage, node=value.node, group=value.group, kind=value.kind,
            mode=value.mode, anchor=value.anchor, ticket=value.ticket, ready=value.ready,
            view=value.view, type=value.type, scheme=value.scheme, projection=value.projection,
            provenance=value.provenance, authority_source=value.authority_source)
        if authority:
            fields['kind'] = 'authority'
            for key in ('node', 'ticket', 'ready', 'view', 'type', 'scheme', 'projection', 'provenance'):
                fields[key] = None
            if value.kind == 'authority':
                for key in ('capability', 'storage', 'mode', 'anchor'):
                    fields[key] = None
        return fields

    def fact(self, value, role, *, authority=False):
        self.budget.charge(1 + len(role))
        return self._fact(value, role, authority)

    def operand(self, instruction, value, role, *, side='inputs', authority=False):
        self.budget.charge(2 + len(role))  # fact, inventory member, role members
        target = self.instructions[instruction][side]
        index = len(target)
        target.append(self._fact(value, role, authority))
        return index

    def obligation(self, instruction, role, kind, host_site, references, expected, scope, rules, *, origin_cases=None):
        rule_count = sum(rule in rules for rule in RULES)
        if not rule_count:
            raise ValueError('empty obligation rules')
        self.budget.charge(2 + len(role) + 2 * len(references) + rule_count)
        operands = []
        for side, index in references:
            operands.append(dict(instruction=instruction, side=side, index=index))
        rule_rows = []
        for rule in RULES:
            if rule in rules:
                rule_rows.append(rule)
        self.obligations.append(dict(path=self.instructions[instruction]['path'],
            role=list(role), kind=kind, host_site=host_site, operands=operands,
            expected_type=expected, scope=scope, rules=rule_rows))
        if origin_cases is not None:
            self.budget.put(self.obligations[-1], 'origin_cases', self.budget.listing(origin_cases))

    def check_graph(self, program):
        # Scope equality is checked while adding each allocation. Per-root DFS
        # traverses only same-S code edges and proves acyclicity without recursion.
        for site in self.sites:
            if site['code'] is not None and self.codes[site['code']]['type_scope'] != site['type_scope']:
                from .program_schema import diagnostic_path
                path = diagnostic_path(site['path'])
                if site['arm'] is not None:
                    root = site['path']
                    body = program['entry'] if root['root'] == 'entry' else program['functions' if root['root'] == 'function' else 'codes'][root['name']]['body']
                    current = body
                    for segment in root['segments']:
                        current = current[segment]
                    variant = program['families'][current['family']]['variants'][site['arm']]
                    path += '.arms.' + variant
                fail(path, 'graph', 'ALLOCATION_SCOPE', 'allocation must target the exact lexical code scope')
        adjacency = {}
        for edge in self.edges:
            source = edge['from_code']
            if source is None or self.codes[source]['type_scope'] is None:
                continue
            if source not in adjacency:
                self.budget.put(adjacency, source, [])
            self.budget.append(adjacency[source], edge['to_code'])
        color = {}
        for code in self.codes:
            start = code['id']
            if code['type_scope'] is None or color.get(start) == 2:
                continue
            stack = []
            self.budget.append(stack, (start, False))
            while stack:
                current, leaving = stack.pop()
                if leaving:
                    self.budget.put(color, current, 2)
                    continue
                if color.get(current) == 1:
                    target = self.codes[current]
                    prefix = 'functions.' if target['kind'] == 'function' else 'codes.'
                    fail(prefix + target['name'], 'graph', 'ALLOCATION_CYCLE', 'same-scheme allocation graph must be acyclic')
                if color.get(current) == 2:
                    continue
                self.budget.put(color, current, 1)
                self.budget.append(stack, (current, True))
                for target in reversed(adjacency.get(current, ())):
                    self.budget.append(stack, (target, False))

    def closed_entry_proofs(self, program, effects, instruction_meta):
        """Prove the only neutral entry is a directly sealed closure.

        Conditional on new scoped effects. Complete same-S Code declarations,
        including unused ones, must be in the root's finite allocation closure.
        This proves Instance-only invocation, not removal of neutral type rows.
        """
        from .program_schema import diagnostic_path
        b = self.budget
        for scheme in b.ordered(effects):
            b.charge(); matches = []
            for item in self.intros:
                b.examine()
                if item['scheme'] == scheme: b.append(matches, item)
            if len(matches) != 1:
                fail('schemes.' + scheme, 'coverage', 'CLOSED_ENTRY', 'effectful scope requires one introduction')
            intro = matches[0]
            body = program['entry'] if intro['generalize_path']['root'] == 'entry' else program['functions' if intro['generalize_path']['root'] == 'function' else 'codes'][intro['generalize_path']['name']]['body']
            actual = body
            for part in intro['generalize_path']['segments']:
                b.examine(); actual = actual[part]
            p = diagnostic_path(intro['generalize_path'])
            b.charge(3); indices, roots, aliases = [], [], set()
            for index, meta in enumerate(instruction_meta):
                b.examine()
                if meta['intro'] == intro['id']:
                    b.append(indices, index)
                    row = self.instructions[index]
                    if row['op'] not in ('closure', 'retain', 'drop', 'borrow', 'end_borrow', 'seal'):
                        fail(diagnostic_path(row['path']), 'coverage', 'CLOSED_ENTRY', 'effectful neutral introduction permits only one closure and owner lifetime operations')
                    if row['op'] == 'closure': b.append(roots, index)
            if len(roots) != 1:
                fail(p, 'coverage', 'CLOSED_ENTRY', 'effectful scope requires exactly one neutral closure allocation')
            root = self.instructions[roots[0]]
            site = root['sites'][0]
            if intro['result_sites'] != [site] or self.sites[site]['category'] != 'CLOSURE':
                fail(p, 'coverage', 'CLOSED_ENTRY', 'sealed value must be the unique direct closure')
            root_code = self.sites[site]['code']
            # Actual initial alias provenance comes only from checked intro imports.
            parent = None
            for record in self.instructions:
                b.examine(1 + len(record['path']['segments']))
                if record['path'] == intro['generalize_path']:
                    parent = record; break
            if parent is None: fail(p, 'coverage', 'CLOSED_ENTRY', 'missing actual introduction record')
            for fact in parent['outputs'][1:]:
                b.examine(); b.add(aliases, fact['provenance'])
            for fact in root['inputs'][1:]:
                b.examine()
                ty = self.types[fact['type']]
                if (fact['view'] != 'MONO' or fact['projection'] is not None or fact['provenance'] not in aliases
                        or ty['tag'] != 'closed' or ty['atom'] not in ('#i64', '#bool')):
                    fail(p, 'coverage', 'CLOSED_ENTRY', 'neutral root captures must preserve checked scalar import provenance')
            b.charge(3); scoped, seen, pending = [], set(), [root_code]
            for code in self.codes:
                b.examine()
                if code['type_scope'] == scheme: b.append(scoped, code['id'])
            while pending:
                b.examine(); code = pending.pop()
                if code in seen: continue
                b.add(seen, code)
                if self.codes[code]['type_scope'] != scheme:
                    fail(p, 'coverage', 'CLOSED_ENTRY', 'effectful allocation closure crosses Scheme scope')
                for edge in self.edges:
                    b.examine()
                    if edge['from_code'] == code: b.append(pending, edge['to_code'])
            b.examine(len(scoped))
            if len(seen) != len(scoped) or any(code not in seen for code in scoped):
                fail(p, 'coverage', 'CLOSED_ENTRY', 'all same-S Code, including dead declarations, must be reached from the sealed root')
            for index, row in enumerate(self.instructions):
                b.examine()
                if row['type_scope'] != scheme or not row['sites']: continue
                meta = instruction_meta[index]
                if meta['intro'] == intro['id']:
                    if index != roots[0]: fail(p, 'coverage', 'CLOSED_ENTRY', 'additional neutral allocation')
                elif meta['intro'] is not None or meta['container'] not in seen:
                    fail(p, 'coverage', 'CLOSED_ENTRY', 'unproved same-S allocation origin')
            b.put(intro, 'closed_entry', b.row(policy=CLOSED_ENTRY_POLICY, root_site=site,
                root_code=root_code, codes=scoped, effects=b.listing(effects[scheme])))

    def final_data(self, ir_sha256, declaration_sha256):
        # Immutable paths reused directly; copied sorted inventories are charged.
        self.edges = self.budget.ordered(self.edges, key=lambda row:
            (row['from_code'] is None, -1 if row['from_code'] is None else row['from_code'], row['to_code'], row['site']))
        # Rows are already instruction-local ordered except nested generalize,
        # including conditional initial-import acquisitions. Sort for explicit closure.
        instruction_lookup = {}
        for index, row in enumerate(self.instructions):
            self.budget.put(instruction_lookup, id(row['path']), index)
        kind_rank = {kind: index for index, kind in enumerate(KINDS)}  # fixed table
        self.obligations = self.budget.ordered(self.obligations, key=lambda row:
            (instruction_lookup[id(row['path'])], kind_rank[row['kind']]))
        return self.budget.row(format=FORMAT, ir_sha256=ir_sha256,
            declaration_sha256=declaration_sha256, types=self.types, code_typing=self.codes,
            sites=self.sites, introductions=self.intros, uses=self.uses,
            instructions=self.instructions, provenance=self.provenance,
            return_summaries=self.returns, allocation_edges=self.edges,
            obligations=self.obligations, counts=self.counts)
