"""Black-box resolver tests against the native MLF package manager."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
MANAGER = os.environ.get("MLF_PACKAGE_MANAGER", str(ROOT / "mlfpkg"))


def directory_alias(alias, target):
    if os.name == "nt":
        host = os.environ.get("MLF_WINDOWS_HOST", str(Path(MANAGER).parent / "mlf-host.exe"))
        subprocess.run([host, "link", "-s", str(target), str(alias)], check=True)
    else:
        alias.symlink_to(target, target_is_directory=True)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mlf package resolver ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def package(self, name, *, deps=None, module=None, imports="", **extra):
        root = self.root / name
        root.mkdir(exist_ok=True)
        module = module or name.title().replace("-", "")
        (root / "Source.emlf").write_text(f"module {module} where\n{imports}\nvalue = 1\n")
        data = {"format": 1, "name": name, "version": "0.1.0", "library": {"modules": {module: "Source.emlf"}}, **extra}
        if deps:
            data["dependencies"] = {n: {"path": p} for n, p in deps.items()}
        path = root / "mlf-package.json"
        path.write_text(json.dumps(data))
        return path

    def modify(self, path, edit):
        data = json.loads(path.read_text())
        edit(data)
        path.write_text(json.dumps(data))

    def run_manager(self, path, *args, error=None):
        result = subprocess.run([MANAGER, "--manifest", str(path), *args], capture_output=True, text=True, encoding="utf-8", timeout=60)
        if error is None:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, "invalid package succeeded")
            self.assertRegex(result.stderr, error)
        return result

    def plan(self, path, error=None):
        result = self.run_manager(path, "plan", error=error)
        return json.loads(result.stdout) if error is None else None

    def test_transitive_diamond_is_resolved_once(self):
        self.package("base")
        self.package("left", deps={"base": "../base"}, imports="import Base")
        self.package("right", deps={"base": "../base"}, imports="import Base")
        root = self.package("top", deps={"left": "../left", "right": "../right"}, imports="import Left\nimport Right")
        graph = self.plan(root)
        self.assertEqual([p["name"] for p in graph["packages"]], ["base", "left", "right", "top"])
        self.assertEqual(graph["modules"], ["Base", "Left", "Right", "Top"])

    def test_dependency_cycle_reports_chain(self):
        a = self.package("a", deps={"b": "../b"})
        self.package("b", deps={"a": "../a"})
        self.plan(a, r"dependency cycle:.*a.*b.*a")

    def test_symlink_dependency_cycle(self):
        a = self.package("a", deps={"a": "../alias"})
        directory_alias(self.root / "alias", a.parent)
        self.plan(a, "dependency cycle")

    def test_missing_dependency_and_identity(self):
        a = self.package("a", deps={"b": "../b"})
        self.plan(a, "canonical path|missing")
        self.package("b")
        self.modify(a, lambda d: d.update(dependencies={"wrong": {"path": "../b"}}))
        self.plan(a, "resolves to package b")

    def test_duplicate_module_and_package(self):
        self.package("a", module="Shared")
        b = self.package("b", module="Shared", deps={"a": "../a"})
        self.plan(b, "multiple packages")
        self.modify(b, lambda d: d.update(name="a"))
        self.plan(b, "multiple local paths")

    def test_direct_dependency_visibility(self):
        self.package("base")
        self.package("mid", deps={"base": "../base"}, imports="import Base")
        root = self.package("top", deps={"mid": "../mid"}, imports="import Base")
        self.plan(root, "not declared.*direct dependency")

    def test_module_cycle(self):
        root = self.package("a", imports="import B")
        (root.parent / "B.emlf").write_text("module B where\nimport A\ny = 2\n")
        self.modify(root, lambda d: d["library"]["modules"].update(B="B.emlf"))
        self.plan(root, "module cycle: A -> B -> A")

    def test_manifest_module_identity(self):
        root = self.package("a")
        self.modify(root, lambda d: d.update(library={"modules": {"Other": "Source.emlf"}}))
        self.plan(root, "manifest declares Other, source declares A")

    def test_source_escape_and_symlink(self):
        root = self.package("a")
        (self.root / "Outside.emlf").write_text("module A where\nx = 1\n")
        if os.name == "nt":
            directory_alias(root.parent / "link-directory", self.root)
            alias_source = "link-directory/Outside.emlf"
        else:
            (root.parent / "link.emlf").symlink_to(self.root / "Outside.emlf")
            alias_source = "link.emlf"
        for name in ("../Outside.emlf", alias_source):
            self.modify(root, lambda d: d.update(library={"modules": {"A": name}}))
            self.plan(root, "outside package")

    def test_lock_tracks_content(self):
        root = self.package("a")
        before = self.plan(root)
        source = root.parent / "Source.emlf"
        source.write_text(source.read_text().replace("1", "2"))
        self.assertNotEqual(before, self.plan(root))
        self.run_manager(root, "lock")
        self.run_manager(root, "--locked", "plan")
        source.write_text(source.read_text().replace("2", "3"))
        self.run_manager(root, "--locked", "plan", error="mlf.lock is stale")

    def test_unknown_and_duplicate_fields(self):
        root = self.package("a")
        self.modify(root, lambda d: d.update(dependecies={}))
        self.plan(root, "unknown field")
        root.write_text('{"name":"a","name":"b"}')
        self.plan(root, "duplicate JSON key")

    def test_invalid_manifest_shapes(self):
        for edit in (lambda d: d.update(format=True), lambda d: d.update(executables={"a": None}),
                     lambda d: d.update(tests={"a": {"command": []}}),
                     lambda d: d.update(tests={"a": {"main": "Source.emlf"}}),
                     lambda d: d.update(dependencies={"remote": {"url": "https://invalid.example"}})):
            root = self.package("a")
            self.modify(root, edit)
            self.plan(root, ".+")

    def test_real_parser_handles_multiline_imports_and_comments(self):
        self.package("base", module="Real.Library")
        root = self.package("a", deps={"base": "../base"})
        (root.parent / "Source.emlf").write_text('''{- module Fake where {- import Missing -} -}
module A where {
import
 qualified
 Real.Library
 as Alias (value);
-- import Ignored
value = "import Not.Real" }
''')
        self.assertEqual(self.plan(root)["modules"], ["Real.Library", "A"])

    def test_truncated_source_rejected(self):
        root = self.package("a")
        for source in ("{- open {- nested -}", 'module A where\nvalue = "open'):
            (root.parent / "Source.emlf").write_text(source)
            self.plan(root, "unexpected|unterminated")

    def test_json_unicode_and_invalid_tokens(self):
        root = self.package("a")
        # Unicode paths include a non-BMP scalar encoded as JSON surrogate pairs.
        (root.parent / "Source.emlf").rename(root.parent / "λ😀.emlf")
        self.modify(root, lambda d: d["library"]["modules"].update(A="λ😀.emlf"))
        self.assertIn("λ😀.emlf", self.plan(root)["packages"][0]["sources"])
        for text in ('{"format":1,}', '{"format":01}', '{"name":"\\ud800"}', '[true,]'):
            root.write_text(text)
            self.plan(root, "invalid JSON")


if __name__ == "__main__":
    unittest.main()
