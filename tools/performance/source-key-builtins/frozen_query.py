"""Adapt the pinned, named-only query oracle to a host with additional AST constructors."""
from pathlib import Path
import hashlib


def prepare_frozen_query(source: Path, out_dir: Path, *, expected_sha256: str) -> Path:
    original = source.read_bytes()
    if hashlib.sha256(original).hexdigest() != expected_sha256:
        raise ValueError(f"Frozen query source differs from the pinned oracle: {source}")
    # These are all the pattern/expression case expressions in both dated
    # FrozenCrateQuery sources. Keep every historical branch verbatim, even
    # the wildcard in canonicalPattern; typed syntax has no historical key.
    cases = [(b'case pattern of {', 2, [b'SIndexedStringPattern _ _ _']),
             (b'case expression of {', 3, [b'SGlobal _ _', b'SDeclScope _ _', b'SWantedRefs _ _'])]
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
