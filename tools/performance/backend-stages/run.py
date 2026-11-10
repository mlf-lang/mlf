#!/usr/bin/env python3
"""Force current checked-to-LLVM stages, then require ordinary output equality.

Diagnostic intervals include forcing and perturb laziness/GC. This tool does
not infer speedups, run native self-host fixed points, or rebuild shared modules.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
STAGES = ['load-link-checked', 'constructors', 'erase', 'optimize', 'representation', 'generate']
PHASES = ['start', *[name for stage in STAGES for name in (stage, stage + '-forced-again')], 'write']
LIMITS = dict(address_space_per_process_bytes=6*1024**3,
              disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
              max_work_bytes=4*1024**3, process_tree_rss_bytes=5*1024**3,
              wall_seconds=600)


def parse_phases(text):
    points = []
    for line in text.splitlines():
        if line.startswith('MLF_BACKEND_PHASE '):
            fields = line.split()
            if len(fields) != 3 or not fields[2].isascii() or not fields[2].isdigit():
                raise ValueError('invalid phase marker: ' + line)
            points.append((fields[1], int(fields[2])))
    if [label for label, _ in points] != PHASES:
        raise ValueError('incomplete or reordered phase inventory')
    if any(end < start for (_, start), (_, end) in zip(points, points[1:])):
        raise ValueError('non-monotonic phase timestamps')
    return [{'name': name, 'wall_seconds': (end-start)/1e9}
            for (_, start), (name, end) in zip(points, points[1:])]


def parse_inputs(text, cwd):
    paths = []
    for value in text.splitlines():
        if not value or '\x00' in value:
            raise ValueError('invalid artifact path')
        path = Path(value)
        paths.append((path if path.is_absolute() else cwd/path).resolve(strict=True))
    if not paths or len(paths) % 2 or len(paths) != len(set(paths)):
        raise ValueError('incomplete or duplicated artifact inventory')
    for interface, obj in zip(paths[::2], paths[1::2]):
        if interface.suffix != '.mlfci' or obj != interface.with_suffix('.mlfco'):
            raise ValueError('artifact interface/object pairing differs')
    return paths


def module(path):
    loaded = types.ModuleType('backend_guard')
    loaded.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), loaded.__dict__)
    return loaded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['producer', 'producer-source', 'checked-interface', 'output']:
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    producer, source = args.producer.resolve(), args.producer_source.resolve()
    output = args.output.resolve()
    if output.is_relative_to(producer) or producer.is_relative_to(output):
        parser.error('output must be separate from immutable producer')
    interface = args.checked_interface.resolve(strict=True)
    if interface.suffix != '.mlfci':
        parser.error('checked input must name a .mlfci interface')
    output.mkdir(parents=True, exist_ok=False)
    helper_path = ROOT/'tools/performance/a1-private-index/helper.py'
    H = module(helper_path)
    record = dict(complete=False, diagnostic_only=True, performance_samples=0,
                  compiler_modules_rebuilt=False, native_fixed_point=False,
                  ordinary_output_equal=False, commands=[])
    save = lambda: H.save(output/'receipt.json', record)
    save()
    pins, auth = {}, None
    try:
        # Coordinate a single shared producer across separate worker checkouts.
        with H.SerialLock(producer.parent):
            auth = H.authenticate(producer, source)
            object_inputs = auth.get('object_inputs', {})
            H.require(bool(object_inputs), 'producer omitted object/interface inventory')
            for name, digest in object_inputs.items():
                path = (producer/name).resolve(strict=True)
                H.require(path.is_relative_to(producer) and H.sha(path) == digest,
                          'producer object/interface changed: ' + name)
                pins[str(path)] = digest
            # Admit only this checkout's exact production implementation. New
            # diagnostic tooling need not be part of the producer build receipt.
            for section in ['shared_inputs', 'host_inputs', 'configuration_inputs']:
                for item in auth[section].values():
                    relative = Path(item['path']).relative_to(source)
                    local = ROOT/relative
                    H.require(H.sha(local) == item['sha256'],
                              'probe checkout differs from producer: ' + str(relative))
                    pins[str(local)] = item['sha256']
            for path in [Path(__file__).resolve(), HERE/'Main.hs', helper_path, producer/'receipt.json']:
                pins[str(path)] = H.sha(path)
            record.update(producer_receipt=str(producer/'receipt.json'),
                          producer_source=str(source), checked_interface=str(interface))
            save()
            shutil.copy2(HERE/'Main.hs', output/'Main.hs')
            pins[str(output/'Main.hs')] = H.sha(output/'Main.hs')
            flags = ['-XHaskell2010', '-package-env', '-', '-clear-package-db',
                     '-global-package-db', '-no-user-package-db', '-hide-all-packages',
                     '-O2', '-fpedantic-bottoms', '-fno-state-hack']
            for package in ['base', 'array', 'bytestring', 'text', 'containers', 'directory']:
                flags += ['-package', package]
            def run(label, argv):
                H.check_pins(pins)
                row = H.Runner(output, LIMITS).run(argv, source, output/label)
                record['commands'].append(row)
                save()
                return output/label
            ghc, cc = auth['ghc']['path'], auth['cc']['path']
            obj, hi = output/'Main.o', output/'Main.hi'
            run('compile-probe', [ghc, '-c', *flags, '-Werror=incomplete-patterns',
                '-Werror=incomplete-uni-patterns', '-i', '-i'+str(producer/'objects'),
                '-o', obj, '-ohi', hi, output/'Main.hs'])
            transports = []
            for label, path in [('host', source/'host/ghc/cbits/host.c'),
                                ('supervisor', source/'runtime/mlf_process_supervisor.c')]:
                target = output/(label+'.o')
                run('compile-'+label, [cc, '-O2', '-std=c11', '-I'+str(source/'runtime'),
                                      '-c', path, '-o', target])
                transports.append(target)
            linked = [producer/name for name in sorted(object_inputs)
                      if name.endswith('.o') and name != 'objects/Main.o']
            H.require(bool(linked), 'no authenticated linkable producer objects')
            binary = output/'backend-stages'
            run('link-probe', [ghc, *flags, '-rtsopts=ignoreAll', obj, *linked,
                              *transports, '-o', binary])
            for path in [obj, hi, binary, *transports]:
                pins[str(path)] = H.sha(path)
            controls = run('forcing-controls', [binary, 'self-test'])
            H.require((controls/'stdout').read_bytes() ==
                      b'PASS 26 nested forcing controls and 2 total controls\n',
                      'forcing control inventory differs')
            found = run('discover-inputs', [binary, 'inputs', interface])
            for path in parse_inputs((found/'stdout').read_text(), source):
                H.regular(path)
                pins[str(path)] = H.sha(path)
            H.require(str(interface) in pins, 'root interface absent from dependency graph')
            # Ordinary emission is a fresh process and uses no result of the
            # diagnostic. It is an equivalence control, not a timing baseline.
            ordinary = run('ordinary', [producer/'bin/emlf', '--crate-to-llvm-gc', interface])
            diagnostic = run('diagnostic', [binary, 'profile', interface])
            left, right = ordinary/'stdout', diagnostic/'stdout'
            H.require(left.stat().st_size > 0, 'empty ordinary LLVM')
            # Raw bytes, not just hashes, establish final output equality.
            with left.open('rb') as a, right.open('rb') as b:
                while True:
                    x, y = a.read(1024*1024), b.read(1024*1024)
                    H.require(x == y, 'diagnostic LLVM differs from ordinary output')
                    if not x:
                        break
            record['phases'] = parse_phases((diagnostic/'stderr').read_text())
            H.check_pins(pins)
            H.require(H.authenticate(producer, source) == auth, 'ordinary producer changed')
            record.update(complete=True, ordinary_output_equal=True,
                          llvm_bytes=left.stat().st_size, llvm_sha256=H.sha(left), inputs=pins)
            save()
    except BaseException as error:
        record.update(complete=False, error=repr(error), inputs=pins)
        save()
        raise
    print('PASS diagnostic-only backend stages; ordinary LLVM is byte-identical')


if __name__ == '__main__':
    main()
