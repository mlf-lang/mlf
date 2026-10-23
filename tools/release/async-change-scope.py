#!/usr/bin/env python3
"""Conservative PR-only selection for expensive async parity, never a test result.

The bootstrap snapshots all bootstrap/libraries/package/runtime inputs. The
parity scripts use their own async fixtures. None reads the independent trees
below. Unknown paths are intentionally treated as dependencies: adding a new
source location cannot silently opt out. Keep this allowlist narrow.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_DIFF_BYTES = 4 * 1024 * 1024
PROSE = {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE"}
INDEPENDENT = ("docs/", "papers/", "benchmarks/", "examples/")


def unrelated(path):
    # Do not normalize an ambiguous or unexpected path into an allowed one.
    if (not path or path.startswith("/") or "\\" in path
            or any(ord(c) < 32 or ord(c) == 127 for c in path)
            or any(part in ("", ".", "..") for part in path.split("/"))):
        return False
    return path in PROSE or path.startswith(INDEPENDENT)


def parse_diff(raw):
    if len(raw) > MAX_DIFF_BYTES:
        raise ValueError("diff exceeds the checked size bound")
    if raw and not raw.endswith(b"\0"):
        raise ValueError("incomplete NUL-delimited diff")
    fields = raw.decode("utf-8", errors="strict").split("\0")[:-1]
    if len(fields) % 2:
        raise ValueError("incomplete diff record")
    entries = []
    for status, path in zip(fields[::2], fields[1::2]):
        # --no-renames exposes both sides as delete/add, including moves out of
        # the allowlist. Type changes and unexpected statuses always run full.
        if status not in ("A", "M", "D") or not path:
            raise ValueError("unsupported diff record")
        entries.append({"status": status, "path": path})
    return entries


def decide(repo, event_name, event, checkout_sha):
    result = {"format": 1, "event": event_name, "checkout_sha": checkout_sha,
              "required": True, "reason": "full-event", "complete": True,
              "parity_execution": "required", "changes": []}
    if event_name != "pull_request":
        return result  # Main, manual and merge queue always exercise the gate.

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30).stdout

    try:
        pr = event["pull_request"]
        base, head = pr["base"]["sha"], pr["head"]["sha"]
        result.update(base_sha=base, head_sha=head)
        if not all(isinstance(s, str) and SHA.fullmatch(s)
                   for s in (base, head, checkout_sha)):
            raise ValueError("missing or invalid exact commit identity")
        if git("rev-parse", "HEAD").decode().strip() != checkout_sha:
            raise ValueError("checkout identity mismatch")
        for commit in (base, head, checkout_sha):
            git("cat-file", "-e", commit + "^{commit}")
        # Default pull_request checkout is its tested merge commit. Prove it
        # contains both event inputs; stale or shallow histories run full.
        git("merge-base", "--is-ancestor", base, checkout_sha)
        git("merge-base", "--is-ancestor", head, checkout_sha)
        merge_bases = git("merge-base", "--all", base, head).decode().splitlines()
        if len(merge_bases) != 1 or not SHA.fullmatch(merge_bases[0]):
            raise ValueError("ambiguous or missing merge base")
        result["merge_base_sha"] = merge_bases[0]
        raw = git("diff", "--no-ext-diff", "--no-textconv", "--no-renames",
                  "--name-status", "-z", merge_bases[0], head, "--")
        result["diff_sha256"] = hashlib.sha256(raw).hexdigest()
        changes = parse_diff(raw)
        result["changes"] = changes
        if all(unrelated(item["path"]) for item in changes):
            result.update(required=False, reason="verified-unrelated-pr-diff",
                          parity_execution="not-executed")
        else:
            result["reason"] = "dependency-or-unknown-path"
    except (KeyError, TypeError, ValueError, UnicodeError, OSError,
            subprocess.SubprocessError) as error:
        # Failure to prove irrelevance is not permission to skip. No network
        # API/pagination or third-party changed-files action is trusted here.
        result.update(required=True, reason="uncertain-diff-run-full",
                      parity_execution="required", detail=str(error)[:500])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--event-name", default=os.environ.get("GITHUB_EVENT_NAME", ""))
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH", ""))
    parser.add_argument("--checkout-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--output", required=True)
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT"))
    args = parser.parse_args()
    try:
        event = json.loads(Path(args.event_path).read_text())
    except (OSError, ValueError):
        event = {}
    result = decide(args.repo, args.event_name, event, args.checkout_sha)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    # Emit the selection only after its complete receipt is safely written.
    if args.github_output:
        with open(args.github_output, "a") as stream:
            stream.write("required=" + str(result["required"]).lower() + "\n")
    print(json.dumps(result, sort_keys=True))
    if not result["required"]:
        print("Async language parity was NOT EXECUTED: verified unrelated PR diff.")


if __name__ == "__main__":
    main()
