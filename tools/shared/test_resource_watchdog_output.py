"""Deterministic controls for the watchdog's actual output accounting."""

import errno
import os
from pathlib import Path
import sys
import tempfile
from unittest import mock

from resource_watchdog import output_bytes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'testing'))
import events

def rejects(action, exception):
    try:
        action()
    except exception:
        return
    raise AssertionError('expected ' + exception.__name__)


def injected(root, error, after=None, names=()):
    def walk(root, **kwargs):
        yield str(root), list(names), []
        if after:
            after()
        kwargs['onerror'](error)
    with mock.patch.object(os, 'walk', walk):
        return output_bytes(root)


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
        check('regular-bytes', lambda: equals(output_bytes(root), 3))

        child = root / 'child'
        gone = FileNotFoundError(errno.ENOENT, 'gone', str(child))
        check('named-vanish', lambda: equals(injected(root, gone, names=['child']), 0))
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
            check(label, lambda: rejects(lambda: injected(root, error, names=names), type(error)))

        check('absent-root', lambda: rejects(lambda: output_bytes(basis / 'absent'), FileNotFoundError))
        regular = basis / 'file'
        regular.write_bytes(b'x')
        check('file-root', lambda: rejects(lambda: output_bytes(regular), NotADirectoryError))

        # Root loss after the opening stat must not be suppressed as a child race.
        lost = basis / 'lost'
        lost.mkdir()
        loss = FileNotFoundError(errno.ENOENT, 'gone', str(lost / 'child'))
        check('root-vanished', lambda: rejects(
            lambda: injected(lost, loss, lost.rmdir, names=['child']), FileNotFoundError))
        changed = basis / 'changed'
        changed.mkdir()

        def replace():
            changed.rmdir()
            changed.write_bytes(b'x')

        replacement = FileNotFoundError(errno.ENOENT, 'gone', str(changed / 'child'))
        check('root-replaced', lambda: rejects(
            lambda: injected(changed, replacement, replace, names=['child']), NotADirectoryError))

        # Use a real walk and rename after its first directory snapshot.
        race = basis / 'race'
        work = race / 'work'
        work.mkdir(parents=True)
        (work / 'data').write_bytes(b'payload')

        original_walk = os.walk

        def rename_walk(path, **kwargs):
            iterator = original_walk(path, **kwargs)
            yield next(iterator)
            work.rename(race / 'published')
            yield from iterator

        with mock.patch.object(os, 'walk', rename_walk):
            check('renamed-before-sample', lambda: equals(output_bytes(race), 0))
        check('renamed-next-sample', lambda: equals(output_bytes(race), 7))

        vanished = basis / 'vanished'
        vanished.mkdir()
        missing = vanished / 'gone'
        missing.write_bytes(b'x')

        def file_walk(path, **kwargs):
            missing.unlink()
            yield str(path), [], ['gone']

        with mock.patch.object(os, 'walk', file_walk):
            check('vanished-file', lambda: equals(output_bytes(vanished), 0))
        (root / 'symlink').symlink_to(race, target_is_directory=True)
        check('symlink-excluded', lambda: equals(output_bytes(root), 3))
    print('PASS 20 deterministic output traversal controls; no compiler execution')


if __name__ == '__main__':
    main()
