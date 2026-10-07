"""Correctness and failure-path tests for the benchmark driver (no performance gates)."""
import importlib.util
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("benchmarks", ROOT / "scripts/benchmark-languages.py")
B = importlib.util.module_from_spec(spec)
spec.loader.exec_module(B)


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.workload = B.load_manifest()["workloads"][0]

    def test_oracle_matches_independent_pinned_fixture(self):
        B.validate_output(self.workload, 10, (ROOT / self.workload["fixture"]).read_bytes())
        self.assertEqual(B.expected_output(self.workload, 0), B.expected_output(self.workload, 6))
        self.assertIn(b"32 trees of depth 6 check: 4064", B.expected_output(self.workload, 7))

    def test_only_whitespace_is_normalized(self):
        expected = B.expected_output(self.workload, 10)
        B.validate_output(self.workload, 10, expected.replace(b" ", b"\t  ") + b"\n")
        for corrupt in (expected + b" extra", expected.replace(b"4095", b"4094"),
                        expected.replace(b"32704", b"-32704"), b"", b"\n".join(expected.splitlines()[:-1])):
            with self.subTest(corrupt=corrupt[:80]), self.assertRaises(ValueError):
                B.validate_output(self.workload, 10, corrupt)

    def test_pin_tampering_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "source.c"
            file.write_text("original")
            manifest = B.load_manifest()
            manifest["pinned_sha256"][str(file)] = B.digest(file)
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest))
            B.load_manifest(path)
            file.write_text("changed")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                B.load_manifest(path)

    def test_four_languages_are_mandatory(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = B.load_manifest()
            del manifest["workloads"][0]["sources"]["rust"]
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "all four"):
                B.load_manifest(path)

    def test_changes_during_measurement_invalidate_the_run(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_text("original")
            fingerprints = {str(source): B.digest(source)}
            B.check_integrity(fingerprints)
            source.write_text("modified during measurement")
            with self.assertRaisesRegex(ValueError, "changed during benchmarking"):
                B.check_integrity(fingerprints)

    def test_failed_and_timed_out_children_are_not_samples(self):
        with self.assertRaisesRegex(RuntimeError, "exited 9"):
            B.run([sys.executable, "-c", "raise SystemExit(9)"])
        start = time.perf_counter()
        with self.assertRaises(TimeoutError):
            B.run([sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1)
        self.assertLess(time.perf_counter() - start, 3)
        with self.assertRaises(ChildProcessError):
            os.waitpid(-1, os.WNOHANG)

    def test_rss_is_per_process_not_cumulative_high_water(self):
        large, _ = B.run([sys.executable, "-c", "x=bytearray(64*1024*1024); print(len(x))"])
        small, _ = B.run([sys.executable, "-c", "print(1)"])
        self.assertGreater(large["peak_rss_bytes"], small["peak_rss_bytes"] + 32 * 1024 * 1024)

    def test_llvm_emission_time_is_included_and_build_directory_is_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            compiler = directory / "compiler"
            # A deliberately slow emitting stage catches accidentally timing only
            # Clang. Its on-disk artifact also detects reuse of an output directory.
            compiler.write_text(f"#!{sys.executable}\n" +
                "import pathlib,sys,time\n"
                "if '--emit-llvm' in sys.argv:\n"
                " time.sleep(0.1); print('IR')\n"
                "else:\n"
                " assert not pathlib.Path('cache.o').exists()\n"
                " pathlib.Path('cache.o').touch()\n"
                " out=pathlib.Path(sys.argv[sys.argv.index('-o')+1]); out.write_text('binary'); out.chmod(0o755)\n")
            compiler.chmod(0o755)
            paths = {"emlf": str(compiler), "clang": str(compiler)}
            _, sample = B.build(self.workload, "mlf", directory / "first", paths, ROOT / "runtime/mlf_runtime.c", [], None, 10)
            self.assertEqual(len(sample["stages"]), 2)
            self.assertGreaterEqual(sample["wall_seconds"], 0.1)
            self.assertGreaterEqual(sample["wall_seconds"], sum(s["wall_seconds"] for s in sample["stages"]))
            with self.assertRaises(FileExistsError):
                B.build(self.workload, "mlf", directory / "first", paths, ROOT / "runtime/mlf_runtime.c", [], None, 10)
            B.build(self.workload, "mlf", directory / "second", paths, ROOT / "runtime/mlf_runtime.c", [], None, 10)

    def test_medians_and_ratios_allow_c_to_lose(self):
        samples = [{"wall_seconds": n, "cpu_seconds": n / 2, "peak_rss_bytes": n * 100} for n in [9, 1, 2]]
        self.assertEqual(B.summarize(samples)["median_wall_seconds"], 2)
        self.assertIsNone(B.summarize([]))
        self.assertEqual(B.ratios({"c": 2, "rust": 1, "haskell": 4, "mlf": 6}),
                         {"c": 1, "rust": 0.5, "haskell": 2, "mlf": 3})

    def test_failure_replaces_stale_success_and_no_measurement_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            output = directory / "results.json"
            output.write_text('{"status":"passed"}')
            binary = directory / "bad-output"
            binary.write_text(f"#!{sys.executable}\nprint('wrong')\n")
            binary.chmod(0o755)
            with patch.object(B, "toolchain", return_value=({}, ROOT / "runtime/mlf_runtime.c", [], {})), \
                 patch.object(B, "build", return_value=(binary, {})) as build, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = B.main(["--emlf", "unused", "--compile-only", "--output", str(output)])
            self.assertEqual(result, 1)
            self.assertEqual(build.call_count, 1)  # preparation failed before timed builds
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertIn("output mismatch", report["error"])
            self.assertEqual(report["geometric_means"], {})

    def test_invalid_cli_inputs_fail_before_tools(self):
        for options in (["--size", "21"], ["--benchmark", "unknown"]):
            with tempfile.TemporaryDirectory() as directory, patch.object(B, "toolchain") as tools, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = B.main(["--emlf", "unused", "--output", str(Path(directory) / "result.json"), *options])
                self.assertEqual(result, 1)
                tools.assert_not_called()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            B.main(["--emlf", "unused", "--runs", "1"])


class NativeAllocationTests(unittest.TestCase):
    def test_mlf_allocates_every_tree_node(self):
        # Untimed allocation probe. The generated LLVM is unchanged; a temporary
        # runtime counts fully applied constructors, not curried descriptors.
        # Tags follow this checked source: 0 Unit, 1 Nil, 2 Node, 3 Rec,
        # 4 Monad dictionary (see MLF.LLVM).
        # This tests work, not merely an output that a closed formula could fake.
        emlf = shutil.which("emlf")
        self.assertIsNotNone(emlf, "Run using cabal test benchmark-harness-tests")
        clang = B.tool("clang")
        gmp = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "gmp"], text=True))
        runtime = Path(subprocess.check_output([emlf, "--llvm-runtime"], text=True).strip())
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            ir = directory / "program.ll"
            ir.write_bytes(subprocess.check_output([emlf, "--emit-llvm", str(ROOT / "benchmarks/binary-trees/mlf/main.emlf")]))
            probe = ROOT / "test/benchmark_allocations.c"
            subprocess.run([clang, "-O2", "-DMLF_ALLOCATION_AUDIT", "-Dmlf_run=mlf_original_run", "-I", str(runtime.parent),
                            *gmp, "-c", str(runtime), "-o", str(directory / "runtime.o")], check=True, capture_output=True)
            binary = directory / "program"
            subprocess.run([clang, "-O2", "-Wno-override-module", str(ir), str(directory / "runtime.o"), str(probe),
                            "-I", str(runtime.parent), *gmp, "-o", str(binary)], check=True, capture_output=True)
            workload = B.load_manifest()["workloads"][0]
            for size in (6, 7, 10, 16):
                sample = B.execute(workload, "mlf", binary, size, None, 60)
                counts = [int(n) for n in re.findall(rb"check: (\d+)", B.expected_output(workload, size))]
                self.assertEqual(sample["stderr"].strip(), f"allocated_tree_nodes={sum(counts)}")


if __name__ == "__main__":
    unittest.main()
