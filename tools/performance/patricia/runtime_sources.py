"""Copy maintained controls and expose a private module without editing its body."""
import hashlib
import importlib.util
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location(
    'patricia_frozen_oracles', Path(__file__).with_name('frozen_oracles.py'))
_oracles = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_oracles)


def copy_sources(root, out, sources):
    """Return this run's input hashes; maintained controls have no fixed pins."""
    inputs = {}
    for name, relative in sources.items():
        source = Path(root) / relative
        if relative in _oracles.FILES:
            source, raw = _oracles.read_oracle(root, relative)
        else:
            raw = source.read_bytes()
        (Path(out) / name).write_bytes(raw)
        inputs[str(source)] = hashlib.sha256(raw).hexdigest()
    return inputs


_NAME = re.compile(rb'[A-Z][A-Za-z0-9_\']*(?:\.[A-Z][A-Za-z0-9_\']*)*')
_WORD = re.compile(rb'[A-Za-z_][A-Za-z0-9_\']*')
_SYMBOLS = b'!#$%&*+./<=>?@\\^|-~:'


def private_module_view(raw, target, owner='Bootstrap.CrateSession'):
    """Replace only the module/export declaration; leave every body byte intact.

    This small lexer stops at the header's `where`. It ignores whitespace,
    line comments and nested block comments, so the public export list is not
    part of the private test view's contract. GHC checks the resulting module.
    """
    if not isinstance(raw, bytes) or not isinstance(target, str):
        raise ValueError('private module view requires bytes and a module name')
    try:
        destination = target.encode('ascii')
        expected = owner.encode('ascii')
    except (UnicodeEncodeError, AttributeError) as error:
        raise ValueError('invalid private module name') from error
    if not _NAME.fullmatch(destination) or not _NAME.fullmatch(expected):
        raise ValueError('invalid private module name')

    def skip(position):
        while position < len(raw):
            if raw[position:position + 1].isspace():
                position += 1
            elif raw.startswith(b'{-', position):
                depth = 1
                position += 2
                while position < len(raw) and depth:
                    if raw.startswith(b'{-', position):
                        depth += 1
                        position += 2
                    elif raw.startswith(b'-}', position):
                        depth -= 1
                        position += 2
                    else:
                        position += 1
                if depth:
                    raise ValueError('unterminated module-header comment')
            elif raw.startswith(b'--', position):
                dashes_end = position + 2
                while raw[dashes_end:dashes_end + 1] == b'-':
                    dashes_end += 1
                if dashes_end < len(raw) and raw[dashes_end] in _SYMBOLS:
                    break
                end = raw.find(b'\n', position)
                position = len(raw) if end < 0 else end + 1
            else:
                break
        return position

    def word(position, expected_word):
        position = skip(position)
        match = _WORD.match(raw, position)
        if match is None or match[0] != expected_word:
            raise ValueError('expected module-header ' + expected_word.decode())
        return match.end()

    start = skip(0)
    position = skip(word(start, b'module'))
    name = _NAME.match(raw, position)
    if name is None or name[0] != expected:
        raise ValueError('unexpected private module owner')
    position = skip(name.end())
    if raw[position:position + 1] == b'(':
        depth = 1
        position += 1
        while depth:
            position = skip(position)
            if position == len(raw):
                raise ValueError('unterminated module export list')
            token = raw[position:position + 1]
            if token == b'(':
                depth += 1
            elif token == b')':
                depth -= 1
            position += 1
    end = word(position, b'where')
    return raw[:start] + b'module ' + destination + b' where' + raw[end:]
