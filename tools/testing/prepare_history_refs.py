#!/usr/bin/env python3
"""Fetch PR19 source when no authenticated sealed source is available.

The PR ref is a locator, never authority. The fetched source must be the exact
single-parent, single-literal seal of the pinned precursor. Ordinary historical
reads remain offline. Full-history checkout is required.
"""
import subprocess
import history_refs as history

SOURCE_REF = 'refs/pull/19/head'


def prepare():
    history._require_complete_history()
    if history.SOURCE_ANCHOR == '0' * 40:
        raise ValueError('unsealed publication source anchor')
    available = history._object_tree(history.ROOT, history.SOURCE_ANCHOR, 'commit')
    source = None
    if available is not None:
        history.verify_anchor()
        source = history.verified_source_in_checkout()
    if source is None:
        subprocess.run(['git', '--no-replace-objects', 'fetch', '--no-tags', 'origin', SOURCE_REF],
                       cwd=history.ROOT, check=True, timeout=120)
        candidate = history._git('rev-parse', '--verify', 'FETCH_HEAD').decode('ascii').strip()
        history.verify_source(candidate)
        # Publish this local locator only after all source checks succeeded.
        # Rejected fetches may install P, but cannot make a retry trust P alone.
        subprocess.run(['git', '--no-replace-objects', 'update-ref',
                        history.VERIFIED_SOURCE_REF, candidate], cwd=history.ROOT, check=True)
    for original in history.REVISIONS:
        history.verify_published_revision(original)


if __name__ == '__main__':
    prepare()
    print('Reviewed historical identities and sealed squash transport verified.')
