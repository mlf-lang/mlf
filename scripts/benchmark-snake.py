#!/usr/bin/env python3
"""Compare Snake compilation to xMLF, LLVM IR, and native code with GHC.

Run with `cabal bench -j1`; pass overrides via --benchmark-options.
Requires Python 3, Clang and pkg-config/GMP.
Query tool metadata before timing, then rotate workflow order using fresh
processes. Native eMLF builds include fresh LLVM emission, Clang -O2 runtime
compilation, and linking. GHC uses -O2 -fforce-recomp on every sample. There
is no cached game/runtime build or source-compilation warmup. --max-ratio
(default 1) retains the xMLF/GHC gate; LLVM ratios are reported separately.
This does not measure OS first-launch checks on a newly linked compiler.
"""

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
import statistics
import subprocess
import tempfile
import time


def digest(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def run(command, data=None):
    started = time.perf_counter()
    result = subprocess.run(command, input=data, capture_output=True, timeout=300)
    elapsed = time.perf_counter() - started
    if result.returncode:
        raise RuntimeError(f"{command} failed:\n{result.stderr.decode(errors='replace')}")
    return elapsed, result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emlf", required=True, type=Path)
    parser.add_argument("--ghc", default="ghc")
    parser.add_argument("--clang", default="clang")
    parser.add_argument("--pkg-config", default="pkg-config")
    parser.add_argument("--source", type=Path, default=Path("examples/snake.emlf"))
    parser.add_argument("--baseline", type=Path, default=Path("examples/SnakeBaseline.hs"))
    parser.add_argument("--reference-xmlf", type=Path)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-ratio", type=float, default=1,
                        help="maximum xMLF/GHC ratio in every round (LLVM ratios are informational)")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.runs < 1 or not math.isfinite(args.max_ratio) or args.max_ratio <= 0:
        parser.error("--runs and --max-ratio must be positive")
    emlf = args.emlf.resolve(strict=True)
    toolchain = {}
    for name in ("ghc", "clang", "pkg_config"):
        toolchain[name] = shutil.which(getattr(args, name))
        if toolchain[name] is None:
            parser.error(f"Tool not found: {getattr(args, name)}")
    ghc, clang, pkg_config = (toolchain[name] for name in ("ghc", "clang", "pkg_config"))
    source = args.source.resolve(strict=True)
    baseline = args.baseline.resolve(strict=True)
    # Treat executable startup symmetrically: this benchmark already queried
    # GHC's version. Also record the emlf build/runtime metadata before timing.
    # These probes do not parse or compile either game.
    ghc_probe_seconds, ghc_version = run([ghc, "--numeric-version"])
    emlf_probe_seconds, emlf_info = run([str(emlf), "+RTS", "--info", "-RTS"])
    clang_probe_seconds, clang_version = run([clang, "--version"])
    gmp_probe_seconds, gmp_version = run([pkg_config, "--modversion", "gmp"])
    gmp_flags_seconds, gmp_flags = run([pkg_config, "--cflags", "--libs", "gmp"])
    runtime_probe_seconds, runtime_path = run([str(emlf), "--llvm-runtime"])
    runtime = Path(os.fsdecode(runtime_path).strip()).resolve(strict=True)
    runtime_header = runtime.with_name("mlf_runtime.h").resolve(strict=True)
    fingerprints = {str(p): digest(p) for p in
                    (emlf, source, baseline, runtime, runtime_header, *runtime.parent.glob("*.h"), Path(__file__).resolve(),
                     *(Path(tool) for tool in toolchain.values()))}
    report = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "ghc_version": ghc_version.decode().strip(),
        "clang_version": clang_version.decode().strip(),
        "gmp_version": gmp_version.decode().strip(),
        "emlf_runtime_info": emlf_info.decode().strip(),
        "metadata_probe_seconds": {
            "ghc": ghc_probe_seconds, "emlf": emlf_probe_seconds,
            "clang": clang_probe_seconds, "gmp_version": gmp_probe_seconds,
            "gmp_flags": gmp_flags_seconds, "runtime_path": runtime_probe_seconds,
        },
        "ghcrts_environment": os.environ.get("GHCRTS"),
        "scope": "eMLF source to verified xMLF, LLVM IR, or a linked native executable; "
                 "GHC source to a linked native executable. Native eMLF timing includes "
                 "fresh --emit-llvm, writing IR, Clang -O2 runtime compilation and linking. "
                 "Includes process startup; excludes building emlf and running the games. "
                 "Tool metadata probes precede timing. Serial fresh processes, rotating "
                 "workflow order, no source-compilation warmup or cached game/runtime builds. "
                 "GHC recompiles and links on every sample.",
        "sha256": fingerprints,
        "max_ratio": args.max_ratio,
        "gate_workflow": "emlf (source to xMLF)",
        "pairs": [],
    }
    expected = args.reference_xmlf.read_bytes() if args.reference_xmlf else None
    expected_ir = None
    workflows = ("emlf", "llvm_ir", "llvm_native", "ghc")
    samples = {name: [] for name in workflows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="snake-bench-", dir=args.output.parent) as scratch:
        scratch = Path(scratch).resolve()
        haskell_native = scratch / "snake-haskell"
        llvm_native = scratch / "snake-llvm"
        llvm_source = scratch / "snake.ll"
        commands = {
            "emlf": [str(emlf), str(source)],
            "llvm_ir": [str(emlf), "--emit-llvm", str(source)],
            "ghc": [ghc, "-O2", "-Wall", "-Werror", "-fforce-recomp", "-main-is", "SnakeBaseline",
                    str(baseline), "-outputdir", str(scratch), "-o", str(haskell_native)],
        }
        commands["llvm_native"] = [commands["llvm_ir"],
            [clang, "-O2", "-Wno-override-module", str(llvm_source), str(runtime),
             *shlex.split(gmp_flags.decode()), "-lm", "-o", str(llvm_native)]]
        report["commands"] = commands
        for repetition in range(args.runs):
            offset = repetition % len(workflows)
            order = workflows[offset:] + workflows[:offset]
            pair = {"order": order}
            for name in order:
                if name == "llvm_native":
                    started = time.perf_counter()
                    emit_seconds, output = run(commands[name][0])
                    llvm_source.write_bytes(output)
                    link_seconds, _ = run(commands[name][1])
                    elapsed = time.perf_counter() - started
                    pair["llvm_native_stages_seconds"] = {
                        "emit": emit_seconds, "compile_and_link": link_seconds,
                        "write_ir_and_driver": elapsed - emit_seconds - link_seconds,
                    }
                else:
                    elapsed, output = run(commands[name])
                samples[name].append(elapsed)
                pair[name + "_seconds"] = elapsed
                if name == "emlf":
                    if expected is None:
                        expected = output
                    elif output != expected:
                        raise RuntimeError("xMLF differs between samples or from --reference-xmlf")
                elif name in ("llvm_ir", "llvm_native"):
                    if expected_ir is None:
                        expected_ir = output
                    elif output != expected_ir:
                        raise RuntimeError("LLVM IR differs between samples or workflows")
            pair["ratio"] = pair["emlf_seconds"] / pair["ghc_seconds"]
            pair["ratios_vs_ghc"] = {
                name: pair[name + "_seconds"] / pair["ghc_seconds"] for name in workflows[:-1]
            }
            report["pairs"].append(pair)
            print(f"Run {repetition + 1}: xMLF {pair['emlf_seconds']:.4f}s; "
                  f"LLVM IR {pair['llvm_ir_seconds']:.4f}s; "
                  f"LLVM native {pair['llvm_native_seconds']:.4f}s; "
                  f"GHC native {pair['ghc_seconds']:.4f}s", flush=True)
        report["checked_type"] = run([str(emlf), "--check"], expected)[1].decode().strip()
        if report["checked_type"] != "IO Unit":
            raise RuntimeError(f"Unexpected Snake type: {report['checked_type']}")
        xmlf = args.output.with_suffix(".xmlf")
        xmlf.write_bytes(expected)
        args.output.with_suffix(".ll").write_bytes(expected_ir)
        if run([str(emlf), "--xmlf-to-llvm", str(xmlf)])[1] != expected_ir:
            raise RuntimeError("Standalone xMLF lowering differs from source-to-LLVM emission")
        report["llvm_ir_matches_standalone_xmlf"] = True
        # Outside the compilation timings: check a complete game transcript
        # against the executable produced by the final GHC sample.
        inputs = b"d\n\nw\na\nq\n"
        haskell_output = run([str(haskell_native)], inputs)[1]
        emlf_output = run([str(emlf), "--run-xmlf", str(xmlf)], inputs)[1]
        llvm_output = run([str(llvm_native)], inputs)[1]
        if haskell_output != emlf_output:
            raise RuntimeError("Snake transcript differs from the Haskell baseline")
        if haskell_output != llvm_output:
            raise RuntimeError("LLVM Snake transcript differs from the Haskell baseline")
        report["transcript_matches_haskell"] = True
        report["llvm_transcript_matches_haskell"] = True
    for filename, fingerprint in fingerprints.items():
        if digest(Path(filename)) != fingerprint:
            raise RuntimeError(f"Input or compiler changed during measurement: {filename}")
    medians = {name: statistics.median(times) for name, times in samples.items()}
    report.update({
        "samples_seconds": samples,
        "median_seconds": medians,
        "median_ratio": medians["emlf"] / medians["ghc"],
        "median_ratios_vs_ghc": {name: medians[name] / medians["ghc"] for name in workflows[:-1]},
        "worst_pair_ratio": max(pair["ratio"] for pair in report["pairs"]),
        "worst_paired_ratios_vs_ghc": {
            name: max(pair["ratios_vs_ghc"][name] for pair in report["pairs"])
            for name in workflows[:-1]
        },
        "xmlf_sha256": hashlib.sha256(expected).hexdigest(),
        "llvm_ir_sha256": hashlib.sha256(expected_ir).hexdigest(),
        "identical_to_reference": args.reference_xmlf is not None,
    })
    report["passed"] = report["worst_pair_ratio"] <= args.max_ratio
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print("\n| Compilation workflow | Median (s) | vs GHC | Worst paired ratio |")
    print("| --- | ---: | ---: | ---: |")
    labels = ("eMLF -> xMLF", "eMLF -> LLVM IR", "eMLF -> LLVM native", "Haskell -> GHC native")
    for name, label in zip(workflows, labels):
        ratio = medians[name] / medians["ghc"]
        worst = report["worst_paired_ratios_vs_ghc"].get(name, 1)
        print(f"| {label} | {medians[name]:.6f} | {ratio:.4f}x | {worst:.4f}x |")
    print(f"\nxMLF/GHC gate (every round <= {args.max_ratio:g}x): "
          f"{'PASS' if report['passed'] else 'FAIL'}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
