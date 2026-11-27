"""Integrity of fixed independent reference programs, never current-source admission.

Origins and the one-time compile-ready adaptations are in oracles/README.md.
Maintained controls are only hashed as inputs to the current run.
"""
import hashlib
from pathlib import Path

DIRECTORY = Path('tools/performance/patricia/oracles')
FILES = {'tools/performance/crate-optimizations/p1/FrozenSelectorMap.hs': '9b7dce8485229d577862ea78e8be34cd28edd9766809a91de7ddf87dd43102e9',
 'tools/performance/crate-optimizations/p1/FrozenSelectorSet.hs': '882f4a8beba89fa538b398c99831891628e0b6ae28c5c7f8ce70680f6ef91d19',
 'tools/performance/crate-optimizations/p3/FrozenInferenceUnit.hs': '4693d0bc2a733200f9916fc756ab5a2df8736e95a0fdd3e625600725f5578351',
 'tools/performance/crate-optimizations/p3/FrozenPrefix.hs': '486ce3801e0d286d0884c46962bcb0311d8a1b889544fbc4bff774613f64a369',
 'tools/performance/patricia/oracles/V1FrozenSession.hs': 'a349d926b5f138c17e7a6ee79cb8b1e89de839a307746e377a68c4346e85d2b9',
 'tools/performance/patricia/oracles/graph/FrozenConstraint.hs': '6bcca99c530075c706f9913bea85b0cccc9765bce6c9bebb9fec453aff25e3ee',
 'tools/performance/patricia/oracles/graph/FrozenGraph.hs': '9e5b9bae98da5de3e55fa15f506e265cb3391701e4eb6f83546d5e86ef4462e7',
 'tools/performance/patricia/oracles/graph/FrozenSolver.hs': 'f6d537e02316f5cc466a1e2294d44fdcd5df5c55a4d7b06247393cffe36dd2e8',
 'tools/performance/patricia/oracles/p123/FrozenSelectors.hs': 'b72dcd1aea7d2d6d69358eb95f94630183c426619652d7a9e5d82f9fd84e3dc3'}


def read_oracle(root, relative):
    path = Path(root) / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FILES[relative]:
        raise ValueError('frozen runtime oracle changed: ' + relative)
    return path, raw
