#!/usr/bin/env python3
"""Paired public emlf SOURCE -o / GHC builds. Keep this endpoint's receipts separate."""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

import generate
from fit_growth import median_peak_rss, peak_rss_ratio
from framework_results import events
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
WORKLOADS = ("dependency_chain", "flat_functions", "recursive_ring", "module_diamond", "compiler_unicode")


def select_cases(names, size, edited):
    cases = {name: f"{name}-{size}" + ("-edited" if edited else "") for name in names}
    by_id = {f"compiler-shapes-installed/{kind}/{cell}": name
             for name, cell in cases.items() for kind in ("correctness", "comparison")}
    exact = os.environ.get("MLF_TEST_EXACT") if os.environ.get("MLF_TEST_SUITE") == "compiler-shapes-installed" else None
    if exact:
        require(exact in by_id, "unknown installed shape case: " + exact)
        return {exact: by_id[exact]}
    return by_id


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
    require(native["format"] == "MLF-NATIVE-INSTALL-2" and native["complete"],
            "native crate installation regeneration did not succeed")
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


def leaf_edit(case):
    file = Path(case["directory"]) / "Shared.hs"
    original = file.read_text()
    require(original.count("leaf x = addInt x 1") == 1, "unexpected shared leaf")
    edited = original.replace("leaf x = addInt x 1", "leaf x = addInt x 2")
    return {
        "file": file.name,
        "fresh": original,
        "edited": edited,
        "sources": {**case["sources"], file.name: hashlib.sha256(edited.encode()).hexdigest()},
        "oracle": {arg: str(3 * int(arg) + 9) + "\n" for arg in case["oracle"]},
    }


def measured(argv, cwd, directory, runner, env_overrides):
    started = time.time_ns()
    try:
        row = runner.run(argv, cwd, directory, timed=True, env_overrides=env_overrides)
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


