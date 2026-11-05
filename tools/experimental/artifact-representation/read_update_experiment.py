"""Fixed small-corpus read/update experiment, called only by a coordinated guard.

No compiler is invoked. A synthetic compiler-identity change is a single-record
storage exercise, not a real compiler upgrade or a semantic-cache qualification.
"""
import copy
import json
from pathlib import Path
import statistics
import time

TARGET = "d6595c38cb6e3e5204df3f9a0bf4361acff0b616e5433c84c92fd5216efe6f57.mlfq"
MAX_LOGICAL_READ_BYTES = 256 * 1024 * 1024


class Ledger:
    def __init__(self):
        self.bytes = 0
        self.calls = 0

    def __call__(self, path, size, operation):
        self.bytes += size
        self.calls += 1
        if self.bytes > MAX_LOGICAL_READ_BYTES:
            raise ValueError("experiment logical-read budget exceeded")


def counting_reader(codec):
    class CountedReader(codec.Reader):
        def __init__(self, directory, ledger):
            self.io = {}
            self.ledger = ledger
            super().__init__(directory)

        def note(self, path, size, operation):
            row = self.io.setdefault(str(path), dict(bytes=0, calls=0, file_calls=0, node_calls=0))
            row["bytes"] += size
            row["calls"] += 1
            row[operation + "_calls"] += 1
            self.ledger(str(path), size, operation)

        def _file(self, name, limit):
            raw = super()._file(name, limit)
            self.note(self.directory / name, len(raw), "file")
            return raw

        def node(self, key):
            result = super().node(key)
            self.note(self.directory / "objects.pack", len(result[1]), "node")
            return result

    return CountedReader


def io_total(reader):
    return {key: sum(row[key] for row in reader.io.values()) for key in ("bytes", "calls", "file_calls", "node_calls")}


