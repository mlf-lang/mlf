"""Invert only the reviewed driver delta for the retained validation proof.

This source admission does not supply behavioral expectations. Runtime controls
use the unprojected candidate and the complete independent old datatype encoder.
"""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
MANIFEST_SHA='981e66aaffbbfeaf76bb5b08efc9615e691f14816e0eaecf525fb7122bab141f'

def require(value,message):
    if not value:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def manifest():
    raw=(HERE/'session-delta.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed datatype-context session delta')
    value=json.loads(raw)
    require(value['format']=='datatype-context-session-projection-v1'
        and value['path']=='libraries/mlf-crates/Bootstrap/CrateSession.hs'
        and len(value['edits'])==4,'exact four driver edits')
    return value

def restore_previous_owner(raw):
    value=manifest()
    require(sha(raw)==value['new_sha256'],'exact datatype-context session owner')
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
