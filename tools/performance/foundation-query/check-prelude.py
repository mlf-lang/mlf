#!/usr/bin/env python3
"""Exercise installation, verified hits and repair through the ordinary crate CLI."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from compare import compile_crate, crate_spec


def check_witness(producer, binary, work):
    root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(root / 'tools/shared'))
    import build
    import test_direct

    producer = producer.resolve(strict=True)
    receipt = test_direct.authenticate_build(producer / 'receipt.json', producer / 'bin', root=root)
    if Path(receipt['outputs']['emlf']['path']) != binary:
        raise ValueError('witness fixture and CLI must use the same producer')
    flags = receipt['flags'][:receipt['flags'].index('-i')]
    for package in build.PACKAGES:
        flags.extend(['-package', package])
    ghc = receipt['ghc']['path']
    source = Path(__file__).with_name('PreludeInstall.hs')
    obj = work / 'witness.o'
    subprocess.run([ghc, '-c', *flags, '-i', '-i' + str(producer / 'objects'), source,
                    '-o', obj, '-ohi', work / 'witness.hi'], check=True, timeout=120)
    objects = [producer / name for name in sorted(receipt['object_inputs'])
               if name.endswith('.o') and name != 'objects/Main.o']
    for name, relative in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        target = work / (name + '.o')
        subprocess.run([receipt['cc']['path'], '-O2', '-std=c11', '-I' + str(root / 'runtime'),
                        '-c', root / relative, '-o', target], check=True, timeout=120)
        objects.append(target)
    executable = work / 'check-witness'
    subprocess.run([ghc, *flags, '-rtsopts=ignoreAll', obj, *objects, '-o', executable], check=True, timeout=120)
    subprocess.run([executable, work / 'invalid-literal/unit'], check=True, timeout=240)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--producer', type=Path, help='also run the forged-witness control against this authenticated build')
    args = parser.parse_args()
    binary = args.compiler.resolve(strict=True)
    work = args.output.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = work / 'Sample.hs'
    source.write_text("""-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
             KindSignatures, FlexibleContexts, FlexibleInstances,
             MultiParamTypeClasses, OverloadedStrings #-}
module Sample where {
  import MLF.Primitive;
  value :: Int;
  value = 41
}
""")
    installed = work / 'builtin/unit'
    spec = work / 'crate.spec'
    spec.write_text(crate_spec([('Sample', source)], 'prelude-control/1/library', work / 'cache', installed))
    paths = [installed.with_suffix(ext) for ext in ['.mlfci', '.mlfco']]

    def run(name, expected):
        output = work / name
        compile_crate(binary, spec, output)
        report = json.loads(output.with_suffix('.queries').read_text())
        if (report['inferred_groups'], report['reused_groups']) != expected:
            raise ValueError('unexpected inference counts for ' + name)
        return tuple(output.with_suffix(path.suffix).read_bytes() for path in paths)

    def read_pair():
        return tuple(path.read_bytes() for path in paths)

    artifact = run('initialize', (1, 0))
    reference = read_pair()
    if reference == artifact:
        raise ValueError('foreign-pair control needs different valid objects')
    before = [p.stat() for p in paths]
    if run('warm', (0, 1)) != artifact or read_pair() != reference:
        raise ValueError('valid installation changed')
    if [(p.st_ino, p.st_mtime_ns) for p in before] != [(p.stat().st_ino, p.stat().st_mtime_ns) for p in paths]:
        raise ValueError('valid installation was rewritten')

    for name in ('missing-object', 'damaged-object', 'damaged-interface', 'foreign-valid-pair'):
        if name == 'missing-object':
            paths[1].unlink()
        elif name == 'foreign-valid-pair':
            for path, contents in zip(paths, artifact):
                path.write_bytes(contents)
        else:
            path = paths[0] if name == 'damaged-interface' else paths[1]
            bad = bytearray(path.read_bytes())
            bad[-1] ^= 1
            path.write_bytes(bad)
        if run(name, (0, 1)) != artifact or read_pair() != reference:
            raise ValueError('failed to repair ' + name)
    print('PASS clean install, untouched hit, missing object, damaged object/interface and valid foreign pair')
    if args.producer:
        check_witness(args.producer, binary, work)


if __name__ == '__main__':
    main()
