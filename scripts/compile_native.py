#!/usr/bin/env python3
"""Compile eMLF to an executable, overlapping independent compiler phases."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile
import time

from compiler_process import ROOT, run, run_group


def build(*, compiler, clang, source, runtime, directory, flags=("-O2",),
          gmp=(), frontend_options=(), env=None, timeout=600):
    """Build in an empty directory, with no object or IR reuse.

    The frontend and C runtime compiler run concurrently. The LLVM compile
    and link start only after both succeed. All work is inside wall_seconds;
    CPU is summed and RSS remains the largest per-child high-water mark.
    """
    directory = Path(directory).resolve()
    if not directory.is_dir() or any(directory.iterdir()):
        raise ValueError("Native build requires an empty working directory")
    ir, obj, binary = (directory / name for name in ("program.ll", "runtime.o", "program"))
    include_flags = [flag for flag in gmp if not flag.startswith(("-l", "-L", "-Wl,"))]
    commands = [([str(compiler), *frontend_options, "--emit-llvm", str(source)], b"", ir),
                ([str(clang), *flags, *include_flags, "-c", str(runtime), "-o", str(obj)], b"", None)]
    started = time.perf_counter()
    stages = [sample for sample, _ in run_group(commands, cwd=directory, env=env, timeout=timeout)]
    stages[0]["phase"], stages[1]["phase"] = "frontend", "runtime"
    for sample in stages:
        sample["parallel_group"] = 0
    linked, _ = run([str(clang), *flags, str(ir), str(obj), *gmp, "-lm", "-o", str(binary)],
                    cwd=directory, env=env, timeout=timeout)
    linked["phase"] = "llvm-and-link"
    stages.append(linked)
    wall = time.perf_counter() - started
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RuntimeError("Native compilation did not produce an executable")
    return binary, {"wall_seconds": wall, "cpu_seconds": sum(s["cpu_seconds"] for s in stages),
                    "peak_rss_bytes": max(s["peak_rss_bytes"] for s in stages), "stages": stages,
                    "scheduling": "Frontend and fresh runtime compilation overlap; LLVM/link follows both",
                    "maximum_parallel_compilers": 2,
                    "executable_bytes": binary.stat().st_size,
                    "executable_sha256": hashlib.sha256(binary.read_bytes()).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    bundled = Path(__file__).resolve().with_name("emlf")
    parser.add_argument("--compiler", default=str(bundled) if bundled.is_file() else "emlf",
                        help="Installed native compiler, or emlf on PATH when run from the source tree")
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--pkg-config", default="pkg-config")
    parser.add_argument("--runtime", type=Path, help="Otherwise use the compiler's --llvm-runtime path")
    parser.add_argument("-i", "--include", type=Path, action="append", default=[])
    parser.add_argument("--no-prelude", action="store_true")
    parser.add_argument("--report", type=Path, help="Write phase measurements and exact commands as JSON")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args(argv)
    if not args.timeout > 0 or not args.timeout < float("inf"):
        parser.error("--timeout must be finite and positive")
    try:
        compiler = shutil.which(args.compiler)
        clang = shutil.which(args.clang)
        if compiler is None or clang is None:
            raise ValueError("The selected compiler and Clang must be executable")
        compiler, clang = str(Path(compiler).resolve()), str(Path(clang).resolve())
        runtime = args.runtime
        if runtime is None:
            _, output = run([compiler, "--llvm-runtime"], timeout=args.timeout)
            runtime = Path(os.fsdecode(output).strip())
        _, flags = run([args.pkg_config, "--cflags", "--libs", "gmp"], timeout=args.timeout)
        frontend_options = ["--no-prelude"] if args.no_prelude else []
        for path in args.include:
            frontend_options.extend(["-i", str(path.resolve())])
        destination = args.output.resolve()
        # Same-directory rename preserves an existing executable if any
        # compilation phase fails, and publishes only a complete replacement.
        with tempfile.TemporaryDirectory(prefix=".mlf-build-", dir=destination.parent) as work:
            binary, report = build(compiler=compiler, clang=clang,
                source=args.source.resolve(strict=True), runtime=runtime.resolve(strict=True),
                directory=work, gmp=shlex.split(flags.decode()), frontend_options=frontend_options,
                timeout=args.timeout)
            os.replace(binary, destination)
            report["output"] = str(destination)
        if args.report:
            args.report.write_text(json.dumps(report, indent=2) + "\n")
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
