#!/usr/bin/env python3
"""Bounded direct-source item-4 probes, with source/tool hashes and durable logs.

These are focused host/native contracts, not full shared-corpus, guest, or
fixed-point receipts. Concurrent source edits invalidate the run explicitly.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/shared/fixtures/item4'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths = set()
    for folder, glob in [('libraries', '*.hs'), ('host/ghc', '*'), ('runtime', '*'),
                         ('tools/shared/fixtures/item4', '*')]:
        paths.update(p for p in (ROOT / folder).rglob(glob) if p.is_file()
                     and p.suffix in {'.hs', '.c', '.h'})
    manifest = json.loads((ROOT / 'shared-sources.json').read_text())
    paths.update(ROOT / entry['path'] for entry in manifest['modules'])
    paths.update([ROOT / 'shared-sources.json', Path(__file__).resolve()])
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(paths)}


def process_memory(group):
    rss = 0
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            pid = int(path.parent.name)
            if os.getpgid(pid) == group:
                # stat fields after the parenthesized comm start at field 3.
                fields = path.read_text().rsplit(')', 1)[1].split()
                rss += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, ValueError, ProcessLookupError):
            pass
    available = next(int(line.split()[1]) * 1024 for line in
                     Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
    return rss, available


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=['artifact', 'interpreter', 'host', 'native', 'core', 'builtin', 'query', 'source'], required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--gc-prefix', type=Path, default=os.environ.get('MLF_GC_PREFIX'))
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    out = args.build_dir.resolve()
    if out == ROOT or ROOT.is_relative_to(out):
        parser.error('build directory must not contain checkout')
    out.mkdir(parents=True, exist_ok=True)
    before = sources()
    receipt = {'scope': 'focused-item4-' + args.suite, 'status': 'running',
               'inputs': before, 'commands': [], 'tools': {}}
    receipt_path = out / 'receipt.json'

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')

    def tool(name):
        path = Path(shutil.which(name) or name).resolve(strict=True)
        receipt['tools'][str(path)] = sha(path)
        return str(path)

    def run(command, label, expected=0, contains=None):
        log = out / (label + '.log')
        entry = {'argv': list(map(str, command)), 'log': str(log), 'expected_exit': expected}
        receipt['commands'].append(entry)
        save()
        start = time.monotonic()
        peak = 0
        with log.open('w') as stream:
            proc = subprocess.Popen(entry['argv'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'GHC_ENVIRONMENT': '-'}, start_new_session=True)
            try:
                while proc.poll() is None:
                    rss, available = process_memory(proc.pid)
                    peak = max(peak, rss)
                    if rss > 1536 * 1024**2 or available < 3 * 1024**3 or time.monotonic() - start > args.timeout:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                        entry['guard_stopped'] = True
                        break
                    time.sleep(.2)
            except BaseException:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                raise
        entry.update(exit_code=proc.returncode, seconds=time.monotonic()-start,
                     peak_group_rss_bytes=peak, log_sha256=sha(log))
        save()
        print(log.read_text()[-12000:], end='', flush=True)
        good = proc.returncode == expected if expected is not None else proc.returncode != 0
        if not good or entry.get('guard_stopped') or (contains and contains not in log.read_text()):
            raise RuntimeError('probe failed: ' + label)

    try:
        cc = tool(args.cc)
        binary = out / 'probe'
        if args.suite == 'native':
            gc_flags = ['-lgc']
            if args.gc_prefix:
                prefix = args.gc_prefix.resolve()
                library = prefix / 'lib/libgc.a'
                receipt['tools'][str(library)] = sha(library)
                for header in (prefix / 'include').rglob('*.h'):
                    receipt['tools'][str(header)] = sha(header)
                gc_flags = ['-I' + str(prefix / 'include'), str(library)]
            run([cc, '-O0', '-std=c11', '-D_GNU_SOURCE', FIXTURES / 'NativeIO.c',
                 *gc_flags, '-lgmp', '-lm', '-pthread', '-ldl', '-o', binary], 'compile')
        else:
            ghc = tool(args.ghc)
            run([ghc, '--numeric-version'], 'ghc-version')
            run([ghc, '--print-libdir'], 'ghc-libdir')
            version = (out / 'ghc-version.log').read_text().strip()
            if version != '9.14.1':
                raise RuntimeError('expected pinned GHC 9.14.1, got ' + version)
            libdir = Path((out / 'ghc-libdir.log').read_text().strip())
            actual = libdir.parent / 'bin' / ('ghc-' + version)
            if not actual.is_file():
                raise RuntimeError('cannot identify actual GHC bindist executable: ' + str(actual))
            receipt['tools'][str(actual)] = sha(actual)
            receipt['tools'][str(libdir / 'settings')] = sha(libdir / 'settings')
            manifest = json.loads((ROOT / 'shared-sources.json').read_text())
            fixture = {'artifact': 'ArtifactIdentity.hs', 'interpreter': 'InterpreterIO.hs',
                       'host': 'HostIO.hs', 'core': 'CoreIdentity.hs', 'builtin': 'BuiltinArtifact.hs', 'query': 'QueryCache.hs', 'source': 'SourceSemantics.hs'}[args.suite]
            flags = ['-I' + str(ROOT / 'runtime'), '--make', '-j1', '-O0', '-fforce-recomp', '-fpedantic-bottoms', '-fno-state-hack', '-rtsopts',
                     '-package-env', '-', '-no-user-package-db', '-i',
                     *['-i' + str(ROOT / p) for p in manifest['source_roots']],
                     '-odir', out / 'objects', '-hidir', out / 'objects', '-o', binary]
            (out / 'objects').mkdir(exist_ok=True)
            run([ghc, *flags, FIXTURES / fixture, ROOT / 'host/ghc/cbits/host.c',
                 ROOT / 'runtime/mlf_process_supervisor.c'], 'compile')
        arguments = [binary]
        if args.suite == 'source':
            arguments.extend(['+RTS', '-M700m', '-RTS'])
        if args.suite == 'query':
            arguments.append(out / ('cache-' + str(time.time_ns())))
        run(arguments, 'positive')
        if args.suite == 'native':
            for mode, diagnostic in [('surrogate', 'Unicode'), ('panic', 'pure panic'), ('uncaught', 'Runtime: user error (hé😀)')]:
                run([binary, mode], mode, expected=1, contains=diagnostic)
        receipt['status'] = 'passed'
    except Exception as exc:
        receipt.update(status='failed', error=str(exc))
    finally:
        after = sources()
        closure = {'tools/shared/test_item4_contracts.py', 'shared-sources.json',
                   'runtime/mlf_process_supervisor.c', 'host/ghc/cbits/host.c'}
        closure.update(k for k in before if k.startswith('runtime/') and k.endswith('.h'))
        if args.suite == 'native':
            closure.update(['runtime/mlf_runtime.c', 'tools/shared/fixtures/item4/NativeIO.c'])
        else:
            text = (out / 'compile.log').read_text() if (out / 'compile.log').exists() else ''
            for name in re.findall(r'Compiling\s+[\w.]+\s+\(\s*([^,\n]+),', text):
                path = Path(name.strip())
                if not path.is_absolute(): path = ROOT / path
                closure.add(str(path.resolve().relative_to(ROOT)))
        receipt['compiled_input_closure'] = sorted(closure)
        receipt['changed_inputs'] = sorted(k for k in closure if before.get(k) != after.get(k))
        if receipt['changed_inputs']:
            receipt['status'] = 'invalidated-concurrent-source-change'
        receipt['outputs'] = {str(p.relative_to(out)): sha(p) for p in out.glob('*')
                              if p.is_file() and p != receipt_path}
        save()
    print(str(receipt_path) + ': ' + receipt['status'])
    if receipt['status'] != 'passed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
