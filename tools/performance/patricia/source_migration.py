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

BATCH_MANIFEST_SHA='10f2da2458cbda85d61787be112fcb09e28d93cf97ebbd7b974eaccac5466f6b'

PERMISSION_MANIFEST_SHA='da5f482bb5c89e0e88d812eaacaafc4788bafef2cfbe709c924fed0e6179746e'

CANONICAL_CARRY_MANIFEST_SHA='bd5061cfcaecd26eb05c4f07628f9125dc0f226d679984ee7ad3fadaeed7451b'

FULL_MANIFEST_SHA='8a7118c56442506571541c5c20821086e8ce9aff987de058097a81e224e29bb0'

def full_delta():
    raw=(HERE.parent/'full-compiler/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=FULL_MANIFEST_SHA:
        raise ValueError('fixed reviewed owned projection source migration required')
    value=json.loads(raw)
    metadata={
        'format':'owned-projection-view-source-migration-v1',
        'parent_manifest_sha256':SURVIVORS_MANIFEST_SHA,
        'parent_ref':'5172c4ade3b3141da2e64593c383892575b36699',
        'module_count':128, 'unchanged_sources':127,
        'added_sources':{}, 'removed_sources':{}, 'host_sources':{}}
    if (set(value)!=set(metadata)|{'changed_sources'}
        or any(value[key]!=wanted for key,wanted in metadata.items())
        or set(value['changed_sources'])!={'Bootstrap.CrateSession'}):
        raise ValueError('exact one-owner owned projection source migration')
    for row in value['changed_sources'].values():
        if (set(row)!={'old','new','reviewed_change'} or not row['reviewed_change']
            or row['old']==row['new']
            or any(not isinstance(row[key],str) or len(row[key])!=64
                   or set(row[key])-set('0123456789abcdef') or row[key]=='0'*64
                   for key in ('old','new'))):
            raise ValueError('exact owned projection source hash row')
    return value

SCRATCH_MANIFEST_SHA='9ecbc912e288495a1ff7f5652e81b429c5cfafd2dcd2da951c395efdc762a95a'

def scratch_delta():
    raw=(HERE.parent/'query-key-scratch/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SCRATCH_MANIFEST_SHA:
        raise ValueError('fixed reviewed query-key scratch migration required')
    value=json.loads(raw)
    metadata={
        'format':'query-key-scratch-source-migration-v1',
        'parent_manifest_sha256':SOURCE_CONTEXT_MANIFEST_SHA,
        'parent_ref':'d6fe38c56fde162506700af40e031534c075e129',
        'baseline_ref':'5172c4ade3b3141da2e64593c383892575b36699',
        'module_count':128, 'unchanged_sources':126,
        'added_sources':{}, 'removed_sources':{}, 'host_sources':{}}
    hashes={
        'Bootstrap.CrateQuery':(
            '9d6cda4a88c1891cd52e292691955ab2a34f9e03dd70ad764dbf52eb9de5ccb2',
            '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68'),
        'Bootstrap.CrateSession':(
            'a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf',
            '5c888e550760f023278beaeffb137a5e3940980b19be2850186ce35ff117805b')}
    if (not isinstance(value,dict) or set(value)!=set(metadata)|{'changed_sources'}
        or any(value[key]!=wanted for key,wanted in metadata.items())
        or not isinstance(value['changed_sources'],dict)
        or set(value['changed_sources'])!=set(hashes)):
        raise ValueError('exact two-owner query-key scratch migration')
    for name,row in value['changed_sources'].items():
        if (not isinstance(row,dict) or set(row)!={'old','new','reviewed_change'}
            or not isinstance(row['reviewed_change'],str) or not row['reviewed_change']
            or (row['old'],row['new'])!=hashes[name]):
            raise ValueError('exact query-key scratch owner hashes')
    return value

SOURCE_CONTEXT_MANIFEST_SHA='5dbb5cbc5fcb047732e1ef48931c88a3dbd73030af4cc853f6a07ed951208a6e'

def source_context_delta():
    raw=(HERE.parent/'source-query-context/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_CONTEXT_MANIFEST_SHA:
        raise ValueError('fixed reviewed source-query context migration required')
    value=json.loads(raw)
    metadata={
        'format':'source-query-context-source-migration-v1',
        'parent_manifest_sha256':SURVIVORS_MANIFEST_SHA,
        'parent_ref':'941b6c03bed05db0a5b3054d6d789e54204e3cea',
        'baseline_ref':'5172c4ade3b3141da2e64593c383892575b36699',
        'module_count':128, 'unchanged_sources':126,
        'added_sources':{}, 'removed_sources':{}, 'host_sources':{}}
    hashes={
        'Bootstrap.CrateQuery':(
            '06263b9871c593c9f4f7a4f51975b8a38c9f96737f84a632afe5aa7525e50576',
            '9d6cda4a88c1891cd52e292691955ab2a34f9e03dd70ad764dbf52eb9de5ccb2'),
        'Bootstrap.CrateSession':(
            '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9',
            'a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf')}
    if (not isinstance(value,dict) or set(value)!=set(metadata)|{'changed_sources'}
        or any(value[key]!=wanted for key,wanted in metadata.items())
        or not isinstance(value['changed_sources'],dict)
        or set(value['changed_sources'])!=set(hashes)):
        raise ValueError('exact two-owner source-query context migration')
    for name,row in value['changed_sources'].items():
        if (not isinstance(row,dict) or set(row)!={'old','new','reviewed_change'}
            or not isinstance(row['reviewed_change'],str) or not row['reviewed_change']
            or (row['old'],row['new'])!=hashes[name]):
            raise ValueError('exact source-query context owner hashes')
    return value

SURVIVORS_MANIFEST_SHA='de9192eeaa64cc15ef8039ce2db936db0ed4d23b4578ecd40ac293c066730aff'

def survivors_delta():
    raw=(HERE.parent/'c3-survivors/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SURVIVORS_MANIFEST_SHA:
        raise ValueError('fixed reviewed C3 survivor source migration required')
    value=json.loads(raw)
    metadata={
        'format':'c3-survivors-source-migration-v1',
        'parent_manifest_sha256':C3_MANIFEST_SHA,
        'parent_ref':'ffa3d201e4ea9c08109ff00df3f4fd66b56f3ab2',
        'module_count':128, 'unchanged_sources':127,
        'added_sources':{}, 'removed_sources':{}, 'host_sources':{}}
    if (set(value)!=set(metadata)|{'changed_sources'}
        or any(value[key]!=wanted for key,wanted in metadata.items())
        or set(value['changed_sources'])!={'Bootstrap.CrateSession'}):
        raise ValueError('exact one-owner C3 survivor source migration')
    for row in value['changed_sources'].values():
        if (set(row)!={'old','new','reviewed_change'} or not row['reviewed_change']
            or row['old']==row['new']
            or any(not isinstance(row[key],str) or len(row[key])!=64
                   or set(row[key])-set('0123456789abcdef') or row[key]=='0'*64
                   for key in ('old','new'))):
            raise ValueError('exact C3 survivor source hash row')
    return value

C3_MANIFEST_SHA='ab3b36c9b7429bdc2b0a5e28beaf1afe92330c3279568a4ac34bb26d2a48e6e8'

def c3_delta():
    raw=(HERE.parent/'c3-delayed-index/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=C3_MANIFEST_SHA:
        raise ValueError('fixed reviewed C3 source migration required')
    value=json.loads(raw)
    metadata={
        'format':'c3-delayed-index-source-migration-v1',
        'parent_manifest_sha256':CANONICAL_CARRY_MANIFEST_SHA,
        'parent_ref':'9b35151dff377a8e0742e9a265f373bc53db98b0',
        'baseline_ref':'e123603d00f6f64e20e4d771836e49ddd808320f',
        'module_count':128, 'unchanged_sources':127,
        'added_sources':{}, 'removed_sources':{}, 'host_sources':{}}
    if (set(value)!=set(metadata)|{'changed_sources'}
        or any(value[key]!=wanted for key,wanted in metadata.items())
        or set(value['changed_sources'])!={'Bootstrap.CrateSession'}):
        raise ValueError('exact one-owner C3 source migration')
    for row in value['changed_sources'].values():
        if (set(row)!={'old','new','reviewed_change'} or not row['reviewed_change']
            or row['old']==row['new']
            or any(not isinstance(row[key],str) or len(row[key])!=64
                   or set(row[key])-set('0123456789abcdef') or row[key]=='0'*64
                   for key in ('old','new'))):
            raise ValueError('exact C3 source hash row')
    return value

def canonical_carry_delta():
    raw=(HERE.parent/'canonical-carry/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=CANONICAL_CARRY_MANIFEST_SHA:
        raise ValueError('fixed reviewed canonical-carry source migration required')
    value=json.loads(raw)
    metadata={
        'format':'pooled-canonical-carry-source-migration-v1',
        'parent_manifest_sha256':PERMISSION_MANIFEST_SHA,
        'parent_ref':'69580e21d20a742a235b3ea95aa4c68f20783265',
        'implementation_commit':'e123603d00f6f64e20e4d771836e49ddd808320f',
        'module_count':128, 'unchanged_sources':125,
        'added_sources':{}, 'removed_sources':[], 'host_sources':{}}
    if (set(value)!=set(metadata)|{'changed_sources'}
        or any(value[key]!=wanted for key,wanted in metadata.items())
        or set(value['changed_sources'])!={'Bootstrap.Separate','Bootstrap.CrateArtifact','MLF.BuiltinPreludeData'}):
        raise ValueError('exact three-source canonical-carry migration')
    for row in value['changed_sources'].values():
        if (set(row)!={'old','new','reviewed_change'} or not row['reviewed_change']
            or row['old']==row['new']
            or any(not isinstance(row[key],str) or len(row[key])!=64
                   or set(row[key])-set('0123456789abcdef') or row[key]=='0'*64
                   for key in ('old','new'))):
            raise ValueError('exact canonical-carry source hash rows')
    return value

def permission_delta():
    raw=(HERE.parent/'permission-view/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PERMISSION_MANIFEST_SHA:
        raise ValueError('fixed reviewed permission-view source migration required')
    value=json.loads(raw)
    if (value['format']!='permission-view-source-migration-v1'
        or value['parent_manifest_sha256']!=BATCH_MANIFEST_SHA
        or value['parent_ref']!='01ef8e70741c9f9ac4f27e489d059c96a4b33df5'
        or set(value['changed_sources'])!={'Bootstrap.Graph','MLF.BuiltinPreludeData'}
        or value['module_count']!=128 or value['unchanged_sources']!=126
        or value['added_sources'] or value['removed_sources'] or value['host_sources']):
        raise ValueError('exact Graph and regenerated-builtin source migration')
    return value

def batch_delta():
    raw=(HERE.parent/'batch-replacement/source-migration.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=BATCH_MANIFEST_SHA:
        raise ValueError('fixed reviewed batch-replacement source migration required')
    value=json.loads(raw)
    if (value['format']!='batch-replacement-source-migration-v1'
        or value['parent_manifest_sha256']!=SPARSE_MANIFEST_SHA
        or value['parent_ref']!='7bf7ac6db5e3db2daff2e0a1c249e68ae0db2d0c'
        or set(value['changed_sources'])!={'Bootstrap.LLVM','Bootstrap.LLVM.Library','Bootstrap.LLVM.Optimize'}
        or value['module_count']!=128 or value['unchanged_sources']!=125
        or value['added_sources'] or value['removed_sources'] or value['host_sources']):
        raise ValueError('exact three-owner batch-replacement source migration')
    return value

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

def memo_contract():
    import importlib.util
    path=Path(__file__).resolve().parent.parent/'source-context-read-reuse/source_contract.py'
    spec=importlib.util.spec_from_file_location('source_context_read_reuse_contract',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def diamond_contract():
    import importlib.util
    path=HERE.parent/'source-context-projection-merge/source_contract.py'
    spec=importlib.util.spec_from_file_location('source_diamond_registry',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

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
    result=apply_changes(result,sparse_delta()['changed_sources'])
    result=apply_changes(result,batch_delta()['changed_sources'])
    result=apply_changes(result,permission_delta()['changed_sources'])
    result=apply_changes(result,canonical_carry_delta()['changed_sources'])
    result=apply_changes(result,c3_delta()['changed_sources'])
    result=apply_changes(result,survivors_delta()['changed_sources'])
    upstream=apply_changes(result,full_delta()['changed_sources'])
    result=apply_changes(result,source_context_delta()['changed_sources'])
    result=apply_changes(result,scratch_delta()['changed_sources'])
    return memo_contract().advance_registry(diamond_contract().merge_registry(result,upstream))


def host_sources(base):
    raw=(HERE/'source-migration.json').read_bytes()
    if MANIFEST_SHA is None or hashlib.sha256(raw).hexdigest()!=MANIFEST_SHA:
        raise ValueError('fixed host ABI migration')
    rows=json.loads(raw)['host_sources']
    if not set(base)<=set(rows) or any(v not in (rows[k]['old'],rows[k].get('retained_F1_parent')) or not rows[k]['reviewed_change'] for k,v in base.items()):
        raise ValueError('exact frozen host parent')
    updated=apply_changes({k:row['new'] for k,row in rows.items()},design_delta()['host_sources'])
    return {k:updated[k] for k in base}
