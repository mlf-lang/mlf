#!/usr/bin/env python3
"""Pinned, single-threaded cross-language benchmarks. Primary entry: cabal bench."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = ("c", "rust", "haskell", "mlf")
LABELS = {"c": "Clang/C", "rust": "rustc/Rust", "haskell": "GHC/Haskell", "mlf": "MLF/LLVM"}
DISCLAIMER = ("This benchmark measures practical end-to-end compiler/language implementation "
              "performance. It does NOT perfectly isolate backend code-generation quality "
              "because C, Rust, Haskell and MLF have different language semantics, runtime "
              "systems, allocation models and abstractions.")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_integrity(fingerprints):
    for path, expected in fingerprints.items():
        if digest(ROOT / path) != expected:
            raise ValueError(f"Input changed during benchmarking: {path}")


def load_manifest(path=ROOT / "benchmarks/manifest.json"):
    manifest = json.loads(path.read_text())
    if manifest["schema_version"] != 1 or not manifest["workloads"]:
        raise ValueError("Unsupported or empty benchmark manifest")
    for name, expected in manifest["pinned_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Pinned source checksum mismatch: {name}")
    for workload in manifest["workloads"]:
        if set(workload["sources"]) != set(LANGUAGES):
            raise ValueError(f"{workload['name']}: all four languages are required")
    return manifest


def expected_output(workload, size):
    # Independent mathematical oracle, used only in the driver, never in a
    # measured executable. Also checked against the pinned upstream fixture.
    if workload["name"] != "binary-trees":
        raise ValueError("No correctness oracle for " + workload["name"])
    maximum = max(6, size)
    lines = [f"stretch tree of depth {maximum + 1} check: {2 ** (maximum + 2) - 1}"]
    for depth in range(4, maximum + 1, 2):
        iterations = 2 ** (maximum - depth + 4)
        lines.append(f"{iterations} trees of depth {depth} check: {iterations * (2 ** (depth + 1) - 1)}")
    lines.append(f"long lived tree of depth {maximum} check: {2 ** (maximum + 1) - 1}")
    return "\n".join(lines).encode()


def validate_output(workload, size, output):
    # Whitespace ONLY. Extra/missing tokens, wrong signs and checks all fail.
    expected = expected_output(workload, size)
    if output.split() != expected.split():
        raise ValueError(f"{workload['name']}({size}) output mismatch:\n"
                         f"expected: {expected!r}\nactual: {output[:4096]!r}")


def run(command, *, data=b"", cwd=ROOT, env=None, timeout=600, output_file=None):
    """POSIX wait4 gives per-child CPU/RSS (not cumulative child high-water RSS).

    Files prevent pipe deadlocks and keep output parsing outside wall timing.
    An alarm bounds wait4; timeout kills and reaps the whole process group.
    """
    with tempfile.TemporaryFile() as inp, tempfile.TemporaryFile() as err:
        inp.write(data)
        inp.seek(0)
        out = open(output_file, "w+b") if output_file else tempfile.TemporaryFile()
        child = None

        def expired(_signum, _frame):
            raise TimeoutError(f"Command exceeded {timeout}s: {shlex.join(command)}")

        previous = signal.signal(signal.SIGALRM, expired)
        try:
            signal.setitimer(signal.ITIMER_REAL, timeout)
            start = time.perf_counter()
            child = subprocess.Popen(command, stdin=inp, stdout=out, stderr=err,
                                     cwd=cwd, env=env, start_new_session=True)
            _, status, usage = os.wait4(child.pid, 0)
            elapsed = time.perf_counter() - start
            child.returncode = os.waitstatus_to_exitcode(status)
            signal.setitimer(signal.ITIMER_REAL, 0)
            err.seek(0)
            errors = err.read()
            if child.returncode:
                raise RuntimeError(f"Command exited {child.returncode}: {shlex.join(command)}\n"
                                   + errors.decode(errors="replace"))
            out.seek(0)
            output = b"" if output_file else out.read()
            return {"command": command, "cwd": str(cwd), "wall_seconds": elapsed,
                    "user_seconds": usage.ru_utime, "system_seconds": usage.ru_stime,
                    "cpu_seconds": usage.ru_utime + usage.ru_stime,
                    "peak_rss_bytes": int(usage.ru_maxrss * (1 if sys.platform == "darwin" else 1024)),
                    "stderr": errors.decode(errors="replace")}, output
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous)
            if child is not None and child.returncode is None:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, _ = os.wait4(child.pid, 0)
                child.returncode = os.waitstatus_to_exitcode(status)
            out.close()


def tool(name):
    path = shutil.which(str(name))
    if path is None:
        raise ValueError(f"Required tool not found: {name}")
    return str(Path(path).absolute())


def toolchain(args, env):
    paths = {name: tool(getattr(args, name)) for name in ("clang", "rustc", "ghc", "emlf", "pkg_config")}
    probes = {"clang": ["--version"], "rustc": ["--version", "--verbose"],
              "ghc": ["--version"], "emlf": ["+RTS", "--info", "-RTS"],
              "pkg_config": ["--version"]}
    versions = {}
    for name, options in probes.items():
        _, output = run([paths[name], *options], env=env)
        versions[name] = output.decode().strip()
    _, output = run([paths["emlf"], "--llvm-runtime"], env=env)
    runtime = Path(os.fsdecode(output).strip()).resolve(strict=True)
    _, output = run([paths["pkg_config"], "--cflags", "--libs", "gmp"], env=env)
    gmp = shlex.split(output.decode())
    metadata = {name: {"path": path, "version": versions[name], "sha256": digest(path)}
                for name, path in paths.items()}
    metadata["runtime"] = {"path": str(runtime), "sha256": digest(runtime),
                           "header_sha256": digest(runtime.with_suffix(".h"))}
    metadata["gmp_flags"] = gmp
    _, output = run([paths["pkg_config"], "--modversion", "gmp"], env=env)
    metadata["gmp_version"] = output.decode().strip()
    return paths, runtime, gmp, metadata


def build(workload, language, directory, paths, runtime, gmp, env, timeout):
    directory.mkdir(parents=True)  # Fail if the supposedly fresh directory exists.
    source = str(ROOT / workload["sources"][language])
    binary = directory / "program"
    ir = directory / "program.ll"
    flags = workload["flags"][language]
    if language == "c":
        commands = [([paths["clang"], *flags, source, "-lm", "-o", str(binary)], None)]
    elif language == "rust":
        commands = [([paths["rustc"], *flags, source, "-o", str(binary)], None)]
    elif language == "haskell":
        commands = [([paths["ghc"], *flags, source, "-outputdir", str(directory), "-o", str(binary)], None)]
    else:
        commands = [([paths["emlf"], "--emit-llvm", source], ir),
                    ([paths["clang"], *flags, str(ir), str(runtime), *gmp, "-o", str(binary)], None)]
    start = time.perf_counter()
    stages = []
    for command, output in commands:
        sample, _ = run(command, cwd=directory, env=env, timeout=timeout, output_file=output)
        if output:
            sample["stdout_file"] = str(output)
        stages.append(sample)
    wall = time.perf_counter() - start
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError(f"{language} compilation did not produce an executable")
    return binary, {"wall_seconds": wall, "cpu_seconds": sum(s["cpu_seconds"] for s in stages),
                    "peak_rss_bytes": max(s["peak_rss_bytes"] for s in stages), "stages": stages,
                    "executable_bytes": binary.stat().st_size, "executable_sha256": digest(binary)}


def execute(workload, language, binary, size, env, timeout):
    command = [str(binary)] + ([] if language == "mlf" else [str(size)])
    data = f"{size}\n".encode() if language == "mlf" else b""
    sample, output = run(command, data=data, env=env, timeout=timeout)
    validate_output(workload, size, output)
    sample.update(stdin=data.decode(), output_sha256=hashlib.sha256(output).hexdigest())
    return sample


def summarize(samples):
    if not samples:
        return None
    return {"samples": samples, "sample_count": len(samples),
            "median_wall_seconds": statistics.median(s["wall_seconds"] for s in samples),
            "median_cpu_seconds": statistics.median(s["cpu_seconds"] for s in samples),
            "max_peak_rss_bytes": max(s["peak_rss_bytes"] for s in samples)}


def ratios(values):
    baseline = values["c"]
    if any(not math.isfinite(v) or v <= 0 for v in values.values()):
        raise ValueError("Ratios require finite positive measurements")
    return {language: value / baseline for language, value in values.items()}


def render(report):
    print("\nMLF cross-language benchmarks (smaller times/ratios are better)")
    for dimension in ("compilation", "runtime"):
        rows = [row for row in report["results"] if row["languages"]["c"][dimension]]
        if not rows:
            continue
        print(f"\n=== {dimension.capitalize()} ===")
        print(f"{'workload':<22}" + "".join(f"{LABELS[l]:>17}" for l in LANGUAGES))
        for row in rows:
            print(f"{row['benchmark']:<22}" + "".join(
                f"{row['languages'][l][dimension]['median_wall_seconds'] * 1000:>14.2f} ms" for l in LANGUAGES))
            print(f"{'relative to C':<22}" + "".join(f"{row[dimension + '_ratios'][l]:>16.2f}x" for l in LANGUAGES))
        geomean = report["geometric_means"][dimension]
        if geomean:
            print(f"{'geometric mean':<22}" + "".join(f"{geomean[l]:>16.2f}x" for l in LANGUAGES))
        else:
            print("Geometric mean omitted: only one workload.")
    for row in report["results"]:
        print(f"\n{row['benchmark']}: input={row['input']}; pre-timing correctness passed for all four languages")
        print(f"{'language':<16}{'runtime CPU (s)':>18}{'peak RSS (MiB)':>18}{'binary (KiB)':>18}")
        for language in LANGUAGES:
            item = row["languages"][language]
            cpu = f"{item['runtime']['median_cpu_seconds']:.4f}" if item["runtime"] else "unmeasured"
            rss = f"{item['runtime']['max_peak_rss_bytes'] / 2**20:.2f}" if item["runtime"] else "unmeasured"
            print(f"{LABELS[language]:<16}{cpu:>18}{rss:>18}{item['executable_bytes'] / 1024:>18.2f}")
    for warning in report["warnings"]:
        print("Measurement note: " + warning)
    print("\n" + DISCLAIMER)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as output:
        json.dump(data, output, indent=2, allow_nan=False)
        output.write("\n")
        temporary = Path(output.name)
    temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emlf", required=True)
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--rustc", default="rustc")
    parser.add_argument("--ghc", default="ghc")
    parser.add_argument("--pkg-config", default="pkg-config")
    parser.add_argument("--benchmark", action="append", help="select a manifest workload (repeatable)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compile-only", action="store_true")
    mode.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--runs", type=int, default=3, help="samples per language per dimension, at least 2")
    parser.add_argument("--size", type=int, help="override workload input; binary-trees maximum depth 0..20")
    parser.add_argument("--timeout", type=float, default=600, help="seconds per subprocess")
    parser.add_argument("--output", type=Path, default=ROOT / "bench-results.json")
    args = parser.parse_args(argv)
    if args.runs < 2 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--runs must be at least 2; --timeout must be finite and positive")
    report = {"schema_version": 1, "status": "running",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "disclaimer": DISCLAIMER,
              "host": {"os": platform.system(), "release": platform.release(),
                       "platform": platform.platform(), "architecture": platform.machine(),
                       "logical_cpus": os.cpu_count(), "python": platform.python_version()},
              "configuration": {"runs": args.runs, "size_override": args.size,
                                "compile_only": args.compile_only, "runtime_only": args.runtime_only,
                                "timeout_seconds": args.timeout},
              "results": [], "warnings": [], "geometric_means": {}, "corpus_compilation": None}
    try:
        if sys.platform not in ("darwin", "linux"):
            raise ValueError("Per-process wait4 measurement currently supports macOS and Linux")
        manifest = load_manifest()
        names = args.benchmark or [w["name"] for w in manifest["workloads"]]
        workloads = [w for w in manifest["workloads"] if w["name"] in names]
        if set(names) != {w["name"] for w in workloads}:
            raise ValueError("Unknown benchmark; available: " + ", ".join(w["name"] for w in manifest["workloads"]))
        sizes = {w["name"]: args.size if args.size is not None else w["default_input"] for w in workloads}
        for w in workloads:
            if not w["minimum_input"] <= sizes[w["name"]] <= w["maximum_input"]:
                raise ValueError(f"{w['name']}: input must be {w['minimum_input']}..{w['maximum_input']}")
            validate_output(w, 10, (ROOT / w["fixture"]).read_bytes())
        # Prevent inherited runtime tuning from silently changing the comparison.
        env = dict(os.environ, LC_ALL="C", LANG="C", GHCRTS="", GHC_ENVIRONMENT="-")
        report["controlled_environment"] = {k: env[k] for k in ("LC_ALL", "LANG", "GHCRTS", "GHC_ENVIRONMENT")}
        paths, runtime, gmp, report["toolchain"] = toolchain(args, env)
        report["manifest"] = manifest
        report["source_sha256"] = {name: digest(ROOT / name) for name in
                                    {p for w in workloads for p in w["sources"].values()}}
        report["harness_sha256"] = digest(__file__)
        inputs = [*report["source_sha256"], *manifest["pinned_sha256"],
                  "benchmarks/manifest.json", str(Path(__file__).resolve()),
                  *paths.values(), str(runtime), str(runtime.with_suffix(".h"))]
        report["input_sha256"] = {name: digest(ROOT / name) for name in inputs}
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
        report["repository"] = {"revision": git.stdout.strip() if git.returncode == 0 else None,
                                "dirty": bool(status.stdout) if status.returncode == 0 else None}
        report["methodology"] = {
            "compile": "Fresh serial source-to-executable builds, including MLF LLVM emission, IR writes, "
                       "runtime C compilation and linking. Tool/compiler/harness setup excluded. "
                       "Fresh output directory per sample; no object cache. Rotating language order.",
            "runtime": "All binaries built and checked before any timed samples; exact runtime input checked "
                       "once before timing as warmup. Process startup/IO/GC/exit included. Output checked "
                       "again after each sample, outside timing. No time subtraction.",
            "resource_measurement": "wait4 child usage: user+system CPU; Darwin RSS bytes, Linux RSS KiB "
                                    "converted to bytes. Pipeline CPU summed, RSS maximum over stages.",
            "normalization": "Wall medians divided by C wall median; ratio below 1 is allowed."}
        scratch_parent = ROOT / "dist-newstyle/benchmarks"
        scratch_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="languages-", dir=scratch_parent) as temporary:
            scratch = Path(temporary)
            prepared = {}
            for workload in workloads:
                name = workload["name"]
                row = {"benchmark": name, "input": sizes[name], "languages": {},
                       "correctness_inputs": sorted(set(workload["check_inputs"] + ([] if args.compile_only else [sizes[name]])))}
                report["results"].append(row)
                for language in LANGUAGES:
                    print(f"Prepare and validate {name}/{language}: inputs {row['correctness_inputs']}", flush=True)
                    binary, preparation = build(workload, language, scratch / name / language / "prepared",
                                               paths, runtime, gmp, env, args.timeout)
                    checks = [execute(workload, language, binary, size, env, args.timeout)
                              for size in row["correctness_inputs"]]
                    prepared[name, language] = binary
                    row["languages"][language] = {"source": workload["sources"][language],
                        "compiler_flags": workload["flags"][language], "preparation": preparation,
                        "correctness": checks, "executable_bytes": binary.stat().st_size,
                        "compilation": [], "runtime": []}
            print("All four outputs match the oracle and pinned fixture; starting measurements.", flush=True)
            for dimension in ("compilation", "runtime"):
                if (dimension == "compilation" and args.runtime_only) or (dimension == "runtime" and args.compile_only):
                    continue
                for repetition in range(args.runs):
                    order = LANGUAGES[repetition % 4:] + LANGUAGES[:repetition % 4]
                    for workload, row in zip(workloads, report["results"]):
                        name = workload["name"]
                        for language in order:
                            print(f"{dimension} {repetition + 1}/{args.runs}: {name}/{language}", flush=True)
                            if dimension == "compilation":
                                binary, sample = build(workload, language, scratch / name / language / f"sample-{repetition}",
                                                       paths, runtime, gmp, env, args.timeout)
                                # The just-timed product must itself work; this run is NOT timed as compilation.
                                sample["post_build_check"] = execute(workload, language, binary, 6, env, args.timeout)
                            else:
                                sample = execute(workload, language, prepared[name, language], sizes[name], env, args.timeout)
                            sample["round"] = repetition + 1
                            sample["order_in_round"] = list(order).index(language)
                            row["languages"][language][dimension].append(sample)
            for row in report["results"]:
                for language in LANGUAGES:
                    for dimension in ("compilation", "runtime"):
                        row["languages"][language][dimension] = summarize(row["languages"][language][dimension])
                for dimension in ("compilation", "runtime"):
                    row[dimension + "_ratios"] = ratios({l: row["languages"][l][dimension]["median_wall_seconds"]
                                                           for l in LANGUAGES}) if row["languages"]["c"][dimension] else None
                for language in LANGUAGES:
                    runtime_result = row["languages"][language]["runtime"]
                    if runtime_result and runtime_result["median_wall_seconds"] < 0.1:
                        report["warnings"].append(f"{row['benchmark']}/{language} ran below 100 ms; "
                                                   "use a larger --size for performance conclusions.")
            for dimension in ("compilation", "runtime"):
                rs = [row[dimension + "_ratios"] for row in report["results"] if row[dimension + "_ratios"]]
                report["geometric_means"][dimension] = {
                    l: math.exp(statistics.mean(math.log(r[l]) for r in rs)) for l in LANGUAGES
                } if len(rs) > 1 else None
            if not args.runtime_only:
                # The aggregate is explicitly a sum, not an invented persistent compiler measurement.
                corpus = {}
                for language in LANGUAGES:
                    totals = [sum(row["languages"][language]["compilation"]["samples"][r]["wall_seconds"]
                                  for row in report["results"]) for r in range(args.runs)]
                    median = statistics.median(totals)
                    corpus[language] = {"summed_wall_samples_seconds": totals, "median_seconds": median,
                                        "programs_per_second": len(workloads) / median}
                report["corpus_compilation"] = {"program_count": len(workloads), "languages": corpus,
                    "scope": "Sum of fresh per-program latencies per round; includes each compiler startup. "
                             "With one workload this duplicates latency and does not isolate processing throughput."}
            check_integrity(report["input_sha256"])
            report["input_integrity"] = "All recorded source, manifest, harness, compiler and runtime hashes unchanged"
            report["status"] = "passed"
            report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(args.output, report)
        render(report)
        print(f"\nRaw samples, commands, provenance and metadata: {args.output.resolve()}")
        return 0
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as error:
        report.update(status="failed", error=str(error))
        atomic_json(args.output, report)
        print(f"Benchmark failed: {error}\nFailure report: {args.output.resolve()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
