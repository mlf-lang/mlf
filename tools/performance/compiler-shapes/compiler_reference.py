"""Select and build the Git baseline for the candidate compiler."""
import fcntl
from pathlib import Path
import subprocess
import sys
import tempfile

import command_runner
import provenance


PREPARE = Path(__file__).with_name('prepare.py')


def fixed_setup_pins(setup):
    """Use the preparation's recorded identities, never repin changed files."""
    producer = Path(setup['producer']).resolve()
    identity = setup['identity']
    pins = {str(producer / 'receipt.json'): identity['producer_receipt_sha256'],
            str(producer / 'bin/emlf'): identity['producer_emlf_sha256'],
            str(producer / 'bin/builtin-prelude'): identity['builtin_prelude_sha256']}
    pins.update({setup['builtin'] + suffix: setup['builtin_record'][setup['builtin'] + suffix]
                 for suffix in ('.mlfci', '.mlfco')})
    return pins


def select_revision(root, outputs=()):
    root = Path(root).resolve()
    head = provenance.git(root, 'rev-parse', 'HEAD^{commit}').decode().strip()
    tracked = provenance.git(root, 'status', '--porcelain', '--untracked-files=no')
    pathspec = ['.']
    for output in outputs:
        path = Path(output).resolve()
        if path != root and path.is_relative_to(root):
            pathspec.append(':(exclude,top,literal)' + path.relative_to(root).as_posix())
    untracked = provenance.git(root, 'ls-files', '--others', '--exclude-standard', '-z', '--', *pathspec)
    dirty = bool(tracked or untracked)
    if dirty:
        commit = head
    else:
        parents = provenance.git(root, 'rev-list', '--parents', '-1', head).decode().split()[1:]
        if not parents:
            if provenance.git(root, 'rev-parse', '--is-shallow-repository').strip() == b'true':
                raise ValueError('A clean checkout needs its first parent. Fetch at least two commits.')
            return {'candidate_commit': head, 'dirty': False, 'commit': None, 'basis': 'root commit has no parent'}
        commit = parents[0]
    return {'candidate_commit': head, 'dirty': dirty, 'commit': commit,
            'basis': 'working tree vs HEAD' if dirty else 'HEAD vs first parent'}


def authenticate(reference, helper=None):
    """Recheck the unchanged baseline and all of its prepared dependencies."""
    h = helper or command_runner.load_helper()
    source, producer = Path(reference['source']), Path(reference['producer'])
    if (provenance.git(source, 'rev-parse', 'HEAD').decode().strip() != reference['commit']
            or provenance.git(source, 'status', '--porcelain', '--untracked-files=normal').strip()):
        raise ValueError(f'Baseline compiler checkout changed: {source}')
    h.check_pins({producer / 'bin/emlf': reference['emlf_sha256'],
                  producer / 'receipt.json': reference['receipt_sha256']})
    if 'fixed_dependencies' in reference:
        h.check_pins(reference['fixed_dependencies']['inputs'])
    return h.authenticate(producer, source)


