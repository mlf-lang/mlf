#!/usr/bin/env python3
"""Bounded ABI controls against the actual pinned 2916 runtime (not a mutant).

Materializes immutable Git blobs into a fresh output directory. Four old guard
families must fail against current v3, and v3 must fail against old 2916. Two
positive links prove both runtimes are otherwise linkable. This does not qualify
old compiler output, the full corpus, bootstrap, or cross-platform execution.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
# Preserve original provenance while pinning identical content across history transport.
LEGACY_COMMIT = '2916c477468efaa24ae2c76e8b2f41e5f15236a6'
LEGACY_SOURCE_TREE = '7efa13e6a64c0445ebcf891c4e15694321a43780'
CURRENT_GUARD = 'mlf_require_haskell_boundary_v3_abi'
OLD_GUARDS = ['mlf_require_compact_gc_abi', 'mlf_require_process_supervisor_v1_abi',
              'mlf_require_async_completion_v2_abi', 'mlf_require_haskell_boundary_v2_abi']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    paths = [Path(__file__).resolve()]
    paths += sorted(p for p in (ROOT / 'runtime').rglob('*')
                    if p.is_file() and p.suffix in {'.c', '.h'})
    return {str(p.relative_to(ROOT)): sha(p) for p in paths}


def memory(group):
    rss = 0
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            if os.getpgid(int(path.parent.name)) == group:
                fields = path.read_text().rsplit(')', 1)[1].split()
                rss += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, ValueError, ProcessLookupError):
            pass
    available = next(int(line.split()[1]) * 1024 for line in
                     Path('/proc/meminfo').read_text().splitlines()
                     if line.startswith('MemAvailable:'))
    return rss, available


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--git', default='git')
    parser.add_argument('--gc-prefix', type=Path, default=os.environ.get('MLF_GC_PREFIX'))
    parser.add_argument('--timeout', type=int, default=120, help='per-command seconds')
    args = parser.parse_args()
    out = args.build_dir.resolve()
    if out == ROOT or ROOT.is_relative_to(out):
        parser.error('build directory must not contain the checkout')
    if out.exists() and any(out.iterdir()):
        parser.error('use a new/empty build directory; previous evidence is never overwritten')
    if args.gc_prefix is None or args.timeout <= 0:
        parser.error('--gc-prefix and positive --timeout are required')
    out.mkdir(parents=True, exist_ok=True)
    before = inputs()
    receipt = {'scope': 'focused-actual-historical-runtime-abi', 'status': 'running',
               'legacy_commit': LEGACY_COMMIT, 'legacy_source_tree': LEGACY_SOURCE_TREE, 'inputs': before, 'tools': {},
               'historical_blobs': {}, 'commands': [], 'outputs': {},
               'resource_limits': {'command_seconds': args.timeout, 'max_rss_bytes': 1536 * 1024**2,
                                   'minimum_available_bytes': 3 * 1024**3}}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def tool(name):
        path = Path(shutil.which(name) or name).resolve(strict=True)
        receipt['tools'][str(path)] = sha(path)
        return str(path)

    def run(argv, label, expected=0, capture=None, symbol=None):
        log = out / (label + '.log')
        entry = {'argv': list(map(str, argv)), 'expected_exit': expected, 'log': str(log)}
        receipt['commands'].append(entry)
        save()
        start = time.monotonic()
        peak = 0
        with log.open('wb') as stream:
            output = capture.open('wb') if capture else stream
            try:
                proc = subprocess.Popen(entry['argv'], cwd=ROOT, stdout=output, stderr=stream,
                                        env=os.environ, start_new_session=True)
                try:
                    while proc.poll() is None:
                        rss, available = memory(proc.pid)
                        peak = max(peak, rss)
                        if (rss > 1536 * 1024**2 or available < 3 * 1024**3 or
                                time.monotonic() - start > args.timeout):
                            os.killpg(proc.pid, signal.SIGKILL)
                            proc.wait()
                            entry['guard_stopped'] = True
                            break
                        time.sleep(.1)
                except BaseException:
                    if proc.poll() is None:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    raise
            finally:
                if capture:
                    output.close()
        entry.update(exit=proc.returncode, seconds=time.monotonic() - start,
                     peak_rss_bytes=peak, log_sha256=sha(log))
        if capture:
            entry.update(stdout=str(capture), stdout_sha256=sha(capture))
        save()
        if entry.get('guard_stopped') or proc.returncode != expected:
            raise RuntimeError(label + ': unexpected exit; inspect ' + str(log))
        text = log.read_text(errors='replace')
        if symbol and (symbol not in text or not any(marker in text for marker in
                      ['undefined reference', 'undefined symbol', 'Undefined symbols'])):
            raise RuntimeError(label + ': rejection was not the required missing ABI symbol')
        return capture.read_bytes() if capture else text

    try:
        cc, git = tool(args.cc), tool(args.git)
        gc = args.gc_prefix.resolve(strict=True)
        archive = gc / 'lib/libgc.a'
        receipt['external_inputs'] = {str(archive): sha(archive)}
        receipt['external_inputs'].update({str(p): sha(p) for p in sorted((gc / 'include').rglob('*.h'))})
        run([cc, '--version'], 'cc-version')
        run([git, '--version'], 'git-version')
        resolved = run([git, 'rev-parse', LEGACY_SOURCE_TREE + '^{tree}'], 'legacy-source-tree').strip()
        if resolved != LEGACY_SOURCE_TREE:
            raise RuntimeError('historical source tree identity mismatch')
        receipt['legacy_runtime_tree'] = run([git, 'rev-parse', LEGACY_SOURCE_TREE + ':runtime'], 'legacy-tree').strip()
        records = run([git, 'ls-tree', '-rz', '--full-tree', LEGACY_SOURCE_TREE, '--', 'runtime'],
                      'legacy-inventory', capture=out / 'legacy-inventory.bin')
        old = out / 'legacy'
        for index, record in enumerate(records.split(b'\0')):
            if not record:
                continue
            descriptor, raw_path = record.split(b'\t', 1)
            mode, kind, oid = descriptor.decode().split()
            path = Path(raw_path.decode())
            if (mode not in {'100644', '100755'} or kind != 'blob' or path.is_absolute()
                    or '..' in path.parts or path.parts[0] != 'runtime'):
                raise RuntimeError('unsafe or unsupported historical runtime entry')
            target = old / path
            target.parent.mkdir(parents=True, exist_ok=True)
            run([git, 'cat-file', 'blob', oid], 'legacy-blob-' + str(index), capture=target)
            receipt['historical_blobs'][str(path)] = {'git_blob': oid, 'sha256': sha(target)}
        libraries = [archive, '-lgmp', '-lm', '-lpthread', '-ldl']
        for label, folder in [('current', ROOT / 'runtime'), ('legacy', old / 'runtime')]:
            run([cc, '-O0', '-std=c11', '-I' + str(folder), '-I' + str(gc / 'include'),
                 '-c', folder / 'mlf_runtime.c', '-o', out / (label + '.o')], label + '-compile')
            receipt['outputs'][label + '.o'] = sha(out / (label + '.o'))
        cases = [(g, 'current', False) for g in OLD_GUARDS]
        cases += [(CURRENT_GUARD, 'legacy', False), (CURRENT_GUARD, 'current', True),
                  ('mlf_require_async_completion_v2_abi', 'legacy', True)]
        for index, (guard, runtime, accepts) in enumerate(cases):
            label = 'case-' + str(index) + '-' + runtime
            source = out / (label + '.c')
            source.write_text('extern void ' + guard + '(void);\nint main(void) { ' + guard + '(); return 0; }\n')
            binary = out / label
            run([cc, source, out / (runtime + '.o'), *libraries, '-o', binary], label + '-link',
                expected=0 if accepts else 1, symbol=None if accepts else guard)
            receipt['outputs'][source.name] = sha(source)
            if accepts:
                run([binary], label + '-run')
                receipt['outputs'][binary.name] = sha(binary)
        receipt['changed_inputs'] = sorted(k for k in before if inputs().get(k) != before[k])
        if receipt['changed_inputs']:
            raise RuntimeError('compiled current inputs changed during run; evidence invalidated')
        receipt['status'] = 'passed'
        save()
        print('PASS actual historical runtime ABI controls: ' + str(out / 'receipt.json'))
    except BaseException as exc:
        receipt.update(status='failed', error=str(exc), inputs_unchanged=inputs() == before)
        save()
        raise


if __name__ == '__main__':
    main()
