"""Exact current-target -> resource Phase A source inventory transition.

This is source custody, not a compiled producer or behavioral acceptance. The
historical A1 and subsequent numeric/Patricia source transitions are unchanged.
Their complete current-target result is required as the input to migrate().
No current source hash is learned or granted admission by this module.
"""
from pathlib import Path
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MANIFEST = HERE / 'resource_source_migration.json'
# Finalize only after the genuine combined-source builtin regeneration and
# Entry identity transition, followed by exact independent source review.
# This finalized digest admits only the exact reviewed transition bytes.
MANIFEST_SHA256 = '9729306434730c32472762bd875e4ba17573b764a5eb86268703c4f8699e86fa'
TARGET_SNAPSHOT_SHA256 = '0747cafe709e4963ff60875dca95bfbf7b176b93b99441d746b593c5b909823b'
TARGET_CANONICAL_SHA256 = 'af3cde7e818d0d249efb05163973d64bccc53fb95625b108e32bfd60d7c78383'
TARGET_COMMIT = 'c5928b5be73cd78d194405e734aa012415570e1a'
TARGET_TREE = '60e441003697e5ad02c8d93189cf9cd68d691c9f'
PLAN_SHA256 = '4a345187d9a8b22e371d9dff3c225d7a71c9244ea05c5911b6de3a539719a75a'
CHANGED = frozenset({'MLF.Entry.Emlf', 'Bootstrap.Module',
                     'Bootstrap.CompilerCore', 'MLF.BuiltinPreludeData'})
ADDITIONS = (
    (1, 'MLF.ResourceModuleExport', 'bootstrap/MLF/ResourceModuleExport.hs'),
    (2, 'MLF.ResourceProjection', 'bootstrap/MLF/ResourceProjection.hs'),
    (3, 'MLF.ResourceModules', 'bootstrap/MLF/ResourceModules.hs'),
    (131, 'MLF.ResourceExport', 'bootstrap/MLF/ResourceExport.hs'),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False).encode('utf-8')


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate migration JSON key: ' + key)
        result[key] = value
    return result


def digest(value):
    return (type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None
            and value != '0' * 64)


def exact_keys(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ' exact keys')


