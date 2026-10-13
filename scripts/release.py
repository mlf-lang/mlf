#!/usr/bin/env python3
"""Build, verify and install the self-hosted stage 3 compiler.

Builds run serially, including Cabal tests and all benchmark samples. A release
is publishable only after its exact binary passes the full bootstrap corpus,
both native backend matrices, and all nine compilation/runtime limits.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent.parent
LANGUAGES = {"c", "rust", "haskell", "mlf"}
LIMITS = {"compilation": 5.0, "runtime": 2.0}
WORKLOADS = {"binary-trees", "pidigits", "n-body", "fannkuch-redux", "spectral-norm",
             "fasta", "mandelbrot", "reverse-complement", "k-nucleotide"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def gate_environment():
    # Each gate selects its own backend and collector profile. Ambient test
    # overrides must not substitute a different compiler or timing profile.
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("MLF_BOOTSTRAP_", "MLF_LLVM_TEST_", "MLF_TEST_", "GC_"))}


def sources():
    files = {ROOT / "mlf.cabal", ROOT / "cabal.project"}
    for pattern in ("src/**/*.hs", "app/*.hs", "bench/*.hs", "bootstrap/**/*.emlf", "bootstrap/**/*.hs",
                    "bootstrap/**/*.c", "bootstrap/**/*.expected", "test/*", "test/fixtures/*",
                    "runtime/*", "scripts/*.py", "examples/**/*.emlf", "benchmarks/manifest.json",
                    "benchmarks/*/*/*.emlf", "benchmarks/*/*/*.hs", "benchmarks/*/*/*.rs",
                    "benchmarks/*/*/*.c", "benchmarks/*/*.txt", "benchmarks/*/*.pbm"):
        files.update(p for p in ROOT.glob(pattern) if p.is_file())
    return {str(p.relative_to(ROOT)): digest(p) for p in sorted(files)}


def validate_evidence(bootstrap, backends, benchmark, compiler_hash, manifest):
    require(bootstrap.get("complete") is True and bootstrap.get("fixed_point") is True,
            "Bootstrap is incomplete or has no fixed point")
    stages = bootstrap.get("stages", [])
    require([s.get("stage") for s in stages] == [1, 2, 3], "Bootstrap must contain all three stages")
    require(all(s.get("reused_seed_compilation") is False for s in stages), "Release requires fresh stages")
    require(stages[1]["llvm_sha256"] == stages[2]["llvm_sha256"], "Stage 2/3 LLVM differs")
    candidate = bootstrap.get("candidate", {})
    require(candidate.get("stage") == 3 and candidate.get("sha256") == compiler_hash == stages[2]["binary_sha256"],
            "Release candidate must be the verified stage 3 binary")
    parity = bootstrap.get("parity", {})
    require(parity.get("compiler") == candidate["path"] and parity.get("compiler_sha256") == compiler_hash,
            "Parity was not run through the release candidate")
    require(parity.get("cases", 0) >= 7083 and parity.get("accepted", 0) >= 3199 and
            parity.get("rejected", 0) >= 3884 and parity.get("runtime_rows", 0) >= 80 and
            parity.get("runtime_executions") == 2 * parity.get("runtime_rows", 0), "Incomplete parity coverage")
    require(backends.get("complete") is True and backends.get("compiler_sha256") == compiler_hash and
            backends.get("compiler") == candidate["path"], "Native matrices used a different compiler")
    matrices = backends.get("matrices", {})
    require(set(matrices) == {"standard", "compact-gc"}, "Both native layouts must pass")
    for abi, matrix in matrices.items():
        require(matrix.get("rows", 0) >= 475 and matrix.get("fixtures", 0) >= 428 and
                matrix.get("backends") == 2 and matrix.get("cli_compiler") == candidate["path"] and
                matrix.get("environment", {}).get("MLF_LLVM_TEST_ABI") == abi,
                "Incomplete or misdirected native matrix: " + abi)
    require(benchmark.get("status") == "passed" and benchmark["toolchain"]["emlf"]["sha256"] == compiler_hash and
            benchmark["toolchain"]["emlf"]["path"] == candidate["path"], "Benchmark did not validate the candidate")
    config = benchmark["configuration"]
    require(config.get("runs") == 5 and config.get("maximum_mlf_c_ratios") == LIMITS and
            config.get("size_override") is None and not config.get("compile_only") and
            not config.get("runtime_only"), "Wrong release benchmark configuration")
    workloads = {w["name"]: w for w in manifest["workloads"]}
    require(set(workloads) == WORKLOADS, "Unexpected benchmark manifest")
    rows = benchmark["results"]
    require(len(rows) == len(WORKLOADS) and {r["benchmark"] for r in rows} == WORKLOADS,
            "Release benchmark must cover all nine workloads")
    checks = benchmark.get("performance_checks", [])
    require(len(checks) == 18 and {(c["benchmark"], c["dimension"]) for c in checks} ==
            {(w, d) for w in WORKLOADS for d in LIMITS}, "Missing or duplicate performance checks")
    for row in rows:
        workload = workloads[row["benchmark"]]
        require(row["input"] == workload["default_input"] and row["correctness_inputs"] ==
                sorted(set(workload["check_inputs"] + [workload["default_input"]])), "Benchmark inputs changed")
        require(set(row["languages"]) == LANGUAGES, "Benchmark must compare all four languages")
        for language, data in row["languages"].items():
            require(len(data.get("correctness", [])) == len(row["correctness_inputs"]) > 0,
                    "Missing benchmark correctness checks")
            require(all(len(check.get("output_sha256", "")) == 64 for check in data["correctness"]),
                    "Missing benchmark output evidence")
            for dimension in LIMITS:
                measurements = data[dimension]
                require(measurements["sample_count"] == len(measurements["samples"]) == 5,
                        "Missing benchmark samples")
                times = [sample["wall_seconds"] for sample in measurements["samples"]]
                require(all(math.isfinite(t) and t > 0 for t in times) and
                        measurements["median_wall_seconds"] == statistics.median(times),
                        "Invalid or inconsistent benchmark timing")
        for dimension, limit in LIMITS.items():
            ratio = row["languages"]["mlf"][dimension]["median_wall_seconds"] / row["languages"]["c"][dimension]["median_wall_seconds"]
            check = next(c for c in checks if (c["benchmark"], c["dimension"]) == (row["benchmark"], dimension))
            require(check.get("passed") is True and check["maximum_ratio"] == limit and
                    check["mlf_over_c"] == ratio and 0 < ratio <= limit, "Failed or inconsistent performance limit")


def step(name, argv, directory, report):
    log_path = directory / (name + ".log")
    entry = {"name": name, "command": list(map(str, argv)), "started": time.time(), "log": log_path.name}
    print("+ " + shlex.join(entry["command"]), flush=True)
    with log_path.open("wb") as log:
        result = subprocess.run(entry["command"], cwd=ROOT, env=gate_environment(), stdout=log, stderr=subprocess.STDOUT)
    entry.update(finished=time.time(), exit_code=result.returncode, log_sha256=digest(log_path))
    report["steps"].append(entry)
    write_json(directory / "verification.json", report)
    require(result.returncode == 0, f"{name} failed ({result.returncode}); see {log_path}")


def smoke(package):
    """Exercise installed paths and module loading away from the checkout."""
    compiler = package / "emlf"
    env = gate_environment()
    with tempfile.TemporaryDirectory(prefix="mlf release smoke ") as temporary:
        work = Path(temporary)
        (work / "Message.emlf").write_text('module Message where\ndata Message = Message String\nrender (Message text) = text\nmessage = Message "native release"\n')
        source = work / "Main.emlf"
        source.write_text('import Message\nmain = do\n  putStrLn (render message)\n')
        runtime = subprocess.check_output([compiler, "--llvm-runtime"], cwd=work, env=env, text=True).strip()
        require(Path(runtime).resolve() == (package / "runtime/mlf_runtime.c").resolve(),
                "Installed compiler selected a runtime outside its package")
        observed = subprocess.run([compiler, "--run", source], cwd=work, env=env, capture_output=True, check=True)
        require(observed.stdout == b"native release\n" and not observed.stderr, "Installed interpreter smoke failed")
        binary = work / "program"
        subprocess.run([sys.executable, package / "emlf-compile", source, "-o", binary,
                        "-i", work / "unused missing search root"], cwd=work, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        observed = subprocess.run([binary], cwd=work, env=env, capture_output=True, check=True)
        require(observed.stdout == b"native release\n" and not observed.stderr, "Installed LLVM smoke failed")
    return {"backends": ["interpreter", "llvm"], "expected_stdout": "native release\n",
            "outside_checkout": True, "features": ["modules", "algebraic data types", "do", "prelude"]}


def package_files(package):
    return {str(p.relative_to(package)): digest(p) for p in sorted(package.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


def build(directory):
    require(not directory.exists(), "Use a new --output directory; existing release evidence is preserved")
    directory.mkdir(parents=True)
    report = {"schema_version": 1, "complete": False, "started": time.time(), "steps": [],
              "host": {"system": platform.system(), "machine": platform.machine()}, "sources": sources()}
    write_json(directory / "verification.json", report)
    try:
        step("cabal-tests", ["cabal", "test", "-j1", "--test-show-details=direct"], directory, report)
        bootstrap_dir = directory / "bootstrap"
        step("bootstrap", [sys.executable, ROOT / "scripts/bootstrap-compiler.py", "--output", bootstrap_dir], directory, report)
        candidate = bootstrap_dir / "emlf-stage3"
        backend_dir = directory / "backends"
        step("backends", [sys.executable, ROOT / "scripts/bootstrap-backends.py", "--compiler", candidate,
                          "--abi", "both", "--output", backend_dir], directory, report)
        benchmark_path = directory / "benchmarks.json"
        options = shlex.join(["--emlf", str(candidate), "--runs", "5", "--max-compile-ratio", "5",
                              "--max-runtime-ratio", "2", "--output", str(benchmark_path)])
        step("benchmarks", ["cabal", "bench", "compiler-bench", "-j1", "--benchmark-options=" + options], directory, report)
        bootstrap = json.loads((bootstrap_dir / "verification.json").read_text())
        backends = json.loads((backend_dir / "verification.json").read_text())
        benchmark = json.loads(benchmark_path.read_text())
        manifest = json.loads((ROOT / "benchmarks/manifest.json").read_text())
        validate_evidence(bootstrap, backends, benchmark, digest(candidate), manifest)
        require(sources() == report["sources"], "Sources changed during the release gate")
        package = directory / "package"
        (package / "runtime").mkdir(parents=True)
        (package / "evidence").mkdir()
        (package / "licenses").mkdir()
        for source, destination in ((candidate, "emlf"), (ROOT / "scripts/compile_native.py", "emlf-compile"),
                                    (ROOT / "scripts/compiler_process.py", "compiler_process.py")):
            shutil.copy2(source, package / destination)
        for source in (ROOT / "runtime").glob("*"):
            if source.suffix in (".c", ".h"):
                shutil.copy2(source, package / "runtime" / source.name)
        shutil.copy2(ROOT / "dist-newstyle/bootstrap-deps/gc-8.2.12/README.QUICK", package / "licenses/BDWGC.txt")
        shutil.copy2(ROOT / "mlf.cabal", package / "mlf.cabal")
        for source, name in ((bootstrap_dir / "verification.json", "bootstrap.json"),
                             (backend_dir / "verification.json", "backends.json"),
                             (benchmark_path, "benchmarks.json"), (ROOT / "benchmarks/manifest.json", "manifest.json"),
                             (directory / "cabal-tests.log", "cabal-tests.log")):
            shutil.copy2(source, package / "evidence" / name)
        (package / "emlf-compile").chmod(0o755)
        report["smoke"] = smoke(package)
        report["compiler_sha256"] = digest(package / "emlf")
        report["package_files"] = package_files(package)
        require(sources() == report["sources"], "Sources changed while assembling the release")
        report["complete"] = True
        print(f"Verified stage 3 release: {directory}", flush=True)
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        report["error"] = str(error)
        raise
    except KeyboardInterrupt:
        report["error"] = "interrupted"
        raise
    finally:
        report["finished"] = time.time()
        write_json(directory / "verification.json", report)


def verify(directory):
    report = json.loads((directory / "verification.json").read_text())
    require(report.get("schema_version") == 1 and report.get("complete") is True, "Release is incomplete")
    require(report.get("host") == {"system": platform.system(), "machine": platform.machine()},
            "Release was built for a different operating system or architecture")
    package = directory / "package"
    require(package_files(package) == report.get("package_files"), "Release package files changed")
    require(digest(package / "emlf") == report["compiler_sha256"], "Release compiler changed")
    require(all(os.access(package / name, os.X_OK) for name in ("emlf", "emlf-compile")),
            "Release commands are not executable")
    require(report.get("smoke", {}).get("backends") == ["interpreter", "llvm"] and
            report["smoke"].get("outside_checkout") is True, "Missing installed-package validation")
    require([s["name"] for s in report["steps"]] == ["cabal-tests", "bootstrap", "backends", "benchmarks"] and
            all(s["exit_code"] == 0 for s in report["steps"]), "Release steps are incomplete")
    evidence = package / "evidence"
    require(digest(evidence / "cabal-tests.log") == report["steps"][0]["log_sha256"], "Cabal test evidence changed")
    bootstrap, backends, benchmark = [json.loads((evidence / (name + ".json")).read_text())
                                      for name in ("bootstrap", "backends", "benchmarks")]
    validate_evidence(bootstrap, backends, benchmark, report["compiler_sha256"],
                      json.loads((evidence / "manifest.json").read_text()))
    for path, expected in bootstrap["runtime_sources"].items():
        require(digest(package / path) == expected, "Packaged runtime differs from verified runtime")
    return report


def install(directory, prefix):
    directory, prefix = directory.resolve(), prefix.resolve()
    report = verify(directory)
    # Versioned payloads are immutable; never replace an unrelated executable.
    identity = hashlib.sha256(json.dumps(report["package_files"], sort_keys=True).encode()).hexdigest()[:16]
    store = prefix / "libexec/mlf"
    destination = store / identity
    current = store / "current"
    links = {prefix / "bin/emlf": current / "emlf", prefix / "bin/emlf-compile": current / "emlf-compile"}
    if current.exists() or current.is_symlink():
        require(current.is_symlink() and store in current.resolve().parents,
                "Refusing to replace an unrelated current package")
    for link in links:
        if link.exists() or link.is_symlink():
            require(link.is_symlink() and store in link.resolve().parents,
                    "Refusing to replace an unrelated installed command: " + str(link))
    store.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=store) as temporary:
        staged = Path(temporary) / "package"
        shutil.copytree(directory / "package", staged, ignore=shutil.ignore_patterns("__pycache__"))
        require(package_files(staged) == report["package_files"], "Package changed during installation")
        smoke(staged)
        if destination.exists():
            require(package_files(destination) == report["package_files"], "Existing versioned package differs")
        else:
            staged.rename(destination)
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    for link, target in links.items():
        temporary = link.with_name("." + link.name + ".new")
        require(not temporary.exists() and not temporary.is_symlink(), "Installation already in progress")
        temporary.symlink_to(os.path.relpath(target, link.parent))
        temporary.replace(link)
    temporary = store / ".current.new"
    require(not temporary.exists() and not temporary.is_symlink(), "Installation already in progress")
    temporary.symlink_to(identity)
    temporary.replace(current)
    print(f"Installed verified stage 3 compiler: {prefix / 'bin/emlf'}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    builder = commands.add_parser("build", help="Run every gate and assemble an installable stage 3 package")
    builder.add_argument("--output", type=Path, default=ROOT / "dist-newstyle/release")
    for name in ("verify", "install"):
        command = commands.add_parser(name)
        command.add_argument("--release", type=Path, default=ROOT / "dist-newstyle/release")
        if name == "install":
            command.add_argument("--prefix", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            return build(args.output.resolve())
        if args.command == "install":
            return install(args.release.resolve(), args.prefix.resolve())
        verify(args.release.resolve())
        print("Release identity, correctness and performance evidence verified.")
        return 0
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print("release: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("release: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
