"""Exact two-parent source diamond; never replaces frozen historical contracts."""
from pathlib import Path
import hashlib, importlib.util, json
HERE=Path(__file__).resolve().parent
MANIFEST_SHA='be4b1897299a20e7f2cc1ae0ad7dc056da48418920141ca7a9329b14271c6112'
EXPECTED={'format': 'source-context-projection-diamond-v1', 'common_ref': '5172c4ade3b3141da2e64593c383892575b36699', 'left_ref': '2c3ce0ee4d13cf8d2da19e745189cb85005d3cad', 'right_ref': '9dfcd6625775819568eaaa5065f8dd1431df52f8', 'left_parent_manifest_sha256': '9ecbc912e288495a1ff7f5652e81b429c5cfafd2dcd2da951c395efdc762a95a', 'right_parent_manifest_sha256': '8a7118c56442506571541c5c20821086e8ce9aff987de058097a81e224e29bb0', 'module_count': 128, 'left_unchanged_sources': 127, 'right_unchanged_sources': 126, 'added_sources': {}, 'removed_sources': {}, 'host_sources': {}, 'session_edges': {'left': {'file': 'left-session-delta.json', 'sha256': '73fb0aae3ec2efe06c4c8654e869f77efd07cf96460663b96ee12092de3fb076', 'old_sha256': '5c888e550760f023278beaeffb137a5e3940980b19be2850186ce35ff117805b', 'new_sha256': 'b35637aab8fb473646af9719fe857f1fdb1cda822feedf05e06739e95f4a73a4', 'edit_count': 1}, 'right': {'file': 'right-session-delta.json', 'sha256': 'c7d673c951ea8ddc9e64f091bfec6c539d6088739f6da9611bdf51bb10bd5396', 'old_sha256': '1210cfc8605bb8e45fd6801661175f892ebeddef561afa097b3fa3eafdde3c37', 'new_sha256': 'b35637aab8fb473646af9719fe857f1fdb1cda822feedf05e06739e95f4a73a4', 'edit_count': 3}}, 'query': {'path': 'libraries/mlf-crates/Bootstrap/CrateQuery.hs', 'common_sha256': '06263b9871c593c9f4f7a4f51975b8a38c9f96737f84a632afe5aa7525e50576', 'left_sha256': '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68', 'right_sha256': '06263b9871c593c9f4f7a4f51975b8a38c9f96737f84a632afe5aa7525e50576', 'merged_sha256': '43af002afc2ddb1d69efef0a2d5c1c75dc3dd0b33c85685d4e83fd3290101a68'}, 'common_session_sha256': '51aeddfb084faf84019db88c634d972f48eeecd597d8070c60f59c7402454df9', 'registries': {'common': 'f3cdd7d5328f2060ea9afcdd649c96ba90ff0d60aad38da4d5dfa8827ceb582b', 'left': 'feac2529b2d5da25dff158a0d8043c4dbbdbf26dbc201e4af7d318d78903abee', 'right': '3843ccebb5581db27d6ec385a7e8f403e07acb9856712e7db9aa5a1106af0538', 'merged': '8d259a293e60df946362123fd631156fdedbad1e1c956d67235b87960af6c9fa'}, 'frozen_references': {'source-query-context/source_contract.py': '8cacdec2b8f398d357fd01555e5095eeb2f56376beebffcd9f57980a504cec29', 'source-query-context/source-migration.json': '5dbb5cbc5fcb047732e1ef48931c88a3dbd73030af4cc853f6a07ed951208a6e', 'source-query-context/session-delta.json': '6442aa9316137001e8c71cc54c2257f5c3bee388b7dee1f957b52edae99abc5a', 'source-query-context/query-delta.json': 'd35a696a0dbe00def5c8bf579e88ae4b515b1c2f40f2318408c3dcf8548bc864', 'query-key-scratch/source_contract.py': 'a445a69b7c5a8eaae9cfeb794192ea5bfd7201e5a1bc96fb1dd231933f8281ba', 'query-key-scratch/source-migration.json': '9ecbc912e288495a1ff7f5652e81b429c5cfafd2dcd2da951c395efdc762a95a', 'query-key-scratch/session-delta.json': '5534f3bfc032fbc51aa71eee39992f67760bb337a6690f9490bea08a5b364e06', 'query-key-scratch/query-delta.json': '0c04d92f7da1eea83192e14fa870de681c4fac962bf79badb80c38ab6f20c411', 'full-compiler/source_contract.py': '68eec55dbeb8eec2a1d983dac1f5f61f03e1c03057c0cf9689c6361e8141a027', 'full-compiler/source-migration.json': '8a7118c56442506571541c5c20821086e8ce9aff987de058097a81e224e29bb0', 'full-compiler/session-delta.json': '6aeb0fac2965143ec648c30ce2d540060480af1a422b146654d5c9377e605c5d'}}

def require(ok,message):
    if not ok: raise ValueError(message)
