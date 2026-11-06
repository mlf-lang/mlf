#!/usr/bin/env python3
"""Collect actual generator stdout after the specific stale-source builtin gate.

This diagnostic never repairs source, updates a build receipt, or qualifies a
toolchain. Its producer is an INCOMPLETE build. Hashes authenticate local build
evidence, not a third-party signature or a sandbox against a malicious producer.
The original failed verification, logs, and build receipt remain untouched.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
import types

FORMAT = 'builtin-generation-evidence-v1'
STALE = b'prepared Prelude build source identity is stale\n'
MAX_LITERAL = 8 * 1024 * 1024
MAX_STDERR = 64 * 1024
MAX_JSON = 16 * 1024 * 1024
MAX_RECEIPT = 4 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]
HOST_MODULES = {'MLF.Primitive': 'host/ghc/MLF/Primitive.hs',
                'MLF.Host.Base': 'host/ghc/MLF/Host/Base.hs',
                'MLF.Host.Async': 'host/ghc/MLF/Host/Async.hs',
                'MLF.Host.IO': 'host/ghc/MLF/Host/IO.hs'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_source(path):
    """Load source bytes, never bytecode."""
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def read_json(path):
    require(path.stat().st_size <= MAX_JSON, 'oversized receipt or manifest')
    def unique(rows):
        result = {}
        for key, value in rows:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def canonical(path, must_exist=True):
    path = Path(os.path.abspath(path))
    require(path.resolve(strict=must_exist) == path, 'symlink or noncanonical path: ' + str(path))
    return path


def bounded_timeout(timeout, upper):
    return type(timeout) in (int, float) and math.isfinite(timeout) and 0 < timeout <= upper


def authenticate_failure(verifier, snapshot, path):
    """Accept only an unchanged current-source, exit-1 stale-identity failure."""
    reference = verifier.identified(path)
    verifier.verify_file(reference, path)
    record = read_json(path)
    require(record.get('format') == verifier.FORMAT and record.get('complete') is False,
            'failed builtin verification receipt required')
    require(record.get('immutable_inputs_verified_after') is True and
            record.get('source_files_rewritten') is False and
            record.get('toolchain_qualification') is False and
            not record.get('candidate_verified') and not record.get('exact_regeneration') and
            'input_error' not in record,
            'failed builtin verification has invalid input evidence')
    require(record.get('error') == 'ValueError: builtin verification command failed: check-candidate',
            'unexpected original builtin verification failure')
    for key, value in snapshot.items():
        require(record.get(key) == value, 'failed builtin snapshot mismatch: ' + key)
    verifier.verify_inputs(snapshot['inputs'])
    rows = record.get('commands')
    require(isinstance(rows, list) and len(rows) == 1, 'failed verification must contain only check-candidate')
    row = rows[0]
    label, argv = verifier.commands(snapshot)[0]
    require(row.get('label') == label and row.get('argv') == argv and
            row.get('cwd') == snapshot['source_root'] and type(row.get('exit_code')) is int and
            row['exit_code'] == 1 and row.get('input_pins_verified_before') is True and
            row.get('input_pins_verified_after') is True and bounded_timeout(row.get('timeout_seconds'), 7200),
            'invalid failed check-candidate command evidence')
    stdout = verifier.verify_file(row.get('stdout'), path.parent / 'check-candidate.stdout')
    stderr = verifier.verify_file(row.get('stderr'), path.parent / 'check-candidate.stderr')
    require(stdout.stat().st_size == 0 and stderr.stat().st_size == len(STALE) and stderr.read_bytes() == STALE,
            'failure is not the exact stale-source builtin diagnostic')
    verifier.verify_file(reference, path)
    return {'receipt': reference, 'error': record['error'], 'stdout': row['stdout'], 'stderr': row['stderr']}


def build_commands(builder, root, build, manifest, receipt):
    """Reconstruct current build.py commands; never execute receipt argv."""
    ghc, cc = receipt['ghc']['path'], receipt['cc']['path']
    flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
             '-no-user-package-db', '-hide-all-packages', '-O' + receipt['optimization'],
             *builder.DEMAND_FLAGS, '-i',
             *['-i' + str((root / value).resolve()) for value in manifest['source_roots']],
             '-odir', str(build / 'objects'), '-hidir', str(build / 'objects')]
    for package in builder.PACKAGES:
        flags += ['-package', package]
    require(receipt.get('flags') == flags, 'build flags differ from current build driver')
    shared = [str(root / row['path']) for row in manifest['modules']]
    rows = [('shared-compile', [ghc, '--make', '-j1', '-fforce-recomp', '-v', '-ddump-types',
                              '-no-link', *builder.EXHAUSTIVENESS_FLAGS, *flags, *shared])]
    objects = []
    for label, source in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        obj = str(build / (label + '.o'))
        rows.append(('c-' + label, [cc, '-O2', '-std=c11', '-I' + str(root / 'runtime'),
                                    '-c', str(root / source), '-o', obj]))
        objects.append(obj)
    for row in manifest['executables']:
        rows.append(('link-' + row['name'], [ghc, '--make', '-j1', *flags, *builder.LINK_FLAGS,
                     str(root / row['wrapper']), *objects, '-o', str(build / 'bin' / row['name'])]))
    emlf = str(build / 'bin/emlf')
    rows += [('shared-profile', [emlf, '--check-shared', *shared]),
             ('implementation-identity', [emlf, '--implementation-identity'])]
    return rows


def authenticate_build(verifier, root, path, snapshot):
    reference = verifier.identified(path)
    verifier.verify_file(reference, path)
    receipt = read_json(path)
    build = path.parent
    require(receipt.get('format') == 1 and receipt.get('complete') is False and
            receipt.get('typecheck_only') is False and receipt.get('producer_host') == 'GHC' and
            receipt.get('implementation_language') == 'MLF/shared-haskell-v1' and
            receipt.get('builtin_verification', 'missing') is None and receipt.get('optimization') in ('0', '2'),
            'incomplete GHC runtime build before builtin verification required')
    pins = {}
    def pin(item, expected=None):
        file = verifier.verify_file(item, expected)
        if expected is not None and Path(expected).is_relative_to(root):
            require(file == Path(expected), 'checkout input follows a symlink: ' + str(expected))
        digest = item['sha256']
        require(str(file) not in pins or pins[str(file)] == digest, 'conflicting input pins')
        pins[str(file)] = digest
        return file
    def inventory(name, expected):
        actual = receipt.get(name)
        require(isinstance(actual, dict) and set(actual) == set(expected), 'build inventory differs: ' + name)
        for key, expected_path in expected.items():
            pin(actual[key], expected_path)
        return actual
    driver = pin(receipt.get('build_driver'), root / 'tools/shared/build.py')
    pin(receipt.get('orchestrator'), sys.executable)
    require(receipt['orchestrator'].get('version') == sys.version, 'build Python version changed')
    pin(receipt.get('cabal_manifest'), root / 'mlf-shared.cabal')
    builder = load_source(driver)
    require(builder.ROOT == root, 'build driver source root differs')
    manifest = builder.load_manifest()
    require(receipt.get('manifest_sha256') == verifier.sha(root / 'shared-sources.json'), 'build manifest changed')
    for key in ('source_syntax', 'primitive_abi', 'builtin_interface', 'frontend_semantics'):
        require(receipt.get(key) == manifest.get(key), 'build semantic manifest differs: ' + key)
    expected_shared = {row['module']: root / row['path'] for row in manifest['modules']}
    shared = inventory('shared_inputs', expected_shared)
    for row in manifest['modules']:
        expected = {**row, **verifier.identified(root / row['path'])}
        require(shared[row['module']] == expected, 'shared source metadata differs: ' + row['module'])
    inventory('resolved_modules', expected_shared)
    expected_host = {name: root / relative for name, relative in HOST_MODULES.items()}
    inventory('resolved_host_modules', expected_host)
    inventory('configuration_inputs', {str(p.relative_to(root)): p for p in verifier.configuration_paths(root)})
    host_paths = [*sorted((root / 'host/ghc').rglob('*.hs')), *sorted((root / 'host/ghc').rglob('*.c')),
                  root / 'runtime/mlf_process_supervisor.c', *sorted((root / 'runtime').glob('*.h'))]
    inventory('host_inputs', {str(p.relative_to(root)): p for p in host_paths})
    inventory('builtin_verification_helpers', {p: root / p for p in verifier.HELPERS})
    prepared_path = pin(receipt.get('prepared_verification_helper'), root / 'tools/shared/verify_prepared_libraries.py')
    prepared = load_source(prepared_path)
    # Owned prepared jobs use a different provenance contract.
    require(receipt.get('prepared_verification', {}).get('kind') == 'empty', 'prepared source jobs are outside this diagnostic')
    native_helper = root / 'tools/shared/native_install.py'
    if native_helper.exists():
        pin(verifier.identified(native_helper), native_helper)
    prepared.authenticate(receipt['prepared_verification'], root)
    ghc = pin(receipt.get('ghc'))
    cc = pin(receipt.get('cc'))
    require(receipt['ghc'].get('version') == builder.GHC_VERSION, 'build GHC version differs')
    settings = pin(receipt.get('ghc_settings'))
    require(settings.name == 'settings', 'unexpected GHC settings path')
    for name, field in [('packages.txt', 'package_database_sha256'), ('ghc-info.txt', 'ghc_info_sha256')]:
        pin({'path': str(build / name), 'sha256': receipt.get(field)}, build / name)
    toolchain = receipt.get('toolchain', {})
    actual_ghc = pin(toolchain.get('actual_ghc'))
    require(actual_ghc.name == 'ghc-' + builder.GHC_VERSION and
            actual_ghc == (settings.parent.parent / 'bin' / actual_ghc.name).resolve(),
            'actual GHC location differs from settings')
    for field in ('toolchain', 'installed_dependencies'):
        files = receipt.get(field, {}).get('files')
        require(isinstance(files, dict) and bool(files), 'missing recorded ' + field + ' input pins')
        for name, digest in files.items():
            pin({'path': name, 'sha256': digest})
    require({str(ghc), str(cc), str(actual_ghc)} <= set(toolchain['files']), 'toolchain omitted its producer binaries')
    require(builder.package_inputs((build / 'packages.txt').read_text(), builder.PACKAGES) == receipt['installed_dependencies'],
            'installed dependency inventory differs')
    outputs = inventory('outputs', {row['name']: build / 'bin' / row['name'] for row in manifest['executables']})
    require(outputs.get('emlf') == snapshot['compiler'] and outputs.get('builtin-prelude') == snapshot['generator'],
            'failed snapshot producer differs from build outputs')
    rows, expected_commands = receipt.get('commands'), build_commands(builder, root, build, manifest, receipt)
    require(isinstance(rows, list) and len(rows) == len(expected_commands), 'build command inventory differs')
    logs = {}
    for row, (label, argv) in zip(rows, expected_commands):
        log = build / (label + '.log')
        require(row.get('argv') == argv and row.get('cwd') == str(root) and
                type(row.get('exit_code')) is int and row['exit_code'] == 0 and row.get('log') == str(log),
                'build command evidence differs: ' + label)
        pin({'path': row['log'], 'sha256': row.get('log_sha256')}, log)
        logs[label] = log
    compile_log = logs['shared-compile'].read_text()
    expected_resolution = {**expected_shared, **expected_host}
    seen = set()
    for name, source in re.findall(r'Compiling\s+([\w.]+)\s+\(\s*([^,\n]+),', compile_log):
        require(name in expected_resolution and name not in seen, 'unexpected or duplicate compiled module')
        resolved = Path(source.strip())
        if not resolved.is_absolute():
            resolved = root / resolved
        require(resolved.resolve() == expected_resolution[name].resolve(), 'compiled source path differs: ' + name)
        seen.add(name)
    require(seen == set(expected_resolution), 'compile log omitted source modules')
    require(builder.audit_inferred_interfaces(compile_log, shared) == receipt.get('inferred_shared_interfaces'),
            'inferred shared interfaces differ from successful compile log')
    banner = 'MLF/shared-haskell-v1 GHC'
    require(logs['implementation-identity'].read_text().strip() == banner and
            receipt.get('implementation_identity', banner) == banner,
            'implementation identity command banner differs')
    # build.py has not saved implementation_identity when verification fails.
    pin(reference, path)
    return reference, receipt['optimization'], pins


def authenticate(root, build_receipt):
    root, build_receipt = canonical(root), canonical(build_receipt)
    require(build_receipt == root / '.mlf-build/shared-ghc/receipt.json',
            'diagnostic requires the canonical CI shared-ghc build receipt')
    verifier_path = canonical(root / 'tools/shared/verify_builtin_prelude.py')
    verifier = load_source(verifier_path)
    compiler = canonical(build_receipt.parent / 'bin/emlf')
    generator = canonical(build_receipt.parent / 'bin/builtin-prelude')
    canonical(root / 'tools/shared/builtin_prelude_identity.py')
    snapshot = verifier.input_snapshot(root, compiler, generator)
    failure = authenticate_failure(verifier, snapshot, canonical(build_receipt.parent / 'builtin-verification/receipt.json'))
    original, optimization, pins = authenticate_build(verifier, root, build_receipt, snapshot)
    for item in [original, failure['receipt'], failure['stdout'], failure['stderr'],
                 verifier.identified(__file__)]:
        pins[item['path']] = item['sha256']
    for path, digest in snapshot['inputs'].items():
        require(path not in pins or pins[path] == digest, 'conflicting snapshot and build input pins')
        pins[path] = digest
    verifier.verify_inputs(pins)
    return verifier, {'snapshot': snapshot, 'original_build_receipt': original,
                      'original_failure': failure, 'optimization': optimization, 'inputs': pins}


def open_new(path):
    canonical(path.parent)
    # O_EXCL also rejects dangling symlinks.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    return os.fdopen(fd, 'wb')


def run_generator(verifier, argv, root, output, timeout, entry):
    """Drain bounded pipes, retaining partial output on every command failure."""
    stdout_path, stderr_path = output / 'fresh-literal.stdout', output / 'fresh-literal.stderr'
    process = None
    try:
        with open_new(stdout_path) as stdout, open_new(stderr_path) as stderr:
            process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
                env={**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8'})
            deadline = time.monotonic() + timeout
            try:
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ, (stdout, MAX_LITERAL))
                    selector.register(process.stderr, selectors.EVENT_READ, (stderr, MAX_STDERR))
                    while selector.get_map():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(argv, timeout)
                        for key, _ in selector.select(min(remaining, 0.25)):
                            chunk = os.read(key.fileobj.fileno(), 65536)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            stream, limit = key.data
                            available = max(0, limit - stream.tell())
                            stream.write(chunk[:available])
                            require(len(chunk) <= available, 'generator output exceeded byte limit')
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(argv, timeout)
                    process.wait(timeout=remaining)
            except BaseException:
                verifier.stop(process)
                raise
            finally:
                process.stdout.close()
                process.stderr.close()
    finally:
        entry['exit_code'] = None if process is None else process.returncode
        for label, path in [('stdout', stdout_path), ('stderr', stderr_path)]:
            if path.exists():
                canonical(path)
                entry[label] = {**verifier.identified(path), 'bytes': path.stat().st_size}


def identity_delta(canonical_bytes, fresh, source_identity):
    """A small reconstruction hint, issued ONLY after real full-byte equality."""
    result = {'identity_only': False, 'canonical_sha256': hashlib.sha256(canonical_bytes).hexdigest(),
              'generated_sha256': hashlib.sha256(fresh).hexdigest(),
              'canonical_bytes': len(canonical_bytes), 'generated_bytes': len(fresh)}
    matches = list(re.finditer(rb'builtin-source-v1:([0-9a-f]{64})', canonical_bytes))
    encoded = source_identity.encode('ascii')
    if len(matches) == 1 and re.fullmatch(rb'builtin-source-v1:[0-9a-f]{64}', encoded):
        match = matches[0]
        replaced = canonical_bytes[:match.start()] + encoded + canonical_bytes[match.end():]
        if fresh == replaced and match.group() != encoded:
            result.update(identity_only=True, offset=match.start(1), length=64,
                          old_identity=match.group(1).decode('ascii'), new_identity=encoded[-64:].decode('ascii'))
    return result


def generate(root, build_receipt, output, timeout=600):
    require(bounded_timeout(timeout, 1800), 'generator timeout must be finite and at most 1800 seconds')
    root, build_receipt = canonical(root), canonical(build_receipt)
    output = canonical(output, must_exist=False)
    build = build_receipt.parent
    require(build_receipt == root / '.mlf-build/shared-ghc/receipt.json',
            'diagnostic requires the canonical CI shared-ghc build receipt')
    require(output == root / '.mlf-build/builtin-generation-guard/results',
            'diagnostic requires the separate canonical CI evidence directory')
    canonical(output.parent)
    # A fresh directory prevents stale success, file replacement, or evidence loss.
    output.mkdir(exist_ok=False)
    receipt_path = output / 'receipt.json'
    receipt = {'format': FORMAT, 'complete': False, 'generation_only': True,
               'toolchain_qualification': False, 'source_files_rewritten': False,
               'original_build_complete': False, 'producer_build_complete': False,
               'candidate_verified': False, 'scope': 'actual generator evidence from an incomplete GHC runtime build',
               'source_root': str(root), 'commands': []}
    verifier, evidence = None, None
    # Saves retain the original descriptor, never following a replaced symlink.
    with open_new(receipt_path) as receipt_stream:
        def save():
            canonical(output)
            require(not receipt_path.is_symlink() and receipt_path.stat().st_ino == os.fstat(receipt_stream.fileno()).st_ino,
                    'diagnostic receipt was replaced')
            data = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
            require(len(data) <= MAX_RECEIPT, 'diagnostic receipt exceeds byte limit')
            receipt_stream.seek(0)
            receipt_stream.write(data)
            receipt_stream.truncate()
            receipt_stream.flush()
        save()
        try:
            verifier, evidence = authenticate(root, build_receipt)
            snapshot = evidence['snapshot']
            receipt.update(evidence)
            receipt['source_identity'] = snapshot['source_identity']
            receipt['diagnostic_driver'] = verifier.identified(__file__)
            require(not any(Path(path).is_relative_to(output) for path in evidence['inputs']),
                    'output overlaps an authenticated input')
            verifier.verify_inputs(evidence['inputs'])
            argv = [str(build / 'bin/builtin-prelude'), snapshot['source_identity']]
            entry = {'label': 'fresh-literal', 'argv': argv, 'cwd': str(root),
                     'timeout_seconds': timeout, 'input_pins_verified_before': True,
                     'stdout_limit_bytes': MAX_LITERAL, 'stderr_limit_bytes': MAX_STDERR}
            receipt['commands'].append(entry)
            save()
            run_generator(verifier, argv, root, output, timeout, entry)
            verifier.verify_inputs(evidence['inputs'])
            entry['input_pins_verified_after'] = True
            require(entry['exit_code'] == 0, 'fresh generator exited unsuccessfully')
            require(entry['stderr']['bytes'] == 0, 'fresh generator wrote stderr')
            require(0 < entry['stdout']['bytes'] <= MAX_LITERAL, 'fresh generator output must be nonempty and bounded')
            stdout = verifier.verify_file(entry['stdout'], output / 'fresh-literal.stdout')
            fresh = stdout.read_bytes()
            require(fresh.startswith(b'-- mlf:syntax shared-haskell-v1\n') and
                    b'module MLF.BuiltinPreludeData ' in fresh and
                    snapshot['source_identity'].encode('ascii') in fresh,
                    'fresh output is not a current-source builtin literal')
            receipt['comparison'] = identity_delta(Path(snapshot['canonical']['path']).read_bytes(), fresh,
                                                    snapshot['source_identity'])
            _, after = authenticate(root, build_receipt)
            require(after == evidence, 'authenticated input inventory changed during generation')
            verifier.verify_file(entry['stderr'], output / 'fresh-literal.stderr')
            verifier.verify_file(entry['stdout'], output / 'fresh-literal.stdout')
            receipt.update(complete=True, generation_succeeded=True)
        except BaseException as error:
            receipt.update(complete=False, error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            try:
                if evidence is not None:
                    verifier.verify_inputs(evidence['inputs'])
                    receipt['immutable_inputs_verified_after'] = True
            except BaseException as error:
                receipt.update(complete=False, immutable_inputs_verified_after=False,
                               input_error=type(error).__name__ + ': ' + str(error))
                raise
            finally:
                save()
    return receipt_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    path = generate(args.root, args.build_receipt, args.output, args.timeout)
    receipt = read_json(path)
    print(json.dumps({'receipt': str(path), 'generation_only': True, 'toolchain_qualification': False,
                      'source_identity': receipt['source_identity'], **receipt['comparison']}, sort_keys=True))


if __name__ == '__main__':
    main()
