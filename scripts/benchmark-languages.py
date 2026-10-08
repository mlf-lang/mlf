#!/usr/bin/env python3
"""Pinned, single-threaded cross-language benchmarks. Primary entry: cabal bench."""

import argparse
from datetime import datetime, timezone
import hashlib
from functools import lru_cache
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
    if workload["name"] == "pidigits":
        digits = pi_digits(size)
        return "\n".join(f"{digits[i:i+10]:<10}\t:{min(i+10,size)}" for i in range(0,size,10)).encode()
    if workload["name"] == "n-body":
        return "\n".join(f"{e:.9f}" for e in nbody_energy(size)).encode()
    if workload["name"] == "spectral-norm":
        return f"{spectral_norm(size):.9f}".encode()
    if workload["name"] == "fasta":
        return fasta_output(size)
    if workload["name"] == "mandelbrot":
        return mandelbrot_output(size)
    if workload["name"] == "fannkuch-redux":
        checksum, maximum = fannkuch_result(size)
        return f"{checksum}\nPfannkuchen({size}) = {maximum}".encode()
    if workload["name"] != "binary-trees":
        raise ValueError("No correctness oracle for " + workload["name"])
    maximum = max(6, size)
    lines = [f"stretch tree of depth {maximum + 1} check: {2 ** (maximum + 2) - 1}"]
    for depth in range(4, maximum + 1, 2):
        iterations = 2 ** (maximum - depth + 4)
        lines.append(f"{iterations} trees of depth {depth} check: {iterations * (2 ** (depth + 1) - 1)}")
    lines.append(f"long lived tree of depth {maximum} check: {2 ** (maximum + 1) - 1}")
    return "\n".join(lines).encode()


