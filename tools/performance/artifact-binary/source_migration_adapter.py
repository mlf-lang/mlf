"""Reviewed live binary migration loader; no current manifest self-trust.

Install beside source_contract.py and the future frozen metadata bundle at
 tools/performance/artifact-binary/. The historical source chain is unchanged.
This loader performs no IO until explicitly called. No final SHA exists yet.
"""
from pathlib import Path
import hashlib
import types

FINAL_MANIFEST_SHA256 = '4f58855ea85e120d5830eb9a7b77eeb836047e1186ad8aeec04adc9da7458851'
CONTRACT_SOURCE_SHA256 = '3785d5cc85bfce4450f8f90e818c767588558ebaec9e85b78e495e5b2bf42ea8'


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
