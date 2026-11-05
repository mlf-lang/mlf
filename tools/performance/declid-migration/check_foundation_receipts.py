#!/usr/bin/env python3
"""Rebuild the tag 427 receipts for each arm of a completed Foundation study."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crate-query-graph"))
from verify import check_receipts, graph
from query_generation import cache_directory


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check_generation(cache, prefix, expected, output):
    address, nodes = graph(cache)
    if address != expected["generation"]:
        raise ValueError("published generation differs from the measured one")
    receipt = check_receipts(prefix, cache, nodes)
    if receipt["retained"] + receipt["rewritten"] != 504:
        raise ValueError("incomplete Foundation group inventory")
    wire = cache_directory(cache) / "generations" / (address + ".mlfqg")
    shutil.copyfile(wire, output)
    return {**receipt, "generation": address, "rows": len(nodes),
            "ordered_reads": sum(len(node["reads"]) for node in nodes.values()), "bytes": wire.stat().st_size}


def check_arm(study, report, output, arm, compiler):
    if digest(compiler) != report["binary_sha256"][arm]:
        raise ValueError(f"{arm} compiler differs from the measured one")
    seed = study / ("seed-cache-" + arm)
    results = {"seed": check_generation(seed, study / ("seed-" + arm), report["seeds"][arm]["graph"],
                                        output / (arm + "-seed.mlfqg"))}
    samples = {row["state"]: (index, row) for index, row in enumerate(report["samples"])
               if row["arm"] == arm and "graph" in row}
    for state in ("warm", "cold"):
        index, row = samples[state]
        results[state] = check_generation(seed, study / "legs" / str(index) / "unit", row["graph"],
                                          output / f"{arm}-{state}.mlfqg")

    # Timed legs discard their private caches. Reapply the same edit outside
    # the timer, then check the measured product digests and generation.
    source = study / "input/Bootstrap/Version.hs"
    original = source.read_bytes()
    if original.count(b'version = "0.3.0"') != 1:
        raise ValueError("unexpected Foundation version source")
    cache, builtin = study / "cache", study / "builtin"
    if cache.exists() or builtin.exists():
        raise ValueError("study has an active sample")
    cache.mkdir()
    try:
        shutil.copytree(seed, cache, dirs_exist_ok=True)
        shutil.copytree(study / ("seed-builtin-" + arm), builtin)
        source.write_bytes(original.replace(b'version = "0.3.0"', b'version = "0.3.1"'))
        prefix = output / (arm + "-edit")
        subprocess.run([compiler, "--compile-crate", study / "foundation.spec", "-o", prefix], cwd=study, check=True)
        _, row = samples["edit"]
        if any(digest(prefix.with_suffix(ext)) != expected for ext, expected in row["products"].items()):
            raise ValueError(f"{arm} edit replay changed compiler products")
        results["edit"] = check_generation(cache, prefix, row["graph"], output / (arm + "-edit.mlfqg"))
    finally:
        source.write_bytes(original)
        shutil.rmtree(cache)
        if builtin.exists():
            shutil.rmtree(builtin)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("study", type=Path)
    args = parser.parse_args()
    study = args.study.resolve(strict=True)
    report = json.loads((study / "results.json").read_bytes())
    if not report["complete"] or not report["normalized_group_members_equal"]:
        raise ValueError("incomplete Foundation study")
    output = study / "independent-receipts"
    output.mkdir(exist_ok=False)
    results = {arm: check_arm(study, report, output, arm, compiler.resolve(strict=True))
               for arm, compiler in (("before", args.before), ("after", args.after))}
    (output / "summary.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
