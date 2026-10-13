#!/usr/bin/env python3
"""Run the MLF inference port on both backends against the Haskell compiler."""
import argparse
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def run(command, output=None):
    result = subprocess.run([str(x) for x in command], cwd=ROOT,
                            stdout=output or subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise RuntimeError(f"{shlex.join([str(x) for x in command])}\n"
                           f"{result.stderr.decode(errors='replace')}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--emlf", required=True)
    parser.add_argument("--clang", default="clang")
    args = parser.parse_args()
    compiler = Path(args.emlf).resolve()
    source = ROOT / "bootstrap/tests/InferenceConformance.emlf"
    oracle = ["runghc", "-isrc", "-itest", "bootstrap/tests/InferenceReference.hs"]
    generated = run([*oracle, "--generate"])
    if source.read_bytes() != generated:
        raise RuntimeError("Inference fixtures changed; regenerate and review the MLF fixture source")
    expected = run(oracle)
    if expected != (ROOT / "bootstrap/tests/InferenceConformance.expected").read_bytes():
        raise RuntimeError("Haskell inference oracle changed; review expectations before updating")
    if b"Fig12-A8\tREJECT Inference\n" not in expected:
        raise RuntimeError("Figure 12 A8 must remain an inference rejection")
    cases = len(expected.splitlines())
    with tempfile.TemporaryDirectory(prefix="mlf-inference-conformance-") as folder:
        temporary = Path(folder)
        target = temporary / "inference.xmlf"
        ir = temporary / "inference.ll"
        executable = temporary / "inference"
        with target.open("wb") as output:
            run([compiler, "-i", "bootstrap", source], output)
        for backend in ("interpreter", "LLVM"):
            if backend == "interpreter":
                actual = run([compiler, "--run-xmlf", target])
            else:
                with ir.open("wb") as output:
                    run([compiler, "--xmlf-to-llvm", target], output)
                flags = shlex.split(run(["pkg-config", "--cflags", "--libs", "gmp"]).decode())
                run([args.clang, "-O2", "-Wno-override-module", ir,
                     ROOT / "runtime/mlf_runtime.c", *flags, "-lm", "-o", executable])
                actual = run([executable])
            if actual != expected:
                left, right = actual.splitlines(), expected.splitlines()
                offset = next((i for i, pair in enumerate(zip(left, right)) if pair[0] != pair[1]), min(len(left), len(right)))
                got = left[offset] if offset < len(left) else b"<missing>"
                wanted = right[offset] if offset < len(right) else b"<none>"
                raise RuntimeError(f"{backend} inference parity failed at case {offset + 1}: "
                                   f"actual {got!r}, expected {wanted!r}")
            print(f"{backend}: {cases} compiler results match Haskell, including all 43 Figure 12 cases", flush=True)


if __name__ == "__main__":
    main()
