"""Reviewed builtin-regeneration source loader; graph135 and frozen132 evidence are unchanged.

Install beside source_contract.py and the future frozen metadata bundle at
 tools/performance/artifact-binary/. The historical source chain is unchanged.
This loader performs no IO until explicitly called. Both live pins are explicit.
"""
from pathlib import Path
import hashlib
import types
import os
import stat

FINAL_MANIFEST_SHA256 = 'fb8335e198e463d3a25b336f124d56dac141c6ad2063df531c09ade8e7411559'
CONTRACT_SOURCE_SHA256 = '80ab586aed593698fc60f1644e8f0b4b24fc5d33140e7da60675ee5cf6677c19'


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
    path = directory / 'builtin_regeneration_contract.py'
    raw = read_implementation(path)
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError('fixed builtin-regeneration source contract implementation SHA')
    module = types.ModuleType('fixed_binary_source_contract')
    module.__file__ = str(path)
    # Execute only this separately author-pinned maintenance implementation;
    # never a candidate Haskell module or timestamp-selected .pyc.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module.Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
