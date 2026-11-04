#!/usr/bin/env python3
"""Compare two CodecProbe decoders with alternating, paired samples."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("native", "interpreter"), required=True)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, help="emlf for --backend interpreter")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--schema", type=int, required=True)
    parser.add_argument("--iterations", type=int, required=True)
    parser.add_argument("--rounds", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.iterations < 1 or args.rounds < 1:
        parser.error("iterations and rounds must be positive")
    if args.backend == "interpreter" and args.compiler is None:
        parser.error("--compiler is required for the interpreter backend")

    probes = {"before": args.before.resolve(strict=True), "after": args.after.resolve(strict=True)}
    source = args.input.resolve(strict=True)
    compiler = args.compiler.resolve(strict=True) if args.compiler else None
    env = dict(os.environ, GHCRTS="", GHC_ENVIRONMENT="-", LANG="C.UTF-8", LC_ALL="C.UTF-8", TZ="UTC")
    result = {
        "complete": False,
        "backend": args.backend,
        "input_sha256": sha256(source),
        "input_bytes": source.stat().st_size,
        "probe_sha256": {side: sha256(path) for side, path in probes.items()},
        "compiler_sha256": sha256(compiler) if compiler else None,
        "schema": args.schema,
        "iterations": args.iterations,
        "rounds": args.rounds,
        "samples": [],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise FileExistsError(args.output)

    def save():
        args.output.write_text(json.dumps(result, indent=2) + "\n")

    save()
    expected = None
    for index in range(args.rounds):
        for side in (("before", "after") if index % 2 == 0 else ("after", "before")):
            prefix = [str(probes[side])] if args.backend == "native" else [
                str(compiler), "--run-xmlf", str(probes[side]), "--"
            ]
            command = [*prefix, "timed", str(source), str(args.schema), str(args.iterations)]
            with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
                start = time.monotonic_ns()
                process = subprocess.Popen(command, stdout=out, stderr=err, stdin=subprocess.DEVNULL, env=env)
                _, status, usage = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
                wall = (time.monotonic_ns() - start) / 1e9
                out.seek(0)
                err.seek(0)
                stdout, stderr = out.read(), err.read()
            if process.returncode or stderr:
                raise RuntimeError(f"{side} failed ({process.returncode}): {stderr[:1000]!r}")
            total, milliseconds = map(int, stdout.split())
            if expected is None:
                expected = total
            if total != expected:
                raise ValueError(f"{side} produced {total}, expected {expected}")
            rss = usage.ru_maxrss if sys.platform == "darwin" else usage.ru_maxrss * 1024
            result["samples"].append({"round": index + 1, "side": side, "decode_ms": milliseconds,
                                      "wall_s": wall, "cpu_s": usage.ru_utime + usage.ru_stime,
                                      "peak_rss_bytes": rss})
            save()

    means = {side: statistics.mean(sample["decode_ms"] for sample in result["samples"]
                                   if sample["side"] == side) for side in probes}
    result["total"] = expected
    result["mean_decode_ms"] = means
    result["complete"] = True
    save()
    print(json.dumps(result["mean_decode_ms"], sort_keys=True))


if __name__ == "__main__":
    main()
