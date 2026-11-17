#!/usr/bin/env python3
"""Single-target UTF8 qualification via the existing managed route.
Not a full original direct.main run or per-vector fresh-process equivalence.
The separate source-basis and outer-stage evidence must also pass.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def raw_module(raw, name, path):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module

def require_o0(producer):
    require(producer.get("complete") is True
            and producer.get("typecheck_only") is False
            and producer.get("producer_host") == "GHC"
            and producer.get("optimization") == "0",
            "fresh executable-producing GHC O0 authentication required")

def check_inputs(inputs):
    for name, expected in inputs.items():
        path = Path(name)
        require(path.is_file() and digest(path.read_bytes()) == expected,
                "qualification input changed: " + name)

def load_context():
    entry_path = HERE / "test_direct_bounded.py"
    worker_path = HERE / "utf8_batch_worker.py"
    entry_raw, worker_raw = entry_path.read_bytes(), worker_path.read_bytes()
    entry = raw_module(entry_raw, "_utf8_qualification_entry", entry_path)
    worker = raw_module(worker_raw, "_utf8_qualification_worker", worker_path)
    raws, pins = worker.snapshot()
    require(raws["test_direct_bounded.py"] == entry_raw
            and raws["utf8_batch_worker.py"] == worker_raw,
            "loaded successor differs from authenticated snapshot")
    require((entry.WORK, entry.CLEANUP, entry.OUTER, entry.CANCEL_GRACE)
            == (600, 10, 625, 25), "unchanged managed UTF8 budgets required")
    crc = raw_module(raws["test_direct_crc_successor.py"],
                     "_utf8_qualification_crc", HERE / "test_direct_crc_successor.py")
    direct = raw_module(raws["test_direct.py"], "_utf8_qualification_direct",
                        HERE / "test_direct.py")
    require(direct.ROOT == ROOT and entry.HERE == HERE and worker.HERE == HERE,
            "single unchanged checkout root required")
    return entry, worker, crc, direct, pins

def run_one(entry, worker, crc, direct, pins, output, record, save,
            build_receipt, clang):
    """Production route; no virtual original-main result is manufactured."""
    composed = entry.compose(direct, crc, worker, pins)
    runner = composed.CommandRunner(direct.ROOT, output, record, save)
    argv = [sys.executable, "-B", str(HERE / "test_utf8_length.py"),
            "--build-receipt", str(build_receipt), "--clang", str(clang),
            "--output", str(output / "utf8-length")]
    result = runner.run("utf8-length", argv, timeout=600)
    require(type(result.returncode) is int and result.returncode == 0,
            "managed UTF8 invocation did not complete successfully")
    return argv

def validate_single_result(record, worker, output, argv):
    commands = record.get("commands")
    require(type(commands) is list and len(commands) == 1,
            "exactly one managed UTF8 command required")
    command = commands[0]
    require(command.get("name") == "utf8-length" and command.get("argv") == argv
            and command.get("state") == "passed"
            and type(command.get("exit_code")) is int and command["exit_code"] == 0,
            "single managed UTF8 command failed or changed")
    require(not any(key in command for key in
            ("error", "evidence_error", "cleanup_unverified", "leader_reap_unverified")),
            "managed UTF8 error or unverified cleanup")
    state_path = output / "utf8-length-batch-worker.json"
    state = json.loads(state_path.read_text())
    require(state == command.get("worker") and state.get("complete") is True,
            "actual worker receipt differs from managed result")
    original_path = output / "utf8-length" / "receipt.json"
    original = json.loads(original_path.read_text())
    require(original == state.get("original_receipt"),
            "original UTF8 receipt differs from retained worker receipt")
    worker.validate_inventory(original, state["physical_commands"],
                              state["logical_indices"], state["batch_commands"])
    require(type(state.get("logical_vectors")) is list
            and len(state["logical_vectors"]) == 100, "100 actual batch projections required")
    require(state.get("fixture_generation") == "monomorphic-runtime-loop-v2",
            "explicit monomorphic runtime-loop successor required")
    require(original.get("fresh_process_equivalence_claimed") is False
            and original.get("execution_policy_is_not_completion_evidence") is True
            and original.get("batch_worker_receipt") == str(state_path),
            "explicit logical-versus-physical execution policy required")
    return dict(worker_receipt=str(state_path),
                worker_receipt_sha256=digest(state_path.read_bytes()),
                original_utf8_receipt=str(original_path),
                original_utf8_receipt_sha256=digest(original_path.read_bytes()),
                physical_commands=len(state["physical_commands"]),
                batch_executions=len(state["batch_commands"]),
                batch_projections=len(state["logical_vectors"]),
                original_vector_counts=original["vector_counts"],
                original_demand_counts=original["demand_counts"],
                runtime_cases=len(original["direct_runtime_cases"]))

def qualify(build_receipt, binaries, output, clang_name):
    build_receipt = build_receipt.resolve(strict=True)
    binaries = binaries.resolve(strict=True)
    output = output.absolute()
    require(not os.path.lexists(output), "fresh qualification output required")
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve(strict=True)
    record = dict(format="MLF-UTF8-SINGLE-TARGET-QUALIFICATION-1", complete=False,
                  original_direct_main_executed=False, full_direct_suite_qualified=False,
                  scope="Actual full UTF8 controls through managed route; batch projections not fresh interpreter vectors",
                  source_basis_requirement="Separate qualification-commit and full production-input comparison must pass",
                  commands=[])
    record_path = output / "qualification.json"
    def save():
        temp = record_path.with_suffix(".tmp")
        temp.write_text(json.dumps(record, indent=2) + "\n")
        temp.replace(record_path)
    save()
    try:
        entry, worker, crc, direct, pins = load_context()
        record["successor_pins"] = pins
        initial_receipt = digest(build_receipt.read_bytes())
        clang_found = shutil.which(clang_name)
        require(clang_found is not None, "Clang executable not found")
        clang = Path(clang_found).resolve(strict=True)
        require(clang.is_file() and os.access(clang, os.X_OK),
                "regular executable Clang required")
        inputs = {
            str(build_receipt): initial_receipt,
            str(Path(__file__).resolve()): digest(Path(__file__).read_bytes()),
            str(Path(sys.executable).resolve()): digest(Path(sys.executable).resolve().read_bytes()),
            str(clang): digest(clang.read_bytes()),
        }
        record["inputs"] = inputs
        save()
        producer = direct.authenticate_build(build_receipt, binaries)
        require_o0(producer)
        check_inputs(inputs)
        require(worker.snapshot()[1] == pins, "successor changed before run")
        record["producer"] = dict(path=str(build_receipt), sha256=initial_receipt,
                                  host=producer["producer_host"], optimization=producer["optimization"])
        record["authentication_before_passed"] = True
        save()
        argv = run_one(entry, worker, crc, direct, pins, output, record, save,
                       build_receipt, clang)
        record["utf8_inventory"] = validate_single_result(record, worker, output, argv)
        after = direct.authenticate_build(build_receipt, binaries)
        require_o0(after)
        require(after == producer, "authenticated producer changed during run")
        check_inputs(inputs)
        require(worker.snapshot()[1] == pins, "successor changed after run")
        record["authentication_after_passed"] = True
        record["complete"] = True
    except BaseException as error:
        record["complete"] = False
        record["error"] = dict(type=type(error).__name__, message=str(error))
        raise
    finally:
        save()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--bin-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--clang", default="clang")
    args = parser.parse_args()
    qualify(args.build_receipt, args.bin_dir, args.output, args.clang)

if __name__ == "__main__":
    main()
