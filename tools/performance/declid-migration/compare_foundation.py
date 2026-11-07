#!/usr/bin/env python3
"""Compare logical versions/ordered edges and artifacts of both timed Foundation arms."""
import argparse
import gzip
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared"))
from artifact_binary_typed import unpack


def compare_graphs(before, after):
    if before.keys() != after.keys():
        missing = list(before.keys() - after.keys())
        extra = list(after.keys() - before.keys())
        raise ValueError(f"query keys differ: missing={missing[:3]} added={extra[:3]}")
    changed, reads = Counter(), 0
    for key, old in before.items():
        new = after[key]
        kind, identity = unpack(key)
        if kind == "Input":
            kind = "Input/" + unpack(identity)[0]
        if [edge[0] for edge in old["reads"]] != [edge[0] for edge in new["reads"]]:
            raise ValueError(f"ordered reads changed at {key}")
        for graph, node in ((before, old), (after, new)):
            for other, observed in node["reads"]:
                if observed != graph[other]["sha"]:
                    raise ValueError(f"stale read at {key}")
        reads += len(new["reads"])
        if (old["sha"], old["payload"]) != (new["sha"], new["payload"]):
            if kind != "Input/Prepared":
                raise ValueError(f"unexpected result or payload change at {key}")
            changed[kind] += 1
    return {"rows": len(before), "ordered_reads": reads, "changed_results": dict(changed)}


def compare(study):
    with (study / "results.json").open() as stream:
        result = json.load(stream)
    if not result["complete"] or not result["normalized_group_members_equal"]:
        raise ValueError("paired run incomplete or group membership changed")
    summary = {}
    for state in ("warm", "edit", "cold"):
        arms = {}
        for row in result["samples"]:
            if row["state"] == state and "graph" in row:
                arms[row["arm"]] = row
        before, after = arms["before"], arms["after"]
        for ext in (".mlfci", ".mlfco", ".queries"):
            if before["products"][ext] != after["products"][ext]:
                raise ValueError(f"{state} {ext} differs")
        def load_rows(arm):
            with gzip.open(study / arm["graph"]["logical_rows"], "rt") as stream:
                return json.load(stream)
        summary[state] = compare_graphs(load_rows(before), load_rows(after))
        if summary[state]["changed_results"] != {"Input/Prepared": 504}:
            raise ValueError(f"{state} did not change exactly one Prepared input per Foundation group")
        summary[state]["counts"] = after["counts"]
        summary[state]["products"] = after["products"]
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("study", type=Path)
    args = parser.parse_args()
    print(json.dumps(compare(args.study), indent=2))
