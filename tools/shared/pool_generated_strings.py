#!/usr/bin/env python3
"""Share String literals in the compiler-owned prepared-library data module.

Generate.hs emits immutable constructor expressions, not string patterns. This
transformation is restricted to that generator's output; it is not a Haskell
optimizer for user code. The unmodified generated file remains the independent
regeneration oracle. Expanding the inserted references recovers its exact bytes.
GHC still compiles the transformed module with the ordinary -O2 flags.
"""
from collections import Counter
import hashlib
import re

TOKEN = re.compile(r'"(?:[^"\\]|\\[\s\S])*"|\'(?:[^\'\\]|\\[\s\S])*\'|--[^\n]*|\{-|[A-Za-z_][A-Za-z_0-9\']*|[()]')
COMMENT = re.compile(r'\{-|-\}')
PROFILE = '-- mlf:syntax shared-haskell-v1\n'
MODULE = 'module MLF.PreparedLibraryData (libraries, parseLibrary) where {'


def tokens(text):
    """Visit strings and names, skipping character literals and nested comments."""
    position = 0
    while (match := TOKEN.search(text, position)) is not None:
        raw = match.group()
        position = match.end()
        if raw == '{-':
            depth = 1
            while depth:
                found = COMMENT.search(text, position)
                if found is None:
                    raise ValueError('unterminated generated-source comment')
                position = found.end()
                depth += 1 if found.group() == '{-' else -1
            continue
        if raw.startswith('--') or raw.startswith("'"):
            continue
        kind = 'string' if raw.startswith('"') else 'paren' if raw in ('(', ')') else 'identifier'
        yield (kind, match.start(), match.end(), raw)


def pool_leaves(text, string_names):
    """Factor only closed, typed constructor leaves from this data generator.

    In particular XTyVar and Parameter occur tens of thousands of times. No
    function application, variable operand or polymorphic constructor is
    eligible. Explicit signatures retain the constructor result types. No
    host-specific pragma or change to the shared syntax profile is introduced.
    """
    strings = {'Parameter': 'Field', 'SVar': 'SExpr', 'SConstructor': 'SExpr',
               'SStringLit': 'SExpr', 'STVar': 'SType', 'XStringTerm': 'XTerm'}
    integers = {'XTyVar': 'XTyVar', 'SIntLit': 'SExpr', 'XIntTerm': 'XTerm'}
    booleans = {'SBoolLit': 'SExpr', 'XBoolTerm': 'XTerm'}
    empty_lists = {'SCon': 'SType', 'XCon': 'XType', 'Applied': 'Field'}
    stack, candidates, types = [], [], {}
    stream = list(tokens(text))
    for kind, start, stop, raw in stream:
        if kind != 'paren':
            continue
        if raw == '(':
            stack.append(start)
            continue
        if not stack:
            raise ValueError('unbalanced generated constructor parentheses')
        begin = stack.pop()
        if stop-begin > 160:
            continue
        expression = text[begin:stop]
        match = re.fullmatch(r'\(([A-Z][A-Za-z0-9]*) (.+)\)', expression)
        if match is None:
            continue
        constructor, argument = match.groups()
        ty = None
        if constructor in strings and argument in string_names:
            ty = strings[constructor]
        elif constructor in integers and re.fullmatch(r'[0-9]+|\(-[0-9]+\)', argument):
            ty = integers[constructor]
        elif constructor in booleans and argument in ('True', 'False'):
            ty = booleans[constructor]
        elif constructor == 'SPrimitive' and re.fullmatch(r'P[A-Z][A-Za-z0-9]*', argument):
            ty = 'SExpr'
        elif constructor in empty_lists and argument.endswith(' []') and argument[:-3] in string_names:
            ty = empty_lists[constructor]
        if ty is not None:
            candidates.append((begin, stop, expression))
            types[expression] = ty
    if stack:
        raise ValueError('unbalanced generated constructor parentheses')
    counts = Counter(raw for _, _, raw in candidates)
    identifiers = {raw for kind, _, _, raw in stream if kind == 'identifier'}
    prefix = 'mlfPreparedLeaf'
    while any(name.startswith(prefix) for name in identifiers):
        prefix += 'X'
    names = {raw: prefix+str(index) for index, raw in
             enumerate(raw for raw in counts if counts[raw] > 1)}
    parts, cursor = [], 0
    for start, stop, raw in sorted(candidates):
        if raw not in names:
            continue
        if start < cursor:
            raise ValueError('overlapping generated leaf candidates')
        parts.extend([text[cursor:start], names[raw]])
        cursor = stop
    parts.append(text[cursor:])
    body = ''.join(parts)
    inverse = {name: raw for raw, name in names.items()}
    parts, cursor = [], 0
    for kind, start, stop, raw in tokens(body):
        if kind == 'identifier' and raw in inverse:
            parts.extend([body[cursor:start], inverse[raw]])
            cursor = stop
    parts.append(body[cursor:])
    if ''.join(parts) != text:
        raise ValueError('generated constructor-pool inverse is not byte exact')
    if names:
        definitions = '\n-- Shared closed generated constructor leaves.\n'+''.join(
            f'{name} :: {types[raw]}; {name} = {raw};\n'
            for raw, name in names.items())
        end = body.rfind('}')
        body = body[:end]+definitions+body[end:]
    return body, {'bindings': len(names), 'references': sum(counts[raw] for raw in names),
                  'inverse_verified': True, 'closed_typed_leaves_only': True}


def pool(text):
    if not text.startswith(PROFILE) or MODULE not in text:
        raise ValueError('not the compiler-owned prepared-library data module')
    end = text.rfind('}')
    if end < 0 or text[end:].strip() != '}':
        raise ValueError('invalid generated module terminator')
    stream = list(tokens(text))
    counts = Counter(raw for kind, _, _, raw in stream if kind == 'string')
    identifiers = {raw for kind, _, _, raw in stream if kind == 'identifier'}
    prefix = 'mlfPreparedString'
    while any(name.startswith(prefix) for name in identifiers):
        prefix += 'X'
    names = {raw: prefix + str(index)
             for index, raw in enumerate(raw for raw in counts if counts[raw] > 1)}
    parts, cursor = [], 0
    for kind, start, stop, raw in stream:
        if kind == 'string' and raw in names:
            parts.extend([text[cursor:start], names[raw]])
            cursor = stop
    parts.append(text[cursor:])
    body = ''.join(parts)
    inverse = {name: raw for raw, name in names.items()}
    parts, cursor = [], 0
    for kind, start, stop, raw in tokens(body):
        if kind == 'identifier' and raw in inverse:
            parts.extend([body[cursor:start], inverse[raw]])
            cursor = stop
    parts.append(body[cursor:])
    if ''.join(parts) != text:
        raise ValueError('generated string-pool inverse is not byte exact')
    if names:
        definitions = '\n-- Shared immutable generated String literals.\n' + ''.join(
            f'{name} :: String; {name} = {raw};\n' for raw, name in names.items())
        end = body.rfind('}')
        result = body[:end] + definitions + body[end:]
    else:
        result = body
    result, leaves = pool_leaves(result, set(names.values()))
    digest = lambda s: hashlib.sha256(s.encode('utf-8')).hexdigest()
    return result, {'format': 2, 'original_sha256': digest(text),
                    'pooled_sha256': digest(result), 'original_bytes': len(text.encode('utf-8')),
                    'pooled_bytes': len(result.encode('utf-8')), 'bindings': len(names),
                    'references': sum(counts[raw] for raw in names), 'inverse_verified': True,
                    'constructor_pool': leaves}
