#!/usr/bin/env python3
"""Independent exact/demand controls against a frozen authenticated O2 producer.

Only private renamed Optimize modules and the independent Main are compiled.
There is no demand instrumentation and this runner makes no timing assertion.
"""
from __future__ import annotations
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import types

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCRATCH = ROOT / '.mlf-build/batch-replacement-20261101'
MODULE = 'libraries/mlf-llvm/Bootstrap/LLVM/Optimize.hs'
BASELINE_REVISION = '7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c'
BASELINE_SHA256 = 'b1a1e81d21a81300e8df8be5c62d21c824496e77c8040e3ca5cc122c4334fee4'
CHECKS = ['exact-pass-optimize-seeds', 'independent-counts', 'witness-implication',
          'witness-nonvacuity', 'long-chain-admission', 'pending-materialization',
          'fresh-order', 'unsupported-contexts', 'common-call-success-fallback',
          'public-raw-laziness', 'io-lazy-semantics']
EXPECTED = ''.join('PASS ' + name + '\n' for name in CHECKS).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--producer', type=Path, default=SCRATCH / 'baseline-producer')
    parser.add_argument('--producer-source', type=Path, default=ROOT)
    parser.add_argument('--baseline-source', type=Path, help='optional frozen checkout; exact pinned oracle hash still required')
    parser.add_argument('--optimization', choices=('0', '2'), default='2')
    args = parser.parse_args()
    dest, producer, producer_source = args.output.resolve(), args.producer.resolve(), args.producer_source.resolve()
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('batch_control_transport')
    H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    H.require(dest.is_relative_to(SCRATCH) and dest != SCRATCH and not dest.exists(),
              'fresh child of dedicated scratch required')
    H.require(not dest.is_relative_to(producer) and not producer.is_relative_to(dest), 'producer isolation')
    dest.mkdir(parents=True)
    record = {'complete': False, 'commands': [], 'scope': 'independent structural, demand and interpreted controls',
              'performance_assertions': False, 'native_execution': False, 'demand_instrumentation': False}
    save = lambda: H.save(dest / 'receipt.json', record)
    save()
    try:
        with H.SerialLock(ROOT / '.mlf-build'):
            auth = H.authenticate(producer, producer_source)
            producer_pins = H.file_pins(producer / 'objects')
            H.require({str(Path(p).relative_to(producer)): h for p, h in producer_pins.items()} == auth['object_inputs'],
                      'exact authenticated object inventory required')
            if args.baseline_source:
                oracle = args.baseline_source.resolve() / MODULE
                frozen = oracle.read_bytes()
            else:
                frozen = subprocess.check_output(['git', 'show', BASELINE_REVISION + ':' + MODULE], cwd=ROOT)
                oracle = dest / 'frozen-Optimize.hs'
                oracle.write_bytes(frozen)
            H.require(hashlib.sha256(frozen).hexdigest() == BASELINE_SHA256, 'exact pinned independent baseline oracle required')
            originals = {'LegacyOptimize': oracle, 'CandidateOptimize': ROOT / MODULE}
            transformed = []
            transformations = {}
            for name, source in originals.items():
                original = source.read_bytes()
                old, new = b'module Bootstrap.LLVM.Optimize where {', ('module ' + name + ' where {').encode()
                H.require(original.count(old) == 1, 'unique module rename anchor')
                changed = original.replace(old, new)
                H.require(changed.replace(new, old) == original, 'rename reversibility')
                target = dest / (name + '.hs')
                target.write_bytes(changed)
                transformed.append(target)
                transformations[name] = {'source': str(source), 'sha256': H.sha(source), 'replacement_only': 'module name'}
            fixture_source = ROOT / 'tools/shared/fixtures/native/IOActionSharing.hs'
            fixture = dest / 'IOFixture.hs'
            original_fixture = fixture_source.read_bytes()
            changed_fixture = original_fixture.replace(b'module Main where', b'module IOFixture where').replace(b':: Integer ->', b':: B.Int ->').replace(b'-> Integer ->', b'-> B.Int ->')
            H.require(changed_fixture.replace(b'module IOFixture where', b'module Main where').replace(b':: B.Int ->', b':: Integer ->').replace(b'-> B.Int ->', b'-> Integer ->') == original_fixture, 'fixture rename/type-adapter reversibility')
            fixture.write_bytes(changed_fixture)
            inputs = [helper, HERE / 'run.py', HERE / 'Main.hs', fixture_source, fixture, *originals.values(), *transformed,
                      producer / 'receipt.json', producer / 'host.o', producer / 'supervisor.o']
            pins = {str(p): H.sha(p) for p in inputs}
            record.update(inputs=pins, producer=str(producer), producer_source=str(producer_source),
                          baseline_revision=BASELINE_REVISION, baseline_sha256=BASELINE_SHA256,
                          transformations=transformations, producer_object_inventory=producer_pins)
            save()
            objects = dest / 'objects'
            shutil.copytree(producer / 'objects', objects)
            for suffix in ('.o', '.hi'):
                (objects / ('Main' + suffix)).unlink(missing_ok=True)
            copied_pins = H.file_pins(objects)
            flags, oldflags, i = [], list(auth['flags']), 0
            while i < len(oldflags):
                flag = oldflags[i]
                if flag in ('-odir', '-hidir'):
                    i += 2
                elif flag.startswith('-i'):
                    i += 1
                elif flag in ('-O0', '-O2'):
                    flags.append('-O' + args.optimization)
                    i += 1
                else:
                    flags.append(flag)
                    i += 1
            flags += ['-i', '-i' + str(objects), '-i' + str(producer / 'objects'),
                      '-odir', str(objects), '-hidir', str(objects)]
            limits = {'address_space_per_process_bytes': 6 * 1024**3, 'disk_free_floor_bytes': 5 * 1024**3,
                      'host_available_floor_bytes': 3 * 1024**3, 'max_work_bytes': 2 * 1024**3,
                      'process_tree_rss_bytes': 5 * 1024**3, 'wall_seconds': 600}
            def run(name, argv):
                result = H.Runner(dest, limits).run(argv, ROOT, dest / name, timed=False)
                record['commands'].append(result)
                save()
            ghc = auth['ghc']['path']
            record['private_module_optimization'] = args.optimization
            for source in [*transformed, fixture, HERE / 'Main.hs']:
                run('compile-' + source.stem, [ghc, *flags, '-c', str(source)])
            executable = dest / 'batch-controls'
            H.check_pins(copied_pins)
            run('link', [ghc, *flags, *map(str, sorted(objects.rglob('*.o'))),
                         str(producer / 'host.o'), str(producer / 'supervisor.o'), '-o', str(executable)])
            for repeat in (1,):
                name = 'controls-' + str(repeat)
                run(name, [str(executable)])
                H.require((dest / name / 'stdout').read_bytes() == EXPECTED, 'exact independent check inventory')
                H.require(not (dest / name / 'stderr').read_bytes(), 'empty stderr required')
            H.check_pins(pins)
            H.check_pins(producer_pins)
            H.require(H.authenticate(producer, producer_source) == auth, 'producer changed')
            record.update(complete=True, checks=CHECKS, executions=1,
                          executable_sha256=H.sha(executable), immutable_inputs_verified_after=True)
            save()
    except BaseException as exc:
        record['error'] = repr(exc)
        save()
        raise
    print(str(dest / 'receipt.json'))


if __name__ == '__main__':
    main()
