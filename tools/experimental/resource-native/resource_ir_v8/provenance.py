"""Finite derived records, symbolic provenance, and scoped allocation graph.

These are proof premises and pending runtime equations, never runtime Access.
"""
from __future__ import annotations

from .program_schema import fail

FORMAT = 'resource-ir-v8-resource-analysis/1'
RULES = ('exact_mono_type', 'down_support', 'same_group', 'strict_below',
         'argument_identity', 'no_once_copy', 'live_exact_anchor',
         'neutral_same_capsule', 'closed_preserve_target_access', 'principal_force_result')
KINDS = ('publish', 'application_argument', 'callback_return', 'fill', 'field_acquire', 'force_result')
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

    def obligation(self, instruction, role, kind, host_site, references, expected, scope, rules):
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

    def final_data(self, ir_sha256, declaration_sha256):
        # Immutable paths reused directly; copied sorted inventories are charged.
        self.edges = self.budget.ordered(self.edges, key=lambda row:
            (row['from_code'] is None, -1 if row['from_code'] is None else row['from_code'], row['to_code'], row['site']))
        # Rows are already instruction-local ordered except nested generalize,
        # whose enclosing instruction has no obligation. Sort for explicit closure.
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
