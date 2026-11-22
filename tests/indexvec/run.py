#!/usr/bin/env python3
"""Exercise typed graph storage on GHC, the MLF checker/interpreter, and compact-GC LLVM."""

import argparse
from pathlib import Path
import shlex
import subprocess
import hashlib
import json
import sys

from packages import compare_managers
from crates import check_crates
from interfaces import check_interfaces
from link_fragments import check_diamond
from diagnostics import check_diagnostics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EXPECTED = b"0\n2\n7\n7\n66\n0\n1\n3\n9\n64\n2156\n"
WORLD_EXPECTED = b"7\n7\n9\n11\n0\n17\n7\n"

sys.path.insert(0, str(ROOT / "tools/testing"))
sys.path.insert(0, str(ROOT / "tools/shared"))
import events
from artifact_binary_cases import corpus
from artifact_binary_reference import Invalid, Limits, explicit_document, read_document

VECTOR_FAILURES = {
    **dict.fromkeys(["read-negative", "read-end", "huge", "get-end", "set-end"], b"IndexVec index out of bounds"),
    **dict.fromkeys(["snapshot-empty", "snapshot-negative"], b"array index out of bounds"),
    "capacity": b"invalid IndexVec length",
}
WORLD_FAILURES = ["read-negative", "write-end", "fixed-read-end", "fixed-write-end"]
COMPILE_NEGATIVES = [
    ("DomainMismatch", b"Package", b"Declaration"),
    ("Escape", b"type variable", b"cannot raise a protected type variable"),
    ("WorldEscape", b"type variable", b"rigid or protected type variable"),
    ("WorldGeneralize", b"type variable", b"type constructor mismatch"),
]


def case_id(identity):
    return "indexvec/" + identity


def inventory(wire_cases):
    return [
        *["packages", "crates", "interfaces", "link-diamond", "diagnostics"],
        *["host/" + name for name in ["graphs", "decl-query", "import-bindings", "prepared-imports", "fragments", "decl-core"]],
        *["runtime-st/" + mode for mode in ["direct", "world-gc", "world-generic"]],
        *["vector/interpreter/" + name for name in ["success", "set-end", "snapshot-empty"]],
        *[f"vector/{backend}/{mode}" for backend in ("ghc", "llvm") for mode in ("success", *VECTOR_FAILURES)],
        "world/interpreter/success",
        *[f"world/{backend}/{mode}" for backend in ("ghc", "llvm") for mode in ("success", *WORLD_FAILURES)],
        *["codec/native/" + case.name for _, case in wire_cases],
        *["codec/limits/" + name for name in ("max-depth", "excess-depth", "max-work", "excess-work")],
        "codec/interpreter/selected-corpus",
        *[f"rejected/{name}/{backend}" for name, _, _ in COMPILE_NEGATIVES for backend in ("ghc", "mlf")],
    ]


