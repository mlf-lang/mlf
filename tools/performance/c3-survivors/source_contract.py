"""Exact C3 fresh-survivor owner inverse, used only to retain earlier source-ownership proofs."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
MANIFEST_SHA='a25ffb909953e07c881e38091f7fcf0bcf5e68abbd67e09bbcc45ada7fc6f5f7'
OLD_SHA='157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094'
NEW_SHA='51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9'


def require(value,message):
    if not value:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def manifest():
    raw=(HERE/'session-delta.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed C3 session source delta')
    value=json.loads(raw)
    require(value['format']=='c3-survivors-projection-v1'
            and value['path']=='libraries/mlf-crates/Bootstrap/CrateSession.hs'
            and value['parent_ref']=='ffa3d201e4ea9c08109ff00df3f4fd66b56f3ab2'
            and value['old_sha256']==OLD_SHA and value['new_sha256']==NEW_SHA
            and len(value['edits'])==1,'exact one-block fresh-survivor owner transition')
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
    if sha(raw) in (OLD_SHA,'18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f'):return raw
    return restore_previous_owner(raw)
