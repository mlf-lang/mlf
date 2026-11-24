#!/usr/bin/env python3
"""Run the unchanged Patricia suite against its authenticated stock endpoint."""
from pathlib import Path
import os
import runpy
import sys

from check_benchmark_phase2_successor import ROOT, successor

REPLAY = 'tools/release/replay_phase2_benchmark_reconciliation.py'
REPLAY_SHA = '9ea3c6afec5f092823f5916540b90891de65100b77393936d23ae5740de73281'
ORIGINAL = 'tools/performance/patricia/test_adapters.py'
ORIGINAL_SHA = '8c8f8d71866653cb07bf204fceedb702a22b50b73653857fc8dbb57d9286a8d5'


def main():
    # The composed outer edge verifies the actual Phase 2 source before the
    # original tests hit stock's own live/relocated and historical contracts.
    # Never use the reconstructed bytes to admit the actual live checkout.
    # Discovery goes through the same endpoint as execution; the original
    # unittest runner still owns list, exact selection and every case result.
    with successor.qualified(ROOT) as opened:
        replay = successor.pinned_module(ROOT, REPLAY, REPLAY_SHA)
        prior = replay.materialize_stock_metadata(opened)
        oracle = prior / ORIGINAL
        raw = successor.read(prior, ORIGINAL, 131072)
        successor.require(successor.sha(raw) == ORIGINAL_SHA,
                          'exact unmodified Patricia source-bound fixtures')
        parent = str(oracle.parent)
        cwd = Path.cwd()
        sys.path.insert(0, parent)
        try:
            os.chdir(prior)
            runpy.run_path(str(oracle), run_name='__main__')
        finally:
            os.chdir(cwd)
            sys.path.remove(parent)


if __name__ == '__main__':
    main()
