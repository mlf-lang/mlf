"""Small shared adapter for the existing finite W1 controls; no work on import."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
_ARGS = None
_PINS = {}


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory():
    return json.loads((HERE / 'CONTROL-INVENTORY.json').read_text())


def check_inventory():
    data = inventory()
    for name, digest in data['fixture_hashes'].items():
        if sha(HERE / name) != digest:
            raise ValueError('frozen fixture changed: ' + name)
    for name, row in data['baseline_files'].items():
        if row['sha256'] != data['fixture_hashes'][row['fixture']]:
            raise ValueError('baseline provenance mismatch: ' + name)
    if len(data['transport_cases']) != 20 or len(data['fault_cases']) != 20:
        raise ValueError('finite inventory changed')
    return data


def arguments():
    global _ARGS
    if sys.flags.optimize:
        raise ValueError('Do not run these assertion-based controls with -O/PYTHONOPTIMIZE')
    parser = argparse.ArgumentParser(description='Finite process-readiness qualification, not a benchmark')
    for option in ['producer', 'baseline-root', 'baseline-producer', 'output']:
        parser.add_argument('--' + option, type=Path, required=True)
    _ARGS = parser.parse_args()
    for name in ['producer', 'baseline_root', 'baseline_producer', 'output']:
        setattr(_ARGS, name, getattr(_ARGS, name).resolve())
    for protected in [ROOT, _ARGS.baseline_root, _ARGS.producer, _ARGS.baseline_producer]:
        if _ARGS.output.is_relative_to(protected) or protected.is_relative_to(_ARGS.output):
            raise ValueError('output must be separate from sources and producers')
    if sys.platform != 'linux' or platform.machine() not in ['x86_64', 'AMD64']:
        raise ValueError('This exact full inventory requires Linux x86_64/glibc; no silent skips')
    check_inventory()
    return _ARGS


def env():
    result = {**os.environ, 'GHC_ENVIRONMENT': '-', 'GHCRTS': '', 'LC_ALL': 'C.UTF-8',
              'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1', 'MAKEFLAGS': '-j1'}
    # A control process must not inherit ownership of the invoking build scope.
    result.pop('MLF_BUILD_SCOPE', None)
    result.pop('MLF_WAIT_FAULT', None)
    return result


def authenticate(producer):
    producer = Path(producer).resolve()
    if _ARGS is None:
        raise ValueError('arguments must be established first')
    if producer == _ARGS.producer:
        root = ROOT
    elif producer == _ARGS.baseline_producer:
        root = _ARGS.baseline_root
    else:
        raise ValueError('undeclared producer')
    auth = root / 'tools/shared/test_direct.py'
    module = types.ModuleType('process_readiness_producer_auth')
    module.__file__ = str(auth)
    exec(compile(auth.read_bytes(), str(auth), 'exec'), module.__dict__)
    result = module.authenticate_build(producer / 'receipt.json', producer / 'bin', root=root)
    if result['optimization'] != '2' or result['ghc']['version'] != '9.14.1':
        raise ValueError('an authenticated official GHC 9.14.1 O2 producer is required')
    if Path(result['build_driver']['path']).resolve().parents[2] != root:
        raise ValueError('producer belongs to a different source root')
    return result, root


def check_pins(pins):
    for path, digest in pins.items():
        if sha(path) != digest:
            raise ValueError('input changed: ' + str(path))


def object_hashes(producer):
    return {'objects/' + str(p.relative_to(producer / 'objects')): sha(p)
            for p in sorted((producer / 'objects').rglob('*')) if p.is_file()}


def check_pair(args):
    """Keep the private study's two authentic producers and exact baseline bytes."""
    data = check_inventory()
    baseline, base_root = authenticate(args.baseline_producer)
    candidate, source = authenticate(args.producer)
    tree = subprocess.check_output(['git', '-C', str(base_root), 'rev-parse', 'HEAD^{tree}'], text=True).strip()
    if tree != data['baseline_tree']:
        raise ValueError('baseline committed tree differs; equivalent-tree commit IDs are allowed')
    if subprocess.call(['git', '-C', str(base_root), 'diff', '--quiet', 'HEAD', '--']):
        raise ValueError('baseline tracked source differs from the frozen tree')
    # New tests/docs may be tracked or untracked; no third production change.
    changed_paths = subprocess.check_output(
        ['git', '-C', str(source), 'diff', '--name-only', data['baseline_tree'], '--'], text=True).splitlines()
    untracked = subprocess.check_output(
        ['git', '-C', str(source), 'ls-files', '--others', '--exclude-standard'], text=True).splitlines()
    for name in changed_paths + untracked:
        if name not in data['candidate']['changed_paths'] and not name.startswith('tools/performance/process-readiness/'):
            raise ValueError('unrelated source-tree change: ' + name)
    for name, row in data['baseline_files'].items():
        if sha(base_root / name) != row['sha256']:
            raise ValueError('baseline C bytes differ: ' + name)
    for name, digest in data['candidate']['source_hashes'].items():
        if sha(source / name) != digest:
            raise ValueError('this inventory qualifies only the frozen W1 C change: ' + name)
    if baseline['cc'] != candidate['cc'] or baseline['ghc'] != candidate['ghc']:
        raise ValueError('both producers must use the same authenticated toolchain')
    for name in ['tools/shared/test_direct.py', 'tools/shared/build.py']:
        if sha(base_root / name) != sha(source / name):
            raise ValueError('producer/authentication recipe changed: ' + name)
    def normalized(record, root, producer):
        return [[str(x).replace(str(root), '<SOURCE>').replace(str(producer), '<PRODUCER>')
                 for x in command['argv']] for command in record['commands']]
    if normalized(baseline, base_root, args.baseline_producer) != normalized(candidate, source, args.producer):
        raise ValueError('ordinary producer commands differ')
    pins = {str(p): sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    changed = set(data['candidate']['changed_paths'])
    for field in ['resolved_modules', 'resolved_host_modules', 'host_inputs', 'configuration_inputs']:
        if candidate[field].keys() != baseline[field].keys():
            raise ValueError('producer input inventory changed: ' + field)
        for name, row in candidate[field].items():
            old = baseline[field][name]
            relative = str(Path(row['path']).relative_to(source))
            if relative != str(Path(old['path']).relative_to(base_root)):
                raise ValueError('source resolution differs: ' + name)
            if relative not in changed and row['sha256'] != old['sha256']:
                raise ValueError('unrelated producer source changed: ' + relative)
            pins[row['path']] = row['sha256']
            pins[old['path']] = old['sha256']
    for producer, record in [(args.baseline_producer, baseline), (args.producer, candidate)]:
        if object_hashes(producer) != record['object_inputs']:
            raise ValueError('producer dependency objects differ from receipt')
        pins[str(producer / 'receipt.json')] = sha(producer / 'receipt.json')
        for relative, digest in record['object_inputs'].items():
            pins[str(producer / relative)] = digest
        for name in ['host.o', 'supervisor.o']:
            pins[str(producer / name)] = sha(producer / name)
    if sha(args.baseline_producer / 'supervisor.o') != sha(args.producer / 'supervisor.o'):
        raise ValueError('unchanged supervisor object differs between producers')
    global _PINS
    if _PINS:
        check_pins(_PINS)
        if pins != _PINS:
            raise ValueError('qualification input inventory changed')
    else:
        _PINS = pins
    check_pins(_PINS)
    return baseline, candidate


def input_pins():
    return dict(_PINS)


def prepare_command(argv, output, label):
    """Record compiler-selected non-system inputs without changing generated code."""
    argv = list(map(str, argv))
    if '-c' in argv and any(x.endswith('.c') for x in argv):
        argv += ['-MMD', '-MF', str(output / (label + '.d')), '-MT', 'w1-control']
    return argv


def record_c_resolution(item):
    argv = item['argv']
    if '-MF' not in argv:
        return
    depfile = Path(argv[argv.index('-MF') + 1])
    text = depfile.read_text().replace('\\\n', ' ')
    inputs = [Path(x).resolve() for x in shlex.split(text.split(':', 1)[1])]
    expected_source = Path(argv[argv.index('-c') + 1]).resolve()
    if expected_source not in inputs:
        raise ValueError('C dependency record omitted the exact source')
    known = input_pins()
    missing_sys = _ARGS.output / 'faults/no-pidfd.h'
    if missing_sys.exists():
        expected = b'#include <sys/syscall.h>\n#undef SYS_pidfd_open\n'
        if missing_sys.read_bytes() != expected:
            raise ValueError('missing-SYS fixture changed')
        known[str(missing_sys)] = hashlib.sha256(expected).hexdigest()
    for path in inputs:
        if str(path) not in known or sha(path) != known[str(path)]:
            raise ValueError('compiler resolved an unregistered C input: ' + str(path))
    result = Path(argv[argv.index('-o') + 1])
    item['compiled_inputs'] = {str(p): sha(p) for p in inputs}
    item['dependency_record_sha256'] = sha(depfile)
    item['compiled_object_sha256'] = sha(result)
