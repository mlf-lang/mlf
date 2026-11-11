"""Strict GHC 9.14.1 -pj reader. No execution or inference of ordinary cost.

Schema source: https://raw.githubusercontent.com/ghc/ghc/ghc-9.14.1-release/rts/ProfilerReportJson.c
Writer lines 207-270: node id is a COST-CENTRE reference, not a stack ID;
alloc and total_alloc multiply internal words by sizeof(W_). Local installed
RTS and a real known-allocation control must still qualify the reporting unit.
"""
import json
import math
import re
from collections import defaultdict

class ProfileError(ValueError):
    pass

LABELS = frozenset('CONSTRAINT_GENERATION SOLVE PREPARED_TYPES RESOLVE_EVIDENCE ELABORATE SCHEME_TYPE CLOSED_CHECK TYPE_AGREEMENT ERASURE_AGREEMENT OPEN_ENV OPEN_INITIAL OPEN_OWNERSHIP INVENTORY CANONICAL_PLAN CANONICAL_REALIZE CANONICAL_SYNTAX CANONICAL_RESULT OPEN_NORMALIZE STAMP FREE_NAMES ENCODE CONTENT_SHA PUBLISH WITNESS_FALLBACK'.split())
CONTEXTS = frozenset(('CLOSED_CHECK', 'OPEN_INITIAL', 'OPEN_NORMALIZE'))
ROOT_KEYS = frozenset('program arguments rts_arguments end_time initial_capabilities total_time total_ticks tick_interval total_alloc cost_centres profile'.split())
CC_KEYS = frozenset(('id', 'label', 'module', 'src_loc', 'is_caf'))
NODE_KEYS = frozenset(('id', 'entries', 'alloc', 'ticks', 'children'))

def require(condition, message):
    if not condition:
        raise ProfileError(message)

def integer(value, where):
    require(type(value) is int and value >= 0, where + ': nonnegative integer required')
    return value

def keys(value, expected, where):
    require(type(value) is dict and value.keys() == expected, where + ': unsupported schema')

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result

def bucket(stack):
    for i in range(len(stack) - 1, -1, -1):
        label = stack[i]['label']
        if label in LABELS:
            if label == 'INVENTORY':
                context = next((x['label'] for x in reversed(stack[:i]) if x['label'] in CONTEXTS), 'UNRESOLVED')
                return 'INVENTORY/' + context
            return label
    if any(x['is_caf'] for x in stack):
        return 'RESIDUAL/CAF'
    if any(x['module'] == 'RTS' for x in stack[1:] or stack):
        return 'RESIDUAL/RTS'
    return 'RESIDUAL/UNKNOWN'

