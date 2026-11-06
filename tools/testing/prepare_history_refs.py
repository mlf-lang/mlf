#!/usr/bin/env python3
"""Prepare closed PR19/25 sources and the independent PR22 seal.

Fetch refs are locators, never proof. Only successful candidate authentication
can retain a local locator; failed fetches installing P cannot authorize retry.
"""
import subprocess
import history_refs as history

SOURCE_REF = 'refs/pull/22/head'
SOURCE_REFS = {
    '33abccb3055efca34608810bc3b5d4010e98ef46': 'refs/pull/19/head',
    '90319e3b8c3a7758cd68b3b6474ba0dff6a61923': 'refs/pull/25/head',
}


def _fetch(ref):
    subprocess.run(['git', '--no-replace-objects', 'fetch', '--no-tags', 'origin', ref],
                   cwd=history.ROOT, check=True, timeout=120)
    return history._git('rev-parse', '--verify', 'FETCH_HEAD').decode('ascii').strip()


def _retain(ref, candidate):
    subprocess.run(['git', '--no-replace-objects', 'update-ref', ref, candidate],
                   cwd=history.ROOT, check=True)


def _prepare_closed_source(source, verifier):
    retained = 'refs/history/verified-source-' + source
    result = subprocess.run(['git', '--no-replace-objects', 'rev-parse', '--verify', '--quiet', retained],
                            cwd=history.ROOT, stdout=subprocess.PIPE)
    if result.returncode == 0:
        candidate = result.stdout.decode('ascii').strip()
    elif result.returncode == 1:
        ref = SOURCE_REFS.get(source)
        if ref is None:
            raise ValueError('no reviewed source fetch ref')
        candidate = _fetch(ref)
    else:
        raise ValueError('verified historical source locator lookup failed')
    if candidate != source:
        raise ValueError('fetched historical source differs from reviewed SHA')
    verifier()
    _retain(retained, candidate)


def prepare():
    history._require_complete_history()
    if history.SOURCE_ANCHOR == '0' * 40:
        raise ValueError('unsealed publication source anchor')
    for event in history.COMPLETED_SEALS.values():
        _prepare_closed_source(event.source, lambda event=event: history.verify_completed_source(event))
    for rewritten, transport in history.SQUASH_TRANSPORTS.items():
        _prepare_closed_source(transport.source, lambda rewritten=rewritten, transport=transport:
                               history.verify_squash_source(rewritten, transport))
    available = history._object_tree(history.ROOT, history.SOURCE_ANCHOR, 'commit')
    source = None
    if available is not None:
        history.verify_anchor()
        source = history.verified_source_in_checkout()
    if source is None:
        candidate = _fetch(SOURCE_REF)
        history.verify_source(candidate)
        _retain(history.VERIFIED_SOURCE_REF, candidate)
    for original in history.REVISIONS:
        history.verify_published_revision(original)


if __name__ == '__main__':
    prepare()
    print('Reviewed historical identities and composed squash transports verified.')
