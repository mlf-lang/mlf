"""Release gates reject incomplete, stale and misdirected verification evidence."""
import copy
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release as R

MANIFEST = json.loads((ROOT / "benchmarks/manifest.json").read_text())


def evidence(compiler_hash):
    candidate = {"stage": 3, "path": "/verified/emlf-stage3", "sha256": compiler_hash}
    bootstrap = {"complete": True, "fixed_point": True, "candidate": candidate,
                 "stages": [{"stage": n, "reused_seed_compilation": False,
                             "llvm_sha256": "same-llvm", "binary_sha256": compiler_hash} for n in (1, 2, 3)],
                 "parity": {"compiler": candidate["path"], "compiler_sha256": compiler_hash,
                            "cases": 7083, "accepted": 3199, "rejected": 3884,
                            "runtime_rows": 80, "runtime_executions": 160}, "runtime_sources": {}}
    backends = {"complete": True, "compiler": candidate["path"], "compiler_sha256": compiler_hash,
                "matrices": {abi: {"rows": 475, "fixtures": 428, "backends": 2,
                                   "cli_compiler": candidate["path"], "environment": {"MLF_LLVM_TEST_ABI": abi}}
                             for abi in ("standard", "compact-gc")}}
    measurements = {"sample_count": 5, "samples": [{"wall_seconds": 1}] * 5, "median_wall_seconds": 1}
    inputs = {w["name"]: sorted(set(w["check_inputs"] + [w["default_input"]])) for w in MANIFEST["workloads"]}
    defaults = {w["name"]: w["default_input"] for w in MANIFEST["workloads"]}
    benchmark = {"status": "passed", "toolchain": {"emlf": {"path": candidate["path"], "sha256": compiler_hash}},
                 "configuration": {"runs": 5, "maximum_mlf_c_ratios": R.LIMITS,
                                   "compile_only": False, "runtime_only": False},
                 "results": [{"benchmark": name, "input": defaults[name], "correctness_inputs": inputs[name],
                              "languages": {language: {"correctness": [{"output_sha256": "0" * 64} for _ in inputs[name]],
                                              "compilation": copy.deepcopy(measurements),
                                              "runtime": copy.deepcopy(measurements)} for language in R.LANGUAGES}}
                             for name in sorted(R.WORKLOADS)],
                 "performance_checks": [{"benchmark": name, "dimension": dimension, "passed": True,
                                         "mlf_over_c": 1, "maximum_ratio": limit}
                                        for name in sorted(R.WORKLOADS) for dimension, limit in R.LIMITS.items()]}
    return bootstrap, backends, benchmark


