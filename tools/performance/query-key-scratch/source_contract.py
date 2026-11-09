"""Exact scratch-lifecycle owner inverse; historical contracts stay frozen."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PARENT_REF = 'd6fe38c56fde162506700af40e031534c075e129'
BASELINE_REF = '5172c4ade3b3141da2e64593c383892575b36699'
OLD_SHA = 'a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf'
NEW_SHA = '5c888e550760f023278beaeffb137a5e3940980b19be2850186ce35ff117805b'
QUERY_OLD_SHA = '9d6cda4a88c1891cd52e292691955ab2a34f9e03dd70ad764dbf52eb9de5ccb2'
QUERY_NEW_SHA = '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68'
OWNERS = {'Bootstrap.CrateQuery': {'file': 'query-delta.json', 'manifest_sha256': '0c04d92f7da1eea83192e14fa870de681c4fac962bf79badb80c38ab6f20c411', 'path': 'libraries/mlf-crates/Bootstrap/CrateQuery.hs', 'old': '9d6cda4a88c1891cd52e292691955ab2a34f9e03dd70ad764dbf52eb9de5ccb2', 'new': '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68', 'edit_count': 3}, 'Bootstrap.CrateSession': {'file': 'session-delta.json', 'manifest_sha256': '5534f3bfc032fbc51aa71eee39992f67760bb337a6690f9490bea08a5b364e06', 'path': 'libraries/mlf-crates/Bootstrap/CrateSession.hs', 'old': 'a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf', 'new': '5c888e550760f023278beaeffb137a5e3940980b19be2850186ce35ff117805b', 'edit_count': 1}}
# Complete historical replay only; live registry requires both new owners.
REPLAY_PARENTS = {'Bootstrap.CrateSession': ('a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf', '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9', '157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094', '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f'), 'Bootstrap.CrateQuery': ('9d6cda4a88c1891cd52e292691955ab2a34f9e03dd70ad764dbf52eb9de5ccb2', '06263b9871c593c9f4f7a4f51975b8a38c9f96737f84a632afe5aa7525e50576')}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(module='Bootstrap.CrateSession'):
    require(module in OWNERS, 'known query-key scratch owner')
    owner = OWNERS[module]
    raw = (HERE / owner['file']).read_bytes()
    require(sha(raw) == owner['manifest_sha256'], 'fixed query-key scratch source delta')
    value = json.loads(raw)
    metadata = {
        'format': 'query-key-scratch-projection-v1',
        'module': module, 'path': owner['path'],
        'parent_ref': PARENT_REF, 'baseline_ref': BASELINE_REF,
        'old_sha256': owner['old'], 'new_sha256': owner['new']}
    require(isinstance(value, dict) and set(value) == set(metadata) | {'edits'}
            and all(value[k] == v for k, v in metadata.items()),
            'exact query-key scratch owner transition')
    edits = value['edits']
    require(isinstance(edits, list) and len(edits) == owner['edit_count'],
            'exact query-key scratch edit count')
    for edit in edits:
        require(isinstance(edit, dict) and set(edit) == {'old', 'new'}
                and all(isinstance(edit[k], str) and edit[k] for k in ('old', 'new'))
                and edit['old'] != edit['new'], 'exact query-key scratch edit')
    return value


def restore_previous_owner(raw, module='Bootstrap.CrateSession'):
    value = manifest(module)
    require(sha(raw) == value['new_sha256'], 'complete current query-key scratch owner')
    restored = raw
    for edit in reversed(value['edits']):
        before, after = edit['old'].encode(), edit['new'].encode()
        require(restored.count(after) == 1, 'one inverse query-key scratch block')
        restored = restored.replace(after, before)
    require(sha(restored) == value['old_sha256'], 'complete previous owner recovered')
    forward = restored
    for edit in value['edits']:
        before, after = edit['old'].encode(), edit['new'].encode()
        require(forward.count(before) == 1, 'one forward query-key scratch block')
        forward = forward.replace(before, after)
    require(forward == raw, 'query-key scratch inverse exactly reversible')
    return restored


def current_or_parent(raw, module='Bootstrap.CrateSession'):
    manifest(module)
    if sha(raw) in REPLAY_PARENTS[module]:
        return raw
    return restore_previous_owner(raw, module)
