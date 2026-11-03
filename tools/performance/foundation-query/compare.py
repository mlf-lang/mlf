#!/usr/bin/env python3
"""Run the Foundation cold/warm/edit comparison on two actual emlf binaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time


def framed(fields):
    return ''.join(f'{len(field)}:{field}' for field in fields)


def crate_spec(modules, name, cache, builtin):
    sources = framed([framed([module, str(path)]) for module, path in modules])
    return framed(['MLF-CRATE-1', name, '', 'false', sources, '', str(cache), str(builtin)])


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_crate(binary, spec, prefix, verify_all=False):
    argv = [str(binary), '--compile-crate', str(spec), '-o', str(prefix)]
    if verify_all:
        argv.insert(1, '-Zincremental-verify-ich')
    env = dict(os.environ, GHCRTS='', GHC_ENVIRONMENT='-', LANG='C.UTF-8', LC_ALL='C.UTF-8', TZ='UTC')
    with prefix.with_suffix('.stdout').open('xb') as out, prefix.with_suffix('.stderr').open('xb') as err:
        start = time.monotonic_ns()
        process = subprocess.Popen(argv, cwd=spec.parent, env=env, stdout=out, stderr=err,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        timeout = threading.Timer(900, lambda: os.killpg(process.pid, signal.SIGKILL))
        timeout.start()
        try:
            _, status, usage = os.wait4(process.pid, 0)
            process.returncode = os.waitstatus_to_exitcode(status)
        finally:
            timeout.cancel()
        seconds = (time.monotonic_ns() - start) / 1e9
    if process.returncode or prefix.with_suffix('.stderr').stat().st_size:
        raise RuntimeError(f'Compiler failed. See {prefix.with_suffix(".stderr")}')
    rss = usage.ru_maxrss if sys.platform == 'darwin' else usage.ru_maxrss * 1024
    return dict(wall_s=seconds, cpu_s=usage.ru_utime + usage.ru_stime, rss_bytes=rss)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('--baseline-label', choices=['25','32'], default='25')
    parser.add_argument('candidate', type=Path)
    parser.add_argument('foundation', type=Path, help='mlf-foundation directory from the PR 25 checkout')
    parser.add_argument('output', type=Path, help='new, empty study directory')
    parser.add_argument('--first-install', action='store_true',
                        help='time cold compiles starting with neither a builtin nor a query cache')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    binaries = {args.baseline_label: args.baseline.resolve(strict=True), 'candidate': args.candidate.resolve(strict=True)}
    sources = output / 'input'
    shutil.copytree(args.foundation.resolve() / 'Bootstrap', sources / 'Bootstrap')
    modules = [('Bootstrap.' + f.stem, f) for f in sorted((sources / 'Bootstrap').glob('*.hs'))]
    if len(modules) != 14:
        raise ValueError('Expected the 14 Foundation modules of PR 25')
    version = sources / 'Bootstrap/Version.hs'
    original = version.read_bytes()
    if original.count(b'version = "0.3.0"') != 1:
        raise ValueError('Unexpected Foundation version source')
    edited = original.replace(b'version = "0.3.0"', b'version = "0.3.1"')
    cache, builtin = output / 'cache', output / 'builtin'
    spec = output / 'foundation.spec'
    spec.write_text(crate_spec(modules, 'mlf-foundation/0.3.0/library', cache, builtin / 'unit'))
    if not args.first_install:
        for arm, binary in binaries.items():
            with tempfile.TemporaryDirectory(dir=output) as tmp:
                seed = Path(tmp)
                seed_spec = seed / 'seed.spec'
                seed_spec.write_text(crate_spec([('Bootstrap.Version', version)], 'seed', seed / 'cache', seed / 'builtin/unit'))
                compile_crate(binary, seed_spec, seed / 'unit')
                shutil.copytree(seed / 'builtin', output / ('builtin-' + arm))
    order = [args.baseline_label, 'candidate', 'candidate', args.baseline_label]
    record = dict(order=order, first_install=args.first_install, complete=False, binaries={k: digest(v) for k, v in binaries.items()},
                  sources={n: digest(f) for n, f in modules}, samples=[])
    def save():
        (output / 'results.json').write_text(json.dumps(record, indent=2) + '\n')
    save()
    references = {}
    try:
        for index, arm in enumerate(order):
            run = output / f'{index}-{arm}'
            run.mkdir()
            if not args.first_install:
                shutil.copytree(output / ('builtin-' + arm), builtin)
            version.write_bytes(original)
            stages = [('cold', (504, 0))]
            if not args.first_install:
                stages.extend([('warm', (0, 504)), ('edit', (1, 503))])
            for stage, expected in stages:
                if stage == 'edit':
                    version.write_bytes(edited)
                prefix = run / stage
                stats = compile_crate(binaries[arm], spec, prefix)
                report = json.loads(prefix.with_suffix('.queries').read_text())
                counts = (report['inferred_groups'], report['reused_groups'])
                if counts != expected:
                    raise ValueError(f'{arm}/{stage}: group counts {counts}')
                artifacts = [digest(prefix.with_suffix(ext)) for ext in ('.mlfci', '.mlfco')]
                identity = (artifacts, report)
                if references.setdefault((arm, stage), identity) != identity:
                    raise ValueError(f'{arm}/{stage}: repeated compiler output differs')
                size = sum(f.stat().st_size for f in cache.rglob('*') if f.is_file())
                record['samples'].append(dict(index=index, arm=arm, stage=stage, counts=counts,
                                              artifact_sha256=artifacts, cache_bytes=size, **stats))
                save()
            cache.rename(run / 'cache')
            builtin.rename(run / 'builtin')
        record['complete'] = True
        save()
    finally:
        version.write_bytes(original)


if __name__ == '__main__':
    main()