@lru_cache(maxsize=32)
def pi_digits(size):
    # Independent Machin formula oracle, not the measured spigot algorithm.
    # Thirty guard digits dominate fixed-point truncation for supported sizes.
    if hasattr(sys, "set_int_max_str_digits"):
        sys.set_int_max_str_digits(0)
    scale = 10 ** (size + 30)
    def atan_inverse(q):
        power, total, odd, sign = scale // q, 0, 1, 1
        while power:
            total += sign * (power // odd)
            power //= q*q
            odd += 2
            sign = -sign
        return total
    return str(16*atan_inverse(5) - 4*atan_inverse(239))[:size]


@lru_cache(maxsize=32)
def nbody_energy(steps):
    # Independent Python scalar reference. Only the driver uses this; none of
    # the measured programs can read its state or answers. It runs once per
    # input outside every measured interval, including for the runtime input.
    solar, year = 4*math.pi*math.pi, 365.24
    bodies = [
        [0.,0.,0.,0.,0.,0.,solar],
        [4.84143144246472090,-1.16032004402742839,-.103622044471123109,
         .00166007664274403694*year,.00769901118419740425*year,-.0000690460016972063023*year,.000954791938424326609*solar],
        [8.34336671824457987,4.12479856412430479,-.403523417114321381,
         -.00276742510726862411*year,.00499852801234917238*year,.0000230417297573763929*year,.000285885980666130812*solar],
        [12.8943695621391310,-15.1111514016986312,-.223307578892655734,
         .00296460137564761618*year,.00237847173959480950*year,-.0000296589568540237556*year,.0000436624404335156298*solar],
        [15.3796971148509165,-25.9193146099879641,.179258772950371181,
         .00268067772490389322*year,.00162824170038242295*year,-.0000951592254519715870*year,.0000515138902046611451*solar]]
    pairs = [(a,b) for i,a in enumerate(bodies) for b in bodies[i+1:]]
    for k in (3,4,5):
        bodies[0][k] = -sum(b[k]*b[6] for b in bodies)/solar
    def energy():
        kinetic = sum(.5*b[6]*sum(v*v for v in b[3:6]) for b in bodies)
        potential = sum(a[6]*b[6]/math.sqrt(sum((a[k]-b[k])**2 for k in (0,1,2))) for a,b in pairs)
        return kinetic-potential
    before = energy()
    for _ in range(steps):
        for a,b in pairs:
            dx,dy,dz = a[0]-b[0],a[1]-b[1],a[2]-b[2]
            distance = math.sqrt(dx*dx+dy*dy+dz*dz)
            mag = .01/(distance*distance*distance)
            for k,delta in ((3,dx),(4,dy),(5,dz)):
                a[k] -= delta*b[6]*mag
                b[k] += delta*a[6]*mag
        for b in bodies:
            for k in (0,1,2):
                b[k] += .01*b[k+3]
    return before,energy()


@lru_cache(maxsize=16)
def fannkuch_result(size):
    # Factoradic unranking reconstructs each permutation independently. This
    # deliberately differs from the incremental count-array generators in the
    # measured programs and checks both parity checksum and maximum flips.
    factorials = [math.factorial(i) for i in range(size+1)]
    checksum, maximum = 0,0
    for rank in range(factorials[size]):
        permutation, remaining = list(range(1,size+1)),rank
        for i in range(size-1,0,-1):
            rotation, remaining = divmod(remaining,factorials[i])
            permutation[:i+1] = permutation[rotation:i+1] + permutation[:rotation]
        flips = 0
        while permutation[0] != 1:
            end = permutation[0]
            permutation[:end] = permutation[:end][::-1]
            flips += 1
        checksum += flips if rank % 2 == 0 else -flips
        maximum = max(maximum,flips)
    return checksum,maximum


@lru_cache(maxsize=16)
def spectral_norm(size):
    # Materialize an independent dense matrix, then use accurate summation.
    # Measured programs instead compute entries on demand. Reference storage
    # is released before timing, and no executable can access this state.
    matrix = [[1.0 / ((i+j)*(i+j+1)//2+i+1) for j in range(size)] for i in range(size)]
    def multiply(vector, transpose=False):
        if transpose:
            return [math.fsum(matrix[j][i]*vector[j] for j in range(size)) for i in range(size)]
        return [math.fsum(a*x for a,x in zip(row,vector)) for row in matrix]
    u = [1.0]*size
    for _ in range(20):
        v = u
        u = multiply(multiply(v), transpose=True)
    return math.sqrt(math.fsum(a*b for a,b in zip(u,v)) / math.fsum(b*b for b in v))


@lru_cache(maxsize=16)
def fasta_output(size):
    from fractions import Fraction
    alu = (b"GGCCGGGCGCGGTGGCTCACGCCTGTAATCCCAGCACTTTGGGAGGCCGAGGCGGGCGGATCACCTGAGG"
           b"TCAGGAGTTCGAGACCAGCCTGGCCAACATGGTGAAACCCCGTCTCTACTAAAAATACAAAAATTAGCCGGG"
           b"CGTGGTGGCGCGCGCCTGTAATCCCAGCTACTCGGGAGGCTGAGGCAGGAGAATCGCTTGAACCCGGGAGGC"
           b"GGAGGTTGCAGTGAGCCGAGATCGCGCCACTGCACTCCAGCCTGGGCGACAGAGCGAGACTCCGTCTCAAAAA")
    output = bytearray()
    def record(header, sequence):
        output.extend(header+b"\n")
        for i in range(0,len(sequence),60):
            output.extend(sequence[i:i+60]); output.append(10)
    record(b">ONE Homo sapiens alu", (alu*((2*size+len(alu)-1)//len(alu)))[:2*size])
    seed = 42
    for header, letters, probabilities, count in [
        (b">TWO IUB ambiguity codes", b"acgtBDHKMNRSVWY", ["0.27","0.12","0.12","0.27"]+["0.02"]*11,3*size),
        (b">THREE Homo sapiens frequency", b"acgt", ["0.3029549426680","0.1979883004921","0.1975473066391","0.3015094502008"],5*size)]:
        cumulative, bounds = Fraction(0),[]
        for p in probabilities:
            cumulative += Fraction(p)
            bounds.append((cumulative.numerator*139968,cumulative.denominator))
        sequence = bytearray(count)
        for i in range(count):
            seed = (seed*3877+29573)%139968
            sequence[i] = next(c for c,(numerator,denominator) in zip(letters,bounds) if seed*denominator < numerator)
        record(header,sequence)
    return bytes(output)


@lru_cache(maxsize=16)
def mandelbrot_output(size):
    # Independent complex-number recurrence, with explicit PBM bit positions.
    # The measured programs use scalar components and shift accumulators.
    stride = (size+7)//8
    pixels = bytearray(stride*size)
    for y in range(size):
        for x in range(size):
            c, z = complex(2.0*x/size-1.5, 2.0*y/size-1.0), 0j
            for _ in range(50):
                z = z*z+c
                if z.real*z.real+z.imag*z.imag > 4.0:
                    break
            else:
                pixels[y*stride+x//8] |= 0x80 >> (x%8)
    return f"P4\n{size} {size}\n".encode()+pixels


def validate_output(workload, size, output):
    # Integer workloads normalize whitespace ONLY. The official n-body
    # tolerance is absolute 1e-8; non-finite and missing/extra values fail.
    expected = expected_output(workload, size)
    if workload["name"] in ("n-body", "spectral-norm"):
        try:
            actual = [float(token) for token in output.split()]
        except ValueError:
            actual = []
        reference = nbody_energy(size) if workload["name"] == "n-body" else [spectral_norm(size)]
        if len(actual) == len(reference) and all(math.isfinite(a) and abs(a-b) <= 1e-8 for a,b in zip(actual,reference)):
            return
    elif workload["name"] in ("fasta", "mandelbrot"):
        if output == expected:
            return
    elif output.split() == expected.split():
        return
    raise ValueError(f"{workload['name']}({size}) output mismatch:\n"
                     f"expected: {expected[:4096]!r}\nactual: {output[:4096]!r}")


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
        libraries = gmp if language in workload.get("gmp_languages", []) else []
        commands = [([paths["clang"], *flags, source, *libraries, "-lm", "-o", str(binary)], None)]
    elif language == "rust":
        libraries = ["-Lnative=" + f[2:] for f in gmp if f.startswith("-L")] if language in workload.get("gmp_languages", []) else []
        commands = [([paths["rustc"], *flags, *libraries, source, "-o", str(binary)], None)]
    elif language == "haskell":
        commands = [([paths["ghc"], *flags, source, "-outputdir", str(directory), "-o", str(binary)], None)]
    else:
        commands = [([paths["emlf"], "--emit-llvm", source], ir),
                    ([paths["clang"], *flags, str(ir), str(runtime), *gmp, "-lm", "-o", str(binary)], None)]
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


def performance_checks(results, targets):
    """Gate each workload's median ratio, never just a corpus average."""
    checks = []
    for row in results:
        for dimension, limit in targets.items():
            if limit is None:
                continue
            measured = row.get(dimension + "_ratios")
            if measured is None:
                raise ValueError(f"Cannot check an unmeasured {dimension} target")
            ratio = measured["mlf"]
            if not math.isfinite(ratio) or ratio <= 0:
                raise ValueError("Performance checks require finite positive ratios")
            checks.append({"benchmark": row["benchmark"], "dimension": dimension,
                           "mlf_over_c": ratio, "maximum_ratio": limit, "passed": ratio <= limit})
    return checks


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
    for check in report.get("performance_checks", []):
        print(f"Target {'PASS' if check['passed'] else 'FAIL'}: {check['benchmark']} "
              f"{check['dimension']} {check['mlf_over_c']:.3f}x <= {check['maximum_ratio']:g}x C")
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
    parser.add_argument("--size", type=int, help="override one selected workload's input (range in manifest)")
    parser.add_argument("--timeout", type=float, default=600, help="seconds per subprocess")
    parser.add_argument("--max-compile-ratio", type=float, help="fail if any MLF/C compilation median exceeds this ratio")
    parser.add_argument("--max-runtime-ratio", type=float, help="fail if any MLF/C runtime median exceeds this ratio")
    parser.add_argument("--output", type=Path, default=ROOT / "bench-results.json")
    args = parser.parse_args(argv)
    if args.runs < 2 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--runs must be at least 2; --timeout must be finite and positive")
    targets = {"compilation": args.max_compile_ratio, "runtime": args.max_runtime_ratio}
    if any(v is not None and (not math.isfinite(v) or v <= 0) for v in targets.values()):
        parser.error("Performance ratio limits must be finite and positive")
    if (args.compile_only and args.max_runtime_ratio is not None) or (args.runtime_only and args.max_compile_ratio is not None):
        parser.error("Performance limits require measuring the requested dimension")
    report = {"schema_version": 1, "status": "running",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "disclaimer": DISCLAIMER,
              "host": {"os": platform.system(), "release": platform.release(),
                       "platform": platform.platform(), "architecture": platform.machine(),
                       "logical_cpus": os.cpu_count(), "python": platform.python_version()},
              "configuration": {"runs": args.runs, "size_override": args.size,
                                "compile_only": args.compile_only, "runtime_only": args.runtime_only,
                                "timeout_seconds": args.timeout, "maximum_mlf_c_ratios": targets},
              "results": [], "warnings": [], "geometric_means": {}, "corpus_compilation": None}
    try:
        # Invalidate an old success before setup. Even a hard interruption
        # then leaves a non-success report, never stale green history.
        atomic_json(args.output, report)
        if sys.platform not in ("darwin", "linux"):
            raise ValueError("Per-process wait4 measurement currently supports macOS and Linux")
        manifest = load_manifest()
        names = args.benchmark or [w["name"] for w in manifest["workloads"]]
        workloads = [w for w in manifest["workloads"] if w["name"] in names]
        if set(names) != {w["name"] for w in workloads}:
            raise ValueError("Unknown benchmark; available: " + ", ".join(w["name"] for w in manifest["workloads"]))
        if args.size is not None and len(workloads) != 1:
            raise ValueError("--size requires exactly one --benchmark selection")
        sizes = {w["name"]: args.size if args.size is not None else w["default_input"] for w in workloads}
        for w in workloads:
            if not w["minimum_input"] <= sizes[w["name"]] <= w["maximum_input"]:
                raise ValueError(f"{w['name']}: input must be {w['minimum_input']}..{w['maximum_input']}")
            validate_output(w, w["fixture_input"], (ROOT / w["fixture"]).read_bytes())
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
                                sample["post_build_check"] = execute(workload, language, binary, workload["post_build_input"], env, args.timeout)
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
            report["performance_checks"] = performance_checks(report["results"], targets)
            report["status"] = "passed" if all(c["passed"] for c in report["performance_checks"]) else "failed"
            if report["status"] == "failed":
                report["error"] = "One or more per-workload MLF/C performance limits were exceeded"
            report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(args.output, report)
        render(report)
        print(f"\nRaw samples, commands, provenance and metadata: {args.output.resolve()}")
        return 0 if report["status"] == "passed" else 1
    except KeyboardInterrupt:
        report.update(status="failed", error="Benchmark interrupted")
        atomic_json(args.output, report)
        print(f"Benchmark interrupted; failure report: {args.output.resolve()}", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError, TimeoutError, KeyError) as error:
        report.update(status="failed", error=str(error))
        atomic_json(args.output, report)
        print(f"Benchmark failed: {error}\nFailure report: {args.output.resolve()}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
