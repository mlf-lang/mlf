"""Reviewed live graph135 source loader; frozen132 evidence remains historical.

Install beside source_contract.py and the future frozen metadata bundle at
 tools/performance/artifact-binary/. The historical source chain is unchanged.
This loader performs no IO until explicitly called. Both live pins are explicit.
"""
from pathlib import Path
import hashlib
import types
import os
import stat

FINAL_MANIFEST_SHA256 = '71532df8a848c84d9803c3aa4b9adba65fcb53c90a56e7551a5c6555b2dc00be'
CONTRACT_SOURCE_SHA256 = 'e41fb3ac880e2f53872de56571918b0c26409998fe771f2547f37da8271cf682'


def read_implementation(path):
    """Read only a bounded regular implementation, never follow a file link."""
    descriptor = None
    try:
        if path.is_symlink():
            raise ValueError('source implementation symlink')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) |
                             getattr(os, 'O_NONBLOCK', 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 65536:
            raise ValueError('source implementation regular-file / byte bound')
        raw = os.read(descriptor, 65537)
        if len(raw) > 65536:
            raise ValueError('source implementation grew past byte bound')
        return raw
    except OSError as error:
        raise ValueError('source implementation read failed') from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def live_contract(history_root, source_root=None):
    if FINAL_MANIFEST_SHA256 is None:
        raise ValueError('binary source migration is not frozen; live135 admission is unavailable')
    directory = Path(__file__).resolve().parent
    path = directory / 'query_graph_contract.py'
    raw = read_implementation(path)
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError('fixed graph source contract implementation SHA')
    module = types.ModuleType('fixed_binary_source_contract')
    module.__file__ = str(path)
    # Execute only this separately author-pinned maintenance implementation;
    # never a candidate Haskell module or timestamp-selected .pyc.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module.Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
