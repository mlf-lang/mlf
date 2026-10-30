"""Exact one-owner source admission; no behavioral expectations are generated."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / 'source-contract.json'
MANIFEST_SHA = 'ec83da63b4021b65a882c0edd9bd5b7f39d4fcb14f47af61655389d1caeea6c5'
OLD_OWNER_SHA = '8900a34bf977eaec0d44948be816ca2b5ddb8955170908e7df8fa93967d179df'
NEW_OWNER_SHA = 'e6ffa2603d73f4df1bc69858487168dd53991a8a6243cb046cb1f00e8fbadc13'
CONSTRAINT_SHA = 'ec4520331a84a51a8e702fe027a7bd59d88d6219c7495779d96eec9acf9e3852'
OWNER = 'libraries/mlf-crates/Bootstrap/CrateSession.hs'
CONSTRAINT = 'libraries/mlf-inference/Bootstrap/Constraint.hs'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def manifest(raw=None):
    raw = MANIFEST.read_bytes() if raw is None else raw
    require(sha(raw) == MANIFEST_SHA, 'fixed validation-reuse source contract')
    value = json.loads(raw)
    require(value['old_sha256'] == OLD_OWNER_SHA and value['new_sha256'] == NEW_OWNER_SHA
            and value['constraint_sha256'] == CONSTRAINT_SHA and value['owner'] == OWNER
            and len(value['edits']) == 3, 'exact private-owner source transition')
    return value


def restore_previous_owner(raw):
    require(sha(raw) == NEW_OWNER_SHA, 'exact current validation-reuse owner')
    recovered = raw
    for edit in reversed(manifest()['edits']):
        before, after = edit['old'].encode(), edit['new'].encode()
        require(recovered.count(after) == 1, 'one inverse source edit')
        recovered = recovered.replace(after, before)
    require(sha(recovered) == OLD_OWNER_SHA, 'complete pre-change owner recovered')
    return recovered


def source_hashes(base):
    manifest()
    require(len(base) == 126 and base['Bootstrap.CrateSession'] == OLD_OWNER_SHA
            and base['Bootstrap.Constraint'] == CONSTRAINT_SHA, 'exact validation-reuse source parent')
    return {**base, 'Bootstrap.CrateSession': NEW_OWNER_SHA}


def candidate_dependencies(expected, source):
    """Add only the owner dependency to C4's unchanged complete source contract."""
    require(expected[OWNER] == OLD_OWNER_SHA and expected[CONSTRAINT] == CONSTRAINT_SHA,
            'exact C4 dependencies before owner extension')
    restore_previous_owner((Path(source) / OWNER).read_bytes())
    return {**expected, OWNER: NEW_OWNER_SHA}
