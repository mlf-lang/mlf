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
        fields = ['format', 'identity', 'target_triple', 'data_layout', 'primitive_abi', 'runtime_abi',
                  'export_abi', 'providers', 'runtime', 'objects', 'clang', 'link_args', 'link_inputs',
                  'source_roots']
        manifest = {field: {'sentinel': field} for field in fields}
        manifest.update(exports=['large schema'], declarations=['layout'], constructor_tags=['tags'])
        manifest['runtime_abi'] = 'mlf_require_haskell_boundary_v4_abi'
        rejects('prior runtime ABI', lambda: N.runtime_contract(manifest))
        manifest['runtime_abi'] = 'mlf_require_runtime_v5_abi'
        contract = N.runtime_contract(manifest)
        assert set(contract) == set(fields)
        assert all(contract[field] == manifest[field] for field in fields)
        for field in fields:
            incomplete = dict(manifest)
            del incomplete[field]
            rejects('compact contract requires ' + field, lambda: N.runtime_contract(incomplete))
        print('PASS compact contract exact field projection')

        # A provider set may contain an unsupported crate between two eligible
        # crates. The inventory must retain that crate without inventing an
        # object, and preserve the producer's stable index for later providers.
        providers = []
        for index, owner in enumerate(('alpha', 'beta', 'gamma')):
            eligible = owner != 'beta'
            contract = {'format': 'MLF-NATIVE-CRATE-1', 'export_abi': 'mlf-crate-boxed/1',
                        'runtime_abi': 'mlf_require_runtime_v5_abi', 'crate_id': owner,
                        'identity': 'abc'[index] * 64,
                        'status': 'eligible' if eligible else 'unsupported'}
            if eligible:
                contract.update(imports=[], exports=[], constructor_tags=[])
            else:
                contract['reason'] = 'fixture requires checked IR'
            providers.append({'contract': contract, 'llvm': f'library-{index}.ll' if eligible else None})
        metadata = {'format': 'MLF-NATIVE-INSTALLATION-1', 'export_abi': 'mlf-crate-boxed/1',
                    'runtime_abi': 'mlf_require_runtime_v5_abi', 'providers': providers}
        assert N.provider_rows(metadata) == providers
        outputs = set(N.output_names(metadata))
        assert {'library-0.ll', 'library-0.o', 'library-2.ll', 'library-2.o', 'runtime.o'} <= outputs
        assert not {'library-1.ll', 'library-1.o', 'library.o'}.intersection(outputs)
        commands = N.native_commands(root / 'native', {'clang': {'path': '/fixture/clang'}, 'runtime_flags': []}, metadata)
        assert set(commands) == {'target', 'library-0', 'library-2', 'runtime'}
        assert commands['library-2'][-1] == str(root / 'native/library-2.o')
        duplicate = {**metadata, 'providers': [providers[0], providers[0]]}
        rejects('duplicate provider owner', lambda: N.provider_rows(duplicate))
        unsupported_object = {**metadata, 'providers': [providers[0], {**providers[1], 'llvm': 'library-1.ll'}, providers[2]]}
        rejects('unsupported provider with LLVM', lambda: N.provider_rows(unsupported_object))
        print('PASS mixed provider inventory preserves stable indices')
    if args.disposable_idle_sources is None:
        return
    root = args.disposable_idle_sources.resolve()
    assert N.verify(root)['kind'] == 'installed'
    native = root.parent / 'native'
    receipt = native / 'receipt.json'
    data = root / N.DATA
    manifest = native / 'manifest.json'
    providers = [row for row in N.read(manifest)['providers'] if row['object'] is not None]
    assert providers, 'fixture installation must provide a native crate'
    provider_object = Path(providers[0]['object']['path'])
    provider_backup = Path(N.read(receipt)['first_outputs'][str(provider_object)]['path'])
    # Installation provenance rejects mutated bytes even though a per-program
    # consumer may choose checked IR when an optional provider is unavailable.
    for label, path in [('object corruption', provider_object),
                        ('backup corruption', provider_backup),
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
    contract = native / 'runtime-contract.json'
    contract_edits = [
        ('target', lambda c: c.__setitem__('target_triple', 'forged-unknown-target')),
        ('source roots', lambda c: c.__setitem__('source_roots', ['/untrusted/stdlib'])),
        ('provider ABI', lambda c: c['providers'][0]['contract'].__setitem__('export_abi', 'forged')),
        ('provider inventory', lambda c: c['providers'].pop()),
    ]
    for label, edit in contract_edits:
        with mutate_json(contract, edit):
            with changed(data, N.registry(N.read(contract), contract)):
                rejects('compact ' + label + ' plus self-rehashed registry', lambda: N.verify(root))
    def rehash_provider(value):
        for row in value['objects']:
            if row['path'] == str(provider_object):
                row['sha256'] = N.sha(provider_object)
        for row in value['providers']:
            if row['object'] is not None and row['object']['path'] == str(provider_object):
                row['object']['sha256'] = N.sha(provider_object)

    with changed(provider_object, provider_object.read_bytes() + b'forged'):
        with mutate_json(manifest, rehash_provider):
            contract = native / 'runtime-contract.json'
            with changed(contract, (json.dumps(N.runtime_contract(N.read(manifest))) + '\n').encode()):
                with changed(data, N.registry(N.read(manifest), contract)):
                    rejects('object plus self-rehashed manifests and registry', lambda: N.verify(root))
    assert N.verify(root)['kind'] == 'installed'
    print('PASS original installation restored')


if __name__ == '__main__':
    main()
