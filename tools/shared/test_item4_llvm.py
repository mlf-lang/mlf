#!/usr/bin/env python3
"""Bounded item-4 checked xMLF -> LLVM -> native O0/O2 contract probe.

The source-unit mode instead starts with actual source parsing/inference through
Compiler.compile, then emits LLVM; both its emitter and guest source are hashed.

Includes a SYNTHETIC missing-ABI-symbol link control, not a historical runtime
qualification. This is not a full corpus or fixed-point suite.
Every run records source/tool hashes, exact commands, logs, and output hashes.
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
FIXTURE_NAMES = {'ordinary': 'EmitIO.hs', 'stack': 'EmitStack.hs', 'unit': 'EmitUnit.hs',
                 'unit-fast': 'EmitUnitFast.hs', 'source-unit': 'EmitSourceUnit.hs'}
SOURCE_UNIT = ROOT / 'tools/shared/fixtures/item4/SourceUnit64.hs'


def input_key(path):
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def fixture_for_suite(suite):
    return ROOT / 'tools/shared/fixtures/item4' / FIXTURE_NAMES[suite]


def emission_plan(suite, emitter, llvm):
    if suite == 'source-unit':
        return [emitter, SOURCE_UNIT, llvm], '11\n63\n42\n'
    return [emitter, llvm], EXPECTED if suite == 'ordinary' else '101\n102\n103\n104\n63\n105\nDONE\n'


def compiled_closure(fixture, before, build_log, suite):
    closure = {input_key(__file__), input_key(fixture), 'shared-sources.json',
               'host/ghc/cbits/host.c', 'runtime/mlf_runtime.c', 'runtime/mlf_process_supervisor.c'}
    if suite == 'source-unit':
        closure.add(input_key(SOURCE_UNIT))
    closure.update(k for k in before if k.startswith('runtime/') and k.endswith('.h'))
    for name in re.findall(r'Compiling\s+[\w.]+\s+\(\s*([^,\n]+),', build_log):
        path = Path(name.strip())
        closure.add(input_key(path if path.is_absolute() else ROOT / path))
    return closure

GUARD = 'mlf_require_haskell_boundary_v3_abi'
PREVIOUS_GUARD = 'mlf_require_haskell_boundary_v2_abi'
EXPECTED = 'roundtrip λ😀\n65\n0\ncaught λ😀\nDONE\n'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    paths = {Path(__file__).resolve(), SOURCE_UNIT, ROOT / 'shared-sources.json'}
    paths.update(fixture_for_suite(suite) for suite in FIXTURE_NAMES)
    for folder in ['libraries', 'host/ghc', 'runtime']:
        paths.update(p for p in (ROOT / folder).rglob('*')
                     if p.is_file() and p.suffix in {'.hs', '.h', '.c'})
    return {input_key(p): sha(p) for p in sorted(paths)}


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
    parser.add_argument('--suite', choices=FIXTURE_NAMES, default='ordinary')
    parser.add_argument('--ghc', default='ghc')
    parser.add_argument('--clang', default='clang')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--gc-prefix', type=Path, default=os.environ.get('MLF_GC_PREFIX'))
    parser.add_argument('--timeout', type=int, default=300, help='per-command seconds')
    args = parser.parse_args()
    out = args.build_dir.resolve()
    if out == ROOT or ROOT.is_relative_to(out):
        parser.error('build directory must not contain the checkout')
    if out.exists() and any(out.iterdir()):
        parser.error('use a new or empty build directory; previous evidence is never overwritten')
    if args.gc_prefix is None or args.timeout <= 0:
        parser.error('--gc-prefix and a positive --timeout are required')
    out.mkdir(parents=True, exist_ok=True)
    before = sources()
    fixture = fixture_for_suite(args.suite)
    receipt = {'scope': ('focused-item4-source-compiler-llvm-native-' if args.suite == 'source-unit' else 'focused-item4-checked-llvm-native-') + args.suite, 'status': 'running',
               'synthetic_control': 'new runtime with ONLY new ABI guard renamed; not historical runtime',
               'inputs': before, 'tools': {}, 'commands': [], 'outputs': {},
               'environment': {k: os.environ.get(k) for k in ['PATH', 'LD_LIBRARY_PATH', 'MLF_GC_PREFIX']}}

    def save():
        (out / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')

    def tool(name):
        path = Path(shutil.which(name) or name).resolve(strict=True)
        receipt['tools'][str(path)] = sha(path)
        return str(path)

    def run(command, label, reject=False, contains=None, exact=None):
        log = out / (label + '.log')
        entry = {'argv': list(map(str, command)), 'log': str(log),
                 'expected': 1 if reject else 0}
        receipt['commands'].append(entry)
        save()
        start = time.monotonic()
        peak = 0
        with log.open('w') as stream:
            proc = subprocess.Popen(entry['argv'], cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                    env={**os.environ, 'GHC_ENVIRONMENT': '-',
                                         'GC_INITIAL_HEAP_SIZE': '16777216'}, start_new_session=True)
            try:
                while proc.poll() is None:
                    rss, available = memory(proc.pid)
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
        entry.update(exit=proc.returncode, seconds=time.monotonic() - start,
                     peak_rss_bytes=peak, log_sha256=sha(log))
        save()
        text = log.read_text()
        if entry.get('guard_stopped') or proc.returncode != (1 if reject else 0):
            raise RuntimeError(label + ' unexpected exit; see ' + str(log))
        if contains is not None and contains not in text:
            raise RuntimeError(label + ' lacks required diagnostic: ' + contains)
        if exact is not None and text != exact:
            raise RuntimeError(label + ' output differs from expected; see ' + str(log))
        return text

    try:
        ghc, clang, cc = tool(args.ghc), tool(args.clang), tool(args.cc)
        gc = args.gc_prefix.resolve(strict=True)
        archive = gc / 'lib/libgc.a'
        receipt['external_inputs'] = {str(archive): sha(archive)}
        receipt['external_inputs'].update({str(p): sha(p) for p in sorted((gc / 'include').rglob('*.h'))})
        for name, executable in [('ghc', ghc), ('clang', clang), ('cc', cc)]:
            run([executable, '--version'], name + '-version')
        version = run([ghc, '--numeric-version'], 'ghc-numeric-version').strip()
        if version != '9.14.1':
            raise RuntimeError('expected pinned GHC 9.14.1, got ' + version)
        libdir = Path(run([ghc, '--print-libdir'], 'ghc-libdir').strip())
        actual = libdir.parent / 'bin' / ('ghc-' + version)
        receipt['tools'][str(actual)] = sha(actual)
        receipt['tools'][str(libdir / 'settings')] = sha(libdir / 'settings')
        manifest = json.loads((ROOT / 'shared-sources.json').read_text())
        objects = out / 'objects'
        objects.mkdir()
        c_objects = []
        for label, source in [('host', 'host/ghc/cbits/host.c'), ('supervisor', 'runtime/mlf_process_supervisor.c')]:
            obj = out / (label + '.o')
            run([cc, '-O0', '-std=c11', '-I' + str(ROOT / 'runtime'), '-c', ROOT / source, '-o', obj], 'compile-' + label)
            c_objects.append(obj)
        flags = ['--make', '-j1', '-O0', '-fpedantic-bottoms', '-fno-state-hack', '-package-env', '-', '-i']
        flags += ['-i' + str(ROOT / root) for root in manifest['source_roots']]
        emitter = out / 'emit-item4-io'
        run([ghc, *flags, '-odir', objects, '-hidir', objects, fixture, *c_objects, '-o', emitter], 'build-emitter')
        if args.suite != 'stack':
            llvm = out / 'program.ll'
            emission, expected = emission_plan(args.suite, emitter, llvm)
            run(emission, 'emit-llvm')
            programs = [('program', llvm, False, expected)]
        else:
            run([emitter, out], 'emit-llvm')
            stack = 'CallStack (from HasCallStack):\n  inner, called at file.hs:10:2 in pkg:Mod\n  outer, called at file.hs:10:2 in pkg:Mod\n'
            programs = [
                ('success', out / 'success.ll', False, stack + '\ncaught stack\nbottom stack ignored\nbottom message ignored\nSTACK DONE\n'),
                ('uncaught', out / 'uncaught.ll', True, 'Runtime: user error (message)\n' + stack),
                ('nested', out / 'nested.ll', True, 'Runtime: user error (c)\nWhile handling user error (b)\n'),
                ('active', out / 'active.ll', True, 'Runtime: user error (c)\nWhile handling user error (a)\nWhile handling user error (b)\n')]
        libraries = [archive, '-lgmp', '-lm', '-lpthread', '-ldl']
        common = ['-std=c11', '-I' + str(ROOT / 'runtime'), '-I' + str(gc / 'include')]
        for mode, llvm, rejects, expected in programs:
            if GUARD not in llvm.read_text():
                raise RuntimeError('emitted LLVM lacks new ABI guard: ' + mode)
            receipt['outputs'][llvm.name] = sha(llvm)
            for level in ['0', '2']:
                label = mode + '-O' + level
                binary = out / label
                run([clang, '-O' + level, *common, llvm, ROOT / 'runtime/mlf_runtime.c', *libraries, '-o', binary], label + '-build')
                run([binary], label + '-run', reject=rejects, exact=expected)
                receipt['outputs'][binary.name] = sha(binary)
        if args.suite == 'unit-fast':
            text = programs[0][1].read_text()
            if 'ret ptr inttoptr (i64 12 to ptr)' not in text:
                raise RuntimeError('optimized unit fixture did not expose canonical unit returns')
            mutant = out / 'wrong-unit-tag.ll'
            mutant.write_text(text.replace('ret ptr inttoptr (i64 12 to ptr)', 'ret ptr inttoptr (i64 4 to ptr)'))
            binary = out / 'wrong-unit-tag'
            run([clang, '-O0', *common, mutant, ROOT / 'runtime/mlf_runtime.c', *libraries, '-o', binary], 'wrong-unit-tag-build')
            run([binary], 'wrong-unit-tag-run', reject=True, contains='non-exhaustive')
            receipt['outputs'].update({mutant.name: sha(mutant), binary.name: sha(binary)})
        llvm = programs[0][1]
        original = (ROOT / 'runtime/mlf_runtime.c').read_text()
        if original.count(GUARD) != 1:
            raise RuntimeError('synthetic-control assumption failed: guard must occur exactly once in runtime C')
        synthetic = out / 'synthetic-stale-runtime.c'
        synthetic.write_text(original.replace(GUARD, 'mlf_synthetic_legacy_dummy_abi'))
        rejection = run([clang, '-O0', *common, llvm, synthetic, *libraries, '-o', out / 'must-not-link'],
                        'synthetic-stale-link', reject=True, contains=GUARD)
        if not any(word in rejection for word in ['undefined reference', 'undefined symbol', 'Undefined symbols']):
            raise RuntimeError('synthetic control failed for a reason other than an undefined symbol')
        old_llvm = out / 'synthetic-old-guard.ll'
        old_llvm.write_text(llvm.read_text().replace(GUARD, PREVIOUS_GUARD))
        old_rejection = run([clang, '-O0', *common, old_llvm, ROOT / 'runtime/mlf_runtime.c',
                             *libraries, '-o', out / 'old-must-not-link'],
                            'synthetic-old-guard-link', reject=True, contains=PREVIOUS_GUARD)
        if not any(word in old_rejection for word in ['undefined reference', 'undefined symbol', 'Undefined symbols']):
            raise RuntimeError('reverse old-guard control did not fail at symbol resolution')
        receipt['outputs'].update({llvm.name: sha(llvm), 'synthetic-stale-runtime.c': sha(synthetic),
                                   'synthetic-old-guard.ll': sha(old_llvm)})
        closure = compiled_closure(fixture, before, (out / 'build-emitter.log').read_text(), args.suite)
        after = sources()
        receipt['compiled_input_closure'] = sorted(closure)
        receipt['changed_inputs'] = sorted(k for k in closure if before.get(k) != after.get(k))
        if receipt['changed_inputs']:
            raise RuntimeError('compiled source inputs changed during run; evidence invalidated')
        receipt['status'] = 'passed'
        save()
        print('PASS item4 LLVM O0/O2 and synthetic missing-ABI-symbol control: ' + str(out / 'receipt.json'))
    except BaseException as exc:
        receipt['status'] = 'failed'
        receipt['error'] = str(exc)
        receipt['inputs_unchanged'] = sources() == before
        save()
        raise


if __name__ == '__main__':
    main()
