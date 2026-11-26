#!/usr/bin/env python3
"""Select, run, and reconcile a registered external test adapter."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import uuid

import receipt_adapter
from receipt_adapter import decode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from developer.process import wait_for_group

CATALOG = ROOT / "tests/test-catalog.json"
STATUSES = {"pass", "fail", "skip", "unsupported", "timeout", "crash", "cancelled"}


def ids_in(value, prefix=None):
    if (not isinstance(value, list) or not value
            or not all(isinstance(identity, str) and identity
                       and (prefix is None or identity.startswith(prefix) and identity != prefix)
                       for identity in value)
            or len(value) != len(set(value))):
        raise ValueError("invalid, empty or duplicate case inventory")
    return value


def read_catalog():
    catalog = {}
    manifests = ids_in(decode(CATALOG.read_text(encoding="utf-8"))["external_adapters"])
    for name in manifests:
        path = (ROOT / name).resolve()
        if ROOT not in path.parents:
            raise ValueError(f"catalog escapes checkout: {name}")
        for suite, spec in decode(path.read_text(encoding="utf-8")).items():
            if suite in catalog:
                raise ValueError(f"duplicate suite: {suite}")
            if not suite or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in suite):
                raise ValueError(f"invalid suite name: {suite}")
            kind = spec.get("kind")
            command = spec.get("command")
            if kind not in {"events", "unittest", "exit", "receipt"} or not isinstance(command, list) or not command or not all(isinstance(token, str) and token for token in command):
                raise ValueError(f"invalid adapter: {suite}")
            if ("ids" in spec) == ("prefix" in spec):
                raise ValueError(f"expected one inventory source: {suite}")
            if "ids" in spec:
                ids_in(spec["ids"])
            elif not isinstance(spec["prefix"], str) or not spec["prefix"].endswith("/"):
                raise ValueError(f"invalid case prefix: {suite}")
            if kind == "exit" and len(spec.get("ids", [])) != 1:
                raise ValueError(f"exit adapter must register a single check: {suite}")
            catalog[suite] = spec
    return catalog


def report(path, evidence):
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as output:
        temporary = Path(output.name)
        try:
            json.dump(evidence, output, ensure_ascii=True, allow_nan=False, indent=2)
            output.write("\n")
            output.close()
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)


def argv_for(spec, extra, python_optimization, *, inventory=False):
    command = list(spec.get("list_command", spec["command"]) if inventory else spec["command"])
    if command[0] in {"python", "python3"}:
        command[0] = sys.executable
        if python_optimization and "-O" not in command[1:]:
            command.insert(1, "-O")
    if spec["kind"] == "unittest":
        target = next(i for i in range(1, len(command)) if command[i] == "-m" or not command[i].startswith("-"))
        command.insert(target, str(ROOT / "tools/testing/unittest_adapter.py"))
    return [*command, *extra]


def child_environment(suite, spec, exact, path=None):
    env = os.environ.copy()
    for name in ("MLF_TEST_SUITE", "MLF_TEST_ID_PREFIX", "MLF_TEST_EXACT", "MLF_TEST_LIST", "MLF_TEST_EVENTS"):
        env.pop(name, None)
    env["MLF_TEST_SUITE"] = suite
    if "prefix" in spec:
        env["MLF_TEST_ID_PREFIX"] = spec["prefix"]
    if exact:
        env["MLF_TEST_EXACT"] = exact
    if path is not None:
        env["MLF_TEST_EVENTS"] = str(path)
    return env


def discover(suite, spec, args, extra, capture):
    receipt = spec["kind"] == "receipt"
    if receipt and "list_args" not in spec and "inventory" in spec["receipt"]:
        inventory = ids_in([spec["prefix"] + receipt_adapter.slug(label)
                            for label in spec["receipt"]["inventory"]], spec["prefix"])
        return inventory
    if "ids" in spec:
        return [args.exact] if args.exact else spec["ids"]
    # Receipt producers describe the available plan independently of the exact
    # selector. Validate the selection here before dispatching any real work.
    env = child_environment(suite, spec, None if receipt else args.exact)
    if spec["kind"] == "unittest":
        env["MLF_TEST_LIST"] = "1"
        command = argv_for(spec, extra, args.python_optimization)
    elif "list_args" in spec:
        command = argv_for(spec, [*spec["list_args"], *extra], args.python_optimization, inventory=True)
    else:
        raise ValueError(f"{suite} requires a running adapter to enumerate its plan")
    return ids_in(decode(capture(command, env)), spec["prefix"])


def reconcile(path, spec, exact, evidence):
    by_id = {}
    started = set()
    plan = evidence["expected_ids"]
    planned = set(plan or ())
    with path.open(encoding="utf-8") as source:
        for line in source:
            if not line.endswith("\n"):
                raise ValueError("truncated adapter event")
            event = decode(line)
            if not isinstance(event, dict):
                raise ValueError("invalid adapter event")
            if "plan" in event:
                if plan is not None or by_id or started or set(event) != {"plan"}:
                    raise ValueError("unexpected adapter plan")
                plan = ids_in(event["plan"], spec["prefix"])
                if exact and plan != [exact]:
                    raise ValueError("adapter did not select the requested case")
                evidence["expected_ids"] = plan
                planned = set(plan)
                continue
            if plan is None:
                raise ValueError("adapter emitted observations before its plan")
            identity = event.get("start", event.get("id"))
            if identity not in planned or identity in by_id:
                raise ValueError(f"unknown or duplicate case observation: {identity!r}")
            if "start" in event:
                if identity in started or "id" in event or "status" in event:
                    raise ValueError(f"duplicate or invalid case start: {identity!r}")
                started.add(identity)
                evidence["started_ids"].append(identity)
            else:
                if event.get("status") not in STATUSES:
                    raise ValueError(f"invalid case outcome: {identity!r}")
                by_id[identity] = event
                evidence["results"].append(event)
    if plan is None:
        raise ValueError("missing adapter plan")
    return [identity for identity in plan if identity not in by_id]


@contextmanager
def supervise(inherit_process_group):
    cancelled = []
    owns_session = os.name == "posix" and not inherit_process_group

    def remember(signum, _frame):
        if not cancelled:
            cancelled.append(signum)

    def run_child(argv, environment, stdout=None):
        child = subprocess.Popen(argv, cwd=ROOT, env=environment,
                                 stdout=stdout, start_new_session=owns_session)
        if owns_session:
            return wait_for_group(child, cancelled, cleanup_on_exit=False)
        # An outer watchdog owns this group. Signal only our direct child.
        while not cancelled:
            try:
                return child.wait(timeout=0.05)
            except subprocess.TimeoutExpired:
                pass
        if os.name == "posix":
            child.send_signal(cancelled[0])
            # The group owner enforces the deadline. A suite may still be
            # reaping a nested session whose workers hold our output pipes.
            return child.wait()
        child.terminate()
        try:
            return child.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            child.kill()
            return child.wait()

    def capture_inventory(argv, environment):
        # A descendant can retain a pipe after its leader exits. A temporary
        # file also lets the supervisor drain large inventories without a reader.
        with tempfile.TemporaryFile() as output:
            status = run_child(argv, environment, output)
            if status or cancelled:
                raise subprocess.CalledProcessError(status or -cancelled[0], argv)
            output.seek(0)
            return output.read()

    handlers = {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            handlers[signum] = signal.signal(signum, remember)
        yield cancelled, run_child, capture_inventory
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def execute(suite, spec, args, extra):
    run = uuid.uuid4().hex
    path = (Path(args.report) if args.report else
            ROOT / ".mlf-build/test-framework" / suite / f"{run}.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    event_path = path.with_name(f"{path.stem}.{run}.events.jsonl")
    event_path.touch(exist_ok=False)
    env = child_environment(suite, spec, args.exact, event_path)
    command = argv_for(spec, extra, args.python_optimization)
    selected = [args.exact] if args.exact else spec.get("ids")
    evidence = {
        "schema": "mlf-external-test-run-v1",
        "run_id": run,
        "suite": suite,
        "producer": command,
        "adapter_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "scope": "focused" if args.exact else spec.get("scope", "declared"),
        "expected_ids": selected if "ids" in spec else None,
        "started_ids": [],
        "results": [],
        "events": str(event_path),
        "complete": False,
        "status": "running",
    }
    report(path, evidence)
    status = None
    available = set()
    receipt_path = None
    setup_failed = False
    with supervise(args.inherit_process_group) as (cancelled, run_child, capture_inventory):
        try:
            if spec["kind"] == "receipt":
                try:
                    inventory = discover(suite, spec, args, extra, capture_inventory)
                    available = set(inventory)
                    if args.exact and args.exact not in available:
                        raise ValueError(f"unknown case: {args.exact}")
                    evidence["expected_ids"] = [args.exact] if args.exact else inventory
                    evidence["missing_ids"] = evidence["expected_ids"].copy()
                    if args.exact:
                        evidence["prerequisite_results"] = []
                    report(path, evidence)
                    receipt_path = receipt_adapter.source(ROOT, spec["receipt"], extra)
                    receipt_before = receipt_adapter.fingerprint(receipt_path)
                except (OSError, ValueError, IndexError, KeyError, subprocess.CalledProcessError) as error:
                    evidence["launch_error"] = str(error)
                    setup_failed = True
            if not setup_failed and not cancelled:
                status = run_child(command, env)
        except OSError as error:
            evidence["launch_error"] = str(error)
    interrupted = cancelled[0] if cancelled else None
    if status is not None:
        evidence["exit_code"] = status if status >= 0 else None
        evidence["signal"] = -status if status < 0 else None
    if interrupted is not None:
        evidence["interrupted"] = interrupted
    try:
        if spec["kind"] == "receipt":
            if status is not None:
                evidence["complete"] = (
                    receipt_adapter.import_results(receipt_path, receipt_before, spec, evidence,
                                                   status, available, args.exact)
                    and interrupted is None)
        elif spec["kind"] == "exit" and status is not None and interrupted is None:
            evidence["results"].append({"id": selected[0],
                                        "status": "crash" if status < 0 else "pass" if status == 0 else "fail"})
            evidence["missing_ids"] = []
            evidence["complete"] = status >= 0
        else:
            missing = reconcile(event_path, spec, args.exact, evidence)
            evidence["missing_ids"] = missing
            evidence["complete"] = not missing and status is not None and status >= 0 and interrupted is None
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        evidence["protocol_error"] = str(error)
    evidence["events_sha256"] = hashlib.sha256(event_path.read_bytes()).hexdigest()
    passed = (evidence["complete"] and status == 0
              and all(row["status"] == "pass" or spec.get("allow_skip") is True and row["status"] == "skip"
                      for row in evidence["results"]))
    if passed:
        evidence["status"] = "pass-with-skips" if any(row["status"] == "skip" for row in evidence["results"]) else "pass"
    else:
        evidence["status"] = "interrupted" if interrupted is not None else "fail"
    report(path, evidence)
    print(f"{suite}: {evidence['status']} ({path})", file=sys.stderr)
    if setup_failed and interrupted is None:
        print(f"test: {evidence['launch_error']}", file=sys.stderr)
        return 2
    if interrupted is not None:
        return 128 + interrupted
    if status:
        return status if status > 0 else 128 - status
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", nargs="?")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--exact")
    parser.add_argument("--report")
    parser.add_argument("--python-optimization", action="store_true")
    parser.add_argument("--inherit-process-group", action="store_true",
                        help="keep the adapter in the process group of an outer watchdog")
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        index = argv.index("--")
        extra, argv = argv[index + 1:], argv[:index]
    else:
        extra = []
    args = parser.parse_args(argv)
    try:
        catalog = read_catalog()
        if args.suite is None and args.list and not extra:
            print(json.dumps(sorted(catalog)))
            return 0
        if args.suite not in catalog:
            raise ValueError("select a registered suite (use --list to see suite names)")
        spec = catalog[args.suite]
        if args.exact == "":
            raise ValueError("empty exact selector")
        if args.exact:
            if "ids" in spec and args.exact not in spec["ids"]:
                raise ValueError(f"unknown case: {args.exact}")
            if "prefix" in spec and not args.exact.startswith(spec["prefix"]):
                raise ValueError(f"case is outside suite: {args.exact}")
            if not args.list and not (spec.get("exact") or spec["kind"] == "exit"):
                raise ValueError("this adapter keeps the original combined invocation")
        if args.list:
            with supervise(args.inherit_process_group) as (cancelled, _, capture):
                try:
                    inventory = discover(args.suite, spec, args, extra, capture)
                except subprocess.CalledProcessError:
                    if not cancelled:
                        raise
                if cancelled:
                    return 128 + cancelled[0]
            if args.exact:
                if spec["kind"] == "receipt":
                    if args.exact not in inventory:
                        raise ValueError(f"unknown case: {args.exact}")
                    inventory = [args.exact]
                elif inventory != [args.exact]:
                    raise ValueError("adapter did not list the requested exact case")
            if args.report:
                destination = Path(args.report).resolve()
                destination.parent.mkdir(parents=True, exist_ok=True)
                report(destination, {"schema": "mlf-external-test-inventory-v1",
                                     "suite": args.suite, "ids": inventory})
            print(json.dumps(inventory))
            return 0
        return execute(args.suite, spec, args, extra)
    except (OSError, ValueError, IndexError, KeyError, subprocess.CalledProcessError) as error:
        print(f"test: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
