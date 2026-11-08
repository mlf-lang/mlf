#!/usr/bin/env python3
"""Replay a pinned query snapshot against exact reference and candidate sources.

This GHC-hosted diagnostic checks semantics, not native-MLF qualification or
the performance of the native compiler. The shared-language driver can also
be compiled through the ordinary native crate path using checked dependencies.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools/shared"))
from artifact_binary_reference import read_document, tree_document
from artifact_binary_typed import pack
from query_generation import Generation

MODULE = Path("libraries/mlf-crates/Bootstrap/QueryGraph.hs")
BASELINE = "1ce9f25eecf8283cd818ba79ea5d751ab05d0df4"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def tool(name):
    resolved = shutil.which(str(name))
    if resolved is None:
        raise ValueError(f"tool not found: {name}")
    return Path(resolved).resolve(strict=True)


def renamed(raw, name):
    old = b"module Bootstrap.QueryGraph where {"
    if raw.count(old) != 1:
        raise ValueError("expected exactly one QueryGraph module declaration")
    return raw.replace(old, f"module Diagnostic.{name} where {{".encode(), 1)


def synthetic_generation():
    """Independent V2 fixture with every descriptor, Unicode and repeated reads."""
    n = lambda tag, *children: ("node", tag, children)
    text = lambda value: ("text", value)
    integer = lambda value: ("int", value)
    key = lambda kind, identity: pack([kind, identity])
    group = pack(["b", "a"])
    request = pack([group, "19", "Eq λ"])
    zero, one = "0" * 64, "1" * 64
    definitions = [
        (key("Binding", "a"), integer(0), [], zero, False),
        (key("Binding", "b"), integer(1), [key("Binding", "a"), key("Binding", "a")], zero, False),
        (key("Binding", "λ"), integer(2), [key("Binding", "b")], one, True),
        (key("Input", key("Binding", "a")), n(415, integer(0)), [], zero, False),
        (key("Input", key("Prepared", group)), n(416, integer(0)), [], zero, False),
        (key("Input", key("ScopeInventory", group)), n(417, integer(0)), [], zero, False),
        (key("Scope", group), n(418, integer(0)), [key("Input", key("ScopeInventory", group))], zero, False),
        (key("InferScc", group), n(419, integer(0)),
         [key("Scope", group), key("Binding", "b"), key("Binding", "a"), key("Binding", "b")], zero, False),
        (key("FinishScc", group), n(431, integer(0)), [key("InferScc", group)], zero, False),
        (key("Evidence", request), n(432, integer(0)), [key("FinishScc", group)], one, True),
        (key("Datatype", "T"), n(433, integer(0)), [], zero, False),
        (key("Input", key("Datatype", "T")), n(434, integer(0)), [], zero, False),
    ]
    descriptors = {name: descriptor for name, descriptor, *_ in definitions}
    rows = [n(413, descriptor, text(digest), n(1, *(descriptors[r] for r in reads)),
              n(5, text(digest)) if payload else n(4))
            for _, descriptor, reads, digest, payload in sorted(definitions)]
    config = b"synthetic-boundary-control"
    root = n(412, text("MLF-CRATE-QUERY-GRAPH-2"), text(config.decode()),
             n(1, *(text(name) for name in ["a", "b", "λ"])),
             n(1, n(1, integer(1), integer(0))),
             n(1, n(414, integer(0), integer(19), text("Eq λ"))),
             n(1, text("T")), n(1, *rows))
    return tree_document([root], schema=6), config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-ref", default=BASELINE)
    parser.add_argument("--ghc", default="ghc")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"))
    parser.add_argument("--timeout", type=int, default=360)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    reference_sha = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.reference_ref + "^{commit}"], cwd=ROOT, text=True).strip()
    reference = subprocess.check_output(["git", "show", f"{reference_sha}:{MODULE}"], cwd=ROOT)
    candidate = (ROOT / MODULE).read_bytes()
    raw, config = args.input.resolve(strict=True).read_bytes(), args.config.resolve(strict=True).read_bytes()
    generation = Generation(raw, configuration=config.decode())
    accounting = read_document(raw, 6).accounting()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    modules = out / "Diagnostic"
    modules.mkdir()
    (modules / "ReferenceQueryGraph.hs").write_bytes(renamed(reference, "ReferenceQueryGraph"))
    (modules / "CandidateQueryGraph.hs").write_bytes(renamed(candidate, "CandidateQueryGraph"))
    (out / "QueryGraphBoundary.hs").write_bytes((HERE / "QueryGraphBoundary.hs").read_bytes())
    (out / "generation.mlfqg").write_bytes(raw)
    (out / "config.txt").write_bytes(config)
    synthetic_raw, synthetic_config = synthetic_generation()
    (out / "synthetic.mlfqg").write_bytes(synthetic_raw)
    (out / "synthetic-config.txt").write_bytes(synthetic_config)
    synthetic = Generation(synthetic_raw, configuration=synthetic_config.decode())
    if sum(len(n["reads"]) - len(set(n["reads"])) for n in synthetic.nodes.values()) != 2:
        raise ValueError("synthetic duplicate-read oracle changed")
    dependencies = sorted([*ROOT.glob("libraries/**/*.hs"), *ROOT.glob("host/ghc/**/*.hs")])
    dependencies += [ROOT / "host/ghc/cbits/host.c", ROOT / "runtime/mlf_process_supervisor.c",
                     ROOT / "runtime/mlf_process_supervisor.h", HERE / "QueryGraphBoundary.hs", Path(__file__)]
    dependencies += [ROOT / "tools/shared" / name for name in
                     ("query_generation.py", "artifact_binary_reference.py", "artifact_binary_typed.py")]
    pins = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in dependencies}
    ghc, cc, python = tool(args.ghc), tool(args.cc), Path(sys.executable).resolve(strict=True)
    record = dict(complete=False, qualification=False, scope="GHC-hosted QueryGraph boundary semantic diagnostic",
                  reference_commit=reference_sha, reference_source_sha256=sha(reference),
                  candidate_source_sha256=sha(candidate), dependencies=pins,
                  toolchain={str(p): sha(p.read_bytes()) for p in [ghc, cc, python]},
                  timing_scope="Host diagnostic only; both node maps and all fields are forced before encoder timing. Not native performance qualification.",
                  input_sha256=sha(raw), config_sha256=sha(config),
                  input_accounting=accounting, query_nodes=len(generation.nodes),
                  ordered_reads=sum(len(n["reads"]) for n in generation.nodes.values()),
                  fixed_negative_cases=12,
                  synthetic=dict(sha256=sha(synthetic_raw), query_nodes=len(synthetic.nodes), duplicate_reads=2),
                  commands=[])
    def save():
        (out / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    save()
    env = dict(os.environ, GHCRTS="", GHC_ENVIRONMENT="-", LANG="C.UTF-8", LC_ALL="C.UTF-8", TZ="UTC")
    for key in ("MLF_QUERY_PROFILE", "MLF_QUERY_FAILPOINT", "MLF_QUERY_SEMANTIC_AUDIT"):
        env.pop(key, None)

    def run(label, argv, extra=None):
        stdout, stderr = out / (label + ".stdout"), out / (label + ".stderr")
        row = dict(label=label, argv=list(map(str, argv)), timeout_seconds=args.timeout, complete=False)
        record["commands"].append(row)
        save()
        start = time.monotonic()
        with stdout.open("xb") as so, stderr.open("xb") as se:
            try:
                completed = subprocess.run(row["argv"], cwd=ROOT, env=dict(env, **(extra or {})),
                                           stdout=so, stderr=se, timeout=args.timeout)
                row.update(exit=completed.returncode, timed_out=False)
            except subprocess.TimeoutExpired:
                row.update(exit=None, timed_out=True)
            finally:
                row.update(wall_seconds=time.monotonic() - start, complete=True)
        row.update(stdout_sha256=sha(stdout.read_bytes()), stderr_sha256=sha(stderr.read_bytes()))
        save()
        if row["exit"] != 0 or row["timed_out"]:
            raise RuntimeError(f"{label} failed; logs retained in {out}")
        return stdout.read_text(), stderr.read_bytes()

    objects = out / "objects"
    objects.mkdir()
    host = []
    for source in (ROOT / "host/ghc/cbits/host.c", ROOT / "runtime/mlf_process_supervisor.c"):
        obj = objects / (source.stem + ".o")
        run(source.stem, [cc, "-O2", "-I" + str(ROOT / "runtime"), "-c", source, "-o", obj])
        host.append(obj)
    binary = out / "probe"
    run("build", [ghc, "-v0", "-w", "-O0", "-i" + str(out), "-ihost/ghc", "-ibootstrap",
                  *["-i" + str(p) for p in sorted((ROOT / "libraries").iterdir()) if p.is_dir()],
                  "-odir", objects, "-hidir", objects, "-main-is", "QueryGraphBoundary",
                  out / "QueryGraphBoundary.hs", *host, "-o", binary])
    record["binary_sha256"] = sha(binary.read_bytes())
    cases = [("snapshot", "generation.mlfqg", "config.txt", raw, config, generation),
             ("synthetic", "synthetic.mlfqg", "synthetic-config.txt", synthetic_raw, synthetic_config, synthetic)]
    for name, input_file, config_file, expected_raw, expected_config, expected_generation in cases:
        for mode in ("reference", "candidate", "controls"):
            label = name + "-" + mode
            target = out / (label + ".mlfqg")
            stdout, stderr = run(label, [binary], dict(BENCH_INPUT=str(out / input_file),
                BENCH_CONFIG=str(out / config_file), BENCH_OUTPUT=str(target), BENCH_MODE=mode,
                MLF_QUERY_PROFILE="1"))
            if stderr or target.read_bytes() != expected_raw:
                raise ValueError(f"{label}: stderr or byte mismatch")
            expected = f"OK {mode} {len(expected_generation.nodes)} {sha(expected_raw)}"
            if expected not in stdout.splitlines():
                raise ValueError(f"{label}: unexpected probe output")
            reread = Generation(target.read_bytes(), expected_hash=sha(expected_raw), configuration=expected_config.decode())
            if (reread.tables, reread.nodes, reread.rows) != (expected_generation.tables, expected_generation.nodes, expected_generation.rows):
                raise ValueError(f"{label}: independent generation mismatch")
            match = re.search(r"^TIMED_MS (\d+)$", stdout, re.MULTILINE)
            record["commands"][-1]["index_host_ms"] = int(match[1]) if match else None
            save()
    if pins != {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in dependencies}:
        raise ValueError("source inputs changed during replay")
    if record["toolchain"] != {str(p): sha(p.read_bytes()) for p in [ghc, cc, python]}:
        raise ValueError("toolchain changed during replay")
    record["complete"] = True
    save()
    print(json.dumps({k: v for k, v in record.items() if k not in ("dependencies", "commands")}, indent=2))


if __name__ == "__main__":
    main()
