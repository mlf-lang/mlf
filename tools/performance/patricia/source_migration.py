"""Reviewed source identities across the numeric/Patricia ABI boundary."""
from pathlib import Path
import hashlib, json
HERE=Path(__file__).resolve().parent
# Finalized once after canonical builtin regeneration, before confirmation.
MANIFEST_SHA='35feca71afa2d2c392df2d920b890f61a5dce84fd85c8c61909f5da32d31fea6'
DESIGN_MANIFEST_SHA='31e8f91c4de11d92e8d02f739df9ee9b96557ba4fc12f8a08bedd20e17f96d2a'
CONTRACT_MANIFEST_SHA='762b056350c72a204a5edfb4e5a65af7a0d1b4da603226a90f8ebb2b79294071'
SPARSE_MANIFEST_SHA='f925cbc17365a534db21e66ec806820ed7957fc2942dd9b1eb5d789f12b1b4cf'
DATATYPE_MANIFEST_SHA='6b819d779d924972f8123f258abbf0f97c410485bc97995ef0f8d9aee49bb9c2'

def datatype_delta():
    raw=(HERE.parent/'datatype-context/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATATYPE_MANIFEST_SHA:
        raise ValueError('fixed reviewed datatype-context source migration required')
    value=json.loads(raw)
    if (value['format']!='datatype-context-source-migration-v1'
        or value['parent_manifest_sha256']!=DESIGN_MANIFEST_SHA
        or value['parent_ref']!='c1b802bd505d20d3f52653b27bd3db506f1ff617'
        or set(value['changed_sources'])!={'Bootstrap.CrateQuery','Bootstrap.CrateSession'}
        or value['module_count']!=128 or value['unchanged_sources']!=126
        or value['added_sources'] or value['removed_sources'] or value['host_sources']):
        raise ValueError('exact two-owner datatype-context source migration')
    return value

def contract_delta():
    raw=(HERE.parent/'contract-context/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CONTRACT_MANIFEST_SHA:
        raise ValueError('fixed reviewed contract-context source migration required')
    value=json.loads(raw)
    if (value['format']!='contract-context-source-migration-v1'
        or value['parent_manifest_sha256']!=DATATYPE_MANIFEST_SHA
        or set(value['changed_sources'])!={'Bootstrap.CrateQuery','Bootstrap.CrateSession'}
        or value['module_count']!=128 or value['unchanged_sources']!=126
        or value['added_sources'] or value['removed_sources'] or value['host_sources']):
        raise ValueError('exact two-owner contract-context source migration')
    return value

def sparse_delta():
    raw=(HERE.parent/'sparse-contracts/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SPARSE_MANIFEST_SHA:
        raise ValueError('fixed reviewed sparse-contracts source migration required')
    value=json.loads(raw)
    if (value['format']!='sparse-contracts-source-migration-v1'
        or value['parent_manifest_sha256']!=CONTRACT_MANIFEST_SHA
        or value['parent_ref']!='48275901cd7b760cc8dd000ed54898a23a494a87'
        or set(value['changed_sources'])!={'Bootstrap.Classes','Bootstrap.CrateQuery','Bootstrap.CrateSession',
            'Bootstrap.SourceInference','MLF.BuiltinPreludeData'}
        or value['module_count']!=128 or value['unchanged_sources']!=123
        or value['added_sources'] or value['removed_sources'] or value['host_sources']):
        raise ValueError('exact five-owner sparse-contracts source migration')
    return value

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
    result=apply_changes(result,datatype_delta()['changed_sources'])
    result=apply_changes(result,contract_delta()['changed_sources'])
    return apply_changes(result,sparse_delta()['changed_sources'])


def host_sources(base):
    raw=(HERE/'source-migration.json').read_bytes()
    if MANIFEST_SHA is None or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:
        raise ValueError('fixed host ABI migration')
    rows=json.loads(raw)['host_sources']
    if not set(base)<=set(rows) or any(v not in (rows[k]['old'],rows[k].get('retained_F1_parent')) or not rows[k]['reviewed_change'] for k,v in base.items()):
        raise ValueError('exact frozen host parent')
    updated=apply_changes({k:row['new'] for k,row in rows.items()},design_delta()['host_sources'])
    return {k:updated[k] for k in base}
