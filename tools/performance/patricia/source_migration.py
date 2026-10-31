"""Reviewed source identities across the numeric/Patricia ABI boundary."""
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent
# Finalized once after canonical builtin regeneration, before confirmation.
MANIFEST_SHA='35feca71afa2d2c392df2d920b890f61a5dce84fd85c8c61909f5da32d31fea6'

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
    return result


def host_sources(base):
    raw=(HERE/'source-migration.json').read_bytes()
    if MANIFEST_SHA is None or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:
        raise ValueError('fixed host ABI migration')
    rows=json.loads(raw)['host_sources']
    if not set(base)<=set(rows) or any(v not in (rows[k]['old'],rows[k].get('retained_F1_parent')) or not rows[k]['reviewed_change'] for k,v in base.items()):
        raise ValueError('exact frozen host parent')
    return {k:rows[k]['new'] for k in base}
