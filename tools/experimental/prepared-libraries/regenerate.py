#!/usr/bin/env python3
"""Independently regenerate a completed job at its exact artifact path profile.

The first outputs are backed up before the second generator executes. The
producer is rebuilt in fresh object directories, with fresh host objects and a
fresh query directory. This proves only same-path-profile byte reproducibility;
neither source provenance nor artifact dependency paths are normalized.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    job = args.job.resolve(strict=True)
    first = json.loads((job / "build/receipt.json").read_text())
    required_steps = {"build-generate-prepared-libraries", "generate"}
    completed_steps = {row["label"] for row in first["commands"] if row["exit_code"] == 0}
    if not required_steps <= completed_steps or not first.get("immutable_inputs_verified_after"):
        raise ValueError("regeneration requires successful immutable first producer steps")
    request = json.loads((job / "request.json").read_text())
    product = first["generated_product"]
    if product != json.loads((job / "artifacts/generation.json").read_text()):
        raise ValueError("first generation receipt changed")
    source_pins = json.loads((job / "source-pins.json").read_text())
    inputs = {value["snapshot"]: value["sha256"] for value in source_pins.values()}
    inputs[first["canonical_snapshot_registry"]] = first.get("canonical_string_pool", {}).get(
        "pooled_sha256", product["generated_sha256"])
    inputs.update(first["tools"])
    inputs[first["generator"]["path"]] = first["generator"]["sha256"]
    for path, digest in inputs.items():
        if sha(Path(path)) != digest:
            raise ValueError("first-build input changed: " + path)
    expected = {product["generated_source"]: product["generated_sha256"]}
    for artifact in product["artifacts"]:
        for field in ["metadata", "object"]:
            expected[artifact[field + "_path"]] = artifact[field + "_sha256"]
    # Only outputs owned by this job may be overwritten by regeneration.
    for path, digest in expected.items():
        target = Path(path)
        if not target.is_relative_to(job) or sha(target) != digest:
            raise ValueError("first output ownership/digest mismatch: " + path)
    work = job / "regeneration"
    work.mkdir(exist_ok=False)
    backup = work / "first"
    backup.mkdir()
    backups = {}
    for index, (path, digest) in enumerate(expected.items()):
        copied = backup / (str(index) + "-" + Path(path).name)
        copied.write_bytes(Path(path).read_bytes())
        copied.chmod(0o444)
        backups[path] = {"path": str(copied), "sha256": digest}
    for name in ["request.json", "build/receipt.json", "artifacts/generation.json"]:
        target = backup / name.replace("/", "-")
        target.write_bytes((job / name).read_bytes())
        target.chmod(0o444)
    objects = work / "objects"
    objects.mkdir()
    second_request = dict(request)
    second_request["query_directory"] = str(work / "fresh-queries")
    request_file = work / "request.json"
    request_file.write_text(json.dumps(second_request, indent=2, sort_keys=True) + "\n")
    receipt = {"format": "MLF-PREPARED-LIBRARY-REGENERATION-1", "complete": False,
               "scope": "same lexical source and artifact paths; fresh producer and query cache",
               "cross_job_byte_reproducibility": False, "source_or_artifact_path_relocation": False,
               "input_identity": request["input_identity"], "first_full_build_complete": first["complete"],
               "inputs": inputs,
               "first_outputs": backups, "commands": [], "comparisons": [],
               "request_sha256": sha(request_file), "query_directory": second_request["query_directory"],
               "native_qualification": False, "performance_assertions": False}

    def save() -> None:
        (work / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    def run(label: str, command: list[str]) -> None:
        started = time.monotonic()
        with (work / (label + ".stdout")).open("wb") as stdout, (work / (label + ".stderr")).open("wb") as stderr:
            result = subprocess.run(command, cwd=job / "sources",
                env={**os.environ, "GHC_ENVIRONMENT": "-", "GHCRTS": "", "LC_ALL": "C.UTF-8"},
                stdout=stdout, stderr=stderr, check=False)
        receipt["commands"].append({"label": label, "argv": command, "exit_code": result.returncode,
                                    "diagnostic_seconds": time.monotonic() - started})
        save()
        if result.returncode:
            raise RuntimeError(label + " failed; first outputs remain in the immutable backup")

    def prior(label: str) -> list[str]:
        commands = [entry["argv"] for entry in first["commands"] if entry["label"] == label]
        if len(commands) != 1:
            raise ValueError("first build does not have one exact " + label + " command")
        return list(commands[0])

    save()
    try:
        transports = {}
        for name in ["host", "supervisor"]:
            command = prior(name)
            index = command.index("-o") + 1
            before = command[index]
            command[index] = str(work / (name + ".o"))
            transports[before] = command[index]
            run("rebuild-" + name, command)
        command = [transports.get(value, value) for value in prior("build-generate-prepared-libraries")]
        for flag in ["-odir", "-hidir"]:
            command[command.index(flag) + 1] = str(objects)
        executable = work / "generate-prepared-libraries"
        command[command.index("-o") + 1] = str(executable)
        command.insert(1, "-fforce-recomp")
        run("rebuild-generator", command)
        receipt["independent_generator"] = {"path": str(executable), "sha256": sha(executable)}
        if Path(second_request["query_directory"]).exists():
            raise ValueError("independent query directory already exists")
        run("regenerate", [str(executable), str(request_file)])
        for path, record in backups.items():
            original = Path(record["path"]).read_bytes()
            current = Path(path).read_bytes()
            equal = original == current
            receipt["comparisons"].append({"path": path, "first_sha256": record["sha256"],
                                           "second_sha256": sha(Path(path)), "bytes_equal": equal})
            save()
            if not equal:
                raise AssertionError("same-path regeneration changed exact output: " + path)
        receipt["complete"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        changed = [path for path, digest in inputs.items() if sha(Path(path)) != digest]
        changed += [value["path"] for value in backups.values()
                    if sha(Path(value["path"])) != value["sha256"]]
        if sha(request_file) != receipt["request_sha256"]:
            changed.append(str(request_file))
        receipt["immutable_inputs_verified_after"] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
    print(work / "receipt.json")


if __name__ == "__main__":
    main()
