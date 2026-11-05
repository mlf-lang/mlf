#!/usr/bin/env python3
"""Compare the installed compilers on the five source workloads used for #43."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "compiler-shapes"))
from installed import workloads


def invoke(argv):
    return subprocess.run(argv, check=True, capture_output=True, timeout=360).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    compilers = [exe.resolve(strict=True) for exe in (args.before, args.after)]
    summary = {}
    for name, case in workloads(out / "sources", 16).items():
        directory = Path(case["directory"])
        versions = []
        for side, exe in zip(("before", "after"), compilers):
            program = out / f"{name}-{side}.xmlf"
            program.write_bytes(invoke([exe, "-i", directory, directory / "Main.hs"]))
            versions.append(program)
        first, last = versions
        if first.stat().st_size == 0 or first.read_bytes() != last.read_bytes():
            raise ValueError(f"{name}: emitted xMLF differs")
        for exe, program in zip(compilers, reversed(versions)):
            invoke([exe, "--check", program])
            for x, expected in case["oracle"].items():
                actual = invoke([exe, "--run-xmlf", program, "--", x]).decode()
                if actual != expected:
                    raise ValueError(f"{name}({x}): {actual!r} != {expected!r}")
        summary[name] = {"bytes": first.stat().st_size, "sha256": hashlib.sha256(first.read_bytes()).hexdigest(),
                         "cross_checked": True, "runtime_cases_per_reader": case["oracle"]}
    (out / "checks.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
