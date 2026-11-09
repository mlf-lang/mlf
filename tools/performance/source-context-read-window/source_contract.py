"""Strict two-owner call-owned read-window inverse above key-parts.

Only complete current Query, Session, lock and 128-entry registry are live
inputs. Remove this layer before key-parts, publication, memo and frozen history.
The parent_ref is the published synthetic base; parent_manifest_sha256 pins the
reviewed local key-parts layer. Old contracts and their golden identities remain
immutable. This source-proof layer adds no production exception/race guarantee.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
MANIFEST_SHA = '194d1bc6ec983943c067f943feb3b88508df9df8d19cc0d20c39c9666389214b'
OWNER = 'Bootstrap.CrateQuery'
EXPECTED = {'added_sources': {},
 'changed_sources': {'Bootstrap.CrateQuery': {'new': '3b3b7a5de8b1f83b0a369e9a47ead5666d1169490e5466e2d8a9983b20eeb8b9',
                                              'old': 'f1b55c953d2631458af0ab6e736f7c13fd0303bc1b6be8025c90eb0c4f5215f0',
                                              'reviewed_change': 'bounded call-owned eight-context '
                                                                 'window and empty-window '
                                                                 'lifecycle at the existing '
                                                                 'source-group driver'},
                     'Bootstrap.CrateSession': {'new': 'e3002483e06d189b31e3d93e876618c0a65fc807be654f6757452f087088e2a1',
                                                'old': '8adefc9d5346f375dd8568a59400bd498695af270b6fc70bea296c0698b5d190',
                                                'reviewed_change': 'bounded call-owned '
                                                                   'eight-context window and '
                                                                   'empty-window lifecycle at the '
                                                                   'existing source-group driver'}},
 'current_lock_sha256': '123f426bda8ed1ede2bebce0b1c74e3c37e995f3ba0ace7c091c6d4f41a5379a',
 'current_registry_sha256': '269cf6dbecd72de027ddef781ba8b48d00af8d61f91998ccdb7f823795cbb3bd',
 'format': 'source-context-read-window-migration-v1',
 'frozen_references': {'full-compiler/session-delta.json': '6aeb0fac2965143ec648c30ce2d540060480af1a422b146654d5c9377e605c5d',
                       'full-compiler/source-migration.json': '8a7118c56442506571541c5c20821086e8ce9aff987de058097a81e224e29bb0',
                       'full-compiler/source_contract.py': '68eec55dbeb8eec2a1d983dac1f5f61f03e1c03057c0cf9689c6361e8141a027',
                       'llvm-memory/host-delta.json': '3139c588c098659f16b17e88d20f584af54810c26ecda63aad7c042592feec29',
                       'llvm-memory/source_contract.py': 'dafccd15ca69dbce1540b7963403410b9c60e3f83c51659e13b7254c3de7f539',
                       'query-key-scratch/query-delta.json': '0c04d92f7da1eea83192e14fa870de681c4fac962bf79badb80c38ab6f20c411',
                       'query-key-scratch/session-delta.json': '5534f3bfc032fbc51aa71eee39992f67760bb337a6690f9490bea08a5b364e06',
                       'query-key-scratch/source-migration.json': '9ecbc912e288495a1ff7f5652e81b429c5cfafd2dcd2da951c395efdc762a95a',
                       'query-key-scratch/source_contract.py': 'a445a69b7c5a8eaae9cfeb794192ea5bfd7201e5a1bc96fb1dd231933f8281ba',
                       'source-context-key-parts/query-delta.json': 'f12e5cdeaafee31475441bdf5a53d45265a2a273f113780e43339fbc9e1d4568',
                       'source-context-key-parts/source-migration.json': '409ca0938d1b0a4949f6b7de0a44292b2defe8e6beab90bed8f644f5a4fe7392',
                       'source-context-key-parts/source_contract.py': '56c1dea54ff991889ea3829f21d89e2050f11f57f4f64ece610378c77cdc423d',
                       'source-context-projection-merge/left-session-delta.json': '73fb0aae3ec2efe06c4c8654e869f77efd07cf96460663b96ee12092de3fb076',
                       'source-context-projection-merge/right-session-delta.json': 'c7d673c951ea8ddc9e64f091bfec6c539d6088739f6da9611bdf51bb10bd5396',
                       'source-context-projection-merge/source-migration.json': 'be4b1897299a20e7f2cc1ae0ad7dc056da48418920141ca7a9329b14271c6112',
                       'source-context-projection-merge/source_contract.py': '352ae609b851fc57586ccaea7cd77a95a6bb5c85d29ae0b8c7d684962ec1ee2d',
                       'source-context-publication/query-delta.json': '53720f0a1ff588d1eb71356350657dd4fdda5a5ba6c97d06c35f54aebc4b2174',
                       'source-context-publication/source-migration.json': 'b5d62c0a13a2306413167e318687573a790585a85d418203747bfd5956b62ca6',
                       'source-context-publication/source_contract.py': 'b2abf018b5c3b5017d704a2adcb0f6f05c0501038b8edd9e421bb0f49c252c0c',
                       'source-context-read-reuse/query-delta.json': '022636870b0dd0da2abdfcca3764efb4fb947dc17402b88025434742588f7ee0',
                       'source-context-read-reuse/session-delta.json': '624818cd1064a142066198aed31f49c8ed3c22f9143042fe33b27c7900b3544f',
                       'source-context-read-reuse/source-migration.json': 'f53f560ee5f2014ecd7db26c555040a8bf531fa4d6c77bd36d32934d67172c1c',
                       'source-context-read-reuse/source_contract.py': '186714be67b6866b711a38f53d532b4cc68641e91b2103a7aa5ce60234f5a890',
                       'source-query-context/query-delta.json': 'd35a696a0dbe00def5c8bf579e88ae4b515b1c2f40f2318408c3dcf8548bc864',
                       'source-query-context/session-delta.json': '6442aa9316137001e8c71cc54c2257f5c3bee388b7dee1f957b52edae99abc5a',
                       'source-query-context/source-migration.json': '5dbb5cbc5fcb047732e1ef48931c88a3dbd73030af4cc853f6a07ed951208a6e',
                       'source-query-context/source_contract.py': '8cacdec2b8f398d357fd01555e5095eeb2f56376beebffcd9f57980a504cec29'},
 'host_sources': {},
 'module_count': 128,
 'owners': {'Bootstrap.CrateQuery': {'delta_sha256': '6754fceb1b7c99f6823a6f8361d1c1872a2e69b0e3e1ab8f9395565cd99894e3',
                                     'edit_count': 5,
                                     'file': 'query-delta.json',
                                     'new': '3b3b7a5de8b1f83b0a369e9a47ead5666d1169490e5466e2d8a9983b20eeb8b9',
                                     'old': 'f1b55c953d2631458af0ab6e736f7c13fd0303bc1b6be8025c90eb0c4f5215f0',
                                     'path': 'libraries/mlf-crates/Bootstrap/CrateQuery.hs'},
            'Bootstrap.CrateSession': {'delta_sha256': '49cfbc634c790d453c08eaaed04a431c3454a72322046afaa59dc450a8db2c81',
                                       'edit_count': 3,
                                       'file': 'session-delta.json',
                                       'new': 'e3002483e06d189b31e3d93e876618c0a65fc807be654f6757452f087088e2a1',
                                       'old': '8adefc9d5346f375dd8568a59400bd498695af270b6fc70bea296c0698b5d190',
                                       'path': 'libraries/mlf-crates/Bootstrap/CrateSession.hs'}},
 'parent_lock_sha256': '0c7ef4f26547c1b9c0eb49dc814ac417a4317a1cd803dacd90d9499e626631f4',
 'parent_manifest_sha256': '409ca0938d1b0a4949f6b7de0a44292b2defe8e6beab90bed8f644f5a4fe7392',
 'parent_ref': '97fe3dc80237bbd4d58594b043f189c5ba633209',
 'parent_registry_sha256': '7eae16f2e1df8be084b411e676e524f75d61626687e8fafd9b98acf6b26b70e2',
 'removed_sources': {},
 'unchanged_count': 126,
 'unchanged_owners': {}}
OWNERS = EXPECTED['owners']

def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def registry_sha(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def manifest():
    raw = (HERE / 'source-migration.json').read_bytes()
    require(sha(raw) == MANIFEST_SHA, 'fixed read-window manifest')
    value = json.loads(raw)
    require(value == EXPECTED, 'exact two-owner read-window scope and identities')
    for path, digest in value['frozen_references'].items():
        require(sha((HERE.parent / path).read_bytes()) == digest,
                'unchanged frozen predecessor ' + path)
    return value


def owner_delta(module=OWNER):
    spec = manifest()
    require(module in spec['owners'], 'known changed read-window owner')
    owner = spec['owners'][module]
    raw = (HERE / owner['file']).read_bytes()
    require(sha(raw) == owner['delta_sha256'], 'fixed read-window owner delta')
    delta = json.loads(raw)
    expected = {'format': 'source-context-read-window-owner-v1', 'module': module,
                'path': owner['path'], 'parent_ref': spec['parent_ref'],
                'old_sha256': owner['old'], 'new_sha256': owner['new']}
    require(isinstance(delta, dict) and set(delta) == set(expected) | {'edits'}
            and all(delta[key] == value for key, value in expected.items()),
            'exact read-window owner transition')
    require(isinstance(delta['edits'], list)
            and len(delta['edits']) == owner['edit_count'], 'exact read-window edit count')
    for edit in delta['edits']:
        require(isinstance(edit, dict) and set(edit) == {'old', 'new'}
                and all(isinstance(edit[key], str) and edit[key] for key in ('old', 'new'))
                and edit['old'] != edit['new'], 'exact nonempty read-window replacement')
    return delta


def restore_previous_owner(raw, module=OWNER):
    delta = owner_delta(module)
    require(sha(raw) == delta['new_sha256'], 'complete current read-window owner')
    previous = raw
    for edit in reversed(delta['edits']):
        before, after = edit['old'].encode(), edit['new'].encode()
        require(previous.count(after) == 1, 'unique read-window inverse block')
        previous = previous.replace(after, before)
    require(sha(previous) == delta['old_sha256'], 'complete prior read-window owner')
    forward = previous
    for edit in delta['edits']:
        before, after = edit['old'].encode(), edit['new'].encode()
        require(forward.count(before) == 1, 'unique read-window forward block')
        forward = forward.replace(before, after)
    require(forward == raw, 'exact full read-window owner round trip')
    return previous


def project_owner(raw, module):
    # Live-entry projection only. Historical replay remains in the existing
    # key-parts/publication/memo/diamond adapters, never token fallbacks.
    spec = manifest()
    if module in spec['owners']:
        return restore_previous_owner(raw, module)
    unchanged = spec['unchanged_owners']
    require(module in unchanged and sha(raw) == unchanged[module]['sha256'],
            'exact unchanged read-window owner')
    return raw


def require_registry(value, kind):
    spec = manifest()
    require(kind in ('parent', 'current'), 'known read-window registry side')
    require(isinstance(value, dict) and len(value) == spec['module_count']
            and all(isinstance(k, str) and isinstance(v, str) for k, v in value.items())
            and registry_sha(value) == spec[kind + '_registry_sha256'],
            'exact complete ' + kind + ' read-window registry')


def registry_to_parent(value):
    require_registry(value, 'current')
    previous = dict(value)
    for name, owner in EXPECTED['owners'].items():
        require(previous[name] == owner['new'], 'current read-window registry owner')
        previous[name] = owner['old']
    require_registry(previous, 'parent')
    return previous


def advance_registry(value):
    require_registry(value, 'parent')
    current = dict(value)
    for name, owner in EXPECTED['owners'].items():
        require(current[name] == owner['old'], 'prior read-window registry owner')
        current[name] = owner['new']
    require_registry(current, 'current')
    require(registry_to_parent(current) == value, 'complete read-window registry round trip')
    return current


def restore_previous_lock(raw):
    spec = manifest()
    require(sha(raw) == spec['current_lock_sha256'], 'complete current read-window lock')
    previous = raw
    for module, owner in spec['owners'].items():
        before, after = owner['old'].encode(), owner['new'].encode()
        require(previous.count(after) == 1, 'one current read-window lock owner ' + module)
        previous = previous.replace(after, before)
    require(sha(previous) == spec['parent_lock_sha256'], 'complete prior read-window lock')
    forward = previous
    for module, owner in spec['owners'].items():
        before, after = owner['old'].encode(), owner['new'].encode()
        require(forward.count(before) == 1, 'one prior read-window lock owner ' + module)
        forward = forward.replace(before, after)
    require(forward == raw, 'exact full two-owner read-window lock round trip')
    return previous


def advance_lock(raw):
    spec = manifest()
    require(sha(raw) == spec['parent_lock_sha256'], 'complete prior read-window lock')
    current = raw
    for module, owner in spec['owners'].items():
        before, after = owner['old'].encode(), owner['new'].encode()
        require(current.count(before) == 1, 'one prior read-window lock owner ' + module)
        current = current.replace(before, after)
    require(sha(current) == spec['current_lock_sha256'], 'complete current read-window lock')
    require(restore_previous_lock(current) == raw, 'complete two-owner read-window lock forward round trip')
    return current
