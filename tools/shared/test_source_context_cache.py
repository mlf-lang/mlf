#!/usr/bin/env python3
"""Compile production source-context controls against an authenticated producer.

Candidate harness: run only under the campaign's outer resource/tree guard.
Default CI inputs come from this checkout. Explicit --source-root/--fixture/
--controls permit local, pinned tests without patching module globals. They do
not excuse an old producer: authenticate_build checks the actual source root.
No producer source, interface, object, or executable is copied back or rewritten.
SourceSCC remains a separate full maintained item4 gate with its original flags.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import sys

ROOT = Path(__file__).resolve().parents[2]
BINARY_HELPER_NAMES = ('artifact_binary_reference.py', 'artifact_binary_typed.py',
                       'artifact_structure_contract.json')
EXPECTED_COMMANDS = ["helper", "raw-final"]
for _kind in ("query", "session"):
    EXPECTED_COMMANDS += [_kind + "-cold", _kind + "-warm"]
    if _kind == "query":
        EXPECTED_COMMANDS += ["query-install-legacy", "query-mixed-old-new"]
    EXPECTED_COMMANDS += [_kind + "-one-value-change", _kind + "-changed-warm"]
    EXPECTED_COMMANDS += [_kind + "-" + suffix for suffix in
                          ("missing-context", "corrupt-context", "corrupt-record")]

EXPECTED_COMMANDS += ["left-legacy", "lock-after-legacy", "left-source", "lock-after-source",
                      "left-session", "lock-after-session", "empty-stale-success",
                      "empty-directory-failure", "lock-after-empty-directory", "cleanup-dual-failure",
                      "lock-after-cleanup-dual", "concurrent-a", "concurrent-b"]

EXPECTED_COMMANDS += ["memo-helper", "memo-query", "memo-session"]

EXPECTED_COMMANDS += ["context-directory-setup", "context-directory-reject", "context-stage-cleanup-failure"]

EXPECTED_COMMANDS += ["decoder-differential"]

EXPECTED_COMMANDS += ["window-helper", "session-window-raw-final"]

def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def regular(path):
    path = Path(path).absolute()
    require(path.resolve(strict=True) == path and stat.S_ISREG(path.lstat().st_mode),
            'real regular input required: ' + str(path))
    return path


def load_actual(name, path, source):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'module loader missing')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(Path(module.__file__).resolve() == path and module.ROOT.resolve() == source,
            'loaded helper identity/root mismatch: ' + name)
    return module


def closed_tree(root):
    # Metadata is an additional mutation check; it never replaces body hashes.
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode),
                'producer contains nonregular/nondirectory entry: ' + str(path))
        result[str(path.relative_to(root))] = [s.st_dev, s.st_ino, s.st_mode,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_blocks]
    return result


def verify_control_receipt(path, binary, python, controls, inspector_hashes):
    receipt = json.loads(path.read_text())
    require(receipt.get('complete') is True and receipt.get('fixture_sha256') == sha(binary),
            'controls did not complete against this fixture')
    require(receipt.get('binary_inspector_inputs') == inspector_hashes,
            'controls did not use the pinned independent binary/typed inspectors')
    rows = receipt.get('commands', [])
    require([r.get('name') for r in rows] == EXPECTED_COMMANDS,
            'fixed original K38 plus window and actual Session PreparedRaw command inventory differs')
    require(set(receipt.get('drivers', {})) == {'query', 'session'}, 'both actual drivers required')
    for row in rows:
        require(row.get('state') == 'passed' and row.get('exit_code') == 0,
                'nonpassing inner command: ' + str(row.get('name')))
        argv = row.get('argv', [])
        if row['name'].startswith('lock-after-'):
            require(row.get('kind') == 'lock-probe' and argv[:5] ==
                    [str(python), '-I', '-B', str(controls), '--lock-probe'],
                    'independent lock probe interpreter/script identity changed')
        else:
            require(argv and argv[0] == str(binary), 'inner fixture identity changed')
        for label in ('stdout', 'stderr'):
            evidence = row[label]
            capture = regular(evidence['path'])
            require(capture.parent == path.parent and capture.name == row['name'] + '.' + label,
                    'capture outside exact controls output')
            require(capture.stat().st_size == evidence['bytes'] and sha(capture) == evidence['sha256'],
                    'inner capture changed')
        require(row['stderr']['bytes'] == 0, 'unexpected fixture stderr')
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--fixture', type=Path)
    parser.add_argument('--controls', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--controls-timeout', type=int, default=900,
                        help='One bound for the whole 40-command runner; not a guarantee of each per-command ceiling.')
    args = parser.parse_args()
    require(1 <= args.controls_timeout <= 1800, 'controls timeout outside 1..1800')
    source = args.source_root.absolute()
    require(source.resolve(strict=True) == source and source.is_dir(), 'real source root required')
    fixture = regular(args.fixture or source / 'tools/shared/fixtures/item4/SourceContextCache.hs')
    controls = regular(args.controls or source / 'tools/shared/run_context_controls.py')
    inspectors = [regular(controls.with_name(name)) for name in BINARY_HELPER_NAMES]
    inspector_hashes = {str(path): sha(path) for path in inspectors}
    receipt_path = regular(args.build_receipt)
    producer_dir = receipt_path.parent
    output = args.output.absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == output.parent,
            'fresh output under an existing real parent required')
    require(not source.is_relative_to(output), 'output must not equal or contain source root')
    if output.is_relative_to(source):
        build_area = source / '.mlf-build'
        require(output != build_area and output.is_relative_to(build_area),
                'in-checkout output must be a strict descendant of .mlf-build')
    require(not output.is_relative_to(producer_dir) and not producer_dir.is_relative_to(output),
            'output must be disjoint from the read-only producer')
    require(not fixture.is_relative_to(output) and not controls.is_relative_to(output) and
            all(not path.is_relative_to(output) for path in inspectors),
            'test source must be outside output')
    build_path = regular(source / 'tools/shared/build.py')
    direct_path = regular(source / 'tools/shared/test_direct.py')
    # Prevent loader cache files in the authenticated source tree.
    sys.dont_write_bytecode = True
    python = regular(Path(sys.executable).resolve(strict=True))
    witness = regular(source / 'tools/shared/fixtures/item4/SourceKeyWitness.hs')
    inputs = [regular(__file__), fixture, witness, controls, *inspectors, build_path, direct_path,
              regular(source / 'host/ghc/cbits/host.c'),
              regular(source / 'runtime/mlf_process_supervisor.c'),
              regular(source / 'runtime/mlf_byte_file.h'),
              python]
    input_hashes = {str(path): sha(path) for path in inputs}
    build = load_actual('source_context_actual_build', build_path, source)
    td = load_actual('source_context_actual_direct', direct_path, source)
    output.mkdir()
    record = {'format': 1, 'complete': False, 'commands': [],
              'mode': 'authenticated-production-source-context', 'source_root': str(source),
              'inputs': input_hashes, 'producer_receipt': str(receipt_path),
              'binary_inspector_inputs': inspector_hashes,
              'python_invocation': sys.executable, 'canonical_python': str(python),
              'producer_receipt_sha256': sha(receipt_path),
              'limits': {'compile_link_seconds_each': 120,
                         'whole_controls_seconds': args.controls_timeout,
                         'original_fixture_seconds_each': 180,
                         'added_fixture_seconds_each': 60, 'lock_probe_seconds': 5,
                         'ready_barrier_seconds': 10, 'pair_whole_seconds': 60,
                         'complete_cache_logical_and_allocated_cap_bytes': 16 * 1024**2,
                         'outer_resource_guard_required': True},
              'limitations': ['No standalone resource admission; use the original outer guard.',
                  'Per-command ceilings do not guarantee each command its full time under the outer bound.',
                  'SourceSCC and companion reviews require their separate original maintained gate.',
                  'Not a native, bootstrap, corpus-performance, or crash-durability qualification.']}

    def save():
        temp = output / 'receipt.json.new'
        temp.write_text(json.dumps(record, indent=2) + '\n')
        temp.replace(output / 'receipt.json')

    runner = td.CommandRunner(source, output, record, save)
    before, objects, artifacts = None, {}, {}

    def check_objects():
        # authenticate_build validates producer identity, but receipt-listed
        # files alone are not a closed interface search path. Reject stray .hi
        # and .o entries as well as missing listed files before GHC sees it.
        actual = {str(path.relative_to(producer_dir))
                  for path in (producer_dir / 'objects').rglob('*')
                  if path.suffix in {'.o', '.hi'}}
        expected_paths = {name for name in objects if Path(name).suffix in {'.o', '.hi'}}
        require(actual == expected_paths, 'producer object/interface path set differs from receipt')
        for name, expected in objects.items():
            relative = Path(name)
            require(not relative.is_absolute() and '..' not in relative.parts,
                    'unsafe producer object path')
            path = regular(producer_dir / relative)
            require(path.is_relative_to(producer_dir) and sha(path) == expected,
                    'producer object/interface changed: ' + name)

    def postcheck():
        td.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        require(sha(receipt_path) == record['producer_receipt_sha256'], 'producer receipt changed')
        check_objects()
        require(closed_tree(producer_dir) == before, 'producer path/stat closure changed')
        require(all(sha(path) == expected for path, expected in input_hashes.items()), 'test input changed')
        require(all(sha(path) == expected for path, expected in artifacts.items()), 'test build artifact changed')

    save()
    try:
        producer = td.authenticate_build(receipt_path, producer_dir / 'bin', root=source)
        objects = producer.get('object_inputs', {})
        require(objects, 'producer omitted object/interface inventory')
        check_objects()
        before = closed_tree(producer_dir)
        record.update(producer_optimization=producer['optimization'], object_inputs=objects,
                      producer_objects_verified_before=True, producer_closed_before=before)
        save()
        flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db', '-global-package-db',
                 '-no-user-package-db', '-hide-all-packages', '-O' + producer['optimization'],
                 *build.DEMAND_FLAGS]
        for package in build.PACKAGES:
            flags.extend(['-package', package])
        ghc, cc = producer['ghc']['path'], producer['cc']['path']
        main_object, main_interface = output / 'SourceContextCache.o', output / 'SourceContextCache.hi'
        witness_object = output / 'SourceKeyWitness.o'
        witness_interface = output / 'SourceKeyWitness.hi'
        runner.run('compile-key-witness', [ghc, '-c', *flags, *build.EXHAUSTIVENESS_FLAGS,
            '-i', '-i' + str(producer_dir / 'objects'), '-o', witness_object, '-ohi', witness_interface, witness], timeout=120)
        runner.run('compile-fixture', [ghc, '-c', *flags, *build.EXHAUSTIVENESS_FLAGS,
            '-i', '-i' + str(producer_dir / 'objects'), '-i' + str(output), '-o', main_object, '-ohi', main_interface, fixture], timeout=120)
        transport = []
        for name, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            obj = output / (name + '.o')
            runner.run('compile-' + name, [cc, '-O2', '-std=c11', '-I' + str(source / 'runtime'),
                       '-c', source / relative, '-o', obj], timeout=120)
            transport.append(obj)
        link_objects = [producer_dir / name for name in sorted(objects)
                        if name.endswith('.o') and name != 'objects/Main.o']
        require(link_objects, 'no authenticated linkable producer objects')
        binary = output / 'source-context-cache'
        runner.run('link-fixture', [ghc, *flags, '-rtsopts=ignoreAll', main_object, witness_object,
                   *link_objects, *transport, '-o', binary], timeout=120)
        artifacts.update({str(path): sha(path) for path in [binary, main_object, main_interface, witness_object, witness_interface, *transport]})
        record['artifacts'] = artifacts
        save()
        inner = output / 'controls'
        result = runner.run('source-context-controls', [python, '-I', '-B', controls,
                            '--fixture', binary, '--output', inner], timeout=args.controls_timeout)
        require(json.loads(result.stdout) == {'complete': True, 'commands': 40, 'drivers': ['query', 'session']},
                'controls completion summary differs')
        verify_control_receipt(inner / 'receipt.json', binary, python, controls, inspector_hashes)
        record['controls_receipt'] = {'path': str(inner / 'receipt.json'), 'sha256': sha(inner / 'receipt.json')}
        record['controls_commands'] = EXPECTED_COMMANDS
        postcheck()
        record.update(complete=True, producer_objects_verified_after=True, post_integrity=True)
    except BaseException as error:
        record.update(error=type(error).__name__ + ': ' + str(error), complete=False)
        # Always attempt the original read-only post-audit after target failure.
        if before is not None:
            try:
                postcheck()
                record['post_integrity'] = True
            except BaseException as audit_error:
                record['post_integrity'] = False
                record['post_integrity_error'] = type(audit_error).__name__ + ': ' + str(audit_error)
    finally:
        save()
    print(str(output / 'receipt.json') + ': ' + ('complete' if record['complete'] else 'failed'))
    if not record['complete']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
