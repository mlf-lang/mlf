#!/usr/bin/env python3
"""Generated-validation boundaries against a complete fixed pre-change owner."""
from pathlib import Path
import argparse
import re
import shutil
import sys
import types

import source_contract as C

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTROL_SHA = '4fbe283e60e853550f204cab759207894d5b88fb319bffba2b0c825990334626'
EXPECTED = b'PASS validation reuse: 20 authored programs, raw solver states, skeleton demand, 3 raw rejections, 4 partial-value orders\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    producer, out = args.producer.resolve(strict=True), args.output.resolve()
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    H = types.ModuleType('unchanged_resource_helper'); H.__file__ = str(helper)
    exec(compile(helper.read_bytes(), str(helper), 'exec'), H.__dict__)
    H.require(not out.exists() and not ROOT.is_relative_to(out)
              and not producer.is_relative_to(out) and not out.is_relative_to(producer),
              'fresh controls separate from source ancestor and producer')
    out.mkdir(parents=True)
    record = {'complete': False, 'commands': [], 'performance_measured': False,
              'candidate_output_used_for_expectations': False, 'inputs': H.file_pins(HERE)}
    record['inputs'][str(helper)] = H.sha(helper)
    controls = ROOT / 'tools/performance/a1-private-index/controls'
    historical_path = controls.parent / 'run_controls.py'
    compatibility = H.load(controls.parent / 'current/source-compatibility.json')
    H.require(H.sha(historical_path) == compatibility['historical_runner_sha256'], 'frozen A1 runner')
    historical = H.module(historical_path, 'frozen_a1')
    record['inputs'][str(historical_path)] = H.sha(historical_path)
    H.require(H.sha(HERE / 'BoundaryControls.hs') == CONTROL_SHA, 'fixed authored boundary controls')
    auth = H.authenticate(producer, ROOT)
    owner = ROOT / C.OWNER
    raw = owner.read_bytes(); previous = C.restore_previous_owner(raw)
    H.require(C.sha(previous) == historical.OWNER_SHA, 'original independent A1 owner identity')
    H.require(auth['shared_inputs']['Bootstrap.Constraint']['sha256'] == C.CONSTRAINT_SHA,
              'generation validation unchanged')
    record['inputs'][str(owner)] = C.NEW_OWNER_SHA
    record['inputs'][str(producer / 'receipt.json')] = H.sha(producer / 'receipt.json')
    objects = out / 'objects'; shutil.copytree(producer / 'objects', objects)
    for suffix in ['.o', '.hi']: (objects / ('Main' + suffix)).unlink(missing_ok=True)
    immutable = H.file_pins(objects)
    flags = []; i = 0
    while i < len(auth['flags']):
        value = auth['flags'][i]
        if value in ['-odir', '-hidir']: i += 2; continue
        if value.startswith('-i'): i += 1; continue
        flags.append(value); i += 1
    flags += ['-i', '-i' + str(objects), '-odir', str(objects), '-hidir', str(objects)]
    limits = {'address_space_per_process_bytes': 6*1024**3, 'disk_free_floor_bytes': 5*1024**3,
              'host_available_floor_bytes': 3*1024**3, 'max_work_bytes': 1024**3,
              'process_tree_rss_bytes': 5*1024**3, 'wall_seconds': 600}
    def save(): H.save(out / 'receipt.json', record)
    def run(label, argv, expected=0):
        result = H.Runner(out, limits).run(argv, ROOT, out / label, expected_exit=expected)
        record['commands'].append(result); save()
    ghc = auth['ghc']['path']; done = set()
    def compile_frozen(name):
        if name in done: return
        path = controls / (name + '.hs'); data = path.read_bytes()
        H.require(H.sha(path) == historical.CONTROL_HASHES[path.name], 'complete pinned oracle ' + name)
        for dep in re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Za-z0-9_.]+)', data.decode(), re.M):
            if (controls / (dep + '.hs')).is_file(): compile_frozen(dep)
        record['inputs'][str(path)] = H.sha(path)
        run(name, [ghc, *flags, '-c', path]); done.add(name)
    save()
    try:
        with H.SerialLock(out):
            compile_frozen('SessionOracle')
            for name, data in [('V1FrozenSession', previous), ('V1SessionUnderTest', raw)]:
                old = b'module Bootstrap.CrateSession (compileSpecFile) where {'
                new = ('module ' + name + ' where {').encode()
                H.require(data.count(old) == 1, 'sealed owner header')
                copy = out / (name + '.hs'); copy.write_bytes(data.replace(old, new))
                H.require(copy.read_bytes().replace(new, old) == data, 'exact test-only export inverse')
                record['inputs'][str(copy)] = H.sha(copy)
                run(name, [ghc, *flags, '-c', copy])
            run('main', [ghc, *flags, '-c', HERE / 'BoundaryControls.hs'])
            H.check_pins(immutable)
            run('link', [ghc, *flags, '-rtsopts=ignoreAll', *sorted(objects.rglob('*.o')),
                         producer / 'host.o', producer / 'supervisor.o', '-o', out / 'boundary-controls'])
            run('execute', [out / 'boundary-controls'])
            H.require((out / 'execute/stdout').read_bytes() == EXPECTED
                      and not (out / 'execute/stderr').read_bytes(), 'exact boundary-control completion')
            for symbol in ['solveGenerated', 'prepareValidatedGraph', 'solvePreparedGraph']:
                negative = out / (symbol + '.hs')
                negative.write_text('module PrivateAccess where\nimport Bootstrap.CrateSession (' + symbol + ')\n')
                run('private-' + symbol, [ghc, *flags, '-c', negative], expected=1)
                error = (out / ('private-' + symbol) / 'stderr').read_text()
                H.require('does not export' in error and symbol in error
                          and 'Could not find module' not in error, 'actual sealed export rejection ' + symbol)
            H.check_pins(immutable); H.check_pins(record['inputs'])
            H.require(H.authenticate(producer, ROOT) == auth, 'ordinary producer unchanged')
            record.update(complete=True, authored_programs=20, raw_rejections=3,
                          partial_value_orders=4, export_rejections=3,
                          previous_owner_sha256=C.sha(previous), current_owner_sha256=C.sha(raw))
            save()
    except BaseException as error:
        record['error'] = repr(error); save(); raise
    print(EXPECTED.decode().strip())


if __name__ == '__main__':
    main()
