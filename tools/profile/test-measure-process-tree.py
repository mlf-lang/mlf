#!/usr/bin/env python3
"""Small, dependency-free tests for the qualification measurement helper."""
import importlib.util
from pathlib import Path
import os
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


if __name__ == "__main__":
    unittest.main()
