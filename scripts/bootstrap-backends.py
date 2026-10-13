#!/usr/bin/env python3
"""Rebuild native MLF drivers and run the complete two-backend Cabal matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
INTERPOSE = ["-Dgetline=mlf_test_getline", "-Dfwrite=mlf_test_fwrite",
             "-Dfputc=mlf_test_fputc", "-Dfflush=mlf_test_fflush"]
BUILD = ["cabal", "build", "exe:emlf", "test:backend-tests", "-j1"]
TEST = ["cabal", "test", "backend-tests", "-j1", "--test-show-details=direct"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources() -> dict[str, str]:
    files = {ROOT / "mlf.cabal", ROOT / "test" / "native_trace.c", Path(__file__).resolve()}
    for pattern in ("bootstrap/**/*.emlf", "src/**/*.hs", "app/*.hs", "test/*.hs",
                    "runtime/*.c", "runtime/*.h", "scripts/bootstrap-gc.py"):
        files.update(ROOT.glob(pattern))
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted(files)}


def show(argv, output=None, errors=None):
    text = "+ " + shlex.join(map(str, argv))
    if output is not None:
        text += " > " + shlex.quote(str(output))
    if errors is not None:
        text += " 2> " + shlex.quote(str(errors))
    print(text, flush=True)


def run(argv, *, env, capture=False):
    show(argv)
    result = subprocess.run(list(map(str, argv)), cwd=ROOT, env=env,
                            stdout=subprocess.PIPE if capture else None,
                            text=True, check=True)
    return result.stdout if capture else None


def runtime_commands(directory, gmp_cflags, gc_cflags):
    common = ["clang", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
              "-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", "-DMLF_GC_THRESHOLD=1048576", *gmp_cflags, *gc_cflags]
    runtime = ROOT / "runtime" / "mlf_runtime.c"
    return [common + ["-c", runtime, "-o", directory / "runtime.o"],
            common + INTERPOSE + ["-c", runtime, "-o", directory / "runtime-traced.o"],
            ["clang", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-c",
             ROOT / "test" / "native_trace.c", "-o", directory / "trace.o"]]


def driver_commands(directory, compiler, gmp_libs, gc_libs, system):
    stack = ["-Wl,-stack_size,0x4000000"] if system == "Darwin" else []
    for name, objects in (
            ("RuntimeDriver", [directory / "runtime-traced.o", directory / "trace.o"]),
            ("LLVMDriver", [directory / "runtime.o"])):
        ir = directory / (name + ".ll")
        errors = directory / (name + ".stderr")
        executable = directory / name
        emit = [compiler, "-i", ROOT / "bootstrap", "--emit-llvm-gc",
                ROOT / "bootstrap" / (name + ".emlf")]
        link = ["clang", "-O2", "-Wno-override-module", ir, *objects,
                *gmp_libs, "-lm", *gc_libs, *stack, "-o", executable]
        yield name, emit, ir, errors, link, executable


def environment(directory, seed, compiler, abi="standard", gc=None):
    env = os.environ.copy()
    # The drivers use BDWGC; generated programs use the ordinary test runtime.
    # Do not accidentally inherit a different matrix/profile from the caller.
    for key in ("MLF_TEST_TRACE", "MLF_TEST_FAIL_WRITE"):
        env.pop(key, None)
    env.update(MLF_BOOTSTRAP_INTERPRETER=str(directory / "RuntimeDriver"),
               MLF_BOOTSTRAP_LLVM=str(directory / "LLVMDriver"),
               MLF_BOOTSTRAP_COMPILER=str(compiler),
               MLF_BOOTSTRAP_TIMEOUT_SECONDS="1800",
               MLF_LLVM_TEST_ABI="standard", MLF_LLVM_TEST_CFLAGS="", MLF_LLVM_TEST_LIBS="", MLF_LLVM_TEST_OPT="-O2",
               GC_INITIAL_HEAP_SIZE="536870912", GC_FREE_SPACE_DIVISOR="1")
    env["PATH"] = str(seed.parent) + os.pathsep + env.get("PATH", "")
    if abi == "compact-gc":
        if gc is None:
            raise ValueError("Compact backend matrix requires collector flags")
        env.update(MLF_LLVM_TEST_ABI=abi,
                   MLF_LLVM_TEST_CFLAGS=shlex.join(gc["cflags"]),
                   MLF_LLVM_TEST_LIBS=shlex.join(gc["libs"]),
                   GC_INITIAL_HEAP_SIZE="8388608")
    elif abi != "standard":
        raise ValueError("Unknown backend matrix ABI: " + abi)
    return env


def dry_run(directory, compiler, abis):
    print("Plan only: no commands executed, drivers reused, or test result recorded.")
    seed = Path("<cabal-seed-directory>") / "emlf"
    show(BUILD)
    show(["cabal", "list-bin", "exe:emlf"])
    show(["pkg-config", "--cflags", "gmp"])
    show(["pkg-config", "--libs", "gmp"])
    show([sys.executable, ROOT / "scripts" / "bootstrap-gc.py", "--flags"])
    for argv in runtime_commands(directory, ["<GMP cflags>"], ["<BDWGC cflags>"]):
        show(argv)
    for _, emit, ir, errors, link, _ in driver_commands(
            directory, compiler or seed, ["<GMP libraries>"], ["<BDWGC libraries>"], platform.system()):
        show(emit, ir, errors)
        show(link)
    for abi in abis:
        env = environment(directory, seed, compiler or seed, abi,
                          {"cflags": ["<BDWGC cflags>"], "libs": ["<BDWGC libraries>"]})
        print(f"Matrix environment ({abi}):")
        for key in ("MLF_BOOTSTRAP_INTERPRETER", "MLF_BOOTSTRAP_LLVM", "MLF_BOOTSTRAP_COMPILER", "MLF_BOOTSTRAP_TIMEOUT_SECONDS",
                    "MLF_LLVM_TEST_ABI", "MLF_LLVM_TEST_CFLAGS", "MLF_LLVM_TEST_LIBS", "MLF_LLVM_TEST_OPT",
                    "GC_INITIAL_HEAP_SIZE", "GC_FREE_SPACE_DIVISOR"):
            print(f"  {key}={shlex.quote(env[key])}")
        print("  PATH=<cabal-seed-directory>:<inherited PATH>")
        show(TEST)


def matrix_summary(text, compiler):
    rows = re.findall(r"^Backend matrix: ([0-9]+) rows x 2 backends; no missing executions$", text, re.M)
    fixtures = re.findall(r"^([0-9]+) shared IO/prelude/backend fixtures; 0 failures$", text, re.M)
    if len(rows) != 1 or len(fixtures) != 1 or int(rows[0]) == 0 or int(fixtures[0]) == 0:
        raise RuntimeError("Cabal did not report one complete, nonempty two-backend matrix")
    selected = re.findall(r"^Module CLI compiler: (.+)$", text, re.M)
    if selected != [str(Path(compiler).resolve())]:
        raise RuntimeError("Module CLI tests did not execute the selected compiler exactly once")
    return {"rows": int(rows[0]), "backends": 2, "fixtures": int(fixtures[0]),
            "cli_compiler": selected[0]}


def matrix(env, log_path):
    show(TEST)
    with log_path.open("w") as log:
        with subprocess.Popen(TEST, cwd=ROOT, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
            for line in process.stdout:
                print(line, end="", flush=True)
                log.write(line)
                log.flush()
            status = process.wait()
    if status:
        raise RuntimeError(f"Cabal backend-tests failed ({status}); see {log_path}")
    return matrix_summary(log_path.read_text(), env["MLF_BOOTSTRAP_COMPILER"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path,
                        help="Compiler used to build both drivers; defaults to the Cabal Haskell seed")
    parser.add_argument("--output", type=Path, default=ROOT / "dist-newstyle" / "bootstrap-backends",
                        help="Driver artifacts, build diagnostics, matrix log and verification report")
    parser.add_argument("--abi", choices=("standard", "compact-gc", "both"), default="standard",
                        help="Generated-program layouts to test; both rebuilds the drivers once and runs both matrices")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the command plan without building, reusing drivers, or running tests")
    args = parser.parse_args()
    directory = args.output.resolve()
    compiler = args.compiler.resolve() if args.compiler else None
    abis = ("standard", "compact-gc") if args.abi == "both" else (args.abi,)
    if args.dry_run:
        dry_run(directory, compiler, abis)
        return 0
    if compiler is not None and (not compiler.is_file() or not os.access(compiler, os.X_OK)):
        parser.error(f"--compiler is not an executable file: {compiler}")
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "verification.json"
    report = {"schema_version": 2, "complete": False, "started": time.time(), "drivers": {}, "matrices": {}}
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    try:
        build_env = os.environ.copy()
        run(BUILD, env=build_env)
        seed = Path(run(["cabal", "list-bin", "exe:emlf"], env=build_env, capture=True).strip()).resolve()
        compiler = compiler or seed
        if not compiler.is_file() or not os.access(compiler, os.X_OK):
            raise RuntimeError(f"Compiler is not executable: {compiler}")
        report.update(compiler=str(compiler), compiler_sha256=digest(compiler),
                      seed=str(seed), seed_sha256=digest(seed), sources=sources())
        env = environment(directory, seed, compiler)
        report["environment"] = {key: env[key] for key in (
            "MLF_BOOTSTRAP_INTERPRETER", "MLF_BOOTSTRAP_LLVM", "MLF_BOOTSTRAP_COMPILER", "MLF_BOOTSTRAP_TIMEOUT_SECONDS",
            "MLF_LLVM_TEST_ABI", "MLF_LLVM_TEST_CFLAGS", "MLF_LLVM_TEST_LIBS", "MLF_LLVM_TEST_OPT",
            "GC_INITIAL_HEAP_SIZE", "GC_FREE_SPACE_DIVISOR")}
        gmp_cflags = shlex.split(run(["pkg-config", "--cflags", "gmp"], env=env, capture=True))
        gmp_libs = shlex.split(run(["pkg-config", "--libs", "gmp"], env=env, capture=True))
        gc = json.loads(run([sys.executable, ROOT / "scripts" / "bootstrap-gc.py", "--flags"],
                            env=env, capture=True))
        report["allocator"] = {"profile": "BDWGC compact", "flags": gc, "io_threshold": 1048576,
                               "macos_stack_bytes": 67108864 if platform.system() == "Darwin" else None}
        for argv in runtime_commands(directory, gmp_cflags, gc["cflags"]):
            run(argv, env=env)
        for name, emit, ir, errors, link, executable in driver_commands(
                directory, compiler, gmp_libs, gc["libs"], platform.system()):
            show(emit, ir, errors)
            with ir.open("wb") as out, errors.open("wb") as err:
                subprocess.run(list(map(str, emit)), cwd=ROOT, env=env,
                               stdout=out, stderr=err, check=True)
            if ir.stat().st_size == 0:
                raise RuntimeError(f"Compiler emitted an empty module: {ir}")
            run(link, env=env)
            report["drivers"][name] = {"llvm_sha256": digest(ir), "binary_sha256": digest(executable)}
        if sources() != report["sources"] or digest(compiler) != report["compiler_sha256"]:
            raise RuntimeError("Compiler or sources changed while building the drivers")
        for abi in abis:
            matrix_env = environment(directory, seed, compiler, abi, gc)
            summary = matrix(matrix_env, directory / ("matrix.log" if len(abis) == 1 else f"matrix-{abi}.log"))
            report["matrices"][abi] = {**summary, "environment": {key: matrix_env[key] for key in report["environment"]}}
        if len(abis) == 1:
            report["matrix"] = summary
        if (sources() != report["sources"] or digest(compiler) != report["compiler_sha256"] or
                digest(seed) != report["seed_sha256"]):
            raise RuntimeError("Compiler, seed or sources changed during the backend matrix")
        report["complete"] = True
        print(f"Native MLF backend matrix passed; report: {report_path}", flush=True)
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        report["error"] = str(error)
        print(f"bootstrap backends: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        report["error"] = "interrupted"
        print("bootstrap backends: interrupted", file=sys.stderr)
        return 130
    finally:
        report["finished"] = time.time()
        report_path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())
