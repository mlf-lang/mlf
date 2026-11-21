"""Opt-in elimination of two temporary owners at a concrete lazy application.

Match only retain f1 f; retain x1 x; application r f1 x1; drop f1; drop x1,
in one ordinary top-level body, for Repeat Int -> Int and Int. Publication
copies the two slots without consuming or forcing the original owners.
There is no intervening operation or change to either original lifetime.

Graph/evaluation equivalence assumes sufficient resources. Allocation failure,
trace, fuel and guard-work positions may change. This is not source admission,
a default pipeline pass, generic ownership optimization or performance proof.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .budgets import Budget, canonical_encode
from .checker import check_resources


@dataclass(frozen=True, slots=True, eq=False)
class ApplicationCopyElision:
    canonical_json: str
    sha256: str
    original_sha256: str
    derived_sha256: str
    witness_json: str
    eliminated_applications: int

    def data(self):
        return json.loads(self.canonical_json)


def _body(program, root, name):
    return (program['entry'] if root == 'entry' else
            program['functions' if root == 'function' else 'codes'][name]['body'])


def _owner(fact):
    return (fact['kind'] == 'value' and fact['mode'] == 'own'
            and fact['view'] == 'MONO' and fact['ticket'] is False
            and fact['anchor'] is None and fact['scheme'] is None)


def _same_value(left, right):
    return all(left[k] == right[k] for k in (
        'node', 'group', 'type', 'ready', 'view', 'scheme', 'projection',
        'provenance', 'ticket', 'anchor'))


def _eligible(window, types):
    a, b, app, da, db = window
    if [r['op'] for r in window] != ['retain', 'retain', 'application', 'drop', 'drop']:
        return False
    if any(r['type_scope'] is not None for r in window):
        return False
    for retain, drop in ((a, da), (b, db)):
        if (len(retain['inputs']) != 1 or len(retain['outputs']) != 1
                or len(drop['inputs']) != 1 or drop['outputs']):
            return False
        source, copy, released = retain['inputs'][0], retain['outputs'][0], drop['inputs'][0]
        if (source['role'] != ['value'] or copy['role'] != ['out']
                or released['role'] != ['value']
                or not all(_owner(x) for x in (source, copy, released))
                or not _same_value(source, copy) or not _same_value(copy, released)
                or released['capability'] != copy['capability']):
            return False
    f, x = a['inputs'][0], b['inputs'][0]
    fc, xc = a['outputs'][0], b['outputs'][0]
    if len({v['capability'] for v in (f, x, fc, xc)}) != 4:
        return False
    arrow, scalar = types[f['type']], types[x['type']]
    # Types come from the fresh structural checker, never spelling such as T0.
    if not (scalar['tag'] == 'closed' and scalar['atom'] == '#i64'
            and arrow['tag'] == 'arrow' and arrow['protocol'] == 'repeat'
            and arrow['argument'] == scalar['id'] == arrow['result']
            and arrow['result_identity'] == 'unknown'):
        return False
    if (len(app['inputs']) != 3 or len(app['outputs']) != 1
            or app['inputs'][0]['role'] != ['in']
            or app['inputs'][0]['kind'] != 'authority'
            or app['inputs'][0]['capability'] in (fc['capability'], xc['capability'])):
        return False
    for fact, copy, role in zip(app['inputs'][1:], (fc, xc), ('function', 'argument')):
        if (fact['role'] != [role] or not _owner(fact)
                or fact['capability'] != copy['capability'] or not _same_value(fact, copy)):
            return False
    return True


def elide_application_input_copies(program):
    """Fresh-check, rewrite exact concrete windows, fresh-check; no analysis input.

    Schemes, nested/type-scoped bodies, tickets, loans, Once, borrowed
    application and all nonadjacent/reordered windows remain excluded.
    Both original owners remain live: retain does not consume them, and the
    only intervening operation publishes Repeat/Int slots without consumption.
    Existing loans anchored to an original owner are not consumed or rewritten;
    this rule does not claim that no such loan exists.
    """
    original = check_resources(program)
    raw = json.loads(original.canonical_json)
    derived = json.loads(original.derived_json)
    budget = Budget()
    rows, deleted, changes = {}, set(), []
    for row in derived['instructions']:
        budget.examine()
        p = row['path']
        if len(p['segments']) == 1:
            budget.put(rows, (p['root'], p['name'], p['segments'][0]), row)
    for path, row in rows.items():
        budget.examine()
        if row['op'] != 'retain' or path in deleted or row['type_scope'] is not None:
            continue
        root, name, index = path
        window = [rows.get((root, name, index + n)) for n in range(5)]
        budget.examine(5)
        if any(r is None for r in window) or not _eligible(window, derived['types']):
            continue
        body = _body(raw, root, name)
        first, second, app = body[index:index + 3]
        if app['in'] in (first['out'], second['out']):
            continue
        # Only these two explicit operand roles change; no name-based traversal.
        app['function'] = first['value']
        app['argument'] = second['value']
        for offset in (0, 1, 3, 4):
            budget.add(deleted, (root, name, index + offset))
        budget.record_append(changes, application=window[2]['path'],
            function_source=window[0]['inputs'][0]['capability'],
            argument_source=window[1]['inputs'][0]['capability'],
            function_copy=window[0]['outputs'][0]['capability'],
            argument_copy=window[1]['outputs'][0]['capability'])
    blocks = set()
    for root, name, _ in deleted:
        budget.add(blocks, (root, name))
    for root, name in blocks:
        body = _body(raw, root, name)
        kept = []
        for index, instruction in enumerate(body):
            budget.examine()
            if (root, name, index) not in deleted:
                budget.append(kept, instruction)
        body[:] = kept
    checked = check_resources(raw)
    witness, _ = canonical_encode({
        'format': 'resource-ir-v8-application-input-copy-elision/1',
        'rule': 'two-retains-repeat-int-application-two-copy-drops',
        'original_sha256': original.sha256, 'result_sha256': checked.sha256,
        'original_derived_sha256': original.derived_sha256,
        'result_derived_sha256': checked.derived_sha256,
        'applications': changes, 'removed_instructions': 4 * len(changes),
        'rewritten_operands': 2 * len(changes), 'source_admitted': False,
        'native_executed': False, 'creation_units': budget.creation_units,
        'work_units': budget.order_edge_examinations})
    return ApplicationCopyElision(checked.canonical_json, checked.sha256,
        original.sha256, checked.derived_sha256, witness, len(changes))
