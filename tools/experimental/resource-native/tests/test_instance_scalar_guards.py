#!/usr/bin/env python3
"""Focused real-session Instance scalar-operation controls on a checked pair.

The supplied generated callbacks must have passed fresh resource/metadata checks.
This runner invokes no source compiler and changes no admitted metadata. It uses
the existing bounded process helper and ordinary O0/O2 compilation, not LTO.
Private frame/value-fact injections are not hostile-pointer or public ABI claims.
"""
import argparse
import json
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(BASE))
from source_build_v8 import MIB, RUNTIME_SOURCES, executable, require, run, save, sha

FILES = ('ir8_packet_generated.h', 'ir8_packet_generated.c',
         'ir8_runtime_generated.h', 'ir8_runtime_generated.c')
CASES = ('healthy', 'generic-force', 'generic-prim2', 'generic-select',
         'neutral-frame', 'foreign-env', 'neutral-env', 'foreign-code',
         'foreign-execution', 'zero-capsule', 'future-capsule', 'wrong-activation',
         'active-intro', 'wrong-kind', 'wrong-result', 'wrong-identity',
         'wrong-home', 'entry-work', 'force-arrow', 'force-principal',
         'force-shape', 'force-type-work')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--expected-scalar', type=int, default=42)
    parser.add_argument('--require-prim2', action='store_true')
    parser.add_argument('--require-select', action='store_true')
    args = parser.parse_args(argv)
    require(-(1 << 63) <= args.expected_scalar < (1 << 63), 'expected scalar out of range')
    source = args.generated.resolve()
    payloads = {name: (source / name).read_bytes() for name in FILES}
    require(all(0 < len(data) <= 32*MIB for data in payloads.values()),
            'bounded nonempty generated source files required')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cc = executable(args.cc)
    env = dict(os.environ, LANG='C', LC_ALL='C', TZ='UTC')
    outcomes = []
    for opt in ('O0', 'O2'):
        directory = output / opt
        directory.mkdir()
        for name, data in payloads.items():
            with (directory / name).open('xb') as stream:
                stream.write(data)
        binary = directory / 'instance-scalar-guards'
        command = [cc, '-std=c11', '-' + opt, '-g', '-Wall', '-Wextra', '-Werror',
                   '-pedantic', '-fno-lto', '-I', str(BASE / 'runtime_v8'),
                   '-I', str(BASE / 'packet_v8'), '-I', str(directory),
                   str(HERE / 'instance_scalar_guard_driver.c'),
                   str(BASE / 'packet_v8/ir8_packet.c')]
        command += [str(BASE / 'runtime_v8' / name) for name in RUNTIME_SOURCES]
        command += [str(directory / 'ir8_packet_generated.c'),
                    str(directory / 'ir8_runtime_generated.c'),
                    '-Wl,--wrap=rt8_private_enter', '-Wl,--wrap=rt8_force',
                    '-Wl,--wrap=rt8_generic_seal', '-Wl,--wrap=rt8_private_value',
                    '-Wl,--wrap=rt8_private_intrinsic_scalar_type', '-o', str(binary)]
        run(command, directory, 'compile', cwd=directory, env=env,
            wall=60, cpu=30, memory=1024*MIB)
        run([str(binary)], directory, 'run', cwd=directory, env=env,
            wall=60, cpu=40, memory=512*MIB)
        require((directory / 'run.stderr').read_bytes() == b'', 'unexpected target stderr')
        rows = [json.loads(line) for line in (directory / 'run.stdout').read_text().splitlines()]
        require(len(rows) == len(CASES)+1 and rows[-1] == dict(
            summary=True, runtime_cases=len(CASES), failures=0), 'control count mismatch')
        controls = rows[:-1]
        require([row['case'] for row in controls] == list(CASES), 'control names changed')
        require(all(row['ok'] == 1 for row in controls), 'independent C control failed')
        require(all(row['enter_calls'] == row['enter_real'] and
                    row['force_calls'] == row['force_real'] and
                    row['scalar_calls'] == row['scalar_real'] for row in controls),
                'each intercepted call must delegate once')
        healthy = controls[0]
        require(healthy['rc'] == healthy['fault'] == healthy['live_bytes'] == healthy['live_blocks'] == 0 and
                healthy['scalar_kind'] == 1 and healthy['scalar'] == args.expected_scalar and
                healthy['instance_force'] > 0 and healthy['scalar_calls'] > 0 and
                healthy['instance_prim2'] + healthy['instance_select'] > 0,
                'healthy genuine Instance computation failed')
        if args.require_prim2:
            require(healthy['instance_prim2'] > 0, 'Instance PRIM2 not exercised')
        if args.require_select:
            require(healthy['instance_select'] > 0, 'Instance SELECT not exercised')
        require(all(row['rc'] == 2 and row['fault'] == 8 and
                    row['live_bytes'] == row['retired_bytes'] > 0 and
                    row['live_blocks'] == row['retired_blocks'] > 0 for row in controls[1:]),
                'fault retention and distinct terminal surrender differ')
        require(all(row['manual_enters'] == 1 for row in controls[1:4]) and
                all(row['manual_enters'] == 0 for row in [controls[0]] + controls[4:]),
                'neutral introduction probes differ')
        outcomes.append(rows)
    require(outcomes[0] == outcomes[1], 'O0/O2 control reports differ, including work')
    require(all((source / name).read_bytes() == data for name, data in payloads.items()),
            'supplied generated files changed')
    save(output / 'results.json', {
        'status': 'pass', 'scope': 'real Instance scalar-operation controls',
        'builds': 2, 'native_runs': 2, 'controls_per_run': len(CASES),
        'generated_files': {name: sha(data) for name, data in payloads.items()},
        'guard_sha256': sha((BASE / 'runtime_v8/rir8_guard.c').read_bytes()),
        'force_sha256': sha((BASE / 'runtime_v8/rir8_force.c').read_bytes()),
        'driver_sha256': sha((HERE / 'instance_scalar_guard_driver.c').read_bytes()),
        'coverage_limits': ['Known-valid generated objects before private interposition.',
                            'No admitted packet or callback mutation.',
                            'No arbitrary pointer or forged allocation recovery.',
                            'No native per-Code effect whitelist is claimed.',
                            'All three neutral opcodes are refused; only exercised Instance operations are claimed.']})
    print('PASS: two optimizer modes;', len(CASES), 'controls per run', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
