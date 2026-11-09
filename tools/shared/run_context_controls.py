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

def binary_query(raw, shared=True):
    document = binary_artifact(raw, 2)
    root = binary_helpers()[1].query_payload_root(document)
    if shared:
        tag = document.nodes[root].data[0]
        if tag in (303,306):
            if tag == 306:
                key, result, reference, header, body = graph_node(document, root, tag, 5)
            else:
                reference, key, result, header, body = graph_node(document, root, tag, 5)
            fingerprint = binary_helpers()[1].verify_source_result(document)
            return {'document': document, 'reference': graph_text(document, reference),
                    'fingerprint': fingerprint, 'header': header, 'body': body}
        reference, compact, header, body = graph_node(document, root, 301, 4)
        return {'document': document, 'reference': graph_text(document, reference),
                'compact': [graph_text(document, i) for i in graph_node(document, compact, 1)],
                'header': header, 'body': body}
    key, unit = graph_node(document, root, 300, 2)
    header, body = graph_node(document, unit, 241, 2)
    return {'document': document, 'key': graph_text(document, key), 'header': header, 'body': body}

def binary_context(raw, reference):
    require(digest(raw) == reference, 'actual complete binary context SHA256')
    document = binary_artifact(raw, 1)
    declarations, = graph_node(document, document.roots[0], 244, 1)
    return document, declarations

def graph_equal(left, left_root, right, right_root, rename=None):
    """Compare complete DAG structures in linear distinct-pair work, no tree expansion.

    Optional rename permits exactly one XName identity's hint substitution;
    integer identity, constructor tags, types and all other metadata stay exact.
    """
    pending, seen, changed = [(left_root, right_root)], set(), set()
    while pending:
        a, b = pending.pop()
        if (a, b) in seen:
            continue
        seen.add((a, b)); x, y = left.nodes[a], right.nodes[b]
        if x.kind != y.kind:
            return False, changed
        if x.kind == 3:
            xtag, xs = x.data; ytag, ys = y.data
            if xtag != ytag or len(xs) != len(ys):
                return False, changed
            if rename is not None and xtag == 31:
                identity, old_hint, new_hint = rename
                if len(xs) == 2 and left.nodes[xs[0]].kind == 0 and left.nodes[xs[0]].data == identity:
                    if (right.nodes[ys[0]].kind != 0 or right.nodes[ys[0]].data != identity or
                        graph_text(left, xs[1]) != old_hint or graph_text(right, ys[1]) != new_hint):
                        return False, changed
                    changed.add(a)
                    continue
            pending.extend(zip(xs, ys))
        elif x.kind == 2:
            if left.symbols[x.data] != right.symbols[y.data]:
                return False, changed
        elif x.data != y.data:
            return False, changed
    return True, changed

def require_graph_equal(left, left_root, right, right_root, message):
    require(graph_equal(left, left_root, right, right_root)[0], message)

def require_alpha_graph(raw_query, poisoned_query, identity, old_hint, new_hint, owner):
    left, right = raw_query['document'], poisoned_query['document']
    same, changed = graph_equal(left, raw_query['body'], right, poisoned_query['body'],
                                (identity, old_hint, new_hint))
    require(same and changed, 'complete binary body changes only the source-issued XName hint')
    pending, seen, references = [raw_query['body']], set(), 0
    while pending:
        index = pending.pop()
        if index in seen:
            continue
        seen.add(index); node = left.nodes[index]
        if node.kind == 3:
            references += sum(child in changed for child in node.data[1])
            pending.extend(node.data[1])
    require(references >= 2, 'binary evidence identity occurs at its binder and a reference')
    root = raw_query['body']
    while left.nodes[root].kind == 3 and left.nodes[root].data[0] == 71:
        root = graph_node(left, root, 71, 3)[2]  # actual external parameter prefix
    bound_owner, value, result = graph_node(left, root, 75, 3)
    _, owner_hint = graph_node(left, bound_owner, 31, 2)
    require(graph_text(left, owner_hint) == owner, 'actual raw singleton declaration owns the poisoned evidence')
    binder, _, _ = graph_node(left, value, 71, 3)
    binder_id, binder_hint = graph_node(left, binder, 31, 2)
    require(left.nodes[binder_id].kind == 0 and left.nodes[binder_id].data == identity and
            graph_text(left, binder_hint) == old_hint, 'changed XName is the actual root evidence abstraction')
    constructor, arguments = graph_node(left, result, 82, 2)
    require(graph_text(left, constructor) == '()' and not graph_node(left, arguments, 1),
            'actual singleton raw root retains its unit result')

def require_contextual_unit(query, context, declarations, object_document, unit):
    header, term = graph_node(object_document, unit, 241, 2)
    full = graph_node(object_document, header, 240, 8)
    compact = graph_node(query['document'], query['header'], 240, 8)
    # Shared-query checksum covers the body alone, just like historical MLFF2;
    # a full object checksum includes its independently stored datatype prefix.
    for field in (0, 1, 2, 4, 5, 6):
        require_graph_equal(query['document'], compact[field], object_document, full[field],
                            'binary contextual header equals actual complete final interface')
    require_graph_equal(context, declarations, object_document, full[3],
                        'binary contextual declarations equal actual final header datatype context')
    body_context, body = graph_node(object_document, term, 84, 2)
    require_graph_equal(context, declarations, object_document, body_context,
                        'binary contextual declarations equal actual final body datatype context')
    require_graph_equal(query['document'], query['body'], object_document, body,
                        'complete whole-final binary payload equals actual cold target fragment')

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

def legacy_fingerprint(text):
    """Independent scalar recurrence for explicitly legacy witness checksums."""
    first, second = 0, 1
    for char in text:
        code = ord(char)
        first = (first * 65599 + code) % 2147483647
        second = (second * 131 + code) % 2147483629
    return str(first) + '-' + str(second)

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



DECODER_DIFFERENTIAL_RIGHT = [
    "writer-raw41", "writer-second-raw41", "writer-box-context",
    "codec-raw42-original-key", "codec-raw42-other-key", "unicode-scalar-framing",
]
DECODER_DIFFERENTIAL_LEFT = [
    *["compact-field-" + name for name in
      ["tag", "crate", "compiler", "members", "bindings", "prepared", "contracts", "scopes"]],
    "compact-leading-zero-length", "compact-truncated", "compact-trailing-bytes",
    "compact-seven-fields", "compact-nine-fields", "compact-empty", "compact-nondigit-length",
    "unicode-utf8-length", "unicode-utf16-length", "unicode-short-scalar-length",
    "full-key-leading-zero-length", "full-key-truncated", "full-key-trailing-bytes",
    "full-key-eight-fields", "full-key-ten-fields", "full-key-wrong-tag",
    "single-expected-context-field", "same-context-other-record-key", "same-context-other-expected-key",
    "actual-datatypes-mismatch", "box-layout-mismatch", "context-carrier-mismatch",
    "context-carrier-wrong-tag", "context-carrier-leading-zero-length", "context-carrier-truncated",
    "context-carrier-extra-field", "record-wrong-format", "record-invalid-reference",
    "actual-digest-mismatch", "record-leading-zero-length", "record-truncated", "record-trailing-bytes",
    "record-three-fields", "record-five-fields", "payload-empty", "owner-mismatch", "binding-mismatch",
    "declaration-mismatch", "priority-framing-before-key", "priority-truncation-before-key",
    "priority-record-shape-before-key", "priority-reference-before-key", "priority-key-before-context",
    "priority-datatypes-before-compact", "priority-context-before-compact",
    "priority-compact-framing-before-payload", "priority-key-mismatch-before-payload",
    "priority-payload-before-owner", "priority-owner-before-declarations",
]