def validate_transition(value):
    """Replay the declared delta; callers must first authenticate raw bytes.

    Direct callers can use this structural replay for negative controls. Only
    parse_transition() grants the immutable manifest's exact digest admission.
    """
    metadata = {
        'format': 'resource-phase-a-current-source-migration-v1',
        'from_commit': TARGET_COMMIT, 'from_tree': TARGET_TREE,
        'target_snapshot_sha256': TARGET_SNAPSHOT_SHA256,
        'integration_plan_sha256': PLAN_SHA256,
        'module_count': 132, 'unchanged_shared_input_count': 124,
        'source_inventory_only': True,
    }
    exact_keys(value, set(metadata) | {'target_snapshot', 'changed_modules',
               'added_modules', 'destination_modules'}, 'transition')
    require(all(type(value[key]) is type(wanted) and value[key] == wanted
                for key, wanted in metadata.items()), 'exact transition metadata')
    target = value['target_snapshot']
    require(sha(canonical(target)) == TARGET_CANONICAL_SHA256,
            'exact independently authenticated current-target snapshot')
    exact_keys(target, {'schema', 'commit', 'tree', 'shared_manifest_sha256',
                       'modules'}, 'target snapshot')
    require(target['schema'] == 'exact-shared-source-inventory/1' and
            target['commit'] == TARGET_COMMIT and target['tree'] == TARGET_TREE,
            'exact current-target identity')
    rows = target['modules']
    require(type(rows) is list and len(rows) == 128, 'exact target128 rows')
    by_name = {row['module']: row for row in rows}
    require(len(by_name) == 128 and len({row['path'] for row in rows}) == 128,
            'distinct target names and source paths')

    changes = value['changed_modules']
    require(type(changes) is list and len(changes) == 4 and
            [row.get('module') if type(row) is dict else None for row in changes]
            == [row['module'] for row in rows if row['module'] in CHANGED],
            'exact four changed owners in target order')
    changed_hashes = {}
    for row in changes:
        exact_keys(row, {'module', 'path', 'role', 'old', 'new'}, 'changed owner')
        before = by_name[row['module']]
        require(all(row[key] == before[key] for key in ('module', 'path', 'role'))
                and row['old'] == before['sha256'], 'exact old owner identity')
        require(digest(row['new']) and row['new'] != row['old'],
                'distinct valid changed owner hash')
        changed_hashes[row['module']] = row['new']

    additions = value['added_modules']
    require(type(additions) is list and len(additions) == len(ADDITIONS),
            'exact four resource additions')
    added_rows = {}
    for row, (index, name, path) in zip(additions, ADDITIONS):
        exact_keys(row, {'index', 'module', 'path', 'role', 'sha256'}, 'added owner')
        require(type(row['index']) is int and row['index'] == index and
                row['module'] == name and row['path'] == path and
                row['role'] == 'implementation' and digest(row['sha256']),
                'exact resource name/path/role/position/hash')
        require(name not in by_name, 'addition must not replace a target owner')
        added_rows[index] = {key: row[key] for key in
                             ('module', 'path', 'role', 'sha256')}

    pending = iter(rows)
    expected = []
    for index in range(132):
        if index in added_rows:
            expected.append(added_rows[index])
        else:
            row = dict(next(pending))
            if row['module'] in changed_hashes:
                row['sha256'] = changed_hashes[row['module']]
            expected.append(row)
    require(next(pending, None) is None, 'every target row retained exactly once')
    require(value['destination_modules'] == expected,
            'complete ordered destination inventory differs from exact delta')
    require(len({row['module'] for row in expected}) == 132 and
            len({row['path'] for row in expected}) == 132,
            'distinct destination source identities')
    unchanged = [row for row in expected
                 if row['module'] in by_name and row['module'] not in CHANGED]
    require(len(unchanged) == 124 and
            all(row == by_name[row['module']] for row in unchanged),
            'all124 unmodified current-target owners retained exactly')
    return expected


def parse_transition(raw):
    require(type(raw) is bytes and digest(MANIFEST_SHA256) and
            sha(raw) == MANIFEST_SHA256, 'fixed reviewed resource transition required')
    value = json.loads(raw.decode('utf-8'), object_pairs_hook=strict_object)
    validate_transition(value)
    return value


def transition():
    return parse_transition(MANIFEST.read_bytes())


def migrate(previous, raw=None):
    """Require the complete old migration chain's exact128-owner endpoint."""
    value = transition() if raw is None else parse_transition(raw)
    base = {row['module']: row['sha256'] for row in value['target_snapshot']['modules']}
    require(type(previous) is dict and previous == base,
            'exact128-module current-target input after historical transitions')
    return {row['module']: row['sha256'] for row in validate_transition(value)}


def authenticate_inventory(rows, source_hashes, raw=None):
    """Compare observed names/paths/roles/order and all132 actual byte hashes."""
    value = transition() if raw is None else parse_transition(raw)
    expected = validate_transition(value)
    require(type(rows) is list and rows == [
        {key: row[key] for key in ('module', 'path', 'role')} for row in expected],
        'exact132 ordered shared-source name/path/role inventory')
    require(type(source_hashes) is dict and source_hashes == {
        row['module']: row['sha256'] for row in expected},
        'exact132 shared source byte identities')
    return source_hashes


def authenticate_current_source(root, previous):
    """Bind live source bytes, not a copied build receipt or counters."""
    root = Path(root).resolve(strict=True)
    manifest = json.loads((root / 'shared-sources.json').read_text(),
                          object_pairs_hook=strict_object)
    rows = manifest['modules']
    # Validate metadata before opening supplied paths, including duplicates,
    # role changes, traversal, and reordered rows.
    wanted = migrate(previous)
    authenticate_inventory(rows, wanted)
    actual = {}
    for row in rows:
        source = root / row['path']
        require(source.is_file() and not source.is_symlink() and
                source.resolve().is_relative_to(root), 'source path escaped root')
        actual[row['module']] = sha(source.read_bytes())
    return authenticate_inventory(rows, actual)
