"""Deterministic correctness/failure tests; timing limits use synthetic data."""
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

    def test_performance_limits_apply_to_every_workload_and_include_boundary(self):
        rows = [dict(benchmark="fast", compilation_ratios={"mlf": 1}, runtime_ratios={"mlf": 2}),
                dict(benchmark="slow", compilation_ratios={"mlf": 5.001}, runtime_ratios={"mlf": 1.5})]
        checks = B.performance_checks(rows, {"compilation": 5, "runtime": 2})
        self.assertEqual([c["passed"] for c in checks], [True, True, False, True])
        self.assertEqual(checks[2]["benchmark"], "slow")
        self.assertEqual(B.performance_checks(rows, {"compilation": None, "runtime": None}), [])
        for ratio in [float("nan"), float("inf"), 0, -1]:
            with self.subTest(ratio=ratio), self.assertRaises(ValueError):
                B.performance_checks([dict(benchmark="bad", runtime_ratios={"mlf": ratio})], {"runtime": 2})
        with self.assertRaisesRegex(ValueError, "unmeasured"):
            B.performance_checks([dict(benchmark="missing", runtime_ratios=None)], {"runtime": 2})

    def test_invalid_performance_limits_fail_before_tools(self):
        options = [["--max-compile-ratio", "0"], ["--max-runtime-ratio", "nan"],
                   ["--max-runtime-ratio", "inf"], ["--max-compile-ratio", "-1"],
                   ["--compile-only", "--max-runtime-ratio", "2"],
                   ["--runtime-only", "--max-compile-ratio", "5"]]
        for args in options:
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                B.main(["--emlf", "nonexistent-compiler", *args])

    def test_oracle_matches_independent_pinned_fixture(self):
        B.validate_output(self.workload, 10, (ROOT / self.workload["fixture"]).read_bytes())
        self.assertEqual(B.expected_output(self.workload, 0), B.expected_output(self.workload, 6))
        self.assertIn(b"32 trees of depth 6 check: 4064", B.expected_output(self.workload, 7))

    def test_all_workloads_have_complete_provenance_and_fixtures(self):
        manifest = B.load_manifest()
        self.assertEqual([w["name"] for w in manifest["workloads"]],
                         ["binary-trees", "pidigits", "n-body", "fannkuch-redux", "spectral-norm", "fasta", "mandelbrot", "reverse-complement", "k-nucleotide"])
        for w in manifest["workloads"]:
            with self.subTest(workload=w["name"]):
                self.assertEqual(set(w["flags"]), set(B.LANGUAGES))
                self.assertIn(w["fixture_input"], w["check_inputs"])
                self.assertLessEqual(w["minimum_input"], w["default_input"])
                self.assertLessEqual(w["default_input"], w["maximum_input"])
                self.assertTrue(all((ROOT / s).is_file() for s in w["sources"].values()))
                self.assertTrue(w["fixture_upstream_path"].startswith("public/download/"))
                B.validate_output(w, w["fixture_input"], (ROOT / w["fixture"]).read_bytes())
                for lang in ("c", "rust", "haskell"):
                    provenance = w["provenance"][lang]
                    self.assertEqual(w["sources"][lang], provenance["build_source"])
                    for key in ("build_source", "original_source"):
                        self.assertIn(provenance[key], manifest["pinned_sha256"])
                    self.assertEqual(len(provenance["upstream_git_blob"]), 40)

    def test_dna_inputs_match_pinned_fasta_fixtures(self):
        for w in B.load_manifest()["workloads"]:
            if w.get("input_kind") == "fasta":
                self.assertEqual(B.fasta_output(w["fixture_input"]), (ROOT / w["input_fixture"]).read_bytes())
                self.assertTrue(w["input_fixture_upstream_path"].startswith("public/download/"))

    def test_reverse_complement_checks_headers_ambiguity_and_line_wrapping(self):
        source = b">id description\nacgtumrwsykvhdbn\n>empty\n>last\n" + b"a"*61
        expected = b">id description\nNVHDBMRSWYKAACGT\n>empty\n>last\n" + b"T"*60 + b"\nT\n"
        self.assertEqual(B.reverse_complement(source), expected)
        self.assertEqual(B.reverse_complement(b""), b"")
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "reverse-complement")
        expected = B.expected_output(w, 31)
        for wrong in (expected[:-1], expected.replace(b">ONE", b">OTHER"),
                      expected.replace(b"T", b"A", 1), expected.replace(b"\n", b"\r\n")):
            with self.subTest(wrong=wrong[:40]), self.assertRaises(ValueError):
                B.validate_output(w, 31, wrong)

    def test_nucleotide_counts_include_overlaps_ties_and_only_record_three(self):
        zero = b"0\tGGT\n0\tGGTA\n0\tGGTATT\n0\tGGTATTTTAATT\n0\tGGTATTTTAATTTATAGT\n"
        expected = b"A 25.000\nC 25.000\nG 25.000\nT 25.000\n\nAC 33.333\nCG 33.333\nGT 33.333\n\n" + zero
        self.assertEqual(B.nucleotide_counts(b">ONE\nGGT\n>THREE description\naCgT\n>FOUR\nGGT\n"), expected)
        self.assertEqual(B.nucleotide_counts(b">THREE\nAAAA"), b"A 100.000\n\nAA 100.000\n\n" + zero)
        self.assertEqual(B.nucleotide_counts(b">THREE\n"), b"\n\n" + zero)
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "k-nucleotide")
        expected = B.expected_output(w, 1000)
        for wrong in (expected.replace(b"GGT\n", b"GGA\n"), expected[:-1],
                      expected.replace(b"54\t", b"55\t"), b"\n".join(reversed(expected.splitlines()))):
            self.assertNotEqual(wrong, expected)
            with self.assertRaises(ValueError):
                B.validate_output(w, 1000, wrong)

    def test_nucleotide_rounding_accepts_only_exact_midpoint_neighbours(self):
        # A=1/320 gives 0.3125 percent: only 0.312 and 0.313 are permitted.
        lines = B.nucleotide_lines(b">THREE\nA" + b"C"*319)
        self.assertIn((b"A 0.312\n", b"A 0.313\n"), lines)
        self.assertNotIn(b"A 0.311\n", next(options for options in lines if options[0].startswith(b"A ")))
        not_tie = B.nucleotide_lines(b">THREE\nA" + b"C"*318)
        self.assertEqual(next(options for options in not_tie if options[0].startswith(b"A ")), (b"A 0.313\n",))
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "k-nucleotide")
        with patch.object(B, "nucleotide_expected_lines", return_value=lines):
            output = b"".join(options[0] for options in lines)
            B.validate_output(w, 1, output)
            B.validate_output(w, 1, output.replace(b"A 0.312", b"A 0.313"))
            with self.assertRaises(ValueError):
                B.validate_output(w, 1, output.replace(b"A 0.312", b"A 0.311"))

    def test_stdin_workloads_share_bytes_and_record_hash_without_embedding_input(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "reverse-complement")
        expected = B.expected_output(w, 31)
        for language in B.LANGUAGES:
            with patch.object(B, "run", return_value=({}, expected)) as run:
                sample = B.execute(w, language, Path("program"), 31, {}, 10)
            self.assertEqual(run.call_args.args[0], ["program"])
            self.assertEqual(run.call_args.kwargs["data"], B.fasta_output(31))
            self.assertEqual(sample["stdin_bytes"], len(B.fasta_output(31)))
            self.assertEqual(sample["stdin_sha256"], B.hashlib.sha256(B.fasta_output(31)).hexdigest())
            self.assertNotIn("stdin", sample)

    def test_spectral_norm_checks_single_finite_result(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "spectral-norm")
        self.assertEqual(B.spectral_norm(1), 1.0)
        self.assertAlmostEqual(B.spectral_norm(100), 1.274219991, places=8)
        B.validate_output(w, 1, b"1.000000000\n")
        for wrong in (b"", b"NaN", b"Infinity", b"1 1", b"1.00000002", b"1 extra"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                B.validate_output(w, 1, wrong)

    def test_fasta_requires_exact_bases_wrapping_and_rng_continuity(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "fasta")
        expected = b">ONE Homo sapiens alu\nGG\n>TWO IUB ambiguity codes\nctt\n>THREE Homo sapiens frequency\ntgagc\n"
        self.assertEqual(B.fasta_output(1), expected)
        B.validate_output(w,1,expected)
        for wrong in (expected.replace(b"ctt",b"ctg"),expected.replace(b"tgagc",b"cttga"),
                      expected.replace(b"\n",b"\r\n"),expected[:-1],expected+b"\n"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                B.validate_output(w,1,wrong)
        lines=B.fasta_output(31).splitlines()
        self.assertEqual([len(line) for line in lines if not line.startswith(b">")], [60,2,60,33,60,60,35])

    def test_mandelbrot_requires_exact_pixels_header_and_zero_padding(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "mandelbrot")
        expected = b"P4\n9 9\n"+bytes([0,0,2,0,7,128,15,128,63,128,63,128,15,128,7,128,2,0])
        self.assertEqual(B.mandelbrot_output(1), b"P4\n1 1\n\0")
        self.assertEqual(B.mandelbrot_output(8), b"P4\n8 8\n"+bytes([2,0,15,47,255,47,15,0]))
        self.assertEqual(B.mandelbrot_output(9), expected)
        B.validate_output(w,9,expected)
        for wrong in (expected.replace(b"P4",b"P1"), expected.replace(b"9 9",b"9 8"),
                      expected[:-1], expected+b"\n", expected[:-1]+b"\x01",
                      expected[:7]+b"\x80"+expected[8:]):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                B.validate_output(w,9,wrong)

    def test_pidigits_oracle_and_partial_row_checks(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "pidigits")
        self.assertEqual(B.pi_digits(50), "31415926535897932384626433832795028841971693993751")
        expected = b"3141592653\t:10\n5897932384\t:20\n6264338   \t:27\n"
        B.validate_output(w, 27, expected)
        for wrong in (expected.replace(b"6264338", b"6264337"), expected.replace(b":27", b":30"), expected[:-5], b""):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                B.validate_output(w, 27, wrong)

    def test_nbody_tolerance_rejects_nonfinite_missing_and_wrong_values(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "n-body")
        reference = B.nbody_energy(1)
        self.assertAlmostEqual(reference[0], -0.16907516382852447, places=14)
        self.assertAlmostEqual(reference[1], -0.16907495402506745, places=14)
        near = f"{reference[0]+5e-9:.12f} {reference[1]-5e-9:.12f}".encode()
        B.validate_output(w, 1, near)
        for wrong in (b"NaN NaN", b"Infinity -Infinity", b"", b"-0.169075164",
                      b"-0.169075164 -0.169074954 extra", b"-0.169075164 -0.169075164",
                      b"-0.169075164 -0.1690749", b"0.169075164 -0.169074954"):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                B.validate_output(w, 1, wrong)

    def test_fannkuch_unranking_checks_checksum_and_maximum(self):
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "fannkuch-redux")
        for n, result in [(1,(0,0)), (2,(-1,1)), (3,(2,2)), (5,(11,7)), (8,(1616,22))]:
            self.assertEqual(B.fannkuch_result(n), result)
        for wrong in (b"-228\nPfannkuchen(7) = 16", b"228\nPfannkuchen(7) = 15",
                      b"228\nPfannkuchen(8) = 16", b"228 16", b""):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                B.validate_output(w, 7, wrong)

    def test_vendored_adaptation_patches_reconstruct_build_sources(self):
        # Pinning a patch is not enough: prove it describes the actual compiled
        # source and the preserved upstream original, for every adaptation.
        for w in B.load_manifest()["workloads"]:
            for lang, info in w["provenance"].items():
                if info["original_source"] == info["build_source"]:
                    continue
                patch_file = ROOT / info["build_source"]
                patch_file = patch_file.with_name("adaptation.patch")
                with self.subTest(workload=w["name"], language=lang), tempfile.TemporaryDirectory() as directory:
                    original = Path(directory) / Path(info["original_source"]).name
                    shutil.copyfile(ROOT / info["original_source"], original)
                    subprocess.run(["patch", "--batch", str(original), str(patch_file)],
                                   check=True, capture_output=True)
                    self.assertEqual(original.read_bytes(), (ROOT / info["build_source"]).read_bytes())

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
                 patch.object(B, "haskell_dependencies", return_value=([], {}, {})), \
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
        for options in (["--size", "10"], ["--benchmark", "binary-trees", "--size", "21"],
                        ["--benchmark", "pidigits", "--size", "0"], ["--benchmark", "n-body", "--size", "-1"],
                        ["--benchmark", "fannkuch-redux", "--size", "0"],
                        ["--benchmark", "n-body", "--benchmark", "pidigits", "--size", "10"],
                        ["--benchmark", "unknown"]):
            with tempfile.TemporaryDirectory() as directory, patch.object(B, "toolchain") as tools, \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                result = B.main(["--emlf", "unused", "--output", str(Path(directory) / "result.json"), *options])
                self.assertEqual(result, 1)
                tools.assert_not_called()
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            B.main(["--emlf", "unused", "--runs", "1"])

    def test_interruption_cannot_leave_a_stale_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.json"
            output.write_text('{"status":"passed"}')
            def interrupted():
                self.assertEqual(json.loads(output.read_text())["status"], "running")
                raise KeyboardInterrupt
            with patch.object(B, "load_manifest", side_effect=interrupted), \
                 contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(B.main(["--emlf", "unused", "--output", str(output)]), 130)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["error"], "Benchmark interrupted")
            self.assertEqual(report["geometric_means"], {})