def prepare_fixed_dependencies(setup, reference, output, helper=None):
    """Use the ordinary preparer with this compiler's own source and ABI.

    This runs before the measured schedule. A fresh cohort owns fresh setup
    evidence; the cached producer receipt and previous cohorts stay unchanged.
    """
    h = helper or command_runner.load_helper()
    source, producer = Path(reference['source']).resolve(), Path(reference['producer']).resolve()
    output = Path(output).resolve()
    before = h.authenticate(producer, source)
    recipe_pins = {str(path.resolve()): h.sha(path)
                   for path in (PREPARE, Path(__file__), Path(command_runner.__file__), Path(h.__file__))}
    log_path = output.with_name(output.name + '-prepare.log')
    with log_path.open('x') as log:
        result = subprocess.run([sys.executable, '-B', PREPARE,
                                 '--source', source, '--producer', producer,
                                 '--build-builtin', '--endpoint', setup['endpoint'],
                                 '--ghc', before['ghc']['path'], '--clang', setup['clang'],
                                 '--output', output], cwd=source, env=h.env(), stdout=log, stderr=log)
    if result.returncode:
        raise RuntimeError(f'Baseline fixed dependency preparation failed (exit {result.returncode}): {log_path}')
    fixed = h.load(output / 'setup.json')
    preparation = h.load(output / 'preparation.json')
    h.require(fixed['complete'] and fixed['endpoint'] == setup['endpoint'], 'qualified baseline endpoint dependencies')
    h.require(Path(fixed['source']).resolve() == source and Path(fixed['producer']).resolve() == producer,
              'baseline dependencies belong to the baseline source and producer')
    h.require(Path(fixed['clang']).resolve() == Path(setup['clang']).resolve(), 'same Clang for both compiler lanes')
    h.require(Path(fixed['builtin']).resolve().is_relative_to(output)
              and Path(fixed['runtime']).resolve().is_relative_to(output), 'baseline dependencies belong to this preparation')
    identity = fixed['identity']
    expected = fixed_setup_pins(fixed)
    h.require(identity['producer_receipt_sha256'] == reference['receipt_sha256']
              and identity['producer_emlf_sha256'] == reference['emlf_sha256'], 'baseline dependency producer identity')
    expected[fixed['runtime']] = h.sha(h.regular(fixed['runtime']))
    inputs = {**recipe_pins, **h.file_pins(output), **preparation['source_pins'], **preparation['runtime_pins'],
              **{str(Path(path).resolve()): digest for path, digest in expected.items()},
              str(log_path): h.sha(log_path)}
    for path in (fixed['ghc'], fixed['clang']):
        inputs[str(Path(path).resolve())] = h.sha(path)
    h.check_pins(inputs)
    h.require(h.authenticate(producer, source) == before, 'baseline producer unchanged during dependency preparation')
    return {'setup': fixed, 'setup_file': str(output / 'setup.json'), 'inputs': inputs}


def prepare(setup, selection, producer_ghc, fixed_output):
    root = Path(setup['source']).resolve()
    commit = selection['commit']
    if commit is None:
        return None
    h = command_runner.load_helper()
    ghc = Path(producer_ghc).resolve()
    cache = root / '.mlf-build/compiler-shapes-head' / commit / h.sha(ghc)
    cache.mkdir(parents=True, exist_ok=True)
    ready = cache / 'reference.json'
    with (cache / 'prepare.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ready.exists():
            reference = h.load(ready)
        else:
            attempt = Path(tempfile.mkdtemp(prefix='build-', dir=cache))
            source, producer = attempt / 'source', attempt / 'producer'
            subprocess.run(['git', 'init', '--quiet', source], check=True)
            subprocess.run(['git', '-C', source, 'fetch', '--quiet', '--depth=1', root.as_uri(), commit], check=True)
            subprocess.run(['git', '-C', source, 'checkout', '--quiet', '--detach', commit], check=True)
            with (attempt / 'build.log').open('w') as log:
                result = subprocess.run([sys.executable, '-B', source / 'tools/shared/build.py',
                                         '--bootstrap-only', '--optimization', '2', '--ghc', ghc,
                                         '--build-dir', producer], cwd=source, stdout=log, stderr=log)
            if result.returncode:
                raise RuntimeError(f'Baseline compiler build failed (exit {result.returncode}): {log.name}')
            reference = {'commit': commit, 'source': str(source), 'producer': str(producer),
                         'emlf_sha256': h.sha(producer / 'bin/emlf'),
                         'receipt_sha256': h.sha(producer / 'receipt.json')}
        if reference['commit'] != commit:
            raise ValueError('Baseline compiler cache revision changed')
        authenticate(reference, h)
        if not ready.exists():
            h.save(ready, reference)
    fixed = prepare_fixed_dependencies(setup, reference, fixed_output, h)
    return {**reference, **selection, 'fixed_dependencies': fixed}
