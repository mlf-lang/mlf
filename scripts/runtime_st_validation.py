"""Shared native ST ABI gate, usable with a runtime source or compiled object."""
from pathlib import Path
import hashlib
import subprocess

ST_ERRORS = {
    "negative-size": "invalid array length",
    "huge-size": "invalid array length",
    "zero-read": "array index out of bounds",
    "negative-read": "array index out of bounds",
    "past-read": "array index out of bounds",
    "huge-read": "array index out of bounds",
    "negative-write": "array index out of bounds",
    "past-write": "array index out of bounds",
    "huge-write": "array index out of bounds",
    "ignored-invalid-read": "array index out of bounds",
    "io-as-st": "invalid value for runtime operation",
    "nested-io-as-st": "invalid value for runtime operation",
    "st-as-io": "invalid value for runtime operation",
    "int-array-as-st": "invalid value for runtime operation",
    "st-array-as-io": "invalid value for runtime operation",
    "null-return": "invalid environment write",
    "wrong-arity": "unary primitive arity mismatch",
    "demand-poison": "runtime ST: forced a lazy element",
    "cycle": "cyclic evaluation of a recursive binding",
}
# The direct codegen ABI must keep the same checked operand boundary.
ST_ERRORS.update({"direct-" + key: value for key, value in ST_ERRORS.items()
                  if key in {"negative-size", "huge-size", "zero-read", "negative-read",
                             "past-read", "huge-read", "negative-write", "past-write",
                             "huge-write", "io-as-st", "nested-io-as-st", "int-array-as-st"}})
ST_ERRORS.update({"direct-wrong-length": "invalid value for runtime operation",
                  "direct-null-initial": "missing runtime value",
                  "direct-null-stored": "missing runtime value"})
ST_SUCCESS = "runtime ST: laziness, snapshots, repetition, nesting, WHNF, and GC passed\n"


def validate_st_runtime(*, compiler, fixture, runtime, include_dirs, cflags,
                        libraries, output, environment=None):
    """Build and execute every ABI mode, raising on status/output mismatch.

    Ordinary invocation passes runtime C with -DMLF_GC_THRESHOLD=32. BDWGC
    invocation passes the bootstrap runtime object, -DMLF_USE_BDWGC, collector
    include flags and collector library, so C callbacks collect active roots.
    """
    fixture, runtime, output = map(Path, (fixture, runtime, output))
    output.parent.mkdir(parents=True, exist_ok=True)
    arguments = [str(compiler), "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 *cflags, *("-I" + str(path) for path in include_dirs),
                 str(fixture), str(runtime), *libraries, "-lm", "-o", str(output)]
    compiled = subprocess.run(arguments, capture_output=True, text=True,
                              env=environment, timeout=60)
    if compiled.returncode:
        raise RuntimeError("ST runtime probe compilation failed:\n" + compiled.stdout + compiled.stderr)
    cases = []
    for mode in ("success", *ST_ERRORS):
        executed = subprocess.run([str(output), mode], capture_output=True,
                                  text=True, env=environment, timeout=60)
        expected_status = 0 if mode == "success" else 91 if mode == "demand-poison" else 1
        expected_output = ST_SUCCESS if mode == "success" else ""
        expected_error = ("" if mode == "success" else
                          ST_ERRORS[mode] + "\n" if mode == "demand-poison" else
                          "Runtime: " + ST_ERRORS[mode] + "\n")
        observed = (executed.returncode, executed.stdout, executed.stderr)
        expected = (expected_status, expected_output, expected_error)
        if observed != expected:
            raise RuntimeError(f"ST runtime {mode}: expected {expected!r}, observed {observed!r}")
        cases.append({"mode": mode, "status": executed.returncode,
                      "stdout": executed.stdout, "stderr": executed.stderr})
    return {"source_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "runtime_sha256": hashlib.sha256(runtime.read_bytes()).hexdigest(),
            "executions": len(cases), "cases": cases}
