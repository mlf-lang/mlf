#!/usr/bin/env python3
"""Generate and authenticate fixed native installation inputs in an owned job.

No measured user program is an input. The producer imports only fixed checked
library data; native registry bytes are never an input to their own producer.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

DATA = 'bootstrap/MLF/PreparedNativeData.hs'
EMPTY_SHA256 = '908d33b2f9a5c74067684be01b0aecfb1a3ab802bfeda18b8f02608d0dc7de33'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')

def require(ok, message):
    if not ok:
        raise ValueError('native installation: ' + message)

def registry(manifest, manifest_path):
    def text(value):
        require(all(ord(c) >= 32 for c in value), 'control character in sealed registry field')
        return json.dumps(value, ensure_ascii=False)
    fields = [('identity', manifest['identity']), ('manifestPath', str(manifest_path)),
              ('manifestSHA', sha(manifest_path)), ('targetTriple', manifest['target_triple']),
              ('dataLayout', manifest['data_layout']), ('primitiveABI', manifest['primitive_abi']),
              ('exportABI', manifest['export_abi'])]
    lines = ['-- mlf:syntax shared-haskell-v1',
        '{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,',
        '             KindSignatures, FlexibleContexts, FlexibleInstances,',
        '             MultiParamTypeClasses, OverloadedStrings #-}',
        'module MLF.PreparedNativeData',
        '  (enabled, identity, manifestPath, manifestSHA, objectPaths,',
        '   targetTriple, dataLayout, primitiveABI, exportABI, reservedTypeNames) where {',
        '  import MLF.Primitive; import Bootstrap.Types;',
        '  enabled :: Bool; enabled = True;']
    for name, value in fields:
        lines += [f'  {name} :: String; {name} = {text(value)};']
    values = ', '.join('(,) ' + text(row['path']) + ' ' + text(row['sha256']) for row in manifest['objects'])
    lines += ['  reservedTypeNames :: [] String;', '  reservedTypeNames = [' + ', '.join(text(name) for name in manifest['reserved_type_names']) + '];']
    lines += ['  objectPaths :: [] ((,) String String);', '  objectPaths = [' + values + ']', '}']
    return ('\n'.join(lines) + '\n').encode()

def commands(root, job, request, generation, fresh):
    """Exact producer/Clang command contract, recomputed during verification."""
    native = job / 'native'
    work = native / ('fresh' if fresh else 'first')
    prior = {row['label']: row['argv'] for row in generation['commands']}
    result = {}
    for name in ['host', 'supervisor']:
        command = list(prior[name]); command[command.index('-o') + 1] = str(work / (name + '.o'))
        result[name] = command
    command = list(prior['build-generate-prepared-libraries'])
    command = [value.replace(str(root / 'tools/experimental/prepared-libraries/Generate.hs'),
                             str(root / 'tools/experimental/prepared-libraries/GenerateNative.hs'))
               .replace(str(job / 'build/host.o'), str(work / 'host.o'))
               .replace(str(job / 'build/supervisor.o'), str(work / 'supervisor.o')) for value in command]
    for flag in ['-odir', '-hidir']:
        command[command.index(flag) + 1] = str(work / 'objects')
    command[command.index('-o') + 1] = str(work / 'generate-native')
    command.insert(1, '-fforce-recomp')
    result['producer'] = command
    result['generate'] = [str(work / 'generate-native'), str(native / 'library.ll'), str(native / 'metadata.json')]
    clang = request['clang']['path']
    result['target'] = [clang, '-S', '-emit-llvm', '-x', 'c', '/dev/null', '-o', str(native / 'target.ll')]
    result['library'] = [clang, '-O2', '-Wno-override-module', '-c', str(native / 'library.ll'), '-o', str(native / 'library.o')]
    result['runtime'] = [clang, '-O2', '-std=c11', '-MD', '-MF', str(native / 'runtime.d'), '-c',
                         str(root / 'runtime/mlf_runtime.c'), *request['runtime_flags'], '-o', str(native / 'runtime.o')]
    return result

def producer_closure(root):
    sources = {row['module']: row['path'] for row in read(root / 'shared-sources.json')['modules']}
    pending = [root / 'tools/experimental/prepared-libraries/GenerateNative.hs']; found = {}
    while pending:
        path = pending.pop()
        if str(path) in found:
            continue
        found[str(path)] = sha(path)
        for name in re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)', path.read_text(), re.M):
            require(name != 'MLF.PreparedNativeData', 'native producer depends on generated native registry')
            if name == 'MLF.Primitive':
                continue
            require(name in sources, 'unregistered native producer dependency: ' + name)
            pending.append(root / sources[name])
    return found

def native_tool_inputs(clang):
    """Installation provenance only; per-user compilation does not rehash dylibs."""
    import sys
    pending, found = [Path(clang).resolve()], {}
    while pending:
        path = pending.pop()
        if str(path) in found:
            continue
        found[str(path)] = sha(path)
        if sys.platform == 'darwin':
            output = subprocess.check_output(['/usr/bin/otool', '-L', str(path)], text=True)
            names = re.findall(r'^\s+(\S+) \(compatibility version ', output, re.M)
            for name in names:
                if name.startswith(('/usr/lib/', '/System/Library/')):
                    continue  # Covered by final normal build's OS/dyld evidence.
                if name.startswith('@loader_path/'):
                    child = path.parent / name[len('@loader_path/'):]
                elif name.startswith('@rpath/'):
                    candidates = {p.resolve() for base in [Path(clang).parent.parent / 'lib', path.parent]
                                  for p in base.rglob(Path(name).name)}
                    require(len(candidates) == 1, 'ambiguous native tool rpath: ' + name)
                    child = next(iter(candidates))
                else:
                    child = Path(name)
                require(child.is_absolute() and child.is_file(), 'missing native tool dependency: ' + name)
                pending.append(child.resolve())
        else:
            result = subprocess.run(['ldd', str(path)], text=True, capture_output=True)
            require(result.returncode == 0, 'cannot identify native tool dependencies')
            for name in re.findall(r'(?:=>\s+)?(/[^\s]+)', result.stdout):
                pending.append(Path(name).resolve(strict=True))
    return found

def manifest_for(root, native, request):
    result = read(native / 'metadata.json')
    require(result['format'] == 'MLF-NATIVE-LIBRARY-1', 'metadata format')
    require(result['export_abi'] == 'mlf-native-typed-tuple/2', 'metadata ABI')
    require(result['identity'] == read(root.parent / 'request.json')['input_identity'], 'metadata input identity mismatch')
    target = (native / 'target.ll').read_text()
    require(('target triple = \"' + request['target_triple'] + '\"') in target and ('target datalayout = \"' + request['data_layout'] + '\"') in target, 'native target probe differs')
    ir = (native / 'library.ll').read_text()
    # LLVM output may omit target declarations; the exact Clang target defaults
    # are captured from a separately compiled empty C translation unit.
    result.update(target_triple=request['target_triple'], data_layout=request['data_layout'],
                  primitive_abi=read(root / 'shared-sources.json')['primitive_abi'],
                  source_roots=[read(root.parent / 'request.json')['source_root']],
                  clang=request['clang'], link_args=request['link_args'],
                  link_inputs=[{'path':str(Path(p).resolve()), 'sha256':sha(p)} for p in request['link_args'] if Path(p).is_absolute()],
                  objects=[{'path': str(native / name), 'sha256': sha(native / name)}
                           for name in ['library.o', 'runtime.o']])
    require('target triple =' not in ir or ('target triple = "' + request['target_triple'] + '"') in ir,
            'emitted target differs from installation')
    return result

def runtime_contract(manifest):
    """Small per-invocation contract, derived from the full checked metadata."""
    fields = ['format', 'identity', 'target_triple', 'data_layout', 'primitive_abi',
              'export_abi', 'objects', 'clang', 'link_args', 'link_inputs', 'source_roots', 'reserved_type_names']
    return {field: manifest[field] for field in fields}

def install(job, config):
    started = time.monotonic()
    root, native = job / 'sources', job / 'native'
    require(sha(root / DATA) == EMPTY_SHA256, 'producer source must have exact disabled native registry')
    native.mkdir(exist_ok=False)
    config = read(config)
    require(set(config) == {'clang', 'runtime_flags', 'link_args'}, 'config keys')
    clang = Path(shutil.which(config['clang']) or config['clang']).resolve(strict=True)
    for field in ['runtime_flags', 'link_args']:
        require(isinstance(config[field], list) and all(isinstance(x, str) for x in config[field]), 'argv array required')
    # Runtime flags are include/define switches only; never replace the input,
    # output, ordinary optimization pipeline, or inject an alternate program.
    require(all((x.startswith('-I') and Path(x[2:]).is_absolute()) or (x.startswith('-D') and len(x) > 2) for x in config['runtime_flags']), 'unsupported runtime flag')
    require(all(x == '-lm' or (Path(x).is_absolute() and Path(x).is_file()) for x in config['link_args']), 'unsupported link argument')
    config['link_args'] = [str(Path(x).resolve(strict=True)) if Path(x).is_absolute() else x for x in config['link_args']]
    target = subprocess.run([str(clang), '-S', '-emit-llvm', '-x', 'c', '-', '-o', '-'], input=b'', stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    target_text = target.stdout.decode()
    request = {**config, 'clang': {'path': str(clang), 'sha256': sha(clang)},
               'target_triple': re.search(r'target triple = "([^"]+)"', target_text).group(1),
               'data_layout': re.search(r'target datalayout = "([^"]+)"', target_text).group(1)}
    dump(native / 'request.json', request)
    (native / 'target.ll').write_bytes(target.stdout)
    generation = read(job / 'build/receipt.json')
    receipt = {'format': 'MLF-NATIVE-INSTALL-1', 'complete': False,
               'measurement_scope': 'installation only; concurrency not controlled; not a user-program benchmark',
               'request_sha256': sha(native / 'request.json'), 'source_inputs': producer_closure(root),
               'commands': [], 'first_outputs': {}, 'comparisons': [],
               'helper_sha256': sha(root / 'tools/shared/native_install.py')}
    inputs = {str(root / row['path']): sha(root / row['path']) for row in read(root / 'shared-sources.json')['modules']}
    inputs.update({str(p): sha(p) for p in (root / 'runtime').rglob('*') if p.is_file()})
    inputs.update(generation['tools']); inputs[str(clang)] = sha(clang)
    receipt['native_tool_inputs'] = native_tool_inputs(clang)
    receipt['inputs'] = inputs
    receipt['link_inputs'] = {str(Path(p).resolve()): sha(p) for p in request['link_args'] if Path(p).is_absolute()}
    def save(): dump(native / 'receipt.json', receipt)
    def run(label, argv):
        before = time.monotonic()
        with (native / (label + '.stdout')).open('wb') as out, (native / (label + '.stderr')).open('wb') as err:
            result = subprocess.run(argv, cwd=root, env={**os.environ, 'GHC_ENVIRONMENT':'-', 'GHCRTS':'', 'LC_ALL':'C.UTF-8'}, stdout=out, stderr=err)
        receipt['commands'].append({'label': label, 'argv': argv, 'exit_code': result.returncode, 'wall_seconds': time.monotonic() - before});save()
        require(result.returncode == 0, label + ' failed')
    save()
    try:
        for fresh in [False, True]:
            prefix = 'fresh' if fresh else 'first';work = native / prefix;(work / 'objects').mkdir(parents=True)
            for label, argv in commands(root, job, request, generation, fresh).items(): run(prefix + '-' + label, argv)
            import shlex
            dependency_text = (native / 'runtime.d').read_text().replace('\\\n', '')
            dependencies = {str((root / p).resolve()): sha(root / p) for p in shlex.split(dependency_text.split(':', 1)[1])}
            if fresh:
                require(dependencies == receipt['runtime_dependencies'], 'runtime dependencies changed during regeneration')
            else:
                receipt['runtime_dependencies'] = dependencies
            receipt[prefix + '_producer'] = {'path': str(work / 'generate-native'), 'sha256': sha(work / 'generate-native')}
            manifest = manifest_for(root, native, request);dump(native / 'manifest.json', manifest)
            dump(native / 'runtime-contract.json', runtime_contract(manifest))
            (native / 'PreparedNativeData.hs').write_bytes(registry(manifest, native / 'runtime-contract.json'))
            for name in ['library.ll','metadata.json','library.o','runtime.o','runtime.d','target.ll','manifest.json','runtime-contract.json','PreparedNativeData.hs']:
                path = native / name
                if not fresh:
                    backup = native / 'first' / name;shutil.copy2(path, backup);backup.chmod(0o444)
                    receipt['first_outputs'][str(path)] = {'path': str(backup), 'sha256': sha(path)}
                else:
                    saved = receipt['first_outputs'][str(path)]
                    require(path.read_bytes() == Path(saved['path']).read_bytes(), 'fresh regeneration differs: ' + name)
                    receipt['comparisons'].append({'path': str(path), 'sha256': sha(path), 'bytes_equal': True})
            save()
        require(all(sha(p) == h for p,h in receipt['native_tool_inputs'].items()), 'native toolchain changed during installation')
        require(all(sha(p) == h for p,h in receipt['link_inputs'].items()), 'link dependencies changed during installation')
        require(all(sha(p) == h for p,h in inputs.items()), 'inputs changed during installation')
        (root / DATA).write_bytes((native / 'PreparedNativeData.hs').read_bytes())
        receipt['canonical_sha256'] = sha(root / DATA);receipt['complete'] = True
    except BaseException as error:
        receipt['error'] = repr(error);raise
    finally:
        receipt['installation_wall_seconds'] = time.monotonic() - started
        save()
    verify(root)

def verify(root):
    root = Path(root).resolve();data = root / DATA
    if sha(data) == EMPTY_SHA256:
        return {'kind': 'empty', 'sha256': sha(data)}
    job, native = root.parent, root.parent / 'native'
    require(root == job / 'sources', 'enabled registry requires owned job')
    receipt = read(native / 'receipt.json');request = read(native / 'request.json')
    require(receipt['format'] == 'MLF-NATIVE-INSTALL-1' and receipt['complete'], 'incomplete receipt')
    require(receipt['helper_sha256'] == sha(root / 'tools/shared/native_install.py'), 'installer source changed')
    require(receipt['request_sha256'] == sha(native / 'request.json'), 'request changed')
    require(receipt['source_inputs'] == producer_closure(root), 'producer source closure changed')
    expected = {}
    for fresh in [False, True]:
        prefix = 'fresh' if fresh else 'first'
        expected.update({prefix + '-' + key: value for key,value in commands(root, job, request, read(job / 'build/receipt.json'), fresh).items()})
        producer = receipt[prefix + '_producer']
        require(producer['path'] == str(native / prefix / 'generate-native') and sha(producer['path']) == producer['sha256'], 'producer executable changed')
    rows = receipt['commands']; require(len(rows) == len(expected) and {r['label']:r['argv'] for r in rows} == expected and all(r['exit_code'] == 0 for r in rows), 'producer commands differ')
    outputs = {str(native / name) for name in ['library.ll','metadata.json','library.o','runtime.o','runtime.d','target.ll','manifest.json','runtime-contract.json','PreparedNativeData.hs']}
    require(set(receipt['first_outputs']) == outputs, 'output inventory mismatch')
    require(len(receipt['comparisons']) == len(outputs) and {r['path'] for r in receipt['comparisons']} == outputs, 'regeneration inventory mismatch')
    for path, record in receipt['first_outputs'].items():
        require(record['path'] == str(native / 'first' / Path(path).name), 'backup path mismatch')
        require(sha(path) == record['sha256'] == sha(record['path']) and Path(path).read_bytes() == Path(record['path']).read_bytes(), 'regenerated output changed')
    for row in receipt['comparisons']:
        require(row['bytes_equal'] and row['sha256'] == sha(row['path']), 'regeneration comparison mismatch')
    require(receipt['native_tool_inputs'] == native_tool_inputs(request['clang']['path']), 'native toolchain inventory changed')
    expected_inputs = {str(root / row['path']): sha(root / row['path']) for row in read(root / 'shared-sources.json')['modules']}
    expected_inputs[str(data)] = EMPTY_SHA256
    expected_inputs.update({str(p): sha(p) for p in (root / 'runtime').rglob('*') if p.is_file()})
    expected_inputs.update(read(job / 'build/receipt.json')['tools']);expected_inputs[request['clang']['path']] = request['clang']['sha256']
    require(receipt['inputs'] == expected_inputs, 'native source/tool input inventory mismatch')
    for path, digest in receipt['inputs'].items():
        if path != str(data): require(sha(path) == digest, 'input changed: ' + path)
    import shlex
    deps = shlex.split((native / 'runtime.d').read_text().replace('\\\n', '').split(':', 1)[1])
    require(set(receipt['runtime_dependencies']) == {str((root / p).resolve()) for p in deps}, 'runtime dependency inventory differs')
    require(set(receipt['link_inputs']) == {str(Path(p).resolve()) for p in request['link_args'] if Path(p).is_absolute()}, 'link dependency inventory differs')
    for field in ['runtime_dependencies','link_inputs']:
        require(receipt[field], 'missing native dependency inventory')
        for path,digest in receipt[field].items(): require(sha(path) == digest, 'native dependency changed: ' + path)
    manifest = manifest_for(root, native, request)
    require(manifest == read(native / 'manifest.json'), 'manifest differs from canonical inputs')
    require(read(native / 'runtime-contract.json') == runtime_contract(manifest), 'runtime contract differs from full manifest')
    require(data.read_bytes() == registry(manifest, native / 'runtime-contract.json') == (native / 'PreparedNativeData.hs').read_bytes(), 'sealed registry changed')
    require(receipt['canonical_sha256'] == sha(data), 'canonical registry digest mismatch')
    return {'kind':'installed', 'sha256':sha(data), 'receipt_sha256':sha(native / 'receipt.json'),
            'helper_sha256':sha(root / 'tools/shared/native_install.py')}

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--job',type=Path);p.add_argument('--config',type=Path);p.add_argument('--verify',type=Path);a=p.parse_args()
    if a.verify: print(json.dumps(verify(a.verify)))
    else: install(a.job.resolve(strict=True),a.config.resolve(strict=True))
