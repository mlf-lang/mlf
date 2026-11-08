#!/usr/bin/env python3
"""Small cold compile comparison through the ordinary compiler CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/shared"))
from artifact_binary_reference import read_document
from artifact_binary_typed import pack, text, unpack
from query_generation import Generation, cache_directory


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def frame(values):
    return "".join(f"{len(value)}:{value}" for value in values)


def generated_source(groups):
    header = """-- mlf:syntax shared-haskell-v1
{-# LANGUAGE NoImplicitPrelude, NoMonomorphismRestriction, RankNTypes,
KindSignatures, FlexibleContexts, FlexibleInstances, MultiParamTypeClasses,
OverloadedStrings #-}
module App where {
import MLF.Primitive;
"""
    return header + "".join(f"probe{i} x = addInt x {i + 1};\n" for i in range(groups)) + "}\n"


def inspect(cache, compiler_hash):
    directory = cache_directory(cache)
    address = text(read_document((directory / "CURRENT").read_bytes(), 6).values()[0])
    generation = Generation((directory / "generations" / (address + ".mlfqg")).read_bytes(),
                            expected_hash=address)
    config = unpack(text(generation.config))
    if config[1] != compiler_hash:
        raise ValueError("query generation belongs to another compiler")
    payloads = {}
    for row in generation.nodes.values():
        address = row["payload"]
        if address is not None and address not in payloads:
            raw = (directory / "results" / (address + ".mlfqr")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != address:
                raise ValueError("corrupt query payload")
            payloads[address] = raw
    normalized_config = ("text", pack(config[:1] + ["compiler-normalized"] + config[2:]))
    # Re-encode all original tables and rows, preserving their order. Comparing
    # node dictionaries alone would miss insertion order or unused table data.
    normalized_generation = generation.encode_rows(generation.rows, normalized_config)
    return (normalized_generation, generation.nodes, payloads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--builtin-prefix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--groups", type=int, default=256)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--module", default="App")
    parser.add_argument("--dependency", type=Path, action="append", default=[])
    parser.add_argument("--profile", action="store_true", help="separate instrumented diagnostic")
    parser.add_argument("--timeout", type=int, default=120, help="diagnostic child budget in seconds")
    args = parser.parse_args()
    if not 0 <= args.groups <= 4096 or args.timeout <= 0:
        parser.error("groups must be 0..4096 and timeout must be positive")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = out / "Input.hs"
    source.write_bytes(args.source.resolve(strict=True).read_bytes() if args.source
                       else generated_source(args.groups).encode())
    builtin = args.builtin_prefix.resolve()
    dependencies = [p.resolve(strict=True) for p in args.dependency]
    companions = [path.with_suffix(".mlfco") for path in dependencies
                  if path.with_suffix(".mlfco").is_file()]
    inputs = [source, *(Path(str(builtin) + ext) for ext in (".mlfci", ".mlfco")),
              *dependencies, *companions]
    pins = {str(path): digest(path) for path in inputs}
    env = dict(os.environ, GHCRTS="", GHC_ENVIRONMENT="-", LANG="C.UTF-8", LC_ALL="C.UTF-8", TZ="UTC")
    for key in ("MLF_QUERY_PROFILE", "MLF_QUERY_FAILPOINT", "MLF_QUERY_SEMANTIC_AUDIT"):
        env.pop(key, None)
    if args.profile:
        env["MLF_QUERY_PROFILE"] = "1"
    record = dict(complete=False, scope="small CLI diagnostic; not full qualification",
                  script_sha256=digest(Path(__file__)),
                  profile=args.profile, timeout_seconds=args.timeout, inputs=pins, samples=[])
    save = lambda: (out / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    save()
    reference = None
    for name, selected in (("reference", args.reference), ("candidate", args.compiler)):
        binary = selected.resolve(strict=True)
        leg = out / name
        leg.mkdir()
        cache, prefix = leg / "cache", leg / "unit"
        spec = leg / "crate.spec"
        spec.write_text(frame(["MLF-CRATE-1", "native-cold-repro/0.3.0/library", "", "false",
                               frame([frame([args.module, str(source)])]),
                               frame([str(p) for p in dependencies]), str(cache), str(builtin)]))
        argv = [str(binary), "--compile-crate", str(spec), "-o", str(prefix)]
        binary_hash = digest(binary)
        deadline_reached = False
        with (leg / "stdout").open("xb") as stdout, (leg / "stderr").open("xb") as stderr:
            start = time.monotonic_ns()
            child = subprocess.Popen(argv, cwd=out, env=env, stdin=subprocess.DEVNULL,
                                     stdout=stdout, stderr=stderr, start_new_session=True)
            while True:
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                if pid:
                    break
                if time.monotonic_ns() - start >= args.timeout * 1_000_000_000:
                    deadline_reached = True
                    # The unreaped direct child still owns its PID, so this
                    # cannot signal a different process after PID reuse.
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    _, status, usage = os.wait4(child.pid, 0)
                    break
                time.sleep(0.01)
            child.returncode = os.waitstatus_to_exitcode(status)
            timed_out = deadline_reached and child.returncode == -signal.SIGKILL
            elapsed_ns = time.monotonic_ns() - start
        sample = dict(arm=name, binary=str(binary), binary_sha256=binary_hash, argv=argv,
                      exit=child.returncode, deadline_reached=deadline_reached, timed_out=timed_out,
                      wall_seconds=elapsed_ns / 1e9,
                      cpu_seconds=usage.ru_utime + usage.ru_stime,
                      peak_rss_bytes=usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024))
        record["samples"].append(sample)
        save()
        if child.returncode or timed_out or (leg / "stderr").stat().st_size:
            raise RuntimeError(f"{name} failed; retained {leg}")
        queries = json.loads(prefix.with_suffix(".queries").read_bytes())
        if queries["reused_groups"] or (not args.source and queries["inferred_groups"] != args.groups):
            raise ValueError("expected cold inference for every input group")
        products = {ext: prefix.with_suffix(ext).read_bytes() for ext in (".mlfci", ".mlfco", ".queries")}
        wire = inspect(cache, sample["binary_sha256"])
        if reference is None:
            reference = (products, wire)
        elif reference != (products, wire):
            raise ValueError("products, logical query graph or payload bytes differ")
        sample.update(inferred_groups=queries["inferred_groups"], reused_groups=queries["reused_groups"],
                      products={ext: hashlib.sha256(raw).hexdigest() for ext, raw in products.items()},
                      query_nodes=len(wire[1]), ordered_reads=sum(len(r["reads"]) for r in wire[1].values()))
        if args.profile:
            sample["phase_ms"] = json.loads(prefix.with_suffix(".query-profile").read_bytes())
        if pins != {str(path): digest(path) for path in inputs}:
            raise ValueError("input changed during comparison")
        save()
    record["complete"] = True
    save()
    print(json.dumps(record["samples"], indent=2))


if __name__ == "__main__":
    main()
