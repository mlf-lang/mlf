#!/usr/bin/env python3
"""Select expensive async parity; a policy decision is never a test result.

PRs opt in with the maintainer-applied ci:async-parity label. Main pushes,
manual dispatches and merge-queue events retain full async coverage. Invalid
or incomplete event metadata fails closed by requiring execution.
"""
import argparse
import json
import os
from pathlib import Path
import re

SHA = re.compile(r"[0-9a-f]{40}\Z")
OPT_IN_LABEL = "ci:async-parity"


def decide(repo, event_name, event, checkout_sha):
    # Keep the call shape stable for the CLI; policy does not infer irrelevance
    # from a source diff and therefore needs no network or Git history access.
    result = {"format": 1, "event": event_name, "checkout_sha": checkout_sha,
              "required": True, "reason": "full-event", "complete": True,
              "parity_execution": "required", "opt_in_label": OPT_IN_LABEL}
    if event_name != "pull_request":
        return result
    try:
        pr = event["pull_request"]
        base, head, labels = pr["base"]["sha"], pr["head"]["sha"], pr["labels"]
        if not all(isinstance(s, str) and SHA.fullmatch(s)
                   for s in (base, head, checkout_sha)):
            raise ValueError("missing or invalid exact commit identity")
        if not isinstance(labels, list) or not all(
                isinstance(label, dict) and isinstance(label.get("name"), str)
                for label in labels):
            raise ValueError("missing or invalid PR label metadata")
        opted_in = any(label["name"] == OPT_IN_LABEL for label in labels)
        result.update(base_sha=base, head_sha=head, required=opted_in,
                      reason="pull-request-explicit-opt-in" if opted_in else "pull-request-default-opt-out",
                      parity_execution="required" if opted_in else "not-executed")
    except (KeyError, TypeError, ValueError) as error:
        result.update(reason="uncertain-event-run-full", detail=str(error)[:500])
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
    if args.github_output:
        with open(args.github_output, "a") as stream:
            stream.write("required=" + str(result["required"]).lower() + "\n")
    print(json.dumps(result, sort_keys=True))
    if not result["required"]:
        print("Async language parity was NOT EXECUTED: PR default opt-out; add ci:async-parity to opt in.")


if __name__ == "__main__":
    main()