def decoder_seed_snapshot(cache):
    # This command reads this run's original helper-cache only, after all 37
    # preceding commands. Helper's terminal source has exactly these six
    # records, two canonical contexts and its existing zero regular lock.
    # No added tree, seed write, glob-selected record, old P cache or W cache.
    directory = publication_directory_identity(cache)
    source_records = ["record.mlfq", "second.mlfq", "box.mlfq"]
    record_leaves = source_records + ["pooled.mlfq", "fallback.mlfq", "legacy2.mlfq"]
    selected, references = {}, {}
    expected_compact = ["MLF-SOURCE-CRATE-QUERY-7", "crate:α😀", "compiler", "member:opaque:😀",
                        "bindings", "source-group", "observed-contracts", "scope-table:α😀"]
    fields = ["st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns", "st_blocks"]

    def sample(path, cap):
        before = path.lstat()
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= cap,
                "bounded single-link decoder seed file")
        if path.name == ".lock":
            # Never reopen/close this inode under the parent's POSIX lockf.
            require(before.st_size == 0, "decoder seed existing zero regular lock")
            raw = b""
        else:
            raw = path.read_bytes()
        after = path.lstat()
        require(len(raw) == before.st_size and all(getattr(before, f) == getattr(after, f) for f in fields),
                "decoder seed changed while sampling")
        return {**{f: getattr(before, f) for f in fields}, "sha256": digest(raw)}, raw

    for leaf in source_records:
        identity, raw = sample(cache / leaf, 65536)
        record = binary_query(raw)
        compact = expected_compact.copy()
        if leaf == "second.mlfq":
            compact[1] = "another-crate"
        require(record['compact'] == compact, "fixed full non-context binary seed key fields")
        references[leaf] = record['reference']
        selected[leaf] = identity
    require(references["record.mlfq"] == references["second.mlfq"] and
            references["box.mlfq"] != references["record.mlfq"], "exact two helper seed contexts")
    context_leaves = sorted({"context-" + value + ".mlfqc" for value in references.values()})
    expected_leaves = sorted([".lock", *record_leaves, *context_leaves])
    require(directory["children"] == expected_leaves and len(expected_leaves) == 9,
            "exact helper terminal nine-file population")
    # Preserve the original individual and aggregate cache limit. Only the
    # three decoder record reads use 64KiB and the two context reads 128KiB.
    require(sum((cache / leaf).lstat().st_size for leaf in expected_leaves) <= 16 * 1024**2,
            "decoder seed remains inside original complete cache cap")
    identities = {}
    for leaf in expected_leaves:
        cap = 128 * 1024 if leaf in context_leaves else 65536 if leaf in source_records or leaf == ".lock" else 16 * 1024**2
        identity, raw = sample(cache / leaf, cap)
        identities[leaf] = identity
        if leaf in selected:
            require(identity == selected[leaf], "fixed decoder record stable across seed checks")
        if leaf in context_leaves:
            binary_context(raw, leaf[8:-6])
        elif leaf in record_leaves and leaf not in source_records:
            binary_query(raw, shared=(leaf == 'pooled.mlfq'))
    require(publication_directory_identity(cache) == directory, "decoder seed directory stable while read")
    return {"directory": directory, "files": identities, "references": references,
            "source_record_count": 3, "context_count": 2, "all_regular_files": 9,
            "identity_scope": "dev/ino/mode/nlink/size/mtime/ctime/blocks/full SHA; atime deliberately excluded"}


