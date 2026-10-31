#!/usr/bin/env python3
"""Execute a staged producer/probe build after the source freeze is approved.

The generated module replaces its registered canonical path in the owned
snapshot. No include-path overlay, live source mutation, or benchmark dispatch
is used. This is host diagnostic preparation, not native-host qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import time

HERE = Path(__file__).resolve().parent


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", type=Path, required=True)
    parser.add_argument("--ghc", type=Path, required=True)
    parser.add_argument("--cc", type=Path, required=True)
    parser.add_argument("--generate-only", action="store_true")
    args = parser.parse_args()
    job = args.job.resolve(strict=True)
    snapshot = job / "sources"
    pins = json.loads((job / "source-pins.json").read_text())
    for value in pins.values():
        if sha(Path(value["snapshot"])) != value["sha256"]:
            raise ValueError("staged source changed before build: " + value["snapshot"])
    ghc, cc = args.ghc.resolve(strict=True), args.cc.resolve(strict=True)
    build = job / "build"
    build.mkdir(exist_ok=False)
    description = json.loads((snapshot / "shared-sources.json").read_text())
    source_roots = [snapshot / value for value in description["source_roots"]]
    tool = snapshot / "tools/experimental/prepared-libraries"
    receipt = {"format": "MLF-PREPARED-LIBRARY-BUILD-1", "complete": False,
               "input_identity": json.loads((job / "request.json").read_text())["input_identity"],
               "tools": {str(ghc): sha(ghc), str(cc): sha(cc)}, "commands": [],
               "production_source_changed": False, "native_qualification": False,
               "native_object_reuse": False, "user_program_cache": False,
               "performance_assertions": False}
    expected = {value["snapshot"]: value["sha256"] for value in pins.values()}
    environment = {**os.environ, "GHC_ENVIRONMENT": "-", "GHCRTS": "", "LC_ALL": "C.UTF-8"}

    def save() -> None:
        (build / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    def run(label: str, command: list) -> None:
        start = time.monotonic()
        with (build / (label + ".stdout")).open("wb") as stdout, (build / (label + ".stderr")).open("wb") as stderr:
            result = subprocess.run(list(map(str, command)), cwd=snapshot, env=environment,
                                    stdout=stdout, stderr=stderr, check=False)
        receipt["commands"].append({"label": label, "argv": list(map(str, command)),
                                    "exit_code": result.returncode, "diagnostic_seconds": time.monotonic() - start})
        save()
        if result.returncode:
            raise RuntimeError(label + " failed; inspect its saved stderr")

    def compile_tool(name: str, source: str) -> Path:
        objects = build / (name + "-objects")
        objects.mkdir()
        flags = ["-XHaskell2010", "-package-env", "-", "-clear-package-db", "-global-package-db",
                 "-no-user-package-db", "-hide-all-packages", "-O2", "-fpedantic-bottoms", "-fno-state-hack",
                 "-Werror=incomplete-patterns", "-Werror=incomplete-uni-patterns", "-Wno-star-is-type",
                 "-Wno-overlapping-patterns", "-Wno-deprecations", "-i",
                 *["-i" + str(path) for path in source_roots], "-odir", objects, "-hidir", objects]
        for package in ["base", "array", "bytestring", "text", "containers", "directory"]:
            flags += ["-package", package]
        executable = build / name
        run("build-" + name, [ghc, "--make", "-j1", *flags, tool / source,
                              build / "host.o", build / "supervisor.o", "-o", executable])
        return executable

    save()
    try:
        for label, source in [("host", "host/ghc/cbits/host.c"), ("supervisor", "runtime/mlf_process_supervisor.c")]:
            run(label, [cc, "-O2", "-std=c11", "-I" + str(snapshot / "runtime"), "-c", snapshot / source,
                        "-o", build / (label + ".o")])
        generator = compile_tool("generate-prepared-libraries", "Generate.hs")
        run("generate", [generator, job / "request.json"])
        product = json.loads((job / "artifacts/generation.json").read_text())
        generated = Path(product["generated_source"])
        if sha(generated) != product["generated_sha256"]:
            raise ValueError("generated registry digest mismatch")
        for artifact in product["artifacts"]:
            for field in ["metadata", "object"]:
                if sha(Path(artifact[field + "_path"])) != artifact[field + "_sha256"]:
                    raise ValueError("generated artifact digest mismatch")
        canonical = snapshot / "bootstrap/MLF/PreparedLibraryData.hs"
        pool = runpy.run_path(str(snapshot / "tools/shared/pool_generated_strings.py"))["pool"]
        pooled, proof = pool(generated.read_bytes().decode("utf-8"))
        canonical.write_bytes(pooled.encode("utf-8"))
        expected[str(canonical)] = proof["pooled_sha256"]
        receipt["canonical_string_pool"] = proof
        receipt["generated_product"] = product
        receipt["canonical_snapshot_registry"] = str(canonical)
        receipt["generator"] = {"path": str(generator), "sha256": sha(generator)}
        if not args.generate_only:
            for name, source in [("prepared-library-probe", "Probe.hs"), ("loader-controls", "LoaderControls.hs")]:
                executable = compile_tool(name, source)
                receipt[name] = {"path": str(executable), "sha256": sha(executable)}
        receipt["complete"] = True
    except BaseException as error:
        receipt["error"] = repr(error)
        raise
    finally:
        changed = [path for path, digest in expected.items() if sha(Path(path)) != digest]
        changed += [path for path, digest in receipt["tools"].items() if sha(Path(path)) != digest]
        receipt["immutable_inputs_verified_after"] = not changed
        if changed:
            receipt.update(complete=False, changed_inputs=changed)
        save()
    print(build / "receipt.json")


if __name__ == "__main__":
    main()
