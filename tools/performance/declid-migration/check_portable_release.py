#!/usr/bin/env python3
"""Qualify portable open releases through the installed package-manager CLI.

Publish a transitive library, move its bundle, delete only this run's producer
sources/build/cache, then compare the old manager with the installed candidate.
The candidate must build and run a native consumer without producer sources and
reuse the exact materialization receipt/files on a warm build.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
HEADER = ("-- mlf:syntax shared-haskell-v1\n"
          "{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes, "
          "KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses, "
          "OverloadedStrings #-}\n")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def regular(path):
    path = Path(path).resolve(strict=True)
    require(stat.S_ISREG(path.stat().st_mode), "regular file required: " + str(path))
    return path


def executable(path):
    result = regular(shutil.which(str(path)) or path)
    require(os.access(result, os.X_OK), "executable required: " + str(result))
    return result


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        mode = path.lstat().st_mode
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "nonregular bundle entry")
        if stat.S_ISREG(mode):
            result[str(path.relative_to(directory))] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    return result


def snapshot(paths):
    result = {}
    for path in sorted(paths):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode), "materialized file must be regular")
        result[str(path)] = {"sha256": digest(path), "stat": [info.st_dev, info.st_ino,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-manager", required=True, type=Path)
    parser.add_argument("--after-prefix", required=True, type=Path)
    parser.add_argument("--after-compiler", type=Path, help="Defaults to AFTER_PREFIX/bin/emlf")
    parser.add_argument("--runtime", type=Path, default=Path(os.environ.get("MLF_RUNTIME", ROOT / "runtime/mlf_runtime.c")))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout", type=int, default=600, help="Per-command deadline in seconds")
    args = parser.parse_args()
    require(0 < args.timeout <= 3600, "invalid command deadline")
    prefix = args.after_prefix.resolve(strict=True)
    before = executable(args.before_manager)
    after = executable(prefix / "bin/mlfpkg")
    compiler = executable(args.after_compiler or prefix / "bin/emlf")
    runtime = regular(args.runtime)
    runner = executable(os.environ.get("MLF_BUILD_RUNNER", prefix / "bin/mlf-build-runner"))
    clang = executable(os.environ.get("MLF_CLANG", "clang"))
    pkg_config = executable(os.environ.get("MLF_PKG_CONFIG", "pkg-config"))
    gc = Path(os.environ["MLF_GC_PREFIX"]).resolve(strict=True) if os.environ.get("MLF_GC_PREFIX") else None
    inputs = {str(path): digest(path) for path in (regular(__file__), before, after, compiler, runtime, runner, clang, pkg_config)}
    if gc:
        for path in [*sorted((gc / "include").rglob("*.h")), gc / "lib/libgc.a"]:
            path = regular(path)
            inputs[str(path)] = digest(path)
    out = args.output.resolve()
    require(all(not Path(path).is_relative_to(out) for path in inputs), "output overlaps an input")
    out.mkdir(parents=True, exist_ok=False)
    record = {"complete": False, "inputs": inputs, "commands": [], "source_sha256": {},
              "after_prefix": str(prefix), "gc_prefix": str(gc) if gc else None,
              "runner": str(runner), "command_timeout_seconds": args.timeout}
    report = out / "results.json"
    env = dict(os.environ, MLF_BUILD_RUNNER=str(runner))

    def save():
        report.write_text(json.dumps(record, indent=2) + "\n")

    def run(name, argv, expected=0):
        argv = list(map(str, argv))
        stdout, stderr = out / (name + ".stdout"), out / (name + ".stderr")
        start = time.monotonic()
        with stdout.open("xb") as output, stderr.open("xb") as errors:
            result = subprocess.run(argv, cwd=out, env=env, stdout=output, stderr=errors, timeout=args.timeout)
        row = {"name": name, "argv": argv, "exit_code": result.returncode,
               "seconds": time.monotonic() - start,
               "stdout": {"path": str(stdout), "sha256": digest(stdout)},
               "stderr": {"path": str(stderr), "sha256": digest(stderr)}}
        record["commands"].append(row)
        save()
        require(result.returncode == expected, f"{name}: expected exit {expected}, got {result.returncode}; see {stderr}")
        return stdout.read_text(), stderr.read_text()

    def postcheck():
        require(all(digest(Path(path)) == expected for path, expected in inputs.items()), "tool/runtime input changed")
        require(inventory(bundle) == record["bundle_inventory"], "pinned relocated bundle changed")
        require(all(not path.exists() for path in removed), "producer sources or caches reappeared")

    try:
        save()
        common = ["--offline", "--compiler", compiler, "--runtime", runtime, "--clang", clang,
                  "--pkg-config", pkg_config, "--jobs", "1", "--timeout", str(args.timeout)]
        if gc:
            common.extend(["--gc-prefix", gc])
        producer, producer_build, producer_cache = (out / name for name in ("producer", "producer-build", "producer-cache"))
        producer.mkdir()
        for name, module, dependency, imported, value in (
                ("leaf", "Leaf", None, None, "40"),
                ("middle", "Middle", "leaf", "Leaf", "Leaf.value + 1"),
                ("greeting", "Greeting", "middle", "Middle", "Middle.value + 1")):
            directory = producer / name
            directory.mkdir()
            imports = "import MLF.Primitive; " + (f"import qualified {imported}; " if imported else "")
            (directory / (module + ".hs")).write_text(HEADER + f"module {module} where {{ {imports}value :: Int; value = {value} }}\n")
            manifest = {"format": 1, "name": name, "version": "1.0.0", "source-syntax": "shared-haskell-v1",
                        "library": {"modules": {module: module + ".hs"}}}
            if dependency:
                manifest["dependencies"] = {dependency: {"path": "../" + dependency}}
            (directory / "mlf-package.json").write_text(json.dumps(manifest) + "\n")
            record["source_sha256"].update({str(path): digest(path) for path in directory.iterdir()})
        release, bundle = out / "release", out / "relocated bundle"
        run("publish", [after, "--manifest", producer / "greeting/mlf-package.json", "--build-dir", producer_build,
                        "--cache-dir", producer_cache, *common, "release", release])
        release.rename(bundle)
        record["bundle_inventory"] = inventory(bundle)
        record["release_manifest"] = json.loads((bundle / "release.json").read_bytes())
        rows = record["release_manifest"]["crates"]
        require({row["identity"] for row in rows} == {"mlf:builtin-shared-haskell-v1:13",
                "leaf/1.0.0/library", "middle/1.0.0/library", "greeting/1.0.0/library"}, "incomplete transitive release")
        pin = digest(bundle / "release.json")
        record["release_sha256"] = pin
        require(all(digest(Path(path)) == expected for path, expected in record["source_sha256"].items()), "producer source changed")
        removed = (producer, producer_build, producer_cache)
        for path in removed:
            require(path.parent == out and path.is_dir() and not path.is_symlink(), "cleanup must own its direct child")
            shutil.rmtree(path)
        record["removed_owned_paths"] = list(map(str, removed))
        record["producer_sources_absent"] = all(not path.exists() for path in removed)
        consumer = out / "consumer"
        consumer.mkdir()
        (consumer / "Main.hs").write_text(HEADER + "module Main where { import MLF.Primitive; import qualified Greeting; main = putStrLn (showInt Greeting.value) }\n")
        manifest = {"format": 1, "name": "consumer", "version": "1.0.0", "source-syntax": "shared-haskell-v1",
                    "dependencies": {"greeting": {"release": str(bundle), "sha256": pin}},
                    "executables": {"answer": {"main": "Main.hs", "dependencies": ["greeting"]}}}
        (consumer / "mlf-package.json").write_text(json.dumps(manifest) + "\n")
        command = ["--manifest", consumer / "mlf-package.json", *common]
        _, error = run("before-rejects-portable-path", [before, *command, "--build-dir", out / "before-build",
                         "--cache-dir", out / "before-cache", "build"], expected=1)
        require("crate metadata does not exist: /__mlf_release__/" in error, "before manager did not reproduce portable-path regression")
        cache = out / "after-cache"
        candidate = [after, *command, "--build-dir", out / "after-build", "--cache-dir", cache]
        run("source-free-cold-build", [*candidate, "build"])
        receipts = list((cache / ".releases/verified").glob("*.json"))
        require(len(receipts) == 1, "one checked release materialization receipt required")
        receipt = json.loads(receipts[0].read_bytes())
        require(receipt["release"] == pin and receipt["validator_sha256"] == digest(after), "materialization receipt pins")
        paths = [Path(path) for path in receipt["files"]]
        require(len(paths) == 2 * len(rows) and all(path.is_relative_to(cache) for path in paths), "complete installed artifact closure")
        require(all(digest(Path(path)) == expected for path, expected in receipt["files"].items()), "materialization file hashes")
        stable = snapshot([*paths, *receipts])
        postcheck()
        run("source-free-warm-build", [*candidate, "build"])
        require(snapshot([*paths, *receipts]) == stable, "warm materialization rewrote verified files/receipt")
        stdout, _ = run("source-free-native-run", [*candidate, "run", "answer"])
        require(stdout == "42\n", "native result must be exactly 42")
        require(snapshot([*paths, *receipts]) == stable, "native run rewrote verified materialization")
        postcheck()
        record.update(complete=True, warm_materialization_unchanged=True, native_stdout=stdout,
                      installed_snapshot=stable, post_input_integrity=True)
        save()
        print(json.dumps({"complete": True, "native_stdout": stdout, "commands": len(record["commands"]), "report": str(report)}))
    except BaseException as error:
        record["error"] = str(error)
        save()
        raise


if __name__ == "__main__":
    main()
