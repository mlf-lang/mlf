"""Deterministic controls for the watchdog's actual output accounting."""

import ast
import errno
import os
from pathlib import Path
import stat
import sys
import tempfile
import types

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'testing'))
import events

SOURCE = Path(__file__).with_name('resource_watchdog.py')
TREE = ast.parse(SOURCE.read_text())
FUNCTION = next(node for node in TREE.body
                if isinstance(node, ast.FunctionDef) and node.name == 'output_bytes')


def get(walk=os.walk):
    env = {'Path': Path, 'stat': stat, 'errno': errno,
           'os': types.SimpleNamespace(path=os.path, walk=walk)}
    exec(compile(ast.Module(body=[FUNCTION], type_ignores=[]), str(SOURCE), 'exec'), env)
    return env['output_bytes']


def rejects(action, exception):
    try:
        action()
    except exception:
        return
    raise AssertionError('expected ' + exception.__name__)


def injected(error, after=None, names=()):
    def walk(root, **kwargs):
        yield str(root), list(names), []
        if after:
            after()
        kwargs['onerror'](error)
    return get(walk)


def check(label, action):
    identity = 'release/watchdog-output/' + label
    events.start(identity)
    try:
        action()
    except Exception as error:
        events.result(identity, 'fail', detail=str(error))
        raise
    events.result(identity, 'pass')


def equals(actual, expected):
    if actual != expected:
        raise AssertionError(f'expected {expected} bytes, observed {actual}')


def main():
    with tempfile.TemporaryDirectory() as directory:
        basis = Path(directory)
        root = basis / 'watched'
        root.mkdir()
        (root / 'a').write_bytes(b'abc')
        check('regular-bytes', lambda: equals(get()(root), 3))

        child = root / 'child'
        gone = FileNotFoundError(errno.ENOENT, 'gone', str(child))
        check('named-vanish', lambda: equals(injected(gone, names=['child'])(root), 0))
        for label, error, names in (
            ('unlisted-vanish', gone, []),
            ('nested-path', FileNotFoundError(errno.ENOENT, 'gone', str(child / 'nested')), ['child']),
            ('root', FileNotFoundError(errno.ENOENT, 'gone', str(root)), []),
            ('outside', FileNotFoundError(errno.ENOENT, 'gone', str(basis / 'outside')), []),
            ('dotdot', FileNotFoundError(errno.ENOENT, 'gone', str(root / '..' / 'outside')), []),
            ('wrong-errno', FileNotFoundError(errno.EACCES, 'wrong errno', str(child)), ['child']),
            ('permission', PermissionError(errno.EACCES, 'denied', str(child)), ['child']),
            ('not-directory', NotADirectoryError(errno.ENOTDIR, 'not directory', str(child)), ['child']),
            ('io', OSError(errno.EIO, 'io', str(child)), ['child']),
            ('no-filename', FileNotFoundError('no filename'), []),
        ):
            check(label, lambda: rejects(lambda: injected(error, names=names)(root), type(error)))

        check('absent-root', lambda: rejects(lambda: get()(basis / 'absent'), FileNotFoundError))
        regular = basis / 'file'
        regular.write_bytes(b'x')
        check('file-root', lambda: rejects(lambda: get()(regular), NotADirectoryError))

        # Root loss after the opening stat must not be suppressed as a child race.
        lost = basis / 'lost'
        lost.mkdir()
        loss = FileNotFoundError(errno.ENOENT, 'gone', str(lost / 'child'))
        check('root-vanished', lambda: rejects(
            lambda: injected(loss, lost.rmdir, names=['child'])(lost), FileNotFoundError))
        changed = basis / 'changed'
        changed.mkdir()

        def replace():
            changed.rmdir()
            changed.write_bytes(b'x')

        replacement = FileNotFoundError(errno.ENOENT, 'gone', str(changed / 'child'))
        check('root-replaced', lambda: rejects(
            lambda: injected(replacement, replace, names=['child'])(changed), NotADirectoryError))

        # Use a real walk and rename after its first directory snapshot.
        race = basis / 'race'
        work = race / 'work'
        work.mkdir(parents=True)
        (work / 'data').write_bytes(b'payload')

        def rename_walk(path, **kwargs):
            iterator = os.walk(path, **kwargs)
            yield next(iterator)
            work.rename(race / 'published')
            yield from iterator

        check('renamed-before-sample', lambda: equals(get(rename_walk)(race), 0))
        check('renamed-next-sample', lambda: equals(get()(race), 7))

        vanished = basis / 'vanished'
        vanished.mkdir()
        missing = vanished / 'gone'
        missing.write_bytes(b'x')

        def file_walk(path, **kwargs):
            missing.unlink()
            yield str(path), [], ['gone']

        check('vanished-file', lambda: equals(get(file_walk)(vanished), 0))
        (root / 'symlink').symlink_to(race, target_is_directory=True)
        check('symlink-excluded', lambda: equals(get()(root), 3))
    print('PASS 20 deterministic output traversal controls; no compiler execution')


if __name__ == '__main__':
    main()
