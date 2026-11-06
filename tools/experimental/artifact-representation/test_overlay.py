#!/usr/bin/env python3
"""Tiny synthetic overlay controls. Never run the historical read experiment."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def local_module(name):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("overlay_test_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(directory):
    fixtures = local_module("test_representation")
    codec = fixtures.r
    overlay = local_module("overlay")
    directory = Path(directory).absolute()
    directory.mkdir(exist_ok=False)
    passed = []

    def check(name, condition):
        assert condition, name
        passed.append(name)

    def rejects(name, operation):
        try:
            operation()
        except (ValueError, KeyError, TypeError, OSError):
            passed.append(name)
        else:
            raise AssertionError("unexpected acceptance: " + name)

    originals = {"one.mlfq": fixtures.fixture("one"), "two.mlfq": fixtures.fixture("two")}
    assert sum(map(len, originals.values())) < 32768
    builder = codec.Builder()
    records = [fixtures.record(raw, builder.query(raw), name) for name, raw in sorted(originals.items())]
    base = directory / "base"
    base_manifest = builder.write(base, records)
    old_files = {path.name: path.read_bytes() for path in base.iterdir()}
    old_reader = codec.Reader(base)
    check("synthetic-base-two-records-exact", all(old_reader.restore(name) == raw for name, raw in originals.items()))

    outer = codec.unpacked(originals["one.mlfq"].decode())
    key = codec.unpacked(outer[1]); key[2] = codec.sha((key[2] + "offline-synthetic-update").encode())
    outer[1] = codec.packed(key)
    changed = codec.packed(outer).encode()
    updated = dict(originals); updated["one.mlfq"] = changed
    changed_builder = codec.Builder()
    new_root = changed_builder.query(changed)
    delta_nodes = {node: value for node, value in changed_builder.nodes.items() if node not in old_reader.entries}
    check("one-key-field-update-only-adds-three-nodes", len(delta_nodes) == 3)
    new_records = copy.deepcopy(records)
    for record in new_records:
        if record["name"] == "one.mlfq":
            record.update(root=new_root, legacy_bytes=len(changed), legacy_sha256=codec.sha(changed))
    delta = directory / "delta"
    base_descriptor = overlay.descriptor(base_manifest)
    overlay.write_overlay(codec, delta, base_descriptor, delta_nodes, new_records)
    # No old Reader object or old manifest is passed to this fresh reader.
    reader = overlay.OverlayReader(codec, base, delta)
    check("unchanged-record-exact", reader.restore("two.mlfq") == originals["two.mlfq"])
    check("changed-record-exact", reader.restore("one.mlfq") == changed)
    expected = {str(base / name) for name in ("objects.pack", "objects.index")}
    expected |= {str(delta / name) for name in ("objects.pack", "objects.index", "manifest.json")}
    check("fresh-reader-exact-five-file-dependency-audit", set(reader.io) == expected)
    check("old-base-manifest-not-read", str(base / "manifest.json") not in reader.io)
    current_roots = [row["root"] for row in new_records]
    old_roots = [row["root"] for row in records]
    reachable = reader.reachable(current_roots)
    check("two-old-base-nodes-are-dead-for-current-root", len(reader.base_ids - reachable) == 2)
    check("old-and-new-pinned-roots-reach-all-nodes", reader.reachable(current_roots + old_roots) == set(reader.entries))
    current = reader.physical_accounting()
    check("current-physical-closure-counts-all-five-files", current["complete_physical_bytes"] == sum(Path(path).stat().st_size for path in expected))
    pinned = reader.physical_accounting(base / "manifest.json")
    check("pinned-old-root-adds-old-manifest-once", pinned["complete_physical_bytes"] == current["complete_physical_bytes"] + (base / "manifest.json").stat().st_size)
    compact = codec.Builder()
    compact.nodes = {node: reader.node(node) for node in reachable}
    compact_path = directory / "full-rewrite"
    compact.write(compact_path, new_records)
    compact_reader = codec.Reader(compact_path)
    check("full-rewrite-two-records-exact", all(compact_reader.restore(name) == raw for name, raw in updated.items()))
    check("full-rewrite-excludes-dead-base-nodes", set(compact_reader.entries) == reachable and compact_reader.accounting()["orphan_nodes"] == 0)
    old_again = codec.Reader(base)
    check("old-snapshot-still-restores-both-originals", all(old_again.restore(name) == raw for name, raw in originals.items()))
    check("base-all-three-files-byte-unchanged", old_files == {path.name: path.read_bytes() for path in base.iterdir()})

    rejects("old-reader-refuses-overlay-version", lambda: codec.Reader(delta))
    missing = directory / "missing-base"; missing.mkdir()
    rejects("missing-base-not-silently-fetched", lambda: overlay.OverlayReader(codec, missing, delta))
    wrong = dict(base_descriptor); wrong["index_sha256"] = "0" * 64
    wrong_dir = directory / "wrong-base"
    overlay.write_overlay(codec, wrong_dir, wrong, delta_nodes, new_records)
    rejects("wrong-base-identity", lambda: overlay.OverlayReader(codec, base, wrong_dir))
    duplicate = dict(delta_nodes)
    smallest = min(old_reader.entries, key=lambda node: old_reader.entries[node][1])
    duplicate[smallest] = old_reader.node(smallest)
    duplicate_dir = directory / "duplicate-id"
    overlay.write_overlay(codec, duplicate_dir, base_descriptor, duplicate, new_records)
    rejects("duplicate-identity-across-layers", lambda: overlay.OverlayReader(codec, base, duplicate_dir))
    dangling = dict(delta_nodes)
    kind, payload, decoded, scalars = dangling.pop(new_root)
    refs = codec.decode_refs(payload); refs[0] = "0" * 64
    bad_payload = codec.encode_refs(refs)
    bad_root = codec.content_id(kind, bad_payload)
    dangling[bad_root] = (kind, bad_payload, decoded, scalars)
    bad_records = copy.deepcopy(new_records)
    for record in bad_records:
        if record["name"] == "one.mlfq":
            record["root"] = bad_root
    dangling_dir = directory / "dangling-cross-layer"
    overlay.write_overlay(codec, dangling_dir, base_descriptor, dangling, bad_records)
    rejects("hash-valid-dangling-cross-layer-reference", lambda: overlay.OverlayReader(codec, base, dangling_dir))
    recursive = dict(base_descriptor); recursive["base"] = dict(base_descriptor)
    recursive_dir = directory / "recursive-base"
    rejects("recursive-base-descriptor-refused", lambda: overlay.write_overlay(codec, recursive_dir, recursive, delta_nodes, new_records))
    check("recursive-descriptor-rejected-before-write", not recursive_dir.exists())

    # Wrapper qualification only: no historical base copy, no 20-read measurement.
    measure = Path(__file__).with_name("measure.py")
    help_result = subprocess.run([sys.executable, "-I", "-B", str(measure), "--help"],
                                 capture_output=True, timeout=10, check=False)
    check("measurement-wrapper-help", help_result.returncode == 0 and b"run-fixed-experiment" in help_result.stdout)
    rejected = directory / "should-not-measure"
    bad_base = subprocess.run([sys.executable, "-I", "-B", str(measure), "--base-dir", str(base),
                               "--output-dir", str(rejected), "--run-fixed-experiment"],
                              capture_output=True, timeout=10, check=False)
    check("measurement-wrapper-rejects-unpinned-synthetic-base-before-write", bad_base.returncode != 0 and not rejected.exists() and b"expected fixed baseline" in bad_base.stderr)
    optimized_dir = directory / "optimized-tests"
    optimized = subprocess.run([sys.executable, "-I", "-B", "-O", str(Path(__file__)), "--output-dir", str(optimized_dir)],
                               capture_output=True, timeout=10, check=False)
    check("overlay-test-entrypoint-refuses-disabled-assertions", optimized.returncode != 0 and not optimized_dir.exists())
    check("bounded-wrapper-output", all(len(result.stdout) + len(result.stderr) <= 65536 for result in (help_result, bad_base, optimized)))
    return dict(passed=len(passed), cases=passed, current_physical_bytes=current["complete_physical_bytes"],
                pinned_physical_bytes=pinned["complete_physical_bytes"], full_rewrite_bytes=compact_reader.accounting()["complete_reachable_bytes"],
                historical_measurements_executed=False,
                scope="Tiny synthetic storage controls only; no compiler semantics, GC, production safety, or performance claim.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    if not __debug__:
        parser.error("tests require assertions; do not use Python -O")
    print(json.dumps(run(args.output_dir), sort_keys=True))
