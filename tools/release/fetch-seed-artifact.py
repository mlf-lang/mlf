#!/usr/bin/env python3
"""Fetch explicitly pinned original seed bytes from a temporary Actions artifact.

This is a transport only: fetch-seed.sh retains the archive, COMMIT and executable
checks. SHA256SUMS here is derived from the reviewed archive pin, not downloaded
release metadata. There is deliberately no artifact discovery or fallback.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

REPOSITORY = "mlf-lang/mlf"
REPOSITORY_ID = 1420436874
WORKFLOW = "Cross-platform release"
WORKFLOW_PATH = ".github/workflows/platform-release.yml"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def api(endpoint):
    # Do not let GH_HOST or a fork's GITHUB_REPOSITORY change the source.
    return ["gh", "api", "--hostname", "github.com", f"repos/{REPOSITORY}/{endpoint}"]


def fetch(args):
    require(re.fullmatch(r"[1-9][0-9]*", args.run_id), "invalid artifact run pin")
    require(re.fullmatch(r"[1-9][0-9]*", args.artifact_id), "invalid artifact ID pin")
    require(re.fullmatch(r"[0-9a-f]{40}", args.source), "invalid source pin")
    for value in (args.sha256, args.archive_sha256):
        require(re.fullmatch(r"[0-9a-f]{64}", value), "invalid SHA-256 pin")
    archive = re.fullmatch(r"mlf-[0-9]+\.[0-9]+\.[0-9]+-(macos-arm64|linux-x64)\.tar\.gz", args.archive)
    require(archive is not None, "invalid seed archive name")
    require(args.name == f"release-{archive[1]}", "artifact name does not match seed platform")

    run = json.loads(subprocess.check_output(api(f"actions/runs/{args.run_id}")))
    require(run.get("id") == int(args.run_id), "workflow run ID mismatch")
    require(run.get("name") == WORKFLOW, "workflow name mismatch")
    require(run.get("path") == WORKFLOW_PATH, "workflow path mismatch")
    require(run.get("status") == "completed" and run.get("conclusion") == "success",
            "seed workflow run did not complete successfully")
    require(run.get("head_sha") == args.source, "workflow run source mismatch")
    repository = run.get("repository", {})
    head_repository = run.get("head_repository", {})
    require(repository.get("full_name") == REPOSITORY
            and head_repository.get("full_name") == REPOSITORY,
            "workflow repository mismatch")
    repository_id = repository.get("id")
    require(repository_id == REPOSITORY_ID
            and head_repository.get("id") == REPOSITORY_ID, "workflow repository ID mismatch")

    artifact = json.loads(subprocess.check_output(api(f"actions/artifacts/{args.artifact_id}")))
    require(artifact.get("id") == int(args.artifact_id), "artifact ID mismatch")
    require(artifact.get("name") == args.name, "artifact name mismatch")
    require(artifact.get("digest") == f"sha256:{args.sha256}", "artifact metadata digest mismatch")
    workflow = artifact.get("workflow_run", {})
    require(workflow.get("id") == int(args.run_id), "artifact workflow run mismatch")
    require(workflow.get("head_sha") == args.source, "artifact source mismatch")
    require(workflow.get("repository_id") == repository_id
            and workflow.get("head_repository_id") == repository_id, "artifact repository mismatch")
    require(artifact.get("expired") is False, "seed artifact is expired or expiry is missing")
    expires = datetime.fromisoformat(artifact.get("expires_at", "").replace("Z", "+00:00"))
    require(expires.tzinfo is not None and expires > datetime.now(timezone.utc),
            "seed artifact has expired")

    destination = Path(args.destination)
    require(not (destination / args.archive).exists() and not (destination / "SHA256SUMS").exists(),
            "seed archive or SHA256SUMS already exists")
    with tempfile.TemporaryDirectory(prefix=".seed-artifact-", dir=destination) as work:
        work = Path(work)
        zipped = work / "artifact.zip"
        command = api(f"actions/artifacts/{args.artifact_id}/zip")
        # Recent gh versions sanitize binary output unless explicitly allowed.
        help_text = subprocess.check_output(["gh", "api", "--help"], text=True)
        if "--allow-escape-sequences" in help_text:
            command.append("--allow-escape-sequences")
        with zipped.open("wb") as output:
            subprocess.run(command, stdout=output, check=True)
        # Authenticate the outer ZIP before opening it or reading its directory.
        require(sha256(zipped) == args.sha256, "artifact ZIP digest mismatch")
        with zipfile.ZipFile(zipped) as bundle:
            entries = bundle.infolist()
            require(len(entries) == 1, "artifact ZIP must contain exactly one seed archive")
            entry = entries[0]
            require(entry.filename == args.archive and entry.orig_filename == args.archive,
                    "unexpected artifact ZIP path")
            mode = stat.S_IFMT(entry.external_attr >> 16)
            require(mode in (0, stat.S_IFREG) and not entry.is_dir()
                    and not entry.flag_bits & 1, "artifact ZIP entry must be an unencrypted regular file")
            # Never extract paths supplied by the ZIP: write only the reviewed filename.
            original = work / args.archive
            with bundle.open(entry) as source, original.open("xb") as output:
                shutil.copyfileobj(source, output)
        require(sha256(original) == args.archive_sha256, "original seed archive digest mismatch")
        with original.open("rb") as source, (destination / args.archive).open("xb") as output:
            shutil.copyfileobj(source, output)
        with (destination / "SHA256SUMS").open("x") as output:
            output.write("# Derived from the reviewed MLF_SEED_ARCHIVE_SHA256 pin; not a release asset.\n")
            output.write(f"{args.archive_sha256}  {args.archive}\n")
    print(f"Verified temporary Actions artifact {args.artifact_id} from run {args.run_id}; "
          "SHA256SUMS is derived from the reviewed archive pin.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-id", "artifact-id", "name", "sha256", "source", "archive", "archive-sha256", "destination"):
        parser.add_argument(f"--{name}", required=True)
    try:
        fetch(parser.parse_args())
    except (ValueError, OSError, KeyError, TypeError, AttributeError, zipfile.BadZipFile,
            RuntimeError, NotImplementedError, subprocess.CalledProcessError) as error:
        print(f"Seed artifact transport failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
