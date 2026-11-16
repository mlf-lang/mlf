#!/usr/bin/env python3
"""Read-only numeric provenance validator. Does not run MLF or reconstruct graphs."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from decimal import Decimal

MAX_BYTES = 8 * 1024 * 1024
U64 = (1 << 64) - 1
I64 = (1 << 63) - 1
COLUMNS = ("event site success words nodes h1 h2 encoding_ns action_whnf_ns "
           "first_equation first_fresh_external first_child first_binder "
           "first_structural_parent first_binding_child connected selected "
           "scope_added fresh_count stub_count equation_unique fresh_unique "
           "equation_fresh_overlap direct_union external_unique").split()
SITES = ("UnifyDistinct", "PreparedFallback")
ROUTES = COLUMNS[9:15]
PARTITION = ("connected", "scope_added", "fresh_count", "stub_count")
DIRECT = ("equation_unique", "fresh_unique", "equation_fresh_overlap",
          "direct_union", "external_unique")

def need(ok, message):
    if not ok:
        raise ValueError(message)

def natural(s, cap=U64):
    need(re.fullmatch(r"0|[1-9][0-9]*", s) is not None, "noncanonical unsigned integer")
    n = int(s)
    need(n <= cap, "integer overflow")
    return n

def read_bytes(path, expected_sha=None):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    need(0 < len(raw) <= MAX_BYTES, "empty or oversized TSV")
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha is not None:
        need(sha == expected_sha, "TSV SHA256 mismatch")
    need(raw.endswith(b"\n") and b"\r" not in raw, "require ASCII LF lines")
    raw.decode("ascii")
    return raw

def parse(raw, reference=False):
    lines = raw.decode("ascii").splitlines()
    need(len(lines) >= 4, "incomplete TSV")
    hd, footer = lines[0].split("\t"), lines[-1].split("\t")
    schema = "local-problem-digest-v2" if reference else "local-problem-provenance-v1"
    need(len(hd) == len(footer) == 5 and hd[0] == schema and footer[0] == "complete",
         "header/footer schema")
    header = [natural(v) for v in hd[1:]]
    need(footer[1:] == hd[1:], "header/footer mismatch")
    count, total_words, encoding, action = header
    need(0 < count <= 32768 and total_words <= 134217728, "global caps")
    columns = COLUMNS[:9] if reference else COLUMNS
    need(lines[1].split("\t") == columns, "column names/order")
    need(len(lines) == count + 3, "row count")
    rows = []
    for i, line in enumerate(lines[2:-1]):
        cells = line.split("\t")
        need(len(cells) == len(columns), "row width")
        need(cells[1] in SITES, "unknown route")
        values = {name: natural(cells[j]) for j, name in enumerate(COLUMNS[:9]) if j != 1}
        need(values["event"] == i and values["success"] in (0, 1), "event/success")
        need(values["words"] <= 1048576 and values["nodes"] <= 131072, "input caps")
        if not values["success"]:
            need(all(values[k] == 0 for k in ("words", "nodes", "h1", "h2")), "Left encoding")
        else:
            need(5 <= values["words"] and values["nodes"] <= values["words"], "Right encoding")
        eligible = bool(values["success"]) and 129 <= values["nodes"] <= 2048
        values.update(site=cells[1], first7=cells[:7], metadata=None)
        if not reference:
            if eligible:
                m = [natural(v, I64) for v in cells[9:]]
                a, b, c, d, e, f, connected, selected, scopes, fresh, stubs, eq, fu, ov, direct, external = m
                need(a+b+c+d+e+f == connected, "first-discovery conservation")
                need(selected == connected+scopes, "selected conservation")
                need(values["nodes"] == connected+scopes+fresh+stubs, "node partition")
                need(fresh == fu and ov <= min(eq, fu) and direct == eq+fu-ov, "direct-set arithmetic")
                need(direct <= selected+fresh and external <= selected and stubs <= selected,
                     "set-size bounds")
                need(a <= eq and b <= external, "seed-route bounds")
                values["metadata"] = dict(zip(COLUMNS[9:], m))
            else:
                need(cells[9:] == ["NA"]*16, "ineligible metadata must be NA")
        rows.append(values)
    need(sum(r["words"] for r in rows) == total_words, "word sum")
    need(sum(r["encoding_ns"] for r in rows) == encoding, "encoding sum")
    need(sum(r["action_whnf_ns"] for r in rows) == action, "action sum")
    # Deliberately no interval-sum <= external wall-time condition: re-entry can overlap.
    return rows

def stats(values):
    need(bool(values), "empty statistic")
    ordered = sorted(values)
    n = len(ordered)
    median = (Decimal(ordered[n//2]) if n % 2
              else (Decimal(ordered[n//2-1]) + Decimal(ordered[n//2])) / 2)
    return {"sum_decimal": str(sum(values)), "event_median_decimal": format(median, "f"),
            "event_max_decimal": str(ordered[-1])}

def summarize(raw, reference_raw=None):
    rows = parse(raw)
    chosen = [r for r in rows if r["metadata"] is not None]
    result = {
        "schema": "public-local-closure-provenance-analysis-v1",
        "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
        "events": len(rows), "right": sum(r["success"] for r in rows),
        "left": sum(1-r["success"] for r in rows), "selected_events": len(chosen),
        "selected_range": [129, 2048],
        "all_input_nodes_occurrences_decimal": str(sum(r["nodes"] for r in rows)),
        "total_words_decimal": str(sum(r["words"] for r in rows)),
        "reported_action_ns_sum_decimal": str(sum(r["action_whnf_ns"] for r in rows)),
        "reported_encoding_ns_sum_decimal": str(sum(r["encoding_ns"] for r in rows)),
        "first7_sha256": hashlib.sha256(
            "".join("\t".join(r["first7"])+"\n" for r in rows).encode("ascii")).hexdigest(),
        "selected_node_occurrences_decimal": str(sum(r["nodes"] for r in chosen)),
        "selected_reported_action_ns_sum_decimal": str(sum(r["action_whnf_ns"] for r in chosen)),
        "node_partition": {k: str(sum(r["metadata"][k] for r in chosen)) for k in PARTITION},
        "first_discovery_connected_totals": {k: str(sum(r["metadata"][k] for r in chosen)) for k in ROUTES},
        "overlapping_direct_size_totals": {k: str(sum(r["metadata"][k] for r in chosen)) for k in DIRECT},
        "sites": {},
        "interpretation": [
            "Node occurrences across selected events, not unique nodes or allocation.",
            "First-discovery route depends on DFS order; not incidence, necessity or avoidable work.",
            "Direct set sizes overlap and must not be added as a partition.",
            "Interval sums can overlap through thunk re-entry and include GC/scheduling.",
            "No exclusive CPU, CLI phase, speedup or automatic optimization admission.",
            "Fingerprint matches are not graph equality; numeric conservation is not an identity proof."
        ]
    }
    for site in SITES:
        rs = [r for r in rows if r["site"] == site]
        ss = [r for r in rs if r["metadata"] is not None]
        result["sites"][site] = {
            "events": len(rs), "right": sum(r["success"] for r in rs),
            "left": sum(1-r["success"] for r in rs), "selected_events": len(ss),
            "selected_input_nodes": stats([r["nodes"] for r in ss]) if ss else None,
            "selected_reported_action_ns": stats([r["action_whnf_ns"] for r in ss]) if ss else None,
            "metadata": {k: stats([r["metadata"][k] for r in ss]) if ss else None for k in COLUMNS[9:]}
        }
    need(sum(int(v) for v in result["node_partition"].values()) ==
         int(result["selected_node_occurrences_decimal"]), "aggregate node partition")
    need(sum(int(v) for v in result["first_discovery_connected_totals"].values()) ==
         int(result["node_partition"]["connected"]), "aggregate first discovery")
    if reference_raw is not None:
        old = parse(reference_raw, reference=True)
        need([r["first7"] for r in rows] == [r["first7"] for r in old], "reference first7 mismatch")
        result["reference_first7"] = {
            "byteexact": True, "raw_sha256": hashlib.sha256(reference_raw).hexdigest(),
            "timing_join": False,
            "meaning": "Ordered source/route/input fingerprint qualification, not raw graph equality."
        }
    return result

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tsv")
    parser.add_argument("--sha256")
    parser.add_argument("--reference-v4")
    parser.add_argument("--reference-sha256")
    args = parser.parse_args()
    raw = read_bytes(args.tsv, args.sha256)
    old = read_bytes(args.reference_v4, args.reference_sha256) if args.reference_v4 else None
    need(args.reference_v4 is not None or args.reference_sha256 is None, "reference path missing")
    print(json.dumps(summarize(raw, old), sort_keys=True, indent=2))

if __name__ == "__main__":
    main()
