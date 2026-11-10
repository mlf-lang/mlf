"""Opt-in owned-handle forwarding on freshly checked explicit IR8.

Only adjacent ``retain y x; drop x`` is reduced. The surviving owner keeps x's
name; later operands of y's exact capability are renamed, never arbitrary text.
There is no operation between the retain and drop that could observe the extra
owner, and the drop cannot close its group while the retained owner is live.
Both sides of the rewrite have the same node, type, support and readiness.

The fresh output is independently resource-checked. That check is a safety gate,
not by itself a semantic equivalence proof. Source witnesses, metadata, packets,
native code and performance qualifications do not transfer across this pass.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .budgets import Budget, canonical_encode
from .checker import check_resources
from .program_schema import fail


@dataclass(frozen=True, slots=True, eq=False)
class Forwarding:
    canonical_json: str
    sha256: str
    original_sha256: str
    derived_sha256: str
    witness_json: str
    eliminated_pairs: int

    def data(self):
        """Return a new mutable copy, never a reusable admission token."""
        return json.loads(self.canonical_json)


def _path(row):
    path = row['path']
    return path['root'], path['name'], tuple(path['segments'])


def _body(program, root, name):
    if root == 'entry':
        return program['entry']
    return program['functions' if root == 'function' else 'codes'][name]['body']


def _instruction(program, path):
    root, name, segments = path
    current = _body(program, root, name)
    for part in segments:
        current = current[part]
    return current


def _operand(instruction, role):
    current = instruction
    for part in role[:-1]:
        current = current[part]
    return current, role[-1]


def _owner(fact):
    return (fact['kind'] == 'value' and fact['mode'] == 'own'
            and fact['view'] == 'MONO' and fact['ticket'] is False
            and fact['anchor'] is None)


def _same_value(left, right):
    return all(left[key] == right[key] for key in (
        'node', 'group', 'type', 'ready', 'view', 'scheme', 'projection',
        'provenance', 'ticket', 'anchor'))


def _resolve(capability, aliases, budget):
    """Resolve and compress an acyclic earlier-owner chain."""
    pending = []
    current = capability
    while current in aliases:
        budget.examine()
        target, name = aliases[current]
        if target == current:
            fail('forwarding', 'resource', 'FORWARDING_CYCLE', 'invalid owner chain')
        budget.append(pending, current)
        current = target
        if len(pending) > len(aliases):
            fail('forwarding', 'resource', 'FORWARDING_CYCLE', 'invalid owner chain')
    if not pending:
        return None
    result = (current, name)
    for item in pending:
        aliases[item] = result
    return result


def forward_owned(program):
    """Check raw input, eliminate exact adjacent owner pairs, then check again.

    No user-supplied analysis is accepted. Generic bodies and Scheme/loan/ticket
    operands are deliberately excluded. Root-scope import operands can be
    renamed, but child import binders and bodies retain their own capabilities.
    Work uses the existing monotone analysis limits; exhaustion refuses.
    """
    original = check_resources(program)
    raw = json.loads(original.canonical_json)
    derived = json.loads(original.derived_json)
    budget = Budget()
    rows = {}
    for row in derived['instructions']:
        budget.examine()
        budget.put(rows, _path(row), row)

    aliases, names, deleted, pairs = {}, {}, set(), []
    for path, row in rows.items():
        budget.examine()
        root, name, segments = path
        # Only ordinary concrete, linear instruction lists. No reduction in a
        # nested introduction or a type-scoped callback in this first slice.
        if (row['op'] != 'retain' or row['type_scope'] is not None
                or len(segments) != 1):
            continue
        next_path = (root, name, (segments[0] + 1,))
        following = rows.get(next_path)
        if following is None or following['op'] != 'drop':
            continue
        if (len(row['inputs']) != 1 or len(row['outputs']) != 1
                or len(following['inputs']) != 1):
            continue
        source, target, released = row['inputs'][0], row['outputs'][0], following['inputs'][0]
        if (source['role'] != ['value'] or target['role'] != ['out']
                or released['role'] != ['value'] or not _owner(source)
                or not _owner(target) or not _same_value(source, target)
                or released['capability'] != source['capability']):
            continue
        retain = _instruction(raw, path)
        drop = _instruction(raw, next_path)
        if drop['value'] != retain['value']:
            fail('forwarding', 'resource', 'FORWARDING_OPERAND', 'fresh analysis operand mismatch')
        budget.put(aliases, target['capability'], (source['capability'], retain['value']))
        budget.put(names, target['capability'], retain['out'])
        budget.add(deleted, path)
        budget.add(deleted, next_path)
        budget.record_append(pairs, retain=row['path'], drop=following['path'],
            source_name=retain['value'], target_name=retain['out'], node=source['node'],
            source_capability=source['capability'], target_capability=target['capability'])

    rewritten = 0
    for path, row in rows.items():
        instruction = _instruction(raw, path)
        for fact in row['inputs']:
            budget.examine()
            replacement = _resolve(fact['capability'], aliases, budget)
            if replacement is None:
                continue
            parent, key = _operand(instruction, fact['role'])
            if parent[key] != names[fact['capability']]:
                fail('forwarding', 'resource', 'FORWARDING_OPERAND', 'fresh capability/name mismatch')
            parent[key] = replacement[1]
            rewritten += 1

    blocks = set()
    for root, name, _ in deleted:
        budget.add(blocks, (root, name))
    for root, name in blocks:
        body = _body(raw, root, name)
        kept = []
        for index, instruction in enumerate(body):
            budget.examine()
            if (root, name, (index,)) not in deleted:
                budget.append(kept, instruction)
        body[:] = kept

    # Always recheck, including a no-op. New identities and instruction addresses
    # require new derived data; original metadata must never accompany this IR.
    checked = check_resources(raw)
    witness, _ = canonical_encode({
        'format': 'resource-ir-v8-owned-forwarding/1',
        'rule': 'adjacent-retain-drop-exact-owned-mono-capability',
        'original_sha256': original.sha256, 'result_sha256': checked.sha256,
        'original_derived_sha256': original.derived_sha256,
        'result_derived_sha256': checked.derived_sha256,
        'eliminated_pairs': pairs, 'rewritten_operands': rewritten,
        'source_admitted': False, 'native_executed': False,
        'creation_units': budget.creation_units,
        'work_units': budget.order_edge_examinations})
    return Forwarding(checked.canonical_json, checked.sha256, original.sha256,
                      checked.derived_sha256, witness, len(pairs))