def observe(identity, action, *args, **kwargs):
    identity = case_id(identity)
    events.start(identity)
    try:
        value = action(*args, **kwargs)
    except subprocess.TimeoutExpired as error:
        events.result(identity, "timeout", detail=str(error))
        raise
    except Exception as error:
        events.result(identity, "fail", detail=str(error))
        raise
    events.result(identity, "pass")
    return value


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
    parser.add_argument("--compiler", type=Path)
    parser.add_argument(
        "--reference-manager", type=Path, help="optional pre-change manager for byte comparison"
    )
    parser.add_argument("--reference-compiler", type=Path, help="compatible compiler for cross-crate byte comparison")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--framework-list", action="store_true")
    args = parser.parse_args()
    wire_cases = [(index, case) for index, case in enumerate(corpus())
                  if case.schema == 7 and case.limits == Limits()]
    ids = [case_id(identity) for identity in inventory(wire_cases)]
    if args.framework_list:
        print(json.dumps(ids))
        return
    if args.compiler is None or args.output is None:
        parser.error("--compiler and --output are required")
    events.plan(ids)
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    emlf = args.compiler.resolve(strict=True)
    observe("packages", compare_managers, out / "packages", emlf.with_name("mlfpkg"), args.reference_manager)
    observe("crates", check_crates, run, out / "crates", emlf, args.reference_compiler)
    observe("interfaces", check_interfaces, run, out / "interfaces", emlf, args.reference_compiler)
    observe("link-diamond", check_diamond, run, out / "link-diamond", emlf)
    observe("diagnostics", check_diagnostics, out / "diagnostics", emlf, args.reference_compiler)
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
    for name in ["Graphs", "Vector", "World", "DeclQueryControls", "ImportBindings", "PreparedImports", "FragmentAdmission", "DeclCore"]:
        obj = out / name
        obj.mkdir()
        run([*ghc, *(["-i" + str(ROOT / "tests/shared")] if name == "Graphs" else []), "-odir", obj, "-hidir", obj, HERE / (name + ".hs"), *host, "-o", obj / "probe"])
    observe("host/graphs", run,
        [out / "Graphs/probe"],
        expected=b"1032 ordered SCC and reach comparisons, query DAG and package controls passed\n",
    )

    observe("host/decl-query", run, [out / "DeclQueryControls/probe", out / "decl-query-cache"])
    observe("host/import-bindings", run, [out / "ImportBindings/probe"], expected=b"consumer import ID controls passed\n")
    observe("host/prepared-imports", run, [out / "PreparedImports/probe", out / "crates"],
        expected=b"prepared source and native wrapper import controls passed\n")

    observe("host/fragments", run, [out / "FragmentAdmission/probe", out], expected=b"raw and final fragment admission controls passed\n")
    observe("host/decl-core", run, [out / "DeclCore/probe"],
        expected=b"Core declaration slots, lexical shadowing, polymorphic imports and recursion passed\n")

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
    observe("runtime-st/direct", run, [out / "runtime-st"])
    for mode in ("world-gc", "world-generic"):
        observe("runtime-st/" + mode, run, [out / "runtime-st", mode])
    interpreted = [*mlf, "--run", source, "--"]
    observe("vector/interpreter/success", run, [*interpreted, "success"], expected=EXPECTED)
    for mode in ("set-end", "snapshot-empty"):
        observe("vector/interpreter/" + mode, run, [*interpreted, mode], failure=VECTOR_FAILURES[mode])
    for backend, exe in [("ghc", out / "Vector/probe"), ("llvm", out / "native")]:
        observe(f"vector/{backend}/success", run, [exe, "success"], expected=EXPECTED)
        for mode, diagnostic in VECTOR_FAILURES.items():
            observe(f"vector/{backend}/{mode}", run, [exe, mode], failure=diagnostic)
    world = HERE / "World.hs"
    with (out / "world.ll").open("wb") as ir:
        run([*mlf, "--emit-llvm", world], stdout=ir)
    run(["clang", "-O2", "-Wno-override-module", out / "world.ll",
         ROOT / "runtime/mlf_runtime.c", *flags, "-lm", "-o", out / "world-native"])
    observe("world/interpreter/success", run, [*mlf, "--run", world, "--", "success"], expected=WORLD_EXPECTED)
    for backend, exe in [("ghc", out / "World/probe"), ("llvm", out / "world-native")]:
        observe(f"world/{backend}/success", run, [exe, "success"], expected=WORLD_EXPECTED)
        for mode in WORLD_FAILURES:
            observe(f"world/{backend}/{mode}", run, [exe, mode], failure=b"IndexVec index out of bounds")
    # Record these independent rejections before the codec fixture builds.
    # The invalid declarations are still exported and checked even though main is harmless.
    for name, ghc_diagnostic, mlf_diagnostic in COMPILE_NEGATIVES:
        source = HERE / (name + ".hs")
        observe(f"rejected/{name}/ghc", run, [*ghc, "-fno-code", source], failure=ghc_diagnostic)
        observe(f"rejected/{name}/mlf", run, [*mlf, "--type", source], failure=mlf_diagnostic)

    # The separate Python reader decides which default-limit wire files are valid.
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
    def native_wire_comparison(case, path):
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
        return result

    for index, case in wire_cases:
        path = corpus_dir / (str(index) + ".bin")
        path.write_bytes(case.data)
        native_output[case.name] = observe("codec/native/" + case.name, native_wire_comparison, case, path)
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
    observe("codec/limits/max-depth", run, [out / "codec-native", "limits", depth_path, "65536", "2147483647"],
        expected=b"OK\n65536\n65535\n65536\n")
    observe("codec/limits/excess-depth", run, [out / "codec-native", "limits", depth_path, "65535", "2147483647"],
        expected=b"E binary graph depth limit exceeded\n")
    observe("codec/limits/max-work", run, [out / "codec-native", "limits", work_path, "65536", "2147483647"],
        expected=b"OK\n31\n30\n31\n")
    observe("codec/limits/excess-work", run, [out / "codec-native", "limits", work_path, "65536", "2147483646"],
        expected=b"E binary expanded-work limit exceeded\n")
    chosen = ["empty", "int-zero", "all-scalars", "structural-sharing", "ordered-distinct-roots",
              "max-node-tag", "crc-mismatch", "root-out-of-range", "child-forward",
              "duplicate-int-node", "duplicate-structural-node", "unused-symbol", "unused-node",
              "root-postorder", "children-postorder", "node-padding-bits", "root-padding-bits"]
    observe("codec/interpreter/selected-corpus", run, [*codec_mlf, "--run", codec, "--", "check", *[corpus_files[name] for name in chosen]],
        expected=b"".join(native_output[name] for name in chosen))
    print("Passed ordered graph, package scheduling, typed index, IO-world, wire corpus, region, interpreter and LLVM controls.")


if __name__ == "__main__":
    main()
