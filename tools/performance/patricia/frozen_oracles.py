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
 'tools/performance/patricia/oracles/LegacyArtifactWriter.hs': 'ce63201b67af6645882ac54a26b4ea8c63eae8804761666146d55ac3ab1790bc',
 'tools/performance/patricia/oracles/V1FrozenSession.hs': 'a349d926b5f138c17e7a6ee79cb8b1e89de839a307746e377a68c4346e85d2b9',
 'tools/performance/patricia/oracles/graph/FrozenConstraint.hs': 'f61a8f545ab30af3a32230525b0fd835e18c01c6bee910badf77313e76c50626',
 'tools/performance/patricia/oracles/graph/FrozenGraph.hs': '939106e58b3b6b5769f3df7b8f9ea0a2f5ba76383e2c37989dda12d047247c94',
 'tools/performance/patricia/oracles/graph/FrozenIntMap.hs': 'f21e6723c710840e5012819628842b8593a92a2c7fc9278e2bc788005fb9aa77',
 'tools/performance/patricia/oracles/graph/FrozenIntSet.hs': '07890ca66e7aa8934533a4238ace385d5c1a13343a61dfe3baf6ca5198b03519',
 'tools/performance/patricia/oracles/graph/FrozenMap.hs': 'bfea8400e98570b91a04e79651f54d50383a32a967a81cc82378ab8182ba5cfe',
 'tools/performance/patricia/oracles/graph/FrozenSolver.hs': '3953f3305a1b0a18afe26c6773fe07cf8ba04c751bf7539dc18b838c1343917e',
 'tools/performance/patricia/oracles/p123/FrozenFingerprint.hs': '707ac4d9802385fd548b90f68837e7f0c2702b3568fedf993a5ee65714d5f0a0',
 'tools/performance/patricia/oracles/p123/FrozenSelectors.hs': 'b72dcd1aea7d2d6d69358eb95f94630183c426619652d7a9e5d82f9fd84e3dc3'}


def read_oracle(root, relative):
    path = Path(root) / relative
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FILES[relative]:
        raise ValueError('frozen runtime oracle changed: ' + relative)
    return path, raw
