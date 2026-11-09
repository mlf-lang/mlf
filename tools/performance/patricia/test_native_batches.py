#!/usr/bin/env python3
"""Keep native batching lossless against the original, independently modeled gate."""
import hashlib
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("patricia_native", HERE / "run_native.py")
native = importlib.util.module_from_spec(spec)
spec.loader.exec_module(native)

def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()

def actions(source):
    start = "main = runActions ["
    if source.count(start) != 1 or not source.endswith("];\n}\n"):
        raise ValueError("one complete generated action sequence required")
    return source.split(start, 1)[1][:-5]

class NativeBatchTests(unittest.TestCase):
    def test_original_full_fixture_and_model_remain_byte_exact(self):
        good, expected, bad, inventory = native.fixture()
        self.assertEqual(digest(good), "2de3d6d50d08c7cadf6e0651046aceae0d0424671e05694374fe60dc309dd8ff")
        self.assertEqual(digest(expected), "4a93db24d2adfba8420650fb3d9d359be942d1cfe2a56af9b973cada336bdfc6")
        self.assertEqual(digest(bad), "016665a1cbac56fd0fec739e4a17da27cd7608efc4e38391e87725fe36b8d706")
        self.assertEqual(inventory, dict(signed_keys=199, output_lines=4107, map_cases=9,
            set_cases=7, index_view_checks=35, lazy_payload_checks=9, selected_payload_error_checks=1))

    def test_all_actions_and_model_bytes_are_partitioned_once_in_order(self):
        good, expected, bad, _ = native.fixture()
        batches = [native.fixture(name) for name in native.BATCH_NAMES]
        self.assertEqual(len(batches), 8)
        self.assertEqual(",".join(actions(row[0]) for row in batches), actions(good))
        self.assertEqual(b"".join(row[1] for row in batches), expected)
        self.assertTrue(all(row[1] for row in batches))
        self.assertTrue(all(row[2] == bad for row in batches))

    def test_batch_definitions_are_exact_full_population_not_smaller_samples(self):
        good, _, _, _ = native.fixture()
        prefixes = ("a ::", "b ::", "sa =", "sb =", "lazyMap ::", "leftMap =", "rightMap ::")
        definitions = {prefix: next(line for line in good.splitlines() if line.startswith(prefix))
                       for prefix in prefixes}
        required = ((0, 1), (0, 1), (), (0,), (2, 3), (2,), (0, 2), (0, 4, 5, 6))
        for name, indices in zip(native.BATCH_NAMES, required):
            source, _, _, _ = native.fixture(name)
            for index, prefix in enumerate(prefixes):
                actual = [line for line in source.splitlines() if line.startswith(prefix)]
                self.assertEqual(actual, [definitions[prefix]] if index in indices else [], name)

    def test_rank_views_and_all_lazy_probes_remain_selected(self):
        rank, _, _, _ = native.fixture("rank-views")
        lazy, _, bad, _ = native.fixture("lazy-payloads")
        self.assertEqual(actions(rank).count("Rank.mapRank "), 9)
        self.assertEqual(actions(rank).count("Rank.setRank "), 9)
        self.assertEqual(actions(rank).count("Rank.mapSelect "), 7)
        self.assertEqual(actions(rank).count("Rank.setSelect "), 7)
        self.assertEqual(actions(lazy).count("Rank."), 6)  # three view + index constructors
        for marker in ("unselected-payload", "unselected-right", "unselected-map"):
            self.assertIn(marker, lazy)
        self.assertIn('putStrLn "before"', bad)
        self.assertIn('panic "selected-payload"', bad)

    def test_default_runtime_command_is_unchanged(self):
        source, output = Path("/checkout"), Path("/output/runtime.o")
        self.assertEqual(native.runtime_build_command("/usr/bin/clang", source, output, ["-I/gc/include"]),
            ["/usr/bin/clang", "-O2", "-std=c11", "-I/gc/include", "-I/checkout/runtime",
             "-c", source/"runtime/mlf_runtime.c", "-o", output])

    def test_explicit_runtime_input_keeps_sealed_header_root(self):
        source, output, runtime = Path("/sealed/source"), Path("/output/runtime.o"), Path("/inputs/runtime.c")
        command = native.runtime_build_command("/toolchain/clang", source, output, [], runtime)
        self.assertEqual(command, ["/toolchain/clang", "-O2", "-std=c11",
            "-I/sealed/source/runtime", "-c", runtime, "-o", output])

    def test_unknown_batch_fails_closed(self):
        for name in ("", "missing", "standalone-good"):
            with self.assertRaisesRegex(ValueError, "unknown native fixture batch"):
                native.fixture(name)

if __name__ == "__main__":
    unittest.main()
