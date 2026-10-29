#!/usr/bin/env python3
"""Mutation controls for native installation verification.

The optional owned source tree must be idle: mutations are restored in finally.
No compiler or native build is run. Use only a disposable test installation.
"""
import argparse
import contextlib
import importlib.util
import json
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('native_install', HERE / 'native_install.py')
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)


def rejects(label, action):
    try:
        action()
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError):
        print('PASS ' + label)
        return
    raise AssertionError('accepted mutation: ' + label)


@contextlib.contextmanager
def changed(path, data):
    old = path.read_bytes()
    mode = path.stat().st_mode & 0o777
    path.chmod(mode | 0o200)
    try:
        path.write_bytes(data)
        yield
    finally:
        path.write_bytes(old)
        path.chmod(mode)


def mutate_json(path, edit):
    value = json.loads(path.read_text())
    edit(value)
    return changed(path, (json.dumps(value, indent=2) + '\n').encode())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-idle-sources', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='mlf-native-verifier-') as tmp:
        root = Path(tmp)
        data = root / N.DATA
        data.parent.mkdir(parents=True)
        data.write_bytes((HERE.parent.parent / N.DATA).read_bytes())
        assert N.sha(data) == N.EMPTY_SHA256
        assert N.verify(root)['kind'] == 'empty'
        print('PASS exact disabled registry')
        with changed(data, data.read_bytes() + b'\n'):
            rejects('changed disabled registry', lambda: N.verify(root))
        (root / 'shared-sources.json').write_text('{"modules": []}')
        producer = root / 'tools/experimental/prepared-libraries/GenerateNative.hs'
        producer.parent.mkdir(parents=True)
        producer.write_text('import MLF.PreparedNativeData\n')
        rejects('producer generated native dependency', lambda: N.producer_closure(root))
        fields = ['format', 'identity', 'target_triple', 'data_layout', 'primitive_abi',
                  'export_abi', 'objects', 'clang', 'link_args', 'link_inputs',
                  'source_roots', 'reserved_type_names']
        manifest = {field: {'sentinel': field} for field in fields}
        manifest.update(exports=['large schema'], declarations=['layout'], constructor_tags=['tags'])
        contract = N.runtime_contract(manifest)
        assert set(contract) == set(fields)
        assert all(contract[field] == manifest[field] for field in fields)
        for field in fields:
            incomplete = dict(manifest)
            del incomplete[field]
            rejects('compact contract requires ' + field, lambda: N.runtime_contract(incomplete))
        print('PASS compact contract exact field projection')
    if args.disposable_idle_sources is None:
        return
    root = args.disposable_idle_sources.resolve()
    assert N.verify(root)['kind'] == 'installed'
    native = root.parent / 'native'
    receipt = native / 'receipt.json'
    data = root / N.DATA
    for label, path in [('object corruption', native / 'library.o'),
                        ('backup corruption', native / 'first/library.o'),
                        ('generated module mutation', data),
                        ('runtime contract mutation', native / 'runtime-contract.json')]:
        with changed(path, path.read_bytes() + b'\n'):
            rejects(label, lambda: N.verify(root))
    edits = [
        ('command mutation', lambda r: r['commands'][0]['argv'].append('-DUNTRUSTED=1')),
        ('producer path mutation', lambda r: r['first_producer'].__setitem__('path', '/untrusted/producer')),
        ('input inventory mutation', lambda r: r['inputs'].pop(next(iter(r['inputs'])))),
    ]
    for label, edit in edits:
        with mutate_json(receipt, edit):
            rejects(label, lambda: N.verify(root))
    manifest = native / 'manifest.json'
    contract = native / 'runtime-contract.json'
    contract_edits = [
        ('target', lambda c: c.__setitem__('target_triple', 'forged-unknown-target')),
        ('source roots', lambda c: c.__setitem__('source_roots', ['/untrusted/stdlib'])),
        ('reserved type census', lambda c: c.__setitem__('reserved_type_names', [])),
    ]
    for label, edit in contract_edits:
        with mutate_json(contract, edit):
            with changed(data, N.registry(N.read(contract), contract)):
                rejects('compact ' + label + ' plus self-rehashed registry', lambda: N.verify(root))
    with changed(native / 'library.o', (native / 'library.o').read_bytes() + b'forged'):
        with mutate_json(manifest, lambda m: m['objects'][0].__setitem__('sha256', N.sha(native / 'library.o'))):
            contract = native / 'runtime-contract.json'
            with changed(contract, (json.dumps(N.runtime_contract(N.read(manifest))) + '\n').encode()):
                with changed(data, N.registry(N.read(manifest), contract)):
                    rejects('object plus self-rehashed manifests and registry', lambda: N.verify(root))
    assert N.verify(root)['kind'] == 'installed'
    print('PASS original installation restored')


if __name__ == '__main__':
    main()
