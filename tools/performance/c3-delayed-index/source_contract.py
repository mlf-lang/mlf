"""Exact C3 owner inverse, used only to retain earlier source-ownership proofs."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
MANIFEST_SHA='d9cd27a5679e0e2e6509283e6441531d8dc91b3e21b4abb0cf0988a603e2b828'
OLD_SHA='18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f'
NEW_SHA='157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094'


def require(value,message):
    if not value:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def manifest():
    raw=(HERE/'session-delta.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed C3 session source delta')
    value=json.loads(raw)
    require(value['format']=='c3-private-session-projection-v1'
            and value['path']=='libraries/mlf-crates/Bootstrap/CrateSession.hs'
            and value['parent_ref']=='e123603d00f6f64e20e4d771836e49ddd808320f'
            and value['old_sha256']==OLD_SHA and value['new_sha256']==NEW_SHA
            and len(value['edits'])==2,'exact two-block C3 owner transition')
    return value


def restore_previous_owner(raw):
    value=manifest()
    require(sha(raw)==NEW_SHA,'complete current C3 owner')
    restored=raw
    for edit in reversed(value['edits']):
        before,after=edit['old'].encode(),edit['new'].encode()
        require(restored.count(after)==1,'one inverse C3 block')
        restored=restored.replace(after,before)
    require(sha(restored)==OLD_SHA,'complete previous owner recovered')
    forward=restored
    for edit in value['edits']:
        before,after=edit['old'].encode(),edit['new'].encode()
        require(forward.count(before)==1,'one forward C3 block')
        forward=forward.replace(before,after)
    require(forward==raw,'C3 owner inverse exactly reversible')
    return restored


def current_or_parent(raw):
    # Older independently authenticated producers remain replayable. This does
    # not admit the old owner as the current candidate: the live source registry
    # separately requires NEW_SHA. Unknown or partially projected owners fail.
    manifest()
    if sha(raw)==OLD_SHA:return raw
    return restore_previous_owner(raw)
