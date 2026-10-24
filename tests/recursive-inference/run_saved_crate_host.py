#!/usr/bin/env python3
"""Run exact retained saved-crate fixtures with the existing GHC host.

This is a focused checking-only harness, not a native-code or release campaign.
Its evidence is separate from the ordinary shared compiler build receipts.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": digest(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler-build", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, default=Path(".mlf-build/qualified-host-crate"))
    args = parser.parse_args()
    compiler = args.compiler_build.resolve()
    directory = args.build_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    receipt_path = compiler / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("complete") is not True:
        raise RuntimeError("a completed existing compiler build is required")
    inputs = {}
    for group in ("shared_inputs", "host_inputs", "configuration_inputs"):
        for name, item in receipt[group].items():
            if digest(item["path"]) != item["sha256"]:
                raise RuntimeError("compiler receipt input changed: " + name)
            inputs[item["path"]] = item["sha256"]
    ghc = receipt["ghc"]
    if digest(ghc["path"]) != ghc["sha256"]:
        raise RuntimeError("recorded GHC executable changed")
    wrapper = directory / "Main.hs"
    wrapper.write_text("module Main where\nimport qualified QualifiedCrateHost as Entry\n"
                       "import MLF.Host.IO (runEntry)\nmain :: IO ()\nmain = runEntry Entry.main\n")
    flags = list(receipt["flags"])
    for option in ("-odir", "-hidir"):
        flags[flags.index(option) + 1] = str(directory / "objects")
    linked = [compiler / "host.o", compiler / "supervisor.o"]
    command = [ghc["path"], "--make", "-j1", "-fforce-recomp", *flags,
               "-i" + str(ROOT / "tests/recursive-inference"), "-rtsopts=ignoreAll",
               str(wrapper), *map(str, linked), "-o", str(directory / "check")]
    own_inputs = [Path(__file__), ROOT / "tests/recursive-inference/QualifiedCrateHost.hs",
                  ROOT / "tests/Tests/Modules.emlf", ROOT / "tests/Tests/Separate.emlf", wrapper]
    evidence = {"format": 1, "scope": "six exact saved-crate fixtures; GHC host; no target evaluation",
                "compiler_receipt": identity(receipt_path), "ghc": ghc,
                "validated_compiler_input_inventory": inputs,
                "harness_inputs": [identity(path) for path in own_inputs],
                "linked_host_objects": [identity(path) for path in linked],
                "command": command}
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    started = time.monotonic()
    with (directory / "build.log").open("w") as output:
        built = subprocess.run(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    evidence["build_exit"] = built.returncode
    if built.returncode == 0:
        evidence["binary"] = identity(directory / "check")
        with (directory / "run.log").open("w") as output:
            ran = subprocess.run([str(directory / "check")], cwd=ROOT,
                                 stdout=output, stderr=subprocess.STDOUT)
        evidence["run_exit"] = ran.returncode
        evidence["run_log"] = identity(directory / "run.log")
        print((directory / "run.log").read_text(), end="")
    evidence["elapsed_seconds"] = time.monotonic() - started
    evidence["complete"] = evidence.get("run_exit") == 0
    evidence["build_log"] = identity(directory / "build.log")
    # Guard against editing source while this focused build/run was active.
    for item in evidence["harness_inputs"]:
        if digest(item["path"]) != item["sha256"]:
            evidence["complete"] = False
            evidence["changed_during_run"] = item["path"]
    (directory / "result.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    if not evidence["complete"]:
        raise SystemExit(evidence.get("run_exit", built.returncode) or 1)


if __name__ == "__main__":
    main()
