#!/usr/bin/env python3
"""Offline end-to-end contracts for the explicitly pinned seed transport."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import tarfile
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
FETCH = ROOT / "tools/release/fetch-seed.sh"
SOURCE = "ad299fa17296945ca0cf34d6fc4ac35dc5eb0924"
RUN = 39712937640
REPOSITORY_ID = 1420436874
MOCK_GH = '''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["TEST_SEED_FIXTURES"])
args = sys.argv[1:]
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps(args) + "\\n")
if args == ["api", "--help"]:
    print("--allow-escape-sequences" if os.environ.get("TEST_GH_LEGACY") != "1" else "old gh")
    sys.exit(0)
if args[:2] == ["release", "download"]:
    sys.exit(23)
assert args[:3] == ["api", "--hostname", "github.com"], args
endpoint = args[3]
assert endpoint.startswith("repos/mlf-lang/mlf/actions/"), args
kind = "zip" if endpoint.endswith("/zip") else "run" if "/runs/" in endpoint else "artifact"
if os.environ.get("TEST_GH_FAIL") == kind:
    print("mock GitHub resource unavailable", file=sys.stderr)
    sys.exit(22)
file = "artifact.zip" if kind == "zip" else kind + ".json"
sys.stdout.buffer.write((root / file).read_bytes())
'''


def digest(data):
    return hashlib.sha256(data).hexdigest()


class ArtifactSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="mlf-seed-contract-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        binary = self.root / "bin"
        binary.mkdir()
        (binary / "gh").write_text(MOCK_GH)
        (binary / "gh").chmod(0o755)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("MLF_SEED_")}
        self.env.update(PATH=f"{binary}:{os.environ['PATH']}", TEST_SEED_FIXTURES=str(self.root),
                        GITHUB_REPOSITORY="untrusted/fork", GH_HOST="example.invalid")
        self.counter = 0
        self.prepare()

    def prepare(self, platform="linux-x64"):
        self.package = f"mlf-0.3.0-{platform}"
        self.archive = f"{self.package}.tar.gz"
        artifact_id = 12402192066 if platform == "linux-x64" else 12401994144
        self.pins = dict(MLF_SEED_TRANSPORT="github-actions-artifact", MLF_SEED_PLATFORM=platform,
                         MLF_SEED_VERSION="0.3.0", MLF_SEED_SOURCE_COMMIT=SOURCE,
                         MLF_SEED_ARTIFACT_RUN_ID=str(RUN), MLF_SEED_ARTIFACT_ID=str(artifact_id),
                         MLF_SEED_ARTIFACT_NAME=f"release-{platform}")
        self.run = dict(id=RUN, name="Cross-platform release", path=".github/workflows/platform-release.yml",
                        status="completed", conclusion="success",
                        head_sha=SOURCE, repository=dict(id=REPOSITORY_ID, full_name="mlf-lang/mlf"),
                        head_repository=dict(id=REPOSITORY_ID, full_name="mlf-lang/mlf"))
        self.artifact = dict(id=artifact_id, name=f"release-{platform}", expired=False,
                             expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                             workflow_run=dict(id=RUN, head_sha=SOURCE, repository_id=REPOSITORY_ID, head_repository_id=REPOSITORY_ID))
        self.members = {"COMMIT": f"{SOURCE}\n".encode(), "libexec/emlf": b"compiler bytes\n",
                        "libexec/mlfpkg": b"manager bytes\n"}
        self.pins["MLF_SEED_COMPILER_SHA256"] = digest(self.members["libexec/emlf"])
        self.pins["MLF_SEED_MANAGER_SHA256"] = digest(self.members["libexec/mlfpkg"])
        self.repack()

    def repack(self):
        packed = io.BytesIO()
        with tarfile.open(fileobj=packed, mode="w:gz") as bundle:
            for name, value in self.members.items():
                entry = tarfile.TarInfo(f"{self.package}/{name}")
                entry.size = len(value)
                entry.mode = 0o755 if name.startswith("libexec/") else 0o644
                bundle.addfile(entry, io.BytesIO(value))
        self.original = packed.getvalue()
        self.pins["MLF_SEED_ARCHIVE_SHA256"] = digest(self.original)
        self.set_zip([(self.archive, self.original)])

    def set_zip(self, entries):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
                for name, value in entries:
                    bundle.writestr(name, value)
        self.set_raw_zip(buffer.getvalue())

    def set_raw_zip(self, data):
        self.zipped = data
        self.pins["MLF_SEED_ARTIFACT_SHA256"] = digest(data)
        self.artifact["digest"] = f"sha256:{digest(data)}"

    def invoke(self, success=False, error=None):
        self.counter += 1
        output = self.root / f"destination {self.counter}"
        env_file = self.root / f"github-env-{self.counter}"
        env_file.write_text("EXISTING=value\n")
        pin = self.root / "pin.env"
        pin.write_text("".join(f"{key}={shlex.quote(value)}\n" for key, value in self.pins.items()))
        (self.root / "run.json").write_text(json.dumps(self.run))
        (self.root / "artifact.json").write_text(json.dumps(self.artifact))
        (self.root / "artifact.zip").write_bytes(self.zipped)
        self.calls_file = self.root / "calls.jsonl"
        self.calls_file.write_text("")
        result = subprocess.run([str(FETCH), str(output), str(pin)], cwd=ROOT,
                                env={**self.env, "GITHUB_ENV": str(env_file)}, text=True, capture_output=True)
        self.calls = [json.loads(line) for line in self.calls_file.read_text().splitlines()]
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines()[-1], str(output / self.package))
            self.assertEqual(env_file.read_text(), "EXISTING=value\n"
                             f"MLF_COMPILER={output / self.package}/libexec/emlf\n"
                             f"MLF_PACKAGE_MANAGER={output / self.package}/libexec/mlfpkg\n")
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(env_file.read_text(), "EXISTING=value\n", result.stderr)
            self.assertNotIn(str(output / self.package), result.stdout)
            self.assertNotIn("MLF_COMPILER=", result.stdout)
            if error:
                self.assertIn(error, result.stderr)
        return output, result

    def test_original_bytes_both_platforms_and_default_macos(self):
        for platform in ("linux-x64", "macos-arm64"):
            with self.subTest(platform=platform):
                self.prepare(platform)
                if platform == "macos-arm64":
                    del self.pins["MLF_SEED_PLATFORM"]
                    self.env["TEST_GH_LEGACY"] = "1"
                output, result = self.invoke(success=True)
                self.assertEqual((output / self.archive).read_bytes(), self.original)
                sums = (output / "SHA256SUMS").read_text()
                self.assertIn("Derived from the reviewed MLF_SEED_ARCHIVE_SHA256 pin; not a release asset", sums)
                self.assertIn(f"{digest(self.original)}  {self.archive}\n", sums)
                self.assertIn("SHA256SUMS is derived", result.stderr)
                self.assertEqual(list(output.glob(".seed-artifact-*")), [])
                endpoints = [call[3] for call in self.calls if call != ["api", "--help"]]
                self.assertEqual(endpoints, [f"repos/mlf-lang/mlf/actions/runs/{RUN}",
                                 f"repos/mlf-lang/mlf/actions/artifacts/{self.artifact['id']}",
                                 f"repos/mlf-lang/mlf/actions/artifacts/{self.artifact['id']}/zip"])
                self.assertEqual("--allow-escape-sequences" in self.calls[-1], platform == "linux-x64")

    def test_reject_run_metadata_before_download(self):
        original = deepcopy(self.run)
        cases = [("id", RUN + 1), ("name", "Unrelated build"), ("path", ".github/workflows/other.yml"),
                 ("status", "in_progress"),
                 ("conclusion", "failure"), ("conclusion", None), ("head_sha", "0" * 40),
                 ("repository", dict(id=REPOSITORY_ID, full_name="other/mlf")),
                 ("head_repository", dict(id=REPOSITORY_ID, full_name="other/mlf")),
                 ("head_repository", dict(id=456, full_name="mlf-lang/mlf")),
                 ("repository", dict(id=456, full_name="mlf-lang/mlf")),
                 ("repository", {}), ("repository", None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.run = {**deepcopy(original), field: value}
                self.invoke()
                self.assertEqual(len(self.calls), 1)

    def test_consistently_changed_repository_id_rejected(self):
        # Matching names and internally consistent IDs cannot replace the pinned repository.
        self.run["repository"]["id"] = 456
        self.run["head_repository"]["id"] = 456
        self.artifact["workflow_run"]["repository_id"] = 456
        self.artifact["workflow_run"]["head_repository_id"] = 456
        self.invoke(error="workflow repository ID mismatch")
        self.assertEqual(len(self.calls), 1)

    def test_reject_artifact_metadata_before_download(self):
        original = deepcopy(self.artifact)
        cases = [("id", 1), ("name", "other-name"), ("digest", "sha256:" + "0" * 64),
                 ("digest", None), ("expired", True), ("expired", "false"),
                 ("expires_at", "2000-01-01T00:00:00Z"), ("expires_at", ""),
                 ("expires_at", "3000-01-01T00:00:00"), ("expires_at", None)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.artifact = {**deepcopy(original), field: value}
                self.invoke()
                self.assertEqual(len(self.calls), 2)
        for field, value in (("id", RUN + 1), ("head_sha", "0" * 40),
                             ("repository_id", 456), ("head_repository_id", 456)):
            with self.subTest(workflow_field=field):
                self.artifact = deepcopy(original)
                self.artifact["workflow_run"][field] = value
                self.invoke()
                self.assertEqual(len(self.calls), 2)
        for field in original:
            with self.subTest(missing=field):
                self.artifact = deepcopy(original)
                del self.artifact[field]
                self.invoke()
                self.assertEqual(len(self.calls), 2)

    def test_missing_or_invalid_pins_never_download(self):
        original = self.pins.copy()
        required = ("SOURCE_COMMIT", "ARCHIVE_SHA256", "COMPILER_SHA256", "MANAGER_SHA256",
                    "ARTIFACT_RUN_ID", "ARTIFACT_ID", "ARTIFACT_NAME", "ARTIFACT_SHA256")
        for field in required:
            with self.subTest(missing=field):
                self.pins = original.copy()
                del self.pins[f"MLF_SEED_{field}"]
                self.invoke()
                self.assertEqual(self.calls, [])
        for field in ("SOURCE_COMMIT", "ARCHIVE_SHA256", "ARTIFACT_RUN_ID", "ARTIFACT_ID",
                      "ARTIFACT_NAME", "ARTIFACT_SHA256", "VERSION", "PLATFORM", "TRANSPORT"):
            with self.subTest(invalid=field):
                self.pins = {**original, f"MLF_SEED_{field}": "invalid"}
                self.invoke()
                self.assertEqual(self.calls, [])

    def test_missing_remote_resources_do_not_fall_back(self):
        for kind in ("run", "artifact", "zip"):
            with self.subTest(kind=kind):
                self.env["TEST_GH_FAIL"] = kind
                self.invoke(error="mock GitHub resource unavailable")
                self.assertTrue(all(call[0] == "api" for call in self.calls))

    def test_release_failure_does_not_try_artifacts(self):
        for explicit in (False, True):
            with self.subTest(explicit=explicit):
                if explicit:
                    self.pins["MLF_SEED_TRANSPORT"] = "release"
                else:
                    self.pins.pop("MLF_SEED_TRANSPORT", None)
                self.invoke()
                self.assertEqual(len(self.calls), 1)
                self.assertEqual(self.calls[0][:2], ["release", "download"])

    def test_outer_digest_precedes_zip_parsing(self):
        self.zipped = b"not even a ZIP; do not parse unauthenticated bytes"
        output, _ = self.invoke(error="artifact ZIP digest mismatch")
        self.assertFalse((output / self.archive).exists())

    def test_reject_unsafe_or_ambiguous_zip(self):
        link = zipfile.ZipInfo(self.archive)
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        fifo = zipfile.ZipInfo(self.archive)
        fifo.create_system = 3
        fifo.external_attr = (stat.S_IFIFO | 0o600) << 16
        cases = {"empty": [], "extra": [(self.archive, self.original), ("extra", b"extra")],
                 "duplicate": [(self.archive, self.original)] * 2,
                 "directory": [(self.archive + "/", b"")],
                 "traversal": [("../" + self.archive, self.original)],
                 "absolute": [("/" + self.archive, self.original)],
                 "nested": [("dir/" + self.archive, self.original)],
                 "backslash": [("dir\\" + self.archive, self.original)],
                 "wrong": [("other.tar.gz", self.original)],
                 "symlink": [(link, b"outside")], "fifo": [(fifo, b"")]}
        for name, entries in cases.items():
            with self.subTest(layout=name):
                self.set_zip(entries)
                output, _ = self.invoke()
                self.assertFalse((output / self.archive).exists())
        self.set_raw_zip(b"invalid ZIP with correctly pinned outer digest")
        self.invoke(error="File is not a zip file")

    def test_encrypted_zip_rejected(self):
        data = bytearray(self.zipped)
        for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
            position = data.index(signature) + offset
            data[position] |= 1
        self.set_raw_zip(bytes(data))
        self.invoke(error="unencrypted regular file")

    def test_original_archive_bytes_and_remaining_pin_gates(self):
        self.set_zip([(self.archive, b"not the pinned original archive")])
        output, _ = self.invoke(error="original seed archive digest mismatch")
        self.assertFalse((output / self.archive).exists())
        for field in ("ARCHIVE_SHA256", "COMPILER_SHA256", "MANAGER_SHA256"):
            with self.subTest(pin=field):
                self.prepare()
                self.pins[f"MLF_SEED_{field}"] = "0" * 64
                self.invoke()
        self.prepare()
        self.members["COMMIT"] = b"wrong source commit\n"
        self.repack()
        self.invoke()
        for member in ("COMMIT", "libexec/emlf", "libexec/mlfpkg"):
            with self.subTest(missing_member=member):
                self.prepare()
                del self.members[member]
                self.repack()
                self.invoke()


if __name__ == "__main__":
    unittest.main()
