#!/usr/bin/env python3
"""Tiny self-created fixtures only. Never use a real archive, toolchain or cache."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HELPER = Path(__file__).with_name("cleanup-ghc-install.py")
spec = importlib.util.spec_from_file_location("ghc_install_cleanup", HELPER)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


class CleanupTests(unittest.TestCase):
    def setUp(self):
        # All writes/deletions are confined to this fresh, tiny test fixture.
        self.temporary = tempfile.TemporaryDirectory(prefix="ghc-cleanup-test-", dir=Path.cwd())
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.root = self.home / "runner-temp"
        self.root.mkdir()
        self.archive = self.root / cleanup.ARCHIVE
        self.archive.write_bytes(b"synthetic pinned archive\n")
        self.staging = self.root / cleanup.STAGING
        self.staging.mkdir()
        (self.staging / "configure").write_text("synthetic install input\n")
        self.prefix = self.root / "ghc"
        self.bin = self.prefix / "bin"
        self.bin.mkdir(parents=True)
        self.lib = self.prefix / "lib" / "ghc-9.14.1"
        self.db = self.lib / "package.conf.d"
        self.db.mkdir(parents=True)
        (self.lib / "settings").write_text("[]\n")
        (self.db / "package.cache").write_bytes(b"synthetic cache\n")
        (self.db / "base.conf").write_text(f"name: base\nimport-dirs: {self.lib}\n")
        self.write_executable("ghc", f'''#!/bin/sh
test "$GHC_ENVIRONMENT" = - && test -z "${{GHC_PACKAGE_PATH+x}}" || exit 8
case "$*" in
  --numeric-version) printf '9.14.1\\n';;
  --print-libdir) printf '%s\\n' '{self.lib}';;
  --info) printf '[("Project version","9.14.1")]\\n';;
  *) exit 9;;
esac
''')
        self.write_executable("ghc-pkg", f'''#!/bin/sh
test "$GHC_ENVIRONMENT" = - && test -z "${{GHC_PACKAGE_PATH+x}}" || exit 8
case "$*" in
  '--global-package-db={self.db} --global --no-user-package-db list --simple-output')
    printf 'ghc-9.14.1 base-4.22.0.0\\n';;
  '--global-package-db={self.db} --global --no-user-package-db dump --expand-pkgroot')
    printf 'name: base\\nimport-dirs: {self.lib}\\n';;
  '--global-package-db={self.db} --global --no-user-package-db check') :;;
  *) exit 9;;
esac
''')
        self.other = self.root / "cache-preserve"
        self.other.write_bytes(b"unrelated evidence must survive\n")
        self.outside = self.home / "outside-preserve"
        self.outside.write_bytes(b"outside target must survive\n")
        self.receipt = {}
        self.events = []
        self.pin = mock.patch.object(cleanup, "SHA256", hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.environment = mock.patch.dict(os.environ, {
            "GHC_PACKAGE_PATH": "/must/not/be/read", "GHC_ENVIRONMENT": "/must/not/be/read"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def write_executable(self, name, text):
        file = self.bin / name
        file.write_text(text)
        file.chmod(0o755)

    def save(self):
        self.events.append(json.loads(json.dumps(self.receipt)))

    def run_cleanup(self):
        cleanup.cleanup(self.root, self.receipt, self.save)

    def assert_preserved(self):
        self.assertEqual(self.other.read_bytes(), b"unrelated evidence must survive\n")
        self.assertEqual(self.outside.read_bytes(), b"outside target must survive\n")
        self.assertTrue((self.bin / "ghc").is_file())
        self.assertTrue((self.lib / "settings").is_file())

    def refuse(self, pattern):
        with self.assertRaisesRegex((RuntimeError, OSError), pattern):
            self.run_cleanup()
        self.assertTrue(os.path.lexists(self.archive))
        self.assertTrue(os.path.lexists(self.staging))
        self.assertFalse(self.receipt.get("cleanup_started", False))
        self.assert_preserved()

    def test_success_preserves_install_and_every_unrelated_file(self):
        (self.staging / "configure-alias").symlink_to("configure")
        (self.bin / "ghc-alias").symlink_to("ghc")
        self.run_cleanup()
        self.assertEqual(self.receipt["status"], "complete")
        self.assertEqual(set(self.receipt["removed"]), {str(self.archive), str(self.staging)})
        self.assertFalse(self.archive.exists())
        self.assertFalse(self.staging.exists())
        self.assertEqual(self.receipt["installed_before"], self.receipt["installed_after"])
        self.assertTrue(cleanup.same_installed_tree(
            self.receipt["installed_tree_before"], self.receipt["installed_tree_after"]))
        self.assertGreater(self.receipt["installed_tree_before"]["runtime_files_scanned"], 3)
        self.assertIn("validated", [event.get("status") for event in self.events])
        self.assertIsInstance(self.receipt["free_bytes_after"], int)
        self.assert_preserved()


    def test_allocation_only_changes_are_recorded_but_not_identity_changes(self):
        original = cleanup.tree_snapshot
        snapshots = []
        def snapshot(root, device, installed=False):
            value = original(root, device, installed=installed)
            if installed:
                value["allocated_bytes"] = 4096 * (len(snapshots) + 1)
                snapshots.append(dict(value))
            return value
        with mock.patch.object(cleanup, "tree_snapshot", side_effect=snapshot):
            self.run_cleanup()
        self.assertEqual(len(snapshots), 3)
        self.assertEqual(self.receipt["status"], "complete")
        self.assertEqual(self.receipt["installed_tree_before"], snapshots[0])
        self.assertEqual(self.receipt["installed_tree_after"], snapshots[2])
        self.assertEqual(snapshots[0]["allocated_bytes"], 4096)
        self.assertEqual(snapshots[1]["allocated_bytes"], 8192)
        self.assertEqual(snapshots[2]["allocated_bytes"], 12288)
        self.assertEqual(set(self.receipt["removed"]), {str(self.archive), str(self.staging)})
        self.assertFalse(self.archive.exists())
        self.assertFalse(self.staging.exists())
        self.assertEqual(self.receipt["installed_before"], self.receipt["installed_after"])
        self.assert_preserved()

    def test_only_allocation_statistic_is_ignored(self):
        before = {"sha256": "a" * 64, "entries": 7,
                  "allocated_bytes": 4096, "runtime_files_scanned": 4}
        self.assertTrue(cleanup.same_installed_tree(before, dict(before)))
        self.assertTrue(cleanup.same_installed_tree(
            before, {**before, "allocated_bytes": 8192}))
        for field, value in (("sha256", "b" * 64), ("entries", 8),
                             ("runtime_files_scanned", 5), ("future_identity_field", True)):
            with self.subTest(field=field):
                changed = {**before, field: value, "allocated_bytes": 8192}
                self.assertFalse(cleanup.same_installed_tree(before, changed))
                self.assertFalse(cleanup.same_installed_tree(changed, before))
        for field in ("sha256", "entries", "runtime_files_scanned"):
            changed = dict(before)
            del changed[field]
            with self.subTest(missing=field):
                self.assertFalse(cleanup.same_installed_tree(before, changed))

    def test_actual_identity_changes_remain_detected(self):
        # No production tree is touched. Each subcase changes one fresh fixture.
        nonruntime = self.lib / "ordinary-data"
        runtime = self.lib / "settings"
        nonruntime.write_bytes(b"ordinary data\n")
        alias = self.prefix / "settings-alias"
        alias.symlink_to(runtime.relative_to(self.prefix))
        device = self.prefix.stat().st_dev
        def changed(action):
            before = cleanup.tree_snapshot(self.prefix, device, installed=True)
            action()
            after = cleanup.tree_snapshot(self.prefix, device, installed=True)
            self.assertFalse(cleanup.same_installed_tree(before, after))
        changed(lambda: nonruntime.write_bytes(b"modified data\n"))
        changed(lambda: runtime.write_bytes(b"{}\n"))
        changed(lambda: nonruntime.chmod(0o600))
        added = self.prefix / "added"
        changed(lambda: added.write_bytes(b"new\n"))
        changed(added.unlink)
        renamed = self.lib / "renamed-data"
        changed(lambda: nonruntime.rename(renamed))
        replacement = self.home / "replacement"
        replacement.write_bytes(renamed.read_bytes())
        replacement.chmod(renamed.stat().st_mode & 0o777)
        self.assertNotEqual(replacement.stat().st_ino, renamed.stat().st_ino)
        changed(lambda: replacement.replace(renamed))
        def to_directory():
            renamed.unlink()
            renamed.mkdir()
        changed(to_directory)
        def retarget():
            alias.unlink()
            alias.symlink_to((self.db / "base.conf").relative_to(self.prefix))
        changed(retarget)

    def test_installed_change_during_validation_refuses_before_deletion(self):
        original = cleanup.installed_check
        def checked(prefix):
            result = original(prefix)
            (self.lib / "settings").write_text("changed during validation\n")
            return result
        with mock.patch.object(cleanup, "installed_check", side_effect=checked):
            self.refuse("Installed files changed during validation")

    def test_installed_change_after_deletion_is_reported_as_incomplete(self):
        original = cleanup.installed_check
        def checked(prefix):
            result = original(prefix)
            if not self.staging.exists():
                (self.lib / "settings").write_text("changed after cleanup\n")
            return result
        with mock.patch.object(cleanup, "installed_check", side_effect=checked):
            with self.assertRaisesRegex(RuntimeError, "Installed files changed after cleanup"):
                self.run_cleanup()
        self.assertTrue(self.receipt["cleanup_started"])
        self.assertNotEqual(self.receipt["status"], "complete")
        self.assertEqual(set(self.receipt["removed"]), {str(self.archive), str(self.staging)})
        self.assertFalse(self.archive.exists())
        self.assertFalse(self.staging.exists())
        self.assert_preserved()

    def test_bad_archive_pin(self):
        self.archive.write_bytes(b"tampered archive\n")
        self.refuse("SHA256 mismatch")

    def test_archive_symlink(self):
        self.archive.unlink()
        self.archive.symlink_to(self.outside)
        self.refuse("owned, singly linked regular")

    def test_archive_hardlink(self):
        os.link(self.archive, self.home / "archive-alias")
        self.refuse("owned, singly linked regular")

    def test_missing_exact_archive_basename(self):
        self.archive.rename(self.root / "ghc-other.tar.xz")
        with self.assertRaises(FileNotFoundError):
            self.run_cleanup()
        self.assertTrue(self.staging.exists())
        self.assertTrue((self.root / "ghc-other.tar.xz").exists())
        self.assert_preserved()

    def test_root_symlink(self):
        alias = self.home / "alias"
        alias.symlink_to(self.root, target_is_directory=True)
        self.root = alias
        self.refuse("Symlink or noncanonical")

    def test_staging_root_symlink(self):
        original = self.root / "unrelated-staging"
        self.staging.rename(original)
        self.staging.symlink_to(original, target_is_directory=True)
        self.refuse("Symlink or noncanonical")

    def test_writable_by_others(self):
        self.root.chmod(0o777)
        self.refuse("writable by other users")

    def test_escape_symlinks_in_either_tree(self):
        for tree in (self.staging, self.prefix):
            with self.subTest(tree=tree.name):
                link = tree / "escaping-link"
                link.symlink_to(self.outside)
                self.refuse("Symlink escapes")
                link.unlink()

    def test_installed_symlink_back_to_staging(self):
        (self.prefix / "back-link").symlink_to(self.staging / "configure")
        self.refuse("Symlink escapes")

    def test_special_staging_entry(self):
        os.mkfifo(self.staging / "pipe")
        self.refuse("Special file")

    def test_nested_bind_mount_even_on_same_device(self):
        mount = str(self.staging / "nested mount").replace(" ", "\\040")
        with mock.patch.object(Path, "read_text", return_value=f"1 0 8:1 / {mount} rw - ext4 /dev/root rw\n"):
            self.refuse("Mount inside")

    def test_cross_device_entry(self):
        with self.assertRaisesRegex(RuntimeError, "Cross-device"):
            cleanup.tree_snapshot(self.staging, self.staging.stat().st_dev + 1)
        self.assertTrue(self.archive.exists())
        self.assert_preserved()

    def test_runtime_reference_in_wrappers_settings_and_package_files(self):
        for file in (self.bin / "ghc", self.lib / "settings", self.db / "base.conf", self.db / "package.cache"):
            with self.subTest(file=file.name):
                original = file.read_bytes()
                file.write_bytes(original + str(self.staging).encode())
                self.refuse("Installed staging reference")
                file.write_bytes(original)

    def test_runtime_reference_across_read_chunk_boundary(self):
        file = self.lib / "settings"
        # Shrink the helper's input chunks with an in-memory reader instead of
        # creating a megabyte fixture; the full data still fits below 100 bytes.
        original_open = Path.open
        data = b"x" + cleanup.STAGING.encode() + b"\n"
        class SmallReads:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def read(self, size):
                return self.stream.read(min(size, 8))
            def seek(self, offset):
                return self.stream.seek(offset)
        def opened(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return SmallReads(stream) if path == file else stream
        file.write_bytes(data)
        with mock.patch.object(Path, "open", opened):
            self.refuse("Installed staging reference")

    def test_incomplete_install(self):
        (self.db / "package.cache").unlink()
        self.refuse("package database incomplete")

    def test_wrong_version(self):
        self.write_executable("ghc", "#!/bin/sh\nprintf '0.0.0\\n'\n")
        self.refuse("Unexpected installed GHC version")

    def test_libdir_outside_prefix(self):
        original = cleanup.command
        def command(prefix, executable, *args):
            if args == ("--print-libdir",):
                return str(self.home)
            return original(prefix, executable, *args)
        with mock.patch.object(cleanup, "command", side_effect=command):
            self.refuse("libdir is outside")

    def test_missing_core_packages(self):
        original = cleanup.command
        def command(prefix, executable, *args):
            if args[-1] == "--simple-output":
                return "base-4.22.0.0"
            return original(prefix, executable, *args)
        with mock.patch.object(cleanup, "command", side_effect=command):
            self.refuse("ghc/base packages missing")

    def test_package_integrity_failure(self):
        original = cleanup.command
        def command(prefix, executable, *args):
            if args[-1] == "check":
                raise RuntimeError("synthetic broken package")
            return original(prefix, executable, *args)
        with mock.patch.object(cleanup, "command", side_effect=command):
            self.refuse("broken package")

    def test_staging_changed_after_validation(self):
        def save():
            self.save()
            if self.receipt.get("status") == "validated":
                (self.staging / "new-file").write_text("concurrent change\n")
        with self.assertRaisesRegex(RuntimeError, "Staging changed"):
            cleanup.cleanup(self.root, self.receipt, save)
        self.assertTrue(self.archive.exists())
        self.assertTrue(self.staging.exists())
        self.assertFalse(self.receipt.get("cleanup_started", False))

    def test_post_cleanup_checks_are_required(self):
        original = cleanup.installed_check
        def checked(prefix):
            if not self.staging.exists():
                raise RuntimeError("synthetic post-cleanup failure")
            return original(prefix)
        with mock.patch.object(cleanup, "installed_check", side_effect=checked):
            with self.assertRaisesRegex(RuntimeError, "post-cleanup failure"):
                self.run_cleanup()
        self.assertNotEqual(self.receipt["status"], "complete")
        self.assert_preserved()

    def test_cli_retains_refusal_receipt_and_never_accepts_test_pin(self):
        output = self.home / "receipt.json"
        env = dict(os.environ, RUNNER_TEMP=str(self.root))
        flags = ["-O"] if sys.flags.optimize else []
        result = subprocess.run([sys.executable, "-B", *flags, str(HELPER), "--receipt", str(output)],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        receipt = json.loads(output.read_text())
        self.assertEqual(receipt["status"], "refused")
        self.assertIn("SHA256 mismatch", receipt["reason"])
        self.assertEqual(receipt["removed"], [])
        self.assertEqual(receipt["download_url"], cleanup.URL)
        self.assertTrue(self.archive.exists())
        self.assertTrue(self.staging.exists())
        self.assert_preserved()


if __name__ == "__main__":
    unittest.main()
