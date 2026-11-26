#!/usr/bin/env python3
"""Check submitted commits in CI as well as staged and unstaged local changes."""

import json
import os
from pathlib import Path
import re
import subprocess


def git_output(*arguments, **options):
    return subprocess.check_output(["git", *arguments], text=True, **options).strip()


def commit_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", value):
        raise ValueError("event must contain full base and head commit IDs")
    return value


def empty_tree():
    return git_output("hash-object", "-w", "-t", "tree", "--stdin", input="")


def submitted_range():
    event = os.environ.get("GITHUB_EVENT_NAME")
    if event in {"pull_request", "merge_group", "push"}:
        payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        if event == "pull_request":
            request = payload["pull_request"]
            base, head = commit_id(request["base"]["sha"]), commit_id(request["head"]["sha"])
            # The base branch may have advanced independently of this PR.
            return [base + "..." + head]
        if event == "merge_group":
            group = payload["merge_group"]
            return [commit_id(group["base_sha"]), commit_id(group["head_sha"])]
        base, head = commit_id(payload["before"]), commit_id(payload["after"])
        return [empty_tree() if set(base) == {"0"} else base, head]
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # Manual qualification can check out a ref other than GITHUB_SHA.
        commits = git_output("rev-list", "--parents", "-n", "1", "HEAD").split()
        return [commits[1] if len(commits) > 1 else empty_tree(), commits[0]]
    return []


def main():
    revisions = submitted_range()
    if revisions:
        subprocess.run(["git", "diff", "--check", *revisions, "--"], check=True)
    # Check both independently: a worktree edit can hide a bad staged change.
    subprocess.run(["git", "diff", "--check", "--cached", "--"], check=True)
    subprocess.run(["git", "diff", "--check", "--"], check=True)


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode) from error
    except (KeyError, ValueError, OSError) as error:
        raise SystemExit("Cannot check submitted diff: " + str(error)) from error
