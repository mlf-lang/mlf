#!/usr/bin/env python3
"""Compare a representation-only migration with two independently produced generations."""
import argparse
import hashlib
import json
from pathlib import Path

from verify import Generation, cache_directory, frame, read, text, unpack
from artifact_binary_reference import tree_document
from artifact_binary_typed import n, s
from query_generation import V1


def acquire(cache):
    directory = cache_directory(cache)
    current = text(read(directory / 'CURRENT', 6))
    data = (directory / 'generations' / (current + '.mlfqg')).read_bytes()
    return Generation(data, expected_hash=current), data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline_cache', 'candidate_cache'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    old, before = acquire(args.baseline_cache)
    new, after = acquire(args.candidate_cache)
    if (old.version, new.version) != (1, 2):
        raise ValueError('expected v1 baseline and v2 candidate')
    ca, cb = unpack(text(old.config)), unpack(text(new.config))
    if ca[:1] + ca[2:] != cb[:1] + cb[2:] or len(ca) != 5 or len(cb) != 5:
        raise ValueError('configuration changed beyond compiler identity')
    if old.nodes != new.nodes:
        raise ValueError('logical rows changed')
    # Substitute only the measured compiler identity, then reconstruct every old byte.
    cb[1] = ca[1]
    recovered = tree_document([n(411, s(V1), s(frame(cb)), n(1, *new.rows))], 6)
    if recovered != before:
        raise ValueError('legacy generation bytes changed')
    print(json.dumps({'baseline_sha256': hashlib.sha256(before).hexdigest(),
                      'candidate_sha256': hashlib.sha256(after).hexdigest(),
                      'reencoded_sha256': hashlib.sha256(recovered).hexdigest(),
                      'rows': len(old.nodes),
                      'ordered_reads': sum(len(row['reads']) for row in old.nodes.values())}, indent=2))


if __name__ == '__main__':
    main()