def summarize(cases, samples, repeats, states):
    result = []
    for name in cases:
        for state in states:
            rows = [s for s in samples if s["case"] == name and s["state"] == state]
            medians = {}
            for lane in ("before", "after", "ghc"):
                group = [s for s in rows if s["lane"] == lane]
                if len(group) == repeats and all(s.get("passed") for s in group):
                    medians[lane] = {
                        field: statistics.median(s[field] for s in group)
                        for field in ("wall_s", "user_s", "system_s", "peak_rss_bytes")
                    }
                    medians[lane]["sampled_group_rss_bytes"] = median_peak_rss(
                        [s.get("sampled_group_rss_bytes") for s in group]
                    )
            row = {"case": name, "state": state, "medians": medians}
            ghc_rss = medians.get("ghc", {}).get("sampled_group_rss_bytes")
            for lane in ("before", "after"):
                mlf_rss = medians.get(lane, {}).get("sampled_group_rss_bytes")
                ratio = peak_rss_ratio(mlf_rss, ghc_rss)
                row[lane + "_over_ghc_peak_rss"] = ratio
                row[lane + "_peak_rss_at_most_ghc"] = None if ratio is None else ratio <= 1.
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
    listing = "--framework-list" in sys.argv[1:]
    parser.add_argument("--framework-list", action="store_true")
    for option in ("before", "after", "output"):
        parser.add_argument("--" + option, type=Path, required=not listing)
    parser.add_argument("--size", type=int, default=16)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument(
        "--diamond-edit",
        action="store_true",
        help="measure a separate cohort with an edit to the common module dependency",
    )
    args = parser.parse_args()
    require(args.size > 0 and args.repeats >= 3, "positive size and at least three rounds required")
    identities = select_cases(("module_diamond",) if args.diamond_edit else WORKLOADS,
                              args.size, args.diamond_edit)
    if args.framework_list:
        print(json.dumps(list(identities)))
        return 0
    report_cases = os.environ.get("MLF_TEST_SUITE") == "compiler-shapes-installed"
    if report_cases:
        events.plan(identities)
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
    require(tuple(cases) == WORKLOADS, "installed shape case inventory differs")
    cases = {name: case for name, case in cases.items() if name in identities.values()}
    edit = None
    states = ("fresh", "warm")
    if args.diamond_edit:
        cases = {"module_diamond": cases["module_diamond"]}
        edit = leaf_edit(cases["module_diamond"])
        states = ("fresh", "edited")
    # Alternate before/after, with GHC at rotating positions; each warm build
    # uses its own lane's immediately preceding fresh artifacts and identical bytes.
    schedule = []
    for c, name in enumerate(cases):
        for r in range(args.repeats):
            order = ["before", "after"] if (r + c) % 2 == 0 else ["after", "before"]
            order.insert((r + c + 1) % 3, "ghc")
            for state in states:
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
        "source_query_cache": "isolated per workload, round and MLF producer; shared with its warm or edited build",
        "limits": LIMITS,
        "producers": producers,
        "cases": cases,
        "leaf_edit": edit,
        "schedule": schedule,
    }
    dump(out / "plan.json", plan)
    results = {"plan_sha256": sha(out / "plan.json"), "samples": [], "complete": False}
    runner = resources.Runner(out, LIMITS)
    started = set()
    expected_per_case = args.repeats * len(states) * 3
    by_case = {name: [] for name in cases}
    for item in schedule:
        lane, name, state, r = (item[k] for k in ("lane", "case", "state", "round"))
        case = cases[name]
        if report_cases and name not in started:
            for identity, workload in identities.items():
                if workload == name:
                    events.start(identity, endpoint=plan["endpoint"], repeats=args.repeats)
            started.add(name)
        src = Path(case["directory"])
        dest = out / "legs" / name / str(r) / lane
        dest.mkdir(parents=True, exist_ok=True)
        program = dest / "program"
        sample = dict(item)
        try:
            if edit:
                leaf = src / edit["file"]
                desired = edit[state]
                current = leaf.read_text()
                require(current in (edit["fresh"], edit["edited"]), "shared leaf changed outside the plan")
                if current != desired:
                    leaf.write_text(desired)
                if state == "edited":
                    case = {**case, "sources": edit["sources"], "oracle": edit["oracle"]}
            require(all(sha(src / k) == v for k, v in case["sources"].items()), "workload bytes changed")
            if state != "fresh":
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
            env_overrides = {}
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
                source_queries = dest / "source-queries"
                if state == "fresh":
                    require(not source_queries.exists(), "fresh source query cache exists")
                env_overrides["MLF_SOURCE_CACHE_DIR"] = str(source_queries)
                sample["source_query_cache"] = str(source_queries)
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
            sample.update(measured(command, src, dest / state, runner, env_overrides))
            require(
                sample["exit"] == 0 and not sample["guard"],
                sample["guard"] or (dest / state / "stderr").read_text()[-1400:],
            )
            if lane != "ghc":
                receipt = json.loads((build / "receipt.json").read_text())
                require(
                    receipt["format"] == "MLF-NATIVE-PROGRAM-BUILD-3"
                    and receipt["complete"]
                    and receipt["fresh_user_compilation"]
                    and receipt["runtime_reused"]
                    and receipt["source_sha256"] == case["sources"]["Main.hs"]
                    and receipt["output_sha256"] == sha(program)
                    and [c["phase"] for c in receipt["commands"]] == ["llvm", "link"]
                    and receipt["compiler"] == producers[lane]["binary"],
                    "incomplete or mismatched installed receipt",
                )
                providers = receipt["native_providers"]
                owners = [row["dependency"] for row in providers]
                selected = [row["dependency"] for row in receipt["dependency_modes"]
                            if row["mode"] == "native" and row["dependency"] != "runtime"]
                installed = {row["contract"]["crate_id"]: row
                             for row in receipt["installation"]["providers"]}
                objects = [{"path": row["path"], "sha256": row["sha256"]} for row in providers]
                expected = [*objects, receipt["installation"]["runtime"]]
                require(len(owners) == len(set(owners)) and sorted(owners) == sorted(selected)
                        and receipt["link_objects"] == expected
                        and any(row["dependency"] == "runtime" and row["mode"] == "native"
                                for row in receipt["dependency_modes"])
                        and all(installed[row["dependency"]]["object"] == objects[index]
                                and installed[row["dependency"]]["contract"]["export_abi"] == "mlf-crate-boxed/1"
                                for index, row in enumerate(providers))
                        and all(sha(row["path"]) == row["sha256"]
                                and receipt["commands"][1]["command"].count(row["path"]) == 1
                                for row in expected), "native dependency selection differs from actual link inputs")
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
                        "native_providers",
                        "dependency_modes",
                        "link_objects",
                        "runtime_reused",
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
        by_case[name].append(sample)
        dump(out / "receipt.json", results)
        print(
            f"{name} {r} {state} {lane} {sample.get('wall_s', '-')} {sample.get('error', 'OK')}", flush=True
        )
        if report_cases and len(by_case[name]) == expected_per_case:
            failed = sum(not sample["passed"] for sample in by_case[name])
            for identity, workload in identities.items():
                if workload == name:
                    events.result(identity, "fail" if failed else "pass", receipt=str(out / "receipt.json"),
                                  states=list(states), failed=failed)
    results["complete"] = all(s["passed"] for s in results["samples"])
    results["summary"] = summarize(cases, results["samples"], args.repeats, states)
    results["growth"] = {"status": "incomplete", "reason": "each installed workload has one size"}
    dump(out / "receipt.json", results)
    print("Compile-time growth checks require several sizes of the same workload", flush=True)
    return 0 if results["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
