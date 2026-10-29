#!/usr/bin/env python3
"""Authenticate canonical prepared data against frozen inputs and fresh regeneration.

This is local build evidence, not a cryptographic signature from a third party.
A populated registry is never authenticated by builtin-prelude equality alone.
"""
from __future__ import annotations
import hashlib
import json
import re
import stat
from pathlib import Path

DATA = 'bootstrap/MLF/PreparedLibraryData.hs'
NATIVE_DATA = 'bootstrap/MLF/PreparedNativeData.hs'
# Exact committed disabled registry; arbitrary code containing `libraries = []`
# must not bypass the populated-registry gate.
EMPTY_SHA256 = 'eececfa9f5b0ef2901e749b4a1798ac2cf78bea3378d9e33fcbc0a0ded94c6b1'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(path.read_text())

def require(condition, message):
    if not condition:
        raise ValueError('prepared library verification: ' + message)

def producer_commands(root, job, manifest, ghc, cc):
    """The canonical producer command contract shared by validation controls."""
    build = job / 'build'
    objects = build / 'generate-prepared-libraries-objects'
    flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
             '-no-user-package-db', '-hide-all-packages', '-O2', '-fpedantic-bottoms', '-fno-state-hack',
             '-Werror=incomplete-patterns', '-Werror=incomplete-uni-patterns', '-Wno-star-is-type',
             '-Wno-overlapping-patterns', '-Wno-deprecations', '-i',
             *['-i' + str(root / value) for value in manifest['source_roots']],
             '-odir', str(objects), '-hidir', str(objects)]
    for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
        flags += ['-package', package]
    commands = {}
    for name, source in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        commands[name] = [cc, '-O2', '-std=c11', '-I' + str(root / 'runtime'), '-c', str(root / source), '-o', str(build / (name + '.o'))]
    commands['build-generate-prepared-libraries'] = [ghc, '--make', '-j1', *flags,
        str(root / 'tools/experimental/prepared-libraries/Generate.hs'), str(build / 'host.o'),
        str(build / 'supervisor.o'), '-o', str(build / 'generate-prepared-libraries')]
    commands['generate'] = [str(build / 'generate-prepared-libraries'), str(job / 'request.json')]
    return commands

def regeneration_commands(job, first):
    work = job / 'regeneration'
    result, transports = {}, {}
    for name in ['host', 'supervisor']:
        command = list(first[name])
        index = command.index('-o') + 1
        transports[command[index]] = str(work / (name + '.o'))
        command[index] = transports[command[index]]
        result['rebuild-' + name] = command
    command = [transports.get(value, value) for value in first['build-generate-prepared-libraries']]
    for flag in ['-odir', '-hidir']:
        command[command.index(flag) + 1] = str(work / 'objects')
    command[command.index('-o') + 1] = str(work / 'generate-prepared-libraries')
    command.insert(1, '-fforce-recomp')
    result['rebuild-generator'] = command
    result['regenerate'] = [str(work / 'generate-prepared-libraries'), str(work / 'request.json')]
    return result


