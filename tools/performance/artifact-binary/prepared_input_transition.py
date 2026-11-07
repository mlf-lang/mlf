"""Draft successor transition primitives, not a live source-contract adapter.

No final identities are embedded. Callers must provide separately reviewed pins.
This module neither publishes nor updates repository metadata.
"""
import copy
import hashlib
import json
import os
from pathlib import PurePosixPath
import stat
import sys

CHANGED_SOURCES = frozenset({
    'libraries/mlf-crates/Bootstrap/CrateGraph.hs',
    'libraries/mlf-crates/Bootstrap/CrateQuery.hs',
})


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)


def read_regular(path, limit):
    """Reject links in any component and special files before bounded reading."""
    if sys.platform != "linux":
        raise ValueError("Linux-only provisional reader; not eligible for live admission")
    raw_path = os.fspath(path)
    if ".." in raw_path.split(os.sep):
        raise ValueError("parent traversal components are forbidden")
    path = os.path.abspath(raw_path)
    parts = path.split(os.sep)
    descriptor = os.open(os.sep, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=descriptor)
        try:
            before = os.fstat(child)
            require(stat.S_ISREG(before.st_mode) and before.st_size <= limit,
                    'bounded regular input required')
            chunks, count = [], 0
            while chunk := os.read(child, min(65536, limit + 1 - count)):
                chunks.append(chunk)
                count += len(chunk)
                require(count <= limit, 'input exceeded bound')
            after = os.fstat(child)
            require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
                     before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns,
                     after.st_ctime_ns), 'input changed during read')
            return b''.join(chunks)
        finally:
            os.close(child)
    except OSError as error:
        raise ValueError('input path is not an ordinary bounded file') from error
    finally:
        os.close(descriptor)


def validate_lock(old_raw, new_raw, identities):
    require(set(identities) == CHANGED_SOURCES, 'exact two source identities required')
    expected = copy.deepcopy(strict_json(old_raw))
    seen = set()
    for package in expected['packages']:
        for name, digest in package['sources'].items():
            path = str(PurePosixPath(package['path']) / name)
            if path in CHANGED_SOURCES:
                old, new = identities[path]
                require(path not in seen and digest == old, 'unique exact old lock owner')
                package['sources'][name] = new
                seen.add(path)
    require(seen == CHANGED_SOURCES, 'missing lock owner')
    require(strict_json(new_raw) == expected, 'lock changes exceed two source identities')


def validate_projection(current, predecessor, identities):
    """Full byte-map equality outside exact authorized paths; pin both sides."""
    expected_paths = CHANGED_SOURCES | {'mlf.lock'}
    require(set(identities) == expected_paths, 'exact three-file transition required')
    require(set(current) == set(predecessor), 'inventory changed')
    require(expected_paths <= set(current), 'missing transition member')
    for path in current:
        require(type(current[path]) is bytes and type(predecessor[path]) is bytes,
                'raw bytes required')
        if path in identities:
            old, new = identities[path]
            require(sha(predecessor[path]) == old and sha(current[path]) == new,
                    'explicit raw identity mismatch')
        else:
            require(current[path] == predecessor[path], 'unrelated source changed')
    validate_lock(predecessor['mlf.lock'], current['mlf.lock'],
                  {p: identities[p] for p in CHANGED_SOURCES})
