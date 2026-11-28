"""Select and build the Git baseline for the candidate compiler."""
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import command_runner
from prepare import runtime_cflags, runtime_command
import provenance


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


def prepare_runtime(setup, source, cache, h):
    # Called under prepare.lock after authenticating the reference checkout.
    # The candidate runtime digest distinguishes setups built against different
    # host dependencies. The reference object always comes from its own source.
    cflags = setup['runtime_cflags'] if 'runtime_cflags' in setup else runtime_cflags()
    command = runtime_command(setup['clang'], source, cflags, 'runtime.o')
    inputs = [command, h.sha(setup['clang']), h.sha(setup['runtime'])]
    key = hashlib.sha256(json.dumps(inputs).encode()).hexdigest()
    folder = cache / 'runtime' / key
    folder.mkdir(parents=True, exist_ok=True)
    obj, receipt = folder / 'runtime.o', folder / 'receipt.json'
    if receipt.exists():
        digest = h.load(receipt)['sha256']
        h.check_pins({obj: digest})
    else:
        subprocess.run(command, cwd=folder, check=True)
        digest = h.sha(obj)
        h.save(receipt, {'command': command, 'sha256': digest})
    return {'runtime': str(obj), 'runtime_sha256': digest}


def prepare(setup, selection, producer_ghc):
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
        source, producer = Path(reference['source']), Path(reference['producer'])
        if (reference['commit'] != commit or provenance.git(source, 'rev-parse', 'HEAD').decode().strip() != commit
                or provenance.git(source, 'status', '--porcelain', '--untracked-files=normal').strip()):
            raise ValueError(f'Baseline compiler checkout changed: {source}')
        h.check_pins({producer / 'bin/emlf': reference['emlf_sha256'],
                      producer / 'receipt.json': reference['receipt_sha256']})
        h.authenticate(producer, source)
        if not ready.exists():
            h.save(ready, reference)
        return {**reference, **selection, **prepare_runtime(setup, source, cache, h)}
