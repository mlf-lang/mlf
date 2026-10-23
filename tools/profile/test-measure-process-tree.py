#!/usr/bin/env python3
"""Small, dependency-free tests for the qualification measurement helper."""
import importlib.util
from pathlib import Path
import os
import fcntl
import json
import signal
import sys
import time
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("measure", Path(__file__).with_name("measure-process-tree.py"))
measure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(measure)


class MeasurementTests(unittest.TestCase):
    def test_cache_inventory_distinguishes_absent_empty_and_populated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "cache"
            self.assertFalse(measure.cache_inventory(root)["existed"])
            root.mkdir()
            self.assertEqual(measure.cache_inventory(root)["files"], {})
            (root / "artifact.json").write_text("original receipt\n")
            (root / "link").symlink_to("artifact.json")
            files = measure.cache_inventory(root)["files"]
            self.assertEqual(files["artifact.json"]["sha256"], measure.digest(root / "artifact.json"))
            self.assertEqual(files["link"], {"symlink": "artifact.json"})

    def test_dependency_work_is_distinct_from_critical_path(self):
        report = {
            "scheduler": [{"invocation_id": "sample", "jobs": [
                {"id": "a", "dependencies": []},
                {"id": "b", "dependencies": ["a"]},
                {"id": "c", "dependencies": ["a"]},
                {"id": "d", "dependencies": ["b", "c"]},
            ]}],
            "scheduler_results": [{"invocation_id": "sample", "jobs": 2,
                "maximum_parallel_jobs": 2, "wall_seconds": 9,
                "tasks": [{"id": key, "wall_seconds": seconds, "cpu_seconds": seconds / 2}
                          for key, seconds in [("a", 2), ("b", 5), ("c", 3), ("d", 2)]]}],
        }
        row, = measure.scheduler_summary(report)
        self.assertEqual(row["aggregate_task_wall_seconds"], 12)
        self.assertEqual(row["aggregate_task_cpu_seconds"], 6)
        self.assertEqual(row["dependency_critical_path_seconds"], 9)
        self.assertEqual(row["maximum_parallel_jobs"], 2)

    def test_no_scheduler_is_valid(self):
        self.assertEqual(measure.scheduler_summary({}), [])

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "Linux sampling only")
    def test_process_tree_contains_child(self):
        child = subprocess.Popen(["sleep", "10"])
        try:
            rows, rss = measure.tree_snapshot(os.getpid())
            self.assertIn(child.pid, [row[0] for row in rows])
            self.assertGreater(rss, 0)
            self.assertGreater(measure.available_memory(), 0)
        finally:
            child.terminate()
            child.wait()


