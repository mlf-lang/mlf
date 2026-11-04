"""Bounded source snapshots for the opt-in, fresh-source IR8 route.

This is cooperative filesystem reproducibility, not a hostile-filesystem
sandbox or a source/native credential. Only the copied .emlf package is given
to the producer as its working directory. Compiler-generated Prelude and
MLF.Primitive definitions belong to the trusted compiler build, not this guest
inventory. The caller must authenticate and finish its own fresh producer
invocation, then run the full capture verifier after ``loaded_subset``.
"""

import hashlib
import json
import os
from pathlib import Path
import stat

import module_transport
import transport


MAX_FILES = 32                 # Includes the entry supplied on stdin.
MAX_FILE_BYTES = 1 << 20
MAX_TOTAL_BYTES = 8 << 20
MAX_CAPTURE_BYTES = 32 << 20
MAX_ENTRIES = 1024             # Includes directories and ignored regular files.
MAX_DEPTH = 16                 # Relative components, including a file's name.
POLICY = 'bounded-source-snapshot-v8/1'
PACKAGE_KEYS = {'policy', 'live_root', 'snapshot_root', 'root_relative', 'files',
                'copied_files', 'total_bytes',
                'ignored_regular_non_source_files_are_not_claimed_checked'}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _canonical(path, *, directory=False):
    try:
        path = Path(path)
        _require('..' not in path.parts, 'source path contains a parent component')
        if not path.is_absolute():
            path = Path.cwd() / path
        _require(path.resolve(strict=True) == path,
                 'source path traverses a symlink or is not canonical')
        mode = path.lstat().st_mode
        _require(not stat.S_ISLNK(mode), 'source path is a symlink')
        if directory:
            _require(stat.S_ISDIR(mode), 'source root/output is not a directory')
        return path
    except (OSError, RuntimeError, TypeError) as exc:
        raise ValueError('cannot inspect source path: ' + str(exc)) from exc


def _relative(text):
    _require(type(text) is str and text and not text.startswith('/')
             and '\\' not in text and '\0' not in text,
             'unsafe relative source path')
    parts = text.split('/')
    _require(len(parts) <= MAX_DEPTH and all(p not in ('', '.', '..') for p in parts),
             'source path depth or component rejected')
    try:
        text.encode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise ValueError('source path is not UTF-8') from exc
    return text


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _summary(files):
    return {name: {'sha256': _sha(blob), 'bytes': len(blob)}
            for name, blob in sorted(files.items())}


def bounded_read(path, limit):
    """Read at most limit + 1 bytes, rejecting links, specials and changed data.

    The extra byte detects growth at the limit. Reads are chunked; the selected
    ceiling is checked before opening and the descriptor and pathname are
    checked after reading. No global interpreter or filesystem settings change.
    """
    _require(type(limit) is int and limit >= 0, 'read limit must be a nonnegative integer')
    path = _canonical(path)
    try:
        before = path.lstat()
        _require(stat.S_ISREG(before.st_mode) and before.st_size <= limit,
                 'input is not a bounded regular file')
        flags = os.O_RDONLY | getattr(os, 'O_CLOEXEC', 0)
        flags |= getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError('cannot open bounded source input: ' + str(exc)) from exc
    primary = cleanup = None
    blob = None
    try:
        opened = os.fstat(descriptor)
        _require(_identity(before) == _identity(opened) and stat.S_ISREG(opened.st_mode),
                 'input changed while opening')
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 << 10))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        blob = b''.join(chunks)
        after_fd = os.fstat(descriptor)
        _require(_canonical(path) == path, 'input path changed while reading')
        after_path = path.lstat()
        _require(_identity(before) == _identity(after_fd) == _identity(after_path),
                 'input changed while reading')
        _require(len(blob) == after_fd.st_size <= limit, 'input length exceeds read bound')
    except BaseException as exc:
        primary = exc
    try:
        os.close(descriptor)
    except OSError as exc:
        cleanup = exc
    if primary is not None:
        if cleanup is not None:
            # Keep both exception objects, even if a caller prints only str().
            error = ValueError('bounded read failed: ' + str(primary)
                               + '; descriptor close also failed: ' + str(cleanup))
            error.primary_error = primary
            error.cleanup_error = cleanup
            raise error from primary
        if isinstance(primary, OSError):
            raise ValueError('bounded source read failed: ' + str(primary)) from primary
        raise primary
    if cleanup is not None:
        raise ValueError('bounded source descriptor close failed: ' + str(cleanup)) from cleanup
    return blob


