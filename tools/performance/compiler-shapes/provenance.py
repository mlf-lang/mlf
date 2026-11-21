"""Record and compare the tracked Git state of serial benchmark cohorts."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile


PATCH_OPTIONS = ('--binary', '--full-index', '--no-renames', '--no-ext-diff', '--no-textconv',
                 '--no-color', '--src-prefix=a/', '--dst-prefix=b/', '--submodule=short',
                 '--ignore-submodules=none')
PATCH_FORMAT = 'git-binary-v1'
ROOT_DOCUMENTS = {b'README.md', b'CONTRIBUTING.md', b'CHANGELOG.md'}


def git(root, *argv, env=None, data=None):
    command = subprocess.run(['git', '--no-replace-objects', *argv], cwd=root, input=data, capture_output=True, env=env)
    if command.returncode:
        raise ValueError(f"Git {argv[0]} failed: {os.fsdecode(command.stderr).strip()}")
    return command.stdout


def source_identity(root, out):
    commit = git(root, 'rev-parse', 'HEAD').decode().strip()
    branch = os.fsdecode(git(root, 'rev-parse', '--abbrev-ref', 'HEAD')).strip()
    status = os.fsdecode(git(root, 'status', '--porcelain'))
    patch = git(root, 'diff', *PATCH_OPTIONS, commit, '--')
    untracked = {}
    for name in git(root, 'ls-files', '-z', '--others', '--exclude-standard').split(b'\0')[:-1]:
        path = root / os.fsdecode(name)
        if path.is_file():
            untracked[os.fsdecode(name)] = hashlib.sha256(path.read_bytes()).hexdigest()
    source = dict(commit=commit, branch=branch, dirty=bool(status.strip()), status_porcelain=status.splitlines(),
                  patch_format=PATCH_FORMAT, patch_sha256=hashlib.sha256(patch).hexdigest(),
                  patch_bytes=len(patch), untracked=untracked)
    if patch:
        path = out / 'source-patch.diff'
        path.write_bytes(patch)
        source['patch_file'] = str(path)
    return source


def archived_patch(folder, source):
    # The plan's original absolute patch_file can point at another machine.
    path = folder / 'source-patch.diff'
    patch = path.read_bytes() if path.exists() else b''
    size = source['patch_bytes']
    file = source.get('patch_file')
    if (type(size) is not int or size != len(patch) or hashlib.sha256(patch).hexdigest() != source['patch_sha256']
            or (patch and (not isinstance(file, str) or not file)) or (not patch and file is not None)):
        raise ValueError('missing or corrupt archived tracked patch')
    return patch


def documentation_change(root, env, path, old_mode, new_mode, old_blob, new_blob):
    if path not in ROOT_DOCUMENTS and not re.fullmatch(rb'docs/[^/]+\.md', path):
        return False
    for mode, blob in ((old_mode, old_blob), (new_mode, new_blob)):
        if mode == b'000000':
            continue
        if mode != b'100644':
            return False
        contents = git(root, 'cat-file', 'blob', blob, env=env)
        try:
            contents.decode('utf-8')
        except UnicodeDecodeError:
            return False
        if b'\0' in contents:
            return False
    return True


def protected_changes(root, source, patch):
    """Replay the archived delta at its commit without touching the checkout, index or objects."""
    commit = source['commit']
    if (not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', commit)
            or git(root, 'cat-file', '-t', commit).strip() != b'commit'):
        raise ValueError('invalid tracked patch base revision')
    archive_format = source.get('patch_format')
    if archive_format not in (None, PATCH_FORMAT):
        raise ValueError('unsupported tracked patch format')
    if not patch:
        return {}
    objects = git(root, 'rev-parse', '--path-format=absolute', '--git-path', 'objects').rstrip(b'\n')
    with tempfile.TemporaryDirectory() as temp:
        scratch = Path(temp)
        # A private object store holds blobs from uncommitted changes. Git
        # reads the committed base from the repository's existing object store.
        (scratch / 'objects/info').mkdir(parents=True)
        (scratch / 'objects/info/alternates').write_bytes(objects + b'\n')
        env = {**os.environ, 'GIT_INDEX_FILE': str(scratch / 'index'), 'GIT_OBJECT_DIRECTORY': str(scratch / 'objects')}
        git(root, 'read-tree', commit, env=env)
        git(root, 'apply', '--cached', '--whitespace=nowarn', '-', env=env, data=patch)
        # Git apply accepts arbitrary trailing text. Require exact reproduction
        # so only a complete, understood archive can receive the exception.
        options = PATCH_OPTIONS if archive_format else ('--no-ext-diff', '--no-textconv')
        if git(root, 'diff', '--cached', *options, commit, '--', env=env) != patch:
            raise ValueError('archived tracked patch does not reproduce at recorded revision')
        raw = git(root, 'diff-index', '--cached', '--raw', '--no-abbrev', '--no-renames', '-z', commit, '--', env=env)
        records = raw.split(b'\0')[:-1]
        protected = {}
        for header, path in zip(records[::2], records[1::2]):
            old_mode, new_mode, old_blob, new_blob, _ = header.removeprefix(b':').split()
            if not documentation_change(root, env, path, old_mode, new_mode, old_blob, new_blob):
                protected[path] = header
        return protected
