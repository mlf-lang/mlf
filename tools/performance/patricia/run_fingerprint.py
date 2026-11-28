#!/usr/bin/env python3
"""Run maintained Int64 fingerprint controls and inspect current compiler Core.

The independent arithmetic oracle, finite inputs and expected output are ordinary
test files. Qualification executes explicit O0, O2 and Separate stages; it does
not rewrite or execute a historical Python driver.
"""
from pathlib import Path
import argparse
import importlib.util
import re
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools/testing'))
from receipt_selection import inventory_json, select

PREFIX = 'patricia-fingerprint/'
LABELS = ['current-O0','current-O2','actual-separate']
CONTROLS = HERE / 'controls/fingerprint'
CONTROL_FILES = ('Oracle.hs', 'Probe.hs', 'Tests.hs')
RULES = ('mlf/fingerprintIntStep/65599', 'mlf/fingerprintIntStep/131')
PACKAGES = ('base', 'array', 'bytestring', 'text', 'containers', 'directory')
LIMITS = {'address_space_per_process_bytes': 6 * 1024**3,
          'disk_free_floor_bytes': 5 * 1024**3,
          'host_available_floor_bytes': 3 * 1024**3,
          'max_work_bytes': 3 * 1024**3,
          'process_tree_rss_bytes': 5 * 1024**3, 'wall_seconds': 1200}


def require(condition, message):
    if not condition:
        raise ValueError(message)

def machine_worker(text, name, worker=True):
    # GHC may retain a $w worker and forwarding wrapper, or inline the same
    # machine arithmetic into the public binding. Inspect actual binding RHSs,
    # never an unfolding annotation or arithmetic in a different binding.
    def bindings(symbol):
        pattern=r'^(?P<symbol>(?:[A-Za-z][\w.]*\.)?'+re.escape(symbol)+r')[ \t]*(?:\n[ \t]*)?='
        result=[]
        for block in text.split('-- RHS size:'):
            matches=list(re.finditer(pattern,block,re.M))
            if len(matches)>1:raise ValueError('unique Int64 Core worker '+name)
            if matches:result.append((matches[0]['symbol'],block[matches[0].end():]))
        if len(result)>1:raise ValueError('unique Int64 Core worker '+name)
        return result
    public=bindings(name)
    workers=bindings('$w'+name) if worker else []
    if not workers and not public:raise ValueError('unique Int64 Core worker '+name)
    operations=['timesInt64#','plusInt64#','remInt64#']
    for _,body in workers+public:
        if 'fingerprintIntStep' in body or any(op in body for op in ['integerMul','integerAdd','integerRem']):
            raise ValueError('retired Integer narrowing path in '+name)
    if workers and public:
        # The retained GHC wrapper unboxes the first Int64 argument and tail-calls
        # this exact worker with both original arguments in order. A mere mention
        # (including an unused let or a different qualified worker) is not proof.
        identifier=r"[A-Za-z][\w']*"
        forwarding=(r'\s*\\\s*\((?P<a>'+identifier+r')\s*::\s*M\.Int\)\s*'
                    r'\((?P<c>'+identifier+r')\s*::\s*M\.Int\)\s*->\s*'
                    r'case\s+(?P=a)\s+of\s*\{\s*'
                    r'ghc-internal:GHC\.Internal\.Int\.I64#\s+(?P<u>'+identifier+r')\s*->\s*'
                    +re.escape(workers[0][0])+r'\s+(?P=u)\s+(?P=c)\s*\}\s*')
        matched=re.fullmatch(forwarding,public[0][1])
        if matched is None or len({matched['a'],matched['c'],matched['u']})!=3:
            raise ValueError('ambiguous Int64 Core worker '+name)
    body=(workers or public)[0][1]
    if not all(op in body for op in operations):
        raise ValueError('direct Int64 arithmetic missing '+name)


def verify_int64_core(text):
    for name in ['unmatchedMultiplier','unmatchedModulus']:machine_worker(text,name)

def verify_no_retired_rules(counts, optimization):
    if optimization not in ('0','2') or counts!={'mlf/fingerprintIntStep/65599':0,'mlf/fingerprintIntStep/131':0}:
        raise ValueError('retired Integer narrowing rules must be absent')

def verify_separate_int64(text, counts):
    verify_no_retired_rules(counts,'2')
    machine_worker(text,'fingerprintStateChars',worker=False)


def tree_hashes(H, root):
    paths = sorted(root.rglob('*'))
    require(not any(path.is_symlink() for path in paths), 'symlink in input/output inventory')
    return {str(path.relative_to(root)): H.sha(path) for path in paths if path.is_file()}


def rule_counts(path):
    text = path.read_text() if path.exists() else ''
    return {name: text.count('Rule: ' + name + '\n') for name in RULES}


def verify_resolution(text, expected):
    rows = re.findall(r'^\[\s*\d+ of\s*\d+\]\s+Compiling\s+(\S+)\s+\(\s*(.+?),', text, re.M)
    require(len(rows) == len(expected) and len({name for name, _ in rows}) == len(rows),
            'unexpected/duplicate compiled module inventory')
    require({name: str(Path(path).resolve()) for name, path in rows} ==
            {name: str(Path(path).resolve()) for name, path in expected.items()},
            'compiler resolved a different control/production source')