def inventory(root):
    """Read every .emlf file in a bounded, symlink-free tree.

    Ignored regular files are counted and checked for safe type/path, but their
    contents are neither read nor claimed checked. Directories count toward the
    entry limit. The root directory itself has depth zero and is not an entry.
    """
    root = _canonical(root, directory=True)
    work, directories, files, file_stats = [(root, 0)], [], {}, []
    entries = total = 0
    try:
        while work:
            current, depth = work.pop()
            _canonical(current, directory=True)
            before = current.lstat()
            names = []
            with os.scandir(current) as stream:
                for entry in stream:
                    entries += 1
                    _require(entries <= MAX_ENTRIES, 'source inventory exceeds 1024 entries')
                    _require(depth + 1 <= MAX_DEPTH, 'source inventory exceeds depth 16')
                    names.append(entry.name)
            _require(_identity(before) == _identity(current.lstat()),
                     'source directory changed during enumeration')
            directories.append((current, _identity(before)))
            for name in sorted(names):
                path = current / name
                relative = _relative(path.relative_to(root).as_posix())
                info = path.lstat()
                _require(not stat.S_ISLNK(info.st_mode), 'source inventory rejects symlinks')
                _canonical(path)
                if stat.S_ISDIR(info.st_mode):
                    work.append((path, depth + 1))
                    continue
                _require(stat.S_ISREG(info.st_mode), 'source inventory rejects special files')
                _require(path.suffix != '.hs', 'source inventory rejects guest .hs ambiguity')
                if path.suffix != '.emlf':
                    continue
                _require(len(files) < MAX_FILES and relative not in files,
                         'source inventory exceeds 32 files or repeats a path')
                # Bound aggregate allocation before reading the next source.
                blob = bounded_read(path, min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - total))
                try:
                    blob.decode('utf-8', errors='strict')
                except UnicodeError as exc:
                    raise ValueError('source file is not UTF-8: ' + relative) from exc
                total += len(blob)
                files[relative] = blob
                file_stats.append((path, _identity(path.lstat())))
        for path, expected in directories + file_stats:
            _canonical(path)
            _require(_identity(path.lstat()) == expected, 'source inventory changed during capture')
    except OSError as exc:
        raise ValueError('cannot enumerate bounded source inventory: ' + str(exc)) from exc
    _require(files, 'empty .emlf source inventory')
    return root, dict(sorted(files.items()))


def _package_shape(package):
    _require(type(package) is dict and set(package) == PACKAGE_KEYS,
             'source package has unexpected fields')
    _require(package['policy'] == POLICY
             and package['ignored_regular_non_source_files_are_not_claimed_checked'] is True,
             'source package policy differs')
    _require(type(package['live_root']) is str and type(package['snapshot_root']) is str,
             'source package roots must be strings')
    files = package['files']
    _require(type(files) is dict and 1 <= len(files) <= MAX_FILES,
             'source package file count rejected')
    total = 0
    for relative, record in files.items():
        _relative(relative)
        _require(relative.endswith('.emlf'), 'source package contains a non-.emlf file')
        _require(type(record) is dict and set(record) == {'sha256', 'bytes'},
                 'source package file record differs')
        digest, size = record['sha256'], record['bytes']
        _require(type(digest) is str and len(digest) == 64
                 and all(c in '0123456789abcdef' for c in digest), 'invalid source SHA256')
        _require(type(size) is int and 0 <= size <= MAX_FILE_BYTES, 'invalid source byte count')
        total += size
    _require(type(package['copied_files']) is int and package['copied_files'] == len(files),
             'source package copied count differs')
    _require(type(package['total_bytes']) is int and package['total_bytes'] == total <= MAX_TOTAL_BYTES,
             'source package total byte count differs')
    _relative(package['root_relative'])
    _require(package['root_relative'] in files, 'source package entry is missing')


def verify_package(package):
    """Recheck both complete source inventories, not only the loaded subset."""
    _package_shape(package)
    live, live_files = inventory(package['live_root'])
    copied, copied_files = inventory(package['snapshot_root'])
    _require(live != copied and live not in copied.parents,
             'source snapshot must be outside live module root')
    _require(_summary(live_files) == package['files'], 'live source package changed')
    _require(_summary(copied_files) == package['files'], 'copied source package changed')


