#!/usr/bin/env python3
"""Decode maintained Figure12 declarative DATA, never translate/execute guest code.

Only the constructor/application/lexical-let fragment used by the fixture is
accepted. Expressions inside strings remain opaque. The shared Haskell harness
must parse those strings, compute free names, and construct assumption wrappers.
Unsupported fixture syntax is an error, not a guessed interpretation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]

# Semantic contract reviewed against Figure12Direct.hs. These files contain
# executable oracle logic that the DATA decoder intentionally does not execute.
# Pin whole files so any change (including helper semantics or fixture data)
# requires a fresh oracle-parity review before updating this allowlist. Never
# regenerate these digests automatically to make a test pass. Fixture values
# below are still decoded from the maintained files, not duplicated here.
REVIEWED_SEMANTIC_SHA256 = {
    'tests/Tests/Figure12.emlf': '8c46d65781f1e85c8068822bd8416ffc04866a8bb40c08b5160a0358b78d9600',
    'tests/Tests/Figure12Suite.emlf': '7c446bf415dcd96f21c01d6fba1a8bca537932293c63a808739818d4422436fd',
    'tests/Tests/Helpers.emlf': 'e915d86eb800e8ec736a961ccc870d530facc64e37814acd64b1a1f832deb590',
    'tests/Tests/Map.emlf': '104b5066749811d3c9cc106fc40e83cd406c838fbc211e42da62237f626a8d25',
    'tests/Tests/Set.emlf': '07a3b77d3ade77e08aa7cd72e03e5a7023c3d7b3c976bbf652e35745a6989920',
}


class FixtureError(ValueError):
    pass


TOKEN = re.compile(r'\s+|--[^\n]*|"(?:[^"\\]|\\["\\nrt])*"|[A-Za-z_][A-Za-z_0-9\']*|[0-9]+|\[\]|\(:\)|\(,\)|[(){}=;]')


def tokens(source):
    result, pos = [], 0
    while pos < len(source):
        match = TOKEN.match(source, pos)
        if not match:
            raise FixtureError(f"unsupported data syntax at {source[pos:pos+40]!r}")
        value = match.group()
        pos = match.end()
        if not value.isspace() and not value.startswith('--'):
            result.append(value)
    return result


class Parser:
    def __init__(self, source):
        self.ts, self.i = tokens(source), 0

    def peek(self):
        return self.ts[self.i] if self.i < len(self.ts) else None

    def take(self, wanted=None):
        got = self.peek()
        if got is None or (wanted is not None and got != wanted):
            raise FixtureError(f"expected {wanted!r}, got {got!r}")
        self.i += 1
        return got

    def expression(self):
        if self.peek() == 'let':
            self.take('let')
            self.take('{')
            name = self.take()
            params = []
            while self.peek() != '=':
                params.append(self.take())
            if not all(re.fullmatch(r'[a-z][A-Za-z0-9_]*', x) for x in [name] + params):
                raise FixtureError('unsupported let binding')
            self.take('=')
            body = self.expression()
            self.take('}')
            self.take('in')
            return ('let', name, params, body, self.expression())
        parts = []
        while self.peek() not in (None, ')', '}', ';', 'in'):
            token = self.take()
            if token == '(':
                item = self.expression()
                self.take(')')
            elif token.startswith('"'):
                item = ('literal', json.loads(token))
            elif token.isdigit():
                item = ('literal', int(token))
            elif token in ('[]', '(:)', '(,)') or re.fullmatch(r'[A-Za-z_][A-Za-z_0-9\']*', token):
                item = ('name', token)
            else:
                raise FixtureError(f'unsupported atom {token!r}')
            parts.append(item)
        if not parts:
            raise FixtureError('empty expression')
        return ('apply', parts)

    def parse(self):
        tree = self.expression()
        if self.peek() is not None:
            raise FixtureError(f'trailing token {self.peek()!r}')
        return tree


def curry(arity, function, args=()):
    def apply(value):
        collected = args + (value,)
        return function(*collected) if len(collected) == arity else curry(arity, function, collected)
    return apply


def case(name, expression, paper, expected, signatures):
    if not isinstance(name, str) or not isinstance(expression, str) or type(paper) is not bool or type(expected) is not bool:
        raise FixtureError('invalid Case fields')
    pairs(signatures)
    return dict(id=name, expression=expression, paper_acceptance=paper,
                expected_acceptance=expected, local_signatures=signatures)


def pairs(value):
    if not isinstance(value, list) or any(not isinstance(p, list) or len(p) != 2 or not all(isinstance(x, str) for x in p) for p in value):
        raise FixtureError('expected signature pairs')
    return value


def environment():
    env = {'true': True, 'false': False, '[]': [],
           '(,)': curry(2, lambda a, b: [a, b]),
           '(:)': curry(2, lambda a, b: [a] + b if isinstance(b, list) else fail('invalid canonical cons tail')),
           'Case': curry(5, case), 'XBot': ['XBot'],
           'typed': curry(2, lambda source, expected: {'source': source, 'expected': expected})}
    for name, key in [('caseId', 'id'), ('expression', 'expression'), ('paperAcceptance', 'paper_acceptance'), ('expectedAcceptance', 'expected_acceptance'), ('localSignatures', 'local_signatures')]:
        env[name] = curry(1, lambda c, key=key: c[key])
    for name, arity in [('XTyVar', 1), ('XVar', 1), ('XArrow', 2), ('XForall', 3)]:
        env[name] = curry(arity, lambda *args, name=name: [name, *args])
    return env


def fail(message):
    raise FixtureError(message)


def evaluate(tree, env):
    tag = tree[0]
    if tag == 'literal':
        return tree[1]
    if tag == 'name':
        if tree[1] not in env:
            raise FixtureError(f'unknown data name {tree[1]}')
        return env[tree[1]]
    if tag == 'let':
        _, name, params, body, rest = tree
        value = curry(len(params), lambda *args: evaluate(body, dict(env, **dict(zip(params, args))))) if params else evaluate(body, env)
        return evaluate(rest, dict(env, **{name: value}))
    if tag == 'apply':
        value = evaluate(tree[1][0], env)
        for argument in tree[1][1:]:
            if not callable(value):
                raise FixtureError('application of non-function data')
            value = value(evaluate(argument, env))
        return value
    raise FixtureError(f'unknown AST node {tag}')


def declaration(source, name, env):
    # Maintained data declarations deliberately occupy one line. Never consume
    # an arbitrary surrounding executable declaration on a formatting change.
    matches = re.findall(r'^' + re.escape(name) + r' = (.+)$', source, re.M)
    if len(matches) != 1:
        raise FixtureError(f'expected exactly one single-line {name} declaration')
    return evaluate(Parser(matches[0]).parse(), env)


def validate_type(node):
    if not isinstance(node, list) or not node:
        raise FixtureError('invalid expected XType data')
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


def validate_var(node):
    if not isinstance(node, list) or len(node) != 2 or node[0] != 'XTyVar' or type(node[1]) is not int:
        raise FixtureError('invalid expected type variable')


def decode(root=ROOT):
    root = Path(root)
    semantic_hashes = {}
    reviewed_sources = {}
    for relative, reviewed in REVIEWED_SEMANTIC_SHA256.items():
        try:
            contents = (root / relative).read_bytes()
            actual = hashlib.sha256(contents).hexdigest()
        except OSError as error:
            raise FixtureError(f'missing reviewed semantic fixture {relative}: {error}') from error
        if actual != reviewed:
            raise FixtureError(f'unreviewed Figure12 oracle semantics: {relative}; '
                               'review harness/oracle parity before updating semantic digest allowlist')
        semantic_hashes[relative] = actual
        reviewed_sources[relative] = contents.decode('utf-8')
    fixture = reviewed_sources['tests/Tests/Figure12.emlf']
    suite = reviewed_sources['tests/Tests/Figure12Suite.emlf']
    # Projections are the only fixture functions provided by the decoder.
    # Verify their maintained definitions before assigning those meanings.
    projections = [
        'data Case = Case String String Bool Bool ([] ((,) String String))',
        'caseId (Case a _ _ _ _) = a',
        'expression (Case _ a _ _ _) = a',
        'paperAcceptance (Case _ _ a _ _) = a',
        'expectedAcceptance (Case _ _ _ a _) = a',
        'localSignatures (Case _ _ _ _ a) = a',
    ]
    for line in projections:
        if fixture.splitlines().count(line) != 1:
            raise FixtureError('unsupported Case declaration/projection')
    env = environment()
    signatures = pairs(declaration(fixture, 'signatures', env))
    cases = declaration(fixture, 'cases', env)
    if not isinstance(cases, list) or any(not isinstance(c, dict) or set(c) != {'id', 'expression', 'paper_acceptance', 'expected_acceptance', 'local_signatures'} for c in cases):
        raise FixtureError('invalid cases data')
    env['identity'] = declaration(suite, 'identity', env)
    checks = declaration(suite, 'typeChecks', env)
    type_checks = []
    if not isinstance(checks, list) or any(not isinstance(c, list) or len(c) != 2 for c in checks):
        raise FixtureError('invalid typeChecks list')
    for label, check in checks:
        if not isinstance(label, str) or not isinstance(check, dict) or set(check) != {'source', 'expected'}:
            raise FixtureError('invalid typed assertion data')
        if not isinstance(check['source'], str):
            raise FixtureError('invalid typed source string')
        validate_type(check['expected'])
        type_checks.append(dict(label=label, **check))
    # Decode the maintained, closed three-way repair selector. Its dispatch
    # structure is checked, not executed or generalized into a source translator.
    lines = re.findall(r'^  let expression = (.+)$', suite, re.M)
    if len(lines) != 1:
        raise FixtureError('missing/ambiguous repair selector')
    string = r'("(?:[^"\\]|\\["\\nrt])*")'
    match = re.fullmatch(r'if eqString label ' + string + r' then ' + string + r' else if eqString label ' + string + r' then ' + string + r' else ' + string, lines[0])
    if not match:
        raise FixtureError('unsupported repair selector')
    first, first_source, second, second_source, fallback = map(json.loads, match.groups())
    labels = re.findall(r'^  runTest \(\(,\) \(label \+\+ " explicit annotation control"\) \(testCase repaired\)\)\) \(O.words ' + string + r'\)$', suite, re.M)
    if len(labels) != 1:
        raise FixtureError('unsupported repair labels')
    repair_labels = json.loads(labels[0]).split()
    if len(repair_labels) != 3 or repair_labels[:2] != [first, second] or len(set(repair_labels)) != 3:
        raise FixtureError('repair selector/labels do not agree')
    required = '  let repaired = Case (caseId c) expression (paperAcceptance c) true (localSignatures c)'
    if suite.splitlines().count(required) != 1:
        raise FixtureError('unsupported repaired Case construction')
    index = {c['id']: c for c in cases}
    if len(cases) != 43 or len(index) != 43 or len(type_checks) != 4:
        raise FixtureError('maintained Figure12 inventory changed')
    repairs = []
    for label, source in zip(repair_labels, [first_source, second_source, fallback]):
        if label not in index:
            raise FixtureError('repair refers to missing case')
        repairs.append(dict(index[label], expression=source, expected_acceptance=True,
                            label=label + ' explicit annotation control'))
    return {'schema_version': 1, 'signatures': signatures, 'cases': cases,
            'type_checks': type_checks, 'repairs': repairs,
            'fixture_sha256': semantic_hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(decode(args.root), indent=2, ensure_ascii=True))


if __name__ == '__main__':
    main()
