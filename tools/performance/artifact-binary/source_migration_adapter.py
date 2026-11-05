"""Load the pinned DeclId source transition for current qualification and historical projections."""
from pathlib import Path
import hashlib
import types
import os
import stat

FINAL_MANIFEST_SHA256 = '83441de413f5ee62defc11707ce980b25270e576043330761ff90461a4ac62aa'
CONTRACT_SOURCE_SHA256 = '8bde985f649add7efb7625b7f4dba2a99747ff0cb7d1dbe327751f7f5784888e'


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
    path = directory / 'declid_contract.py'
    raw = read_implementation(path)
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError('fixed DeclId source contract implementation SHA')
    import sys
    name = '_mlf_declid_contract_' + CONTRACT_SOURCE_SHA256
    if name in sys.modules:
        return sys.modules[name].Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    # Execute only this separately author-pinned maintenance implementation;
    # never a candidate Haskell module or timestamp-selected .pyc.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    sys.modules[name] = module
    return module.Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
