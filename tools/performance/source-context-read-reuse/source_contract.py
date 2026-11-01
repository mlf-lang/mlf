"""Strict complete-owner inverse for invocation-local context read reuse."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
MANIFEST_SHA='f53f560ee5f2014ecd7db26c555040a8bf531fa4d6c77bd36d32934d67172c1c'
EXPECTED={'format': 'source-context-read-reuse-migration-v1', 'parent_ref': '6a82267e060afadeddd14a14b38b62af0ee82d11', 'module_count': 128, 'unchanged_count': 126, 'added_sources': {}, 'removed_sources': {}, 'host_sources': {}, 'changed_sources': {'Bootstrap.CrateQuery': {'old': '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68', 'new': '3a7cb44316980c5a40916a0cfd595472091efba215ab101382c65963f05023f6', 'reviewed_change': 'per-held-invocation verified context read reuse'}, 'Bootstrap.CrateSession': {'old': 'b35637aab8fb473646af9719fe857f1fdb1cda822feedf05e06739e95f4a73a4', 'new': '8adefc9d5346f375dd8568a59400bd498695af270b6fc70bea296c0698b5d190', 'reviewed_change': 'per-held-invocation verified context read reuse'}}, 'owners': {'Bootstrap.CrateQuery': {'file': 'query-delta.json', 'path': 'libraries/mlf-crates/Bootstrap/CrateQuery.hs', 'old': '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68', 'new': '3a7cb44316980c5a40916a0cfd595472091efba215ab101382c65963f05023f6', 'edit_count': 6, 'delta_sha256': '022636870b0dd0da2abdfcca3764efb4fb947dc17402b88025434742588f7ee0'}, 'Bootstrap.CrateSession': {'file': 'session-delta.json', 'path': 'libraries/mlf-crates/Bootstrap/CrateSession.hs', 'old': 'b35637aab8fb473646af9719fe857f1fdb1cda822feedf05e06739e95f4a73a4', 'new': '8adefc9d5346f375dd8568a59400bd498695af270b6fc70bea296c0698b5d190', 'edit_count': 3, 'delta_sha256': '624818cd1064a142066198aed31f49c8ed3c22f9143042fe33b27c7900b3544f'}}, 'parent_registry_sha256': '8d259a293e60df946362123fd631156fdedbad1e1c956d67235b87960af6c9fa', 'current_registry_sha256': 'd538b5d17534920d708e547b3ad47a75a330a3688e251181e62000bf7ba280ea', 'frozen_references': {'full-compiler/session-delta.json': '6aeb0fac2965143ec648c30ce2d540060480af1a422b146654d5c9377e605c5d', 'full-compiler/source-migration.json': '8a7118c56442506571541c5c20821086e8ce9aff987de058097a81e224e29bb0', 'full-compiler/source_contract.py': '68eec55dbeb8eec2a1d983dac1f5f61f03e1c03057c0cf9689c6361e8141a027', 'query-key-scratch/query-delta.json': '0c04d92f7da1eea83192e14fa870de681c4fac962bf79badb80c38ab6f20c411', 'query-key-scratch/session-delta.json': '5534f3bfc032fbc51aa71eee39992f67760bb337a6690f9490bea08a5b364e06', 'query-key-scratch/source-migration.json': '9ecbc912e288495a1ff7f5652e81b429c5cfafd2dcd2da951c395efdc762a95a', 'query-key-scratch/source_contract.py': 'a445a69b7c5a8eaae9cfeb794192ea5bfd7201e5a1bc96fb1dd231933f8281ba', 'source-query-context/query-delta.json': 'd35a696a0dbe00def5c8bf579e88ae4b515b1c2f40f2318408c3dcf8548bc864', 'source-query-context/session-delta.json': '6442aa9316137001e8c71cc54c2257f5c3bee388b7dee1f957b52edae99abc5a', 'source-query-context/source-migration.json': '5dbb5cbc5fcb047732e1ef48931c88a3dbd73030af4cc853f6a07ed951208a6e', 'source-query-context/source_contract.py': '8cacdec2b8f398d357fd01555e5095eeb2f56376beebffcd9f57980a504cec29', 'source-context-projection-merge/source_contract.py': '352ae609b851fc57586ccaea7cd77a95a6bb5c85d29ae0b8c7d684962ec1ee2d', 'source-context-projection-merge/source-migration.json': 'be4b1897299a20e7f2cc1ae0ad7dc056da48418920141ca7a9329b14271c6112', 'source-context-projection-merge/right-session-delta.json': 'c7d673c951ea8ddc9e64f091bfec6c539d6088739f6da9611bdf51bb10bd5396', 'source-context-projection-merge/left-session-delta.json': '73fb0aae3ec2efe06c4c8654e869f77efd07cf96460663b96ee12092de3fb076'}}
OWNERS=EXPECTED['owners']
def require(value,message):
    if not value:raise ValueError(message)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def registry_sha(value):return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def manifest():
    raw=(HERE/'source-migration.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed read-reuse manifest')
    value=json.loads(raw);require(value==EXPECTED,'exact read-reuse scope and identities')
    for path,digest in value['frozen_references'].items():
        require(sha((HERE.parent/path).read_bytes())==digest,'unchanged frozen predecessor '+path)
    return value
def owner_delta(module='Bootstrap.CrateSession'):
    value=manifest();require(module in OWNERS,'known read-reuse owner');o=OWNERS[module]
    raw=(HERE/o['file']).read_bytes();require(sha(raw)==o['delta_sha256'],'fixed read-reuse owner delta')
    delta=json.loads(raw)
    expected={'format':'source-context-read-reuse-owner-v1','module':module,'path':o['path'],'parent_ref':value['parent_ref'],'old_sha256':o['old'],'new_sha256':o['new']}
    require(isinstance(delta,dict) and set(delta)==set(expected)|{'edits'} and all(delta[k]==v for k,v in expected.items()),'exact read-reuse transition')
    require(isinstance(delta['edits'],list) and len(delta['edits'])==o['edit_count'],'exact read-reuse edits')
    for e in delta['edits']:
        require(isinstance(e,dict) and set(e)=={'old','new'} and all(isinstance(e[k],str) and e[k] for k in ('old','new')) and e['old']!=e['new'],'exact nonempty replacement')
    return delta
def restore_previous_owner(raw,module='Bootstrap.CrateSession'):
    delta=owner_delta(module);require(sha(raw)==delta['new_sha256'],'complete current read-reuse owner')
    old=raw
    for e in reversed(delta['edits']):
        before,after=e['old'].encode(),e['new'].encode();require(old.count(after)==1,'unique read-reuse inverse block');old=old.replace(after,before)
    require(sha(old)==delta['old_sha256'],'complete prior owner')
    forward=old
    for e in delta['edits']:
        before,after=e['old'].encode(),e['new'].encode();require(forward.count(before)==1,'unique read-reuse forward block');forward=forward.replace(before,after)
    require(forward==raw,'exact full read-reuse round trip');return old
def require_registry(value,kind):
    spec=manifest();require(isinstance(value,dict) and len(value)==128 and all(isinstance(k,str) and isinstance(v,str) for k,v in value.items()) and registry_sha(value)==spec[kind+'_registry_sha256'],'exact complete '+kind+' registry')
def registry_to_parent(value):
    require_registry(value,'current');old=dict(value)
    for n,o in OWNERS.items():require(old[n]==o['new'],'current owner');old[n]=o['old']
    require_registry(old,'parent');return old
def advance_registry(value):
    require_registry(value,'parent');new=dict(value)
    for n,o in OWNERS.items():require(new[n]==o['old'],'prior owner');new[n]=o['new']
    require_registry(new,'current');require(registry_to_parent(new)==value,'complete registry round trip');return new