def parse_profile(raw, *, max_bytes=64 * 1024 * 1024, max_nodes=1000000, max_depth=512):
    """Return raw totals, self/inherited stack rows and a disjoint partition.

    JSON IDs may recur in DIFFERENT branches; cycles and shared node objects are
    rejected. Inherited values are computed, never added into the partition.
    Strict total equality applies to this -pj schema, not to RTS -s totals.
    """
    if isinstance(raw, (str, bytes)):
        require(len(raw.encode('utf8') if isinstance(raw, str) else raw) <= max_bytes, 'profile exceeds limit')
        try:
            raw = json.loads(raw, object_pairs_hook=unique_pairs,
                             parse_constant=lambda x: (_ for _ in ()).throw(ProfileError('nonfinite JSON number')))
        except (ValueError, UnicodeError, RecursionError) as e:
            raise ProfileError('invalid JSON: ' + str(e)) from e
    keys(raw, ROOT_KEYS, 'report')
    for key in ('program', 'end_time'):
        require(type(raw[key]) is str, key + ': string required')
    for key in ('arguments', 'rts_arguments'):
        require(type(raw[key]) is list and all(type(x) is str for x in raw[key]), key + ': string list required')
    for key in ('initial_capabilities', 'total_ticks', 'tick_interval', 'total_alloc'):
        integer(raw[key], key)
    require(raw['initial_capabilities'] > 0 and raw['tick_interval'] > 0, 'invalid runtime metadata')
    require(type(raw['total_time']) in (float, int) and math.isfinite(raw['total_time']) and raw['total_time'] >= 0, 'invalid total_time')
    require(type(raw['cost_centres']) is list, 'cost_centres must be a list')
    centres = {}
    for cc in raw['cost_centres']:
        keys(cc, CC_KEYS, 'cost centre')
        i = integer(cc['id'], 'cost centre id')
        require(i not in centres, 'duplicate cost-centre id')
        require(all(type(cc[k]) is str for k in ('label', 'module', 'src_loc')), 'invalid cost-centre strings')
        require(type(cc['is_caf']) is bool, 'invalid is_caf')
        centres[i] = dict(cc)
    rows, seen = [], set()
    partition = defaultdict(lambda: {'alloc': 0, 'ticks': 0, 'nodes': 0})
    # Explicit postorder avoids recursive traversal on hostile input.
    pending = [(raw['profile'], (), (), False)]
    results = {}
    while pending:
        node, path, stack, post = pending.pop()
        if post:
            row = results[path]
            row['inherited_alloc'] = row['self_alloc'] + sum(results[path + (i,)]['inherited_alloc'] for i in range(len(node['children'])))
            row['inherited_ticks'] = row['self_ticks'] + sum(results[path + (i,)]['inherited_ticks'] for i in range(len(node['children'])))
            continue
        keys(node, NODE_KEYS, 'stack node')
        require(id(node) not in seen, 'cyclic or shared stack node')
        seen.add(id(node))
        require(len(seen) <= max_nodes and len(path) <= max_depth, 'profile tree exceeds limit')
        ref = integer(node['id'], 'node id')
        require(ref in centres, 'unknown cost-centre reference')
        require(ref not in [x['id'] for x in stack], 'cyclic cost-centre path')
        for key in ('entries', 'alloc', 'ticks'):
            integer(node[key], key)
        require(type(node['children']) is list, 'children must be a list')
        child_ids = [c.get('id') for c in node['children'] if type(c) is dict]
        require(all(type(x) is int for x in child_ids), 'invalid child reference')
        require(len(set(child_ids)) == len(child_ids), 'duplicate sibling cost centre')
        stack = stack + (centres[ref],)
        part = bucket(stack)
        row = {'path': list(path), 'stack': list(stack), 'entries': node['entries'], 'self_alloc': node['alloc'], 'self_ticks': node['ticks'], 'bucket': part}
        rows.append(row)
        results[path] = row
        partition[part]['alloc'] += node['alloc']
        partition[part]['ticks'] += node['ticks']
        partition[part]['nodes'] += 1
        pending.append((node, path, stack, True))
        pending.extend((child, path + (i,), stack, False) for i, child in reversed(list(enumerate(node['children']))))
    alloc = sum(row['self_alloc'] for row in rows)
    ticks = sum(row['self_ticks'] for row in rows)
    require(alloc == raw['total_alloc'], 'self allocation total mismatch')
    require(ticks == raw['total_ticks'], 'self ticks total mismatch')
    return {'schema': 'ghc-9.14.1-pj', 'interpretation': 'profiled source-demand allocation; not ordinary exclusive CPU or savings',
            'unit': 'raw-json-allocation-unit (bytes pending local qualification)',
            'total_alloc': alloc, 'total_ticks': ticks, 'stacks': rows,
            'partition': dict(sorted(partition.items())), 'metadata': {k: raw[k] for k in ROOT_KEYS - {'profile', 'cost_centres'}}}

def qualify_units(summary, evidence, *, toolchain_sha256):
    """Validate pre-authenticated local control evidence; caller authenticates receipt files.

    Does NOT itself authenticate files, launch a control, or bless a toolchain.
    No multiplication: this writer already emits bytes.
    """
    keys(evidence, frozenset(('toolchain_sha256', 'installed_rts_definition_sha256', 'control_receipt_sha256', 'writer_alloc_unit', 'control_expected_bytes', 'control_observed_raw', 'control_passed')), 'unit evidence')
    for k in ('toolchain_sha256', 'installed_rts_definition_sha256', 'control_receipt_sha256'):
        require(type(evidence[k]) is str and re.fullmatch('[0-9a-f]{64}', evidence[k]), 'invalid evidence digest')
    require(evidence['toolchain_sha256'] == toolchain_sha256, 'toolchain mismatch')
    require(evidence['writer_alloc_unit'] == 'bytes' and evidence['control_passed'] is True, 'unit control not passed')
    expected = integer(evidence['control_expected_bytes'], 'control expected bytes')
    observed = integer(evidence['control_observed_raw'], 'control observed raw')
    require(expected > 0 and expected == observed, 'unit control mismatch')
    require(summary.get('schema') == 'ghc-9.14.1-pj', 'unknown summary schema')
    return dict(summary, unit='bytes', unit_evidence=dict(evidence))
