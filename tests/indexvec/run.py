#!/usr/bin/env python3
"""Exercise typed graph storage on GHC, the MLF checker/interpreter, and compact-GC LLVM."""

import argparse
from pathlib import Path
import shlex
import subprocess
import hashlib
import sys

from packages import compare_managers
from crates import check_crates

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED = b"0\n2\n7\n7\n66\n0\n1\n3\n9\n64\n2156\n"
WORLD_EXPECTED = b"7\n7\n9\n11\n0\n17\n7\n"


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
    parser.add_argument("--reference-compiler", type=Path, help="compatible compiler for cross-crate byte comparison")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    emlf = args.compiler.resolve(strict=True)
    compare_managers(out / "packages", emlf.with_name("mlfpkg"), args.reference_manager)
    check_crates(run, out / "crates", emlf, args.reference_compiler)
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
    for name in ["Graphs", "Vector", "World", "DeclQueryControls"]:
        obj = out / name
        obj.mkdir()
        run([*ghc, "-odir", obj, "-hidir", obj, HERE / (name + ".hs"), *host, "-o", obj / "probe"])
    run(
        [out / "Graphs/probe"],
        expected=b"1032 ordered SCC and reach comparisons, query DAG and package controls passed\n",
    )

    run([out / "DeclQueryControls/probe", out / "decl-query-cache"])

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
    run([out / "runtime-st", "world-gc"])
    run([out / "runtime-st", "world-generic"])
    interpreted = [*mlf, "--run", source, "--"]
    run([*interpreted, "success"], expected=EXPECTED)
    run([*interpreted, "set-end"], failure=b"IndexVec index out of bounds")
    run([*interpreted, "snapshot-empty"], failure=b"array index out of bounds")
    for exe in [out / "Vector/probe", out / "native"]:
        run([exe, "success"], expected=EXPECTED)
        for mode in ["read-negative", "read-end", "huge", "get-end", "set-end"]:
            run([exe, mode], failure=b"IndexVec index out of bounds")
        for mode in ["snapshot-empty", "snapshot-negative"]:
            run([exe, mode], failure=b"array index out of bounds")
        run([exe, "capacity"], failure=b"invalid IndexVec length")
    world = HERE / "World.hs"
    with (out / "world.ll").open("wb") as ir:
        run([*mlf, "--emit-llvm", world], stdout=ir)
    run(["clang", "-O2", "-Wno-override-module", out / "world.ll",
         ROOT / "runtime/mlf_runtime.c", *flags, "-lm", "-o", out / "world-native"])
    run([*mlf, "--run", world, "--", "success"], expected=WORLD_EXPECTED)
    for exe in [out / "World/probe", out / "world-native"]:
        run([exe, "success"], expected=WORLD_EXPECTED)
        for mode in ["read-negative", "write-end", "fixed-read-end", "fixed-write-end"]:
            run([exe, mode], failure=b"IndexVec index out of bounds")
    # Run the same wire fixtures through compiled native and interpreted code.
    # The Python reader independently decides which default-limit files are valid.
    sys.path.insert(0, str(ROOT / "tools/shared"))
    from artifact_binary_cases import corpus
    from artifact_binary_reference import Invalid, Limits, explicit_document, read_document

    codec = HERE / "CodecProbe.hs"
    codec_mlf = [*mlf, "-i", ROOT / "libraries/mlf-crates"]
    with (out / "codec.ll").open("wb") as ir:
        run([*codec_mlf, "--emit-llvm", codec], stdout=ir)
    run(["clang", "-O2", "-Wno-override-module", out / "codec.ll",
         ROOT / "runtime/mlf_runtime.c", *flags, "-lm", "-o", out / "codec-native"])
    corpus_dir = out / "codec-corpus"
    corpus_dir.mkdir()
    native_output = {}
    corpus_files = {}
    for index, case in enumerate(corpus()):
        if case.schema != 7 or case.limits != Limits():
            continue
        path = corpus_dir / (str(index) + ".bin")
        path.write_bytes(case.data)
        try:
            read_document(case.data, 7)
            accepted = True
        except Invalid:
            accepted = False
        result = run([out / "codec-native", "check", path])
        if result.startswith(b"OK\n") != accepted:
            raise ValueError(f"native wire acceptance differs: {case.name}")
        if accepted and not result.endswith(hashlib.sha256(case.data).hexdigest().encode() + b"\n"):
            raise ValueError(f"native wire did not roundtrip exactly: {case.name}")
        native_output[case.name] = result
        corpus_files[case.name] = path
    # Exercise the representable maximum depth and expanded-work boundary
    # without expanding the shared value tree.
    depth_path = corpus_dir / "max-depth.bin"
    count = 65536
    depth_path.write_bytes(explicit_document([], [(0, 0)] +
        [(3, (2, (i - 1,))) for i in range(1, count)], [count - 1]))
    work_path = corpus_dir / "max-work.bin"
    work_path.write_bytes(explicit_document([], [(0, 0)] +
        [(3, (2, (i - 1, i - 1))) for i in range(1, 31)], [30]))
    run([out / "codec-native", "limits", depth_path, "65536", "2147483647"],
        expected=b"OK\n65536\n65535\n65536\n")
    run([out / "codec-native", "limits", depth_path, "65535", "2147483647"],
        expected=b"E binary graph depth limit exceeded\n")
    run([out / "codec-native", "limits", work_path, "65536", "2147483647"],
        expected=b"OK\n31\n30\n31\n")
    run([out / "codec-native", "limits", work_path, "65536", "2147483646"],
        expected=b"E binary expanded-work limit exceeded\n")
    chosen = ["empty", "int-zero", "all-scalars", "structural-sharing", "ordered-distinct-roots",
              "max-node-tag", "crc-mismatch", "root-out-of-range", "child-forward",
              "duplicate-int-node", "duplicate-structural-node", "unused-symbol", "unused-node",
              "root-postorder", "children-postorder", "node-padding-bits", "root-padding-bits"]
    run([*codec_mlf, "--run", codec, "--", "check", *[corpus_files[name] for name in chosen]],
        expected=b"".join(native_output[name] for name in chosen))
    # The invalid declarations are still exported and checked even though main is harmless.
    for name, ghc_diagnostic, mlf_diagnostic in [
        ("DomainMismatch", b"Package", b"Declaration"),
        ("Escape", b"type variable", b"cannot raise a protected type variable"),
        ("WorldEscape", b"type variable", b"rigid or protected type variable"),
        ("WorldGeneralize", b"type variable", b"type constructor mismatch"),
    ]:
        source = HERE / (name + ".hs")
        run([*ghc, "-fno-code", source], failure=ghc_diagnostic)
        run([*mlf, "--type", source], failure=mlf_diagnostic)
    print("Passed ordered graph, package scheduling, typed index, IO-world, wire corpus, region, interpreter and LLVM controls.")


if __name__ == "__main__":
    main()
