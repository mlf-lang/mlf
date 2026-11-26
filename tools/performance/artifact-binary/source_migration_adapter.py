"""Load the pinned current and historical source projection contracts."""
from pathlib import Path
import hashlib
import types
import os
import stat
import sys

FINAL_MANIFEST_SHA256 = '4d8ada0eae02aee9e3f93cea6670a59f51e1f8b5d49d2c5a7d8e2ecbe66432cb'
CONTRACT_SOURCE_SHA256 = '52067d6ba346927ea257ddc45bb52b37d4b66520500d1013f242018e67d240b7'
FRAMEWORK_SOURCE_SHA256 = '535994d5eb58be50280c58d7f5cc7e0c10c2ea648619ca83772252d7647e903f'
FRAMEWORK_MANIFEST_SHA256 = '7dadb5521dec305170eca4169fe9a1195a9a35d5e1eface09bc6edcae1ee05cd'
FOUNDATION_MANIFEST_SHA256 = '4c51f5a1c1825d04ffae830e5b260366c3239d810d9a85809c386f1860128ca3'
PHASE2_MANIFEST_SHA256 = 'd30e6f73bcf1da12258c347668c86097aedbc818e79490fd54a72591322cf8f7'
HEAP_FORCE_MANIFEST_SHA256 = '256e98b459c8b6f279fee380645aeb8b583e8eebd93ea486b2b7573a48ad5f45'
DICTIONARY_DEMAND_MANIFEST_SHA256 = '96064dcd3d09e3e7e3be19a3a1cc701a2ce9660af7702f99f0e07801a30cd737'
THUNK_CAPTURES_MANIFEST_SHA256 = 'eb6062eda5c90fb8f4c4dd16f3dbc3be89b506da58c1446cf47908eed295f53b'
CHECKED_DISPATCH_MANIFEST_SHA256 = '9b4f8a525e657c253c9b7986100ce7e2ab8e93ad6d88c3c7f41342c2f43d883e'
RECURSIVE_WORKERS_MANIFEST_SHA256 = '29eb8ca255fbc467c0451541c2cb855a1ea0605706ed4d514a253a58c79ab308'
COLD_CRATES_MANIFEST_SHA256 = 'f75b2af0d3874216a5f83a67ed416f1d9d4aed822349e908e0d82c5194da4e52'
CHECKED_GRAPH_MANIFEST_SHA256 = '400c7b78ddc60bb5d024869b50a4b99915735843d82d85a9f0b8c80639b84020'


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
    directory = Path(__file__).resolve().parent
    foundation = directory / 'foundation_phase2_source.py'
    if os.path.lexists(foundation):
        module = pinned_module(foundation, 'bea443385dc8bc16550a6a32eb07d7ecc063c024a0c0eb40180b83d69bb1734a')
        return module.qualified_contract(Path(history_root).resolve(strict=True).parents[1], source_root).contract
    directory, previous, current = contracts()
    contract = current.successor_type(previous, FINAL_MANIFEST_SHA256,
                                      FRAMEWORK_MANIFEST_SHA256, FOUNDATION_MANIFEST_SHA256,
                                      PHASE2_MANIFEST_SHA256, HEAP_FORCE_MANIFEST_SHA256,
                                      DICTIONARY_DEMAND_MANIFEST_SHA256, THUNK_CAPTURES_MANIFEST_SHA256,
                                      CHECKED_DISPATCH_MANIFEST_SHA256, RECURSIVE_WORKERS_MANIFEST_SHA256,
                                      COLD_CRATES_MANIFEST_SHA256, CHECKED_GRAPH_MANIFEST_SHA256,
                                      read_implementation)
    return contract(directory, CHECKED_GRAPH_MANIFEST_SHA256, history_root, source_root=source_root)
