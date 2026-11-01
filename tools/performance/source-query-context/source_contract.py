"""Exact source-query storage owner inverse; never weakens historical validators."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PARENT_REF = '941b6c03bed05db0a5b3054d6d789e54204e3cea'
BASELINE_REF = '5172c4ade3b3141da2e64593c383892575b36699'
OLD_SHA = '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9'
NEW_SHA = 'a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf'
QUERY_OLD_SHA = '06263b9871c593c9f4f7a4f51975b8a38c9f96737f84a632afe5aa7525e50576'
QUERY_NEW_SHA = '9d6cda4a88c1891cd52e292691955ab2a34f9e03dd70ad764dbf52eb9de5ccb2'
OWNERS = {
    'Bootstrap.CrateSession': {
        'file': 'session-delta.json',
        'manifest_sha256': '6442aa9316137001e8c71cc54c2257f5c3bee388b7dee1f957b52edae99abc5a',
        'path': 'libraries/mlf-crates/Bootstrap/CrateSession.hs',
        'old': OLD_SHA, 'new': NEW_SHA, 'edit_count': 2},
    'Bootstrap.CrateQuery': {
        'file': 'query-delta.json',
        'manifest_sha256': 'd35a696a0dbe00def5c8bf579e88ae4b515b1c2f40f2318408c3dcf8548bc864',
        'path': 'libraries/mlf-crates/Bootstrap/CrateQuery.hs',
        'old': QUERY_OLD_SHA, 'new': QUERY_NEW_SHA, 'edit_count': 4},
}
# Only previously admitted complete owners may pass through to older layers.
# This replay allowance is not live-source admission: the registry requires
# the new hash of both owners together, and restore_previous_owner is strict.
REPLAY_PARENTS = {
    'Bootstrap.CrateSession': (OLD_SHA,
        '157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094',
        '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f'),
    'Bootstrap.CrateQuery': (QUERY_OLD_SHA,),
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(module='Bootstrap.CrateSession'):
    require(module in OWNERS, 'known source-query context owner')
    owner = OWNERS[module]
    raw = (HERE / owner['file']).read_bytes()
    require(sha(raw) == owner['manifest_sha256'], 'fixed source-query context source delta')
    value = json.loads(raw)
    metadata = {
        'format': 'source-query-context-projection-v1',
        'module': module, 'path': owner['path'],
        'parent_ref': PARENT_REF, 'baseline_ref': BASELINE_REF,
        'old_sha256': owner['old'], 'new_sha256': owner['new']}
    require(isinstance(value, dict) and set(value) == set(metadata) | {'edits'}
            and all(value[k] == v for k, v in metadata.items()),
            'exact source-query context owner transition')
    edits = value['edits']
    require(isinstance(edits, list) and len(edits) == owner['edit_count'],
            'exact source-query context edit count')
    for edit in edits:
        require(isinstance(edit, dict) and set(edit) == {'old', 'new'}
                and all(isinstance(edit[k], str) and edit[k] for k in ('old', 'new'))
                and edit['old'] != edit['new'], 'exact source-query context edit')
    return value


def restore_previous_owner(raw, module='Bootstrap.CrateSession'):
    value = manifest(module)
    require(sha(raw) == value['new_sha256'], 'complete current source-query context owner')
    restored = raw
    for edit in reversed(value['edits']):
        before, after = edit['old'].encode(), edit['new'].encode()
        require(restored.count(after) == 1, 'one inverse source-query context block')
        restored = restored.replace(after, before)
    require(sha(restored) == value['old_sha256'], 'complete previous owner recovered')
    forward = restored
    for edit in value['edits']:
        before, after = edit['old'].encode(), edit['new'].encode()
        require(forward.count(before) == 1, 'one forward source-query context block')
        forward = forward.replace(before, after)
    require(forward == raw, 'source-query context inverse exactly reversible')
    return restored


def current_or_parent(raw, module='Bootstrap.CrateSession'):
    manifest(module)
    if sha(raw) in REPLAY_PARENTS[module]:
        return raw
    return restore_previous_owner(raw, module)