def execute(codec, overlay, base_directory, output_directory):
    base_directory = Path(base_directory).absolute()
    output_directory = Path(output_directory).absolute()
    output_directory.mkdir(exist_ok=False)
    ledger = Ledger()
    Reader = counting_reader(codec)
    initial = Reader(base_directory, ledger)
    original_records = copy.deepcopy(initial.manifest["records"])
    codec.require(len(original_records) == 12, "fixed population count")
    originals = {row["name"]: initial.restore(row["name"]) for row in original_records}
    codec.require(sum(map(len, originals.values())) == 5167282, "fixed population size")
    codec.require(TARGET in originals, "fixed target missing")
    for record in original_records:
        codec.require(codec.sha(originals[record["name"]]) == record["legacy_sha256"], "baseline old-byte oracle mismatch")
    base_descriptor = overlay.descriptor(initial.manifest)

    # This changes only one query's input identity. It does NOT model the full
    # invalidation population caused by an actual compiler identity change.
    fields = codec.unpacked(originals[TARGET].decode("utf-8"))
    key = codec.unpacked(fields[1])
    previous_identity = key[2]
    key[2] = codec.sha((previous_identity + "offline-synthetic-update").encode("utf-8"))
    codec.require(key[2] != previous_identity, "synthetic identity did not change")
    fields[1] = codec.packed(key)
    changed_raw = codec.packed(fields).encode("utf-8")
    updated = dict(originals)
    updated[TARGET] = changed_raw
    started = time.perf_counter_ns()
    builder = codec.Builder(split_lists=True)
    new_root = builder.query(changed_raw)
    build_changed_record_ns = time.perf_counter_ns() - started
    delta_nodes = {node: value for node, value in builder.nodes.items() if node not in initial.entries}
    reused = set(builder.nodes).intersection(initial.entries)
    for node in reused:
        codec.require(builder.nodes[node] == initial.node(node), "existing identity changed its value")
    codec.require(len(delta_nodes) == 3, "expected exactly compiler-text/key/root changes")
    updated_records = copy.deepcopy(original_records)
    for record in updated_records:
        if record["name"] == TARGET:
            codec.require(record["root"] != new_root, "query root failed to invalidate")
            record.update(root=new_root, legacy_bytes=len(changed_raw), legacy_sha256=codec.sha(changed_raw))
    delta_directory = output_directory / "delta"
    started = time.perf_counter_ns()
    delta_manifest = overlay.write_overlay(codec, delta_directory, base_descriptor, delta_nodes, updated_records)
    delta_write_ns = time.perf_counter_ns() - started

    # Fresh independent object: the overlay reader neither accepts initial nor
    # reads its manifest. Its actual file access audit proves the dependency set.
    current = overlay.OverlayReader(codec, base_directory, delta_directory, ledger)
    expected_paths = {str(base_directory / name) for name in ("objects.pack", "objects.index")}
    expected_paths |= {str(delta_directory / name) for name in ("objects.pack", "objects.index", "manifest.json")}
    roundtrips = []
    for record in updated_records:
        restored = current.restore(record["name"])
        codec.require(restored == updated[record["name"]], "overlay exact-byte mismatch")
        roundtrips.append(dict(name=record["name"], exact_bytes=True, changed=record["name"] == TARGET,
                               bytes=len(restored), sha256=codec.sha(restored)))
    codec.require(set(current.io) == expected_paths, "overlay acquired an undeclared file dependency")
    codec.require(str(base_directory / "manifest.json") not in current.io, "overlay unexpectedly read old manifest")

    current_roots = [record["root"] for record in updated_records]
    previous_roots = [record["root"] for record in original_records]
    reachable = current.reachable(current_roots)
    pinned_reachable = current.reachable(current_roots + previous_roots)
    dead_base = current.base_ids - reachable
    codec.require(pinned_reachable == set(current.entries), "pinned snapshots have unexpected orphan nodes")
    codec.require(len(dead_base) == 2, "expected old key/root to be the only dead base nodes")
    compact = codec.Builder(split_lists=True)
    compact.nodes = {node: current.node(node) for node in reachable}
    compact_directory = output_directory / "full-rewrite"
    started = time.perf_counter_ns()
    compact.write(compact_directory, updated_records)
    full_rewrite_ns = time.perf_counter_ns() - started
    compact_reader = Reader(compact_directory, ledger)
    for record in updated_records:
        codec.require(compact_reader.restore(record["name"]) == updated[record["name"]], "full-rewrite exact-byte mismatch")
    compact_accounting = compact_reader.accounting()

    # Old snapshot still decodes from its unchanged original three files.
    old_again = Reader(base_directory, ledger)
    for record in original_records:
        codec.require(old_again.restore(record["name"]) == originals[record["name"]], "old snapshot was damaged")

    negative_directory = output_directory / "negative-controls"
    negative_directory.mkdir()
    negatives = []

    def rejects(name, operation):
        try:
            operation()
        except (ValueError, KeyError, TypeError, OSError):
            negatives.append(name)
        else:
            raise AssertionError("unexpected acceptance: " + name)

    rejects("old-reader-refuses-overlay-version", lambda: Reader(delta_directory, ledger))
    missing_base = negative_directory / "missing-base"; missing_base.mkdir()
    rejects("missing-base-is-not-silently-fetched", lambda: overlay.OverlayReader(codec, missing_base, delta_directory, ledger))
    wrong = dict(base_descriptor); wrong["index_sha256"] = "0" * 64
    wrong_directory = negative_directory / "wrong-base-identity"
    overlay.write_overlay(codec, wrong_directory, wrong, delta_nodes, updated_records)
    rejects("wrong-base-identity", lambda: overlay.OverlayReader(codec, base_directory, wrong_directory, ledger))
    duplicate = dict(delta_nodes)
    smallest = min(initial.entries, key=lambda node: initial.entries[node][1])
    duplicate[smallest] = initial.node(smallest)
    duplicate_directory = negative_directory / "duplicate-id"
    overlay.write_overlay(codec, duplicate_directory, base_descriptor, duplicate, updated_records)
    rejects("duplicate-identity-across-layers", lambda: overlay.OverlayReader(codec, base_directory, duplicate_directory, ledger))
    dangling = dict(delta_nodes)
    kind, payload, decoded, scalars = dangling.pop(new_root)
    refs = codec.decode_refs(payload); refs[0] = "0" * 64
    bad_payload = codec.encode_refs(refs)
    bad_root = codec.content_id(kind, bad_payload)
    dangling[bad_root] = (kind, bad_payload, decoded, scalars)
    bad_records = copy.deepcopy(updated_records)
    for record in bad_records:
        if record["name"] == TARGET:
            record["root"] = bad_root
    dangling_directory = negative_directory / "dangling-cross-layer"
    overlay.write_overlay(codec, dangling_directory, base_descriptor, dangling, bad_records)
    rejects("hash-valid-dangling-cross-layer-reference", lambda: overlay.OverlayReader(codec, base_directory, dangling_directory, ledger))
    recursive = dict(base_descriptor); recursive["base"] = dict(base_descriptor)
    rejects("recursive-base-descriptor-refused", lambda: overlay.write_overlay(codec, negative_directory / "recursive-base", recursive, delta_nodes, updated_records))
    codec.require(not (negative_directory / "recursive-base").exists(), "invalid base descriptor wrote files")

    # Five fixed interleaved repetitions, without cache flushes or compiler work.
    # Initialization includes whole-pack hash and all-node validation; restoration
    # includes old-byte SHA validation and the same exact-byte comparison policy.
    measurements = []
    for repetition in range(5):
        layouts = ("base", "overlay") if repetition % 2 == 0 else ("overlay", "base")
        modes = ("single", "all") if repetition % 2 == 0 else ("all", "single")
        for layout in layouts:
            for mode in modes:
                begin = time.perf_counter_ns()
                reader = Reader(base_directory, ledger) if layout == "base" else overlay.OverlayReader(codec, base_directory, delta_directory, ledger)
                init_ns = time.perf_counter_ns() - begin
                init_io = io_total(reader)
                names = [TARGET] if mode == "single" else sorted(originals)
                expected = originals if layout == "base" else updated
                begin = time.perf_counter_ns()
                restored_bytes = 0
                for name in names:
                    raw = reader.restore(name)
                    codec.require(raw == expected[name], "timed exact-byte mismatch")
                    restored_bytes += len(raw)
                restore_ns = time.perf_counter_ns() - begin
                total_io = io_total(reader)
                restore_io = {key: total_io[key] - init_io[key] for key in init_io}
                if layout == "overlay":
                    codec.require(set(reader.io) == expected_paths, "timed overlay used undeclared files")
                measurements.append(dict(repetition=repetition + 1, layout=layout, mode=mode, init_ns=init_ns,
                                         restore_ns=restore_ns, total_ns=init_ns + restore_ns,
                                         init_logical_reads=init_io, restore_logical_reads=restore_io,
                                         records=len(names), restored_bytes=restored_bytes, exact_bytes=True))
    summaries = []
    for layout in ("base", "overlay"):
        for mode in ("single", "all"):
            rows = [row for row in measurements if row["layout"] == layout and row["mode"] == mode]
            summaries.append(dict(layout=layout, mode=mode, observations=len(rows),
                                  nanoseconds={key: dict(median=statistics.median(row[key] for row in rows),
                                                         minimum=min(row[key] for row in rows), maximum=max(row[key] for row in rows))
                                               for key in ("init_ns", "restore_ns", "total_ns")},
                                  init_logical_reads=rows[0]["init_logical_reads"],
                                  restore_logical_reads=rows[0]["restore_logical_reads"],
                                  logical_counts_identical=all(row["init_logical_reads"] == rows[0]["init_logical_reads"] and
                                                               row["restore_logical_reads"] == rows[0]["restore_logical_reads"] for row in rows)))

    delta_files = {name: (delta_directory / name).stat().st_size for name in ("objects.pack", "objects.index", "manifest.json")}
    current_physical = current.physical_accounting()
    pinned_physical = current.physical_accounting(base_directory / "manifest.json")
    return dict(format="offline-query-read-incremental-experiment-v1", complete=True,
                input=dict(base_directory=str(base_directory), target=TARGET, input_records=12, input_bytes=5167282),
                mutation=dict(field="source-query-v6 key[2] compiler identity", previous=previous_identity, replacement=key[2],
                              synthetic_only=True, meaning="Single-record storage/identity exercise, not a real compiler upgrade or semantic-checker pass."),
                update=dict(new_nodes=len(delta_nodes), reused_nodes_in_changed_record=len(reused), dead_base_nodes=len(dead_base),
                            unchanged_records=11, changed_records=1, exact_roundtrips=roundtrips, old_snapshot_still_exact=True,
                            delta_files=delta_files, actual_new_write_bytes=sum(delta_files.values()),
                            current_complete_physical=current_physical, old_and_new_pinned_complete_physical=pinned_physical,
                            current_reachable_nodes=len(reachable), current_reachable_payload_bytes=sum(current.entries[node][1] for node in reachable),
                            current_reachable_index_entry_bytes=len(reachable) * codec.ENTRY.size,
                            dead_base_payload_bytes=sum(current.entries[node][1] for node in dead_base),
                            dead_base_index_entry_bytes=len(dead_base) * codec.ENTRY.size,
                            full_rewrite=compact_accounting, full_rewrite_exact_records=12,
                            write_reduction_fraction=1 - sum(delta_files.values()) / compact_accounting["complete_reachable_bytes"],
                            single_run_ns=dict(build_changed_record=build_changed_record_ns, write_delta=delta_write_ns, write_full=full_rewrite_ns)),
                overlay_dependency_audit=dict(actual_files=sorted(current.io), expected_files=sorted(expected_paths),
                                              old_manifest_read=False, preloaded_base_reader_required=False),
                negative_controls=dict(passed=len(negatives), cases=negatives), measurements=measurements, summaries=summaries,
                complete_experiment_logical_reads=dict(bytes=ledger.bytes, calls=ledger.calls),
                limitations=["Logical read bytes are bytes returned to Python, not physical disk IO; no cache flush was performed.",
                             "Five fixed repetitions are small observed diagnostics, not cold/warm OS-cache or compiler performance qualification.",
                             "Initialization reads complete packs for SHA and then validates every node; single-record restore is not single-record-only initialization.",
                             "Full physical closure includes dead base nodes retained inside immutable packs. No GC, deletion, compaction in place, or reclamation is claimed.",
                             "Synthetic compiler identity changes only one record here; a real compiler upgrade can invalidate all queries.",
                             "No MLF semantic checker, production cache integration, fsync/crash-safety or concurrent writer qualification is performed."])
