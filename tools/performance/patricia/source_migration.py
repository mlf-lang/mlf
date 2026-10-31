"""Reviewed source identities across the numeric/Patricia ABI boundary."""
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent
# Finalized once after canonical builtin regeneration, before confirmation.
MANIFEST_SHA='35feca71afa2d2c392df2d920b890f61a5dce84fd85c8c61909f5da32d31fea6'
DESIGN_MANIFEST_SHA='31e8f91c4de11d92e8d02f739df9ee9b96557ba4fc12f8a08bedd20e17f96d2a'

def design_delta():
    raw=(HERE/'index-design-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DESIGN_MANIFEST_SHA:
        raise ValueError('fixed reviewed index-design source migration required')
    value=json.loads(raw)
    if value['parent_manifest_sha256']!=MANIFEST_SHA or value['removed_sources']:
        raise ValueError('unchanged complete Int64 migration parent')
    return value

def apply_changes(base, changes):
    result=dict(base)
    for name,row in changes.items():
        if name not in base or row['old']!=base[name] or not row['reviewed_change'] or row['new']==row['old']:
            raise ValueError('declared index-design delta '+name)
        result[name]=row['new']
    return result

def migrate(base):
    raw=(HERE/'source-migration.json').read_bytes()
    if MANIFEST_SHA is None or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:
        raise ValueError('fixed reviewed Int64/Patricia source migration required')
    value=json.loads(raw)
    if value['old_sources']!=base or len(base)!=126 or value['removed_sources']:
        raise ValueError('exact retained 126-module source parent')
    result=dict(base)
    for name,row in value['changed_sources'].items():
        if name not in base or row['old']!=base[name] or not row['reviewed_change'] or row['new']==row['old']:
            raise ValueError('declared source delta '+name)
        result[name]=row['new']
    added=value['added_sources']
    if set(added)!={'Bootstrap.IntTree'} or set(added)&set(base):
        raise ValueError('one explicit Patricia helper module')
    result.update(added)
    if len(result)!=127:raise ValueError('127-module resulting source registry')
    design=design_delta()
    result=apply_changes(result,design['changed_sources'])
    if set(design['added_sources'])!={'Bootstrap.IntRank'} or 'Bootstrap.IntRank' in result:
        raise ValueError('one explicit rank-view module')
    result.update(design['added_sources'])
    if len(result)!=128:raise ValueError('128-module index-design source registry')
    return result


def host_sources(base):
    raw=(HERE/'source-migration.json').read_bytes()
    if MANIFEST_SHA is None or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:
        raise ValueError('fixed host ABI migration')
    rows=json.loads(raw)['host_sources']
    if not set(base)<=set(rows) or any(v not in (rows[k]['old'],rows[k].get('retained_F1_parent')) or not rows[k]['reviewed_change'] for k,v in base.items()):
        raise ValueError('exact frozen host parent')
    updated=apply_changes({k:row['new'] for k,row in rows.items()},design_delta()['host_sources'])
    return {k:updated[k] for k in base}
