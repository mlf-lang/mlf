#!/usr/bin/env python3
"""Run a separately qualified Haskell fixture; never compile or relax guards.

The caller must provide its original bounded guard, authenticated build inputs,
private environment, and a fresh output directory. This script is not that guard.
Publication metrics are observed file changes, NOT write-syscall/IO measurements:
source-context.new staging and query-key.new activity are explicitly not omitted
from the limitation merely because their files disappear or are overwritten.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, stat, subprocess, time, sys
import fcntl, errno
from runpy import run_path

BINARY_HELPER_NAMES = ('artifact_binary_reference.py', 'artifact_binary_typed.py',
                       'artifact_structure_contract.json')
_binary_helpers = None

def binary_helpers():
    """Load the independent, pinned sibling inspectors even under Python -I.

    Do not add a source tree to sys.path, execute production code, or translate
    binary payloads into old artifact text. The JSON contract is a closed tag
    inventory; all framing and graph checks are performed by the independent
    reader before a typed node is used here.
    """
    global _binary_helpers
    if _binary_helpers is None:
        import importlib.util
        sys.dont_write_bytecode = True
        directory = Path(__file__).resolve().parent
        paths = [directory / name for name in BINARY_HELPER_NAMES]
        for path in paths:
            require(path.resolve(strict=True) == path and stat.S_ISREG(path.lstat().st_mode),
                    'real regular independent binary inspector input')
        modules = []
        for name, path in zip(('artifact_binary_reference', 'artifact_binary_typed'), paths):
            require(name not in sys.modules, 'independent binary inspector module already injected')
            spec = importlib.util.spec_from_file_location(name, path)
            require(spec is not None and spec.loader is not None, 'binary inspector loader')
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module  # dataclasses and the typed helper's import need this identity
            spec.loader.exec_module(module)
            require(Path(module.__file__).resolve() == path, 'binary inspector module identity')
            modules.append(module)
        _binary_helpers = (*modules, {str(path): digest(path.read_bytes()) for path in paths})
    return _binary_helpers

def binary_artifact(raw, schema):
    reference, typed, _ = binary_helpers()
    require(raw.startswith(reference.MAGIC), 'actual binary artifact required; no text fallback')
    return typed.inspect_artifact(raw, schema)

def graph_node(document, index, tag, arity=None):
    node = document.nodes[index]
    require(node.kind == 3 and node.data[0] == tag and
            (arity is None or len(node.data[1]) == arity), 'independent typed graph node shape')
    return node.data[1]

def graph_text(document, index):
    node = document.nodes[index]
    require(node.kind == 2, 'independent graph text leaf')
    return document.symbols[node.data]

def binary_query(raw):
    document = binary_artifact(raw, 2)
    root = binary_helpers()[1].query_payload_root(document)
    tag = document.nodes[root].data[0]
    if tag == 306:
        _, _, reference, header, body = graph_node(document, root, tag, 5)
    else:
        reference, _, _, header, body = graph_node(document, root, 303, 5)
    return {'document': document, 'reference': graph_text(document, reference),
            'fingerprint': binary_helpers()[1].verify_source_result(document),
            'header': header, 'body': body}

def binary_context(raw, reference):
    require(digest(raw) == reference, 'actual complete binary context SHA256')
    document = binary_artifact(raw, 1)
    declarations, = graph_node(document, document.roots[0], 244, 1)
    return document, declarations

def require_graph_equal(left, left_root, right, right_root, message):
    """Compare complete DAGs without expanding shared nodes."""
    pending, seen = [(left_root, right_root)], set()
    while pending:
        pair = pending.pop()
        if pair in seen:
            continue
        seen.add(pair)
        a, b = pair
        x, y = left.nodes[a], right.nodes[b]
        require(x.kind == y.kind, message)
        if x.kind == 3:
            xtag, xs = x.data
            ytag, ys = y.data
            require(xtag == ytag and len(xs) == len(ys), message)
            pending.extend(zip(xs, ys))
        elif x.kind == 2:
            require(left.symbols[x.data] == right.symbols[y.data], message)
        else:
            require(x.data == y.data, message)


def source_key_from_binary(context, declarations, compact):
    # This is the historical logical-key oracle, not an artifact serialization.
    # Stored bytes remain independently verified MLFBIN graph nodes.
    _, typed, _ = binary_helpers()
    require(graph_node(context, context.roots[0], 244, 1) == (declarations,),
            'logical source key uses the independently validated context root')
    values = context.values()[0]
    require(len(compact) == 8 and compact[0] == 'MLF-SOURCE-CRATE-QUERY-7', 'complete compact source key')
    logical = typed.logical_context(typed.list_values(typed.value_node(values, 244, 1)[0]), compact[0])
    return pack(compact[:5] + [logical] + compact[5:])

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def unpack(text):
    result = []
    while text:
        count, separator, rest = text.partition(":")
        require(separator and count.isascii() and count.isdecimal(), "scalar framing")
        size = int(count)
        require(str(size) == count and size <= len(rest), "canonical scalar framing")
        result.append(rest[:size])
        text = rest[size:]
    return result

def pack(fields):
    return "".join(f"{len(value)}:{value}" for value in fields)

def snapshot(root, active_hashes):
    files, directories = {}, 0
    allocated = root.lstat().st_blocks * 512
    for path in sorted(root.rglob("*")):
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode), "regular cache tree only")
        allocated += s.st_blocks * 512
        if stat.S_ISDIR(s.st_mode):
            directories += 1
            continue
        require(s.st_nlink == 1 and s.st_size <= 16 * 1024**2, "small private cache file")
        # Never close an extra descriptor for an existing lock inode while a
        # live POSIX owner may be part of this control. Empty bytes are exact.
        raw = b'' if path.name == '.lock' and s.st_size == 0 else path.read_bytes()
        files[str(path.relative_to(root))] = {
            "bytes": len(raw), "sha256": digest(raw), "allocated": s.st_blocks * 512,
            "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
        }
    _, typed, _ = binary_helpers()
    independently_checked = typed.cache_snapshot(root, active_hashes)
    require(independently_checked['files'] == files, 'independent binary closure agrees with full physical snapshot')
    records = independently_checked['active_records']
    contexts = set(independently_checked['reachable_contexts'])
    legacy = independently_checked['legacy_records']
    reachable = set(records) | contexts
    return {
        "files": files, "directories_excluding_root": directories,
        "active_records": records, "reachable_contexts": sorted(contexts),
        "legacy_records": legacy, "reachable_files": sorted(reachable),
        "reachable_logical_bytes": sum(files[n]["bytes"] for n in reachable),
        "reachable_file_allocated_bytes": sum(files[n]["allocated"] for n in reachable),
        "all_cache_logical_bytes": sum(x["bytes"] for x in files.values()),
        "all_cache_pathname_conservative_allocated_bytes": allocated,
        "other_physical_files": sorted(set(files) - reachable),
        "unreachable_context_files": sorted(n for n in set(files) - reachable if n.endswith(".mlfqc")),
        "retained_old_query_files": sorted(n for n in set(files) - reachable if n.endswith(".mlfq")),
        "scratch_and_lock_files": sorted(n for n in set(files) - reachable if not n.endswith((".mlfqc", ".mlfq"))),
        "other_physical_bytes": sum(x["bytes"] for n, x in files.items() if n not in reachable),
        "no_gc_performed": True,
        "binary_details": independently_checked['binary_details'],
    }

def publication_delta(before, after):
    a, b = before["files"], after["files"]
    added = sorted(set(b) - set(a))
    changed = sorted(n for n in set(a) & set(b)
                     if a[n]["mtime_ns"] != b[n]["mtime_ns"] or a[n]["sha256"] != b[n]["sha256"])
    return {
        "added_files": added, "observed_changed_files": changed,
        "added_logical_bytes": sum(b[n]["bytes"] for n in added),
        "observed_published_file_change_bytes": sum(b[n]["bytes"] for n in added + changed),
        "not_total_io_bytes": True,
        "temporary_creation_deletion_and_multiple_writes_not_observed": True,
    }

SENTINELS = {"unrelated.new": b"retain unrelated staging\n",
             "codegen-key.new": b"retain separate codegen scratch\n",
             "key.new": b"retain non-query key scratch\n"}


def no_query_scratch(cache):
    require(not os.path.lexists(cache / "query-key.new"), "query scratch remains after normal return")


def small_identity(path):
    s = path.lstat()
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_size <= 65536, "small regular sentinel")
    # A POSIX record lock is dropped if this process closes ANY fd for the
    # same inode. Never reopen/read/close .lock while the pair holder owns it.
    # For a regular zero-byte file the empty SHA is exact from metadata.
    if path.name == ".lock":
        require(s.st_size == 0, "empty lock sentinel")
        contents = b""
    else:
        contents = path.read_bytes()
    return {"sha256": digest(contents), "bytes": s.st_size,
            "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns,
            "device": s.st_dev, "inode": s.st_ino, "mode": s.st_mode, "blocks": s.st_blocks}


def seed_cache(cache, directory=False):
    cache.mkdir()
    for name, value in SENTINELS.items():
        with (cache / name).open("xb") as stream:
            stream.write(value)
    with (cache / ".lock").open("xb"):
        pass
    scratch = cache / "query-key.new"
    if directory:
        scratch.mkdir()
        with (scratch / "retained-child").open("xb") as stream:
            stream.write(b"must not recurse into reserved scratch directory\n")
    else:
        with scratch.open("xb") as stream:
            stream.write(b"stale query key from a prior stopped run\n")
    result = {name: small_identity(cache / name) for name in SENTINELS}
    result[".lock"] = small_identity(cache / ".lock")
    if directory:
        result["query-key.new/retained-child"] = small_identity(scratch / "retained-child")
    return result


def verify_sentinels(cache, original):
    for name, expected in original.items():
        require(small_identity(cache / name) == expected, "sentinel or lock identity changed: " + name)


def physical_inventory(cache):
    # No reference/liveness claim for failed calls without a QueryReport.
    # Every file/directory is still included, including rejected scratch dirs.
    rows, logical, allocated = {}, 0, 0
    for path in [cache, *sorted(cache.rglob("*"))]:
        s = path.lstat()
        require(stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode), "regular private cache tree")
        allocated += s.st_blocks * 512
        row = {"directory": stat.S_ISDIR(s.st_mode), "bytes": s.st_size,
               "allocated": s.st_blocks * 512, "device": s.st_dev, "inode": s.st_ino}
        if stat.S_ISREG(s.st_mode):
            require(s.st_size <= 16 * 1024**2, "individual cache file cap")
            logical += s.st_size
            row["sha256"] = digest(b'' if path.name == '.lock' and s.st_size == 0 else path.read_bytes())
        rows[str(path.relative_to(cache))] = row
    return {"all_physical_nodes": rows, "all_file_logical_bytes": logical,
            "all_pathname_conservative_allocated_bytes": allocated,
            "active_reference_set_not_inferred_from_failure": True}


def publication_context_identity(path):
    # Preserve the original context/backup-only 128KiB allowance. Binary
    # carriers may be smaller; that is no reason to relax any old file cap.
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 128 * 1024,
            "bounded regular publication context")
    contents = path.read_bytes()
    after = path.lstat()
    require(len(contents) == before.st_size and all(getattr(before, field) == getattr(after, field) for field in
            ["st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_blocks"]),
            "publication context changed during bounded sampling")
    return {"sha256": digest(contents), "bytes": before.st_size,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
            "device": before.st_dev, "inode": before.st_ino, "mode": before.st_mode, "blocks": before.st_blocks}


def publication_directory_identity(path):
    before = path.lstat()
    require(stat.S_ISDIR(before.st_mode), "real publication collision directory")
    children = sorted(p.name for p in path.iterdir())
    after = path.lstat()
    fields = ["st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_blocks"]
    require(all(getattr(before, field) == getattr(after, field) for field in fields),
            "publication directory changed during sampling")
    return {"device": before.st_dev, "inode": before.st_ino, "mode": before.st_mode,
            "links": before.st_nlink, "bytes": before.st_size, "blocks": before.st_blocks,
            "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns,
            "children": children,
            "directory_entry_names_sha256": digest(json.dumps(children, ensure_ascii=True).encode("ascii")),
            "directory_hash_scope": "sorted immediate entry names, not directory contents"}


def with_publication_lock(cache, action):
    # Only after a fixture process exits. Never open/read/close another fd for
    # this inode while this process owns its POSIX record lock.
    path = cache / ".lock"
    require(cache.resolve(strict=True) == cache, "real private publication cache")
    identity = small_identity(path)  # .lock is metadata-only, never reopened.
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        held = os.fstat(fd)
        require(stat.S_ISREG(held.st_mode) and held.st_size == 0 and
                (held.st_dev, held.st_ino) == (identity["device"], identity["inode"]),
                "same publication lock inode")
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        require(small_identity(path) == identity, "publication lock binding changed")
        result = action()
        require(small_identity(path) == identity, "publication lock changed while held")
        fcntl.lockf(fd, fcntl.LOCK_UN)
        return result
    finally:
        os.close(fd)


def independent_lock_probe(arguments):
    require(len(arguments) == 3, "lock probe exact arguments")
    path, device, inode = Path(arguments[0]), int(arguments[1]), int(arguments[2])
    require(path.resolve(strict=True) == path, "real lock path")
    fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (before.st_dev, before.st_ino) == (device, inode), "same lock inode")
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        after = path.lstat()
        require((after.st_dev, after.st_ino) == (device, inode), "lock path binding changed")
        fcntl.lockf(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
    print("PASS independent lock acquisition")



WINDOW_HIDDEN_MARKERS = [
    'alternating contexts reuse without files', 'MRU promotion survives ninth insertion',
    'ninth insertion evicts least recent route', 'oversized input prefix hit returns only eight',
    'oversized input ninth entry is ignored', 'different reference is isolated',
    'different directory is isolated', 'independently verified other directory reuses',
    'encoded guard refuses hidden context reuse',
    *[name + ' guard refuses hidden context reuse' for name in ['kind', 'constructor', 'field']],
    'alpha structural guard refuses hidden context reuse',
    'obsolete source record clears all entries', 'malformed record clears all entries',
    'unsafe reference clears all entries', 'malformed full key clears all entries',
    'complete key mismatch clears before reuse',
    'raw payload rejection clears after reuse',
]
WINDOW_RESTORED_MARKERS = [
    'successful disk miss retains other entries', 'different directory disk miss retains original route',
    'encoded guard disk rejection clears all entries',
    *[name + ' guard disk rejection clears all entries' for name in ['kind', 'constructor', 'field']],
    'same route structural miss succeeds with only fresh entry',
]
WINDOW_STABLE = ['device', 'inode', 'mode', 'links', 'bytes', 'sha256', 'mtime_ns', 'blocks']
WINDOW_STAT_FIELDS = ['st_dev', 'st_ino', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_blocks']


def window_sample(path, cap):
    before = path.lstat()
    require(path.resolve(strict=True) == path and stat.S_ISREG(before.st_mode) and
            before.st_nlink == 1 and before.st_size <= cap, 'bounded regular window evidence')
    if path.name == '.lock':
        require(before.st_size == 0, 'zero regular window lock')
        raw = b''  # metadata only: never open/close a second fd for a held lock inode
    else:
        raw = path.read_bytes()
    after = path.lstat()
    require(len(raw) == before.st_size and all(getattr(before, f) == getattr(after, f) for f in WINDOW_STAT_FIELDS),
            'window evidence changed during sampling')
    return {'device': before.st_dev, 'inode': before.st_ino, 'mode': before.st_mode,
            'links': before.st_nlink, 'bytes': before.st_size, 'mtime_ns': before.st_mtime_ns,
            'ctime_ns': before.st_ctime_ns, 'blocks': before.st_blocks, 'sha256': digest(raw)}, raw


def window_snapshot(cache, references, hidden):
    require(len(references) == len(set(references)) == 9 and
            all(re.fullmatch('[0-9a-f]{64}', r) for r in references), 'nine actual window references')
    other = cache / 'different-cache'
    records = {f'entry-{label}.mlfq': ref for label, ref in zip('abcdefghi', references)}
    records['different-cache/entry-a.mlfq'] = references[0]
    context_paths = {'context-' + ref + '.mlfqc': ref for ref in references}
    context_paths['different-cache/context-' + references[0] + '.mlfqc'] = references[0]
    suffix = '.window-test-backup' if hidden else ''
    expected_main = sorted(['.lock', 'different-cache', *[f'entry-{label}.mlfq' for label in 'abcdefghi'],
                            *['context-' + ref + '.mlfqc' + suffix for ref in references]])
    expected_other = sorted(['.lock', 'entry-a.mlfq', 'context-' + references[0] + '.mlfqc' + suffix])
    directories = {'.': publication_directory_identity(cache), 'different-cache': publication_directory_identity(other)}
    require(directories['.']['children'] == expected_main and directories['different-cache']['children'] == expected_other,
            'exact window tree; no stage, missing raw record, or uncounted backup')
    result = {'hidden': hidden, 'references': references, 'directories': directories,
              'records': {}, 'contexts': {}, 'locks': {}, 'context_locations': {}}
    compact = ['MLF-SOURCE-CRATE-QUERY-7', 'crate:α😀', 'compiler', 'member:opaque:😀',
               'bindings', 'source-group', 'observed-contracts', 'scope-table:α😀']
    for rel, reference in records.items():
        identity, raw = window_sample(cache / rel, 65536)
        query = binary_query(raw)
        carrier = cache / Path(rel).parent / ('context-' + reference + '.mlfqc' + suffix)
        doc, declarations = binary_context(carrier.read_bytes(), reference)
        key = source_key_from_binary(doc, declarations, compact)
        require(query['reference'] == reference and query['fingerprint'] == digest(key.encode()),
                'canonical real binary window writer record and complete typed raw payload')
        result['records'][rel] = identity
    for rel, reference in context_paths.items():
        actual = cache / (rel + suffix)
        missing = cache / (rel if hidden else rel + '.window-test-backup')
        require(not os.path.lexists(missing), 'counterfactual context location is really absent')
        identity, raw = window_sample(actual, 2 * 1024**2)
        binary_context(raw, reference)
        require(identity['sha256'] == reference, 'actual complete binary context SHA and typed graph')
        result['contexts'][rel] = identity
        result['context_locations'][rel] = rel + suffix
    for rel in ['.lock', 'different-cache/.lock']:
        result['locks'][rel] = window_sample(cache / rel, 65536)[0]
    return result


def compare_window_snapshots(before, after):
    require(before['references'] == after['references'] and before['records'] == after['records'] and
            before['locks'] == after['locks'], 'every original raw record and lock unchanged')
    require(set(before['contexts']) == set(after['contexts']), 'complete ten-carrier population')
    for rel, value in before['contexts'].items():
        require(all(value[k] == after['contexts'][rel][k] for k in WINDOW_STABLE),
                'renamed carrier restored with full original inode/bytes/mtime')
    for rel, value in before['directories'].items():
        require(all(value[k] == after['directories'][rel][k] for k in ['device', 'inode', 'mode', 'links']),
                'original cache directories preserved')
    # Rename may change directory size/times and carrier ctime. All values are
    # retained, never misrepresented as unchanged; allocation stays fully counted.


def live_window_held_probe(owner, path):
    require(owner.poll() is None, 'owner alive before held-lock conflict probe')
    identity = window_sample(path, 65536)[0]
    fd = os.open(path, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    acquired, conflict = False, None
    try:
        held = os.fstat(fd)
        require(stat.S_ISREG(held.st_mode) and held.st_nlink == 1 and held.st_size == 0 and
                (held.st_dev, held.st_ino) == (identity['device'], identity['inode']), 'held probe exact regular zero lock')
        try:
            fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as error:
            require(error.errno in [errno.EACCES, errno.EAGAIN], 'only POSIX contention is held-lock evidence')
            conflict = error.errno
        require(not acquired and conflict is not None, 'parent must not acquire the owner-held inode')
        current = path.lstat()
        require(all(getattr(held, f) == getattr(current, f) for f in WINDOW_STAT_FIELDS) and owner.poll() is None,
                'exact lock inode/path stable and owner alive during conflict')
    finally:
        if acquired:
            fcntl.lockf(fd, fcntl.LOCK_UN)
        os.close(fd)
    require(window_sample(path, 65536)[0] == identity and owner.poll() is None, 'stable lock and live owner after conflict')
    return {'identity': identity, 'conflict_errno': conflict, 'owner_pid': owner.pid,
            'owner_alive_before': True, 'owner_alive_after': True, 'parent_acquired': False,
            'scope': 'independent parent kernel contention on child-owned exact inode; not parent lock ownership'}


def live_window_release_probe(owner, path):
    require(owner.poll() is None, 'owner alive before actual released-lock probe')
    identity = window_sample(path, 65536)[0]
    fd = os.open(path, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    acquired = False
    try:
        held = os.fstat(fd)
        require(stat.S_ISREG(held.st_mode) and held.st_nlink == 1 and held.st_size == 0 and
                (held.st_dev, held.st_ino) == (identity['device'], identity['inode']),
                'release probe exact existing zero regular lock inode')
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        # Only fstat/lstat while held: no second open/read/close for this inode.
        current = path.lstat()
        require(all(getattr(held, f) == getattr(current, f) for f in WINDOW_STAT_FIELDS),
                'release probe inode/path stable while held')
        require(owner.poll() is None, 'owner still alive after actual lock acquisition')
    finally:
        if acquired:
            fcntl.lockf(fd, fcntl.LOCK_UN)
        os.close(fd)
    require(window_sample(path, 65536)[0] == identity and owner.poll() is None,
            'lock unchanged and owner alive after release probe')
    return {'identity': identity, 'acquired_nonblocking': True, 'owner_alive_before': True,
            'owner_alive_after': True, 'owner_pid': owner.pid, 'scope': 'parent lockf before owner exit'}


def run_window_owned(fixture, out, record, save, name, arguments, dialogue):
    row = {'name': name, 'argv': [str(fixture), *map(str, arguments)], 'kind': 'fixture',
           'state': 'running', 'timeout_seconds': 60}
    record['commands'].append(row)
    save()
    captures = {kind: out / (name + '.' + kind) for kind in ['stdout', 'stderr']}
    started, owner, failure, expected = time.monotonic(), None, None, None
    active_deadline = [None]
    def wait_marker(prefix, pattern, phase_seconds=10):
        deadline = min(started + 60, time.monotonic() + phase_seconds)
        active_deadline[0] = deadline
        while True:
            require(owner.poll() is None, 'window owner exited before parent ACK')
            require(captures['stdout'].stat().st_size <= 65536 and captures['stderr'].stat().st_size == 0,
                    'bounded marker capture and strict empty stderr')
            raw = captures['stdout'].read_bytes()
            require(len(raw) <= 65536, 'bounded marker read')
            matched = re.fullmatch(pattern, raw)
            if matched:
                return matched, raw
            require(raw.startswith(prefix) or prefix.startswith(raw), 'exact ordered handshake prefix')
            require(time.monotonic() < deadline, 'phase deadline within total60')
            time.sleep(.01)
    def ack(value, audit_deadline=None):
        if audit_deadline is not None:
            active_deadline[0] = min(active_deadline[0], audit_deadline)
        require(active_deadline[0] is not None and time.monotonic() < min(started + 60, active_deadline[0]) and
                owner.poll() is None, 'live ACK including audit within phase deadline and original case60')
        owner.stdin.write(value)
        owner.stdin.flush()
    try:
        with captures['stdout'].open('xb') as stdout, captures['stderr'].open('xb') as stderr:
            owner = subprocess.Popen(row['argv'], cwd=out, env=os.environ.copy(), stdin=subprocess.PIPE,
                                     stdout=stdout, stderr=stderr)
            row['owner_pid'] = owner.pid
            expected = dialogue(owner, wait_marker, ack, row, started)
            owner.stdin.close()
            owner.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
    except BaseException as error:
        failure = error
        row.update(error=type(error).__name__ + ': ' + str(error), timed_out=isinstance(error, subprocess.TimeoutExpired))
    finally:
        if owner is not None:
            try:
                if owner.poll() is None:
                    owner.kill()
                owner.wait(timeout=5)
                if owner.stdin is not None and not owner.stdin.closed:
                    owner.stdin.close()
            except BaseException as error:
                row['cleanup_error'] = type(error).__name__ + ': ' + str(error)
                if failure is None:
                    failure = error
            row['exit_code'] = owner.returncode
        row.update(seconds=time.monotonic() - started, state='failed')
        for kind, path in captures.items():
            if path.exists():
                hasher = hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(65536), b''):
                        hasher.update(block)
                row[kind] = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': hasher.hexdigest()}
        save()  # Preserve all raw captures and phase evidence on timeout/nonzero/assertion failure.
    if failure is not None:
        raise failure
    require(row['exit_code'] == 0 and row['stderr']['bytes'] == 0 and row['stdout']['bytes'] <= 65536,
            'new control exact status/capture bounds')
    require(captures['stdout'].read_bytes() == expected, 'complete ordered new-control markers')
    row['state'] = 'passed'
    save()


def run_window_controls(fixture, out, record, save):
    window_cache = out / 'window-helper-cache'
    evidence = {'helper': {}}
    record['context_read_window'] = evidence
    hidden_markers = b''.join(('PASS window ' + label + '\n').encode('ascii') for label in WINDOW_HIDDEN_MARKERS)
    restored_markers = b''.join(('PASS window ' + label + '\n').encode('ascii') for label in WINDOW_RESTORED_MARKERS)
    def window_dialogue(owner, wait_marker, ack, row, started):
        matched, before_output = wait_marker(b'WINDOW-BEFORE ', rb'WINDOW-BEFORE ' + rb'([0-9a-f]{64}) ' * 8 + rb'([0-9a-f]{64})\n')
        references = [x.decode('ascii') for x in matched.groups()]
        value = evidence['helper']
        value['before'] = window_snapshot(window_cache, references, False)
        value['owner_pid'] = owner.pid
        value['before_held_probes'] = [live_window_held_probe(owner, window_cache / '.lock'),
                                           live_window_held_probe(owner, window_cache / 'different-cache/.lock')]
        save(); ack(b'WINDOW-BEFORE-ACK\n')
        hidden_output = before_output + b'WINDOW-HIDDEN\n'
        wait_marker(before_output + b'WINDOW-HIDDEN', re.escape(hidden_output))
        value['hidden'] = window_snapshot(window_cache, references, True)
        compare_window_snapshots(value['before'], value['hidden'])
        value['hidden_held_probes'] = [live_window_held_probe(owner, window_cache / '.lock'),
                                           live_window_held_probe(owner, window_cache / 'different-cache/.lock')]
        save(); ack(b'WINDOW-HIDDEN-ACK\n')
        restored_output = hidden_output + hidden_markers + b'WINDOW-RESTORED\n'
        wait_marker(hidden_output + hidden_markers + b'WINDOW-RESTORED', re.escape(restored_output))
        value['restored'] = window_snapshot(window_cache, references, False)
        compare_window_snapshots(value['before'], value['restored'])
        value['restored_held_probes'] = [live_window_held_probe(owner, window_cache / '.lock'),
                                           live_window_held_probe(owner, window_cache / 'different-cache/.lock')]
        save(); ack(b'WINDOW-RESTORED-ACK\n')
        released_output = restored_output + restored_markers + b'WINDOW-RELEASED\n'
        wait_marker(restored_output + restored_markers + b'WINDOW-RELEASED', re.escape(released_output))
        value['after'] = window_snapshot(window_cache, references, False)
        require(value['after'] == value['restored'], 'all restored raw/context/lock/tree identities stable through disk controls')
        value['live_release_probes'] = [live_window_release_probe(owner, window_cache / '.lock'),
                                       live_window_release_probe(owner, window_cache / 'different-cache/.lock')]
        value.update(hidden_assertions=WINDOW_HIDDEN_MARKERS, restored_assertions=WINDOW_RESTORED_MARKERS,
                     stable_carrier_fields=WINDOW_STABLE, complete=True,
                     ctime_scope='all observed; renames legitimately change carrier ctime and directory metadata',
                     scope='ten real private carriers absent while owner holds both real locks; all entries from verified reads; not hostile-mutation or foundation hit-count evidence')
        save(); ack(b'WINDOW-RELEASED-ACK\n')
        return released_output + b'PASS window helper complete\n'
    run_window_owned(fixture, out, record, save, 'window-helper',
                     ['window-helper', window_cache], window_dialogue)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--case', help='one control plus its required setup and paired processes')
    args = parser.parse_args()
    plan = run_path(str(Path(__file__).with_name('context_control_plan.py')))
    expected_commands = plan['commands_for'](args.case)
    active = set(expected_commands)
    drivers = ['query'] if 'query-cold' in active else []
    memo_drivers = ['query'] if 'memo-query' in active else []
    left_modes = [kind for kind in ('legacy', 'source') if 'left-' + kind in active]
    fixture, out = args.fixture.absolute(), args.output.absolute()
    require(fixture.is_file() and fixture.resolve() == fixture, "qualified regular fixture path")
    require(not out.exists() and out.parent.is_dir() and out.parent.resolve() == out.parent, "fresh real output")
    inspector_inputs = binary_helpers()[2]
    out.mkdir()
    record = {"complete": False, "fixture_sha256": digest(fixture.read_bytes()), "commands": [], "drivers": {},
              "selected_case": args.case, "planned_commands": expected_commands,
              "binary_inspector_inputs": inspector_inputs,
              "limitations": [
        "Small synthetic source population, not corpus-wide performance or space estimate.",
        "One cooperative POSIX same-cache pair; no same-process thread, hostile-directory, crash, permission-failure or GC qualification.",
        "Publication deltas are snapshots, not total IO; deleted staging writes remain unmeasured.",
        "Final objects/contexts checked on actual local compiler identified by outer build receipt.",
    ]}
    def save():
        raw = (json.dumps(record, indent=2) + "\n").encode()
        require(len(raw) <= 1024**2, "small report")
        (out / "receipt.json").write_bytes(raw)
    def run(name, argv, executable=None, timeout=180):
        row = {"name": name, "argv": [str(executable or fixture), *map(str, argv)], "state": "running",
               "kind": "lock-probe" if executable else "fixture", "timeout_seconds": timeout}
        record["commands"].append(row)
        save()
        started = time.monotonic()
        failure = None
        captures = {label: out / (name + "." + label) for label in ("stdout", "stderr")}
        # Private fresh capture files survive nonzero exit, timeout, and size
        # rejection. Never accumulate an unbounded child pipe in this process.
        try:
            with captures["stdout"].open("xb") as stdout, captures["stderr"].open("xb") as stderr:
                result = subprocess.run(row["argv"], cwd=out, env=os.environ.copy(),
                                        stdout=stdout, stderr=stderr, timeout=timeout)
            row["exit_code"] = result.returncode
        except BaseException as error:
            failure = error
            row["error"] = type(error).__name__ + ": " + str(error)
            row["timed_out"] = isinstance(error, subprocess.TimeoutExpired)
        finally:
            row.update(seconds=time.monotonic()-started, state="failed")
            for label, path in captures.items():
                if not path.exists():
                    continue
                hasher = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(65536), b""):
                        hasher.update(block)
                row[label] = {"path": str(path), "bytes": path.stat().st_size,
                              "sha256": hasher.hexdigest()}
            save()  # Full evidence identity must precede every failure/size check.
        if failure is not None:
            raise failure
        require(all(row[label]["bytes"] <= 65536 for label in captures),
                "small fixture capture (full rejected capture retained under outer guard)")
        require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0,
                "fixture status/stderr: " + name)
        row["state"] = "passed"
        save()
        return captures["stdout"].read_bytes()
    def driver(kind, cache, root, value, name):
        raw = run(name, ["query", cache, root / "final.objects", value])
        report = json.loads(raw)
        require(report["format"] == 1 and len(report["groups"]) > 0, "actual query report")
        no_query_scratch(cache)
        hashes = [x["query_key"] for x in report["groups"]]
        require(len(hashes) == len(set(hashes)), "distinct query records")
        artifact = root / "final.objects"
        measured = {"query_report": report, "cache": snapshot(cache, hashes),
                    "artifact_sha256": {artifact.name: digest(artifact.read_bytes())}}
        return measured
    try:
        if "helper" in active:
            helper = run("helper", ["helper", out / "helper-cache"])
            require(helper.endswith(b"PASS helper CACHE1/CACHE2/CACHE3, complete-key and corrupt-input controls\n"), "helper terminal marker")

        if "raw-final" in active:
            raw_final = run("raw-final", ["raw-final", out / "raw-final-cache"])
            require(raw_final == b"PASS final payload cannot masquerade as raw source cache\n", "raw/final terminal marker")

        for kind in drivers:
            root = out / kind
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache)
            cold = driver(kind, cache, root, "41", kind + "-cold")
            require(cold["query_report"]["inferred_groups"] > 0 and cold["query_report"]["reused_groups"] == 0, "cold actually infers")
            require(len(cold["cache"]["active_records"]) == 2 and len(cold["cache"]["reachable_contexts"]) == 1, "two groups share one context")
            entry = {"sentinels": sentinels, "cold": cold}
            record["drivers"][kind] = entry
            save()
            if kind + "-warm" not in active:
                verify_sentinels(cache, sentinels)
                continue
            warm = driver(kind, cache, root, "41", kind + "-warm")
            require(warm["query_report"]["inferred_groups"] == 0 and warm["query_report"]["reused_groups"] == cold["query_report"]["inferred_groups"], "warm actually hits")
            require(warm["artifact_sha256"] == cold["artifact_sha256"], "final artifacts exact cold/warm")
            require(warm["cache"]["reachable_contexts"], "production cache uses shared representation")
            for n in cold["cache"]["reachable_contexts"]:
                require(cold["cache"]["files"][n] == warm["cache"]["files"][n], "warm context unchanged")
            mixed = None
            before_change = warm
            entry["warm"] = warm
            if "query-install-legacy" in active:
                legacy = run("query-install-legacy", ["legacy-one", cache])
                require(legacy == b"PASS fixture replaced one record with valid old CACHE1\n", "legacy injection marker")
                mixed_before = snapshot(cache, [g["query_key"] for g in cold["query_report"]["groups"]])
                if "query-mixed-old-new" in active:
                    mixed = driver(kind, cache, root, "41", "query-mixed-old-new")
                    retired = mixed_before["legacy_records"]
                    require(len(retired) == 1 and not mixed["cache"]["legacy_records"], "one old cache record replaced")
                    require(mixed["query_report"]["inferred_groups"] == 1 and
                            mixed["query_report"]["reused_groups"] == cold["query_report"]["inferred_groups"] - 1,
                            "old source format reinfers only its group")
                    require(mixed["artifact_sha256"] == cold["artifact_sha256"] and
                            mixed["cache"]["files"][retired[0]]["sha256"] == cold["cache"]["files"][retired[0]]["sha256"],
                            "rebuilding restores the current bytes and exact output")
                    before_change = mixed
                    if "query-rebuilt-warm" in active:
                        rebuilt = driver(kind, cache, root, "41", "query-rebuilt-warm")
                        require(rebuilt["query_report"]["inferred_groups"] == 0 and
                                rebuilt["query_report"]["reused_groups"] == cold["query_report"]["inferred_groups"] and
                                rebuilt["artifact_sha256"] == cold["artifact_sha256"], "rebuilt source record hits")
                        entry["rebuilt_warm"] = before_change = rebuilt
            entry.update(mixed_legacy=mixed, before_one_value_change=before_change)
            save()
            if kind + "-one-value-change" not in active:
                verify_sentinels(cache, sentinels)
                continue
            changed = driver(kind, cache, root, "42", kind + "-one-value-change")
            require(changed["query_report"]["inferred_groups"] == 1 and changed["query_report"]["reused_groups"] > 0, "one independent source change reinfers one group")
            require(changed["artifact_sha256"] != cold["artifact_sha256"],
                    "one value change must alter the final artifact, not be a no-op")
            unchanged_records = set(before_change["cache"]["active_records"]) & set(changed["cache"]["active_records"])
            for name in unchanged_records:
                require(before_change["cache"]["files"][name] == changed["cache"]["files"][name],
                        "unchanged active group preserves exact bytes, hash, allocation and timestamps")
            for n in warm["cache"]["reachable_contexts"]:
                require(warm["cache"]["files"][n] == changed["cache"]["files"][n], "one value change does not rewrite shared context")
            entry.update(changed=changed,
                         one_value_publication_delta=publication_delta(before_change["cache"], changed["cache"]))
            save()
            if kind + "-changed-warm" not in active:
                verify_sentinels(cache, sentinels)
                continue
            stable = driver(kind, cache, root, "42", kind + "-changed-warm")
            require(stable["query_report"]["inferred_groups"] == 0 and stable["artifact_sha256"] == changed["artifact_sha256"], "changed warm exact parity")
            repairs = []
            for mutation in plan['REPAIRS']:
                if kind + '-' + mutation not in active:
                    continue
                current = snapshot(cache, [g["query_key"] for g in changed["query_report"]["groups"]])
                if mutation != "corrupt-record":
                    target = cache / current["reachable_contexts"][0]
                    if mutation == "missing-context":
                        target.unlink()  # Only this test's newly created cache is mutated.
                    else:
                        target.write_bytes(b"broken-context")
                else:
                    target = cache / next(n for n, f in current["active_records"].items()
                                          if f in ("MLFBIN-QUERY-SHARED-3", "MLFBIN-QUERY-SHARED-4"))
                    reference_reader, _, _ = binary_helpers()
                    document = binary_artifact(target.read_bytes(), 2)
                    value = document.values()[-1]
                    # Preserve the canonical binary envelope/key/metadata and
                    # valid CRC; only the typed body becomes an invalid text
                    # leaf. This is a real typed-payload miss, not old text
                    # smuggled into a file whose magic happens to be binary.
                    require(value[1] in (303,306), 'fingerprinted source record')
                    malformed = ('node', value[1], (*value[2][:-1], ('text', '')))
                    target.write_bytes(reference_reader.tree_document([*document.values()[:-1],malformed], schema=2))
                repaired = driver(kind, cache, root, "42", kind + "-" + mutation)
                require(repaired["query_report"]["inferred_groups"] >= 1 and repaired["artifact_sha256"] == changed["artifact_sha256"], "corruption miss + exact reconstruction")
                repairs.append({"mutation": mutation, "result": repaired})
            verify_sentinels(cache, sentinels)
            entry.update(changed_warm=stable, repairs=repairs)
            save()
        if "raw-final" in active:
            no_query_scratch(out / "raw-final-cache")
        lifecycle = {}
        record["scratch_lifecycle"] = lifecycle
        canonical_python = str(Path(sys.executable).resolve(strict=True))
        def probe(name, cache, identity):
            row = identity[".lock"]
            raw = run(name, ["-I", "-B", str(Path(__file__).resolve()), "--lock-probe",
                            cache / ".lock", row["device"], row["inode"]],
                      executable=canonical_python, timeout=5)
            require(raw == b"PASS independent lock acquisition\n", "independent lock probe marker")
        def run_with_live_probe(name, argv, marker, probe_name, cache, sentinels, directory=False):
            row = {"name": name, "argv": [str(fixture), *map(str, argv), "await-probe"],
                   "state": "running", "kind": "fixture", "timeout_seconds": 60,
                   "release_qualification": "independent probe while original owner remains alive"}
            record["commands"].append(row)
            save()
            started, owner, failure = time.monotonic(), None, None
            captures = {label: out / (name + "." + label) for label in ("stdout", "stderr")}
            try:
                with captures["stdout"].open("xb") as stdout, captures["stderr"].open("xb") as stderr:
                    owner = subprocess.Popen(row["argv"], cwd=out, env=os.environ.copy(),
                                             stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
                    row["owner_pid"] = owner.pid
                    ready_deadline = started + 10
                    while True:
                        require(owner.poll() is None, "owner exited before independent probe")
                        require(captures["stdout"].stat().st_size <= 65536 and captures["stderr"].stat().st_size == 0,
                                "live owner bounded marker and empty stderr")
                        with captures["stdout"].open("rb") as stream:
                            raw = stream.read(65537)
                        require(len(raw) <= 65536 and marker.startswith(raw), "unexpected live owner marker")
                        if raw == marker:
                            break
                        require(time.monotonic() < ready_deadline, "owner marker deadline of 10 seconds")
                        time.sleep(.01)
                    # Action returned, but the original process is still blocked
                    # on stdin: exit-time lock release cannot satisfy this probe.
                    verify_sentinels(cache, sentinels)  # .lock metadata only.
                    if directory:
                        require((cache / "query-key.new").is_dir(), "rejected scratch directory remains while owner alive")
                    else:
                        no_query_scratch(cache)
                    require(owner.poll() is None, "owner alive immediately before probe")
                    row["alive_before_probe"] = True
                    probe(probe_name, cache, sentinels)
                    require(owner.poll() is None, "owner exited during independent probe")
                    row["alive_after_probe"] = True
                    verify_sentinels(cache, sentinels)
                    require(time.monotonic() - started < 60, "owner overall 60-second deadline")
                    owner.stdin.write(b"PROBE-ACK\n")
                    owner.stdin.flush()
                    owner.stdin.close()
                    row["acknowledgement"] = "PROBE-ACK"
                    owner.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
            except BaseException as error:
                failure = error
                row.update(error=type(error).__name__ + ": " + str(error),
                           timed_out=isinstance(error, subprocess.TimeoutExpired))
            finally:
                if owner is not None:
                    try:
                        if owner.poll() is None:
                            owner.kill()
                        owner.wait(timeout=5)
                        if owner.stdin is not None and not owner.stdin.closed:
                            owner.stdin.close()
                    except BaseException as cleanup_error:
                        row["cleanup_error"] = type(cleanup_error).__name__ + ": " + str(cleanup_error)
                        if failure is None:
                            failure = cleanup_error
                    row["exit_code"] = owner.returncode
                row.update(seconds=time.monotonic()-started, state="failed")
                for label, path in captures.items():
                    if path.exists():
                        hasher = hashlib.sha256()
                        with path.open("rb") as stream:
                            for block in iter(lambda: stream.read(65536), b""):
                                hasher.update(block)
                        row[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": hasher.hexdigest()}
                save()
            if failure is not None:
                raise failure
            require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0 and row["stdout"]["bytes"] <= 65536,
                    "live-probed owner status and captures")
            raw = captures["stdout"].read_bytes()
            require(raw == marker and row.get("alive_before_probe") and row.get("alive_after_probe"),
                    "fixed owner marker and live release proof")
            row["state"] = "passed"
            save()
            return raw
        for mode in left_modes:
            root = out / ("left-" + mode)
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache)
            argv = ["left-" + mode, cache]
            raw = run_with_live_probe("left-" + mode, argv,
                    b"PASS business Left after held-lock group execution\n", "lock-after-" + mode, cache, sentinels)
            require(raw == b"PASS business Left after held-lock group execution\n", "business Left marker")
            no_query_scratch(cache)
            verify_sentinels(cache, sentinels)
            message_path = Path(str(cache) + ".left-message")
            message = message_path.read_bytes()
            require(len(message) <= 65536 and b"type constructor mismatch:" in message,
                    "actual post-group inference diagnostic required")
            lifecycle["left-" + mode] = {"cache": physical_inventory(cache), "original_sentinels": sentinels,
                                          "diagnostic": {"path": str(message_path), "bytes": len(message), "sha256": digest(message)}}
            save()
        if "empty-stale-success" in active:
            empty_root = out / "empty-success"
            empty_root.mkdir()
            cache = empty_root / "cache"
            sentinels = seed_cache(cache)
            raw = run("empty-stale-success", ["empty-success", cache], timeout=60)
            require(raw == b"PASS empty public plan cleans stale scratch\n", "empty cleanup marker")
            no_query_scratch(cache)
            verify_sentinels(cache, sentinels)
            lifecycle["empty-success"] = {"cache": physical_inventory(cache), "original_sentinels": sentinels}

        for name, mode, probe_name, marker in [
                ("empty-directory-failure", "empty-directory-failure", "lock-after-empty-directory",
                 b"PASS directory scratch rejected without recursive deletion\n"),
                ("cleanup-dual-failure", "cleanup-dual-failure", "lock-after-cleanup-dual",
                 b"PASS original Left and cleanup Left are both retained\n")]:
            if name not in active:
                continue
            root = out / name
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache, directory=True)
            raw = run_with_live_probe(name, [mode, cache], marker, probe_name, cache, sentinels, directory=True)
            require(raw == marker, "directory rejection marker")
            verify_sentinels(cache, sentinels)
            require((cache / "query-key.new").is_dir(), "rejected scratch directory retained")
            lifecycle[name] = {"cache": physical_inventory(cache), "original_sentinels": sentinels,
                               "scope": "public empty-plan tail" if mode == "empty-directory-failure" else "helper under explicit acquired/released lock"}
            save()
        if "concurrent-a" in active:
            pair_root = out / "concurrent"
            pair_root.mkdir()
            cache = pair_root / "cache"
            sentinels = seed_cache(cache)
            stale = small_identity(cache / "query-key.new")
            lock_path = cache / ".lock"
            fd = os.open(lock_path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
            children, handles, pair_rows = [], [], []
            pair_error = None
            started = time.monotonic()
            try:
                lock_stat = os.fstat(fd)
                require((lock_stat.st_dev, lock_stat.st_ino) == (sentinels[".lock"]["device"], sentinels[".lock"]["inode"]), "holder exact lock inode")
                fcntl.lockf(fd, fcntl.LOCK_EX)
                for name in ["concurrent-a", "concurrent-b"]:
                    result_file = pair_root / (name + ".objects")
                    row = {"name": name, "argv": [str(fixture), "concurrent", str(cache), str(result_file)],
                           "state": "running", "kind": "fixture", "timeout_seconds": 60}
                    record["commands"].append(row)
                    pair_rows.append(row)
                    stdout = (out / (name + ".stdout")).open("xb")
                    stderr = (out / (name + ".stderr")).open("xb")
                    handles.extend([stdout, stderr])
                    children.append(subprocess.Popen(row["argv"], cwd=out, env=os.environ.copy(), stdout=stdout, stderr=stderr))
                save()
                ready_deadline = time.monotonic() + 10
                while True:
                    require(all(child.poll() is None for child in children), "cooperative child finished while parent holds lock")
                    ready = []
                    for row in pair_rows:
                        with (out / (row["name"] + ".stdout")).open("rb") as stream:
                            ready.append(stream.read(6) == b"READY\n")
                    if all(ready):
                        break
                    require(time.monotonic() < ready_deadline, "both ready barriers within 10 seconds")
                    time.sleep(.01)
                require(small_identity(cache / "query-key.new") == stale, "scratch modified through held lock")
                verify_sentinels(cache, sentinels)
                bound = lock_path.lstat()
                require((bound.st_dev, bound.st_ino) == (lock_stat.st_dev, lock_stat.st_ino), "holder path still same lock")
                fcntl.lockf(fd, fcntl.LOCK_UN)
                for child in children:
                    child.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
            except BaseException as error:
                pair_error = error
            finally:
                fcntl.lockf(fd, fcntl.LOCK_UN)
                os.close(fd)
                for child in children:
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=5)
                for handle in handles:
                    handle.close()
                for row, child in zip(pair_rows, children):
                    row.update(exit_code=child.returncode, seconds=time.monotonic()-started, state="failed")
                    for label in ["stdout", "stderr"]:
                        path = out / (row["name"] + "." + label)
                        hasher = hashlib.sha256()
                        with path.open("rb") as stream:
                            for block in iter(lambda: stream.read(65536), b""):
                                hasher.update(block)
                        row[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": hasher.hexdigest()}
                save()
            if pair_error is not None:
                raise pair_error
            reports, finals = [], []
            for row in pair_rows:
                require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0 and row["stdout"]["bytes"] <= 65536, "pair status/captures")
                raw = Path(row["stdout"]["path"]).read_bytes()
                require(raw.startswith(b"READY\n"), "pair ready marker")
                reports.append(json.loads(raw[6:]))
                finals.append(digest((pair_root / (row["name"] + ".objects")).read_bytes()))
                row["state"] = "passed"
            require(finals[0] == finals[1], "cooperative final artifacts identical")
            require(sorted((r["inferred_groups"], r["reused_groups"]) for r in reports) == [(0, 2), (2, 0)],
                    "same-cache pair serializes exactly one cold and one warm")
            no_query_scratch(cache)
            verify_sentinels(cache, sentinels)
            lifecycle["concurrent"] = {"reports": reports, "final_sha256": finals, "cache": physical_inventory(cache),
                                         "original_sentinels": sentinels, "scope": "two cooperative POSIX lockf processes; READY is before query preparation, not proof of kernel lock wait; not adversarial TOCTOU/crash proof"}

        # Additive invocation-local context memo controls. Original 31 commands,
        # owner-alive probes, concurrent pair and all their oracles remain above.
        memo_results = {}
        record["context_read_memo"] = memo_results
        def context_identity(path):
            before = path.lstat()
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= 2 * 1024**2,
                    "small regular private context, never a lock path")
            raw = path.read_bytes()
            after = path.lstat()
            require(all(getattr(before, key) == getattr(after, key) for key in
                        ["st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"]),
                    "context identity changed during sampling (read atime excluded)")
            return {"device": before.st_dev, "inode": before.st_ino, "mode": before.st_mode,
                    "links": before.st_nlink, "bytes": len(raw), "sha256": digest(raw),
                    "mtime_ns": before.st_mtime_ns, "ctime_ns": before.st_ctime_ns}
        def run_memo_helper():
            name, cache = "memo-helper", out / "memo-helper-cache"
            row = {"name": name, "argv": [str(fixture), name, str(cache)], "kind": "fixture",
                   "state": "running", "timeout_seconds": 60,
                   "scope": "private held-lock counterfactual; not noncooperative mutation safety"}
            record["commands"].append(row)
            save()
            captures = {label: out / (name + "." + label) for label in ("stdout", "stderr")}
            started, owner, failure = time.monotonic(), None, None
            reference = None
            def wait_marker(prefix, pattern):
                deadline = min(started + 60, time.monotonic() + 10)
                while True:
                    require(owner.poll() is None, "memo owner exited before context identity ACK")
                    require(captures["stdout"].stat().st_size <= 65536 and captures["stderr"].stat().st_size == 0,
                            "bounded memo marker and empty stderr")
                    raw = captures["stdout"].read_bytes()
                    require(len(raw) <= 65536, "bounded memo marker read")
                    match = re.fullmatch(pattern, raw)
                    if match:
                        return match, raw
                    # Prefix includes complete prior markers; a partial next
                    # line may be in flight, but arbitrary earlier lines may not.
                    require(raw.startswith(prefix) or prefix.startswith(raw), "memo handshake prefix changed")
                    require(time.monotonic() < deadline, "memo marker 10-second deadline within total 60")
                    time.sleep(.01)
            try:
                with captures["stdout"].open("xb") as stdout, captures["stderr"].open("xb") as stderr:
                    owner = subprocess.Popen(row["argv"], cwd=out, env=os.environ.copy(), stdin=subprocess.PIPE,
                                             stdout=stdout, stderr=stderr)
                    row["owner_pid"] = owner.pid
                    match, raw_before = wait_marker(b"MEMO-CONTEXT-BEFORE ", rb"MEMO-CONTEXT-BEFORE ([0-9a-f]{64})\n")
                    reference = match.group(1).decode("ascii")
                    path = cache / ("context-" + reference + ".mlfqc")
                    before = context_identity(path)
                    require(before["sha256"] == reference, "before identity matches actual context digest")
                    require(owner.poll() is None, "memo owner alive before first ACK")
                    row["context_before"] = before
                    save()
                    owner.stdin.write(b"MEMO-BEFORE-ACK\n"); owner.stdin.flush()
                    prefix = raw_before + b"PASS empty memo needs context file\nMEMO-CONTEXT-AFTER "
                    _, raw_after = wait_marker(prefix, re.escape(prefix + reference.encode() + b"\n"))
                    after = context_identity(path)
                    stable = ["device", "inode", "mode", "links", "bytes", "sha256", "mtime_ns"]
                    require(all(before[k] == after[k] for k in stable), "bracket restores original context identity and full bytes")
                    require(not Path(str(path) + ".memo-test-backup").exists(), "backup consumed by restoration")
                    require(owner.poll() is None, "memo owner alive after restoration sampling")
                    row.update(context_after=after, restored_fields=stable,
                               ctime_scope="recorded before/after; rename legitimately changes ctime")
                    save()
                    owner.stdin.write(b"MEMO-AFTER-ACK\n"); owner.stdin.flush(); owner.stdin.close()
                    owner.wait(timeout=max(.001, 60 - (time.monotonic() - started)))
            except BaseException as error:
                failure = error
                row.update(error=type(error).__name__ + ": " + str(error), timed_out=isinstance(error, subprocess.TimeoutExpired))
            finally:
                if owner is not None:
                    try:
                        if owner.poll() is None:
                            owner.kill()
                        owner.wait(timeout=5)
                        if owner.stdin is not None and not owner.stdin.closed:
                            owner.stdin.close()
                    except BaseException as error:
                        row["cleanup_error"] = type(error).__name__ + ": " + str(error)
                        if failure is None:
                            failure = error
                    row["exit_code"] = owner.returncode
                row.update(seconds=time.monotonic() - started, state="failed")
                for label, path in captures.items():
                    if path.exists():
                        hasher = hashlib.sha256()
                        with path.open("rb") as stream:
                            for block in iter(lambda: stream.read(65536), b""):
                                hasher.update(block)
                        row[label] = {"path": str(path), "bytes": path.stat().st_size, "sha256": hasher.hexdigest()}
                save()  # Full captures survive wrong marker, EOF, status, timeout, and assertion failure.
            if failure is not None:
                raise failure
            require(row["exit_code"] == 0 and row["stderr"]["bytes"] == 0 and row["stdout"]["bytes"] <= 65536,
                    "memo helper status and bounded captures")
            tail = ["memo rejects bad payload", "memo rejects full scope key change", "memo rejects owner change",
                    "memo rejects parameter change", "memo rejects declaration change", "memo rejects context field change",
                    "memo rejects different digest", "memo rejects unsafe reference", "memo does not cross cache directory",
                    "obsolete source record clears memo", "memo rejects datatype kind change",
                    "memo rejects datatype constructor change", "memo rejects datatype field change",
                    "datatype switch and structural guards", "prepared authority rejects memo-decoded final payload",
                    "memo helper complete"]
            expected = raw_after + b"".join(("PASS " + label + "\n").encode() for label in tail)
            require(captures["stdout"].read_bytes() == expected, "complete ordered memo assertion inventory")
            no_query_scratch(cache)
            no_query_scratch(cache / "prepared-counterexample")
            row["state"] = "passed"
            memo_results["helper"] = {"context_before": row["context_before"], "context_after": row["context_after"],
                                      "assertion_markers": tail, "cache": physical_inventory(cache),
                                      "proof": "real verified state survives private context rename; empty state fails; finally restores original inode/bytes",
                                      "limits": "returned Bool is context branch only; PreparedRaw rejection is checked separately, not a reader-owned invalidation"}
            save()
        if "memo-helper" in active:
            run_memo_helper()
        phases = ["cold", "warm", "mixed", "restored-warm", "corrupt-repair", "missing-repair"]
        expected_counts = [(2, 0), (0, 2), (1, 1), (0, 2), (1, 1), (1, 1)]
        for kind in memo_drivers:
            root = out / ("memo-" + kind)
            cache = root / "cache"
            raw = run("memo-" + kind, ["memo-" + kind, cache, root], timeout=60)
            require(raw == b"PASS six public invocations preserve complete final artifacts and repair context\n",
                    "fixed six-invocation completion marker")
            rows, baseline_artifact, keys = [], None, None
            for phase, counts in zip(phases, expected_counts):
                report_path, artifact_path = root / (phase + ".queries"), root / (phase + ".artifact")
                require(report_path.stat().st_size <= 65536 and artifact_path.stat().st_size <= 2 * 1024**2,
                        "small fixed public memo evidence")
                report = json.loads(report_path.read_bytes())
                require(report["format"] == 1 and len(report["groups"]) == 2, "exact two-group memo population")
                require((report["inferred_groups"], report["reused_groups"]) == counts,
                        "exact cold/warm/mixed/restored/invalidation infer-hit oracle: " + kind + "/" + phase)
                current_keys = sorted(group["query_key"] for group in report["groups"])
                require(len(set(current_keys)) == 2, "distinct memo query keys")
                if keys is None:
                    keys = current_keys
                require(current_keys == keys, "same public keys across all six invocations")
                artifact_sha = digest(artifact_path.read_bytes())
                if baseline_artifact is None:
                    baseline_artifact = artifact_sha
                require(artifact_sha == baseline_artifact, "complete final artifact bytes equal cold in every phase")
                rows.append({"phase": phase, "query_report": report, "artifact_sha256": artifact_sha,
                             "report_sha256": digest(report_path.read_bytes())})
            no_query_scratch(cache)
            final_snapshot = snapshot(cache, keys)
            require(set(final_snapshot["active_records"].values()) == {"MLFBIN-QUERY-SHARED-4"},
                    "all records restored to binary shared source queries")
            require(len(final_snapshot["reachable_contexts"]) == 1, "one shared context after both repairs")
            context = cache / final_snapshot["reachable_contexts"][0]
            require(context.read_bytes() == (root / "context.original").read_bytes(), "final context exact original bytes")
            memo_results[kind] = {"phases": rows, "final_cache": final_snapshot,
                                  "mixed_legacy_scope": "A valid obsolete record is replaced by the exact current record. The following warm run reuses both groups.",
                                  "cross_invocation_scope": "all-fingerprinted warm ends verified; next corrupt/missing invocations must each infer one and hit one, not reuse global state"}
            save()

        # Additive directory-publication controls. All original 34 commands,
        # timeouts, lock probes, pair and memo handshakes remain unchanged above.
        publication = {}
        record["context_directory_publication"] = publication
        collision_cache = out / "context-directory-cache"
        if "context-directory-setup" in active:
            setup = run("context-directory-setup", ["context-directory-setup", collision_cache], timeout=60)
            marker = re.fullmatch(rb"PASS context directory setup ([0-9a-f]{64})\n", setup)
            require(marker is not None, "exact real context setup marker")
            reference = marker.group(1).decode("ascii")
            context_path = collision_cache / ("context-" + reference + ".mlfqc")
            existing = collision_cache / "existing.mlfq"
            existing_identity = small_identity(existing)
            existing_query = binary_query(existing.read_bytes())
            require(existing_query['reference'] == reference, "setup binary record really references observed context")
            require(re.fullmatch(r"[0-9a-f]{64}", existing_query["fingerprint"]), "setup result fingerprint verified")
            original_context_identity = publication_context_identity(context_path)
            original_context = context_path.read_bytes()
            binary_context(original_context, reference)
            backup = collision_cache / "context.original"
            sentinel = context_path / "retained-child"
            publication["setup"] = {"reference": reference, "record": existing_identity, "context": original_context_identity}
            save()

        if "context-directory-reject" in active:
            def install_collision():
                require(small_identity(existing) == existing_identity and
                        publication_context_identity(context_path) == original_context_identity,
                        "setup inputs stable before directory mutation")
                require(not os.path.lexists(backup), "fresh context backup")
                context_path.rename(backup)
                context_path.mkdir()
                with sentinel.open("xb") as stream:
                    stream.write(b"retain child of context destination directory\n")
                return {"directory": publication_directory_identity(context_path),
                        "sentinel": small_identity(sentinel), "existing_record": small_identity(existing),
                        "context_backup": publication_context_identity(backup), "lock": small_identity(collision_cache / ".lock")}

            protected = with_publication_lock(collision_cache, install_collision)
            publication["collision"] = {"reference": reference, "original_context": original_context_identity,
                                        "protected_before": protected}
            save()
            rejected = run("context-directory-reject", ["context-directory-reject", collision_cache], timeout=60)
            require(rejected == b"PASS context directory rejects new.mlfq\nPASS context directory rejects existing.mlfq\n",
                    "both exact public writer directory rejections")

            def verify_collision():
                actual = {"directory": publication_directory_identity(context_path),
                          "sentinel": small_identity(sentinel), "existing_record": small_identity(existing),
                          "context_backup": publication_context_identity(backup), "lock": small_identity(collision_cache / ".lock")}
                require(actual == protected, "directory collision changed a protected identity")
                require(actual["directory"]["children"] == ["retained-child"], "no context stage hidden in destination directory")
                for leaf in ["new.mlfq", "new.mlfq.new", "existing.mlfq.new", "source-context.new"]:
                    require(not os.path.lexists(collision_cache / leaf), "rejected publication left " + leaf)
                require(sorted(p.name for p in collision_cache.iterdir()) ==
                        sorted([".lock", "existing.mlfq", "context.original", context_path.name]),
                        "exact failed-publication cache node inventory")
                return actual

            publication["collision"]["protected_after"] = with_publication_lock(collision_cache, verify_collision)
            publication["collision"]["scope"] = "two real writeSourceCached calls reject; distinct attempted payload cannot create or replace record"
            save()

        stage_cache = out / "context-stage-cleanup-cache"
        if "context-stage-cleanup-failure" in active:
            stage_cache.mkdir()
            with (stage_cache / ".lock").open("xb"):
                pass
            stage = stage_cache / "source-context.new"
            stage.mkdir()
            stage_child = stage / "retained-child"
            with stage_child.open("xb") as stream:
                stream.write(b"must not recursively remove context staging directory\n")
            stage_before = {"directory": publication_directory_identity(stage),
                            "sentinel": small_identity(stage_child), "lock": small_identity(stage_cache / ".lock")}
            publication["cleanup_failure"] = {"protected_before": stage_before,
                "scope": "direct rejectSourceContextPublication helper error composition; not a natural directory after successful writeFile"}
            save()
            cleanup = run("context-stage-cleanup-failure", ["context-stage-cleanup-failure", stage_cache], timeout=60)
            require(cleanup == b"PASS context staging directory preserves publication and cleanup errors\n",
                    "exact helper primary-plus-cleanup failure")

            def verify_cleanup_failure():
                actual = {"directory": publication_directory_identity(stage),
                          "sentinel": small_identity(stage_child), "lock": small_identity(stage_cache / ".lock")}
                require(actual == stage_before, "cleanup helper changed directory, child or lock identity")
                require(sorted(p.name for p in stage_cache.iterdir()) == [".lock", "source-context.new"] and
                        actual["directory"]["children"] == ["retained-child"], "no recursive cleanup or extra stage nodes")
                return actual

            publication["cleanup_failure"]["protected_after"] = with_publication_lock(stage_cache, verify_cleanup_failure)
            save()

        if "window-helper" in active:
            run_window_controls(fixture, out, record, save)
        cache_roots = []
        if "helper" in active:
            cache_roots.append(out / "helper-cache")
        if "raw-final" in active:
            cache_roots.extend((out / "raw-final-cache", out / "raw-final-cache-inputs"))
        cache_roots.extend(out / kind / 'cache' for kind in drivers)
        cache_roots.extend(out / ('left-' + mode) / 'cache' for mode in left_modes)
        for case, directory in (("empty-stale-success", "empty-success"),
                                ("empty-directory-failure", "empty-directory-failure"),
                                ("cleanup-dual-failure", "cleanup-dual-failure"),
                                ("concurrent-a", "concurrent")):
            if case in active:
                cache_roots.append(out / directory / 'cache')
        if "memo-helper" in active:
            cache_roots.append(out / "memo-helper-cache")
        cache_roots.extend(out / ('memo-' + kind) / 'cache' for kind in memo_drivers)
        for case, directory in (("context-directory-setup", "context-directory-cache"),
                                ("context-stage-cleanup-failure", "context-stage-cleanup-cache"),
                                ("window-helper", "window-helper-cache")):
            if case in active:
                cache_roots.append(out / directory)
        record["all_cache_inventory"] = {str(root.relative_to(out)): physical_inventory(root) for root in cache_roots}
        allocated = sum(value["all_pathname_conservative_allocated_bytes"] for value in record["all_cache_inventory"].values())
        logical = sum(value["all_file_logical_bytes"] for value in record["all_cache_inventory"].values())
        record["all_cache_totals"] = {"logical": logical, "allocated": allocated, "cache_roots": len(cache_roots),
                                      "scope": "all selected private cache trees; includes every retained raw/backup/lock/rejected directory; build/capture evidence remains in outer root accounting"}
        require(logical <= 16 * 1024**2 and allocated <= 16 * 1024**2, "16 MiB complete cache budget")
        require([row['name'] for row in record['commands']] == expected_commands, "fixed selected command inventory")
        require(all(digest(Path(path).read_bytes()) == expected for path, expected in inspector_inputs.items()),
                'independent binary inspector input changed during controls')
        record["complete"] = True
        save()
        print(json.dumps({"complete": True, "commands": len(record["commands"]), "drivers": drivers}))
    except BaseException as error:
        record["error"] = type(error).__name__ + ": " + str(error)
        save()
        raise

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--lock-probe":
        independent_lock_probe(sys.argv[2:])
    else:
        main()
