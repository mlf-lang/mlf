"""Project the reviewed prepared-Prelude changes for retained PR 25 source controls."""
import hashlib
import json
from pathlib import Path

MANIFEST = Path(__file__).with_name('source-migration.json')
MANIFEST_SHA = '4acb3a90757a375a423fda9db6eda022597f350d34090ca8f4712a478fa594f5'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError('crate Prelude source transition: ' + message)


def manifest():
    raw = MANIFEST.read_bytes()
    require(sha(raw) == MANIFEST_SHA, 'manifest SHA')
    return json.loads(raw)


def registry_sha(registry):
    return sha(json.dumps(registry, sort_keys=True, separators=(',', ':')).encode())


def advance_registry(parent):
    data = manifest()
    require(registry_sha(parent) == data['parent_registry'], 'full PR 25 parent registry')
    current = dict(parent)
    for name, row in data['changed_sources'].items():
        require(parent[name] == row['old'], 'parent SHA for ' + name)
        current[name] = row['new']
    require(registry_sha(current) == data['current_registry'], 'complete current registry')
    return current


def restore_session(raw):
    data = manifest()
    row = data['changed_sources']['Bootstrap.CrateSession']
    require(sha(raw) == row['new'], 'complete current session')
    restored = raw
    for edit in reversed(data['session_edits']):
        old, new = edit['old'].encode(), edit['new'].encode()
        require(restored.count(new) == 1, 'unique current session region')
        restored = restored.replace(new, old)
    require(sha(restored) == row['old'], 'complete previous session')
    forward = restored
    for edit in data['session_edits']:
        old, new = edit['old'].encode(), edit['new'].encode()
        require(forward.count(old) == 1, 'unique parent session region')
        forward = forward.replace(old, new)
    require(forward == raw, 'session round trip')
    return restored
