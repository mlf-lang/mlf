"""Load the pinned PR43 reconciliation source transition for current qualification and historical projections."""
from pathlib import Path
import hashlib
import types
import os
import stat

FINAL_MANIFEST_SHA256 = '333b2b7df81119d772eca59945f1c1261075a6bd50d0285ac6bc1e3335a908ad'
CONTRACT_SOURCE_SHA256 = '99e37b2b6e082c6962f16bde8d7c55979a065bbe65ff47914c06e986ea6645de'


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
    directory = Path(__file__).resolve().parent
    path = directory / 'reconciliation_contract.py'
    raw = read_implementation(path)
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError('fixed PR43 reconciliation source contract implementation SHA')
    import sys
    name = '_mlf_pr43_contract_' + CONTRACT_SOURCE_SHA256
    if name in sys.modules:
        return sys.modules[name].Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    # Execute only this separately author-pinned maintenance implementation;
    # never a candidate Haskell module or timestamp-selected .pyc.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    sys.modules[name] = module
    return module.Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
