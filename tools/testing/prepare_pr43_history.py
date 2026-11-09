#!/usr/bin/env python3
"""Recover exact PR43 predecessors after its authenticated squash publication.

The PR ref is only a locator. Source, integration, parents and predecessor trees
are independently pinned; no replacement or shallow ancestry is accepted.
"""
import subprocess
import history_refs as history

SOURCE_REF = 'refs/pull/43/head'
TRANSPORT = history.SquashTransport(
    'db7d319a9bd7bc63e4ed1ea1d6aa5f4acf519e3d',
    '4d7724484b39ad9438236ea719ca2ce45c1cf12c',
    'b4b472f7abfe837399e1051aa73e1af3c852d968',
    '894a59e60fbb2f373e1f38b0dfb9af248fa1bd62')
PREDECESSORS = (
    ('4fd6730d35b6ecaf8e169ad228ac3c7a3ed56160',
     '1c60d3daca5162bd24658d295169f601593345ef'),
    ('8c4556416023ac727e3fb2294070358a3dae8d9e',
     'c20bd3d8e0cdd7e319dfca77ea0b86cfbf77554d'),
)


def verify(candidate, target='HEAD'):
    history._require_complete_history()
    if candidate != TRANSPORT.source:
        raise ValueError('PR43 source locator differs from reviewed SHA')
    for identity, tree in PREDECESSORS:
        if history._object_tree(history.ROOT, identity, 'commit') != tree:
            raise ValueError('PR43 predecessor tree differs or is unavailable')
        history.verify_squash_transport(identity, TRANSPORT, target)
    if not history._is_ancestor(PREDECESSORS[1][0], PREDECESSORS[0][0]):
        raise ValueError('PR43 predecessor lineage differs')


def prepare():
    history._require_complete_history()
    # Prove this checkout descends from the reviewed integration before fetching.
    if history._object_tree(history.ROOT, TRANSPORT.integration, 'commit') != TRANSPORT.tree:
        raise ValueError('PR43 integration tree differs or is unavailable')
    if history._parents(TRANSPORT.integration) != [TRANSPORT.parent]:
        raise ValueError('PR43 integration parent differs')
    if not history._is_ancestor(TRANSPORT.integration, 'HEAD'):
        raise ValueError('PR43 integration ancestry differs')
    needed = (TRANSPORT.source, *(identity for identity, _ in PREDECESSORS))
    candidate = TRANSPORT.source
    if any(history._object_tree(history.ROOT, identity, 'commit') is None for identity in needed):
        subprocess.run(['git', '--no-replace-objects', 'fetch', '--no-tags', 'origin', SOURCE_REF],
                       cwd=history.ROOT, check=True, timeout=120)
        candidate = history._git('rev-parse', '--verify', 'FETCH_HEAD').decode('ascii').strip()
    verify(candidate)
    subprocess.run(['git', '--no-replace-objects', 'update-ref',
                    'refs/history/verified-source-' + TRANSPORT.source, candidate],
                   cwd=history.ROOT, check=True)