@unittest.skipUnless(Path("/proc/self/stat").exists(), "Linux lifecycle fixtures only")
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "source"
        self.repo.mkdir()
        self.lock = self.base / "lock"
        self.report = self.repo / ".mlf-build"
        self.report.mkdir()
        (self.repo / ".gitignore").write_text(".mlf-build/\n")
        (self.repo / "source.txt").write_text("before\n")
        self.tool = self.base / "tool"
        self.tool.write_text("tool-before\n")
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
        self.processes = []
        self.addCleanup(self.stop_processes)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args])

    def stop_processes(self):
        for proc in self.processes:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

    def launch(self, name, code, tee=False, sampler=None):
        output = self.base / name
        args = [sys.executable, str(Path(sampler or measure.__file__).resolve()),
                "--output", str(output), "--source-root", str(self.repo),
                "--report-root", str(self.report), "--lock", str(self.lock),
                "--label", name, "--tool", str(self.tool),
                "--minimum-available-mib", "0", "--interval", "0.02"]
        if tee:
            args.append("--tee")
        args += ["--", sys.executable, "-c", code]
        stdout = self.base / (name + ".stdout")
        with open(stdout, "wb") as out:
            proc = subprocess.Popen(args, stdout=out, stderr=subprocess.STDOUT)
        self.processes.append(proc)
        return proc, output, stdout

    def until(self, predicate, timeout=6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("fixture condition timed out")

    def test_term_and_int_reap_descendants_before_next_holder(self):
        for signum in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=signum):
                pidfile = self.base / f"pids-{signum}"
                grandchild = ("import os,signal,time; "
                              "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                              "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                              f"open({str(pidfile)!r},'a').write(str(os.getpid())+'\\n'); "
                              "time.sleep(60)")
                command = ("import os,signal,subprocess,sys,time; "
                           "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                           "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                           f"open({str(pidfile)!r},'w').write(str(os.getpid())+'\\n'); "
                           f"subprocess.Popen([sys.executable,'-c',{grandchild!r}],start_new_session=True); "
                           f"open({str(self.report / 'build-report.json')!r},'w').write('{{\"fixture\":{int(signum)}}}'); "
                           "time.sleep(60)")
                proc, output, _ = self.launch(f"signal-{signum}", command)
                self.until(lambda: pidfile.exists() and len(pidfile.read_text().splitlines()) == 2)
                pids = [int(x) for x in pidfile.read_text().splitlines()]
                checked = self.base / f"queued-check-{signum}"
                next_code = ("from pathlib import Path; import json; "
                             f"Path({str(checked)!r}).write_text(json.dumps([p for p in {pids!r} if Path('/proc/'+str(p)).exists()]))")
                queued, _, _ = self.launch(f"queued-{signum}", next_code)
                self.until(lambda: (self.base / f"queued-{signum}").exists())
                os.kill(proc.pid, signum)
                self.assertEqual(proc.wait(timeout=7), 128 + signum)
                self.assertEqual(queued.wait(timeout=7), 0)
                self.assertEqual(json.loads(checked.read_text()), [])
                self.assertTrue(all(not Path(f"/proc/{pid}").exists() for pid in pids))
                result = json.loads((output / "result.json").read_text())
                self.assertEqual(result["interrupted_signal"], signum)
                self.assertTrue(result["command_started"])
                self.assertTrue(json.loads((output / "report-index.json").read_text()))

    def test_queued_identity_and_report_baseline_are_after_lock(self):
        report = self.report / "build-report.json"
        report.write_text('{"old":true}')
        sampler = self.base / "private-sampler.py"
        sampler.write_bytes(Path(measure.__file__).read_bytes())
        original_sampler_hash = measure.digest(sampler)
        with open(self.lock, "a+") as holder:
            fcntl.flock(holder, fcntl.LOCK_EX)
            proc, output, _ = self.launch("queued-identity", "pass", sampler=sampler)
            self.until(output.exists)
            time.sleep(0.15)
            self.assertFalse((output / "source-files.json").exists())
            sampler.write_text(sampler.read_text() + "\n# Replaced while queued.\n")
            (self.repo / "source.txt").write_text("committed-after-lock\n")
            self.git("add", "source.txt")
            self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "post-lock")
            expected_commit = self.git("rev-parse", "HEAD").decode().strip()
            (self.repo / "source.txt").write_text("dirty-after-lock\n")
            self.tool.write_text("tool-after-lock\n")
            report.write_text('{"prior-holder":true}')
        self.assertEqual(proc.wait(timeout=6), 0)
        context = json.loads((output / "context.json").read_text())
        hashes = json.loads((output / "source-files.json").read_text())
        self.assertEqual(context["source_commit"], expected_commit)
        self.assertEqual(context["measurement_script_sha256"], original_sampler_hash)
        self.assertNotEqual(context["measurement_script_sha256"], measure.digest(sampler))
        self.assertEqual(hashes["source.txt"], measure.digest(self.repo / "source.txt"))
        self.assertEqual(context["tools"][str(self.tool)]["sha256"], measure.digest(self.tool))
        self.assertIn("dirty-after-lock", (output / "source.diff").read_text())
        self.assertEqual(json.loads((output / "report-index.json").read_text()), [])

    def test_sampling_exception_reaps_command_and_writes_result(self):
        pidfile = self.base / "error-child"
        child = ("import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                 f"open({str(pidfile)!r},'w').write(str(os.getpid())); time.sleep(60)")
        output = self.base / "sampling-error"
        wrapper = self.base / "inject-error.py"
        wrapper.write_text("\n".join([
            "import importlib.util,sys",
            "from pathlib import Path",
            "from types import SimpleNamespace",
            f"spec=importlib.util.spec_from_file_location('measure',{measure.__file__!r})",
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)",
            "original=m.available_memory",
            "def injected():",
            f"    if Path({str(pidfile)!r}).exists(): raise RuntimeError('injected sample failure')",
            "    return original()",
            "m.available_memory=injected",
            "args=SimpleNamespace(" + ",".join(f"{k}={v!r}" for k, v in {
                "output": str(output), "source_root": str(self.repo),
                "report_root": str(self.report), "lock": str(self.lock),
                "label": "sampling-error", "tool": [], "cache_dir": [],
                "minimum_available_mib": 0, "interval": 0.02, "tee": False,
                "command": [sys.executable, "-c", child],
            }.items()) + ")",
            "sys.exit(m.run(args))",
        ]))
        with open(self.base / "sampling-error.stdout", "wb") as out:
            proc = subprocess.Popen([sys.executable, str(wrapper)], stdout=out, stderr=subprocess.STDOUT)
        self.processes.append(proc)
        self.assertEqual(proc.wait(timeout=7), 1)
        self.assertFalse(Path('/proc/' + pidfile.read_text()).exists())
        result = json.loads((output / "result.json").read_text())
        self.assertIn("injected sample failure", result["error"])
        self.assertTrue(result["command_started"])

    def test_malformed_report_shapes_do_not_abort_measurement(self):
        command = ("from pathlib import Path; "
                   f"p=Path({str(self.report)!r}); "
                   "(p/'one').mkdir(); (p/'two').mkdir(); "
                   "(p/'one'/'build-report.json').write_text('[]'); "
                   "(p/'two'/'build-report.json').write_text('{\"scheduler\":null}')")
        proc, output, _ = self.launch("malformed-reports", command)
        self.assertEqual(proc.wait(timeout=6), 0)
        self.assertEqual(json.loads((output / 'result.json').read_text())["returncode"], 0)
        self.assertEqual(len(json.loads((output / 'report-errors.json').read_text())), 2)

    def test_tee_streams_before_completion_and_keeps_exact_log(self):
        proc, output, console = self.launch("tee", "import os,time; os.write(1,b'first\\n'); time.sleep(0.5); os.write(2,b'last\\n')", tee=True)
        self.until(lambda: b"first\n" in console.read_bytes())
        self.assertIsNone(proc.poll())
        self.assertEqual(proc.wait(timeout=6), 0)
        self.assertEqual((output / "command.log").read_bytes(), b"first\nlast\n")
        self.assertIn(b"first\nlast\n", console.read_bytes())


if __name__ == "__main__":
    unittest.main()
