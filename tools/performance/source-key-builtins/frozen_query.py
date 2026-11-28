"""Bridge the fixed named query oracle to the host's constructor interface.

The oracle's identity is fixed; the maintained Bootstrap.Types file is not.
Only the two consumed data declarations matter. New constructors are admitted
only when this adapter explicitly rejects them in every oracle traversal.
"""
from pathlib import Path
import hashlib
import re

# Constructor names and field counts are the interface consumed by the old
# algorithm. Changes to unrelated data declarations, comments and formatting
# do not change this contract.
_NAMED_EXPRESSION = {
    'SVar': 1, 'SConstructor': 1, 'SLam': 3, 'SApp': 2, 'SLet': 3,
    'SAnn': 2, 'SSignature': 2, 'SIntLit': 1, 'SDoubleLit': 1,
    'SBoolLit': 1, 'SStringLit': 1, 'SPrimitive': 1, 'SCase': 2,
    'SDo': 2, 'SEquations': 1, 'SLetRec': 2, 'SWanted': 2,
    'SChecked': 2, 'SSourceDefinition': 1, 'SCallSite': 3, 'SSharedBind': 5,
}
_NAMED_PATTERN = {
    'SConstructorPattern': 2, 'SDefaultPattern': 1, 'SNestedPattern': 2,
    'SAnnotatedPattern': 2, 'SIntPattern': 1, 'SStringPattern': 1,
    'SOverloadedStringPattern': 3, 'SBoolPattern': 1, 'SAsPattern': 2,
    'SLazyPattern': 1,
}
_UNSUPPORTED_EXPRESSION = {
    'SGlobal': 2, 'SDeclScope': 2, 'SWantedRefs': 2,
    'SWantedScope': 2, 'SGivenScope': 2,
    'SApplyDictionaries': 2, 'SBindDictionaries': 2,
}
_UNSUPPORTED_PATTERN = {'SIndexedStringPattern': 3}


def _without_comments(source):
    """Strip Haskell line/nested block comments while preserving boundaries."""
    result, index, nesting = [], 0, 0
    while index < len(source):
        pair = source[index:index + 2]
        if pair == '{-':
            nesting += 1
            result.append(' ')
            index += 2
        elif nesting and pair == '-}':
            nesting -= 1
            result.append(' ')
            index += 2
        elif nesting:
            index += 1
        elif pair == '--':
            end = source.find('\n', index)
            index = len(source) if end < 0 else end
        elif source[index] == '"':
            # Unrelated code may quote declarations or comment markers.
            result.append(' ')
            index += 1
            while index < len(source) and source[index] != '"':
                index += 2 if source[index] == '\\' else 1
            if index >= len(source):
                raise ValueError('Unclosed Bootstrap.Types string literal')
            index += 1
        else:
            result.append(source[index])
            index += 1
    if nesting:
        raise ValueError('Unclosed Bootstrap.Types comment')
    return ''.join(result)


def _constructors(source, name):
    # The shared Haskell interface uses explicit declaration semicolons.
    declarations = re.findall(r'\bdata\s+' + name + r'\s*=([^;]+);', source)
    if len(declarations) != 1:
        raise ValueError('Expected one Bootstrap.Types declaration: ' + name)
    constructors = {}
    for declaration in declarations[0].split('|'):
        tokens = re.findall(r'[A-Za-z_][A-Za-z_0-9.\']*|[^\s]', declaration)
        if not tokens or not re.fullmatch(r'[A-Z][A-Za-z_0-9\']*', tokens[0]):
            raise ValueError('Unsupported constructor declaration in ' + name)
        constructor, fields, stack = tokens[0], 0, []
        for token in tokens[1:]:
            if token in ('(', '['):
                if not stack:
                    fields += 1
                stack.append(token)
            elif token in (')', ']'):
                if not stack or stack.pop() != {')': '(', ']': '['}[token]:
                    raise ValueError('Unbalanced constructor fields: ' + constructor)
            elif not stack and token != '!':
                if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9.\']*', token):
                    raise ValueError('Unsupported constructor field: ' + constructor)
                fields += 1
        if stack or constructor in constructors:
            raise ValueError('Invalid constructor declaration: ' + constructor)
        constructors[constructor] = fields
    return constructors


def unsupported_constructors(types_source):
    source = _without_comments(Path(types_source).read_text())
    rejected = []
    for name, named, extra in (('SPattern', _NAMED_PATTERN, _UNSUPPORTED_PATTERN),
                               ('SExpr', _NAMED_EXPRESSION, _UNSUPPORTED_EXPRESSION)):
        actual = _constructors(source, name)
        if any(actual.get(ctor) != arity for ctor, arity in named.items()):
            raise ValueError('Unsupported Bootstrap.Types named interface: ' + name)
        for constructor, arity in actual.items():
            if constructor not in named and extra.get(constructor) != arity:
                raise ValueError('Unsupported Bootstrap.Types constructor: ' + constructor)
        rejected.append([constructor + ' _' * arity
                         for constructor, arity in extra.items() if constructor in actual])
    return rejected


def prepare_frozen_query(source: Path, out_dir: Path, *, expected_sha256: str, types_source: Path) -> Path:
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_sha256:
        raise ValueError(f'Frozen query source differs from the pinned oracle: {source}')
    patterns, expressions = unsupported_constructors(types_source)
    # Only the fixed oracle's known traversal sites are adapted. No code is
    # extracted from the maintained source. The historical branches, including
    # the named canonicalization defaults, stay byte-for-byte unchanged.
    cases = [(b'case pattern of {', 2, patterns),
             (b'case expression of {', 3, expressions)]
    adapted = original
    for anchor, count, constructors in cases:
        inserted = b''.join(b'\n      ' + constructor.encode() +
                            b' -> panic "indexed syntax in historical named query oracle";'
                            for constructor in constructors)
        if adapted.count(anchor) != count:
            raise ValueError(f'Unexpected frozen query cases in {source}')
        adapted = adapted.replace(anchor, anchor + inserted)
    output = out_dir / 'FrozenCrateQuery.hs'
    output.write_bytes(adapted)
    return output
