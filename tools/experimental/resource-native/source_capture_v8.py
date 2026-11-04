"""Read-only verifier for the deliberately incomplete shared-source capture.

This is test/integration evidence, NOT export/3 or native/source admission.
Call only on a completed capture. Source/build/producer authentication and the
fact that an invocation is terminal are external caller obligations. Explicit
reviewed fixture hashes are required; paths or producer booleans cannot replace
them. No producer, compiler, original evaluator or native program is executed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import module_custody as custody
import module_projection as projection
import module_shared_transport as shared
import module_transport
import transport

TOP = {'format', 'status', 'producer', 'module_custody', 'original', 'projection',
       'normalization', 'annotated', 'erased', 'checked_type', 'limitations'}
NORMAL = {'policy', 'input_checked_type', 'input_annotated', 'input_erased',
          'raw_normalized', 'steps', 'original_rechecked', 'normalized_rechecked',
          'root_type_alpha_equal', 'erasure_equal', 'declarations_equal'}
LIMITATIONS = [
    'Not mlf-checked-module-export/3 and not source/native admission',
    'No complete polymorphism/representation/runtime-inventory join',
    'No source-to-IR carrier/allocation/term correspondence claim',
    'No source evaluation, specialization, inlining or body cloning',
]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def equal(left, right, label):
    require(projection.exact_equal(left, right), label + ' differs')


def _read(path, limit, expected=None):
    path = Path(os.path.abspath(path))
    require(path.resolve(strict=True) == path, 'input traverses a symlink: ' + str(path))
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'input is not bounded regular data')
    with path.open('rb') as stream:
        blob = stream.read(limit + 1)
        descriptor = os.fstat(stream.fileno())
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(identity(before) == identity(descriptor) == identity(after), 'input changed while reading')
    require(len(blob) == after.st_size <= limit, 'input length exceeds bound')
    digest = hashlib.sha256(blob).hexdigest()
    if expected is not None:
        require(type(expected) is str and len(expected) == 64 and all(x in '0123456789abcdef' for x in expected),
                'expected SHA256 must be an exact lowercase digest')
        require(digest == expected, 'reviewed input SHA256 mismatch: ' + str(path))
    return blob, {'path': str(path), 'bytes': len(blob), 'sha256': digest, 'mode': after.st_mode}


def _children(node):
    tag = node['tag']
    if tag in ('lambda', 'type_lambda', 'with_data'):
        return [(('body',), node['body'])]
    if tag == 'type_application':
        return [(('value',), node['value'])]
    if tag == 'application':
        return [(('function',), node['function']), (('argument',), node['argument'])]
    if tag == 'let':
        return [(('value',), node['value']), (('body',), node['body'])]
    if tag == 'letrec':
        return [(('bindings', str(i), 'value'), b['value']) for i, b in enumerate(node['bindings'])] + [(('body',), node['body'])]
    if tag == 'case':
        return [(('scrutinee',), node['scrutinee'])] + [(('alternatives', str(i), 'body'), a['body']) for i, a in enumerate(node['alternatives'])]
    return []


def _walk(root, path=()):
    work = [(path, root)]
    while work:
        current, node = work.pop()
        yield current, node
        work.extend((current + suffix, child) for suffix, child in reversed(_children(node)))


def _get(root, path):
    for key in path:
        root = root[int(key)] if type(root) is list else root[key]
    return root


def _projection_origins(original, projected, steps):
    """Occurrence map derived only after exact ordinary projection replay."""
    origins = {}
    old, new, old_path, new_path = original, projected, (), ()
    if old['tag'] == 'with_data':
        require(new['tag'] == 'with_data', 'projection dropped declaration wrapper')
        equal(old['declarations'], new['declarations'], 'projection declarations')
        origins[()] = ()
        old, new, old_path, new_path = old['body'], new['body'], ('body',), ('body',)
    for step in steps:
        require(old['tag'] == step['kind'], 'projection spine kind mismatch')
        if step['keep']:
            require(new['tag'] == old['tag'], 'retained spine kind mismatch')
            origins[new_path] = old_path
            for suffix, child in _children(old):
                if suffix == ('body',):
                    continue
                equal(child, _get(new, suffix), 'retained RHS exact syntax')
                for relative, _ in _walk(child):
                    origins[new_path + suffix + relative] = old_path + suffix + relative
            new, new_path = new['body'], new_path + ('body',)
        old, old_path = old['body'], old_path + ('body',)
    equal(old, new, 'projection final tail')
    for relative, _ in _walk(old):
        origins[new_path + relative] = old_path + relative
    return origins


def _erased_paths(root):
    answer = {}
    work = [((), (), root)]
    while work:
        path, erased, node = work.pop()
        if node['tag'] in ('type_lambda', 'type_application', 'with_data'):
            suffix, child = _children(node)[0]
            work.append((path + suffix, erased, child))
        else:
            answer[path] = erased
            work.extend((path + suffix, erased + suffix, child) for suffix, child in reversed(_children(node)))
    return answer


def _joins(original, projected, steps, binding_rows, selected_ids=None):
    origins = _projection_origins(original, projected, steps)
    erased_paths = _erased_paths(original)
    by_name = {}
    for row_id, row in enumerate(binding_rows):
        for member_id, member in enumerate(row['bindings']):
            ident = member['name']['id']
            require(ident not in by_name, 'duplicate original binder identity')
            by_name[ident] = (row_id, member_id, row, member)
    result = []
    for path, node in _walk(projected):
        if node['tag'] != 'let':
            continue
        if selected_ids is None:
            if node['value']['tag'] != 'type_lambda':
                continue
        elif node['name']['id'] not in selected_ids:
            continue
        original_path = origins[path]
        actual = _get(original, original_path)
        require(actual['tag'] == 'let', 'retained generalized binder is not the original let')
        equal(actual['name'], node['name'], 'retained exact binder identity')
        ident = node['name']['id']
        require(ident in by_name, 'retained binder absent from authenticated origins')
        row_id, member_id, row, member = by_name[ident]
        equal(member['name'], node['name'], 'actual origin member identity')
        require(row['kind'] == 'let', 'origin binding kind differs')
        equal(row['path'], list(erased_paths[original_path]), 'original erased binding path')
        result.append({'binding': node['name'], 'projected_path': list(path),
                       'original_path': list(original_path), 'original_erased_path': row['path'],
                       'origin': {'row': row_id, 'member': member_id},
                       'association': member['association'],
                       'resolver_allocation': member['resolver_allocation']})
    return result


def verify_capture(capture_path, *, fixture_root, entry, expected_source_hashes,
                   expected_capture_sha256=None):
    """Return diagnostic custody/normalization facts, preserving fragment rejection.

    A caller must supply reviewed hashes for the exact root and every imported
    guest file. Rejected fragment output does not become lowering input. The
    returned report contains no executable/native credential.
    """
    root = Path(os.path.abspath(fixture_root))
    require(root.resolve(strict=True) == root and root.is_dir(), 'fixture root is not canonical')
    require(type(expected_source_hashes) is dict and 1 <= len(expected_source_hashes) <= 32,
            'explicit bounded reviewed fixture hashes required')
    require(entry in expected_source_hashes, 'reviewed root entry missing')
    fixtures, pins = {}, {}
    total = 0
    for relative, digest in expected_source_hashes.items():
        require(type(relative) is str and relative and not relative.startswith('/') and '\\' not in relative
                and all(part not in ('', '.', '..') for part in relative.split('/')), 'unsafe fixture name')
        blob, pin = _read(root / relative, 1 << 20, digest)
        total += len(blob)
        require(total <= 8 << 20, 'fixture byte bound')
        fixtures[relative] = blob.decode('utf-8')
        pins[relative] = pin
    blob, capture_pin = _read(capture_path, 32 << 20, expected_capture_sha256)
    try:
        value = json.loads(blob.decode('utf-8'), object_pairs_hook=transport.strict_pairs,
                           parse_float=lambda _: (_ for _ in ()).throw(ValueError('nonintegral number')),
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite number')))
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('capture JSON rejected: ' + str(exc)) from exc
    module_transport.envelope_budget(value)
    transport.exact(value, TOP, 'diagnostic capture')
    equal(value['format'], 'mlf-shared-source-capture/1', 'capture format')
    equal(value['status'], 'diagnostic-not-runtime-admission', 'capture status')
    equal(value['producer'], {'kind': 'standalone-haskell-diagnostic',
                             'ordinary_api': 'MLF.ResourceModules.compileCaptured'}, 'producer descriptor')
    equal(value['limitations'], LIMITATIONS, 'diagnostic limitations')
    original, projected, normal = value['original'], value['projection'], value['normalization']
    transport.exact(projected, module_transport.PROJECTION_KEYS, 'capture projection')
    transport.exact(normal, NORMAL, 'capture normalization')
    equal(projected['policy'], 'outer-lazy-spine/1', 'projection policy')
    require(normal['policy'] in (shared.POLICY, shared.NOMINAL_BETA_POLICY),
            'unknown normalization policy')
    # A supported label grants nothing. Successful independent replay below
    # must derive the exact dialect, tree and complete ordered certificate.
    for record, guards in [(projected, ('original_rechecked', 'projected_rechecked', 'root_type_alpha_equal',
                                       'declarations_equal', 'erased_projection_equal')),
                           (normal, ('original_rechecked', 'normalized_rechecked', 'root_type_alpha_equal',
                                     'erasure_equal', 'declarations_equal'))]:
        require(all(record[k] is True for k in guards), 'producer check guard is not true')
    source = custody.validate_custody(value['module_custody'], original)
    loaded = []
    for row in source['loaded_sources']:
        path = row['path']
        relative = entry if row['is_root'] else (path[2:] if path.startswith('./') else path)
        require((path == '<stdin>') == row['is_root'], 'loaded root marker/path mismatch')
        require(relative in fixtures, 'loaded source outside reviewed fixture package')
        equal(row['text'], fixtures[relative], 'loaded source text at ' + path)
        loaded.append({'source_path': path, 'fixture': relative, 'sha256': pins[relative]['sha256'],
                       'module_identity': row['module_identity'], 'is_root': row['is_root']})
    require(len(loaded) == len(fixtures) and {r['fixture'] for r in loaded} == set(fixtures),
            'loaded closure differs from reviewed source fixture set')
    replay = projection.replay_projection(original['annotated'], original['erased'],
        projected['projected_annotated'], projected['projected_erased'], projected['steps'])
    equal(projected['original_checked_type'], original['checked_type'], 'original root custody')
    equal(normal['input_checked_type'], projected['projected_checked_type'], 'normalization input type custody')
    equal(normal['input_annotated'], projected['projected_annotated'], 'normalization input syntax')
    equal(normal['input_erased'], projected['projected_erased'], 'normalization input erasure')
    equal(normal['raw_normalized'], value['annotated'], 'normalized raw output')
    root_types = [original['checked_type'], projected['projected_checked_type'], value['checked_type']]
    for root_type in root_types:
        shared.replay_type_computation({'tag': 'refl'}, root_type)
    require(all(transport.alpha_type_equal(root_types[0], typ) for typ in root_types[1:]),
            'producer root-type alpha equality differs')
    projection.validate_raw_term(value['annotated'], require_closed=True)
    projection.validate_raw_term(value['erased'], erased=True, require_closed=True)
    equal(projection.erase_total(value['annotated']), value['erased'], 'normalized erasure')
    equal(value['erased'], projected['projected_erased'], 'ordinary graph preserved')
    before_declarations = [(list(p), n['declarations']) for p, n in _walk(projected['projected_annotated']) if n['tag'] == 'with_data']
    after_declarations = [(list(p), n['declarations']) for p, n in _walk(value['annotated']) if n['tag'] == 'with_data']
    # First admitted fragment permits only one root wrapper. General diagnostic
    # captures may move a wrapper's path under type-only reduction, so compare
    # declaration preorder contents, not unchanged raw wrapper paths.
    equal([x[1] for x in before_declarations], [x[1] for x in after_declarations], 'complete declarations')
    joins = _joins(original['annotated'], projected['projected_annotated'], projected['steps'], source['bindings'])
    report = {'status': 'diagnostic-custody-pass-fragment-pending', 'source_admitted': False,
              'native_admitted': False, 'capture': capture_pin, 'fixtures': pins, 'loaded_sources': loaded,
              'custody': {k: source[k] for k in ('guest_module_count', 'source_binding_count', 'resolved_outer_binding_count')},
              'projection': replay, 'retained_prefix_binding_joins': joins,
              'producer_normalization_step_count': len(normal['steps']),
              'build_source_authentication': 'external caller obligation, not established by JSON booleans'}
    try:
        result = shared.derive_shared_fragment(projected['projected_annotated'])
    except shared.SharedTransportError as exc:
        report.update(status='diagnostic-custody-pass-fragment-rejected', fragment_admitted=False,
                      fragment_error={'code': exc.code, 'path': exc.path, 'message': str(exc)},
                      normalization_replay='not completed; retained fragment rejected')
    else:
        for key in ('policy', 'input_checked_type', 'input_annotated', 'input_erased', 'raw_normalized', 'steps'):
            equal(result[key], normal[key], 'independent normalization.' + key)
        equal(result['checked_type'], value['checked_type'], 'independent normalized root type')
        require(transport.alpha_type_equal(original['checked_type'], result['checked_type']), 'original/root alpha equality')
        definitions = result['polymorphism']['definitions']
        joins = _joins(original['annotated'], projected['projected_annotated'], projected['steps'],
                       source['bindings'], {d['binding']['id'] for d in definitions})
        report['retained_prefix_binding_joins'] = joins
        projected_paths = {tuple(row['normalized']['path']): row['projected']['path']
                           for row in result['term_correspondence']}
        by_binding = {x['binding']['id']: x for x in joins}
        require(len(by_binding) == len(joins), 'duplicate retained prefix joins')
        for definition in result['polymorphism']['definitions']:
            require(definition['binding']['id'] in by_binding, 'admitted definition has no custody join')
            join = by_binding[definition['binding']['id']]
            equal(definition['binding'], join['binding'], 'admitted definition identity')
            equal(projected_paths[tuple(definition['binding_source']['path'])], join['projected_path'],
                  'normalized/projected/original definition path')
        report.update(status='diagnostic-capture-replay-pass-not-source-admission', fragment_admitted=True,
                      normalization_replay='all exact independent fields match',
                      fragment={'definitions': result['polymorphism']['definitions'],
                                'uses': result['polymorphism']['uses'],
                                'type_application_count': len(result['polymorphism']['type_applications']),
                                'ordinary_correspondence_count': len(result['term_correspondence'])})
    # Cooperative same-read recheck, not a hostile-filesystem confinement claim.
    for relative, pin in pins.items():
        _read(root / relative, 1 << 20, pin['sha256'])
    _read(capture_path, 32 << 20, capture_pin['sha256'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture')
    parser.add_argument('--inputs', required=True)
    parser.add_argument('--entry', required=True)
    parser.add_argument('--root-sha256', required=True)
    parser.add_argument('--shared-sha256', required=True)
    parser.add_argument('--capture-sha256')
    args = parser.parse_args()
    result = verify_capture(args.capture, fixture_root=args.inputs, entry=args.entry,
        expected_source_hashes={args.entry: args.root_sha256, 'SharedPoly.emlf': args.shared_sha256},
        expected_capture_sha256=args.capture_sha256)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['fragment_admitted'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
