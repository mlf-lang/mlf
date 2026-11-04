#!/usr/bin/env python3
"""Exercise typed graph storage on GHC, the MLF checker/interpreter, and compact-GC LLVM."""

import argparse
from pathlib import Path
import shlex
import subprocess

from packages import compare_managers

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED = b"0\n2\n7\n7\n66\n0\n1\n3\n9\n64\n2156\n"


def run(argv, expected=None, failure=None, stdout=None):
    result = subprocess.run(
        list(map(str, argv)),
        cwd=ROOT,
        stdout=stdout or subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=360,
    )
    if failure is not None:
        if result.returncode == 0 or failure not in result.stderr:
            raise ValueError(f"{argv}: expected rejection {failure!r}, got {result.stderr[:1000]!r}")
    elif result.returncode or (expected is not None and result.stdout != expected):
        raise ValueError(
            f"{argv}: exit {result.returncode}, stdout={result.stdout!r}, stderr={result.stderr[-1200:]!r}"
        )
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument(
        "--reference-manager", type=Path, help="optional pre-change manager for byte comparison"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    emlf = args.compiler.resolve(strict=True)
    compare_managers(out / "packages", emlf.with_name("mlfpkg"), args.reference_manager)
    flags = shlex.split(
        subprocess.check_output(["pkg-config", "--cflags", "--libs", "gmp", "bdw-gc"], text=True)
    )
    host = []
    for source in [ROOT / "host/ghc/cbits/host.c", ROOT / "runtime/mlf_process_supervisor.c"]:
        obj = out / (source.stem + ".o")
        run(["cc", "-O2", "-Iruntime", "-c", source, "-o", obj])
        host.append(obj)
    ghc = [
        "ghc",
        "-v0",
        "-w",
        "-O0",
        "-ihost/ghc",
        "-ibootstrap",
        *["-i" + str(d) for d in sorted((ROOT / "libraries").iterdir())],
    ]
    for name in ["Graphs", "Vector"]:
        obj = out / name
        obj.mkdir()
        run([*ghc, "-odir", obj, "-hidir", obj, HERE / (name + ".hs"), *host, "-o", obj / "probe"])
    run(
        [out / "Graphs/probe"],
        expected=b"1032 ordered SCC comparisons and package/module graph controls passed\n",
    )

    source = HERE / "Vector.hs"
    mlf = [emlf, "-i", ROOT / "libraries/mlf-foundation"]
    with (out / "vector.ll").open("wb") as ir:
        run([*mlf, "--emit-llvm", source], stdout=ir)
    run(
        [
            "clang",
            "-O2",
            "-Wno-override-module",
            out / "vector.ll",
            ROOT / "runtime/mlf_runtime.c",
            *flags,
            "-lm",
            "-o",
            out / "native",
        ]
    )
    run(
        [
            "cc",
            "-O2",
            "-std=c11",
            "-Iruntime",
            HERE.parent / "native/runtime_st.c",
            ROOT / "runtime/mlf_runtime.c",
            *flags,
            "-lm",
            "-o",
            out / "runtime-st",
        ]
    )
    run([out / "runtime-st"])
    interpreted = [*mlf, "--run", source, "--"]
    run([*interpreted, "success"], expected=EXPECTED)
    run([*interpreted, "set-end"], failure=b"IndexVec index out of bounds")
    for exe in [out / "Vector/probe", out / "native"]:
        run([exe, "success"], expected=EXPECTED)
        for mode in ["read-negative", "read-end", "huge", "get-end", "set-end"]:
            run([exe, mode], failure=b"IndexVec index out of bounds")
        run([exe, "capacity"], failure=b"invalid IndexVec length")
    # The invalid declarations are still exported and checked even though main is harmless.
    for name, ghc_diagnostic, mlf_diagnostic in [
        ("DomainMismatch", b"Package", b"Declaration"),
        ("Escape", b"type variable", b"cannot raise a protected type variable"),
    ]:
        source = HERE / (name + ".hs")
        run([*ghc, "-fno-code", source], failure=ghc_diagnostic)
        run([*mlf, "--type", source], failure=mlf_diagnostic)
    print("Passed ordered graph, package scheduling, typed index, region, interpreter and LLVM controls.")


if __name__ == "__main__":
    main()
