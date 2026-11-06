"""Invert only the reviewed driver delta for the retained validation proof.

This source admission does not supply behavioral expectations. Runtime controls
use the unprojected candidate and the complete independent frozen query/source encoders.
"""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
MANIFEST_SHA='ccc237720c8045dc479dd6c2889abeff338a115a56110d54fcd77420d29d242e'

def require(value,message):
    if not value:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def manifest():
    raw=(HERE/'session-delta.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed sparse-contracts session delta')
    value=json.loads(raw)
    require(value['format']=='sparse-contracts-session-projection-v1'
        and value['path']=='libraries/mlf-crates/Bootstrap/CrateSession.hs'
        and value['parent_ref']=='48275901cd7b760cc8dd000ed54898a23a494a87'
        and len(value['edits'])==3,'exact 3 combined driver edits')
    return value

def restore_previous_owner(raw):
    value=manifest()
    require(sha(raw)==value['new_sha256'],'exact sparse-contracts session owner')
    restored=raw
    for edit in reversed(value['edits']):
        before,after=edit['old'].encode(),edit['new'].encode()
        require(restored.count(after)==1,'one inverse driver edit')
        restored=restored.replace(after,before)
    require(sha(restored)==value['old_sha256'],'complete previous session recovered')
    forward=restored
    for edit in value['edits']:
        before,after=edit['old'].encode(),edit['new'].encode()
        require(forward.count(before)==1,'one forward driver edit')
        forward=forward.replace(before,after)
    require(forward==raw,'driver source projection is exactly reversible')
    return restored
