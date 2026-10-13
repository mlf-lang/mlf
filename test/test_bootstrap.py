"""Fault-injection checks for native compiler selection and bootstrap evidence."""
import importlib.util
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


COMPILER = load("bootstrap-compiler")
BACKENDS = load("bootstrap-backends")


class BootstrapHarnessTests(unittest.TestCase):
    def test_native_matrix_requires_the_selected_cli_compiler(self):
        candidate = (ROOT / "dist-newstyle/native compiler/emlf-stage2").resolve()
        matrix = ("Backend matrix: 468 rows x 2 backends; no missing executions\n"
                  "423 shared IO/prelude/backend fixtures; 0 failures\n")
        selected = "Module CLI compiler: " + str(candidate) + "\n"
        self.assertEqual(BACKENDS.matrix_summary(selected + matrix, candidate)["cli_compiler"], str(candidate))
        for damaged in (matrix, selected + selected + matrix,
                        "Module CLI compiler: /seed/emlf\n" + matrix,
                        selected + matrix.replace("468 rows", "0 rows"),
                        selected + matrix.replace("0 failures", "1 failures")):
            with self.subTest(log=damaged), self.assertRaises(RuntimeError):
                BACKENDS.matrix_summary(damaged, candidate)

    def test_native_matrix_overrides_inherited_compiler_selection(self):
        candidate = ROOT / "stage2/emlf"
        seed = ROOT / "seed/emlf"
        with patch.dict(os.environ, {"MLF_BOOTSTRAP_COMPILER": str(seed), "MLF_LLVM_TEST_ABI": "compact-gc"}):
            env = BACKENDS.environment(ROOT / "drivers", seed, candidate)
        self.assertEqual(env["MLF_BOOTSTRAP_COMPILER"], str(candidate))
        self.assertEqual(env["MLF_LLVM_TEST_ABI"], "standard")
        self.assertNotEqual(env["MLF_BOOTSTRAP_COMPILER"], str(seed))

    def test_compact_matrix_requires_collector_and_small_heap(self):
        collector = {"cflags": ["-I/path with spaces/include"], "libs": ["/path with spaces/libgc.a"]}
        with patch.dict(os.environ, {"GC_INITIAL_HEAP_SIZE": "536870912",
                                     "MLF_LLVM_TEST_LIBS": "incorrect", "MLF_TEST_TRACE": "unexpected"}):
            env = BACKENDS.environment(ROOT / "drivers", ROOT / "seed/emlf", ROOT / "stage3/emlf", "compact-gc", collector)
        self.assertEqual(env["MLF_LLVM_TEST_ABI"], "compact-gc")
        self.assertEqual(env["GC_INITIAL_HEAP_SIZE"], "8388608")
        self.assertEqual(env["GC_FREE_SPACE_DIVISOR"], "1")
        self.assertEqual(env["MLF_LLVM_TEST_CFLAGS"], "'-I/path with spaces/include'")
        self.assertEqual(env["MLF_LLVM_TEST_LIBS"], "'/path with spaces/libgc.a'")
        self.assertNotIn("MLF_TEST_TRACE", env)
        for abi in ("compact-gc", "unknown"):
            with self.subTest(abi=abi), self.assertRaises(ValueError):
                BACKENDS.environment(ROOT / "drivers", ROOT / "seed/emlf", ROOT / "stage3/emlf", abi)

    def test_both_layout_plan_builds_drivers_once_and_runs_each_matrix(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch.object(subprocess, "run") as executed:
            BACKENDS.dry_run(ROOT / "drivers", ROOT / "stage3/emlf", ("standard", "compact-gc"))
        executed.assert_not_called()
        plan = output.getvalue()
        self.assertEqual(plan.count("+ cabal test backend-tests"), 2)
        self.assertEqual(plan.count("--emit-llvm-gc"), 2)
        self.assertIn("Matrix environment (standard):", plan)
        self.assertIn("Matrix environment (compact-gc):", plan)

    def test_module_corpus_cannot_drop_rejections_or_prelude_modes(self):
        # Model corpus damage without invoking a compiler: removing a category,
        # replacing negatives with positives, or dropping oracle data must fail.
        counts = {"figure12": 43, "hm-exhaustive": 1712, "hm-generated": 5000,
                  "annotations": 126, "readability": 18, "state": 97,
                  "modules": 60, "examples": 18, "benchmarks": 9}
        rows = [dict(schema_version=1, id=f"{category}-{i}", category=category,
                     expected_accept=True, no_prelude=False)
                for category, count in counts.items() for i in range(count)]
        rows[0].update(id="figure12-A8", expected_accept=False, expected_phase="Inference")
        modules = [r for r in rows if r["category"] == "modules"]
        modules[0]["no_prelude"] = True
        for row in modules[21:]:
            row.update(expected_accept=False, expected_phase="ModuleResolution",
                       expected_error_contains="not in scope")
        COMPILER.validate_manifest(rows)
        with self.assertRaisesRegex(RuntimeError, "lacks modules"):
            COMPILER.validate_manifest([r for r in rows if r["category"] != "modules"])
        with patch.dict(modules[21], expected_accept=True), self.assertRaisesRegex(RuntimeError, "coverage"):
            COMPILER.validate_manifest(rows)
        with patch.dict(modules[0], no_prelude=False), self.assertRaisesRegex(RuntimeError, "coverage"):
            COMPILER.validate_manifest(rows)
        for missing in (None, "", " \n\t"):
            with self.subTest(expectation=missing), patch.dict(modules[21], expected_error_contains=missing), self.assertRaisesRegex(RuntimeError, "expectation"):
                COMPILER.validate_manifest(rows)

    def test_crashes_partial_targets_and_wrong_diagnostics_are_not_rejections(self):
        row = dict(id="private-import", expected_phase="ModuleResolution",
                   expected_error_contains="not in scope: private")
        diagnostic = b"ModuleResolution: not in scope: private\n"
        COMPILER.check_rejection(row, subprocess.CompletedProcess([], 1, b"", diagnostic))
        for code, output, error in ((-11, b"", diagnostic), (2, b"", diagnostic),
                                    (1, b"partial target", diagnostic),
                                    (1, b"", b"Runtime: not in scope: private\n"),
                                    (1, b"", b"ModuleResolution: cannot find module Wrong\n")):
            with self.subTest(code=code, output=output, error=error), self.assertRaises(RuntimeError):
                COMPILER.check_rejection(row, subprocess.CompletedProcess([], code, output, error))


if __name__ == "__main__":
    unittest.main()
