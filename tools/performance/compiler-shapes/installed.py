#!/usr/bin/env python3
"""Paired public emlf SOURCE -o / GHC builds. Keep this endpoint's receipts separate."""

import argparse
import importlib.util
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import generate
from prepare import prepare_host_package

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/shared"))
from test_direct import sha

sys.path.insert(0, str(ROOT / "tools/performance/a1-private-index"))
import helper as resources

GiB = 1024**3
LIMITS = {
    "address_space_per_process_bytes": 6 * GiB,
    "disk_free_floor_bytes": 4 * GiB,
    "host_available_floor_bytes": 3 * GiB,
    "max_work_bytes": 2 * GiB,
    "process_tree_rss_bytes": 5 * GiB,
    "wall_seconds": 180,
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def dump(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def installation(path):
    path = path.resolve(strict=True)
    source = path / "sources"
    spec = importlib.util.spec_from_file_location(
        "installed_direct", source / "tools/shared/test_direct.py"
    )
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    build = verifier.authenticate_build(path / "receipt.json", path / "bin", root=source)
    require(
        build["optimization"] == "2" and build["prepared_verification"]["kind"] == "prepared",
        "an authenticated optimized public installation is required",
    )
    native = json.loads((path / "native/receipt.json").read_text())
    require(native["complete"], "native library regeneration did not succeed")
    compiler = path / "bin/emlf"
    identity = subprocess.check_output([compiler, "--implementation-identity"], text=True).strip()
    require(identity == build["implementation_identity"], "compiler identity differs from receipt")
    checkout = Path(json.loads((path / "owned-source.json").read_text())["root"])
    # Bind compiled shared source to the actual checkout, except the two sealed
    # installation registries, whose provenance authenticate_build already verifies.
    sources = {}
    for name, item in build["shared_inputs"].items():
        relative = Path(item["path"]).relative_to(path / "sources")
        if name not in ("MLF.PreparedLibraryData", "MLF.PreparedNativeData"):
            require(sha(checkout / relative) == item["sha256"], "unmatched source: " + str(relative))
        sources[str(relative)] = item["sha256"]
    return {
        "binary": str(compiler),
        "sha256": sha(compiler),
        "host": identity,
        "checkout": str(checkout),
        "commit": subprocess.check_output(["git", "-C", checkout, "rev-parse", "HEAD"], text=True).strip(),
        "receipt_sha256": sha(path / "receipt.json"),
        "source_sha256": sources,
        "native_receipt_sha256": sha(path / "native/receipt.json"),
        "native_config": json.loads((path / "native/request.json").read_text()),
        "ghc": build["ghc"],
    }


def workloads(root, n):
    root.mkdir()
    cases = {}

    def create(name, files, inputs, expected):
        directory = root / name
        for relative, data in files.items():
            file = directory / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data.encode() if isinstance(data, str) else data)
        cases[name] = {
            "directory": str(directory),
            "sources": {key: sha(directory / key) for key in files},
            "oracle": {str(x): str(expected(x)) + "\n" for x in inputs},
        }

    for name in ("dependency_chain", "flat_functions", "recursive_ring"):
        inputs = [-1, 0, n + 3]
        create(
            name, {"Main.hs": generate.program(name, n)}, inputs, lambda x: generate.expected(name, n, x)
        )
    prefix = generate.HEADER.split("module Main")[0]
    files = {
        "Shared.hs": prefix
        + "module Shared where { import MLF.Primitive; leaf :: Int -> Int; leaf x = addInt x 1 }\n",
        "LeftArm.hs": prefix
        + "module LeftArm where { import MLF.Primitive; import qualified Shared as S; f :: Int -> Int; f x = mulInt 2 (S.leaf x) }\n",
        "RightArm.hs": prefix
        + "module RightArm where { import MLF.Primitive; import qualified Shared as S; f :: Int -> Int; f x = addInt 3 (S.leaf x) }\n",
        "Main.hs": generate.HEADER
        + "import qualified LeftArm as L; import qualified RightArm as R;\nentry :: Int -> Int; entry x = addInt (L.f x) (R.f x);\n"
        + generate.MAIN,
    }
    create("module_diamond", files, [-1, 0, 9], lambda x: 3 * x + 6)
    # Force the repository's real Unicode implementation through both user-module
    # frontends. Only its module name changes to avoid the installed Foundation copy.
    unicode = (ROOT / "libraries/mlf-foundation/Bootstrap/Unicode.hs").read_bytes()
    require(unicode.count(b"module Bootstrap.Unicode") == 1, "Unicode module header changed")
    create(
        "compiler_unicode",
        {
            "Classifier.hs": unicode.replace(b"module Bootstrap.Unicode", b"module Classifier"),
            "Main.hs": generate.HEADER
            + "import qualified Classifier as U;\nentry :: Int -> Int; entry x = if U.isAlpha x then 1 else 0;\n"
            + generate.MAIN,
        },
        [65, 955, 33],
        lambda x: int(chr(x).isalpha()),
    )
    return cases


def measured(argv, cwd, directory, runner):
    started = time.time_ns()
    try:
        row = runner.run(argv, cwd, directory, timed=True)
    except RuntimeError:
        if not (directory / "command.json").exists():
            raise
        row = json.loads((directory / "command.json").read_text())
    return {
        "argv": row["argv"],
        "cwd": row["cwd"],
        "exit": row.get("exit_code"),
        "guard": row.get("reason"),
        "start_ns": started,
        "wall_s": row.get("wall_seconds"),
        "user_s": row.get("child_user_seconds"),
        "system_s": row.get("child_system_seconds"),
        "peak_rss_bytes": row.get("max_individual_child_rss_bytes"),
        "sampled_group_rss_bytes": row.get("sampled_process_tree_peak_rss_bytes"),
    }


def oracle(case, program):
    results = []
    for arg, expected in case["oracle"].items():
        run = subprocess.run([program, arg], capture_output=True, timeout=30)
        require(
            run.returncode == 0 and run.stdout == expected.encode() and not run.stderr,
            "executable oracle mismatch: " + repr((arg, run.returncode, run.stdout, run.stderr)),
        )
        results.append([arg, run.stdout.decode()])
    return results


def summarize(cases, samples, repeats):
    result = []
    for name in cases:
        for state in ("fresh", "warm"):
            rows = [s for s in samples if s["case"] == name and s["state"] == state]
            medians = {}
            for lane in ("before", "after", "ghc"):
                group = [s for s in rows if s["lane"] == lane]
                if len(group) == repeats and all(s.get("passed") for s in group):
                    medians[lane] = {
                        field: statistics.median(s[field] for s in group)
                        for field in ("wall_s", "user_s", "system_s", "peak_rss_bytes")
                    }
            row = {"case": name, "state": state, "medians": medians}
            if len(medians) == 3:
                times = {k: v["wall_s"] for k, v in medians.items()}
                row.update(
                    after_over_before=times["after"] / times["before"],
                    before_over_ghc=times["before"] / times["ghc"],
                    after_over_ghc=times["after"] / times["ghc"],
                )
            result.append(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("before", "after", "output"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--size", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    require(args.size > 0 and args.repeats >= 3, "positive size and at least three rounds required")
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    producers = {k: installation(getattr(args, k)) for k in ("before", "after")}
    a, b = producers.values()
    require(a["native_config"] == b["native_config"] and a["ghc"] == b["ghc"], "toolchain/config mismatch")
    before = Path(a["binary"]).parent.parent
    ghc = Path(a["ghc"]["path"])
    setup_commands = []

    def run_setup(label, command):
        command = list(map(str, command))
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        setup_commands.append({"label": label, "argv": command})

    db = prepare_host_package(ghc, before / "sources", before, out / "host", run_setup)
    cases = workloads(out / "sources", args.size)
    # Alternate before/after, with GHC at rotating positions; each warm build
    # uses its own lane's immediately preceding fresh artifacts and identical bytes.
    schedule = []
    for c, name in enumerate(cases):
        for r in range(args.repeats):
            order = ["before", "after"] if (r + c) % 2 == 0 else ["after", "before"]
            order.insert((r + c + 1) % 3, "ghc")
            for state in ("fresh", "warm"):
                for lane in order if state == "fresh" else reversed(order):
                    schedule.append({"case": name, "round": r, "state": state, "lane": lane})
    plan = {
        "endpoint": "emlf-source-v1",
        "host": platform.platform(),
        "machine": platform.machine(),
        "clang_version": subprocess.check_output(
            [a["native_config"]["clang"]["path"], "--version"], text=True
        ).splitlines()[0],
        "runner_sha256": sha(Path(__file__)),
        "generator_sha256": sha(Path(generate.__file__)),
        "ghc_host_package": sha(out / "host/libHSmlf-shape-primitives-0.1.a"),
        "setup": setup_commands,
        "os_cache": "not flushed",
        "limits": LIMITS,
        "producers": producers,
        "cases": cases,
        "schedule": schedule,
    }
    dump(out / "plan.json", plan)
    results = {"plan_sha256": sha(out / "plan.json"), "samples": [], "complete": False}
    runner = resources.Runner(out, LIMITS)
    for item in schedule:
        lane, name, state, r = (item[k] for k in ("lane", "case", "state", "round"))
        case = cases[name]
        src = Path(case["directory"])
        dest = out / "legs" / name / str(r) / lane
        dest.mkdir(parents=True, exist_ok=True)
        program = dest / "program"
        sample = dict(item)
        try:
            require(all(sha(src / k) == v for k, v in case["sources"].items()), "workload bytes changed")
            if state == "warm":
                prior = next(
                    s
                    for s in results["samples"]
                    if s["case"] == name and s["round"] == r and s["lane"] == lane and s["state"] == "fresh"
                )
                require(
                    prior.get("passed") and sha(program) == prior["program_sha256"],
                    "missing successful fresh build",
                )
            else:
                require(not program.exists(), "fresh output exists")
            if lane == "ghc":
                command = [
                    ghc,
                    "--make",
                    "-j1",
                    "-O2",
                    "-package-env",
                    "-",
                    "-clear-package-db",
                    "-global-package-db",
                    "-package-db",
                    db,
                    "-no-user-package-db",
                    "-hide-all-packages",
                    "-package",
                    "base",
                    "-package",
                    "mlf-shape-primitives",
                    "-i",
                    "-i" + str(src),
                    "-odir",
                    dest,
                    "-hidir",
                    dest,
                    src / "Main.hs",
                    "-o",
                    program,
                ]
            else:
                build = dest / (state + "-build")
                require(not build.exists(), "user build directory exists")
                command = [
                    producers[lane]["binary"],
                    "-i",
                    src,
                    src / "Main.hs",
                    "-o",
                    program,
                    "--build-dir",
                    build,
                ]
            sample.update(measured(command, src, dest / state, runner))
            require(
                sample["exit"] == 0 and not sample["guard"],
                sample["guard"] or (dest / state / "stderr").read_text()[-1400:],
            )
            if lane != "ghc":
                receipt = json.loads((build / "receipt.json").read_text())
                require(
                    receipt["complete"]
                    and receipt["fresh_user_compilation"]
                    and receipt["fixed_runtime_reused"]
                    and receipt["source_sha256"] == case["sources"]["Main.hs"]
                    and receipt["output_sha256"] == sha(program)
                    and [c["phase"] for c in receipt["commands"]] == ["llvm", "link"]
                    and receipt["compiler"] == producers[lane]["binary"],
                    "incomplete or mismatched installed receipt",
                )
                for key, digest in case["sources"].items():
                    if key != "Main.hs":
                        require(
                            any(
                                row["path"] == str(src / key) and row["sha256"] == digest
                                for row in receipt["source_inputs"]
                            ),
                            "user module omitted: " + key,
                        )
                sample["installed"] = {
                    k: receipt[k]
                    for k in (
                        "stdlib_path",
                        "native_export_count",
                        "builtin_inline_count",
                        "llvm_sha256",
                        "user_object_sha256",
                        "commands",
                        "source_inputs",
                    )
                }
                sample["installed"]["receipt_sha256"] = sha(build / "receipt.json")
                boundaries = [sample["start_ns"]] + [
                    (build / k).stat().st_mtime_ns for k in ("program.ll", "program.o", "program")
                ]
                sample["stage_intervals_s"] = [(y - x) / 1e9 for x, y in zip(boundaries, boundaries[1:])]
            sample.update(program_sha256=sha(program), oracle=oracle(case, program), passed=True)
        except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as exc:
            sample.update(passed=False, error=str(exc))
        results["samples"].append(sample)
        dump(out / "receipt.json", results)
        print(
            f"{name} {r} {state} {lane} {sample.get('wall_s', '-')} {sample.get('error', 'OK')}", flush=True
        )
    results["complete"] = all(s["passed"] for s in results["samples"])
    results["summary"] = summarize(cases, results["samples"], args.repeats)
    dump(out / "receipt.json", results)
    return 0 if results["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
