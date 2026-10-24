#!/usr/bin/env python3
"""Static local-source snapshot audit, not a substitute for mlfpkg lock/plan.

Mirrors Package.Manifest.sourceFiles/snapshot for local source dependencies only.
Rejects unsupported remote/released dependencies instead of inventing identities.
--write updates root mlf.lock; normal use verifies it without modifying files.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(), object_pairs_hook=strict_object)


def local(root, name):
    if not name or Path(name).is_absolute() or re.match(r'^[A-Za-z]:', name):
        raise ValueError(f'source path must be relative: {name}')
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'escaping package source: {name}')
    if not path.is_file():
        raise ValueError(f'missing source: {path}')
    return path


def source_imports(text):
    """Scan import keywords outside comments/literals, including braced layout.

    This is an inventory lexer, not a replacement for either compiler parser.
    Unsupported/malformed import heads fail closed instead of disappearing.
    """
    code = list(text)
    index = 0
    def blank(start, end):
        for at in range(start, end):
            if code[at] != '\n':
                code[at] = ' '
    while index < len(text):
        if text.startswith('--', index):
            end = text.find('\n', index)
            end = len(text) if end < 0 else end
            blank(index, end)
            index = end
        elif text.startswith('{-', index):
            start, depth = index, 1
            index += 2
            while index < len(text) and depth:
                if text.startswith('{-', index):
                    depth += 1
                    index += 2
                elif text.startswith('-}', index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise ValueError('unterminated source block comment')
            blank(start, index)
        elif text[index] == '"':
            start = index
            index += 1
            while index < len(text):
                if text[index] == '\\':
                    index += 2
                elif text[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
            else:
                raise ValueError('unterminated source string literal')
            blank(start, min(index, len(text)))
            code[start] = '"'  # A package-string import must not turn into spaces.
        else:
            index += 1
    cleaned = ''.join(code)
    imports = []
    for token in re.finditer(r"(?<![\w'])import(?![\w'])", cleaned):
        tail = cleaned[token.end():]
        matched = re.match(r'\s+(?:qualified\s+)?([A-Z][A-Za-z0-9_\']*(?:\.[A-Z][A-Za-z0-9_\']*)*)(?=\s|[;()}]|$)', tail)
        if not matched:
            raise ValueError('unsupported or malformed source import')
        imports.append(matched[1])
    return imports


def source_builtins(source, text):
    # This is a conservative inventory check, not the compiler prologue parser.
    # Shared sources explicitly opt in before code; a filename alone is not proof.
    marker = text.splitlines()[0] if text.splitlines() else ''
    shared = marker == '-- mlf:syntax shared-haskell-v1'
    if Path(source).suffix == '.hs' and not shared:
        raise ValueError(f'shared source requires explicit profile marker: {source}')
    return {'Prelude', 'MLF.Primitive'} if shared else {'Prelude'}


def snapshot(manifest):
    base = manifest.parent.resolve()
    done, visiting, names, rows, inputs = {}, set(), {}, [], {}
    module_owners = {}
    def visit(path):
        path = path.resolve()
        if path in visiting:
            raise ValueError(f'package dependency cycle: {path}')
        if path in done:
            return done[path]
        visiting.add(path)
        value = read(path)
        if value.get('format') != 1:
            raise ValueError(f'unsupported manifest format: {path}')
        name = value['name']
        if name in names and names[name] != path:
            raise ValueError(f'duplicate package identity: {name}')
        names[name] = path
        inputs[path] = digest(path)
        dependencies = value.get('dependencies', {})
        imported = set()
        for key, dep in sorted(dependencies.items()):
            if set(dep) != {'path'}:
                raise ValueError(f'unsupported non-local dependency: {key}')
            child = visit(path.parent / dep['path'] / 'mlf-package.json')
            if child['name'] != key:
                raise ValueError(f'dependency identity mismatch: {key}')
            imported.update(child.get('library', {}).get('modules', {}))
        root = path.parent
        library = value.get('library', {}).get('modules', {})
        for module in library:
            if module in module_owners:
                raise ValueError(f'module provided by multiple packages: {module}')
            module_owners[module] = name
        groups = [(library, set(library) | imported)]
        sources = set(library.values())
        for section in ('executables', 'tests'):
            for target in value.get(section, {}).values():
                if 'main' not in target:
                    continue
                private = target.get('modules', {})
                if set(private) & set(library):
                    raise ValueError(f'private module shadows package library: {path}')
                selected = target.get('dependencies', list(dependencies))
                if not set(selected) <= set(dependencies):
                    raise ValueError(f'unknown direct target dependency: {path}')
                visible = set(library) | set(private)
                for dependency in selected:
                    child = done[(root / dependencies[dependency]['path'] / 'mlf-package.json').resolve()]
                    visible.update(child.get('library', {}).get('modules', {}))
                main = local(root, target['main'])
                header = re.search(r'^module\s+([A-Za-z0-9_.]+)\b', main.read_text(), re.M)
                if not header:
                    raise ValueError(f'missing module header: {main}')
                if header[1] in private or header[1] in library:
                    raise ValueError(f'entry module repeated in private/library modules: {main}')
                groups.append(({**private, header[1]: target['main']}, visible | {header[1]}))
                sources.update(private.values())
                sources.add(target['main'])
        for modules, visible in groups:
            for module, source in modules.items():
                text = local(root, source).read_text()
                header = re.search(r'^module\s+([A-Za-z0-9_.]+)\b', text, re.M)
                if module in {'Prelude', 'MLF.Primitive'}:
                    raise ValueError(f'reserved builtin module supplied by source: {source}')
                if not header or header[1] != module:
                    raise ValueError(f'module declaration mismatch: {source}')
                imports = source_imports(text)
                builtins = source_builtins(source, text)
                if not (set(imports) - builtins) <= visible:
                    raise ValueError(f'{name}:{module}: undeclared direct imports {sorted(set(imports) - visible - builtins)}')
        hashes = {}
        for source in sorted(sources):
            full = local(root, source)
            relative = str(full.relative_to(root))
            hashes[relative] = digest(full)
            inputs[full] = hashes[relative]
        import os
        rows.append({'name':name,'version':value['version'], 'path':os.path.relpath(root,base),
                     'manifest':inputs[path], 'sources':hashes})
        done[path] = value
        visiting.remove(path)
        return value
    visit(manifest)
    if any(digest(path) != expected for path, expected in inputs.items()):
        raise ValueError('manifest or source changed during audit')
    return {'format':1, 'packages':rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path('mlf-package.json'))
    parser.add_argument('--write', action='store_true')
    parser.add_argument('--graph-only', action='store_true')
    args = parser.parse_args()
    result = snapshot(args.manifest.resolve())
    encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), ensure_ascii=False)+'\n'
    destination = args.manifest.resolve().parent / 'mlf.lock'
    if args.write:
        destination.write_text(encoded)
    elif not args.graph_only:
        if destination.read_text() != encoded:
            raise ValueError('lock differs from actual local manifest/source graph')
    print(json.dumps({'static_only':True, 'packages':len(result['packages']),
                      'source_hashes':sum(len(p['sources']) for p in result['packages']),
                      'snapshot_sha256':hashlib.sha256(encoded.encode()).hexdigest(),
                      'lock_written':args.write, 'native_plan_verified':False},sort_keys=True))

if __name__ == '__main__':
    main()
