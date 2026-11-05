#!/usr/bin/env python3
"""Small offline pack/verify/restore tool; never reads or writes a compiler cache implicitly."""
import argparse
import importlib.util
import json
from pathlib import Path
import stat
import sys


def load_codec():
    path = Path(__file__).with_name("representation.py").resolve()
    spec = importlib.util.spec_from_file_location("artifact_representation", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r = load_codec()
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_RECORDS = 64


def records(reader):
    values = reader.manifest["records"]
    r.require(isinstance(values, list) and 0 < len(values) <= MAX_RECORDS, "record-count limit")
    names = set()
    total = 0
    for record in values:
        name = record["name"]
        size = record["legacy_bytes"]
        r.require(isinstance(name, str) and name and name not in names, "invalid or duplicate record name")
        r.require(type(size) is int and 0 <= size <= MAX_INPUT_BYTES, "invalid record length")
        r.require(isinstance(record["legacy_sha256"], str) and len(record["legacy_sha256"]) == 64, "invalid legacy digest")
        total += size
        names.add(name)
    r.require(total <= MAX_INPUT_BYTES, "total decoded input limit")
    return values


def read_input(path, remaining):
    path = Path(path).absolute()
    r.require(path.resolve() == path, "input must not traverse symlinks")
    before = path.stat()
    r.require(stat.S_ISREG(before.st_mode) and before.st_size <= remaining, "invalid or oversized input")
    with path.open("rb") as stream:
        raw = stream.read(remaining + 1)
    after = path.stat()
    r.require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
              (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "input changed while reading")
    r.require(len(raw) == before.st_size and len(raw) <= remaining, "input length mismatch")
    return raw


def verified_summary(reader):
    values = records(reader)
    for record in values:
        reader.restore(record["name"])
    return dict(records_verified=len(values), original_bytes=sum(record["legacy_bytes"] for record in values),
                strategy=reader.manifest["strategy"], **reader.accounting())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pack = commands.add_parser("pack", help="convert canonical source-v6 CACHE-1 files into a new offline bundle")
    pack.add_argument("--output-dir", required=True, type=Path, help="new directory; its parent must already exist")
    pack.add_argument("--whole-fields", action="store_true", help="disable the additional list-component sharing")
    pack.add_argument("inputs", nargs="+", type=Path)
    verify = commands.add_parser("verify", help="check every record and account for the complete reachable bundle")
    verify.add_argument("bundle", type=Path)
    restore = commands.add_parser("restore", help="restore one record's exact original bytes")
    restore.add_argument("bundle", type=Path)
    restore.add_argument("record", help="record name printed in manifest.json, normally the original basename")
    destination = restore.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output-file", type=Path, help="new file; never overwrite an existing path")
    destination.add_argument("--stdout", action="store_true", help="write only the restored bytes to stdout")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            r.require(0 < len(args.inputs) <= MAX_RECORDS, "input-count limit")
            r.require(not args.output_dir.exists() and not args.output_dir.is_symlink(), "output directory already exists")
            names = [path.name for path in args.inputs]
            r.require(len(set(names)) == len(names), "duplicate input basename")
            builder = r.Builder(split_lists=not args.whole_fields)
            originals, manifest_records = {}, []
            total = 0
            for path in sorted(args.inputs, key=lambda item: item.name):
                raw = read_input(path, MAX_INPUT_BYTES - total)
                total += len(raw)
                originals[path.name] = raw
                root = builder.query(raw)
                manifest_records.append(dict(name=path.name, legacy_bytes=len(raw), legacy_sha256=r.sha(raw), root=root))
            builder.write(args.output_dir, manifest_records)
            reader = r.Reader(args.output_dir)
            for name, raw in originals.items():
                r.require(reader.restore(name) == raw, "post-write exact roundtrip failed")
            summary = verified_summary(reader)
        else:
            reader = r.Reader(args.bundle)
            records(reader)
            if args.command == "verify":
                summary = verified_summary(reader)
            else:
                raw = reader.restore(args.record)
                if args.stdout:
                    sys.stdout.buffer.write(raw)
                    return 0
                with args.output_file.open("xb") as stream:
                    stream.write(raw)
                summary = dict(record=args.record, restored_bytes=len(raw), legacy_sha256=r.sha(raw))
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.exit(2, "error: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
