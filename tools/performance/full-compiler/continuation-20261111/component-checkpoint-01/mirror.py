"""Frozen, host-only sparse SCC mirror. Never feed these copies to the MLF parser."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMMIT = 'f9bdb40a659bfdff4cbb782d438afbb0417dd2e1'
MAINS = {'emlf': 'host/ghc/app/emlf/Main.hs', 'builtin-prelude': 'host/ghc/app/builtin-prelude/Main.hs'}
class MirrorError(ValueError): pass

def sha(data): return hashlib.sha256(data).hexdigest()
def regular(path):
    path = Path(path).absolute()
    for p in [path, *path.parents]:
        if p.is_symlink(): raise MirrorError(f'symlink forbidden: {p}')
    if not path.is_file(): raise MirrorError(f'not a regular file: {path}')
    return path

def specification():
    return json.loads(regular(HERE / 'insertion-map.json').read_text())

def transform(relative, original):
    spec = specification()
    if relative not in spec['pins'] or sha(original) != spec['pins'][relative]:
        raise MirrorError(f'frozen source mismatch: {relative}')
    text = original.decode('utf-8')
    for edit in spec['edits'].get(relative, []):
        if text.count(edit['before']) != 1: raise MirrorError('insertion occurrence mismatch')
        text = text.replace(edit['before'], edit['after'])
    return text.encode('utf-8')

def inverse_bytes(relative, annotated):
    text = annotated.decode('utf-8')
    for edit in reversed(specification()['edits'].get(relative, [])):
        if text.count(edit['after']) != 1: raise MirrorError('inverse occurrence mismatch')
        text = text.replace(edit['after'], edit['before'])
    original = text.encode('utf-8')
    if sha(original) != specification()['pins'].get(relative): raise MirrorError('inverse identity mismatch')
    return original

def prepare(source, destination):
    source, destination = Path(source).absolute(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink(): raise MirrorError('destination must be absent')
    for p in destination.parents:
        if p.is_symlink(): raise MirrorError('symlink destination parent')
    if destination == source or source in destination.parents: raise MirrorError('mirror must be outside source')
    spec = specification()
    closure = spec['union']
    if len(closure) != 95 or len([p for p in closure.values() if p.startswith('host/')]) != 4:
        raise MirrorError('95/91/4 union mismatch')
    prepared = {}
    for rel in spec['pins']:
        original = regular(source / rel).read_bytes()
        annotated = transform(rel, original)
        if inverse_bytes(rel, annotated) != original: raise MirrorError('non-reversible transform')
        prepared[rel] = (original, annotated)
    destination.mkdir(parents=True)
    entries, patch = {}, []
    for rel, (original, annotated) in prepared.items():
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(annotated)
        entries[rel] = {'original_sha256': sha(original), 'annotated_sha256': sha(annotated),
                        'occurrences': len(spec['edits'].get(rel, []))}
        patch.extend(difflib.unified_diff(original.decode().splitlines(True), annotated.decode().splitlines(True),
                                          fromfile='frozen/' + rel, tofile='mirror/' + rel))
    manifest = {'schema': 'sparse-scc-mirror-v1', 'source_commit': COMMIT, 'source': str(source),
                'mirror': str(destination), 'union': closure, 'mains': MAINS, 'files': entries,
                'emlf_modules': spec['emlf_modules'], 'generator_modules': spec['generator_modules'],
                'interpretation': 'profiled source-demand allocation; not ordinary exclusive CPU'}
    (destination / 'mirror-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'mirror.patch').write_text(''.join(patch))
    return manifest

def verify_mirror(source, destination):
    destination = Path(destination).absolute()
    manifest = json.loads(regular(destination / 'mirror-manifest.json').read_text())
    spec = specification()
    if manifest['union'] != spec['union'] or manifest['mains'] != MAINS: raise MirrorError('inventory changed')
    if set(manifest['files']) != set(spec['pins']): raise MirrorError('file inventory changed')
    for rel, entry in manifest['files'].items():
        original = regular(Path(source) / rel).read_bytes()
        annotated = regular(destination / rel).read_bytes()
        if transform(rel, original) != annotated or inverse_bytes(rel, annotated) != original:
            raise MirrorError('mirror content changed')
        if entry['original_sha256'] != sha(original) or entry['annotated_sha256'] != sha(annotated):
            raise MirrorError('manifest content identity changed')
    if manifest['source_commit'] != COMMIT or manifest['mirror'] != str(destination): raise MirrorError('manifest identity changed')
    return manifest

def validate_provenance(records, manifest, role):
    """records are observed GHC compile rows: {module, source, object, interface}.
    Requires exact role closure and Main; paths cannot resolve to ordinary inputs.
    Caller independently verifies logged command flags, fresh output directories and
    actual artifact hashes. A hand-authored row list is not build authentication.
    """
    spec = specification()
    if role == 'union':
        expected = dict(spec['union'])
    elif role in ('emlf-main', 'builtin-prelude-main'):
        expected = {'Main': MAINS[role[:-5]]}
    elif role in MAINS:
        names = spec['emlf_modules'] if role == 'emlf' else spec['generator_modules']
        expected = {name: spec['union'][name] for name in names}
        expected['Main'] = MAINS[role]
    else:
        raise MirrorError('unknown build role')
    if len(records) != len(expected) or {r['module'] for r in records} != set(expected):
        raise MirrorError('actual module closure differs')
    root = Path(manifest['mirror']).absolute()
    for r in records:
        if Path(r['source']).absolute() != root / expected[r['module']]: raise MirrorError('source provenance differs')
        regular(r['source'])
        if not r['object'].endswith('.p_o') or not r['interface'].endswith('.p_hi'): raise MirrorError('ordinary/profile ABI mixing')
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('destination'); parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    result = verify_mirror(args.source, args.destination) if args.verify else prepare(args.source, args.destination)
    print(json.dumps({'files': len(result['files']), 'union': len(result['union']), 'source_commit': COMMIT}))
