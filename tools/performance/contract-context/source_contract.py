"""Invert only the reviewed driver delta for the retained validation proof.

This source admission does not supply behavioral expectations. Runtime controls
use the unprojected candidate and the complete independent old datatype encoder.
"""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent
MANIFEST_SHA='414010e478dde453cafc620baf89cfb3afcab917476b346fb3ff821f08b904c0'

def require(value,message):
    if not value:raise ValueError(message)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def manifest():
    raw=(HERE/'session-delta.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed contract-context session delta')
    value=json.loads(raw)
    require(value['format']=='contract-context-session-projection-v1'
        and value['path']=='libraries/mlf-crates/Bootstrap/CrateSession.hs'
        and len(value['edits'])==4,'exact four contract driver edits')
    return value

def restore_previous_owner(raw):
    value=manifest()
    require(sha(raw)==value['new_sha256'],'exact contract-context session owner')
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
