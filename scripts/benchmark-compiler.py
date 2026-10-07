#!/usr/bin/env python3
"""Compare compiler revisions, including verification and xMLF emission.

Run with cabal bench compiler-bench --benchmark-options='compare-revisions
--before /path/to/saved-emlf'. Cabal supplies the current compiler and a
default report path. With no source arguments, compare all examples/*.emlf.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import statistics
import subprocess
import time


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def compile_file(binary, source):
    start = time.perf_counter()
    result = subprocess.run(
        [str(binary), str(source)], stdin=subprocess.DEVNULL, capture_output=True
    )
    elapsed = time.perf_counter() - start
    if result.returncode:
        raise RuntimeError(
            f"{binary} failed on {source}:\n{result.stderr.decode(errors='replace')}"
        )
    return elapsed, result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=Path)
    parser.add_argument("--after", required=True, type=Path)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("sources", nargs="*", type=Path,
                        default=sorted(Path("examples").glob("*.emlf")))
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    if not args.sources:
        parser.error("no example sources found; provide source files explicitly")
    binaries = {name: getattr(args, name).resolve(strict=True) for name in ("before", "after")}
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "scope": "Fresh serial processes, including parsing, inference, elaboration, "
                 "verification, and captured xMLF output; excludes building the compiler. "
                 "Execution order alternates each repetition. No untimed warmup.",
        "binaries": {
            name: {"path": str(binary), "sha256": digest(binary)}
            for name, binary in binaries.items()
        },
        "results": [],
    }
    for source in args.sources:
        source = source.resolve(strict=True)
        source_hash = digest(source)
        samples = {"before": [], "after": []}
        expected = None
        for repetition in range(args.runs):
            order = ("before", "after") if repetition % 2 == 0 else ("after", "before")
            for name in order:
                elapsed, output = compile_file(binaries[name], source)
                if expected is None:
                    expected = output
                elif output != expected:
                    raise RuntimeError(f"xMLF output mismatch: {name}, {source}")
                samples[name].append(elapsed)
        if digest(source) != source_hash:
            raise RuntimeError(f"source changed during measurement: {source}")
        # This extra parse/check is outside the compilation timing, and is
        # independent of the source inference engine. Check the persisted text.
        checked = subprocess.run(
            [str(binaries["after"]), "--check"], input=expected, capture_output=True
        )
        if checked.returncode:
            raise RuntimeError(f"emitted xMLF did not check: {checked.stderr.decode(errors='replace')}")
        medians = {name: statistics.median(times) for name, times in samples.items()}
        result = {
            "source": str(source),
            "source_sha256": source_hash,
            "samples_seconds": samples,
            "median_seconds": medians,
            "speedup": medians["before"] / medians["after"],
            "identical_xmlf": True,
            "xmlf_sha256": hashlib.sha256(expected).hexdigest(),
            "checked_type": checked.stdout.decode().strip(),
        }
        report["results"].append(result)
        print(f"{source.name}: {medians['before']:.4f}s -> {medians['after']:.4f}s "
              f"({result['speedup']:.2f}x); identical, checked xMLF", flush=True)
    for name, binary in binaries.items():
        if digest(binary) != report["binaries"][name]["sha256"]:
            raise RuntimeError(f"compiler changed during measurement: {binary}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
