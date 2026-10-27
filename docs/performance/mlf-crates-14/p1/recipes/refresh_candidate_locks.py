#!/usr/bin/env python3
"""Refresh exactly six authorized live locks through an authenticated manager.

No lock is synthesized in Python. This driver invokes the ordinary offline lock
and locked-plan commands, preserves original bytes and receipts, then checks the
manager's complete package/source inventories against the unchanged local tree.
Run only under the parent process-tree watchdog. --execute is mandatory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOTS = (
    ("root", "mlf-package.json"),
    ("tests", "tests/mlf-package.json"),
    ("testing-tools", "testing/tools/mlf-package.json"),
    ("async", "libraries/mlf-async/mlf-package.json"),
    ("tests-shared", "tests/shared/mlf-package.json"),
    ("async-fixtures", "tests/async-package/mlf-package.json"),
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def identified(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(data):
    return json.loads(data, object_pairs_hook=unique_object)


def write_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def regular_below(path, root):
    path = Path(path)
    require(not path.is_symlink(), "symlink input is not supported: " + str(path))
    actual = path.resolve(strict=True)
    require(actual.is_relative_to(root) and actual.is_file(), "nonlocal/nonfile input: " + str(path))
    return actual


def tracked_snapshot(source, excluded):
    names = subprocess.check_output(["git", "-C", str(source), "ls-files", "-z"]).decode().split("\0")
    require(len([name for name in names if name]) == len(set(name for name in names if name)), "duplicate tracked path")
    return {name: sha(regular_below(source / name, source))
            for name in sorted(names) if name and name not in excluded}


def dependency_inventory(manifest, source):
    """Independent manifest traversal; reject remote/release dependencies.

    Mirrors the declared source inventory only, not the manager's resolver or
    compiler. Every declared library module and main-bearing target is included.
    """
    start = regular_below(manifest, source)
    anchor = start.parent
    pending, packages = [start], {}
    while pending:
        path = regular_below(pending.pop(), source)
        data = parse_json(path.read_bytes())
        name = data["name"]
        if name in packages:
            require(packages[name]["manifest_path"] == str(path), "conflicting local package: " + name)
            continue
        require(data.get("format") == 1 and isinstance(data.get("version"), str), "unsupported package manifest")
        root = path.parent
        paths = set(data.get("library", {}).get("modules", {}).values())
        for target in [*data.get("executables", {}).values(), *data.get("tests", {}).values()]:
            if "main" in target:
                paths.add(target["main"])
                paths.update(target.get("modules", {}).values())
        files = {}
        for relative in sorted(paths):
            require(isinstance(relative, str) and not Path(relative).is_absolute(), "absolute/nontext source path")
            actual = regular_below(root / relative, source)
            files[os.path.relpath(actual, root)] = sha(actual)
        packages[name] = {"manifest_path": str(path), "expected": {
            "name": name, "version": data["version"], "path": os.path.relpath(root, anchor),
            "manifest": sha(path), "sources": files}}
        for dependency_name, dependency in data.get("dependencies", {}).items():
            require(isinstance(dependency, dict) and set(dependency) == {"path"},
                    "remote/release/nonlocal dependency forbidden: " + dependency_name)
            require(isinstance(dependency["path"], str) and not Path(dependency["path"]).is_absolute(),
                    "absolute dependency forbidden")
            pending.append((root / dependency["path"] / "mlf-package.json").resolve())
    return packages


def verify_package_rows(value, expected):
    require(isinstance(value, dict) and value.get("format") == 1, "unsupported lock/plan format")
    rows = value.get("packages")
    require(isinstance(rows, list), "missing package rows")
    names = [row.get("name") for row in rows]
    require(len(names) == len(set(names)) and set(names) == set(expected), "package inventory mismatch")
    for row in rows:
        require(row == expected[row["name"]]["expected"], "manifest/source snapshot differs: " + row["name"])
    return {"packages": len(rows), "source_entries": sum(len(row["sources"]) for row in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--producer-receipt", type=Path, required=True)
    parser.add_argument("--producer-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    require(args.execute, "explicit --execute required; no work performed")
    source = args.source_root.resolve(strict=True)
    output = args.output.resolve()
    require(not output.exists(), "new output directory required")
    require(not output.is_relative_to(source) and not source.is_relative_to(output), "evidence directory must be separate from source")
    producer_path = args.producer_receipt.resolve(strict=True)
    require(sha(producer_path) == args.producer_sha256, "producer receipt digest mismatch")
    bins = producer_path.parent / "bin"
    helper = regular_below(source / "tools/shared/test_direct.py", source)
    # Import only the pinned maintained authentication helper; never modify it.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("exact_direct_authentication", helper)
    direct = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(direct)
    producer = direct.authenticate_build(producer_path, bins, source)
    require(producer["optimization"] == "2", "the authorized fixed O2 producer is required")
    manager = bins / "mlfpkg"
    compiler = bins / "emlf"
    require(producer["outputs"]["mlfpkg"]["path"] == str(manager.resolve()), "wrong authenticated manager")
    lock_relatives = {str(Path(relative).parent / "mlf.lock") for _, relative in ROOTS}
    require(len(lock_relatives) == 6, "unexpected authorized lock inventory")
    baseline = tracked_snapshot(source, lock_relatives)
    originals = {}
    for relative in lock_relatives:
        path = regular_below(source / relative, source)
        originals[relative] = path.read_bytes()
    # This validation is performed before the first source-tree mutation.
    expected_by_root = {name: dependency_inventory(source / relative, source) for name, relative in ROOTS}
    output.mkdir(parents=True)
    (output / "before").mkdir()
    (output / "after").mkdir()
    (output / "commands").mkdir()
    write_json(output / "source-inputs.json", baseline)
    expected_locks = {relative: hashlib.sha256(data).hexdigest() for relative, data in originals.items()}
    for relative, data in originals.items():
        path = output / "before" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        require(sha(path) == expected_locks[relative], "failed to preserve original lock bytes")
    inputs = {str(producer_path): sha(producer_path), str(helper): sha(helper),
              str(Path(__file__).resolve()): sha(__file__), str(Path(sys.executable).resolve()): sha(sys.executable),
              str(manager.resolve()): sha(manager), str(compiler.resolve()): sha(compiler)}
    environment = {**os.environ, "GHC_ENVIRONMENT": "-", "GHCRTS": "", "LC_ALL": "C.UTF-8",
                   "MLF_COMPILER": str(compiler.resolve())}
    record = {"format": "pr25-authentic-six-lock-refresh-v1", "complete": False,
              "source_root": str(source), "producer_receipt": str(producer_path),
              "producer_sha256": args.producer_sha256, "inputs": inputs,
              "source_inputs": identified(output / "source-inputs.json"),
              "authorized_lock_paths": sorted(lock_relatives), "before_locks": expected_locks.copy(),
              "roots": [], "network_policy": "Only declared local path dependencies; every manager command includes --offline.",
              "mutation_policy": "Only ordinary manager lock commands may write the six authorized live locks; all other tracked bytes must remain unchanged.",
              "resource_policy": "Enclosing parent process-tree watchdog owns shared RSS/AS/disk/host-memory limits; commands also have a 180-second subprocess timeout.",
              "rollback_policy": "On failure retain truthful partial state and original-byte backups; no implicit rollback or receipt rewriting.",
              "environment": {key: environment.get(key, "") for key in ("PATH", "LD_LIBRARY_PATH", "GHC_ENVIRONMENT", "GHCRTS", "LC_ALL", "MLF_COMPILER")}}
    receipt_path = output / "receipt.json"
    def save():
        write_json(receipt_path, record)
    def check_integrity(allowed_changed_lock=None):
        require(tracked_snapshot(source, lock_relatives) == baseline, "non-authorized tracked source change")
        for path, digest in inputs.items():
            require(sha(path) == digest, "input/tool changed: " + path)
        for relative, digest in expected_locks.items():
            if relative != allowed_changed_lock:
                require(sha(regular_below(source / relative, source)) == digest,
                        "unrelated lock changed: " + relative)
    def command(name, phase, argv, allowed_changed_lock=None):
        check_integrity()
        folder = output / "commands" / (name + "-" + phase)
        folder.mkdir()
        stdout, stderr = folder / "stdout", folder / "stderr"
        cmd = {"complete": False, "argv": list(map(str, argv)), "cwd": str(source),
               "stdout": str(stdout), "stderr": str(stderr), "timeout_seconds": 180,
               "input_pins_verified_before": True}
        child_receipt = folder / "receipt.json"
        write_json(child_receipt, cmd)
        started = time.perf_counter_ns()
        try:
            with stdout.open("wb") as outstream, stderr.open("wb") as errstream:
                result = subprocess.run(cmd["argv"], cwd=source, env=environment, stdin=subprocess.DEVNULL,
                                        stdout=outstream, stderr=errstream, timeout=180)
            cmd["exit_code"] = result.returncode
            require(result.returncode == 0, "manager command failed: " + name + "/" + phase)
            require(not stderr.read_bytes(), "manager command wrote stderr: " + name + "/" + phase)
            check_integrity(allowed_changed_lock)
            cmd.update(complete=True, input_pins_verified_after=True)
        except BaseException as error:
            cmd["error"] = type(error).__name__ + ": " + str(error)
            raise
        finally:
            cmd["wall_seconds"] = (time.perf_counter_ns() - started) / 1e9
            for key, path in (("stdout", stdout), ("stderr", stderr)):
                if path.exists():
                    cmd[key + "_sha256"] = sha(path)
            write_json(child_receipt, cmd)
        return {"exit": cmd["exit_code"], "receipt": str(child_receipt), "receipt_sha256": sha(child_receipt),
                "stdout": str(stdout), "stdout_sha256": sha(stdout), "stderr": str(stderr),
                "stderr_sha256": sha(stderr), "wall_seconds": cmd["wall_seconds"]}, stdout.read_bytes()
    save()
    try:
        for name, relative in ROOTS:
            manifest = source / relative
            lock = manifest.parent / "mlf.lock"
            lock_relative = str(lock.relative_to(source))
            row = {"name": name, "manifest": str(manifest), "manifest_sha256": sha(manifest),
                   "lock_path": str(lock), "before_lock": expected_locks[lock_relative]}
            record["roots"].append(row)
            save()
            base = [manager, "--manifest", manifest, "--compiler", compiler,
                    "--build-dir", output / (name + "-unused-build"),
                    "--cache-dir", output / (name + "-unused-cache"), "--offline"]
            row["lock"], stdout = command(name, "lock", [*base, "lock"], lock_relative)
            require(stdout == (str(lock) + "\n").encode(), "unexpected lock stdout")
            current = regular_below(lock, source)
            lock_bytes = current.read_bytes()
            lock_data = parse_json(lock_bytes)
            require(set(lock_data) == {"format", "packages"}, "unexpected lock fields")
            row["independent_lock_inventory"] = verify_package_rows(lock_data, expected_by_root[name])
            expected_locks[lock_relative] = sha(lock)
            row["after_lock"] = expected_locks[lock_relative]
            after_path = output / "after" / lock_relative
            after_path.parent.mkdir(parents=True, exist_ok=True)
            after_path.write_bytes(lock_bytes)
            require(sha(after_path) == row["after_lock"], "failed to preserve refreshed lock")
            save()
            row["plan"], plan_bytes = command(name, "plan", [*base, "--locked", "plan"])
            plan = parse_json(plan_bytes)
            row["independent_plan_inventory"] = verify_package_rows(plan, expected_by_root[name])
            require(plan["packages"] == lock_data["packages"], "locked plan package ordering/content differs from lock")
            require(isinstance(plan.get("crates"), list) and isinstance(plan.get("modules"), list), "incomplete real plan")
            plan_path = output / (name + "-plan.json")
            plan_path.write_bytes(plan_bytes)
            row["plan_sha256"] = sha(plan_path)
            row["complete"] = True
            save()
        check_integrity()
        direct.authenticate_build(producer_path, bins, source)
        require(sha(producer_path) == args.producer_sha256, "producer receipt changed")
        record.update(complete=True, immutable_nonlock_inputs_verified_after=True,
                      producer_reauthenticated_after=True, after_locks=expected_locks.copy())
    except BaseException as error:
        record.update(complete=False, error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        record["actual_final_lock_hashes"] = {relative: sha(source / relative)
            for relative in sorted(lock_relatives) if (source / relative).is_file()}
        try:
            require(tracked_snapshot(source, lock_relatives) == baseline, "nonlock source changed")
            for path, digest in inputs.items():
                require(sha(path) == digest, "tool/input changed")
            record["immutable_nonlock_inputs_verified_after"] = True
        except BaseException as error:
            record.update(complete=False, immutable_nonlock_inputs_verified_after=False, integrity_error=repr(error))
        save()
    require(record["complete"], "refresh postflight failed")
    print(json.dumps({"receipt": str(receipt_path), "complete": True, "roots": len(record["roots"]),
                      "changed_locks": [relative for relative in expected_locks
                                        if expected_locks[relative] != record["before_locks"][relative]]}))


if __name__ == "__main__":
    main()
