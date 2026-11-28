#!/usr/bin/env python3
"""Compare ordinary old/current host modules with independent Unicode controls."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
OWNER = ROOT / 'host/ghc/MLF/Host/Base.hs'
sys.path.insert(0, str(ROOT / 'tools/shared'))
from test_direct import authenticate_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--optimization', choices=['0', '2'], required=True)
    args = parser.parse_args()
    producer, output = args.producer.resolve(), args.output.resolve()
    if (output.exists() or output.is_relative_to(producer) or producer.is_relative_to(output)
            or ROOT.is_relative_to(output)):
        parser.error('output must be new and separate from producer/source')
    output.mkdir(parents=True)
    helper_path = ROOT / 'tools/performance/a1-private-index/helper.py'
    spec = importlib.util.spec_from_file_location('unicode_control_processes', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    limits = dict(address_space_per_process_bytes=6*1024**3, disk_free_floor_bytes=5*1024**3,
                  host_available_floor_bytes=3*1024**3, max_work_bytes=3*1024**3,
                  process_tree_rss_bytes=5*1024**3, wall_seconds=600)
    record = dict(complete=False, optimization=args.optimization, commands=[],
                  scope='94 Unicode fixtures against an independent list oracle and retained host reference')

    def save():
        helper.save(output / 'receipt.json', record)

    save()
    try:
        with helper.SerialLock(ROOT / '.mlf-build'):
            receipt = producer / 'receipt.json'
            auth = authenticate_build(receipt, producer / 'bin', root=ROOT)
            objects = output / 'objects'
            shutil.copytree(producer / 'objects', objects)
            source = output / 'source'
            source.mkdir()
            for name in ('LegacyBase.hs', 'Main.hs'):
                shutil.copy2(HERE / name, source / name)
            pins = helper.file_pins(source)
            pins.update({str(path): helper.sha(path) for path in
                         (Path(__file__), helper_path, ROOT / 'tools/shared/test_direct.py',
                          OWNER, HERE / 'LegacyBase.hs', HERE / 'Main.hs', receipt)})
            record['inputs'] = pins
            save()

            flags, index = [], 0
            while index < len(auth['flags']):
                flag = auth['flags'][index]
                if flag in ('-odir', '-hidir'):
                    index += 2
                elif flag.startswith('-i'):
                    index += 1
                else:
                    flags.append('-O'+args.optimization if flag in ('-O0', '-O2') else flag)
                    index += 1
            flags += ['-i', '-i'+str(objects), '-odir', str(objects), '-hidir', str(objects)]

            def run(label, command):
                record['commands'].append(helper.Runner(output, limits).run(command, ROOT, output / label))
                save()

            # Rebuild the current owner under its real module name in the private
            # object copy, so the requested O0/O2 policy covers both implementations.
            for label, path in (('legacy', source / 'LegacyBase.hs'), ('current', OWNER),
                                ('controls', source / 'Main.hs')):
                run('compile-'+label, [auth['ghc']['path'], *flags, '-c', path])
            binary = output / 'controls'
            run('link', [auth['ghc']['path'], *flags, *sorted(objects.rglob('*.o')),
                         producer / 'host.o', producer / 'supervisor.o', '-o', binary])
            run('run', [binary])
            helper.require((output / 'run/stdout').read_bytes() ==
                           b'PASS 94 Unicode fixtures: every scalar, block-boundary slices, exact bounds errors\n',
                           'complete fixture inventory')
            helper.check_pins(pins)
            helper.require(authenticate_build(receipt, producer / 'bin', root=ROOT) == auth,
                           'producer unchanged')
            record['complete'] = True
    except BaseException as error:
        record['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()
    print('PASS Unicode controls O'+args.optimization)


if __name__ == '__main__':
    main()