def release_fixture(directory):
    package = directory / "package"
    (package / "evidence").mkdir(parents=True)
    (package / "runtime").mkdir()
    for name in ("emlf", "emlf-compile"):
        (package / name).write_text("test executable\n")
        (package / name).chmod(0o755)
    compiler_hash = R.digest(package / "emlf")
    bootstrap, backends, benchmark = evidence(compiler_hash)
    (package / "runtime/mlf_runtime.c").write_text("runtime\n")
    bootstrap["runtime_sources"] = {"runtime/mlf_runtime.c": R.digest(package / "runtime/mlf_runtime.c")}
    for name, data in (("bootstrap", bootstrap), ("backends", backends), ("benchmarks", benchmark)):
        R.write_json(package / "evidence" / (name + ".json"), data)
    (package / "evidence/cabal-tests.log").write_text("Tests passed\n")
    R.write_json(package / "evidence/manifest.json", MANIFEST)
    report = {"schema_version": 1, "complete": True, "compiler_sha256": compiler_hash,
              "host": {"system": platform.system(), "machine": platform.machine()},
              "smoke": {"backends": ["interpreter", "llvm"], "outside_checkout": True},
              "steps": [{"name": name, "exit_code": 0,
                         "log_sha256": R.digest(package / "evidence/cabal-tests.log")}
                        for name in ("cabal-tests", "bootstrap", "backends", "benchmarks")],
              "package_files": R.package_files(package)}
    R.write_json(directory / "verification.json", report)
    return report


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.evidence = evidence("compiler-hash")

    def validate(self):
        R.validate_evidence(*self.evidence, "compiler-hash", MANIFEST)

    def test_complete_stage3_evidence_passes(self):
        self.validate()

    def test_stage2_parity_cannot_certify_stage3(self):
        self.evidence[0]["parity"]["compiler"] = "/verified/emlf-stage2"
        with self.assertRaisesRegex(ValueError, "Parity"):
            self.validate()

    def test_fixed_point_and_fresh_stages_are_required(self):
        for mutation in (lambda b: b.update(fixed_point=False),
                         lambda b: b["stages"].pop(),
                         lambda b: b["stages"][0].update(reused_seed_compilation=True),
                         lambda b: b["stages"][1].update(llvm_sha256="different"),
                         lambda b: b["candidate"].update(stage=2)):
            self.evidence = evidence("compiler-hash")
            mutation(self.evidence[0])
            with self.assertRaises(ValueError):
                self.validate()

    def test_neither_layout_nor_backend_can_be_skipped(self):
        for mutation in (lambda b: b["matrices"].pop("compact-gc"),
                         lambda b: b["matrices"]["standard"].update(backends=1),
                         lambda b: b["matrices"]["standard"].update(rows=0),
                         lambda b: b["matrices"]["standard"].update(cli_compiler="seed"),
                         lambda b: b["matrices"]["compact-gc"]["environment"].update(MLF_LLVM_TEST_ABI="standard")):
            self.evidence = evidence("compiler-hash")
            mutation(self.evidence[1])
            with self.assertRaises(ValueError):
                self.validate()

    def test_benchmark_coverage_and_samples_cannot_be_faked_by_pass_status(self):
        for mutation in (lambda b: b["results"].pop(),
                         lambda b: b["results"].__setitem__(0, b["results"][1]),
                         lambda b: b["performance_checks"].pop(),
                         lambda b: b["results"][0]["languages"].pop("rust"),
                         lambda b: b["results"][0]["languages"]["mlf"]["compilation"].update(samples=[]),
                         lambda b: b["results"][0]["languages"]["mlf"].update(correctness=[]),
                         lambda b: b["results"][0]["languages"]["mlf"]["correctness"][0].clear(),
                         lambda b: b["configuration"].update(size_override=1),
                         lambda b: b["results"][0].update(input=1),
                         lambda b: b["configuration"].update(runtime_only=True),
                         lambda b: b["toolchain"]["emlf"].update(sha256="seed")):
            self.evidence = evidence("compiler-hash")
            mutation(self.evidence[2])
            with self.assertRaises(ValueError):
                self.validate()

    def test_ratios_are_recomputed_from_measurements(self):
        self.evidence[2]["results"][0]["languages"]["mlf"]["compilation"].update(
            median_wall_seconds=6, samples=[{"wall_seconds": 6}] * 5)
        with self.assertRaisesRegex(ValueError, "performance limit"):
            self.validate()

    def test_medians_are_recomputed_and_bad_samples_fail(self):
        for value in (6, 0, -1, float("nan"), float("inf")):
            self.evidence = evidence("compiler-hash")
            self.evidence[2]["results"][0]["languages"]["c"]["compilation"]["samples"] = [{"wall_seconds": value}] * 5
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "timing"):
                self.validate()

    def test_failed_step_preserves_failure_and_never_completes_release(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = {"complete": False, "steps": []}
            with self.assertRaisesRegex(ValueError, "failed"):
                R.step("failure", [sys.executable, "-c", "raise SystemExit(9)"], directory, report)
            saved = json.loads((directory / "verification.json").read_text())
            self.assertFalse(saved["complete"])
            self.assertEqual(saved["steps"][0]["exit_code"], 9)
            self.assertTrue((directory / "failure.log").exists())

    def test_gate_does_not_inherit_compiler_or_collector_overrides(self):
        overrides = {"MLF_BOOTSTRAP_COMPILER": "wrong compiler", "MLF_LLVM_TEST_ABI": "wrong layout",
                     "MLF_TEST_FAIL_WRITE": "1", "GC_INITIAL_HEAP_SIZE": "1048576"}
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, overrides):
            report = {"complete": False, "steps": []}
            code = "import os; assert not any(key in os.environ for key in " + repr(list(overrides)) + ")"
            R.step("environment", [sys.executable, "-c", code], Path(temporary), report)
            self.assertEqual(report["steps"][0]["exit_code"], 0)
            self.assertFalse(report["complete"])

    def test_incomplete_or_changed_packages_are_not_installable(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary) / "release"
            report = release_fixture(directory)
            R.verify(directory)
            report["complete"] = False
            R.write_json(directory / "verification.json", report)
            with self.assertRaisesRegex(ValueError, "incomplete"):
                R.verify(directory)
            report["complete"] = True
            R.write_json(directory / "verification.json", report)
            (directory / "package/runtime/mlf_runtime.c").write_text("changed")
            with self.assertRaisesRegex(ValueError, "files changed"):
                R.install(directory, Path(temporary) / "prefix")
            self.assertFalse((Path(temporary) / "prefix").exists())

    def test_installation_is_relocatable_and_does_not_replace_unrelated_files(self):
        with tempfile.TemporaryDirectory(prefix="release install ") as temporary:
            directory = Path(temporary) / "release"
            release_fixture(directory)
            prefix = Path(temporary) / "prefix with spaces"
            with patch.object(R, "smoke") as checked:
                R.install(directory, prefix)
                checked.assert_called_once()
                R.install(directory, prefix)
            self.assertTrue((prefix / "bin/emlf").is_file())
            self.assertEqual((prefix / "bin/emlf").resolve().parent, (prefix / "bin/emlf-compile").resolve().parent)
            moved = Path(temporary) / "relocated"
            prefix.rename(moved)
            self.assertTrue((moved / "bin/emlf").is_file())
            (moved / "bin/emlf").unlink()
            (moved / "bin/emlf").write_text("other compiler")
            with self.assertRaisesRegex(ValueError, "unrelated"):
                R.install(directory, moved)
            self.assertEqual((moved / "bin/emlf").read_text(), "other compiler")


if __name__ == "__main__":
    unittest.main()
