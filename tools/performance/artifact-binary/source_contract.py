"""Strict, parameterized L128 <-> binary131 source migration.

This is source/metadata plumbing, not artifact compatibility or qualification.
The external caller must pin the final manifest SHA after genuine generation.
No fallback recognizes historical, partially migrated, or mixed current inputs.
Importing this file performs no IO and executes no candidate source.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re


PARENT_INVENTORY_SHA = 'f40bef08aa0deac58d6c7fab727bc13fbf1c595b317fc5cd664f25ed5e79d5e6'
MAINTENANCE_PARENTS_SHA = 'fc75a2310b664ea1c65cfdb99129f3e7d1220ba3652e79303cf18262faaff9c3'
PARENT_REGISTRY_SHA = '269cf6dbecd72de027ddef781ba8b48d00af8d61f91998ccdb7f823795cbb3bd'
PARENT_LOCK_SHA = '123f426bda8ed1ede2bebce0b1c74e3c37e995f3ba0ace7c091c6d4f41a5379a'
ADDED_MODULES = {
    'Bootstrap.ArtifactStorage': 'libraries/mlf-crates/Bootstrap/ArtifactStorage.hs',
    'Bootstrap.ArtifactStructure': 'libraries/mlf-crates/Bootstrap/ArtifactStructure.hs',
    'Bootstrap.Bitstream': 'libraries/mlf-crates/Bootstrap/Bitstream.hs',
}
CANONICAL = 'bootstrap/MLF/BuiltinPreludeData.hs'
LITERAL = 'libraries/mlf-crates/Bootstrap/BuiltinPreludeLiteral.hs'
MAX_METADATA_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 32 * 1024 * 1024
MAX_SPLICES = 65536


def require(condition, message):
    if not condition:
        raise ValueError('binary source migration: ' + message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical_sha(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def is_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def strict_json(raw):
    require(type(raw) is bytes and len(raw) <= MAX_METADATA_BYTES, 'metadata byte bound')

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key: ' + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('binary source migration: nonfinite JSON constant: ' + value)

    return json.loads(raw.decode('utf-8'), object_pairs_hook=object_pairs,
                      parse_constant=invalid_constant)


def relative_path(value):
    require(isinstance(value, str) and value and '\\' not in value and '\0' not in value,
            'invalid relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value and
            all(part not in ('.', '..') for part in path.parts), 'noncanonical relative path')
    return value


def read_file(root, name, limit=MAX_SOURCE_BYTES):
    relative_path(name)
    root = Path(root).resolve(strict=True)
    path = root / name
    require(path.resolve(strict=True).is_relative_to(root), 'path escaped root: ' + name)
    require(not any((root / Path(*PurePosixPath(name).parts[:n])).is_symlink()
                    for n in range(1, len(PurePosixPath(name).parts) + 1)),
            'symlink in source path: ' + name)
    require(path.is_file() and path.stat().st_size <= limit, 'regular file / byte bound: ' + name)
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'file grew past byte bound: ' + name)
    return raw


def hash_map(value, label):
    require(type(value) is dict and all(isinstance(k, str) and k and is_sha(v)
                                      for k, v in value.items()), 'invalid hash map: ' + label)


def decode_blob(value):
    require(isinstance(value, str) and len(value) <= 4 * ((MAX_SOURCE_BYTES + 2) // 3),
            'splice base64 bound')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ValueError('binary source migration: invalid splice base64') from error
    require(len(raw) <= MAX_SOURCE_BYTES and base64.b64encode(raw).decode() == value,
            'noncanonical splice base64')
    return raw


def apply_splices(raw, delta, reverse=False):
    """Positioned byte splices; complete input/output hashes remove ambiguity.

    Positions are in their respective ORIGINAL old/new snapshots. Each gap has
    the same length on both sides. Insertions/deletions are allowed, an empty
    no-op is not. No fuzzy text matching or UTF8 normalization occurs.
    """
    require(type(raw) is bytes and len(raw) <= MAX_SOURCE_BYTES, 'source byte bound')
    require(type(delta) is dict and set(delta) == {
        'format', 'path', 'old_sha256', 'new_sha256', 'old_bytes', 'new_bytes', 'splices'
    } and delta['format'] == 'binary-source-byte-splices-v1', 'delta schema')
    relative_path(delta['path'])
    for key in ('old_sha256', 'new_sha256'):
        require(is_sha(delta[key]), 'delta digest')
    require(delta['old_sha256'] != delta['new_sha256'], 'unchanged delta')
    for key in ('old_bytes', 'new_bytes'):
        require(type(delta[key]) is int and 0 <= delta[key] <= MAX_SOURCE_BYTES,
                'delta size')
    rows = delta['splices']
    require(type(rows) is list and 0 < len(rows) <= MAX_SPLICES, 'splice count')
    source, target = ('new', 'old') if reverse else ('old', 'new')
    require(len(raw) == delta[source + '_bytes'] and sha(raw) == delta[source + '_sha256'],
            'complete ' + source + ' source SHA mismatch: ' + delta['path'])
    old_end = new_end = source_end = 0
    output = []
    output_bytes = 0
    for row in rows:
        require(type(row) is dict and set(row) == {'old_at', 'new_at', 'old', 'new'},
                'splice row schema')
        old, new = decode_blob(row['old']), decode_blob(row['new'])
        old_at, new_at = row['old_at'], row['new_at']
        require(type(old_at) is int and type(new_at) is int and
                old_end <= old_at <= delta['old_bytes'] - len(old) and
                new_end <= new_at <= delta['new_bytes'] - len(new), 'overlapping / out of bounds splice')
        require(old_at - old_end == new_at - new_end and old != new,
                'noncanonical splice gap / no-op')
        at, before, after = (new_at, new, old) if reverse else (old_at, old, new)
        require(raw[at:at + len(before)] == before, 'exact splice bytes mismatch')
        gap = raw[source_end:at]
        output_bytes += len(gap) + len(after)
        require(output_bytes <= MAX_SOURCE_BYTES, 'splice output bound')
        output.extend((gap, after))
        source_end = at + len(before)
        old_end, new_end = old_at + len(old), new_at + len(new)
    require(delta['old_bytes'] - old_end == delta['new_bytes'] - new_end,
            'unequal trailing splice gaps')
    require(output_bytes + len(raw) - source_end <= MAX_SOURCE_BYTES, 'final splice output bound')
    output.append(raw[source_end:])
    result = b''.join(output)
    require(len(result) == delta[target + '_bytes'] and sha(result) == delta[target + '_sha256'],
            'complete ' + target + ' source SHA mismatch: ' + delta['path'])
    return result


def module_paths(manifest):
    require(type(manifest) is dict and type(manifest.get('modules')) is list,
            'shared manifest schema')
    result = {}
    paths = set()
    for row in manifest['modules']:
        require(type(row) is dict and set(row) == {'module', 'path', 'role'} and
                isinstance(row['module'], str) and row['module'] and
                row['module'] not in result and row['path'] not in paths,
                'duplicate / malformed shared module')
        relative_path(row['path'])
        result[row['module']] = row['path']
        paths.add(row['path'])
    return result


def validate_shared_transition(old_raw, new_raw):
    old, new = strict_json(old_raw), strict_json(new_raw)
    expected = dict(old)
    expected['modules'] = sorted(old['modules'] + [
        {'module': name, 'path': path, 'role': 'implementation'}
        for name, path in ADDED_MODULES.items()], key=lambda row: row['module'])
    expected['primitive_abi'] = 'mlf-primitive-132-v7'
    expected['builtin_interface'] = 'mlf-primitive/shared-haskell-v1/11'
    require(new == expected and len(module_paths(old)) == 128 and
            len(module_paths(new)) == 131, 'shared manifest changed beyond exact binary transition')


def lock_path(package_path, name):
    require(package_path == '.' or relative_path(package_path), 'lock package path')
    relative_path(name)
    return name if package_path == '.' else package_path + '/' + name


def validate_lock_transition(old_raw, new_raw, old_files, new_files):
    """Only changed registered source hashes, new three entries, manifest hashes.

    Preserve old package order, identity, versions, and unrelated / nonshared
    source entries exactly. Some old lock entries are outside the L source
    closure; they remain byte-valued JSON identities, never invented files.
    """
    old, new = strict_json(old_raw), strict_json(new_raw)
    require(type(old) is dict and set(old) == {'format', 'packages'} and old['format'] == 1 and
            type(old['packages']) is list, 'parent lock schema')
    expected = json.loads(json.dumps(old))
    packages = set()
    inserted = set()
    changed_shared_paths = {p for p in old_files if p.endswith('.hs') and
                            p in new_files and old_files[p] != new_files[p] and
                            not p.startswith('host/')}
    seen_changed = set()
    for row in expected['packages']:
        require(type(row) is dict and set(row) == {'manifest', 'name', 'path', 'sources', 'version'} and
                isinstance(row['name'], str) and row['name'] not in packages,
                'duplicate / malformed lock package')
        packages.add(row['name'])
        hash_map(row['sources'], 'lock sources')
        manifest_path = lock_path(row['path'], 'mlf-package.json')
        require(manifest_path in old_files and manifest_path in new_files and
                row['manifest'] == old_files[manifest_path], 'parent package manifest hash')
        row['manifest'] = new_files[manifest_path]
        for name in list(row['sources']):
            path = lock_path(row['path'], name)
            if path in changed_shared_paths:
                require(row['sources'][name] == old_files[path], 'parent lock source mismatch: ' + path)
                row['sources'][name] = new_files[path]
                seen_changed.add(path)
        if row['path'] == 'libraries/mlf-crates':
            for path in ADDED_MODULES.values():
                name = path[len(row['path']) + 1:]
                require(name not in row['sources'], 'new module already in parent lock')
                row['sources'][name] = new_files[path]
                inserted.add(path)
    require(inserted == set(ADDED_MODULES.values()), 'missing exact added lock sources')
    require(seen_changed == changed_shared_paths,
            'changed source not represented by old lock: ' + repr(sorted(changed_shared_paths - seen_changed)))
    require(new == expected, 'lock changed outside exact source / manifest bridge')


class Contract:
    """Load a finalized contract using an independently supplied full SHA.

    Merely finding a local manifest or SHA sidecar never authorizes it. Parent
    historical source bytes are verified, not imported. Current SHA identities
    intentionally do not exist in this authoring revision.
    """

    def __init__(self, directory, manifest_sha256, history_root, source_root=None):
        require(is_sha(manifest_sha256), 'explicit final manifest SHA required')
        self.manifest_sha256 = manifest_sha256
        self.directory = Path(directory).resolve(strict=True)
        parent_raw = read_file(self.directory, 'parent-inventory.json', MAX_METADATA_BYTES)
        require(sha(parent_raw) == PARENT_INVENTORY_SHA, 'fixed parent inventory SHA')
        self.parent = strict_json(parent_raw)
        maintenance_raw = read_file(self.directory, 'maintenance-parents.json', MAX_METADATA_BYTES)
        require(sha(maintenance_raw) == MAINTENANCE_PARENTS_SHA, 'fixed maintenance parent inventory SHA')
        self.maintenance_parent = strict_json(maintenance_raw)
        raw = read_file(self.directory, 'source-migration.json', MAX_METADATA_BYTES)
        require(sha(raw) == manifest_sha256, 'fixed final manifest SHA')
        self.value = strict_json(raw)
        self._validate_manifest()
        mutable = set(self.maintenance_parent['mutable_frozen_history'])
        require(mutable == {'patricia/source_migration.py', 'patricia/test_adapters.py'},
                'exact two mutable historical maintenance entries')
        for name, digest in self.parent['frozen_history'].items():
            if name in mutable:
                old = self.restore_maintenance(read_file(history_root, name), name)
                require(sha(old) == digest, 'mutable history exact old full SHA: ' + name)
            else:
                require(sha(read_file(history_root, name)) == digest, 'frozen historical file: ' + name)
        for name in self.maintenance_parent['files']:
            if name not in mutable:
                self.restore_maintenance(read_file(history_root, name), name)
        receipt = read_file(self.directory, 'builtin-verification-receipt.json', MAX_METADATA_BYTES)
        require(sha(receipt) == self.value['generation']['receipt_sha256'], 'generator evidence SHA')
        evidence = strict_json(receipt)
        self._validate_generation(evidence)
        require(isinstance(evidence.get('source_root'), str) and Path(evidence['source_root']).is_absolute(),
                'historical verification source-root fact')
        # Evidence describes the checkout that generated the frozen receipt.
        # Never rebase that fact, resolve it, or use it as a live filesystem root.
        self.evidence_source_root = Path(evidence['source_root'])
        history = Path(history_root).resolve(strict=True)
        if source_root is None:
            require(history.name == 'performance' and history.parent.name == 'tools',
                    'default live root requires actual <checkout>/tools/performance')
            live = history.parent.parent
        else:
            require(Path(source_root).is_absolute(), 'explicit actual live root must be absolute')
            live = Path(source_root).resolve(strict=True)
        require(live.is_dir(), 'actual live checkout directory required')
        self.source_root = live
        # The root transport is not a new authority: authenticate every tracked
        # current byte, including generated data, lock, host IO, and runtime.
        # Extra repository files outside this exact tracked inventory are fine.
        self.live_source_inventory(self.source_root)

    def _validate_manifest(self):
        value, parent = self.value, self.parent
        require(type(value) is dict and set(value) == {
            'format', 'parent_inventory_sha256', 'module_paths', 'parent_registry_sha256',
            'current_registry', 'current_registry_sha256', 'current_files',
            'current_inventory_sha256', 'changed_paths', 'added_paths', 'deltas',
            'module_count', 'primitive_count', 'generation', 'maintenance'
        }, 'manifest fields')
        require(value['format'] == 'binary-source-migration-v1' and
                value['parent_inventory_sha256'] == PARENT_INVENTORY_SHA and
                value['parent_registry_sha256'] == PARENT_REGISTRY_SHA and
                value['module_count'] == 131 and value['primitive_count'] == 132,
                'manifest identity / counts')
        require(value['module_paths'] == {**parent['module_paths'], **ADDED_MODULES},
                'exact added three modules')
        hash_map(value['current_registry'], 'current registry')
        hash_map(value['current_files'], 'current files')
        require(set(value['current_registry']) == set(value['module_paths']) and
                canonical_sha(value['current_registry']) == value['current_registry_sha256'],
                'complete current registry identity')
        files = value['current_files']
        require(set(files) == set(parent['files']) | set(parent['expected_added_paths']) and
                canonical_sha(files) == value['current_inventory_sha256'], 'complete current file inventory')
        require(all(files[path] == value['current_registry'][name]
                    for name, path in value['module_paths'].items()), 'registry / file hash mismatch')
        # The crate CLI supplies its checked Prelude. Datatype admission shares
        # builtin tables, and inferred exports use the checked binding inventory.
        changed_paths = sorted([*parent['expected_changed_paths'], 'bootstrap/MLF/Entry/Emlf.hs',
                                'libraries/mlf-language-core/Bootstrap/Data.hs',
                                'libraries/mlf-crates/Bootstrap/InferenceUnit.hs',
                                'bootstrap/MLF/Entry/BuiltinPrelude.hs'])
        require(value['changed_paths'] == changed_paths and
                value['added_paths'] == parent['expected_added_paths'] and
                sorted(path for path in parent['files'] if parent['files'][path] != files[path]) ==
                value['changed_paths'], 'unexpected / missing changed source path')
        require(type(value['deltas']) is dict and set(value['deltas']) == set(value['changed_paths']),
                'exact delta inventory')
        delta_files = set()
        for path, row in value['deltas'].items():
            require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                    row['old'] == parent['files'][path] and row['new'] == files[path] and
                    is_sha(row['sha256']), 'delta identity: ' + path)
            relative_path(row['file'])
            require(row['file'].startswith('deltas/') and row['file'] not in delta_files,
                    'duplicate / escaped delta file')
            delta_files.add(row['file'])
        maintenance = value['maintenance']
        require(type(maintenance) is dict and set(maintenance) == set(self.maintenance_parent['files']),
                'exact six live maintenance entrypoints')
        for name, row in maintenance.items():
            require(type(row) is dict and set(row) == {'file', 'sha256', 'old', 'new'} and
                    row['old'] == self.maintenance_parent['files'][name]['sha256'] and
                    is_sha(row['new']) and row['new'] != row['old'] and is_sha(row['sha256']),
                    'maintenance before/after identity: ' + name)
            relative_path(row['file'])
            require(row['file'].startswith('maintenance-deltas/') and row['file'] not in delta_files,
                    'maintenance delta path / duplicate')
            delta_files.add(row['file'])
        generation = value['generation']
        require(type(generation) is dict and set(generation) == {
            'receipt_sha256', 'literal_sha256', 'output_sha256', 'source_identity', 'generator', 'compiler'
        } and is_sha(generation['receipt_sha256']) and
                generation['literal_sha256'] == files[LITERAL] and
                generation['output_sha256'] == files[CANONICAL], 'genuine generation binding')

    def _validate_generation(self, receipt):
        value = self.value
        require(receipt.get('format') == 'builtin-prelude-verification-v1' and
                all(receipt.get(k) is True for k in ('complete', 'immutable_inputs_verified_after',
                                                    'exact_regeneration', 'candidate_verified')) and
                receipt.get('source_files_rewritten') is False and
                receipt.get('toolchain_qualification') is False, 'completed maintained generation evidence')
        require(receipt.get('canonical', {}).get('sha256') == value['current_files'][CANONICAL],
                'generation evidence names different output')
        for key in ('source_identity', 'generator', 'compiler'):
            require(receipt.get(key) == value['generation'][key], 'generation identity: ' + key)
        inputs = receipt.get('source_identity_inputs')
        require(type(inputs) is dict and type(inputs.get('modules')) is dict and
                receipt['source_identity'] == 'builtin-source-v1:' + canonical_sha(inputs),
                'generation source identity digest')
        require(inputs.get('primitive_abi') == 'mlf-primitive-132-v7' and
                inputs.get('builtin_interface') == 'mlf-primitive/shared-haskell-v1/11',
                'generation uses old primitive / builtin ABI')
        require('Bootstrap.BuiltinPreludeLiteral' in inputs['modules'], 'missing literal producer input')
        for name, row in inputs['modules'].items():
            require(type(row) is dict and set(row) == {'path', 'sha256'} and
                    value['module_paths'].get(name) == row['path'] and
                    value['current_registry'].get(name) == row['sha256'], 'generation source input: ' + name)

    def require_registry(self, value, side):
        require(side in ('parent', 'current'), 'registry side')
        expected = self.parent['registry'] if side == 'parent' else self.value['current_registry']
        hash_map(value, side + ' registry')
        require(value == expected, 'exact complete ' + side + ' registry required')

    def advance_registry(self, parent):
        self.require_registry(parent, 'parent')
        return dict(self.value['current_registry'])

    def registry_to_parent(self, current, added_source_bytes):
        """Deleting new names requires their actual, full-SHA checked raw bytes."""
        self.require_registry(current, 'current')
        require(type(added_source_bytes) is dict and set(added_source_bytes) == set(ADDED_MODULES),
                'actual added module bytes required for inverse projection')
        for name, raw in added_source_bytes.items():
            require(type(raw) is bytes and len(raw) <= MAX_SOURCE_BYTES and sha(raw) == current[name],
                    'added module raw SHA: ' + name)
        return dict(self.parent['registry'])

    def _delta(self, path):
        row = self.value['deltas'][path]
        raw = read_file(self.directory, row['file'], MAX_METADATA_BYTES)
        require(sha(raw) == row['sha256'], 'fixed delta SHA: ' + path)
        delta = strict_json(raw)
        require(delta.get('path') == path and delta.get('old_sha256') == row['old'] and
                delta.get('new_sha256') == row['new'], 'delta owner binding')
        return delta

    def restore_maintenance(self, raw, name):
        """Current live script -> exact old historical bytes, never execute them."""
        require(name in self.value['maintenance'], 'unknown mutable maintenance entrypoint')
        row = self.value['maintenance'][name]
        require(type(raw) is bytes and sha(raw) == row['new'], 'full current maintenance SHA: ' + name)
        delta_raw = read_file(self.directory, row['file'], MAX_METADATA_BYTES)
        require(sha(delta_raw) == row['sha256'], 'fixed maintenance proof SHA')
        delta = strict_json(delta_raw)
        require(delta.get('path') == name and delta.get('old_sha256') == row['old'] and
                delta.get('new_sha256') == row['new'], 'maintenance proof owner binding')
        old = apply_splices(raw, delta, reverse=True)
        require(sha(old) == row['old'] and apply_splices(old, delta) == raw,
                'strict full old maintenance inverse / forward equality')
        return old

    def restore_path(self, raw, path):
        """Return parent bytes, or None only for a verified exact new file."""
        require(path in self.value['current_files'] and type(raw) is bytes and
                sha(raw) == self.value['current_files'][path], 'full current path SHA: ' + path)
        if path in self.value['added_paths']:
            return None
        if path not in self.value['deltas']:
            return raw
        delta = self._delta(path)
        old = apply_splices(raw, delta, reverse=True)
        require(apply_splices(old, delta) == raw, 'byte-exact reverse / forward replay')
        return old

    def advance_path(self, raw, path):
        require(path in self.parent['files'] and type(raw) is bytes and
                sha(raw) == self.parent['files'][path], 'full parent path SHA: ' + path)
        if path not in self.value['deltas']:
            return raw
        delta = self._delta(path)
        new = apply_splices(raw, delta)
        require(apply_splices(new, delta, reverse=True) == raw, 'byte-exact forward / reverse replay')
        return new

    def project_owner(self, raw, module):
        require(module in self.value['module_paths'], 'unknown source owner')
        return self.restore_path(raw, self.value['module_paths'][module])

    def restore_previous_lock(self, raw):
        old = self.restore_path(raw, 'mlf.lock')
        require(sha(old) == PARENT_LOCK_SHA, 'exact L lock SHA')
        validate_lock_transition(old, raw, self.parent['files'], self.value['current_files'])
        return old

    def advance_lock(self, raw):
        require(sha(raw) == PARENT_LOCK_SHA, 'exact L lock SHA')
        new = self.advance_path(raw, 'mlf.lock')
        validate_lock_transition(raw, new, self.parent['files'], self.value['current_files'])
        return new

    def _require_raw_map(self, value, expected, label):
        require(type(value) is dict and set(value) == set(expected), 'complete raw ' + label + ' inventory')
        for path, raw in value.items():
            require(type(raw) is bytes and len(raw) <= MAX_SOURCE_BYTES and sha(raw) == expected[path],
                    'complete raw ' + label + ' SHA: ' + path)

    def project_tree_bytes(self, current):
        """All 192 production files -> 188 L+explicit old runtime base files."""
        self._require_raw_map(current, self.value['current_files'], 'current')
        result = {}
        for path, raw in current.items():
            old = self.restore_path(raw, path)
            if old is not None:
                result[path] = old
        self._require_raw_map(result, self.parent['files'], 'parent')
        validate_shared_transition(result['shared-sources.json'], current['shared-sources.json'])
        validate_lock_transition(result['mlf.lock'], current['mlf.lock'],
                                 self.parent['files'], self.value['current_files'])
        return result

    def advance_tree_bytes(self, parent, additions):
        self._require_raw_map(parent, self.parent['files'], 'parent')
        self._require_raw_map(additions, {p: self.value['current_files'][p]
                                         for p in self.value['added_paths']}, 'added')
        result = {p: self.advance_path(raw, p) for p, raw in parent.items()}
        result.update(additions)
        self._require_raw_map(result, self.value['current_files'], 'current')
        require(self.project_tree_bytes(result) == parent, 'whole source inverse / forward roundtrip')
        return result

    def advance_host_inventory(self, parent):
        return self._host_bridge(parent, 'parent', self.parent['host_inventory'])

    def host_inventory_to_parent(self, current):
        return self._host_bridge(current, 'current', self.parent['host_inventory'])

    def advance_legacy_host_subset(self, parent):
        """The historical four-key helper is separate from complete 19-key IO."""
        require(type(parent) is dict and set(parent) <= set(self.parent['legacy_host_bridge']),
                'legacy host bridge permits only original four keys')
        return self._host_bridge(parent, 'parent', list(parent))

    def legacy_host_subset_to_parent(self, current):
        require(type(current) is dict and set(current) <= set(self.parent['legacy_host_bridge']),
                'legacy host projection permits only original four keys')
        return self._host_bridge(current, 'current', list(current))

    def _host_bridge(self, value, side, names):
        before = self.parent['files'] if side == 'parent' else self.value['current_files']
        after = self.value['current_files'] if side == 'parent' else self.parent['files']
        require(type(value) is dict and value == {name: before[name] for name in names},
                'exact ' + side + ' host inventory required')
        return {name: after[name] for name in names}

    def live_registry(self, current_root):
        """Read all 131 actual module bytes, never infer live status from counts."""
        result = {name: sha(read_file(current_root, path))
                  for name, path in self.value['module_paths'].items()}
        self.require_registry(result, 'current')
        return result

    def live_source_inventory(self, current_root):
        result = {path: sha(read_file(current_root, path))
                  for path in self.value['current_files']}
        require(result == self.value['current_files'], 'exact whole live source inventory required')
        return result

    def live_host_inventory(self, current_root):
        result = {path: sha(read_file(current_root, path))
                  for path in self.parent['host_inventory']}
        self.host_inventory_to_parent(result)
        return result

    def runtime_inventory_to_parent(self, current, added_header_bytes):
        """Separate native category, including the SHA-checked new byte header."""
        names = [path for path in self.value['current_files'] if path.startswith('runtime/')]
        require(type(current) is dict and current == {
            path: self.value['current_files'][path] for path in names
        }, 'complete current native runtime inventory')
        header = 'runtime/mlf_byte_file.h'
        require(type(added_header_bytes) is bytes and
                sha(added_header_bytes) == self.value['current_files'][header],
                'actual added runtime header SHA before deletion')
        return {path: self.parent['files'][path] for path in names if path in self.parent['files']}

    def advance_runtime_inventory(self, parent):
        names = [path for path in self.parent['files'] if path.startswith('runtime/')]
        require(type(parent) is dict and parent == {
            path: self.parent['files'][path] for path in names
        }, 'complete parent native runtime inventory')
        return {path: digest for path, digest in self.value['current_files'].items()
                if path.startswith('runtime/')}

    def added_source_bytes(self, current_root):
        result = {name: read_file(current_root, path) for name, path in ADDED_MODULES.items()}
        for name, raw in result.items():
            require(sha(raw) == self.value['current_registry'][name], 'actual new source SHA: ' + name)
        return result
