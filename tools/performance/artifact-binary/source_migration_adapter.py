"""Reviewed live binary migration loader; no current manifest self-trust.

Install beside source_contract.py and the future frozen metadata bundle at
 tools/performance/artifact-binary/. The historical source chain is unchanged.
This loader performs no IO until explicitly called. No final SHA exists yet.
"""
from pathlib import Path
import hashlib
import types

FINAL_MANIFEST_SHA256 = '62a8ebfdbb6022eaf8c92e797b94ae0e1c8c841fd631b151679e58fdbad6438e'
CONTRACT_SOURCE_SHA256 = '188a49caf7efb8e954620d13b543ee3f52c4f8750d364e5c239a7b9ccf6e7e8a'


def live_contract(history_root, source_root=None):
    if FINAL_MANIFEST_SHA256 is None:
        raise ValueError('binary source migration is not frozen; live131 admission is unavailable')
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