def snapshot(source, module_root, output):
    """Write only a fresh output/sources tree; return its package and entry bytes.

    Output must already be a real directory outside module_root. Other output
    artifacts are the caller's responsibility. Existing sources, including a
    dangling symlink, are never reused or overwritten. On failure, partial
    output remains diagnostic data; there is no automatic retry or cleanup.
    """
    root, files = inventory(module_root)
    source = _canonical(source)
    try:
        relative = _relative(source.relative_to(root).as_posix())
    except ValueError as exc:
        raise ValueError('source entry must be inside module root') from exc
    _require(relative in files, 'entry must be a captured .emlf regular file')
    output = _canonical(output, directory=True)
    _require(output != root and root not in output.parents, 'output must be outside module root')
    private = output / 'sources'
    _require(not os.path.lexists(private), 'output sources target already exists')
    try:
        private.mkdir()
        for name, blob in files.items():
            target = private / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                count = stream.write(blob)
                _require(count == len(blob), 'short write while copying source')
    except OSError as exc:
        raise ValueError('source snapshot copy failed: ' + str(exc)) from exc
    package = {'policy': POLICY, 'live_root': str(root), 'snapshot_root': str(private),
               'root_relative': relative, 'files': _summary(files),
               'copied_files': len(files), 'total_bytes': sum(map(len, files.values())),
               'ignored_regular_non_source_files_are_not_claimed_checked': True}
    verify_package(package)
    return package, files[relative]


def _no_fraction(_):
    raise ValueError('capture JSON requires finite integral numbers')


def loaded_subset(capture_path, package, rootBytes):
    """Match same-read loaded texts to snapshot bytes; return their exact hashes.

    This is only a bounded file-association check. It neither authenticates a
    producer nor replays resolver/type proofs; the full verifier must follow.
    The fresh invocation's caller must supply a completed capture, not a growing
    output. Builtins do not appear as guest files in the returned mapping.
    """
    verify_package(package)
    _require(type(rootBytes) is bytes, 'entry input must be exact bytes')
    root_record = package['files'][package['root_relative']]
    _require(len(rootBytes) == root_record['bytes'] and _sha(rootBytes) == root_record['sha256'],
             'producer stdin differs from captured entry')
    blob = bounded_read(capture_path, MAX_CAPTURE_BYTES)
    try:
        capture = json.loads(blob.decode('utf-8', errors='strict'),
                             object_pairs_hook=transport.strict_pairs,
                             parse_float=_no_fraction, parse_constant=_no_fraction)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError('bounded diagnostic JSON rejected: ' + str(exc)) from exc
    module_transport.envelope_budget(capture)
    _require(type(capture) is dict and capture.get('format') == 'mlf-shared-source-capture/1'
             and capture.get('status') == 'diagnostic-not-runtime-admission',
             'expected diagnostic shared-source capture')
    custody = capture.get('module_custody')
    _require(type(custody) is dict and type(custody.get('loaded')) is list,
             'capture loaded-source rows are missing')
    loaded = custody['loaded']
    _require(1 <= len(loaded) <= MAX_FILES, 'loaded-source count rejected')
    answer, roots, total = {}, 0, 0
    for index, row in enumerate(loaded):
        _require(type(row) is dict and set(row) == {'source', 'text', 'is_root'},
                 'loaded-source row shape differs')
        _require(type(row['source']) is dict and type(row['source'].get('path')) is str
                 and type(row['text']) is str and type(row['is_root']) is bool,
                 'loaded-source row types differ')
        path, is_root = row['source']['path'], row['is_root']
        _require((path == '<stdin>') == is_root, 'loaded-source root marker/path mismatch')
        if is_root:
            roots += 1
            _require(index == len(loaded) - 1, 'loaded entry must be the last row')
            relative = package['root_relative']
        else:
            relative = _relative(path[2:] if path.startswith('./') else path)
        _require(relative in package['files'] and relative not in answer,
                 'loaded path is outside the package or repeated')
        try:
            actual = row['text'].encode('utf-8', errors='strict')
        except UnicodeError as exc:
            raise ValueError('loaded source text is not UTF-8') from exc
        total += len(actual)
        _require(len(actual) <= MAX_FILE_BYTES and total <= MAX_TOTAL_BYTES,
                 'loaded-source bytes exceed bounds')
        expected = bounded_read(Path(package['snapshot_root']) / relative, MAX_FILE_BYTES)
        _require(actual == expected and (not is_root or actual == rootBytes),
                 'actual loaded source differs from copied source bytes')
        record = package['files'][relative]
        _require(len(actual) == record['bytes'] and _sha(actual) == record['sha256'],
                 'actual loaded source differs from package identity')
        answer[relative] = record['sha256']
    _require(roots == 1, 'capture must contain exactly one entry')
    verify_package(package)
    return dict(sorted(answer.items()))
