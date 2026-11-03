"""Reviewed live binary migration loader; no current manifest self-trust.

Install beside source_contract.py and the future frozen metadata bundle at
 tools/performance/artifact-binary/. The historical source chain is unchanged.
This loader performs no IO until explicitly called. No final SHA exists yet.
"""
from pathlib import Path
import hashlib
import types

FINAL_MANIFEST_SHA256 = 'bd96069b029ff0e7b0b6756dd0f57126c8b016ddf89d4359a8ae83243438e29e'
CONTRACT_SOURCE_SHA256 = 'f6c81c97a1284442c5825d38fc806639af9b49e8634b516d649dfa8c7583910d'


def live_contract(history_root, source_root=None):
    if FINAL_MANIFEST_SHA256 is None:
        raise ValueError('binary source migration is not frozen; live132 admission is unavailable')
    directory = Path(__file__).resolve().parent
    path = directory / 'source_contract.py'
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SOURCE_SHA256:
        raise ValueError('fixed binary source contract implementation SHA')
    module = types.ModuleType('fixed_binary_source_contract')
    module.__file__ = str(path)
    # Execute only this separately author-pinned maintenance implementation;
    # never a candidate Haskell module or timestamp-selected .pyc.
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module.Contract(directory, FINAL_MANIFEST_SHA256, history_root, source_root=source_root)
