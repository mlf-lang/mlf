"""List the benchmark workload cases without building a benchmark tool."""

import argparse
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def identities(workloads, *, check_only=False, prefix="benchmark-game"):
    kinds = ("correctness",) if check_only else ("correctness", "performance")
    return [f"{prefix}/{kind}/{workload['name']}" for workload in workloads for kind in kinds]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", action="append", default=[])
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--prefix", default="benchmark-game")
    args, _setup = parser.parse_known_args()
    workloads = json.loads((ROOT / "benchmarks/manifest.json").read_text())["workloads"]
    if args.workload:
        known = {workload["name"] for workload in workloads}
        if len(args.workload) != len(set(args.workload)) or not set(args.workload) <= known:
            parser.error("unknown or repeated application workload")
        workloads = [workload for workload in workloads if workload["name"] in args.workload]
    ids = identities(workloads, check_only=args.check_only, prefix=args.prefix)
    exact = os.environ.get("MLF_TEST_EXACT")
    if exact:
        if exact not in ids:
            parser.error("case outside the workload selection: " + exact)
        ids = [exact]
    print(json.dumps(ids))


if __name__ == "__main__":
    main()
