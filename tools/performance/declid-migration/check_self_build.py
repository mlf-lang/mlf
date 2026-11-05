#!/usr/bin/env python3
"""Check a cold mlf-crates package build, warm compiler queries and package reuse."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/shared"))
from artifact_binary_reference import Invalid, read_document
from artifact_binary_typed import text, unpack
from query_generation import Generation


def file_receipt(path):
    with path.open("rb") as stream:
        return {"bytes": path.stat().st_size, "sha256": hashlib.file_digest(stream, "sha256").hexdigest()}


def run(argv, log):
    with log.open("wb") as stream:
        subprocess.run(argv, check=True, stdout=stream, stderr=subprocess.STDOUT, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("install", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    prefix = args.install.resolve(strict=True) / "bin"
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manager, compiler = prefix / "mlfpkg", prefix / "emlf"
    cache, build = out / "cache", out / "build"
    manifest = ROOT / "libraries/mlf-crates/mlf-package.json"
    package = json.loads(manifest.read_bytes())
    identity = f'{package["name"]}/{package["version"]}/library'
    command = [manager, "--offline", "--manifest", manifest, "--build-dir", build,
               "--cache-dir", cache, "--compiler", compiler, "--runtime", ROOT / "runtime/mlf_runtime.c",
               "--jobs", "1", "--timeout", "21600", "build"]
    spec = out / "mlf-crates.spec"
    with (out / "cold.log").open("wb") as log:
        with subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT) as proc:
            while proc.poll() is None:
                # mlfpkg removes the transient invocation file on publication.
                if not spec.exists():
                    for source in cache.glob("*.work-*/crate.spec"):
                        try:
                            contents = source.read_text()
                        except FileNotFoundError:
                            continue
                        try:
                            fields = unpack(contents)
                        except Invalid:
                            continue
                        if fields[:2] == ["MLF-CRATE-1", identity]:
                            spec.write_text(contents)
                            break
                time.sleep(2)
            if proc.returncode:
                raise subprocess.CalledProcessError(proc.returncode, command)
    cold_report = json.loads((build / "build-report.json").read_bytes())
    if not spec.is_file():
        raise ValueError("cold build did not expose the target compiler invocation")
    if not cold_report["complete"] or len(cold_report["builds"]) != 7 or any(row["cached"] for row in cold_report["builds"]):
        raise ValueError("cold package build did not check every dependency")
    unit, = [f.parent for f in cache.glob("*/unit.queries") if json.loads(f.read_bytes())["crate"] == identity]
    cold = json.loads((unit / "unit.queries").read_bytes())
    groups = cold["inferred_groups"]
    if not groups or cold["reused_groups"] or len(cold["groups"]) != groups:
        raise ValueError("cold compiler group accounting")
    pointer, = (cache / ".queries/mlf-crates").rglob("query-graph-v2/CURRENT")
    published = pointer.read_bytes()
    address = text(read_document(published, 6).values()[0])
    wire = (pointer.parent / "generations" / f"{address}.mlfqg").read_bytes()
    decoded = Generation(wire, expected_hash=address)
    products = {ext: file_receipt(unit / ("unit." + ext)) for ext in ["mlfci", "mlfco", "queries"]}
    run([compiler, "--compile-crate", spec, "-o", out / "warm"], out / "warm.log")
    warm = json.loads((out / "warm.queries").read_bytes())
    if (warm["inferred_groups"], warm["reused_groups"]) != (0, groups) or pointer.read_bytes() != published:
        raise ValueError("warm compiler did not retain the complete verified generation")
    for ext in ("mlfci", "mlfco"):
        if file_receipt(out / f"warm.{ext}") != products[ext]:
            raise ValueError(f"warm compiler changed {ext}")
    run(command, out / "package-reuse.log")
    reused = json.loads((build / "build-report.json").read_bytes())
    if not reused["complete"] or len(reused["builds"]) != len(cold_report["builds"]) or not all(
            row["cached"] for row in reused["builds"]):
        raise ValueError("second package build did not reuse all checked libraries")
    receipt = {"command": list(map(str, command)), "source_commit": subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "toolchain": cold_report["toolchain"],
        "compiler_host": subprocess.check_output([compiler, "--implementation-identity"], text=True).strip(),
        "cold": [groups, 0], "warm": [0, groups], "products": products,
        "published": address, "index_bytes": len(wire), "rows": len(decoded.nodes),
        "ordered_reads": sum(len(row["reads"]) for row in decoded.nodes.values()),
        "package_builds": cold_report["builds"], "package_reuse": reused["builds"]}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("self-build, query generation and package reuse passed", flush=True)


if __name__ == "__main__":
    main()
