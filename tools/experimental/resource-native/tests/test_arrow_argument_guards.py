#!/usr/bin/env python3
"""Focused packet/real-instantiation controls on a previously checked generated pair.

Supply --generated DIR containing all four ir8_{packet,runtime}_generated files.
This runner does not admit arbitrary source or diagnostic JSON, invoke GHC,
rewrite a packet, replace callbacks, or rebuild source. The C driver first
admits the untouched packet, then tests copied-packet forgeries and calls each
real helper exactly once during genuine generated entry execution. Use checked arrow-coordinate pairs; only reachable arrow nodes are covered.
Copied-packet rejection may occur before the new arrow branch. This is not exhaustive
Access/Env/GC qualification or a timing benchmark.
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
    args = parser.parse_args(argv)
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
        binary = directory / 'arrow-argument-guards'
        command = [cc, '-std=c11', '-' + opt, '-g', '-Wall', '-Wextra', '-Werror',
                   '-pedantic', '-fno-lto', '-I', str(BASE / 'runtime_v8'),
                   '-I', str(BASE / 'packet_v8'), '-I', str(directory),
                   str(HERE / 'arrow_argument_guard_driver.c'),
                   str(BASE / 'packet_v8/ir8_packet.c')]
        command += [str(BASE / 'runtime_v8' / name) for name in RUNTIME_SOURCES]
        command += [str(directory / 'ir8_packet_generated.c'),
                    str(directory / 'ir8_runtime_generated.c'),
                    '-Wl,--wrap=rt8_instantiate', '-Wl,--wrap=rt8_private_table',
                    '-o', str(binary)]
        run(command, directory, 'compile', cwd=directory, env=env,
            wall=60, cpu=30, memory=1024*MIB)
        run([str(binary)], directory, 'run', cwd=directory, env=env,
            wall=60, cpu=40, memory=512*MIB)
        require((directory / 'run.stderr').read_bytes() == b'', 'unexpected target stderr')
        rows = [json.loads(line) for line in (directory / 'run.stdout').read_text().splitlines()]
        require(1 < len(rows) < 10000, 'finite nonempty control output')
        summary = rows[-1]
        require(summary == dict(summary=True, packet_cases=len(rows)-9,
                                runtime_cases=8, failures=0), 'control summary/count mismatch')
        require(all(r['ok'] == 1 for r in rows[:-1]), 'independent C control failed')
        require(all(r['kind'] == 'packet' and r['status'] != 0 for r in rows[:-9]),
                'copied packet must reject')
        runtime = rows[-9:-1]
        require([r['case'] for r in runtime] == ['healthy', 'foreign-use', 'foreign-access',
                    'zero-capsule', 'entry-work', 'arrow-root-work', 'arrow-child-work', 'post-arrow-access-work'], 'runtime cases changed')
        require(runtime[0]['rc'] == 0 and runtime[0]['fault'] == 0 and
                runtime[0]['live_bytes'] == 0, 'genuine healthy execution/close failed')
        require(all(r['rc'] == 2 and r['fault'] == 8 and r['live_bytes'] > 0 and
                    r['live_bytes'] == r['retired_bytes'] for r in runtime[1:]),
                'fault retention and separate surrender must remain distinct')
        require(all(r['arrow_calls'] > 0 and r['calls'] == r['real_calls'] for r in runtime),
                'real helper interposition missing')
        outcomes.append(rows)
    require(outcomes[0] == outcomes[1], 'O0/O2 control reports differ, including work')
    require(all((source / name).read_bytes() == data for name, data in payloads.items()),
            'supplied generated files changed')
    save(output / 'results.json', {
        'status': 'pass', 'scope': 'copied-packet and real-instantiation guard controls',
        'builds': 2, 'native_runs': 2, 'controls_per_run': len(outcomes[0])-1,
        'generated_files': {name: sha(data) for name, data in payloads.items()},
        'packet_sha256': sha((BASE / 'packet_v8/ir8_packet.c').read_bytes()),
        'runtime_sha256': sha((BASE / 'runtime_v8/rir8_runtime.c').read_bytes()),
        'driver_sha256': sha((HERE / 'arrow_argument_guard_driver.c').read_bytes()),
        'coverage_limits': ['Known-valid generated references in interposition.',
                            'No arbitrary diagnostic/source admission.',
                            'No metadata mutation after admission.',
                            'Only arrow/leaf kinds actually present in the supplied program are covered.',
                            'No claim of exhaustive projection, capsule or support guards.']})
    print('PASS: two optimizer modes;', len(outcomes[0])-1, 'controls per run', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
