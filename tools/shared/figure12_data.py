#!/usr/bin/env python3
"""Load the independent Figure 12 reference corpus for the direct GHC checks.

The data was extracted once from the pre-migration suite at 720dd649, and
compared with the reviewed data at 171717ad. It is an oracle for the current
compiler, not a transcription of the current native suite or its helpers.
The native Figure12 target continues to execute its own maintained test code.
Per-run receipts bind this reference file and the actual producer objects.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = Path('tests/golden/figure12-reference.json')
CASE_IDS = (
    'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9',
    'A10.1', 'A10.2', 'A10.3', 'A11', 'A12.1', 'A12.2', 'A12.3',
    'A13.1', 'A13.2', 'B1.1', 'B1.2', 'B1.3', 'B1.4', 'B2', 'B3',
    'B4', 'B5', 'B6', 'B7.1', 'B7.2', 'C1a', 'C1b', 'C1c', 'C2',
    'E1a', 'E1b', 'E2a', 'E2b', 'E3a', 'E3b', 'E4a', 'E4b', 'E5a', 'E5b',
)
TYPE_IDS = ('A1-principal', 'A2-principal', 'A4-result', 'A4-signature')


class FixtureError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise FixtureError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate reference field: ' + key)
        result[key] = value
    return result


def validate_signatures(value):
    require(isinstance(value, list) and all(
        isinstance(pair, list) and len(pair) == 2 and
        all(isinstance(item, str) and item for item in pair) for pair in value),
        'invalid signature pairs')
    names = [pair[0] for pair in value]
    require(len(names) == len(set(names)), 'duplicate signature name')


def validate_var(node):
    require(isinstance(node, list) and len(node) == 2 and
            node[0] == 'XTyVar' and type(node[1]) is int,
            'invalid expected type variable')


def validate_type(node):
    require(isinstance(node, list) and bool(node), 'invalid expected XType data')
    tag = node[0]
    if tag == 'XBot' and len(node) == 1:
        return
    if tag == 'XVar' and len(node) == 2:
        validate_var(node[1])
        return
    if tag == 'XArrow' and len(node) == 3:
        validate_type(node[1])
        validate_type(node[2])
        return
    if tag == 'XForall' and len(node) == 4:
        validate_var(node[1])
        validate_type(node[2])
        validate_type(node[3])
        return
    raise FixtureError('unsupported expected XType constructor/arity')


def validate_case(case, *, repair=False):
    fields = {'id', 'expression', 'paper_acceptance', 'expected_acceptance',
              'local_signatures'} | ({'label'} if repair else set())
    require(isinstance(case, dict) and set(case) == fields, 'invalid case fields')
    for key in ('id', 'expression', *(['label'] if repair else [])):
        require(isinstance(case[key], str) and bool(case[key]), 'invalid case ' + key)
    require(type(case['paper_acceptance']) is bool and
            type(case['expected_acceptance']) is bool, 'invalid acceptance value')
    validate_signatures(case['local_signatures'])


def validate_reference(fixture):
    require(isinstance(fixture, dict) and set(fixture) == {
        'schema_version', 'origin', 'signatures', 'cases', 'type_checks', 'repairs'},
        'invalid Figure12 reference fields')
    require(type(fixture['schema_version']) is int and fixture['schema_version'] == 1,
            'unsupported Figure12 reference schema')
    origin = fixture['origin']
    require(isinstance(origin, dict) and set(origin) == {'revision', 'description', 'sources'}
            and all(isinstance(origin[key], str) and origin[key]
                    for key in ('revision', 'description'))
            and isinstance(origin['sources'], list) and bool(origin['sources'])
            and all(isinstance(path, str) and path for path in origin['sources']),
            'invalid reference origin')
    validate_signatures(fixture['signatures'])
    cases = fixture['cases']
    require(isinstance(cases, list), 'invalid cases data')
    for case in cases:
        validate_case(case)
    require(tuple(case['id'] for case in cases) == CASE_IDS,
            'Figure12 paper case inventory changed')
    require([case['id'] for case in cases if not case['paper_acceptance']] ==
            ['A11', 'C1a', 'C1c', 'E1a'], 'Figure12 paper expectations changed')
    require([case['id'] for case in cases if not case['expected_acceptance']] ==
            ['A8', 'A11', 'C1a', 'C1c', 'E1a'], 'Figure12 regression expectations changed')
    checks = fixture['type_checks']
    require(isinstance(checks, list) and len(checks) == 4, 'invalid type-check inventory')
    for check in checks:
        require(isinstance(check, dict) and set(check) == {'id', 'label', 'source', 'expected'}
                and all(isinstance(check[key], str) and check[key] for key in ('id', 'label', 'source')),
                'invalid typed assertion data')
        validate_type(check['expected'])
    require({check['id'] for check in checks} == set(TYPE_IDS),
            'Figure12 type case identities changed')
    repairs = fixture['repairs']
    require(isinstance(repairs, list), 'invalid repair inventory')
    for repair in repairs:
        validate_case(repair, repair=True)
    require([repair['id'] for repair in repairs] == ['A11', 'C1a', 'C1c'] and
            all(repair['expected_acceptance'] for repair in repairs),
            'Figure12 annotation repairs changed')


def decode(root=ROOT):
    path = Path(root) / REFERENCE
    try:
        raw = path.read_bytes()
        fixture = json.loads(raw, object_pairs_hook=unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FixtureError(f'unreadable Figure12 reference {path}: {error}') from error
    validate_reference(fixture)
    # Figure12Direct.hs assigns its four public type IDs positionally. Bind
    # source/expectation to semantic IDs here so reference row order and labels
    # can change without silently running a different test under an existing ID.
    fixture['type_checks'].sort(key=lambda check: TYPE_IDS.index(check['id']))
    # Record the actual input, including harmless JSON layout changes. The
    # caller checks this identity again after execution to detect mixed runs.
    fixture['fixture_sha256'] = {str(REFERENCE): hashlib.sha256(raw).hexdigest()}
    return fixture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(decode(args.root), indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
