#!/usr/bin/env python3
"""Run exact finite library-reuse controls against a frozen diagnostic probe.

Case manifests carry independent acceptance, route, and byte-output oracles.
Positive cases cannot pass by both routes rejecting; required reuse cannot pass
through fallback. Timings are diagnostic only and have no performance meaning.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from compare import compare


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clang", type=Path)
    parser.add_argument("--runtime-object", type=Path)
    parser.add_argument("--gc-prefix", type=Path)
    parser.add_argument("--gmp-prefix", type=Path)
    args = parser.parse_args()
    probe, manifest_path = args.probe.resolve(strict=True), args.manifest.resolve(strict=True)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format") != "MLF-PREPARED-LIBRARY-CONTROLS-1":
        raise ValueError("unsupported qualification manifest")
    cases = manifest["cases"]
    if not cases or len({case["name"] for case in cases}) != len(cases):
        raise ValueError("qualification requires nonempty, uniquely named cases")
    if any(not case["name"].replace("-", "").replace("_", "").isalnum() for case in cases):
        raise ValueError("case names must be simple file-safe identifiers")
    native = any("native" in case.get("execute", []) for case in cases)
    if native and not all([args.clang, args.runtime_object, args.gc_prefix, args.gmp_prefix]):
        raise ValueError("native cases require explicit clang, runtime object, GC and GMP paths")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    files = {probe, manifest_path, Path(__file__).resolve(), Path(__file__).with_name("compare.py").resolve()}
    files.update(Path(path).resolve(strict=True) for path in manifest["inputs"])
    if native:
        files.update([args.clang.resolve(strict=True), args.runtime_object.resolve(strict=True)])
    pins = {str(path): sha(path) for path in sorted(files)}
    receipt = {"format": "MLF-PREPARED-LIBRARY-CONTROLS-1", "complete": False,
               "inputs": pins, "commands": [], "cases": [], "performance_assertions": False,
               "native_host_compiler_qualification": False, "user_program_cache": False,
               "scope": "finite exact acceptance, principal type, ordered layout and execution controls"}
    environment = {**os.environ, "LC_ALL": "C.UTF-8"}

    def save() -> None:
        (output / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    def run(name: str, command: list, stdin: bytes = b"") -> subprocess.CompletedProcess:
        start = time.monotonic()
        result = subprocess.run(list(map(str, command)), input=stdin, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=environment, check=False)
        (output / (name + ".stdout")).write_bytes(result.stdout)
        (output / (name + ".stderr")).write_bytes(result.stderr)
        receipt["commands"].append({"name": name, "argv": list(map(str, command)), "exit_code": result.returncode,
            "diagnostic_seconds": time.monotonic() - start, "stdout_sha256": hashlib.sha256(result.stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(result.stderr).hexdigest()})
        save()
        return result

    def exact(result: subprocess.CompletedProcess, oracle: dict, label: str) -> None:
        if (result.returncode, result.stdout, result.stderr) != (
                oracle["exit_code"], bytes.fromhex(oracle["stdout_hex"]), bytes.fromhex(oracle["stderr_hex"])):
            raise AssertionError(label + ": literal exit/stdout/stderr oracle failed")

    save()
    try:
        for case in cases:
            expected = case["accepted"]
            if not isinstance(expected, bool) or not isinstance(case["reused"], bool):
                raise ValueError("case acceptance/reuse oracles must be explicit booleans")
            request_path = Path(case["request"]).resolve(strict=True)
            if str(request_path) not in pins:
                raise ValueError("case request is absent from manifest inputs")
            request = json.loads(request_path.read_text())
            root_buffer = request.get("buffer_path", request["source_path"])
            if str(Path(root_buffer).resolve(strict=True)) not in pins:
                raise ValueError("root buffer is not pinned")
            buffers = {request["source_path"]: root_buffer}
            for row in request.get("source_map", []):
                if str(Path(row["buffer_path"]).resolve(strict=True)) not in pins:
                    raise ValueError("provided dependency buffer is not pinned")
                if row["source_path"] in buffers:
                    raise ValueError("provided source map repeats a lexical source path")
                buffers[row["source_path"]] = row["buffer_path"]
            reports = []
            for route in ["ordinary", "prepared"]:
                result = run(case["name"] + "-" + route + "-inspect", [probe, "inspect", route, request_path])
                if result.returncode or result.stderr:
                    raise AssertionError(case["name"] + ": probe inspection failed")
                report = json.loads(result.stdout)
                for read in report["source_reads"]:
                    consumed = Path(buffers.get(read["path"], read["path"])).resolve(strict=True)
                    if str(consumed) not in pins or consumed.read_bytes().decode("utf-8") != read["text"]:
                        raise ValueError("probe consumed an unpinned or mismatched source buffer: " + read["path"])
                reports.append(report)
            if reports[0]["source_reads"] != reports[1]["source_reads"]:
                raise ValueError("ordinary/prepared probes loaded different source graphs")
            compare(*reports, "accepted" if expected else "rejected", case["reused"])
            if not expected and "error" in case and reports[0]["error"] != case["error"]:
                raise AssertionError(case["name"] + ": independent exact error oracle failed")
            executed = []
            for engine in case.get("execute", []):
                if not expected or engine not in {"interpreter", "native"}:
                    raise ValueError("invalid execution case")
                stdin = bytes.fromhex(case.get("stdin_hex", ""))
                if engine == "interpreter":
                    for route in ["ordinary", "prepared"]:
                        result = run(case["name"] + "-" + route + "-run", [probe, "run", route, request_path], stdin)
                        exact(result, case["interpreter"], case["name"] + "/" + route)
                else:
                    for route in ["ordinary", "prepared"]:
                        stem = case["name"] + "-" + route
                        emitted = run(stem + "-emit", [probe, "emit", route, request_path])
                        if emitted.returncode or emitted.stderr:
                            raise AssertionError(stem + ": LLVM emission failed")
                        llvm = output / (stem + ".ll")
                        llvm.write_bytes(emitted.stdout)
                        for level in ["0", "2"]:
                            executable = output / (stem + "-O" + level)
                            linked = run(stem + "-link-O" + level, [args.clang, "-O" + level, llvm,
                                args.runtime_object, "-L" + str(args.gc_prefix / "lib"),
                                "-L" + str(args.gmp_prefix / "lib"), "-lgc", "-lgmp", "-lm", "-o", executable])
                            if linked.returncode:
                                raise AssertionError(stem + ": native link failed")
                            result = run(stem + "-native-O" + level,
                                         [executable, *request.get("arguments", [])], stdin)
                            exact(result, case["native"], stem + "/O" + level)
                executed.append(engine)
            receipt["cases"].append({"name": case["name"], "passed": True,
                "accepted": expected, "reused": case["reused"], "executed": executed})
            save()
        receipt["complete"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        changed = [path for path, digest in pins.items() if sha(Path(path)) != digest]
        receipt["immutable_inputs_verified_after"] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
    print(output / "receipt.json")


if __name__ == "__main__":
    main()