WINDOW_HIDDEN_MARKERS = [
    'alternating contexts reuse without files', 'MRU promotion survives ninth insertion',
    'ninth insertion evicts least recent route', 'oversized input prefix hit returns only eight',
    'oversized input ninth entry is ignored', 'different reference is isolated',
    'different directory is isolated', 'independently verified other directory reuses',
    'encoded guard refuses hidden context reuse',
    *[name + ' guard refuses hidden context reuse' for name in ['kind', 'constructor', 'field']],
    'alpha structural guard refuses hidden context reuse',
    'legacy CACHE1 and CACHE2 clear all entries with exact raw', 'malformed record clears all entries',
    'unsafe reference clears all entries', 'malformed full key clears all entries',
    'complete key mismatch clears after reuse', 'malformed compact key clears before lookup',
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
        require(query['reference'] == reference and query['compact'] == compact,
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


def session_window_snapshot(cache):
    current = sorted(p.name for p in cache.iterdir() if re.fullmatch(r'[0-9a-f]{64}\.mlfq', p.name))
    carriers = sorted(p.name for p in cache.iterdir() if re.fullmatch(r'context-[0-9a-f]{64}\.mlfqc', p.name))
    require(1 <= len(current) <= 16 and 1 <= len(carriers) <= len(current), 'bounded real Session cache population')
    directories = {'.': publication_directory_identity(cache),
                   'retained-raw': publication_directory_identity(cache / 'retained-raw')}
    require(directories['.']['children'] == sorted(['.lock', 'retained-raw', *current, *carriers]) and
            directories['retained-raw']['children'] == current, 'entire cold/terminal cache namespace accounted')
    files, referenced = {}, set()
    for name in ['.lock', *current, *carriers, *['retained-raw/' + n for n in current]]:
        identity, raw = window_sample(cache / name, 65536 if name == '.lock' else 2 * 1024**2)
        files[name] = identity
        if name in current:
            query = binary_query(raw)
            require(query['fingerprint']+'.mlfq'==name, 'real session record input fingerprint')
            referenced.add('context-' + query['reference'] + '.mlfqc')
            _, retained = window_sample(cache / 'retained-raw' / name, 2 * 1024**2)
            require(raw == retained, 'every original raw record independently equal retained cold copy')
        elif name in carriers:
            binary_context(raw, name[8:-6])
            require(identity['sha256'] == name[8:-6],
                    'every actual Session binary context canonical and exact-SHA bound')
    require(referenced == set(carriers), 'all actual Session context files reached by real records')
    logical = sum(v['bytes'] for v in files.values())
    allocated = sum(v['blocks'] * 512 for v in files.values()) + sum(v['blocks'] * 512 for v in directories.values())
    require(logical <= 16 * 1024**2 and allocated <= 16 * 1024**2, 'original complete cache budget still applies')
    return {'files': files, 'directories': directories, 'records': current, 'contexts': carriers,
            'logical': logical, 'allocated': allocated}


def session_window_audit(root, leaf, cold_snapshot):
    cache = root / 'cache'
    inventory_id, inventory_raw = window_sample(root / 'target.inventory', 2 * 1024**2)
    target = unpack(inventory_raw.decode('utf-8'))
    require(len(target) == 10 and target[0] == leaf and re.fullmatch(r'[0-9a-f]{64}\.mlfq', leaf),
            'actual target inventory and fixed released marker')
    leaf, group, packed_names, reference, compact, payload, raw_iface, raw_object, final_iface, final_object = target
    wanted = unpack(packed_names)
    require(len(wanted) == 1 and raw_object != final_object and re.fullmatch('[0-9a-f]{64}', reference),
            'actual singleton raw/final counterexample')
    plan_id, plan_raw = window_sample(root / 'source-plan.inventory', 65536)
    planned = {}
    for value in unpack(plan_raw.decode('utf-8')):
        fields = unpack(value)
        require(len(fields) == 2 and fields[0] not in planned, 'complete unique parsed source-plan groups')
        planned[fields[0]] = unpack(fields[1])
    require(len(planned) == 4 and planned.get(group) == wanted, 'fixed four-group actual parsed source owns negative target')
    rows, baseline, baseline_graphs, stable_groups, keys = {}, None, None, None, None
    counts = {'cold': (len(planned), 0), 'warm': (0, len(planned)),
              'cache3-repair': (1, len(planned) - 1), 'cache1-repair': (1, len(planned) - 1),
              'query-support': (0, len(planned))}
    for phase in ['cold', 'query-support', 'warm', 'cache3-repair', 'cache1-repair']:
        rid, report_raw = window_sample(root / (phase + '.queries'), 65536)
        report = json.loads(report_raw)
        require(report['format'] == 1 and report['crate'] == 'session-window-raw' and
                len(report['groups']) == len(planned) and
                {g['id']: g['members'] for g in report['groups']} == planned and
                (report['inferred_groups'], report['reused_groups']) == counts[phase],
                'exact Session/support parsed population and inference/hit counts')
        current = [{k: g[k] for k in ['id', 'members', 'semantic_fingerprint', 'query_key']} for g in report['groups']]
        current_keys = [g['query_key'] for g in report['groups']]
        require(len(set(current_keys)) == len(planned) and all(re.fullmatch('[0-9a-f]{64}', k) for k in current_keys),
                'distinct canonical actual source-query keys')
        for g in report['groups']:
            expected_hit = phase != 'cold' and not (phase in ['cache3-repair', 'cache1-repair'] and g['id'] == group)
            require(g['cached'] is expected_hit, 'only the actual poisoned group may reinfer')
        if stable_groups is None:
            stable_groups, keys = current, current_keys
        require(current == stable_groups and current_keys == keys, 'all full group identities/keys/semantic hashes stable')
        row = {'report': report, 'report_identity': rid}
        if phase != 'query-support':
            iid, interface = window_sample(root / (phase + '.interface'), 2 * 1024**2)
            oid, obj = window_sample(root / (phase + '.object'), 2 * 1024**2)
            if baseline is None:
                baseline = (interface, obj)
                baseline_graphs = (binary_artifact(interface, 3), binary_artifact(obj, 4))
            require((interface, obj) == baseline, 'all actual complete Session interface/object bytes equal')
            # Exact full-byte equality permits reusing this local independent
            # inspection; do not spend the unchanged live-owner deadline on
            # reparsing the identical formal graph for every phase.
            interface_graph, object_graph = baseline_graphs
            _, embedded_interface, _ = graph_node(object_graph, object_graph.roots[0], 243, 3)
            require_graph_equal(interface_graph, interface_graph.roots[0], object_graph, embedded_interface,
                                'actual binary object contains the exact standalone interface fields')
            row.update(interface_identity=iid, object_identity=oid,
                       binary_interface=interface_graph.accounting(), binary_object=object_graph.accounting())
        rows[phase] = row
    require(any(g['id'] == group and g['query_key'] + '.mlfq' == leaf for g in rows['cold']['report']['groups']),
            'poison filename binds actual target QueryReport key')
    originals_id, originals_raw = window_sample(root / 'cold-records.inventory', 65536)
    originals = unpack(originals_raw.decode('utf-8'))
    require(originals == sorted(k + '.mlfq' for k in keys) and len(set(originals)) == len(planned),
            'every cold raw record preserved')
    require(sorted(p.name for p in (cache / 'retained-raw').iterdir()) == originals and
            sorted(p.name for p in cache.iterdir() if p.suffix == '.mlfq') == originals,
            'exact original/current raw-record path populations')
    raw_rows = {}
    for name in originals:
        retained_id, retained = window_sample(cache / 'retained-raw' / name, 2 * 1024**2)
        current_id, current = window_sample(cache / name, 2 * 1024**2)
        require(current == retained, 'complete original raw bytes recovered after both poison repairs')
        raw_rows[name] = {'retained': retained_id, 'current': current_id, 'full_bytes_equal': True}
    carrier_id, carrier_raw = window_sample(cache / ('context-' + reference + '.mlfqc'), 2 * 1024**2)
    context_graph, declarations = binary_context(carrier_raw, reference)
    compact_fields = unpack(compact)
    require(carrier_id['sha256'] == reference and len(compact_fields) == 8 and
            compact_fields[0] == 'MLF-SOURCE-CRATE-QUERY-7', 'real binary target carrier and complete compact key')
    full_key = source_key_from_binary(context_graph, declarations, compact_fields)
    require(digest(full_key.encode('utf-8')) + '.mlfq' == leaf, 'unaltered complete source-key filename')
    original_id, original = window_sample(root / 'target.original.mlfq', 2 * 1024**2)
    poison3_id, poison3 = window_sample(root / 'target.poisoned-cache3.mlfq', 2 * 1024**2)
    poison1_id, poison1 = window_sample(root / 'target.poisoned-cache1.mlfq', 2 * 1024**2)
    original_query = binary_query(original)
    poison_query = binary_query(poison3)
    c1 = unpack(poison1.decode('utf-8', 'strict'))  # explicitly historical text branch
    require(original_query['reference'] == poison_query['reference'] == reference and
            original_query['fingerprint'] == poison_query['fingerprint'] == digest(full_key.encode()),
            'binary poison preserves actual context reference and all eight key fields')
    alpha_id, alpha_raw = window_sample(root / 'alpha-slot.inventory', 2 * 1024**2)
    alpha = unpack(alpha_raw.decode('utf-8'))
    require(len(alpha) == 7, 'complete actual alpha-slot identity and checked object witness')
    old_hint, new_hint, binder_id, old_token, new_token, poison_iface, poison_object = alpha
    require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', old_hint) and new_hint == old_hint + 'WindowPoison' and
            re.fullmatch(r'-?(0|[1-9][0-9]*)', binder_id) and old_token == old_hint + '_' + binder_id and
            new_token == new_hint + '_' + binder_id, 'same actual binder identity; only evidence hint changes')
    raw_header, poison_header = unpack(raw_iface), unpack(poison_iface)
    raw_object_fields, poison_object_fields = unpack(raw_object), unpack(poison_object)
    require(len(raw_header) == len(poison_header) == 8 and raw_header[:7] == poison_header[:7] and
            len(raw_object_fields) == len(poison_object_fields) == 4 and
            raw_object_fields[:2] == poison_object_fields[:2] == ['MLFO-1', group] and
            raw_object_fields[2] == poison_object_fields[2],
            'complete checked alpha raw interface metadata/types/owner unchanged except checksum')
    # MLFO-1 field2 fingerprints interface fields0..6, unchanged above;
    # MLFI-4 field7 fingerprints the term body and is legitimately refreshed.
    token = re.compile(r'(?<![A-Za-z0-9_])' + re.escape(old_token) + r'(?![A-Za-z0-9_])')
    def alpha_only(before, after):
        require(len(token.findall(before)) >= 2 and new_token not in before and
                token.sub(new_token, before) == after,
                'independent complete body differs only at actual evidence binder and all its references')
    alpha_only(raw_object_fields[3], poison_object_fields[3])
    raw_payload = unpack(payload)
    require(original == (cache / 'retained-raw' / leaf).read_bytes() and poison3 != original and
            c1 == ['MLF-QUERY-CACHE-1', full_key, poison_iface, poison_object] and poison_object != final_object,
            'two poison codecs carry only alpha raw provenance change, not wholesale final or envelope corruption')
    poison_payload_id, poison_payload_raw = window_sample(root / 'target.poisoned-payload.legacy', 2 * 1024**2)
    poison_payload = unpack(poison_payload_raw.decode('utf-8', 'strict'))
    require(len(raw_payload) == len(poison_payload) == 3 and raw_payload[0] == poison_payload[0] == 'MLFF-2' and
            unpack(raw_payload[1])[:7] == unpack(poison_payload[1])[:7],
            'separate legacy contextual witnesses preserve complete interface/types except checksum')
    alpha_only(raw_payload[2], poison_payload[2])
    require(' = \\(' + old_token + ' : ' in raw_payload[2], 'changed identity is the actual root evidence abstraction')
    require(pack(poison_payload).encode('utf-8') == poison_payload_raw and pack(c1).encode('utf-8') == poison1,
            'canonical legacy poison witnesses, not malformed-envelope misses')
    raw_contextual_header, poison_contextual_header = unpack(raw_payload[1]), unpack(poison_payload[1])
    require(len(raw_contextual_header) == len(poison_contextual_header) == 8 and
            raw_contextual_header[7] == legacy_fingerprint(raw_payload[2]) and
            poison_contextual_header[7] == legacy_fingerprint(poison_payload[2]) and
            raw_header[7] == legacy_fingerprint(raw_object_fields[3]) and
            poison_header[7] == legacy_fingerprint(poison_object_fields[3]) and
            raw_object_fields[2] == legacy_fingerprint(pack(raw_header[:7])) and
            poison_object_fields[2] == legacy_fingerprint(pack(poison_header[:7])),
            'independent complete legacy body and interface checksums; contextual and full scope kept distinct')
    original_header = graph_node(original_query['document'], original_query['header'], 240, 8)
    binary_poison_header = graph_node(poison_query['document'], poison_query['header'], 240, 8)
    for field in range(7):
        require_graph_equal(original_query['document'], original_header[field],
                            poison_query['document'], binary_poison_header[field],
                            'binary alpha poison preserves every metadata/type field except body checksum')
    require(graph_text(original_query['document'], original_header[0]) == group and
            graph_text(poison_query['document'], binary_poison_header[0]) == group and
            graph_text(original_query['document'], original_header[7]) == raw_contextual_header[7] and
            graph_text(poison_query['document'], binary_poison_header[7]) == poison_contextual_header[7],
            'binary metadata binds actual owner and complete contextual body fingerprints')
    require_alpha_graph(original_query, poison_query, int(binder_id), old_hint, new_hint, wanted[0])
    wholesale3_id, wholesale3 = window_sample(root / 'target.wholesale-cache3.mlfq', 2 * 1024**2)
    wholesale1_id, wholesale1 = window_sample(root / 'target.wholesale-cache1.mlfq', 2 * 1024**2)
    wholesale_query = binary_query(wholesale3)
    w1 = unpack(wholesale1.decode('utf-8', 'strict'))
    require(wholesale_query['reference'] == reference and wholesale_query['fingerprint'] == digest(full_key.encode()) and
            not graph_equal(wholesale_query['document'], wholesale_query['body'],
                            original_query['document'], original_query['body'])[0] and
            not graph_equal(wholesale_query['document'], wholesale_query['body'],
                            poison_query['document'], poison_query['body'])[0] and
            w1 == ['MLF-QUERY-CACHE-1', full_key, final_iface, final_object] and
            pack(w1).encode('utf-8') == wholesale1,
            'separate whole-final witnesses retain actual final fragment and original envelope')
    wholesale_payload_id, wholesale_payload_raw = window_sample(root / 'target.wholesale-payload.legacy', 2 * 1024**2)
    wholesale_payload = unpack(wholesale_payload_raw.decode('utf-8', 'strict'))
    require(len(wholesale_payload) == 3 and wholesale_payload[0] == 'MLFF-2' and
            pack(wholesale_payload).encode('utf-8') == wholesale_payload_raw,
            'separate canonical whole-final legacy contextual witness')
    wholesale_legacy_header = unpack(wholesale_payload[1])
    wholesale_binary_header = graph_node(wholesale_query['document'], wholesale_query['header'], 240, 8)
    require(len(wholesale_legacy_header) == 8 and wholesale_legacy_header[1] == group and
            wholesale_legacy_header[7] == legacy_fingerprint(wholesale_payload[2]) and
            graph_text(wholesale_query['document'], wholesale_binary_header[7]) == wholesale_legacy_header[7],
            'whole-final binary shared checksum covers exactly the complete contextual body')
    # Independently bind the whole-final contextual witness to the actual cold
    # CrateObject pool, not merely to an author-created expected payload.
    cold_object = baseline_graphs[1]
    legacy_flag, crate_interface, fragment_list = graph_node(cold_object, cold_object.roots[0], 243, 3)
    graph_node(cold_object, legacy_flag, 6, 0)
    crate_fields = graph_node(cold_object, crate_interface, 242, 13)
    require(graph_text(cold_object, crate_fields[0]) == 'session-window-raw', 'actual complete cold binary CrateObject identity')
    final_candidates = []
    for unit in graph_node(cold_object, fragment_list, 1):
        header, _ = graph_node(cold_object, unit, 241, 2)
        fields = graph_node(cold_object, header, 240, 8)
        if graph_text(cold_object, fields[0]) == group:
            final_candidates.append(unit)
    require(len(final_candidates) == 1, 'exactly one actual cold target fragment in binary shared table')
    require_contextual_unit(wholesale_query, context_graph, declarations, cold_object, final_candidates[0])
    wholesale_rejections_id, wholesale_rejections = window_sample(root / 'wholesale-rejection.inventory', 65536)
    require(unpack(wholesale_rejections.decode('utf-8')) == ['cached dependency parameter mismatch'] * 2,
            'both wholesale-final codecs must fail generic envelope before PreparedRaw')
    rejection_id, rejection = window_sample(root / 'prepared-rejection.txt', 65536)
    legacy_rejection_id, legacy_rejection = window_sample(root / 'prepared-rejection-legacy.txt', 65536)
    require(rejection == legacy_rejection == b'raw source evidence prefix identity mismatch',
            'both generic-accepted alpha codecs must fail actual PreparedRaw at source-issued identity boundary')
    for phase in ['interface', 'object']:
        require((root / ('probe.mlfci' if phase == 'interface' else 'probe.mlfco')).read_bytes() ==
                (root / ('cache1-repair.' + phase)).read_bytes(), 'actual final public output matches saved full artifact')
    no_query_scratch(cache)
    require(not os.path.lexists(cache / 'source-context.new'), 'Session repair leaves no context stage')
    final_snapshot = session_window_snapshot(cache)
    require(cold_snapshot['records'] == final_snapshot['records'] == originals and
            cold_snapshot['contexts'] == final_snapshot['contexts'] and
            set(cold_snapshot['files']) == set(final_snapshot['files']), 'same entire raw/context/lock/retained namespace')
    for name, identity in cold_snapshot['files'].items():
        current_identity = final_snapshot['files'][name]
        if name == leaf:
            require(all(identity[k] == current_identity[k] for k in ['bytes', 'sha256']), 'target full original raw restored')
        else:
            require(identity == current_identity, 'every non-target record/context/retained copy/lock full identity unchanged')
    for name, identity in cold_snapshot['directories'].items():
        require(all(identity[k] == final_snapshot['directories'][name][k] for k in ['device', 'inode', 'mode', 'links']),
                'original Session cache directories preserved; staging may change directory times')
    return {'plan_identity': plan_id, 'parsed_groups': planned, 'target_inventory_identity': inventory_id,
            'target_group': group, 'target_names': wanted, 'target_leaf': leaf, 'target_reference': reference,
            'phases': rows, 'original_records_identity': originals_id, 'raw_records': raw_rows,
            'original_target': original_id, 'poison_cache3': poison3_id, 'poison_cache1': poison1_id,
            'prepared_rejection': rejection_id, 'legacy_prepared_rejection': legacy_rejection_id, 'target_context': carrier_id,
            'alpha_slot': alpha_id, 'whole_final_cache3': wholesale3_id, 'whole_final_cache1': wholesale1_id,
            'poisoned_payload_legacy_evidence': poison_payload_id,
            'whole_final_payload_legacy_evidence': wholesale_payload_id,
            'binary_graph_checks': {'original': original_query['document'].accounting(),
                                    'alpha_poison': poison_query['document'].accounting(),
                                    'whole_final': wholesale_query['document'].accounting(),
                                    'actual_cold_object': cold_object.accounting(),
                                    'full_typed_fields_and_alpha_identity_compared': True},
            'whole_final_rejections': wholesale_rejections_id,
            'cache': snapshot(cache, keys), 'cold_full_identity': cold_snapshot, 'terminal_full_identity': final_snapshot,
            'alpha_raw_generic_right_and_prepared_left_asserted_by_real_fixture': True,
            'whole_final_generic_left_asserted_by_real_fixture': True,
            'scope': 'four actual Session compileSpecFile calls plus one all-hit public Query support call. Wholesale final is an envelope-negative witness; alpha-only real raw provenance poison is dual generic Right then actual PreparedRaw Left. No fake PreparedGroup or direct observed multi-entry worker reset count'}


def run_added_window_controls(fixture, out, record, save, include_session=True):
    window_cache = out / 'window-helper-cache'
    session_root = out / 'window-session-raw'
    session_cache = session_root / 'cache'
    evidence = {'helper': {}}
    if include_session:
        evidence['session_prepared_raw'] = {}
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
    run_window_owned(fixture, out, record, save, 'window-helper', ['window-helper', window_cache], window_dialogue)
    if not include_session:
        return window_cache, None
    def session_dialogue(owner, wait_marker, ack, row, started):
        # Both computations and both10s parent audits share the absolute case60.
        _, cold_output = wait_marker(b'SESSION-RAW-COLD', rb'SESSION-RAW-COLD\n', phase_seconds=60)
        cold_started = time.monotonic()
        cold_snapshot = session_window_snapshot(session_cache)
        evidence['session_prepared_raw']['cold_full_identity'] = cold_snapshot
        require(time.monotonic() < min(started + 60, cold_started + 10), 'cold audit/ACK within case60 and10s barrier')
        save(); ack(b'SESSION-RAW-COLD-ACK\n', cold_started + 10)
        prefix = cold_output + b'SESSION-RAW-RELEASED '
        matched, released_output = wait_marker(prefix, re.escape(prefix) + rb'([0-9a-f]{64}\.mlfq)\n', phase_seconds=60)
        audit_started = time.monotonic()
        value = session_window_audit(session_root, matched.group(1).decode('ascii'), cold_snapshot)
        value['live_release_probe'] = live_window_release_probe(owner, session_cache / '.lock')
        require(time.monotonic() < min(started + 60, audit_started + 10), 'terminal audit/ACK within case60 and10s barrier')
        value['complete'] = True
        evidence['session_prepared_raw'] = value
        save(); ack(b'SESSION-RAW-RELEASED-ACK\n', audit_started + 10)
        return released_output + b'PASS actual Session whole-final generic Left and alpha raw generic Right PreparedRaw Left; both repairs preserve final and raw bytes\n'
    run_window_owned(fixture, out, record, save, 'session-window-raw-final',
                     ['session-window-raw-final', session_cache, session_root], session_dialogue)
    return window_cache, session_cache

def canonical_session_builtin_pair(prefix):
    """Pin the already produced session-cold dependency; never generate/copy it here."""
    records, documents = {}, {}
    for suffix, schema in ((".mlfci", 3), (".mlfco", 4)):
        path = Path(str(prefix) + suffix)
        before = path.lstat()
        require(path.resolve(strict=True) == path and stat.S_ISREG(before.st_mode)
                and before.st_nlink == 1 and before.st_size <= 2 * 1024**2,
                "bounded real canonical session builtin pair")
        raw = path.read_bytes()
        after = path.lstat()
        stamp = lambda x: (x.st_dev, x.st_ino, x.st_mode, x.st_nlink, x.st_size,
                           x.st_mtime_ns, x.st_ctime_ns, x.st_blocks)
        require(stamp(before) == stamp(after) and len(raw) == before.st_size,
                "session builtin changed during complete read")
        records[str(path)] = {"sha256": digest(raw), "bytes": before.st_size,
            "device": before.st_dev, "inode": before.st_ino, "mode": before.st_mode,
            "links": before.st_nlink, "mtime_ns": before.st_mtime_ns,
            "ctime_ns": before.st_ctime_ns, "blocks": before.st_blocks}
        documents[suffix] = binary_artifact(raw, schema)
    meta, obj = documents[".mlfci"], documents[".mlfco"]
    iface = graph_node(meta, meta.roots[0], 242, 13)
    require(graph_text(meta, iface[0]) == "mlf:builtin-shared-haskell-v1:13"
            and graph_node(meta, iface[1], 1) == ()
            and sorted(graph_text(meta, n) for n in graph_node(meta, iface[2], 1)) == ["MLF.Primitive", "Prelude"]
            and graph_text(meta, iface[10]) == "", "canonical ABI11 builtin identity/ownership/dependencies")
    _, object_iface, fragments = graph_node(obj, obj.roots[0], 243, 3)
    units = graph_node(obj, fragments, 1)
    require(bool(units), "canonical builtin has a nonempty fully typed fragment list")
    require_graph_equal(meta, meta.roots[0], obj, object_iface, "full canonical builtin interface/object binding")
    # The actual producer splits canonical builtin declarations into SCC units.
    # Do not guess a magic count: derive the complete export inventory from the
    # independently typed crate interface and verify every unit and type below.
    expected_bindings = {}
    for binding in graph_node(meta, iface[9], 1):
        name, ty = graph_node(meta, binding, 2, 2)
        text = graph_text(meta, name)
        require(text not in expected_bindings, "unique canonical crate export")
        expected_bindings[text] = ty
    def declarations_by_name(document, index):
        declarations = {}
        for declaration in graph_node(document, index, 1):
            node = document.nodes[declaration]
            require(node.kind == 3 and node.data[0] in (26, 27) and len(node.data[1]) == 3,
                    "complete typed datatype declaration")
            name = graph_text(document, node.data[1][0])
            require(name not in declarations, "unique canonical datatype declaration name")
            declarations[name] = declaration
        return declarations
    crate_declarations = declarations_by_name(meta, iface[8])
    unit_prefix = "MLF.Split.C" + "".join(str(ord(c)) + "_" for c in graph_text(meta, iface[0])) + ".SCC"
    seen_bindings, inventory = set(), []
    for index, raw_unit in enumerate(units):
        unit_iface, term = graph_node(obj, raw_unit, 241, 2)
        fields = graph_node(obj, unit_iface, 240, 8)
        name = graph_text(obj, fields[0])
        require(name == unit_prefix + str(index), "complete ordered canonical SCC inventory")
        require(all(not graph_node(obj, fields[k], 1) for k in (1, 2, 4, 5)),
                "canonical split unit has no forged dependency/entity/class/instance fields")
        unit_declarations = declarations_by_name(obj, fields[3])
        require(set(unit_declarations) == set(crate_declarations), "exact canonical datatype declaration name set")
        for declaration_name in crate_declarations:
            require_graph_equal(meta, crate_declarations[declaration_name], obj, unit_declarations[declaration_name],
                                "complete canonical datatype declaration graph by name; order is not semantic")
        exports = []
        for binding in graph_node(obj, fields[6], 1):
            key, ty = graph_node(obj, binding, 2, 2)
            text = graph_text(obj, key)
            require(text in expected_bindings and text not in seen_bindings,
                    "each canonical export belongs to exactly one SCC unit")
            require_graph_equal(meta, expected_bindings[text], obj, ty, "exact canonical export type")
            seen_bindings.add(text); exports.append(text)
        require(bool(exports), "canonical declaration SCC has at least one export")
        inventory.append({"name": name, "exports": exports})
    require(seen_bindings == set(expected_bindings), "all canonical exports represented by complete SCC inventory")
    return {"files": records, "fragments": inventory}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument('--legacy-query-only', action='store_true',
                        help='Retain all legacy Query/codec controls; the graph CLI has its own session controls.')
    args = parser.parse_args()
    drivers = ['query'] if args.legacy_query_only else ['query', 'session']
    left_modes = ['legacy', 'source'] if args.legacy_query_only else ['legacy', 'source', 'session']
    fixture, out = args.fixture.absolute(), args.output.absolute()
    require(fixture.is_file() and fixture.resolve() == fixture, "qualified regular fixture path")
    require(not out.exists() and out.parent.is_dir() and out.parent.resolve() == out.parent, "fresh real output")
    inspector_inputs = binary_helpers()[2]
    out.mkdir()
    record = {"complete": False, "fixture_sha256": digest(fixture.read_bytes()), "commands": [], "drivers": {},
              "legacy_query_only": args.legacy_query_only,
              "binary_inspector_inputs": inspector_inputs,
              "format_migration": {
                  "default_query_context_schemas": [2, 1], "formal_interface_object_schemas": [3, 4],
                  "legacy_differential_cases_unchanged": 63,
                  "one_format_specific_oracle_change": {
                      "old_marker": "malformed compact key clears after reuse",
                      "new_marker": "malformed compact key clears before lookup",
                      "old_memo_reused": True, "new_memo_reused": False,
                      "reason": "malformed binary typed compact fields are rejected before context memo lookup; window is cleared"}},
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
        argv = ["query", cache, root / "final.objects", value] if kind == "query" else ["session", cache, root, value]
        raw = run(name, argv)
        report = json.loads(raw)
        require(report["format"] == 1 and len(report["groups"]) > 0, "actual query report")
        no_query_scratch(cache)
        hashes = [x["query_key"] for x in report["groups"]]
        require(len(hashes) == len(set(hashes)), "distinct query records")
        result_files = [root / "final.objects"] if kind == "query" else [root / "probe.mlfci", root / "probe.mlfco"]
        artifacts = {p.name: digest(p.read_bytes()) for p in result_files}
        measured = {"query_report": report, "cache": snapshot(cache, hashes), "artifact_sha256": artifacts}
        if kind == 'session':
            measured['binary_artifacts'] = {p.name: binary_artifact(p.read_bytes(), schema).accounting()
                                            for p, schema in zip(result_files, (3, 4))}
        if kind == "query":
            evidence = (root / "final.objects.legacy-bytes").read_bytes()
            rows = unpack(evidence.decode("utf-8"))
            require(rows and rows[0] == "MLF-QUERY-LEGACY-BYTES-1", "legacy accounting schema")
            sizes = {}
            for row in rows[1:]:
                key, size = unpack(row)
                require(key in hashes and key not in sizes and size.isascii() and size.isdecimal(), "legacy accounting record")
                sizes[key] = int(size)
                require(str(sizes[key]) == size and sizes[key] > 0, "canonical legacy byte count")
            require(set(sizes) == set(hashes), "complete active legacy comparison")
            measured["legacy_self_contained_comparison"] = {
                "per_record_utf8_bytes": sizes, "total_utf8_bytes": sum(sizes.values()),
                "new_complete_reachable_binary_and_legacy_bytes": measured["cache"]["reachable_logical_bytes"],
                "evidence_sha256": digest(evidence),
                "semantic_roundtrip_verified_by_fixture": True,
                "scope": "synthetic Query empty datatype context only; old bytes constructed in memory",
                "not_a_physical_baseline_or_io_measurement": True,
            }
        return measured
    try:
        helper = run("helper", ["helper", out / "helper-cache"])
        require(helper.endswith(b"PASS helper CACHE1/CACHE2/CACHE3, complete-key and corrupt-input controls\n"), "helper terminal marker")
        raw_final = run("raw-final", ["raw-final", out / "raw-final-cache"])
        require(raw_final == b"PASS final payload cannot masquerade as raw source cache\n", "raw/final terminal marker")
        for kind in drivers:
            root = out / kind
            root.mkdir()
            cache = root / "cache"
            sentinels = seed_cache(cache)
            cold = driver(kind, cache, root, "41", kind + "-cold")
            if kind == "session":
                require(not record.get("left_session_builtin_dependency"), "fresh session builtin provenance")
                record["left_session_builtin_dependency"] = {
                    "producer_command": "session-cold",
                    "cold_pair": canonical_session_builtin_pair(out / "session/builtin"),
                    "before_live_probe": None, "after_live_probe": None}
                save()
            require(cold["query_report"]["inferred_groups"] > 0 and cold["query_report"]["reused_groups"] == 0, "cold actually infers")
            warm = driver(kind, cache, root, "41", kind + "-warm")
            require(warm["query_report"]["inferred_groups"] == 0 and warm["query_report"]["reused_groups"] == cold["query_report"]["inferred_groups"], "warm actually hits")
            require(warm["artifact_sha256"] == cold["artifact_sha256"], "final artifacts exact cold/warm")
            require(warm["cache"]["reachable_contexts"], "production cache uses shared representation")
            for n in cold["cache"]["reachable_contexts"]:
                require(cold["cache"]["files"][n] == warm["cache"]["files"][n], "warm context unchanged")
            mixed = None
            before_change = warm
            if kind == "query":
                require(len(cold["cache"]["active_records"]) == 2 and len(cold["cache"]["reachable_contexts"]) == 1, "two groups share one context")
                legacy = run("query-install-legacy", ["legacy-one", cache])
                require(legacy == b"PASS fixture replaced one record with valid old CACHE1\n", "legacy injection marker")
                mixed_before = snapshot(cache, [g["query_key"] for g in cold["query_report"]["groups"]])
                mixed = driver(kind, cache, root, "41", "query-mixed-old-new")
                require(mixed["query_report"]["inferred_groups"] == 0 and mixed["cache"]["legacy_records"], "valid legacy CACHE1 remains a hit")
                for n in mixed["cache"]["legacy_records"]:
                    require(mixed_before["files"][n] == mixed["cache"]["files"][n], "legacy hit not rewritten")
                before_change = mixed
            changed = driver(kind, cache, root, "42", kind + "-one-value-change")
            require(changed["query_report"]["inferred_groups"] == 1 and changed["query_report"]["reused_groups"] > 0, "one independent source change reinfers one group")
            require(changed["artifact_sha256"] != cold["artifact_sha256"],
                    "one value change must alter the final artifact, not be a no-op")
            unchanged_records = set(before_change["cache"]["active_records"]) & set(changed["cache"]["active_records"])
            for name in unchanged_records:
                require(before_change["cache"]["files"][name] == changed["cache"]["files"][name],
                        "unchanged active group preserves exact bytes, hash, allocation and timestamps")
            stable = driver(kind, cache, root, "42", kind + "-changed-warm")
            require(stable["query_report"]["inferred_groups"] == 0 and stable["artifact_sha256"] == changed["artifact_sha256"], "changed warm exact parity")
            for n in warm["cache"]["reachable_contexts"]:
                require(warm["cache"]["files"][n] == changed["cache"]["files"][n], "one value change does not rewrite shared context")
            repairs = []
            for mutation in ["missing-context", "corrupt-context", "corrupt-record"]:
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
            record["drivers"][kind] = {"sentinels": sentinels, "cold": cold, "warm": warm, "mixed_legacy": mixed, "before_one_value_change": before_change,
                "changed": changed, "changed_warm": stable,
                "one_value_publication_delta": publication_delta(before_change["cache"], changed["cache"]), "repairs": repairs}
            save()
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
            if mode == "session":
                dependency = record["left_session_builtin_dependency"]
                dependency["before_live_probe"] = canonical_session_builtin_pair(out / "session/builtin")
                require(dependency["before_live_probe"] == dependency["cold_pair"],
                        "original successful session-cold builtin exact full stat/SHA unchanged")
                require(not any((root / name).exists() for name in ("builtin.mlfci", "builtin.mlfco", "builtin.lock")),
                        "left-session has no substituted local builtin or warm target cache")
                save()
            argv = ["left-" + mode, cache] + ([root, out / "session/builtin.mlfci"] if mode == "session" else [])
            raw = run_with_live_probe("left-" + mode, argv,
                    b"PASS business Left after held-lock group execution\n", "lock-after-" + mode, cache, sentinels)
            require(raw == b"PASS business Left after held-lock group execution\n", "business Left marker")
            if mode == "session":
                dependency["after_live_probe"] = canonical_session_builtin_pair(out / "session/builtin")
                require(dependency["after_live_probe"] == dependency["before_live_probe"] == dependency["cold_pair"],
                        "explicit builtin dependency exact full stat/SHA remains unchanged after live probe")
                require(not any((root / name).exists() for name in ("builtin.mlfci", "builtin.mlfco", "builtin.lock")),
                        "public Session reused validated explicit dependency, no hidden local cold generation")
            no_query_scratch(cache)
            verify_sentinels(cache, sentinels)
            message_path = Path(str(cache) + ".left-message")
            message = message_path.read_bytes()
            require(len(message) <= 65536 and b"type constructor mismatch:" in message,
                    "actual post-group inference diagnostic required")
            lifecycle["left-" + mode] = {"cache": physical_inventory(cache), "original_sentinels": sentinels,
                                          "diagnostic": {"path": str(message_path), "bytes": len(message), "sha256": digest(message)}}
            save()
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
                    "legacy readers clear memo without changing raw", "memo rejects datatype kind change",
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
        run_memo_helper()
        phases = ["cold", "warm", "mixed", "restored-warm", "corrupt-repair", "missing-repair"]
        expected_counts = [(2, 0), (0, 2), (0, 2), (0, 2), (1, 1), (1, 1)]
        for kind in drivers:
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
                                  "mixed_legacy_scope": "Haskell checked full bytes and mtime during mixed hit only; explicit fingerprint record restoration is test setup; no added ctime/devino claim",
                                  "cross_invocation_scope": "all-fingerprinted warm ends verified; next corrupt/missing invocations must each infer one and hit one, not reuse global state"}
            save()

        # Additive directory-publication controls. All original 34 commands,
        # timeouts, lock probes, pair and memo handshakes remain unchanged above.
        publication = {}
        record["context_directory_publication"] = publication
        collision_cache = out / "context-directory-cache"
        setup = run("context-directory-setup", ["context-directory-setup", collision_cache], timeout=60)
        marker = re.fullmatch(rb"PASS context directory setup ([0-9a-f]{64})\n", setup)
        require(marker is not None, "exact real context setup marker")
        reference = marker.group(1).decode("ascii")
        context_path = collision_cache / ("context-" + reference + ".mlfqc")
        existing = collision_cache / "existing.mlfq"
        existing_identity = small_identity(existing)
        existing_query = binary_query(existing.read_bytes())
        require(existing_query['reference'] == reference, "setup binary record really references observed context")
        require(len(existing_query['compact']) == 8, "setup compact source key remains complete")
        original_context_identity = publication_context_identity(context_path)
        original_context = context_path.read_bytes()
        binary_context(original_context, reference)
        backup = collision_cache / "context.original"
        sentinel = context_path / "retained-child"

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

        # One new pure-API comparison mode; seed IO reads the fixed, real
        # writer output of this same K invocation, never an earlier campaign.
        decoder_cache = out / "helper-cache"
        seed_before = with_publication_lock(decoder_cache, lambda: decoder_seed_snapshot(decoder_cache))
        differential = {"seed_before": seed_before, "expected_right": DECODER_DIFFERENTIAL_RIGHT,
                        "expected_left": DECODER_DIFFERENTIAL_LEFT, "case_count": 63,
                        "scope": "explicit legacy-only stateless decoder API differential against frozen P body; real binary seed IO is independently inspected, then fixture derives separate legacy in-memory seeds and their own legacy context SHA; all 63 full Right bytes and exact Left errors remain unchanged",
                        "not_a_prepared_raw_or_performance_claim": True}
        record["decoder_differential"] = differential
        save()
        try:
            compared = run("decoder-differential", ["decoder-differential", decoder_cache], timeout=60)
        finally:
            # Preserve bounded seed post-evidence even on nonzero exit/timeout;
            # an audit error is recorded without replacing the target error.
            try:
                differential["seed_after"] = with_publication_lock(decoder_cache, lambda: decoder_seed_snapshot(decoder_cache))
                differential["seed_identity_unchanged"] = differential["seed_after"] == seed_before
            except BaseException as seed_error:
                differential["seed_audit_error"] = type(seed_error).__name__ + ": " + str(seed_error)
                differential["seed_identity_unchanged"] = False
            save()
        require(len(DECODER_DIFFERENTIAL_RIGHT) == 6 and len(DECODER_DIFFERENTIAL_LEFT) == 57,
                "fixed six valid and fifty-seven invalid differential subcases")
        expected = "".join("PASS decoder differential " + label + " " + kind + "\n"
                           for labels, kind in [(DECODER_DIFFERENTIAL_RIGHT, "Right"), (DECODER_DIFFERENTIAL_LEFT, "Left")]
                           for label in labels) + "PASS decoder differential complete 63 cases\n"
        require(compared == expected.encode("ascii"), "complete ordered decoder differential markers")
        require(differential.get("seed_identity_unchanged") is True, "decoder comparison changed original helper cache identity")
        differential["complete"] = True
        save()

        window_cache, session_raw_cache = run_added_window_controls(fixture, out, record, save,
                                                                   include_session=not args.legacy_query_only)

        cache_roots = [out / "helper-cache", out / "raw-final-cache", out / "raw-final-cache-inputs",
                       *[out / kind / 'cache' for kind in drivers],
                       *[out / ("left-" + mode) / "cache" for mode in left_modes],
                       *[out / name / "cache" for name in ["empty-success", "empty-directory-failure", "cleanup-dual-failure", "concurrent"]]]
        cache_roots += [out / "memo-helper-cache", *[out / ('memo-' + kind) / 'cache' for kind in drivers]]
        cache_roots += [collision_cache, stage_cache]
        cache_roots += [window_cache, *([session_raw_cache] if session_raw_cache is not None else [])]
        record["all_cache_inventory"] = {str(root.relative_to(out)): physical_inventory(root) for root in cache_roots}
        allocated = sum(value["all_pathname_conservative_allocated_bytes"] for value in record["all_cache_inventory"].values())
        logical = sum(value["all_file_logical_bytes"] for value in record["all_cache_inventory"].values())
        record["all_cache_totals"] = {"logical": logical, "allocated": allocated, "cache_roots": len(cache_roots),
                                      "scope": "all selected private cache trees; includes every retained raw/backup/lock/rejected directory; build/capture evidence remains in outer root accounting"}
        require(logical <= 16 * 1024**2 and allocated <= 16 * 1024**2, "16 MiB complete cache budget")
        require(len(record["commands"]) == (29 if args.legacy_query_only else 40), "fixed selected command inventory")
        require(all(digest(Path(path).read_bytes()) == expected for path, expected in inspector_inputs.items()),
                'independent binary inspector input changed during controls')
        if not args.legacy_query_only:
            dependency = record["left_session_builtin_dependency"]
            dependency["terminal_pair"] = canonical_session_builtin_pair(out / "session/builtin")
            require(dependency["terminal_pair"] == dependency["cold_pair"] == dependency["before_live_probe"] == dependency["after_live_probe"],
                    "explicit builtin dependency retained unchanged through all original forty controls")
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
