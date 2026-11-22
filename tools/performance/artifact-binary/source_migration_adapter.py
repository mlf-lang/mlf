"""Load the pinned current and historical source projection contracts."""
from pathlib import Path
import hashlib
import types
import os
import stat
import sys

FINAL_MANIFEST_SHA256 = '4d8ada0eae02aee9e3f93cea6670a59f51e1f8b5d49d2c5a7d8e2ecbe66432cb'
CONTRACT_SOURCE_SHA256 = '52067d6ba346927ea257ddc45bb52b37d4b66520500d1013f242018e67d240b7'
FRAMEWORK_SOURCE_SHA256 = '5a85b7ee1a3b76b5c4824bdecac26682e0c39b045f9587d5748fa37ee24a09d6'
FRAMEWORK_MANIFEST_SHA256 = '7dadb5521dec305170eca4169fe9a1195a9a35d5e1eface09bc6edcae1ee05cd'
FOUNDATION_MANIFEST_SHA256 = '4c51f5a1c1825d04ffae830e5b260366c3239d810d9a85809c386f1860128ca3'


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


def pinned_module(path, expected_sha):
    raw = read_implementation(path)
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError('pinned source contract implementation SHA: ' + path.name)
    name = '_mlf_source_contract_' + expected_sha
    if name not in sys.modules:
        module = types.ModuleType(name)
        module.__file__ = str(path)
        # Load authenticated source bytes without using a local Python cache.
        exec(compile(raw, str(path), 'exec'), module.__dict__)
        sys.modules[name] = module
    return sys.modules[name]


def contracts():
    directory = Path(__file__).resolve().parent
    previous = pinned_module(directory / 'reconciliation_contract.py', CONTRACT_SOURCE_SHA256)
    current = pinned_module(directory / 'framework_source_contract.py', FRAMEWORK_SOURCE_SHA256)
    return directory, previous.Contract, current


def historical_contract(history_root, source_root=None):
    directory, previous, current = contracts()
    archived = current.baseline_root(history_root)
    return previous(directory, FINAL_MANIFEST_SHA256, archived / 'tools/performance',
                    source_root=source_root or archived)


def live_contract(history_root, source_root=None):
    directory, previous, current = contracts()
    contract = current.successor_type(previous, FINAL_MANIFEST_SHA256,
                                      FRAMEWORK_MANIFEST_SHA256, FOUNDATION_MANIFEST_SHA256,
                                      read_implementation)
    return contract(directory, FOUNDATION_MANIFEST_SHA256, history_root, source_root=source_root)