def sha(raw): return hashlib.sha256(raw).hexdigest()
def registry_sha(value):
    return sha(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
def manifest():
    raw=(HERE/'source-migration.json').read_bytes()
    require(sha(raw)==MANIFEST_SHA,'fixed reviewed diamond manifest')
    value=json.loads(raw)
    require(value==EXPECTED,'exact diamond metadata, parents, scope and hashes')
    for path,digest in value['frozen_references'].items():
        require(sha((HERE.parent/path).read_bytes())==digest,'unchanged frozen parent: '+path)
    return value

def contract(name):
    manifest()
    path=HERE.parent/name/'source_contract.py'
    spec=importlib.util.spec_from_file_location('diamond_'+name.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    require(module.HERE==path.parent,'real frozen contract root')
    return module

def edge_manifest(edge):
    value=manifest();require(edge in ('left','right'),'known diamond edge')
    pin=value['session_edges'][edge];raw=(HERE/pin['file']).read_bytes()
    require(sha(raw)==pin['sha256'],'fixed complete diamond source delta')
    delta=json.loads(raw)
    expected={'format':'source-context-projection-merge-edge-v1','edge':edge,
        'path':'libraries/mlf-crates/Bootstrap/CrateSession.hs',
        'old_sha256':pin['old_sha256'],'new_sha256':pin['new_sha256']}
    require(isinstance(delta,dict) and set(delta)==set(expected)|{'edits'}
        and all(delta[k]==v for k,v in expected.items()),'exact edge identity')
    require(isinstance(delta['edits'],list) and len(delta['edits'])==pin['edit_count'],'fixed edge edit count')
    for edit in delta['edits']:
        require(isinstance(edit,dict) and set(edit)=={'old','new'} and
            all(isinstance(edit[k],str) and edit[k] for k in ('old','new')) and
            edit['old']!=edit['new'],'nonempty exact edge blocks')
    return delta

def to_parent(raw,edge):
    delta=edge_manifest(edge)
    require(sha(raw)==delta['new_sha256'],'complete combined owner required')
    restored=raw
    for edit in reversed(delta['edits']):
        before,after=edit['old'].encode(),edit['new'].encode()
        require(restored.count(after)==1,'one inverse diamond block')
        restored=restored.replace(after,before)
    require(sha(restored)==delta['old_sha256'],'complete diamond parent recovered')
    forward=restored
    for edit in delta['edits']:
        before,after=edit['old'].encode(),edit['new'].encode()
        require(forward.count(before)==1,'one forward diamond block')
        forward=forward.replace(before,after)
    require(forward==raw,'full diamond edge round trip')
    return restored

def to_left(raw): return to_parent(raw,'left')
def to_right(raw): return to_parent(raw,'right')

def verify_diamond(raw):
    value=manifest();left=to_left(raw);right=to_right(raw)
    a=contract('query-key-scratch').restore_previous_owner(left)
    a=contract('source-query-context').restore_previous_owner(a)
    b=contract('full-compiler').restore_previous_owner(right)
    require(a==b and sha(a)==value['common_session_sha256'],'both exact inverse paths share common full owner')
    return a

def storage_current_owner(raw,module='Bootstrap.CrateSession'):
    value=manifest()
    if module=='Bootstrap.CrateSession': return to_left(raw)
    require(module=='Bootstrap.CrateQuery' and sha(raw)==value['query']['merged_sha256'],'complete current query owner')
    return raw

def query_to_right(raw):
    value=manifest();require(sha(raw)==value['query']['merged_sha256'],'complete current query')
    old=contract('query-key-scratch').restore_previous_owner(raw,'Bootstrap.CrateQuery')
    old=contract('source-query-context').restore_previous_owner(old,'Bootstrap.CrateQuery')
    require(sha(old)==value['query']['right_sha256'],'complete incoming query recovered')
    return old

def storage_history(raw):
    value=manifest();h=sha(raw)
    if h==value['session_edges']['left']['new_sha256']: return to_left(raw)
    if h==value['session_edges']['right']['old_sha256']:
        return contract('full-compiler').restore_previous_owner(raw)
    # Only complete previously admitted owners, never token-based acceptance.
    known=(value['session_edges']['left']['old_sha256'],
        'a5cd0cb1b939c81785c2c8b7fa2499fd63c24cd6730b8a2e3d74ce9559edabbf',
        value['common_session_sha256'],
        '157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094',
        '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f')
    require(h in known,'known full storage-history owner');return raw

def upstream_history(raw):
    value=manifest();h=sha(raw)
    if h==value['session_edges']['right']['new_sha256']: return to_right(raw)
    known=(value['session_edges']['right']['old_sha256'],value['common_session_sha256'],
        '157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094',
        '18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f')
    require(h in known,'known full upstream-history owner');return raw

def require_registry(value,kind):
    spec=manifest();require(isinstance(value,dict) and len(value)==128 and
        all(isinstance(k,str) and isinstance(v,str) for k,v in value.items()) and
        registry_sha(value)==spec['registries'][kind],'exact complete '+kind+' registry')

def registry_to_parent(value,edge):
    spec=manifest();require_registry(value,'merged');require(edge in ('left','right'),'known registry parent')
    result=dict(value);result['Bootstrap.CrateSession']=spec['session_edges'][edge]['old_sha256']
    result['Bootstrap.CrateQuery']=spec['query'][edge+'_sha256']
    require_registry(result,edge);return result

def merge_registry(left,right):
    spec=manifest();require_registry(left,'left');require_registry(right,'right')
    require(set(left)==set(right),'same complete source population')
    a=dict(left);a['Bootstrap.CrateSession']=spec['session_edges']['left']['new_sha256']
    b=dict(right);b['Bootstrap.CrateSession']=spec['session_edges']['right']['new_sha256'];b['Bootstrap.CrateQuery']=spec['query']['merged_sha256']
    require(a==b,'both complete registry routes agree');require_registry(a,'merged')
    require({n for n in a if a[n]!=left[n]}=={'Bootstrap.CrateSession'} and
        {n for n in b if b[n]!=right[n]}=={'Bootstrap.CrateSession','Bootstrap.CrateQuery'},'exact branch change scopes')
    return a
