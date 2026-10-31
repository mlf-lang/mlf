#!/usr/bin/env python3
"""Finite F1 semantics and actual-source rule proof, bound to the current O2 build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RULES = ('mlf/fingerprintIntStep/65599', 'mlf/fingerprintIntStep/131')
PACKAGES = ('base', 'array', 'bytestring', 'text', 'containers', 'directory')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def hashes(root):
    paths = sorted(root.rglob('*'))
    require(not any(p.is_symlink() for p in paths), 'symlink in input/output inventory')
    return {str(p.relative_to(root)): sha(p) for p in paths if p.is_file()}


def rule_counts(text):
    return {name: text.count('Rule: ' + name + '\n') for name in RULES}


def verify_probe_counts(counts, optimization):
    require(optimization in ('0', '2'), 'unsupported probe optimization')
    expected = 2 if optimization == '2' else 0
    require(counts == dict.fromkeys(RULES, expected), 'unexpected literal public-probe rule firings')


def verify_unmatched_core(text):
    # GHC 9.14.1's top-level RHS blocks, not names/constants elsewhere in the dump.
    for name in ('unmatchedMultiplier', 'unmatchedModulus'):
        blocks = [block for block in text.split('-- RHS size:')
                  if re.search(r'^' + name + r' ::', block, re.M)]
        require(len(blocks) == 1, 'missing/ambiguous unmatched Core function: ' + name)
        block = blocks[0]
        require(all(token in block for token in ('integerMul', 'integerAdd', 'integerRem')),
                'unmatched expression lost ordinary Integer operations: ' + name)
        require('Int64' not in block and 'fingerprintIntStep' not in block,
                'unmatched expression narrowed/fused: ' + name)


def verify_resolution(text, expected):
    rows = re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*(.+?),', text, re.M)
    require(len(rows) == len(expected) and len({name for name, _ in rows}) == len(rows),
            'unexpected/duplicate compiled module inventory')
    require({name: str(Path(path).resolve()) for name, path in rows} ==
            {name: str(Path(path).resolve()) for name, path in expected.items()},
            'compiler resolved a different control/production source')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    producer, out = args.producer.resolve(strict=True), args.output.resolve()
    require(not out.exists() and not out.is_relative_to(producer) and
            not producer.is_relative_to(out) and not ROOT.is_relative_to(out),
            'fresh output separate from producer/source required')
    auth_path = ROOT / 'tools/shared/test_direct.py'
    auth = types.ModuleType('integrated_f1_authentication')
    auth.__file__ = str(auth_path)
    exec(compile(auth_path.read_bytes(), str(auth_path), 'exec'), auth.__dict__)
    build = auth.authenticate_build(producer / 'receipt.json', producer / 'bin', root=ROOT)
    require(build['optimization'] == '2', 'current complete O2 producer required')
    inventory_path = HERE / 'controls/CONTROL-INVENTORY.json'
    inventory = json.loads(inventory_path.read_text())
    require(set(inventory['source_files']) == {'Oracle.hs', 'Tests.hs', 'Probe.hs'},
            'exact frozen control inventory required')
    for name, digest in inventory['source_files'].items():
        require(sha(HERE / 'controls' / name) == digest, 'frozen control changed: ' + name)
    inputs = {str(p): sha(p) for p in [Path(__file__), auth_path, inventory_path,
              *(HERE / 'controls' / name for name in inventory['source_files']),
              producer / 'receipt.json']}
    host_hashes = hashes(ROOT / 'host/ghc')
    object_hashes = hashes(producer / 'objects')
    require(object_hashes, 'missing complete producer objects')
    require({'objects/' + path: digest for path, digest in object_hashes.items()} ==
            build.get('object_inputs'), 'producer objects differ from authenticated receipt')
    for item in build['host_inputs'].values():
        inputs[item['path']] = item['sha256']
    env = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
           'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1'}
    out.mkdir(parents=True)
    record = {'format': 'integrated-fingerprint-fusion-controls-v1', 'complete': False,
              'performance_measured': False, 'native_bootstrap_executed': False,
              'producer_receipt_sha256': sha(producer / 'receipt.json'),
              'inputs': inputs, 'host_source_hashes': host_hashes,
              'producer_object_hashes': object_hashes, 'commands': [], 'runs': [],
              'inventory': inventory}

    def save():
        (out / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')

    def run(label, command, cwd=ROOT):
        item = {'label': label, 'argv': list(map(str, command)), 'cwd': str(cwd)}
        record['commands'].append(item)
        save()
        stdout, stderr = out / (label + '.stdout'), out / (label + '.stderr')
        with stdout.open('wb') as so, stderr.open('wb') as se:
            child = subprocess.Popen(item['argv'], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=so, stderr=se, start_new_session=True)
            try:
                code = child.wait(timeout=600)
            except BaseException:
                for sig in (signal.SIGTERM, signal.SIGKILL):
                    try:
                        os.killpg(child.pid, sig)
                    except ProcessLookupError:
                        pass
                    try:
                        child.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                raise
        item.update(exit_code=code, stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
        save()
        require(code == 0, label + ' failed; retain and inspect logs')
        return stdout.read_bytes(), stderr.read_bytes()

    save()
    try:
        for opt in ('0', '2'):
            label = 'current-O' + opt
            folder = out / label
            snap, objects = folder / 'source', folder / 'objects'
            objects.mkdir(parents=True)
            snap.mkdir()
            shutil.copytree(ROOT / 'host/ghc', snap / 'host/ghc')
            require(hashes(snap / 'host/ghc') == host_hashes, 'host snapshot differs')
            for name, digest in inventory['source_files'].items():
                shutil.copyfile(HERE / 'controls' / name, snap / name)
                require(sha(snap / name) == digest, 'control snapshot differs')
            (snap / 'Main.hs').write_text('{-# OPTIONS_GHC -O0 #-}\nmodule Main where\n'
                                          'import qualified Tests\nmain :: IO ()\nmain = Tests.main\n')
            snapshot_inputs = hashes(snap)
            cobjects = []
            for name, relative in [('host', 'host/ghc/cbits/host.c'),
                                   ('supervisor', 'runtime/mlf_process_supervisor.c')]:
                obj = folder / (name + '.o')
                run(label + '-c-' + name, [build['cc']['path'], '-O2', '-std=c11',
                    '-I' + str(ROOT / 'runtime'), '-c', ROOT / relative, '-o', obj])
                cobjects.append(obj)
            command = [build['ghc']['path'], '--make', '-j1', '-O' + opt,
                '-fpedantic-bottoms', '-fno-state-hack', '-rtsopts=ignoreAll',
                '-package-env', '-', '-clear-package-db', '-global-package-db',
                '-no-user-package-db', '-hide-all-packages', '-i',
                '-i' + str(snap / 'host/ghc'), '-i' + str(snap),
                '-odir', objects, '-hidir', objects, '-dcore-lint',
                '-ddump-rule-rewrites', '-ddump-simpl', '-ddump-to-file']
            for package in PACKAGES:
                command.extend(['-package', package])
            command.extend([snap / 'Main.hs', *cobjects, '-o', folder / 'controls'])
            stdout, stderr = run(label + '-build', command, snap)
            expected = {name: snap / 'host/ghc' / (name.replace('.', '/') + '.hs')
                        for name in ('MLF.Host.Base', 'MLF.Host.Async', 'MLF.Host.IO', 'MLF.Primitive')}
            expected.update({name: snap / (name + '.hs') for name in ('Oracle', 'Probe', 'Tests', 'Main')})
            verify_resolution((stdout + stderr).decode(), expected)
            stdout, stderr = run(label + '-run', [folder / 'controls'], snap)
            require(stdout == inventory['expected_stdout'].encode() and
                    stderr == inventory['expected_stderr'].encode(),
                    label + ' exact finite-control output mismatch')
            rewrite = snap / 'Probe.dump-rule-rewrites'
            counts = rule_counts(rewrite.read_text() if rewrite.exists() else '')
            verify_probe_counts(counts, opt)
            if opt == '2':
                verify_unmatched_core((snap / 'Probe.dump-simpl').read_text())
            require(all(sha(snap / path) == digest for path, digest in snapshot_inputs.items()),
                    'control/host snapshot input changed')
            record['runs'].append({'optimization': opt, 'complete': True,
                'actual_rule_firings': counts, 'executable_sha256': sha(folder / 'controls'),
                'resolved_modules': {name: {'path': str(path), 'sha256': sha(path)}
                                     for name, path in expected.items()},
                'dump_hashes': {str(p.relative_to(out)): sha(p)
                                for p in snap.glob('Probe.dump-*')}})
            save()

        # Do not instrument/rewrite production source or disturb its qualified objects.
        # Only Separate is missing from the copied complete O2 object closure.
        actual = out / 'actual-source'
        objects = actual / 'objects'
        shutil.copytree(producer / 'objects', objects)
        require(hashes(objects) == object_hashes, 'copied producer objects differ')
        for suffix in ('.hi', '.o'):
            (objects / ('Bootstrap/Separate' + suffix)).unlink()
        flags = [str(objects) if value == str(producer / 'objects') else value
                 for value in build['flags']]
        command = [build['ghc']['path'], '--make', '-no-link', '-j1', *flags,
            '-dcore-lint', '-ddump-rule-rewrites', '-ddump-simpl', '-ddump-to-file',
            '-ddump-file-prefix', str(actual / 'Separate'),
            ROOT / 'libraries/mlf-crates/Bootstrap/Separate.hs']
        stdout, stderr = run('actual-separate', command)
        compiled = re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)',
                              (stdout + stderr).decode(), re.M)
        require(compiled == ['Bootstrap.Separate'], 'actual proof recompiled unexpected modules')
        counts = rule_counts((actual / 'Separate.dump-rule-rewrites').read_text())
        require(all(count >= 4 for count in counts.values()), 'actual Separate lost literal rules')
        actual_hashes = hashes(objects)
        require(set(actual_hashes) == set(object_hashes), 'actual proof object inventory changed')
        require(all(actual_hashes[path] == digest for path, digest in object_hashes.items()
                    if path not in ('Bootstrap/Separate.hi', 'Bootstrap/Separate.o')),
                'actual proof rewrote an unrelated copied object')
        record['actual_source'] = {'only_Separate_recompiled': True,
            'actual_literal_rule_firings': counts,
            'dump_hashes': {str(p.relative_to(out)): sha(p) for p in actual.glob('Separate.dump-*')}}
        require(hashes(producer / 'objects') == object_hashes, 'qualified producer objects changed')
        require(hashes(ROOT / 'host/ghc') == host_hashes, 'host source inventory changed')
        require(all(sha(path) == digest for path, digest in inputs.items()), 'control input changed')
        require(auth.authenticate_build(producer / 'receipt.json', producer / 'bin', root=ROOT) == build,
                'current producer identity changed')
        record.update(complete=True, immutable_inputs_verified_after=True,
                      producer_outputs_immutable=True)
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        save()
    print('PASS F1 current O0/O2 finite semantics and actual Separate rule/Core-lint proof; no speed claim')


if __name__ == '__main__':
    main()
