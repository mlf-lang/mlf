"""Exact owned projection-view source inverse; historical proofs only."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
MANIFEST_SHA='6aeb0fac2965143ec648c30ce2d540060480af1a422b146654d5c9377e605c5d'
OLD_SHA='51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9'
NEW_SHA='1210cfc8605bb8e45fd6801661175f892ebeddef561afa097b3fa3eafdde3c37'
PARENT='5172c4ade3b3141da2e64593c383892575b36699'
def require(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def manifest():
    raw=(HERE/'session-delta.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed projection source delta')
    value=json.loads(raw)
    require(value['format']=='owned-projection-view-inverse-v1'
        and value['path']=='libraries/mlf-crates/Bootstrap/CrateSession.hs'
        and value['parent_ref']==PARENT and value['old_sha256']==OLD_SHA
        and value['new_sha256']==NEW_SHA and len(value['edits'])==1,'exact projection owner transition')
    return value
def restore_previous_owner(raw):
    value=manifest();require(sha(raw)==NEW_SHA,'complete current projection owner');restored=raw
    for e in reversed(value['edits']):
        before,after=e['old'].encode(),e['new'].encode()
        require(restored.count(after)==1,'one inverse block');restored=restored.replace(after,before)
    require(sha(restored)==OLD_SHA,'complete previous owner recovered');forward=restored
    for e in value['edits']:
        before,after=e['old'].encode(),e['new'].encode()
        require(forward.count(before)==1,'one forward block');forward=forward.replace(before,after)
    require(forward==raw,'full reversible projection owner');return restored
def current_or_parent(raw):
    # Earlier authenticated producers remain replayable; the live registry
    # separately admits only NEW_SHA. No partial or unknown owner is accepted.
    manifest()
    if sha(raw) in (OLD_SHA,'157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094','18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f'):return raw
    return restore_previous_owner(raw)