def run_probe(H, source, controls, out, build, host_hashes, expectations, opt, run):
    label = 'current-O' + opt
    folder = out / label
    snap, objects = folder / 'source', folder / 'objects'
    objects.mkdir(parents=True)
    snap.mkdir()
    shutil.copytree(source / 'host/ghc', snap / 'host/ghc')
    require(tree_hashes(H, snap / 'host/ghc') == host_hashes, 'host snapshot differs')
    for name in CONTROL_FILES:
        shutil.copyfile(controls / name, snap / name)
        require(H.sha(snap / name) == H.sha(controls / name), 'control snapshot differs')
    (snap / 'Main.hs').write_text('{-# OPTIONS_GHC -O0 #-}\nmodule Main where\n'
                                 'import qualified Tests\nmain :: IO ()\nmain = Tests.main\n')
    snapshot_inputs = tree_hashes(H, snap)
    cobjects = []
    for name, relative in [('host', 'host/ghc/cbits/host.c'),
                           ('supervisor', 'runtime/mlf_process_supervisor.c')]:
        obj = folder / (name + '.o')
        run(label + '-c-' + name, [build['cc']['path'], '-O2', '-std=c11',
            '-I' + str(source / 'runtime'), '-c', source / relative, '-o', obj])
        cobjects.append(obj)
    command = [build['ghc']['path'], '--make', '-j1', '-O' + opt,
        '-fpedantic-bottoms', '-fno-state-hack', '-rtsopts=ignoreAll',
        '-package-env', '-', '-clear-package-db', '-global-package-db',
        '-no-user-package-db', '-hide-all-packages', '-i',
        '-i' + str(snap / 'host/ghc'), '-i' + str(snap),
        '-odir', objects, '-hidir', objects, '-dcore-lint',
        '-ddump-rule-rewrites', '-ddump-simpl', '-ddump-to-file']
    for package in PACKAGES:
        command.extend(['-package', package])
    command.extend([snap / 'Main.hs', *cobjects, '-o', folder / 'controls'])
    stdout, stderr = run(label + '-build', command, snap)
    expected = {name: snap / 'host/ghc' / (name.replace('.', '/') + '.hs')
                for name in ('MLF.Host.Base', 'MLF.Host.Async', 'MLF.Host.IO', 'MLF.Primitive')}
    expected.update({name: snap / (name + '.hs') for name in ('Oracle', 'Probe', 'Tests', 'Main')})
    verify_resolution((stdout + stderr).decode(), expected)
    stdout, stderr = run(label + '-run', [folder / 'controls'], snap)
    require(stdout == expectations['expected_stdout'].encode() and
            stderr == expectations['expected_stderr'].encode(),
            label + ' exact finite-control output mismatch')
    counts = rule_counts(snap / 'Probe.dump-rule-rewrites')
    verify_no_retired_rules(counts, opt)
    if opt == '2':
        verify_int64_core((snap / 'Probe.dump-simpl').read_text())
    require(all(H.sha(snap / path) == digest for path, digest in snapshot_inputs.items()),
            'control/host snapshot input changed')
    return {'optimization': opt, 'complete': True, 'actual_rule_firings': counts,
            'executable_sha256': H.sha(folder / 'controls'),
            'resolved_modules': {name: {'path': str(path), 'sha256': H.sha(path)}
                                 for name, path in expected.items()},
            'dump_hashes': {str(path.relative_to(out)): H.sha(path)
                            for path in snap.glob('Probe.dump-*')}}


def run_separate(H, source, producer, out, build, object_hashes, run):
    # Compile the actual production source using a copy of its complete object
    # closure. Only Separate may change; ordinary producer objects stay untouched.
    actual = out / 'actual-source'
    objects = actual / 'objects'
    shutil.copytree(producer / 'objects', objects)
    require(tree_hashes(H, objects) == object_hashes, 'copied producer objects differ')
    for suffix in ('.hi', '.o'):
        (objects / ('Bootstrap/Separate' + suffix)).unlink()
    flags = [str(objects) if value == str(producer / 'objects') else value
             for value in build['flags']]
    command = [build['ghc']['path'], '--make', '-no-link', '-j1', *flags,
        '-dcore-lint', '-ddump-rule-rewrites', '-ddump-simpl', '-ddump-to-file',
        '-ddump-file-prefix', str(actual / 'Separate'),
        source / 'libraries/mlf-crates/Bootstrap/Separate.hs']
    stdout, stderr = run('actual-separate', command)
    verify_resolution((stdout + stderr).decode(),
                      {'Bootstrap.Separate': source / 'libraries/mlf-crates/Bootstrap/Separate.hs'})
    counts = rule_counts(actual / 'Separate.dump-rule-rewrites')
    verify_separate_int64((actual / 'Separate.dump-simpl').read_text(), counts)
    actual_hashes = tree_hashes(H, objects)
    require(set(actual_hashes) == set(object_hashes), 'actual proof object inventory changed')
    require(all(actual_hashes[path] == digest for path, digest in object_hashes.items()
                if path not in ('Bootstrap/Separate.hi', 'Bootstrap/Separate.o')),
            'actual proof rewrote an unrelated copied object')
    return {'only_Separate_recompiled': True, 'actual_literal_rule_firings': counts,
            'dump_hashes': {str(path.relative_to(out)): H.sha(path)
                            for path in actual.glob('Separate.dump-*')}}


