#!/usr/bin/env python3
"""Authenticate, build and qualify binary artifacts on GHC and actual native.

Run under the maintained resource watchdog; this is not a resource admission
service. The original forty source-context controls remain a separate required
CI step. Source-root helpers are loaded from their actual paths, never rebound
to a different ROOT. No old installed library or native fixture is accepted.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
HELPERS = ('artifact_binary_reference.py', 'artifact_binary_cases.py',
           'artifact_binary_typed.py', 'artifact_binary_integration.py',
           'artifact_structure_contract.json', 'artifact_binary_golden.json')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def regular(path):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path and stat.S_ISREG(path.lstat().st_mode),
            'real regular input required: ' + str(path))
    return path


def executable(name):
    found = shutil.which(str(name))
    path = regular(Path(found or name).resolve(strict=True))
    require(os.access(path, os.X_OK), 'tool is not executable: ' + str(path))
    return path


def failure_sink(name):
    # Metadata only: never open a candidate path while deciding whether it is
    # the one explicitly authorized destructive-failure probe.
    require(sys.platform.startswith('linux') and name == '/dev/full',
            'only literal Linux /dev/full is authorized as a failure sink')
    path = Path(name)
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode) and stat.S_ISCHR(info.st_mode) and
            path.resolve(strict=True) == path, 'failure sink must be canonical non-symlink character device')
    return {'path': name, 'st_dev': info.st_dev, 'st_ino': info.st_ino,
            'st_rdev': info.st_rdev, 'st_mode': info.st_mode}


def load_actual(name, path, source):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'actual helper loader missing')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == path and module.ROOT.resolve() == source,
            'actual helper ROOT/identity mismatch: ' + name)
    return module


def closed_tree(root):
    rows = {}
    for path in [root, *sorted(root.rglob('*'))]:
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode),
                'nonregular producer entry: ' + str(path))
        rows[str(path.relative_to(root))] = [s.st_dev, s.st_ino, s.st_mode,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_blocks]
    return rows



def make_dependencies(data, target):
    """Parse one finite clang -M/-MD rule, not shell words or arbitrary make."""
    require(type(data) is bytes and 0 < len(data) <= 65536, 'dependency evidence size')
    require(target in ('artifact-gmp-header', 'artifact-native-runtime'), 'dependency target identity')
    text = data.decode('utf-8', errors='strict')
    require('\0' not in text and '\r' not in text, 'dependency control byte')
    text = text.replace('\\\n', '')
    require(text.endswith('\n') and '\n' not in text[:-1], 'one dependency rule required')
    prefix = target + ':'
    require(text.startswith(prefix), 'dependency target mismatch')
    body = text[len(prefix):-1]
    require(body and body[0] in ' \t', 'dependency target separator')
    words, word, index = [], [], 0
    while index < len(body):
        char = body[index]
        if char in ' \t':
            if word:
                words.append(''.join(word)); word = []
        elif char == '\\':
            index += 1
            require(index < len(body) and body[index] in ' \t#\\:', 'unresolved dependency escape')
            word.append(body[index])
        elif char == '$':
            index += 1
            require(index < len(body) and body[index] == '$', 'unresolved dependency variable')
            word.append('$')
        else:
            require(char not in ':#' and ord(char) >= 32, 'unexpected dependency syntax')
            word.append(char)
        index += 1
    if word:
        words.append(''.join(word))
    require(words and len(words) == len(set(words)), 'empty or duplicate dependency path')
    return words


def dependency_gmp_path(data, target, expected=None):
    paths = make_dependencies(data, target)
    matches = [name for name in paths if Path(name).name == 'gmp.h']
    require(len(matches) == 1, 'exactly one GMP header dependency required')
    name = matches[0]
    path = Path(name)
    require(path.is_absolute() and str(path) == name and '..' not in path.parts,
            'GMP dependency must be a canonical absolute path')
    require(expected is None or path == expected, 'runtime selected a different GMP header')
    return path


def dependency_parser_controls():
    # Independent literal expectations; these run inside the complete guarded
    # qualification, never as a separate compiler/native probe or fallback.
    target = 'artifact-gmp-header'
    positives = [
        ('plain', b'artifact-gmp-header: /src/probe.c /headers/gmp.h\n', '/headers/gmp.h'),
        ('continued', b'artifact-gmp-header: /src/probe.c \\\n /headers/gmp.h\n', '/headers/gmp.h'),
        ('escaped-space', b'artifact-gmp-header: /src/probe.c /headers/a\\ b/gmp.h\n', '/headers/a b/gmp.h'),
        ('escaped-hash', b'artifact-gmp-header: /src/probe.c /headers/a\\#b/gmp.h\n', '/headers/a#b/gmp.h'),
        ('escaped-dollar', b'artifact-gmp-header: /src/probe.c /headers/a$$b/gmp.h\n', '/headers/a$b/gmp.h')]
    negatives = [
        ('wrong-target', b'other: /headers/gmp.h\n', None),
        ('second-target', b'artifact-gmp-header: /headers/gmp.h\nother: /forged/gmp.h\n', None),
        ('empty', b'', None),
        ('oversize', b'x' * 65537, None),
        ('nul', b'artifact-gmp-header: /headers/\0gmp.h\n', None),
        ('invalid-utf8', b'artifact-gmp-header: /headers/\xff/gmp.h\n', None),
        ('unknown-escape', b'artifact-gmp-header: /headers/\\q/gmp.h\n', None),
        ('unexpanded-variable', b'artifact-gmp-header: /headers/$ROOT/gmp.h\n', None),
        ('unterminated-escape', b'artifact-gmp-header: /headers/gmp.h \\\n', None),
        ('duplicate', b'artifact-gmp-header: /headers/gmp.h /headers/gmp.h\n', None),
        ('two-headers', b'artifact-gmp-header: /headers/gmp.h /forged/gmp.h\n', None),
        ('missing-header', b'artifact-gmp-header: /src/probe.c\n', None),
        ('relative', b'artifact-gmp-header: headers/gmp.h\n', None),
        ('parent-traversal', b'artifact-gmp-header: /headers/../forged/gmp.h\n', None),
        ('noncanonical', b'artifact-gmp-header: /headers/./gmp.h\n', None),
        ('forged-runtime-header', b'artifact-gmp-header: /forged/gmp.h\n', Path('/headers/gmp.h'))]
    for name, data, wanted in positives:
        require(dependency_gmp_path(data, target) == Path(wanted), 'dependency positive: ' + name)
    for name, data, expected in negatives:
        try:
            dependency_gmp_path(data, target, expected)
        except ValueError:
            pass
        else:
            raise ValueError('dependency negative accepted: ' + name)
    return {'positive': [row[0] for row in positives], 'negative': [row[0] for row in negatives]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--shared-fixture', type=Path)
    parser.add_argument('--controls', type=Path)
    parser.add_argument('--clang', required=True)
    parser.add_argument('--gc-prefix', required=True, type=Path)
    parser.add_argument('--pkg-config', default='pkg-config')
    parser.add_argument('--partial-write-sink', required=True, help='Only literal Linux /dev/full; no substitute path.')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    sink_identity = failure_sink(args.partial_write_sink)
    sink = Path(args.partial_write_sink)
    source = args.source_root.absolute()
    require(source.resolve(strict=True) == source and source.is_dir(), 'real source root required')
    receipt_path = regular(args.build_receipt)
    producer_dir = receipt_path.parent
    fixture = regular(args.fixture or source / 'tools/shared/fixtures/item4/ArtifactBinary.hs')
    shared = regular(args.shared_fixture or source / 'tools/shared/fixtures/item4/RawBinaryShared.hs')
    controls = regular(args.controls or source / 'tools/shared/run_artifact_binary_controls.py')
    helpers = [regular(controls.with_name(name)) for name in HELPERS]
    build_path = regular(source / 'tools/shared/build.py')
    direct_path = regular(source / 'tools/shared/test_direct.py')
    clang, pkg_config = executable(args.clang), executable(args.pkg_config)
    gc = args.gc_prefix.absolute()
    require(gc.resolve(strict=True) == gc and gc.is_dir(), 'real selected GC prefix required')
    gc_archive = regular(gc / 'lib/libgc.a')
    gc_headers = [regular(p) for p in sorted((gc / 'include').rglob('*.h'))]
    require(gc_headers and gc / 'include/gc.h' in gc_headers, 'selected GC headers missing')
    output = args.output.absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == output.parent,
            'fresh output under existing real parent required')
    require(not source.is_relative_to(output), 'output contains source root')
    if output.is_relative_to(source):
        require(output != source / '.mlf-build' and output.is_relative_to(source / '.mlf-build'),
                'checkout output must be below .mlf-build')
    require(not output.is_relative_to(producer_dir) and not producer_dir.is_relative_to(output),
            'output overlaps read-only producer')
    sys.dont_write_bytecode = True
    python = regular(Path(sys.executable).resolve(strict=True))
    runtime = regular(source / 'runtime/mlf_runtime.c')
    transport_sources = [regular(source / 'host/ghc/cbits/host.c'),
                         regular(source / 'runtime/mlf_process_supervisor.c')]
    headers = [regular(p) for p in sorted((source / 'runtime').rglob('*.h'))]
    require(regular(source / 'runtime/mlf_byte_file.h') in headers,
            'new byte-file transport header missing')
    inputs = [regular(__file__), fixture, shared, controls, *helpers, build_path,
              direct_path, runtime, *transport_sources, *headers,
              python, clang, pkg_config, gc_archive, *gc_headers]
    require(all(not p.is_relative_to(output) for p in inputs), 'input inside output')
    inputs = {str(p): sha(p) for p in inputs}
    build = load_actual('artifact_binary_actual_build', build_path, source)
    td = load_actual('artifact_binary_actual_direct', direct_path, source)
    output.mkdir()
    record = {'format': 'MLF-ARTIFACT-BINARY-QUALIFICATION-1', 'complete': False,
              'commands': [], 'source_root': str(source), 'inputs': inputs,
              'partial_write_sink': sink_identity,
              'producer_receipt': str(receipt_path), 'producer_receipt_sha256': sha(receipt_path),
              'native_mode': 'fresh standalone LLVM and current runtime, no installed stdlib',
              'limits': {'compile_link_seconds_each': 120, 'native_frontend_seconds': 600,
                         'whole_controls_seconds': 900, 'fixture_seconds_each': 180,
                         'outer_original_resource_guard_required': True},
              'limitations': ['Native scope: raw bytes, wire, typed Graph/admission and public artifact pair.',
                  'Session/Distribution complete integration coverage is GHC, not native bundle qualification.',
                  'Original source-context forty remains an independent required gate.',
                  'No Windows, 32-bit, crash durability, or hermetic system-libc qualification.',
                  '128 MiB local native/test allocation is an estimate, not a fit claim; stop at original guard limits.']}

    def save():
        temporary = output / 'receipt.json.new'
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(output / 'receipt.json')

    runner = td.CommandRunner(source, output, record, save)
    before, objects, artifacts = None, {}, {}
    record['artifacts'] = artifacts

    def check_objects():
        actual = {str(p.relative_to(producer_dir)) for p in (producer_dir / 'objects').rglob('*')
                  if p.suffix in {'.o', '.hi'}}
        expected = {name for name in objects if Path(name).suffix in {'.o', '.hi'}}
        require(actual == expected, 'closed producer object/interface inventory differs')
        for name, digest in objects.items():
            rel = Path(name)
            require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe object path')
            p = regular(producer_dir / rel)
            require(p.is_relative_to(producer_dir) and sha(p) == digest, 'producer object changed: ' + name)

    def postcheck():
        try:
            sink_same = failure_sink(str(sink)) == sink_identity
        except (OSError, ValueError):
            sink_same = False
        record['post_sink_integrity'] = sink_same
        td.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        require(sha(receipt_path) == record['producer_receipt_sha256'], 'producer receipt changed')
        check_objects()
        require(closed_tree(producer_dir) == before, 'closed producer tree metadata changed')
        require(all(sha(p) == digest for p, digest in inputs.items()), 'qualification input changed')
        require(all(sha(p) == digest for p, digest in artifacts.items()), 'built fixture/runtime changed')
        require(sink_same, 'authorized failure sink metadata changed')

    save()
    try:
        record['dependency_parser_controls'] = dependency_parser_controls()
        producer = td.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        manifest = json.loads((source / 'shared-sources.json').read_text())
        require(manifest['primitive_abi'] == 'mlf-primitive-132-v7' and
                manifest['builtin_interface'] == 'mlf-primitive/shared-haskell-v1/11',
                'this finite suite requires the new byte-file/digest ABI')
        objects = producer.get('object_inputs', {})
        require(objects, 'producer object/interface inventory missing')
        check_objects(); before = closed_tree(producer_dir)
        record.update(producer_closed_before=before, object_inputs=objects,
                      producer_objects_verified_before=True, producer_optimization=producer['optimization'])
        save()
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O' + producer['optimization'],
                 *build.DEMAND_FLAGS]
        for package in build.PACKAGES:
            flags.extend(['-package', package])
        ghc, cc = producer['ghc']['path'], producer['cc']['path']
        transports = []
        for name, source_file in zip(('host', 'supervisor'), transport_sources):
            target = output / (name + '.o')
            runner.run('compile-' + name, [cc, '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                       '-c', source_file, '-o', target], timeout=120)
            transports.append(target)
        links = [producer_dir / name for name in sorted(objects)
                 if name.endswith('.o') and name != 'objects/Main.o']
        require(links, 'producer has no linkable library objects')
        binaries = {}
        for label, source_file in (('ghc', fixture), ('shared-ghc', shared)):
            directory = output / (label + '-build'); directory.mkdir()
            obj, hi, binary = directory / 'Main.o', directory / 'Main.hi', directory / 'fixture'
            runner.run('compile-' + label, [ghc, '-c', *flags, *build.EXHAUSTIVENESS_FLAGS,
                '-i', '-i' + str(producer_dir / 'objects'), '-o', obj, '-ohi', hi, source_file], timeout=120)
            runner.run('link-' + label, [ghc, *flags, '-rtsopts=ignoreAll', obj,
                       *links, *transports, '-o', binary], timeout=120)
            binaries[label] = binary
            artifacts.update({str(p): sha(p) for p in (obj, hi, binary)})
        # Qualify selected native dependencies from the actual pkg-config tool.
        # Use an explicit pinned GMP archive, not an ambient -lgmp resolution.
        runner.run('clang-version', [clang, '--version'], timeout=30)
        runner.run('pkg-config-version', [pkg_config, '--version'], timeout=30)
        def variable(name):
            result = runner.run('gmp-' + name, [pkg_config, '--variable=' + name, 'gmp'], timeout=30)
            value = result.stdout.decode().strip()
            require(value and '\0' not in value and '\n' not in value, 'invalid GMP directory')
            return Path(value).resolve(strict=True)
        gmp_libdir, gmp_incdir, gmp_pcdir = variable('libdir'), variable('includedir'), variable('pcfiledir')
        gmp_archive = regular((gmp_libdir / 'libgmp.a').resolve(strict=True))
        gmp_pc = regular((gmp_pcdir / 'gmp.pc').resolve(strict=True))
        cflags = shlex.split(runner.run('gmp-cflags', [pkg_config, '--cflags', 'gmp'], timeout=30).stdout.decode())
        require(cflags in ([], ['-I' + str(gmp_incdir)]),
                'GMP flags must name only the pinned canonical include directory')
        # Debian multiarch may legitimately put gmp.h below a compiler search
        # directory rather than pkg-config's nominal /usr/include. Ask the
        # selected real compiler once, without guessing a target triple.
        probe = output / 'gmp-header-probe.c'
        probe_bytes = b'#include <gmp.h>\n'
        with probe.open('xb') as stream:
            stream.write(probe_bytes)
        require(probe.read_bytes() == probe_bytes, 'GMP probe source identity')
        artifacts[str(probe)] = sha(probe)
        discovered = runner.run('gmp-header-dependencies', [clang, *cflags, '-I' + str(gmp_incdir),
            '-M', '-MT', 'artifact-gmp-header', '-x', 'c', probe], timeout=30)
        gmp_header = regular(dependency_gmp_path(discovered.stdout, 'artifact-gmp-header'))
        require(not gmp_header.is_relative_to(output), 'discovered GMP header overlaps output')
        probe_dependencies = regular(output / 'gmp-header-dependencies.stdout')
        require(probe_dependencies.read_bytes() == discovered.stdout, 'GMP dependency capture identity')
        artifacts[str(probe_dependencies)] = sha(probe_dependencies)
        for p in (gmp_archive, gmp_header, gmp_pc):
            require(not p.is_relative_to(output), 'native dependency overlaps output'); inputs[str(p)] = sha(p)
        record['gmp_header_resolution'] = {'header': str(gmp_header), 'sha256': inputs[str(gmp_header)],
            'pkgconfig_includedir': str(gmp_incdir),
            'probe': {'path': str(probe), 'bytes': len(probe_bytes), 'sha256': artifacts[str(probe)]},
            'probe_dependencies': {'path': str(probe_dependencies), 'bytes': len(discovered.stdout),
                                   'sha256': artifacts[str(probe_dependencies)]}}
        record['native_dependencies'] = {str(p): inputs[str(p)] for p in
            (clang, pkg_config, gc_archive, *gc_headers, gmp_archive, gmp_header, gmp_pc)}
        save(); check_objects()
        native_runtime = output / 'native-runtime.o'
        runtime_dependencies = output / 'native-runtime.d'
        common = ['-O2', '-std=c11', '-I' + str(gmp_header.parent), *cflags,
                  '-I' + str(gmp_incdir), '-I' + str(source / 'runtime'), '-I' + str(gc / 'include')]
        require(sha(gmp_header) == inputs[str(gmp_header)], 'GMP header changed before native compilation')
        runner.run('native-runtime', [clang, *common, '-MD', '-MF', runtime_dependencies,
            '-MT', 'artifact-native-runtime', '-c', runtime, '-o', native_runtime], timeout=120)
        require(regular(runtime_dependencies).stat().st_size <= 65536, 'runtime dependency evidence size')
        dependency_bytes = runtime_dependencies.read_bytes()
        used_header = regular(dependency_gmp_path(dependency_bytes, 'artifact-native-runtime', gmp_header))
        require(sha(used_header) == inputs[str(gmp_header)], 'GMP header changed during native compilation')
        artifacts[str(runtime_dependencies)] = sha(runtime_dependencies)
        artifacts[str(native_runtime)] = sha(native_runtime)
        record['gmp_header_resolution']['runtime_dependencies'] = {
            'path': str(runtime_dependencies), 'bytes': len(dependency_bytes),
            'sha256': artifacts[str(runtime_dependencies)]}
        save()
        compiler = regular(producer_dir / 'bin/emlf')
        native_includes = []
        for library in ('mlf-foundation', 'mlf-language-core', 'mlf-xmlf',
                        'mlf-frontend', 'mlf-inference', 'mlf-crates'):
            native_includes.extend(['-i', source / 'libraries' / library])
        runner.run('native-emit', [compiler, *native_includes, '--emit-llvm', shared], timeout=600)
        # Reuse the captured LLVM directly: do not duplicate a potentially large
        # IR file just to change its extension or move work outside the guard.
        ir = regular(output / 'native-emit.stdout')
        require(ir.stat().st_size > 0, 'empty native LLVM')
        native = output / 'shared-native'
        runner.run('native-link', [clang, '-O2', '-Wno-override-module', '-x', 'ir', ir,
                   '-x', 'none', native_runtime, gc_archive, gmp_archive,
                   '-lm', '-lpthread', '-ldl', '-o', native], timeout=120)
        binaries['shared-native'] = native
        artifacts.update({str(p): sha(p) for p in [*transports, native_runtime, ir, native]})
        record.update(artifacts=artifacts, fixtures={name: str(p) for name, p in binaries.items()})
        save(); postcheck()
        inner = output / 'controls'
        result = runner.run('artifact-binary-controls', [python, '-I', '-B', controls,
            '--fixture', binaries['ghc'], '--shared-ghc-fixture', binaries['shared-ghc'],
            '--shared-native-fixture', native, '--build-receipt', receipt_path,
            '--partial-write-sink', sink, '--output', inner], timeout=900)
        summary = json.loads(result.stdout)
        body = json.loads((inner / 'receipt.json').read_text())
        require(summary.get('complete') is True and body.get('complete') is True and
                body.get('state') == 'passed' and body.get('post_input_integrity') is True,
                'binary aggregate did not complete')
        require(body.get('post_sink_integrity') is True and body.get('partial_write_sink') == sink_identity,
                'aggregate failure sink identity/post-audit mismatch')
        require(summary['commands'] == len(body['commands']) and
                summary['reference_cases'] == len(body['reference_cases']), 'aggregate count summary mismatch')
        required = {'wire-corpus', 'constructors', 'typed-bounds', 'raw-ghc', 'partial-write-ghc',
                    'shared-ghc', 'shared-native', 'shared-ghc-typed', 'shared-native-typed',
                    'shared-ghc-public-pair', 'shared-native-public-pair', 'distribution-seed'}
        names = [row['name'] for row in body['commands']]
        require(len(names) == len(set(names)) and required <= set(names), 'mandatory host/typed/public commands omitted')
        expected_inputs = {str(p): sha(p) for p in [controls, receipt_path, *binaries.values(), *helpers]}
        require(body['inputs'] == expected_inputs, 'aggregate input identity mismatch')
        for row in body['commands']:
            require(row['state'] == 'passed' and row['argv'][0] in {str(p) for p in binaries.values()},
                    'nonpassing or unqualified inner fixture')
            for stream in ('stdout', 'stderr'):
                item = row[stream]; path = regular(item['path'])
                require(path == inner / (row['name'] + '.' + stream) and
                        path.stat().st_size == item['bytes'] and sha(path) == item['sha256'],
                        'inner capture identity mismatch')
        require(set(body['shared_backend_outputs']) == {'shared-ghc', 'shared-native'} and
                set(body['shared_public_pairs']) == {'shared-ghc', 'shared-native'},
                'both actual hosts must qualify raw and full public artifacts')
        postcheck()
        record.update(complete=True, post_integrity=True, producer_objects_verified_after=True,
                      controls_receipt={'path': str(inner / 'receipt.json'), 'sha256': sha(inner / 'receipt.json')},
                      controls_commands=names)
    except BaseException as error:
        record.update(complete=False, error=type(error).__name__ + ': ' + str(error))
        if before is not None:
            try:
                postcheck(); record['post_integrity'] = True
            except BaseException as audit_error:
                record.update(post_integrity=False, post_integrity_error=type(audit_error).__name__ + ': ' + str(audit_error))
    finally:
        save()
    print(str(output / 'receipt.json') + ': ' + ('complete' if record['complete'] else 'failed'))
    if not record['complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
