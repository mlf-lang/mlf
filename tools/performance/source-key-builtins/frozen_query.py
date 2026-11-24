"""Adapt the pinned, named-only query oracle to a host with additional AST constructors."""
from pathlib import Path
import hashlib

_NAMED_TYPES_SHA256 = '7fd4bc9f8459459a4c3ad54da44d56bad274847e4b1af5365b1949d69793906e'
_DICTIONARY_TYPES_SHA256 = '9c6790a0469b6e6de6ac44bc39535f15fbed27cc283e4840cc3df4a34bc54964'
_PRIMITIVE_OPERAND_TYPES_SHA256 = 'c87f0e9e1dc675f324ecbcf5667a4f5761a30c9e16281ff19b38e925fd08d502'
# Only XTerm was extended; the frozen encoder consumes SExpr and SPattern.
_PROJECTION_SPINES_TYPES_SHA256 = 'dea89ecf8b8fbecdd7ba20e8b444eb8ba73a96fc75d34003c22aac1c443231f2'


def prepare_frozen_query(source: Path, out_dir: Path, *, expected_sha256: str, types_source: Path) -> Path:
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_sha256:
        raise ValueError(f"Frozen query source differs from the pinned oracle: {source}")
    types_sha256 = hashlib.sha256(types_source.read_bytes()).hexdigest()
    if types_sha256 == _NAMED_TYPES_SHA256:
        dictionary_nodes = []
    elif types_sha256 in (_DICTIONARY_TYPES_SHA256, _PRIMITIVE_OPERAND_TYPES_SHA256,
                          _PROJECTION_SPINES_TYPES_SHA256):
        dictionary_nodes = [b'SApplyDictionaries _ _', b'SBindDictionaries _ _']
    else:
        raise ValueError(f'Unsupported Bootstrap.Types source SHA-256 {types_sha256}: {types_source}')
    # Dictionary application and binding did not exist for the historical
    # oracle. Never encode them as a historical value.
    # These are all the pattern/expression case expressions in both dated
    # FrozenCrateQuery sources. Keep every historical branch verbatim, even
    # the wildcard in canonicalPattern; typed syntax has no historical key.
    cases = [(b'case pattern of {', 2, [b'SIndexedStringPattern _ _ _']),
             (b'case expression of {', 3, [b'SGlobal _ _', b'SDeclScope _ _', b'SWantedRefs _ _',
                                          b'SWantedScope _ _', b'SGivenScope _ _'] + dictionary_nodes)]
    adapted = original
    for anchor, count, constructors in cases:
        inserted = b''.join(b'\n      ' + ctor + b' -> panic "indexed syntax in historical named query oracle";'
                            for ctor in constructors)
        if adapted.count(anchor) != count or inserted in adapted:
            raise ValueError(f'Unexpected frozen query cases in {source}')
        expanded = adapted.replace(anchor, anchor + inserted)
        if expanded.replace(anchor + inserted, anchor) != adapted:
            raise ValueError(f'Irreversible frozen query adaptation in {source}')
        adapted = expanded
    output = out_dir / 'FrozenCrateQuery.hs'
    output.write_bytes(adapted)
    return output
