"""Bind the provenance shell adapter to the manifest's exact patch inventory."""

import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/testing"))
import events


def main():
    manifest = json.loads((ROOT / "benchmarks/manifest.json").read_text())
    names = ["manifest", "pinned-inputs", "transition", "transition-controls",
             "reconciliation/ordinary", "reconciliation/optimized", "predecessor/declid",
             "predecessor/declid-optimized", "predecessor/main", "predecessor/main-optimized",
             "adaptation-inventory"]
    names.extend("adaptation/" + source["build_source"]
                 for work in manifest["workloads"] for source in work["provenance"].values()
                 if source["original_source"] != source["build_source"])
    ids = ["benchmark-provenance/" + name for name in names]
    exact = (os.environ.get("MLF_TEST_EXACT")
             if os.environ.get("MLF_TEST_SUITE") == "benchmark-provenance" else None)
    if exact:
        if exact not in ids:
            raise SystemExit("unknown benchmark provenance case: " + exact)
        ids = [exact]
    if sys.argv[1:] == ["--framework-list"]:
        print(json.dumps(ids))
    else:
        events.plan(ids)


if __name__ == "__main__":
    main()
