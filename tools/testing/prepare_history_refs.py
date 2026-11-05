#!/usr/bin/env python3
"""Fetch only reviewed squash source history, then verify it offline.

Run explicitly after a full-history checkout. Normal historical reads never
fetch. PR refs, unlike deleted source branches, preserve merged source tips;
the fetched ref is only a locator and must match the reviewed exact SHA.
"""
import subprocess
import history_refs as history


SOURCE_REFS = {
    '90319e3b8c3a7758cd68b3b6474ba0dff6a61923': 'refs/pull/25/head',
}


def prepare():
    for transport in history.SQUASH_TRANSPORTS.values():
        tree = history._object_tree(history.ROOT, transport.source, 'commit')
        if tree is None:
            source_ref = SOURCE_REFS.get(transport.source)
            if source_ref is None:
                raise ValueError('squash source has no reviewed fetch ref: ' + transport.source)
            subprocess.run(['git', 'fetch', '--no-tags', 'origin', source_ref],
                           cwd=history.ROOT, check=True, timeout=120)
            fetched = subprocess.check_output(
                ['git', '--no-replace-objects', 'rev-parse', '--verify', 'FETCH_HEAD'],
                cwd=history.ROOT, text=True).strip()
            if fetched != transport.source:
                raise ValueError('fetched squash source differs from reviewed SHA: ' + fetched)
            tree = history._object_tree(history.ROOT, transport.source, 'commit')
        if tree != transport.tree:
            raise ValueError('squash source tree differs from reviewed tree: ' + transport.source)
    for original in history.REVISIONS:
        history.verify_published_revision(original)


if __name__ == '__main__':
    prepare()
    print('Reviewed historical objects and squash transport verified.')