class NativeAllocationTests(unittest.TestCase):
    def test_real_console_raw_input_matches_native_bytes_and_eof(self):
        emlf = shutil.which("emlf")
        self.assertIsNotNone(emlf, "Run using cabal test benchmark-harness-tests")
        source = ("do { a <- getByteLine; n <- lengthByteArray a; putBytes a 0 n; "
                  "b <- getByteLine; m <- lengthByteArray b; putBytes b 0 m; "
                  "end <- getByteLine; size <- lengthByteArray end; printInt size }")
        data = bytes([0, 255, 128, 10, 129, 65])
        runtime = Path(subprocess.check_output([emlf, "--llvm-runtime"], text=True).strip())
        gmp = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "gmp"], text=True))
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            program = directory / "console.emlf"
            program.write_text(source)
            ir = directory / "console.ll"
            ir.write_bytes(subprocess.check_output([emlf, "--emit-llvm", "--expr", source]))
            binary = directory / "console"
            subprocess.run([B.tool("clang"), "-O2", "-Wno-override-module", str(ir), str(runtime), *gmp,
                            "-lm", "-o", str(binary)], check=True, capture_output=True)
            for command in ([emlf, "--run", str(program)], [str(binary)]):
                _, output = B.run(command, data=data, timeout=30)
                self.assertEqual(output, data + b"0\n")

    def test_mlf_counts_every_window_and_distinct_key_in_all_seven_tables(self):
        emlf = shutil.which("emlf")
        self.assertIsNotNone(emlf, "Run using cabal test benchmark-harness-tests")
        clang = B.tool("clang")
        gmp = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "gmp"], text=True))
        runtime = Path(subprocess.check_output([emlf, "--llvm-runtime"], text=True).strip())
        w = next(w for w in B.load_manifest()["workloads"] if w["name"] == "k-nucleotide")
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            ir = directory / "program.ll"
            ir.write_bytes(subprocess.check_output([emlf, "--emit-llvm", str(ROOT / w["sources"]["mlf"])]))
            subprocess.run([clang, "-O2", "-DMLF_TABLE_AUDIT", "-DMLF_GC_THRESHOLD=32",
                            "-Dmlf_run=mlf_original_run", "-I", str(runtime.parent), *gmp,
                            "-c", str(runtime), "-o", str(directory / "runtime.o")], check=True, capture_output=True)
            binary = directory / "program"
            subprocess.run([clang, "-O2", "-Wno-override-module", str(ir), str(directory / "runtime.o"),
                            str(ROOT / "test/benchmark_tables.c"), "-I", str(runtime.parent), *gmp,
                            "-lm", "-o", str(binary)], check=True, capture_output=True)
            for size in (1, 7, 31, 1000):
                sequence = B.fasta_records(B.fasta_output(size))[2][1].upper()
                expected = []
                for k in (1, 2, 3, 4, 6, 12, 18):
                    distinct = len({sequence[i:i+k] for i in range(len(sequence)-k+1)})
                    writes = max(0, len(sequence)-k+1) + (distinct if k <= 2 else 0)
                    expected.append((writes, distinct))
                sample = B.execute(w, "mlf", binary, size, None, 60)
                self.assertTrue(sample["stderr"].startswith("tables=7\n"))
                observed = [tuple(map(int, pair)) for pair in re.findall(r"writes=(\d+) distinct=(\d+)", sample["stderr"])]
                self.assertEqual(observed, expected)

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
                            "-I", str(runtime.parent), *gmp, "-lm", "-o", str(binary)], check=True, capture_output=True)
            workload = B.load_manifest()["workloads"][0]
            for size in (6, 7, 10, 16):
                sample = B.execute(workload, "mlf", binary, size, None, 60)
                counts = [int(n) for n in re.findall(rb"check: (\d+)", B.expected_output(workload, size))]
                self.assertEqual(sample["stderr"].strip(), f"allocated_tree_nodes={sum(counts)}")


if __name__ == "__main__":
    unittest.main()
