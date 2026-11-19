"""Load the pinned PR43 reconciliation source transition for current qualification and historical projections."""
from pathlib import Path
import hashlib
import types
import os
import stat

FINAL_MANIFEST_SHA256 = '3c9680bfd0a826b3420e846008b45e6b4cf72bd98c489eba2e708c0c4b40490c'
CONTRACT_SOURCE_SHA256 = 'dddb9222c8aac2af88979f48b46e0a0973f2dd167bc75637f293f1a6c97784a5'


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
