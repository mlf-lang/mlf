#!/usr/bin/env python3
"""Build the real MLF compiler through three native stages and verify parity.

The seed is used to build stage 1 and to provide independent test oracles.
Only the previous native MLF stage compiles the next stage's MLF sources.
Clang links ordinary generated LLVM against the generic language runtime.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
import time
from runtime_st_validation import validate_st_runtime

ROOT = Path(__file__).resolve().parent.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, *, cwd=ROOT, stdin=None, stdout=None, stderr=None, env=None):
    print("+ " + shlex.join(map(str, argv)), flush=True)
    return subprocess.run(list(map(str, argv)), cwd=cwd, input=stdin,
                          stdout=stdout, stderr=stderr, env=env, check=True)


def emit(compiler: Path, source: Path, output: Path, log: Path, env=None) -> float:
    started = time.monotonic()
    with output.open("wb") as out, log.open("wb") as err:
        command([compiler, "-i", ROOT / "bootstrap", "--emit-llvm-gc", source],
                stdout=out, stderr=err, env=env)
    if output.stat().st_size == 0:
        raise RuntimeError(f"Compiler emitted an empty module: {output}")
    return time.monotonic() - started


def link(ir: Path, binary: Path, runtime: Path, flags: list[str]):
    command(["clang", "-O2", "-Wno-override-module", ir, runtime, "-lm",
             *flags, "-o", binary])


def gc_defaults(probe: Path) -> list[dict]:
    """Check runtime preferences and collector overrides in fresh processes."""
    mib = 1024 * 1024
    cases = [
        ("default", {}, [], 512 * mib, None, 1),
        ("initial-override", {"GC_INITIAL_HEAP_SIZE": str(8 * mib)}, [], 8 * mib, 8 * mib, 1),
        ("divisor-override", {"GC_FREE_SPACE_DIVISOR": "5"}, [], 512 * mib, None, 5),
        ("both-overrides", {"GC_INITIAL_HEAP_SIZE": str(8 * mib), "GC_FREE_SPACE_DIVISOR": "5"},
         [], 8 * mib, 8 * mib, 5),
        ("environment-cap", {"GC_MAXIMUM_HEAP_SIZE": str(32 * mib)}, [], 1, 32 * mib, 1),
        ("api-cap", {}, ["api-cap"], 1, 8 * mib, 1),
    ]
    # A caller's collector tuning must not mask either the runtime defaults or
    # the deliberately chosen overrides checked by these isolated processes.
    clean_environment = {name: value for name, value in os.environ.items()
                         if not name.startswith("GC_")}
    results = []
    for name, overrides, arguments, minimum, maximum, divisor in cases:
        checked = command([probe, *arguments], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env={**clean_environment, **overrides})
        observed = json.loads(checked.stdout)
        heap = observed.get("heap_bytes")
        if (checked.stderr or type(heap) is not int or heap < minimum or
                (maximum is not None and heap > maximum) or observed.get("divisor") != divisor):
            raise RuntimeError(f"Allocator {name} regression: {observed}, stderr={checked.stderr!r}")
        results.append({"name": name, "environment": overrides, "arguments": arguments, **observed})
    return results


def allocation_cases(probe: Path, collector: bool) -> list[dict]:
    """Check constructor allocation with public ABI and independent C callbacks."""
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith("GC_")}
    modes = ["success", "no-interior", "incremental"] if collector else ["success"]
    failures = {"negative-tag": "invalid constructor descriptor", "short": "invalid constructor descriptor",
                "overflow": "invalid constructor descriptor", "unset-slot": "invalid environment read"}
    results = []
    for mode in modes + list(failures):
        checked = subprocess.run([str(probe), mode], cwd=ROOT, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, env=environment, timeout=60)
        if mode in failures:
            expected_error = ("Runtime: " + failures[mode] + "\n").encode()
            if checked.returncode != 1 or checked.stdout or checked.stderr != expected_error:
                raise RuntimeError(f"Allocation {mode} rejection changed: {checked}")
            observed = {"exit_code": 1, "error": failures[mode]}
        else:
            if checked.returncode or checked.stderr:
                raise RuntimeError(f"Allocation {mode} regression: {checked}")
            observed = json.loads(checked.stdout)
            retained = observed.get("retained_bytes")
            if (observed.get("constructor_arities") != 7 or observed.get("field_evaluations") != 8 or
                    observed.get("zero_environments") != 4100 or type(retained) is not int or
                    retained < 0 or retained >= 4 * 1024 * 1024 or (not collector and retained != 0)):
                raise RuntimeError(f"Allocation {mode} regression: {observed}")
        results.append({"mode": mode, **observed})
    return results


def allocation_regressions(directory: Path, runtime_source: Path, runtime: Path, bootstrap_runtime: Path,
                           cflags: list[str], flags: list[str], gc_flags: dict) -> dict:
    source = ROOT / "test" / "runtime_allocation.c"
    standard_runtime = directory / "bootstrap-runtime-standard.o"
    command(["clang", "-O2", "-std=c11", "-DMLF_USE_BDWGC", *cflags,
             *gc_flags["cflags"], "-c", runtime_source, "-o", standard_runtime])
    compact_debug_runtime = directory / "bootstrap-runtime-compact-debug.o"
    command(["clang", "-O2", "-std=c11", "-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", "-DGC_DEBUG",
             *cflags, *gc_flags["cflags"], "-c", runtime_source, "-o", compact_debug_runtime])
    debug_runtime = directory / "bootstrap-runtime-debug.o"
    command(["clang", "-O2", "-std=c11", "-DMLF_USE_BDWGC", "-DGC_DEBUG",
             "-DMLF_GC_THRESHOLD=1048576", *cflags, *gc_flags["cflags"], "-c", runtime_source,
             "-o", debug_runtime])
    variants = [("ordinary", runtime, [], []),
                ("bdwgc", standard_runtime, ["-DMLF_USE_BDWGC", *gc_flags["cflags"]], gc_flags["libs"]),
                ("bdwgc-compact", bootstrap_runtime,
                 ["-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", *gc_flags["cflags"]], gc_flags["libs"]),
                ("bdwgc-compact-debug", compact_debug_runtime,
                 ["-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", "-DGC_DEBUG", *gc_flags["cflags"]], gc_flags["libs"]),
                ("bdwgc-debug", debug_runtime, ["-DMLF_USE_BDWGC", "-DGC_DEBUG", *gc_flags["cflags"]],
                 gc_flags["libs"])]
    results = []
    for name, runtime_object, compiler_flags, libraries in variants:
        probe = directory / ("runtime-allocation-" + name)
        command(["clang", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "runtime"), *compiler_flags, source, runtime_object,
                 *flags, *libraries, "-lm", "-o", probe])
        results.append({"variant": name, "binary_sha256": digest(probe),
                        "runtime_object_sha256": digest(runtime_object),
                        "cases": allocation_cases(probe, name != "ordinary")})
    return {"source_sha256": digest(source), "variants": results}


def abi_regressions(compilers: list[Path], directory: Path, ordinary: Path, compact: Path,
                    flags: list[str], gc_flags: dict) -> dict:
    """Exercise both real layouts and reject either mismatched runtime at link."""
    source = directory / "layout.emlf"
    source.write_text('''data Record = Record Int Double Bool
showRecord (Record count value enabled) = do
  printInt (if enabled then count else 0)
  putStrLn (formatDouble 2 value)
main = do
  count <- ioReturn (readInt "42")
  values <- newDoubleArray 2 1.25
  writeDoubleArray values 1 3.5
  value <- readDoubleArray values 1
  showRecord (Record count value true)
  size <- lengthDoubleArray values
  printInt size
''')
    rows = []
    previous_ir = {}
    for index, compiler in enumerate(compilers):
        for gc in (False, True):
            name = f"abi-{index}-{'compact' if gc else 'standard'}"
            ir = directory / (name + ".ll")
            with ir.open("wb") as output:
                command([compiler, "--emit-llvm-gc" if gc else "--emit-llvm", source], stdout=output)
            # External declarations may be grouped differently by the two
            # emitters. Preserve every declaration/signature and the exact
            # order/content of all definitions, instructions and metadata.
            lines = ir.read_bytes().splitlines()
            canonical = (sorted(line for line in lines if line.startswith(b"declare ")),
                         [line for line in lines if not line.startswith(b"declare ")])
            if gc in previous_ir and canonical != previous_ir[gc]:
                raise RuntimeError("Seed/native LLVM differ in the ABI fixture")
            previous_ir[gc] = canonical
            binary = directory / name
            link(ir, binary, compact if gc else ordinary, flags + (gc_flags["libs"] if gc else []))
            checked = command([binary], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if checked.stdout != b"42\n3.50\n2\n" or checked.stderr:
                raise RuntimeError(f"{name}: incompatible generated field offsets")
            mismatch = subprocess.run(["clang", "-O2", "-Wno-override-module", str(ir),
                str(ordinary if gc else compact), "-lm", *flags,
                *(gc_flags["libs"] if not gc else []), "-o", str(binary) + "-mismatched"],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            guard = b"mlf_require_compact_gc_abi" if gc else b"mlf_require_standard_abi"
            if not mismatch.returncode or guard not in mismatch.stderr:
                raise RuntimeError(f"{name}: mismatched runtime did not fail on its ABI guard")
            force = force_regression(ir, directory / (name + "-force"), compact if gc else ordinary,
                                     flags, gc_flags, gc)
            rows.append({"compiler": str(compiler), "compact": gc, "llvm_sha256": digest(ir),
                         "binary_sha256": digest(binary), "stdout": checked.stdout.decode(),
                         "mismatched_link_rejected": True, "force_regression": force})
    return {"source_sha256": digest(source), "comparison": "Exact LLVM except external declaration order", "cases": rows}


def force_regression(ir: Path, output: Path, runtime: Path, flags: list[str], gc_flags: dict,
                     compact: bool) -> dict:
    """Call emitted forcing with independently constructed ready/lazy/cyclic values."""
    source = ROOT / "test" / "runtime_force.c"
    text = ir.read_text()
    if text.count("define i32 @main(") != 1:
        raise RuntimeError("Force probe needs exactly one generated entry point")
    symbol = "mlf.force" if compact else "mlf_force"
    if compact and text.count("define private ptr @mlf.force(") != 1:
        raise RuntimeError("Compact compiler did not emit its force helper")
    probe_ir = output.with_suffix(".ll")
    probe_ir.write_text(text.replace("define i32 @main(", "define i32 @mlf_test_program_main(") +
        f"\ndefine ptr @mlf_force_generated(ptr %value) {{\n"
        f"  %result = call ptr @{symbol}(ptr %value)\n  ret ptr %result\n}}\n")
    command(["clang", "-O2", "-Wno-override-module", "-I" + str(ROOT / "runtime"),
             *(["-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", *gc_flags["cflags"]] if compact else []),
             source, probe_ir, runtime, *flags, *(gc_flags["libs"] if compact else []),
             "-lm", "-o", output])
    environment = {name: value for name, value in os.environ.items() if not name.startswith("GC_")}
    environment["GC_INITIAL_HEAP_SIZE"] = str(8 * 1024 * 1024)
    failures = {"null": "missing runtime value", "hole": "cyclic evaluation of a recursive binding",
                "indirection-cycle": "cyclic evaluation of a recursive binding",
                "thunk-cycle": "cyclic evaluation of a recursive binding"}
    rows = []
    for mode in ["success", *failures]:
        checked = subprocess.run([str(output), mode], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=environment, timeout=60)
        if mode == "success":
            expected = {"ready_values": 14, "spine_length": 20000, "thunk_calls": 1, "application_calls": 1}
            if checked.returncode or checked.stderr or json.loads(checked.stdout) != expected:
                raise RuntimeError(f"Generated forcing regression: {checked}")
            rows.append({"mode": mode, **expected})
        else:
            diagnostic = ("Runtime: " + failures[mode] + "\n").encode()
            if checked.returncode != 1 or checked.stdout or checked.stderr != diagnostic:
                raise RuntimeError(f"Generated forcing {mode} rejection changed: {checked}")
            rows.append({"mode": mode, "exit_code": 1, "error": failures[mode]})
    return {"source_sha256": digest(source), "llvm_sha256": digest(probe_ir),
            "binary_sha256": digest(output), "cases": rows}


def validate_manifest(rows: list[dict]):
    categories_present = Counter(row["category"] for row in rows)
    required = {"figure12": 43, "hm-exhaustive": 1712, "hm-generated": 5000,
                "annotations": 126, "readability": 18, "state": 97, "modules": 60,
                "examples": 18, "benchmarks": 9}
    for category, minimum in required.items():
        if categories_present[category] < minimum:
            raise RuntimeError(f"Parity corpus lacks {category}: expected at least {minimum} cases")
    if len({row["id"] for row in rows}) != len(rows):
        raise RuntimeError("Parity corpus contains duplicate case identities")
    if any(row.get("schema_version") != 1 for row in rows):
        raise RuntimeError("Unsupported parity corpus schema")
    a8 = next((row for row in rows if row["id"] == "figure12-A8"), None)
    if not a8 or a8["expected_accept"] or a8.get("expected_phase") != "Inference":
        raise RuntimeError("Parity corpus lost the Figure 12 A8 inference rejection")
    modules = [row for row in rows if row["category"] == "modules"]
    if (sum(row["expected_accept"] for row in modules) < 21 or
            sum(not row["expected_accept"] for row in modules) < 39 or
            not any(row.get("no_prelude") and row["expected_accept"] for row in modules)):
        raise RuntimeError("Module corpus lost positive, negative or explicit-prelude coverage")
    if any(not row["expected_accept"] and (not row.get("expected_phase") or
            not isinstance(row.get("expected_error_contains"), str) or
            not row["expected_error_contains"].strip()) for row in modules):
        raise RuntimeError("Module rejection lacks a prescribed phase or diagnostic expectation")


def check_rejection(row: dict, result):
    if result.returncode != 1 or result.stdout:
        raise RuntimeError(f"{row['id']}: rejected input must exit 1 without emitting a target")
    phase = row.get("expected_phase")
    if phase and not result.stderr.decode("utf8", "replace").startswith(phase + ":"):
        raise RuntimeError(f"{row['id']}: wrong rejection phase: "
                           + result.stderr.decode("utf8", "replace"))
    reason = row.get("expected_error_contains", "")
    if reason not in result.stderr.decode("utf8", "replace"):
        raise RuntimeError(f"{row['id']}: wrong rejection diagnostic, expected {reason!r}: "
                           + result.stderr.decode("utf8", "replace"))


def parity(compiler: Path, manifest: Path, checker: Path, directory: Path,
           runtime: Path, flags: list[str]) -> dict:
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    validate_manifest(rows)
    directory.mkdir(parents=True, exist_ok=True)
    counts = {"accepted": 0, "rejected": 0, "runtime_rows": 0, "runtime_executions": 0}
    categories = {}
    corpus = manifest.parent
    for number, row in enumerate(rows):
        source = corpus / row["source_path"]
        stem = directory / str(number)
        prefix = [str(compiler)]
        for path in row.get("include_dirs", []):
            prefix += ["-i", str(corpus / path)]
        if row.get("no_prelude", False):
            prefix.insert(1, "--no-prelude")
        result = subprocess.run(prefix + [str(source)], cwd=ROOT,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        target = stem.with_suffix(".xmlf")
        target.write_bytes(result.stdout)
        stem.with_suffix(".stderr").write_bytes(result.stderr)
        expected_accept = row["expected_accept"]
        if (result.returncode == 0) != expected_accept:
            raise RuntimeError(f"{row['id']}: acceptance mismatch ({result.returncode}): "
                               + result.stderr.decode("utf8", "replace"))
        category = row["category"]
        categories[category] = categories.get(category, 0) + 1
        if expected_accept:
            counts["accepted"] += 1
            expected = stem.with_suffix(".type")
            expected.write_text(row["expected_type"], encoding="utf-8")
            checked = subprocess.run([str(checker), str(target), str(expected)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if checked.returncode:
                raise RuntimeError(f"{row['id']}: independent target check failed: "
                                   + checked.stderr.decode("utf8", "replace"))
            candidate_check = subprocess.run([str(compiler), "--check", str(target)],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if candidate_check.returncode:
                raise RuntimeError(f"{row['id']}: candidate cannot check its own output: "
                                   + candidate_check.stderr.decode("utf8", "replace"))
        else:
            counts["rejected"] += 1
            check_rejection(row, result)
        if "expected_stdout" in row:
            if not expected_accept:
                raise RuntimeError("Rejected corpus row contains a runtime expectation")
            input_bytes = row.get("expected_stdin", "").encode("utf8")
            expected_bytes = row["expected_stdout"].encode("utf8")
            interpreted = subprocess.run(prefix + ["--run", str(source)], input=input_bytes,
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            expected_errors = row.get("expected_stderr", "").encode("utf8")
            if interpreted.returncode or interpreted.stdout != expected_bytes or interpreted.stderr != expected_errors:
                raise RuntimeError(f"{row['id']}: MLF interpreter output/status mismatch: "
                                   + repr((interpreted.returncode, interpreted.stdout, interpreted.stderr)))
            ir = stem.with_suffix(".ll")
            with ir.open("wb") as output:
                generated = subprocess.run(prefix + ["--emit-llvm", str(source)],
                                           stdout=output, stderr=subprocess.PIPE)
            if generated.returncode:
                raise RuntimeError(f"{row['id']}: LLVM emission failed: "
                                   + generated.stderr.decode("utf8", "replace"))
            binary = stem.with_suffix(".native")
            link(ir, binary, runtime, flags)
            native = subprocess.run([str(binary)], input=input_bytes,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if native.returncode or native.stdout != expected_bytes or native.stderr != expected_errors:
                raise RuntimeError(f"{row['id']}: generated native output/status mismatch: "
                                   + repr((native.returncode, native.stdout, native.stderr)))
            counts["runtime_rows"] += 1
            counts["runtime_executions"] += 2
        if (number + 1) % 100 == 0:
            print(f"Parity: {number + 1}/{len(rows)}", flush=True)
    if not counts["accepted"] or not counts["rejected"] or not counts["runtime_rows"]:
        raise RuntimeError("Parity corpus lacks positive, negative, or two-backend runtime cases")
    return {**counts, "cases": len(rows), "categories": categories, "manifest_sha256": digest(manifest),
            "compiler": str(compiler.resolve()), "compiler_sha256": digest(compiler)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, help="Use an already built Haskell seed")
    parser.add_argument("--output", type=Path, default=ROOT / "dist-newstyle" / "bootstrap")
    parser.add_argument("--manifest", type=Path, help="Use a freshly exported parity manifest")
    parser.add_argument("--reuse-stage1", action="store_true",
                        help="Reuse verified seed-produced LLVM with identical seed and source hashes; always rebuild stages 2 and 3")
    args = parser.parse_args()
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 2, "complete": False, "stages": [], "started": time.time()}
    report_path = directory / "verification.json"
    try:
        previous_report = json.loads(report_path.read_text()) if args.reuse_stage1 else None
        if args.seed:
            seed = args.seed.resolve()
        else:
            command(["cabal", "build", "exe:emlf", "-j1"])
            seed = Path(subprocess.check_output(["cabal", "list-bin", "exe:emlf"], cwd=ROOT, text=True).strip())
        report["llvm_abi"] = "compact-bdwgc-v1"
        report["seed_sha256"] = digest(seed)
        report["sources"] = {str(p.relative_to(ROOT)): digest(p)
                             for p in sorted((ROOT / "bootstrap").rglob("*.emlf"))}
        cached_stage1 = None
        if previous_report is not None:
            if (previous_report.get("llvm_abi") != "compact-bdwgc-v1" or
                    previous_report.get("seed_sha256") != report["seed_sha256"] or
                    previous_report.get("sources") != report["sources"]):
                raise RuntimeError("Cannot reuse stage 1: the seed or MLF sources changed")
            cached_stage1 = next((stage for stage in previous_report.get("stages", [])
                                  if stage.get("stage") == 1), None)
            if not cached_stage1 or digest(directory / "stage1.ll") != cached_stage1["llvm_sha256"]:
                raise RuntimeError("Cannot reuse stage 1: its checked LLVM artifact is missing or changed")
        runtime_source = Path(subprocess.check_output([seed, "--llvm-runtime"], cwd=ROOT, text=True).strip())
        report["runtime_sources"] = {str(p.relative_to(ROOT)): digest(p)
                                      for p in sorted((ROOT / "runtime").glob("*"))
                                      if p.suffix in (".c", ".h")}
        validation_sources = {ROOT / "test" / "runtime_allocation.c",
                              ROOT / "test" / "runtime_force.c",
                              ROOT / "test" / "runtime_st.c",
                              ROOT / "scripts" / "runtime_st_validation.py",
                              ROOT / "bootstrap" / "tests" / "GCSpine.c",
                              ROOT / "bootstrap" / "tests" / "GCDefaults.c",
                              ROOT / "mlf.cabal", Path(__file__).resolve()}
        for pattern in ("src/**/*.hs", "app/*.hs", "test/*.hs", "test/*.py", "bootstrap/**/*.hs", "scripts/bootstrap-gc.py"):
            validation_sources.update(ROOT.glob(pattern))
        report["validation_sources"] = {str(path.relative_to(ROOT)): digest(path)
                                         for path in sorted(validation_sources)}
        cflags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "gmp"], text=True))
        flags = shlex.split(subprocess.check_output(["pkg-config", "--libs", "gmp"], text=True))
        runtime = directory / "runtime.o"
        command(["clang", "-O2", "-std=c11", *cflags, "-c", runtime_source, "-o", runtime])
        gc_flags = json.loads(subprocess.check_output(
            [sys.executable, ROOT / "scripts" / "bootstrap-gc.py", "--flags"], cwd=ROOT, text=True))
        bootstrap_runtime = directory / "bootstrap-runtime.o"
        command(["clang", "-O2", "-std=c11", "-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", "-DMLF_GC_THRESHOLD=1048576", *cflags,
                 *gc_flags["cflags"], "-c", runtime_source, "-o", bootstrap_runtime])
        allocation_environment = os.environ.copy()
        allocation_environment.setdefault("GC_INITIAL_HEAP_SIZE", "536870912")
        allocation_environment.setdefault("GC_FREE_SPACE_DIVISOR", "1")
        report["bootstrap_allocator"] = {"profile": "BDWGC compact", "flags": gc_flags,
                                           "io_collection_allocation_threshold": 1048576,
                                           "environment": {name: allocation_environment[name] for name in
                                               ("GC_INITIAL_HEAP_SIZE", "GC_FREE_SPACE_DIVISOR")},
                                           "builder_sha256": digest(ROOT / "scripts" / "bootstrap-gc.py")}
        gc_probe_source = ROOT / "bootstrap" / "tests" / "GCSpine.c"
        gc_probe = directory / "gc-spine"
        command(["clang", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "runtime"), "-DMLF_COMPACT_BDWGC", *gc_flags["cflags"], gc_probe_source,
                 bootstrap_runtime, *flags, *gc_flags["libs"], "-lm", "-o", gc_probe])
        gc_checked = command([gc_probe], stdout=subprocess.PIPE, env=allocation_environment)
        report["bootstrap_allocator"]["spine_regression"] = {
            **json.loads(gc_checked.stdout), "source_sha256": digest(gc_probe_source)}
        defaults_source = ROOT / "bootstrap" / "tests" / "GCDefaults.c"
        defaults_probe = directory / "gc-defaults"
        command(["clang", "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-I" + str(ROOT / "runtime"), *gc_flags["cflags"], defaults_source,
                 bootstrap_runtime, *flags, *gc_flags["libs"], "-lm", "-o", defaults_probe])
        report["bootstrap_allocator"]["defaults_regression"] = {
            "source_sha256": digest(defaults_source), "cases": gc_defaults(defaults_probe)}
        report["bootstrap_allocator"]["allocation_regression"] = allocation_regressions(
            directory, runtime_source, runtime, bootstrap_runtime, cflags, flags, gc_flags)
        report["bootstrap_allocator"]["state_regression"] = validate_st_runtime(
            compiler="clang", fixture=ROOT / "test" / "runtime_st.c",
            runtime=bootstrap_runtime, include_dirs=[ROOT / "runtime"],
            cflags=["-DMLF_USE_BDWGC", "-DMLF_COMPACT_BDWGC", *cflags, *gc_flags["cflags"]],
            libraries=[*flags, *gc_flags["libs"]], output=directory / "runtime-st",
            environment=allocation_environment)
        # The interpreter itself can be the compiled program. Its host stack
        # needs room for the same deep lazy programs exercised by the seed.
        compiler_link_flags = ["-Wl,-stack_size,0x4000000"] if platform.system() == "Darwin" else []
        report["compiler_link_flags"] = compiler_link_flags
        source = ROOT / "bootstrap" / "Main.emlf"
        previous = seed
        for stage in (1, 2, 3):
            ir = directory / f"stage{stage}.ll"
            binary = directory / f"emlf-stage{stage}"
            reused = stage == 1 and cached_stage1 is not None
            duration = cached_stage1["compilation_seconds"] if reused else emit(
                previous, source, ir, directory / f"stage{stage}.stderr",
                allocation_environment if stage > 1 else None)
            for path, expected in report["sources"].items():
                if digest(ROOT / path) != expected:
                    raise RuntimeError("Sources changed during compilation: " + path)
            link(ir, binary, bootstrap_runtime, flags + gc_flags["libs"] + compiler_link_flags)
            report["stages"].append({"stage": stage, "compiler": str(previous),
                                      "llvm_sha256": digest(ir), "binary_sha256": digest(binary),
                                      "reused_seed_compilation": reused,
                                      "compilation_seconds": duration})
            previous = binary
            report_path.write_text(json.dumps(report, indent=2) + "\n")
        if (directory / "stage2.ll").read_bytes() != (directory / "stage3.ll").read_bytes():
            raise RuntimeError("Bootstrap did not reach a fixed point: stage2.ll differs from stage3.ll")
        report["fixed_point"] = True
        candidate = directory / "emlf-stage3"
        report["candidate"] = {"stage": 3, "path": str(candidate), "sha256": digest(candidate)}
        report["abi_regression"] = abi_regressions(
            [seed, candidate], directory, runtime, bootstrap_runtime, flags, gc_flags)
        checker = directory / "check-target"
        ghc_output = directory / "ghc"
        ghc_output.mkdir(exist_ok=True)
        command(["ghc", "-O2", "-isrc", "-itest", "-outputdir", ghc_output,
                 ROOT / "bootstrap" / "CheckTarget.hs", "-o", checker])
        manifest = args.manifest.resolve() if args.manifest else directory / "corpus" / "manifest.jsonl"
        if not args.manifest:
            exporter = directory / "export-corpus"
            export_output = directory / "ghc-export"
            export_output.mkdir(exist_ok=True)
            command(["ghc", "-O2", "-isrc", "-itest", "-outputdir", export_output,
                     ROOT / "bootstrap" / "ExportCorpus.hs", "-o", exporter])
            command([exporter, manifest.parent])
        report["parity"] = parity(candidate, manifest, checker,
                                   directory / "parity", runtime, flags)
        for path, expected in report["sources"].items():
            if digest(ROOT / path) != expected:
                raise RuntimeError("Sources changed during verification: " + path)
        for path, expected in report["runtime_sources"].items():
            if digest(ROOT / path) != expected:
                raise RuntimeError("Runtime changed during verification: " + path)
        for path, expected in report["validation_sources"].items():
            if digest(ROOT / path) != expected:
                raise RuntimeError("Validation source changed during verification: " + path)
        if digest(seed) != report["seed_sha256"]:
            raise RuntimeError("Haskell seed changed during verification")
        if digest(candidate) != report["candidate"]["sha256"]:
            raise RuntimeError("Stage 3 candidate changed during verification")
        report["complete"] = True
        print("Bootstrap fixed point and full exported parity corpus passed.")
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError) as error:
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        report["finished"] = time.time()
        report_path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
