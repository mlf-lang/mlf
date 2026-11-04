#!/usr/bin/env python3
"""Focused generic concrete-callable capture controls on a freshly checked generated pair.

No source compiler is invoked. Compile the unchanged real callbacks and runtime
at O0/O2, exercise copied-packet rejection before admission and bounded real-entry
role/type/origin/Access/identity, alias-watermark and work-fault controls. Packet
rejections may be earlier than the new capture path. The native rule is not a
source-import whitelist; the supplied pair must have been freshly checked.
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--generated', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cc', default=os.environ.get('CC', 'cc'))
    parser.add_argument('--expected-scalar', type=int, default=42)
    parser.add_argument('--require-helper-captures', action='store_true')
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
        binary = directory / 'generic-callable-capture-guards'
        command = [cc, '-std=c11', '-' + opt, '-g', '-Wall', '-Wextra', '-Werror',
                   '-pedantic', '-fno-lto', '-I', str(BASE / 'runtime_v8'),
                   '-I', str(BASE / 'packet_v8'), '-I', str(directory),
                   str(HERE / 'generic_callable_capture_guard_driver.c'),
                   str(BASE / 'packet_v8/ir8_packet.c')]
        command += [str(BASE / 'runtime_v8' / name) for name in RUNTIME_SOURCES]
        command += [str(directory / 'ir8_packet_generated.c'),
                    str(directory / 'ir8_runtime_generated.c'),
                    '-Wl,--wrap=rt8_retain', '-Wl,--wrap=rt8_closure',
                    '-Wl,--wrap=rt8_generic_seal', '-Wl,--wrap=rt8_private_capture_publish',
                    '-Wl,--wrap=rt8_private_capture_transport',
                    '-o', str(binary)]
        run(command, directory, 'compile', cwd=directory, env=env,
            wall=60, cpu=30, memory=1024*MIB)
        run([str(binary)], directory, 'run', cwd=directory, env=env,
            wall=60, cpu=40, memory=512*MIB)
        require((directory / 'run.stderr').read_bytes() == b'', 'unexpected target stderr')
        rows = [json.loads(line) for line in (directory / 'run.stdout').read_text().splitlines()]
        require(1 < len(rows) < 10000, 'finite nonempty control output')
        summary = rows[-1]
        require(summary == dict(summary=True, packet_cases=len(rows)-22,
                                runtime_cases=21, failures=0), 'control count mismatch')
        require(all(r['ok'] == 1 for r in rows[:-1]), 'independent C control failed')
        require(all(r['kind'] == 'packet' and r['status'] != 0 for r in rows[:-22]),
                'copied packet must reject')
        runtime = rows[-22:-1]
        require([r['case'] for r in runtime] == [
            'healthy', 'foreign-access', 'concrete-capsule', 'instance-origin', 'pending-state', 'foreign-code',
            'wrong-role', 'wrong-type', 'wrong-shape', 'wrong-code', 'wrong-execution', 'wrong-representation', 'wrong-child-rep', 'noncapture-publish',
            'capture-work', 'foreign-request', 'bad-capture-index', 'transport-work',
            'alias-leak', 'alias-balanced', 'after-retain-work'], 'runtime cases changed')
        healthy = [r for r in runtime if r['case'] in ('healthy', 'alias-balanced')]
        faults = [r for r in runtime if r not in healthy]
        require(all(r['rc'] == 0 and r['fault'] == 0 and r['live_bytes'] == 0 for r in healthy),
                'genuine healthy execution/close failed')
        require(all(r['rc'] == 2 and r['fault'] == 8 and r['live_bytes'] > 0 and
                    r['live_bytes'] == r['retired_bytes'] for r in faults),
                'fault retention and separate surrender differ')
        require(all(r['imports'] > 0 and r['alias_checks'] == r['imports'] for r in runtime),
                'post-begin retain coverage missing')
        require(all(r['publish_calls'] == r['publish_real'] + r['old_publish_calls'] and
                    r['transport_calls'] == r['transport_real'] for r in runtime),
                'real helper delegation counts differ')
        require(healthy[0]['scalar_kind'] == healthy[1]['scalar_kind'] and
                healthy[0]['scalar'] == healthy[1]['scalar'], 'balanced aliases changed result')
        require(all(r['scalar_kind'] != 0 and r['scalar'] == args.expected_scalar for r in healthy),
                'healthy result differs from independently supplied expectation')
        require(all(r['callable_seen'] > 0 for r in healthy), 'ready callable capture not observed')
        if args.require_helper_captures:
            require(all(r['helper_slots_seen'] > 0 for r in healthy), 'nonempty original helper captures not exercised')
        outcomes.append(rows)
    require(outcomes[0] == outcomes[1], 'O0/O2 control reports differ, including work')
    require(all((source / name).read_bytes() == data for name, data in payloads.items()),
            'supplied generated files changed')
    save(output / 'results.json', {
        'status': 'pass', 'scope': 'copied-packet and real generic concrete-callable capture controls',
        'builds': 2, 'native_runs': 2, 'controls_per_run': len(outcomes[0])-1,
        'generated_files': {name: sha(data) for name, data in payloads.items()},
        'packet_sha256': sha((BASE / 'packet_v8/ir8_packet.c').read_bytes()),
        'runtime_sha256': sha((BASE / 'runtime_v8/rir8_runtime.c').read_bytes()),
        'driver_sha256': sha((HERE / 'generic_callable_capture_guard_driver.c').read_bytes()),
        'coverage_limits': ['Known-valid generated references in interposition.',
                            'No arbitrary diagnostic/source admission.',
                            'No metadata mutation after admission.',
                            'Private copied-fact controls are not public ABI entry-point claims.',
                            'The noncapture control deliberately calls the unchanged real global guard.',
                            'Only concrete ready closure contracts in the supplied program are covered.',
                            'Forced/returned/UNKNOWN are static provenance exclusions, not native history flags.',
                            'Legacy physical signatures are authenticated in their own representation.',
                            'Copied-packet rejection may precede the new capture branch.',
                            'No claim of exhaustive projection, capsule or support guards.']})
    print('PASS: two optimizer modes;', len(outcomes[0])-1, 'controls per run', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
