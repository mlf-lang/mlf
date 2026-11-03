#!/usr/bin/env python3
"""Exercise both completed native compiler artifacts on authored source cases."""
from pathlib import Path
import argparse
import types

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['mlf', 'ghc', 'setup', 'output']:
        parser.add_argument('--' + option, type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('guard')
    H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    setup = H.load(args.setup)
    limits = dict(address_space_per_process_bytes=6*1024**3,
                  disk_free_floor_bytes=5*1024**3, host_available_floor_bytes=3*1024**3,
                  max_work_bytes=3*1024**3, process_tree_rss_bytes=5*1024**3,
                  wall_seconds=600)
    source = out / 'unicode.emlf'
    source.write_text('''data Box a = Box a
identity x = x
unbox value = case value of { Box x -> x }
main = do { printInt (unbox (Box (identity 42))); putStrLn (identity "éλ中😀"); printInt (stringLength "éλ中😀"); printInt (stringCodeAt "éλ中😀" 3); putStrLn (stringSlice "éλ中😀end" 4 3) }
''')
    expected = '42\néλ中😀\n4\n128512\nend\n'.encode()
    pins = {str(path.resolve()): H.sha(path) for path in
            [args.mlf, args.ghc, args.setup, source, Path(__file__), helper,
             Path(setup['runtime']), Path(setup['clang'])]}
    record = dict(complete=False, performance_samples=0, inputs=pins, commands=[])
    save = lambda: H.save(out / 'receipt.json', record)
    save()
    with H.SerialLock(ROOT / '.mlf-build'):
        runner = H.Runner(out, limits)
        def run(name, command, status=0):
            dest = out / name
            record['commands'].append(runner.run(command, ROOT, dest, expected_exit=status))
            save()
            return (dest / 'stdout').read_bytes(), (dest / 'stderr').read_bytes()
        observations = {}
        for side, compiler in [('mlf', args.mlf.resolve()), ('ghc', args.ghc.resolve())]:
            typed = run(side + '-type', [compiler, '--type', source])
            interpreted = run(side + '-run', [compiler, '--run', source])
            H.require(interpreted[0] == expected and not interpreted[1], 'authored interpreted output')
            emitted = run(side + '-emit', [compiler, '--emit-llvm-gc', source])
            ir = out / (side + '.ll')
            ir.write_bytes(emitted[0])
            H.require(ir.stat().st_size > 0 and not emitted[1], 'LLVM emitted')
            program = out / (side + '-program')
            run(side + '-clang', [setup['clang'], '-O2', '-Wno-override-module', ir,
                                 setup['runtime'], *setup['libs'], '-lm', '-lpthread', '-ldl', '-o', program])
            native = run(side + '-native', [program])
            H.require(native[0] == expected and not native[1], 'authored native output')
            rejected = run(side + '-reject', [compiler, '--type', '--expr', 'stringLength 1'], status=1)
            H.require(bool(rejected[1]), 'nonempty type error')
            observations[side] = (typed, emitted, rejected)
        H.require(observations['mlf'] == observations['ghc'], 'same raw type, LLVM, and error output')
        H.check_pins(pins)
        record.update(complete=True, authored_output=expected.decode(),
                      raw_type_llvm_error_equal=True)
        save()
    print('PASS both native compilers: datatype, polymorphism, Unicode, interpreter, LLVM/O2 execution, rejection')


if __name__ == '__main__':
    main()
