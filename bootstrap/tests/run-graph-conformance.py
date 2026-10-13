#!/usr/bin/env python3
"""Check both MLF backends against the independent Haskell graph oracle."""
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]

def run(command, output=None):
    result = subprocess.run([str(x) for x in command], cwd=ROOT, stdout=output or subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f"{shlex.join([str(x) for x in command])}\n{result.stderr.decode(errors='replace')}")
    return result.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--emlf", required=True)
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--suite", choices=("all", "enumeration", "scopes"), default="all")
    arguments = parser.parse_args()
    compiler = Path(arguments.emlf).resolve()
    suites = [
        ("enumeration", "GraphConformance", "GraphReference", "12000 validations and 5616 full/incremental unifications"),
        ("scopes", "GraphScopes", "GraphScopesReference", "scope, expansion, witness and closed-instance cases"),
    ]
    for selection, name, reference, description in suites:
        if arguments.suite not in ("all", selection):
            continue
        source = ROOT / f"bootstrap/tests/{name}.emlf"
        expected = run(["runghc", "-isrc", "-itest", f"bootstrap/tests/{reference}.hs"])
        checked_in = (ROOT / f"bootstrap/tests/{name}.expected").read_bytes()
        if expected != checked_in:
            raise RuntimeError(f"{name} reference changed; review the expected results before updating them")
        with tempfile.TemporaryDirectory(prefix="mlf-graph-conformance-") as directory:
            temporary = Path(directory)
            target, ir, executable = temporary / "graph.xmlf", temporary / "graph.ll", temporary / "graph"
            with target.open("wb") as output:
                run([compiler, "-i", "bootstrap", source], output)
            for backend in ("interpreter", "LLVM"):
                if backend == "interpreter":
                    actual = run([compiler, "--run-xmlf", target])
                else:
                    with ir.open("wb") as output:
                        run([compiler, "--xmlf-to-llvm", target], output)
                    flags = shlex.split(run(["pkg-config", "--cflags", "--libs", "gmp"]).decode())
                    run([arguments.clang, "-O2", "-Wno-override-module", ir, ROOT / "runtime/mlf_runtime.c", *flags, "-lm", "-o", executable])
                    actual = run([executable])
                if actual != expected:
                    mismatch = next((i for i, pair in enumerate(zip(actual, expected)) if pair[0] != pair[1]), min(len(actual), len(expected)))
                    raise RuntimeError(f"{backend} {name} parity failed at byte {mismatch}; actual {actual[mismatch:mismatch+100]!r}, expected {expected[mismatch:mismatch+100]!r}")
                print(f"{backend}: {description} match the Haskell reference", flush=True)

if __name__ == "__main__":
    main()
