#!/usr/bin/env python3
"""Focused O2 fixtures with authenticated immutable compiler-object reuse.

Not a full producer/fixed-point gate. The first fixture force-rebuilds; subsequent
fixtures reuse only a successful receipt's matching source/tool/options/objects.
Each output directory is new; Main is always rebuilt and C objects are isolated.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
import test_item4_contracts as contract

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {'pattern-do': 'PatternDo.hs', 'source': 'SourceSemantics.hs',
            'managed': 'ManagedArtifacts.hs', 'authority': 'ArtifactAuthority.hs',
            'artifact': 'ArtifactIdentity.hs', 'query': 'QueryCache.hs',
            'core': 'CoreIdentity.hs', 'separate': 'SeparateCrates.hs',
            'builtin': 'BuiltinArtifact.hs', 'source-scc': 'SourceSCC.hs',
            'source-crates': 'SourceCrates.hs'}
PROFILE = 'item4-O2-pedantic-bottoms-no-state-hack-v1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=FIXTURES, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--ghc', required=True)
    parser.add_argument('--seed-receipt', type=Path)
    parser.add_argument('--timeout', type=int, default=600)
    args = parser.parse_args()
    out = args.build_dir.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('build directory must be empty or new')
    if out == ROOT or ROOT.is_relative_to(out):
        parser.error('build directory must not contain checkout')
    out.mkdir(parents=True, exist_ok=True)
    before = contract.sources()
    driver = str(Path(__file__).resolve().relative_to(ROOT))
    before[driver] = contract.sha(__file__)
    fixture = 'tools/shared/fixtures/item4/' + FIXTURES[args.suite]
    closure = {driver, 'tools/shared/test_item4_contracts.py', 'shared-sources.json',
               fixture, 'host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c'}
    closure.update(k for k in before if k.startswith('runtime/') and k.endswith('.h'))
    receipt = {'scope': 'focused-item4-optimized-' + args.suite,
               'status': 'running', 'profile': PROFILE, 'inputs': before,
               'commands': [], 'tools': {}}
    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    def run(argv, label):
        row = {'argv': list(map(str, argv)), 'log': label + '.log'}
        receipt['commands'].append(row)
        save()
        start, peak = time.monotonic(), 0
        with (out / row['log']).open('wb') as log:
            proc = subprocess.Popen(row['argv'], cwd=ROOT, stdout=log,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            try:
                while proc.poll() is None:
                    rss, available = contract.process_memory(proc.pid)
                    peak = max(peak, rss)
                    if rss > 1.5 * 1024**3 or available < 3 * 1024**3:
                        raise RuntimeError('resource-memory guard: ' + label)
                    if time.monotonic() - start > args.timeout:
                        raise RuntimeError('resource-timeout: ' + label)
                    time.sleep(.1)
            except BaseException:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
                raise
        row.update(exit_code=proc.returncode, seconds=time.monotonic() - start,
                   peak_group_rss_bytes=peak, log_sha256=contract.sha(out / row['log']))
        save()
        if proc.returncode:
            raise RuntimeError(label + ' exit ' + str(proc.returncode))
    inherited_objects = {}
    try:
        ghc = Path(shutil.which(args.ghc) or args.ghc).resolve()
        run([ghc, '--numeric-version'], 'ghc-version')
        run([ghc, '--print-libdir'], 'ghc-libdir')
        if (out / 'ghc-version.log').read_text().strip() != '9.14.1':
            raise RuntimeError('expected pinned GHC 9.14.1')
        lib = Path((out / 'ghc-libdir.log').read_text().strip())
        for tool in [ghc, lib.parent / 'bin/ghc-9.14.1', lib / 'settings',
                     Path(shutil.which('cc')).resolve()]:
            receipt['tools'][str(tool)] = contract.sha(tool)
        manifest = json.loads((ROOT / 'shared-sources.json').read_text())
        objects, cbits = out / 'objects', out / 'cbits'
        objects.mkdir()
        cbits.mkdir()
        c_sources = []
        for relative in ['host/ghc/cbits/host.c', 'runtime/mlf_process_supervisor.c']:
            target = cbits / Path(relative).name
            shutil.copy2(ROOT / relative, target)
            if contract.sha(target) != before[relative]:
                raise RuntimeError('C source changed before compilation')
            c_sources.append(target)
        if args.seed_receipt:
            seed_path = args.seed_receipt.resolve()
            seed = json.loads(seed_path.read_text())
            if seed.get('status') != 'passed' or seed.get('profile') != PROFILE:
                raise RuntimeError('seed is not an authenticated compatible O2 pass')
            if seed['tools'] != receipt['tools']:
                raise RuntimeError('seed tool identity differs')
            for relative in seed['compiled_input_closure']:
                if before.get(relative) != seed['inputs'].get(relative):
                    raise RuntimeError('seed source changed: ' + relative)
            closure.update(seed['compiled_input_closure'])
            for relative, digest in seed['object_hashes'].items():
                if Path(relative).is_absolute() or '..' in Path(relative).parts:
                    raise RuntimeError('unsafe seed object path')
                original = seed_path.parent / relative
                if contract.sha(original) != digest:
                    raise RuntimeError('seed object changed: ' + relative)
                if relative in {'objects/Main.o', 'objects/Main.hi'}:
                    continue
                if not (relative.startswith('objects/') or relative.startswith('cbits/')):
                    raise RuntimeError('unexpected seed object path')
                target = out / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original, target)
                inherited_objects[relative] = digest
            receipt['seed'] = {'receipt': str(seed_path), 'sha256': contract.sha(seed_path),
                               'objects_reused': inherited_objects}
        flags = ['--make', '-j1', '-O2', '-fpedantic-bottoms', '-fno-state-hack',
                 '-rtsopts', '-package-env', '-', '-no-user-package-db', '-i', '-i' + str(ROOT / 'tools/shared/fixtures/item4'),
                 *['-i' + str(ROOT / p) for p in manifest['source_roots']],
                 '-I' + str(ROOT / 'runtime'), '-odir', objects, '-hidir', objects]
        c_inputs = [p.with_suffix('.o') for p in c_sources] if args.seed_receipt else c_sources
        if not args.seed_receipt:
            flags.append('-fforce-recomp')
        run([ghc, *flags, '-o', out / 'probe', ROOT / fixture, *c_inputs], 'compile')
        for name in re.findall(r'Compiling\s+[\w.]+\s+\(\s*([^,\n]+),',
                               (out / 'compile.log').read_text()):
            closure.add(str(Path(name.strip()).resolve().relative_to(ROOT)))
        receipt['object_hashes'] = {str(p.relative_to(out)): contract.sha(p)
                                   for folder in [objects, cbits] for p in folder.rglob('*')
                                   if p.suffix in {'.o', '.hi'}}
        if not all(receipt['object_hashes'].get(p) == h for p, h in inherited_objects.items()):
            raise RuntimeError('reused library object changed during compilation')
        arguments = [out / 'probe']
        if args.suite in {'separate', 'source-crates'}:
            arguments.append(out)
        if args.suite in {'query', 'source-scc'}:
            arguments.append(out / ('cache-' + str(time.time_ns())))
        arguments.extend(['+RTS', '-M700m', '-RTS'])
        run(arguments, 'positive')
        if args.suite in {'pattern-do', 'source'}:
            expected = {'pattern-do': 34, 'source': 18}[args.suite]
            actual = (out / 'positive.log').read_text().count('pass: ')
            if actual != expected:
                raise RuntimeError('expected ' + str(expected) + ' passing source cases, got ' + str(actual))
            receipt['passing_cases'] = actual
        if any(contract.sha(out / p) != h for p, h in receipt['object_hashes'].items()):
            raise RuntimeError('compiled object mutated during execution')
        receipt['binary_sha256'] = contract.sha(out / 'probe')
        receipt['status'] = 'passed'
    except BaseException as exc:
        receipt.update(status='failed', error=str(exc))
    finally:
        after = contract.sources()
        after[driver] = contract.sha(__file__)
        receipt['compiled_input_closure'] = sorted(closure)
        receipt['changed_inputs'] = [p for p in closure if before.get(p) != after.get(p)]
        receipt['changed_tools'] = [p for p, h in receipt['tools'].items() if contract.sha(p) != h]
        if receipt['changed_inputs'] or receipt['changed_tools']:
            receipt['status'] = 'invalidated-concurrent-input-change'
        save()
    print(str(out / 'receipt.json') + ': ' + receipt['status'])
    if receipt['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
