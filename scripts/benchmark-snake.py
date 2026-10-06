#!/usr/bin/env python3
"""Measure verified Snake compilation against a fresh GHC compile and link.

Run after `cabal build exe:emlf -j1`. Each compiler runs in a fresh process;
GHC uses -fforce-recomp on every sample. No cached game build or untimed
compilation warmup is used. This is a manual performance gate, not a timing-sensitive
unit test: every paired sample must meet --max-ratio (default 5).
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import tempfile
import time


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def run(command, data=None):
    started = time.perf_counter()
    result = subprocess.run(command, input=data, capture_output=True, timeout=300)
    elapsed = time.perf_counter() - started
    if result.returncode:
        raise RuntimeError(f"{command} failed:\n{result.stderr.decode(errors='replace')}")
    return elapsed, result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emlf", required=True, type=Path)
    parser.add_argument("--ghc", default="ghc")
    parser.add_argument("--source", type=Path, default=Path("examples/snake.emlf"))
    parser.add_argument("--baseline", type=Path, default=Path("examples/SnakeBaseline.hs"))
    parser.add_argument("--reference-xmlf", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-ratio", type=float, default=5)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.runs < 1 or not math.isfinite(args.max_ratio) or args.max_ratio <= 0:
        parser.error("--runs and --max-ratio must be positive")
    emlf = args.emlf.resolve(strict=True)
    ghc = shutil.which(args.ghc)
    if ghc is None:
        parser.error(f"GHC not found: {args.ghc}")
    source = args.source.resolve(strict=True)
    baseline = args.baseline.resolve(strict=True)
    fingerprints = {str(p): digest(p) for p in (emlf, Path(ghc), source, baseline)}
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "ghc_version": run([ghc, "--numeric-version"])[1].decode().strip(),
        "ghcrts_environment": os.environ.get("GHCRTS"),
        "scope": "eMLF source to verified, captured xMLF; GHC source to a linked native executable. "
                 "Includes process startup; excludes building emlf and running either game. "
                 "Serial fresh processes, alternating order, no untimed warmup. "
                 "GHC recompiles and links on every sample.",
        "sha256": fingerprints,
        "max_ratio": args.max_ratio,
        "pairs": [],
    }
    expected = args.reference_xmlf.read_bytes() if args.reference_xmlf else None
    samples = {"emlf": [], "ghc": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="snake-ghc-", dir=args.output.parent) as scratch:
        scratch = Path(scratch).resolve()
        native = scratch / "snake-haskell"
        commands = {
            "emlf": [str(emlf), str(source)],
            "ghc": [ghc, "-O2", "-Wall", "-Werror", "-fforce-recomp", "-main-is", "SnakeBaseline",
                    str(baseline), "-outputdir", str(scratch), "-o", str(native)],
        }
        report["commands"] = commands
        for repetition in range(args.runs):
            order = ["emlf", "ghc"] if repetition % 2 == 0 else ["ghc", "emlf"]
            pair = {"order": order}
            for name in order:
                elapsed, output = run(commands[name])
                samples[name].append(elapsed)
                pair[name + "_seconds"] = elapsed
                if name == "emlf":
                    if expected is None:
                        expected = output
                    elif output != expected:
                        raise RuntimeError("xMLF differs between samples or from --reference-xmlf")
            pair["ratio"] = pair["emlf_seconds"] / pair["ghc_seconds"]
            report["pairs"].append(pair)
            print(f"Run {repetition + 1}: eMLF {pair['emlf_seconds']:.4f}s; "
                  f"GHC {pair['ghc_seconds']:.4f}s; {pair['ratio']:.2f}x", flush=True)
        report["checked_type"] = run([str(emlf), "--check"], expected)[1].decode().strip()
        if report["checked_type"] != "IO Unit":
            raise RuntimeError(f"Unexpected Snake type: {report['checked_type']}")
        xmlf = args.output.with_suffix(".xmlf")
        xmlf.write_bytes(expected)
        # Outside the compilation timings: check a complete game transcript
        # against the executable produced by the final GHC sample.
        inputs = b"d\n\nw\na\nq\n"
        haskell_output = run([str(native)], inputs)[1]
        emlf_output = run([str(emlf), "--run-xmlf", str(xmlf)], inputs)[1]
        if haskell_output != emlf_output:
            raise RuntimeError("Snake transcript differs from the Haskell baseline")
        report["transcript_matches_haskell"] = True
    for filename, fingerprint in fingerprints.items():
        if digest(Path(filename)) != fingerprint:
            raise RuntimeError(f"Input or compiler changed during measurement: {filename}")
    medians = {name: statistics.median(times) for name, times in samples.items()}
    report.update({
        "samples_seconds": samples,
        "median_seconds": medians,
        "median_ratio": medians["emlf"] / medians["ghc"],
        "worst_pair_ratio": max(pair["ratio"] for pair in report["pairs"]),
        "xmlf_sha256": hashlib.sha256(expected).hexdigest(),
        "identical_to_reference": args.reference_xmlf is not None,
    })
    report["passed"] = report["worst_pair_ratio"] <= args.max_ratio
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Median: eMLF {medians['emlf']:.4f}s; GHC {medians['ghc']:.4f}s; "
          f"{report['median_ratio']:.2f}x; {'PASS' if report['passed'] else 'FAIL'}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