def verify(root):
    root = Path(root).resolve(strict=True)
    native = None
    if (root / NATIVE_DATA).exists():
        import types
        helper = root / 'tools/shared/native_install.py'
        module = types.ModuleType('native_install')
        module.__file__ = str(helper)
        exec(compile(helper.read_bytes(), str(helper), 'exec'), module.__dict__)
        native = {**module.verify(root), 'verifier_sha256': sha(helper)}
    registry = root / DATA
    registry_hash = sha(registry)
    if registry_hash == EMPTY_SHA256:
        require(native is None or native['kind'] == 'empty', 'native installation requires populated prepared library')
        return {'format': 1, 'kind': 'empty', 'registry_sha256': registry_hash, **({'native': native} if native else {})}
    job = root.parent
    require(root == job / 'sources', 'populated registry needs an owned source job')
    owner = read(job / 'owned-source.json')
    pins = read(job / 'source-pins.json')
    names = owner['inventory']
    require(owner['format'] == 1 and names == sorted(set(names)) and set(names) == set(pins), 'source inventory mismatch')
    actual = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file())
    require(actual == names, 'owned tree has missing or extra files')
    for name, pin in pins.items():
        path = root / name
        require(not Path(name).is_absolute() and '..' not in Path(name).parts and not path.is_symlink(), 'unsafe source path')
        require(pin['snapshot'] == str(path), 'source snapshot path mismatch')
        require(stat.S_IMODE(path.stat().st_mode) == pin['mode'], 'source mode changed: ' + name)
        if name not in {DATA, NATIVE_DATA}:
            require(sha(path) == pin['sha256'] and path.stat().st_size == pin['bytes'], 'frozen source changed: ' + name)
    identity = read(job / 'identity-input.json')
    request = read(job / 'request.json')
    require(identity['source_hashes'] == {name: pin['sha256'] for name, pin in pins.items() if name not in {DATA, NATIVE_DATA}}, 'identity source hashes mismatch')
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    require(key == owner['input_identity'] == request['input_identity'], 'request identity mismatch')
    require(request['library_identity'] == 'mlf:prepared-library:' + key, 'library identity mismatch')
    for field in ['format', 'roots', 'source_root', 'source_package', 'mode', 'primitive_abi', 'frontend_semantics']:
        require(request[field] == identity[field], 'request field mismatch: ' + field)
    manifest = read(root / 'shared-sources.json')
    for field in ['primitive_abi', 'frontend_semantics']:
        require(request[field] == manifest[field], 'source manifest identity mismatch')
    require([{k: v for k, v in row.items() if k != 'buffer_path'} for row in request['library_inventory']] == identity['library_inventory'], 'library inventory mismatch')
    for row in request['library_inventory']:
        buffer = Path(row['buffer_path'])
        require(buffer.is_relative_to(root) and str(buffer.relative_to(root)) in pins, 'library buffer outside frozen inventory')
        require(sha(buffer) == row['sha256'], 'library source bytes mismatch')
    require(request['generated_source'] == str(job / 'generated/MLF/PreparedLibraryData.hs') and request['output_directory'] == str(job / 'artifacts'), 'output path mismatch')
    first = read(job / 'build/receipt.json')
    second = read(job / 'regeneration/receipt.json')
    for receipt in [first, second]:
        require(receipt['complete'] and receipt['immutable_inputs_verified_after'] and receipt['input_identity'] == key, 'incomplete producer evidence')
        require(receipt['commands'] and all(row['exit_code'] == 0 for row in receipt['commands']), 'producer command failed')
    require({'build-generate-prepared-libraries', 'generate'} <= {r['label'] for r in first['commands']}, 'missing generation commands')
    require({'rebuild-host', 'rebuild-supervisor', 'rebuild-generator', 'regenerate'} <= {r['label'] for r in second['commands']}, 'missing independent regeneration')
    command_map = {row['label']: row['argv'] for row in first['commands']}
    require(len(command_map) == len(first['commands']) == 4, 'producer command inventory mismatch')
    ghc = command_map['build-generate-prepared-libraries'][0]
    cc = command_map['host'][0]
    require(set(first['tools']) == {ghc, cc}, 'producer tool inventory mismatch')
    expected_commands = producer_commands(root, job, manifest, ghc, cc)
    require(command_map == expected_commands, 'producer argv differs from canonical source build')
    fresh_commands = {row['label']: row['argv'] for row in second['commands']}
    require(len(fresh_commands) == len(second['commands']) == 4 and fresh_commands == regeneration_commands(job, expected_commands), 'regeneration argv differs from fresh canonical producer')
    require(first['generator']['path'] == str(job / 'build/generate-prepared-libraries'), 'producer executable path mismatch')
    product = read(job / 'artifacts/generation.json')
    require(product['format'] == 'MLF-PREPARED-LIBRARY-GENERATION-1' and product['input_identity'] == key and product['source_package'] == request['source_package'], 'generation identity mismatch')
    primitive_count = re.fullmatch(r'mlf-primitive-(\d+)-v\d+', manifest['primitive_abi'])
    require(primitive_count is not None, 'unsupported primitive ABI identity')
    schema = 'mlf-prepared-libraries/1/' + manifest['frontend_semantics'] + '/' + manifest['builtin_interface'] + '/' + primitive_count.group(1)
    require(product['schema'] == schema, 'generation schema mismatch')
    modules = product['modules']
    require(modules and len(modules) == len(set(modules)) and set(request['roots']) <= set(modules), 'generation closure roots mismatch')
    library = {row['module']: row for row in request['library_inventory']}
    require(set(modules) <= set(library), 'generation closure outside library inventory')
    require(product['source_paths'] == [library[name]['path'] for name in modules] and product['source_sha256'] == [library[name]['sha256'] for name in modules], 'generation closure source identity mismatch')
    require(product['user_program_cache'] is False and product['native_object_reuse'] is False, 'unsupported generated cache scope')
    require(len(product['artifacts']) == 2, 'generation artifact inventory mismatch')
    for artifact, prefix in zip(product['artifacts'], ['builtin', 'library']):
        for field, suffix in [('metadata', '.mlfci'), ('object', '.mlfco')]:
            require(artifact[field + '_path'] == str(job / 'artifacts' / (prefix + suffix)), 'generation artifact path mismatch')
    require(product['artifacts'][1]['identity'] == request['library_identity'], 'generated library artifact identity mismatch')
    require(product == first['generated_product'], 'generation receipt mismatch')
    require(first['canonical_snapshot_registry'] == str(registry), 'canonical registry path mismatch')
    require(product['generated_source'] == request['generated_source'], 'generated path mismatch')
    outputs = {product['generated_source']: product['generated_sha256']}
    for artifact in product['artifacts']:
        for field in ['metadata', 'object']:
            outputs[artifact[field + '_path']] = artifact[field + '_sha256']
    require(registry_hash == product['generated_sha256'], 'compiled canonical module differs from generated output')
    require(registry.read_bytes() == Path(product['generated_source']).read_bytes(), 'canonical registry bytes differ')
    require(set(second['first_outputs']) == set(outputs), 'regeneration output inventory mismatch')
    comparisons = second['comparisons']
    require(len(comparisons) == len(outputs) and {row['path'] for row in comparisons} == set(outputs), 'regeneration comparison inventory mismatch')
    for path, digest in outputs.items():
        require(Path(path).is_relative_to(job) and sha(path) == digest, 'output changed: ' + path)
        backup = second['first_outputs'][path]
        require(Path(backup['path']).is_relative_to(job / 'regeneration/first'), 'backup outside job')
        require(backup['sha256'] == digest and sha(backup['path']) == digest and Path(path).read_bytes() == Path(backup['path']).read_bytes(), 'fresh regeneration bytes mismatch')
    for row in comparisons:
        require(row['bytes_equal'] and row['first_sha256'] == row['second_sha256'] == outputs[row['path']], 'regeneration digest mismatch')
    second_request_path = job / 'regeneration/request.json'
    require(sha(second_request_path) == second['request_sha256'], 'regeneration request changed')
    second_request = read(second_request_path)
    query = second_request.pop('query_directory')
    require(second_request == request and query == str(job / 'regeneration/fresh-queries') == second['query_directory'], 'regeneration changed semantic request')
    expected_inputs = {pin['snapshot']: pin['sha256'] for pin in pins.values()}
    expected_inputs[str(registry)] = registry_hash
    expected_inputs.update(first['tools'])
    expected_inputs[first['generator']['path']] = first['generator']['sha256']
    require(second['inputs'] == expected_inputs, 'regeneration input inventory mismatch')
    for path, digest in expected_inputs.items():
        if path != str(root / NATIVE_DATA):
            require(sha(path) == digest, 'producer input changed: ' + path)
    independent = second['independent_generator']
    require(independent['path'] == str(job / 'regeneration/generate-prepared-libraries') and sha(independent['path']) == independent['sha256'], 'fresh generator changed')
    evidence = ['owned-source.json', 'source-pins.json', 'identity-input.json', 'request.json', 'build/receipt.json', 'regeneration/receipt.json', 'artifacts/generation.json']
    return {'format': 1, 'kind': 'prepared', 'registry_sha256': registry_hash,
            **({'native': native} if native else {}), 'input_identity': key, 'evidence': {str(job / name): sha(job / name) for name in evidence}}

def authenticate(record, root):
    require(record == verify(root), 'build verification record mismatch')
