"""Project shape coordinates and their completed oracle and sampling results."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'testing'))
import events


def active():
    return os.environ.get('MLF_TEST_SUITE') in ('compiler-shapes', 'compiler-shapes-correctness')


def case_ids(cells, pilot=False):
    kinds = ('correctness',) if pilot else ('correctness', 'comparison')
    return [f'compiler-shapes/{kind}/{family}-{size}'
            for family, size in cells for kind in kinds]


def select(cells, pilot=False, *, exclude=False):
    """Keep the matrix order and select a coordinate without changing its repeats."""
    cells = list(cells)
    exact = os.environ.get('MLF_TEST_EXACT', '') if active() and not exclude else ''
    if exact:
        for cell in cells:
            if exact in case_ids([cell], pilot):
                return [cell], [exact]
        raise SystemExit(f'shape case is outside this selection: {exact}')
    return cells, case_ids(cells, pilot)


def list_cases(cells, pilot=False):
    print(json.dumps(select(cells, pilot)[1]))


def start(ids, cell, pilot=False, **details):
    for identity in case_ids([cell], pilot):
        if identity in ids:
            events.start(identity, **details)


def result(ids, cell, status, pilot=False, **details):
    for identity in case_ids([cell], pilot):
        if identity in ids:
            events.result(identity, status, **details)