def qualify(H, source, producer, out, planned, controls=CONTROLS, driver_inputs=None):
    source, producer, out = source.resolve(), producer.resolve(strict=True), out.resolve()
    require(planned and planned == [label for label in LABELS if label in planned],
            'unknown, duplicate or reordered fingerprint stages')
    require(not out.exists() and not out.is_relative_to(producer) and
            not producer.is_relative_to(out) and not source.is_relative_to(out),
            'fresh output separate from producer/source required')
    build = H.authenticate(producer, source)
    expectations_path = controls / 'expectations.json'
    expectations = H.load(expectations_path)
    require(expectations.get('schema_version') == 1 and
            all(isinstance(expectations.get(key), str)
                for key in ('expected_stdout', 'expected_stderr')),
            'independent fingerprint output expectations required')
    inputs = dict(driver_inputs or {})
    inputs.update({str(path): H.sha(path) for path in
                   [expectations_path, *(controls / name for name in CONTROL_FILES),
                    producer / 'receipt.json']})
    for item in build['host_inputs'].values():
        inputs[item['path']] = item['sha256']
    host_hashes = tree_hashes(H, source / 'host/ghc')
    object_hashes = tree_hashes(H, producer / 'objects')
    require(object_hashes and
            {'objects/' + path: digest for path, digest in object_hashes.items()} ==
            build.get('object_inputs'), 'producer objects differ from authenticated receipt')
    checks = out / 'checks'
    checks.mkdir(parents=True)
    record = {'format': 'int64-fingerprint-controls-v2', 'complete': False,
              'performance_measured': False, 'native_bootstrap_executed': False,
              'planned_checks': list(planned), 'checks': [], 'commands': [], 'runs': [],
              'producer_receipt_sha256': H.sha(producer / 'receipt.json'),
              'inputs': inputs, 'host_source_hashes': host_hashes,
              'producer_object_hashes': object_hashes, 'expectations': expectations}

    def save():
        H.save(checks / 'receipt.json', record)

    def run(label, command, cwd=source):
        item = {'label': label, 'argv': list(map(str, command)), 'cwd': str(cwd)}
        record['commands'].append(item)
        save()
        log = checks / 'guarded' / label
        result = H.Runner(checks, LIMITS).run(command, cwd, log)
        stdout, stderr = (log / 'stdout').read_bytes(), (log / 'stderr').read_bytes()
        (checks / (label + '.stdout')).write_bytes(stdout)
        (checks / (label + '.stderr')).write_bytes(stderr)
        item.update(result)
        save()
        return stdout, stderr

    save()
    try:
        for opt in ('0', '2'):
            label = 'current-O' + opt
            if label in planned:
                record['runs'].append(run_probe(H, source, controls, checks, build,
                                                host_hashes, expectations, opt, run))
                record['checks'].append(label)
                save()
        if 'actual-separate' in planned:
            record['actual_source'] = run_separate(H, source, producer, checks, build,
                                                   object_hashes, run)
            record['checks'].append('actual-separate')
            save()
        require(tree_hashes(H, producer / 'objects') == object_hashes,
                'qualified producer objects changed')
        require(tree_hashes(H, source / 'host/ghc') == host_hashes, 'host source inventory changed')
        H.check_pins(inputs)
        require(H.authenticate(producer, source) == build, 'current producer identity changed')
        require(record['checks'] == planned, 'complete planned F1 gate')
        record.update(complete=True, immutable_inputs_verified_after=True,
                      producer_outputs_immutable=True)
    except BaseException as error:
        record['error'] = str(error)
        raise
    finally:
        save()
    H.save(out / 'receipt.json', record)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    listing = '--framework-list' in sys.argv[1:]
    parser.add_argument('--framework-list', action='store_true')
    parser.add_argument('--producer', type=Path, required=not listing)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=not listing)
    args = parser.parse_args()
    exact = select(PREFIX, LABELS)
    planned = [exact] if exact is not None else LABELS
    if args.framework_list:
        print(inventory_json(PREFIX, planned))
        return
    helper = ROOT / 'tools/performance/a1-private-index/helper.py'
    spec = importlib.util.spec_from_file_location('fingerprint_guard', helper)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    paths = [Path(__file__), helper, ROOT / 'tools/testing/receipt_selection.py',
             args.source.resolve() / 'tools/shared/test_direct.py']
    driver_inputs = {str(path): guard.sha(path) for path in paths}
    with guard.SerialLock(ROOT / '.mlf-build'):
        qualify(guard, args.source, args.producer, args.output, planned,
                driver_inputs=driver_inputs)
    print('PASS Int64 fingerprint qualification: ' + ', '.join(planned) + '; no speed claim')


if __name__ == '__main__':
    main()
