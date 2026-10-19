#!/usr/bin/env python3
"""Real-compiler local package tests; no mock compiler or skipped cases."""
import argparse
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import hashlib

def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def require(condition, message):
    if not condition:
        raise ValueError(message)

def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def executable(path):
    return Path(str(path) + ".exe") if os.name == "nt" else path


def directory_alias(alias, target, manager):
    if os.name == "nt":
        host = os.environ.get("MLF_WINDOWS_HOST", str(Path(manager).parent / "mlf-host.exe"))
        subprocess.run([host, "link", "-s", str(target), str(alias)], check=True)
    else:
        alias.symlink_to(target, target_is_directory=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manager", type=Path)
    args = parser.parse_args()
    args.compiler = args.compiler.resolve()
    args.output = args.output.resolve()
    report = {"complete": False, "compiler_sha256": digest(args.compiler), "cases": []}
    args.output.mkdir(parents=True, exist_ok=True)

    def passed(name):
        report["cases"].append(name)
        print("PASS " + name, flush=True)

    try:
        with tempfile.TemporaryDirectory(prefix="mlf local packages ") as temporary:
            work = Path(temporary)
            package = work / "app with spaces"
            shutil.copytree(ROOT / "examples/packages", package,
                            ignore=shutil.ignore_patterns(".mlf-build", "mlf.lock"))
            output = work / "build output"
            manifest = package / "mlf-package.json"
            prefix = [str(args.manager.resolve()) if args.manager else os.environ.get("MLF_PACKAGE_MANAGER", str(ROOT / "mlfpkg")), "--compiler", str(args.compiler.resolve()),
                      "--manifest", str(manifest), "--build-dir", str(output),
                      "--runtime", str(ROOT / "runtime/mlf_runtime.c")]

            def run(arguments, success=True, env=None):
                result = subprocess.run([*prefix, *arguments], cwd=work, capture_output=True, timeout=180, env=env)
                if success:
                    require(result.returncode == 0, result.stderr.decode(errors="replace") + result.stdout.decode(errors="replace"))
                else:
                    require(result.returncode != 0, "invalid package succeeded: " + str(arguments))
                return result

            def build_report():
                return json.loads((output / "build-report.json").read_text())

            def edit(path, transform):
                data = json.loads(path.read_text())
                transform(data)
                path.write_text(json.dumps(data))

            run(["build"])
            initial = build_report()
            require(initial["complete"] and len(initial["builds"]) == 4, "expected three separately compiled modules and an executable")
            require(all(not b["cached"] for b in initial["builds"]), "first build reused an artifact")
            require(subprocess.check_output([executable(output / "bin/hello")]) == b"Hello, local packages!\n", "wrong native output")
            passed("transitive local dependencies, ADT, do notation, spaces in paths")
            run(["build"])
            require(all(b["cached"] for b in build_report()["builds"]), "unchanged build did not reuse all artifacts")
            passed("content-addressed no-op build")

            run(["test"])
            require(build_report()["tests"][0]["backends"] == ["interpreter", "llvm"], "test did not cover both backends")
            passed("expected output checked on interpreter and LLVM")
            executable_row = initial["builds"][-1]
            artifact = output / "cache" / executable_row["key"]
            source = package / "message/Message.emlf"
            original_bytes = source.read_bytes()
            original = source.read_text()
            source.unlink()
            result = subprocess.check_output([args.compiler, "-i", artifact / "modules", "--run-module", artifact / "modules/Main.mlfi"], cwd=work)
            require(result == b"Hello, local packages!\n", "linked module still requires dependency source")
            source.write_bytes(original_bytes)
            passed("interface/object executable works without dependency source")

            source.write_text(original.replace("render (Message text) = text", 'render (Message text) = text ++ " updated"'))
            run(["build"])
            require(not build_report()["builds"][-1]["cached"], "transitive implementation change did not relink")
            require(subprocess.check_output([executable(output / "bin/hello")]) == b"Hello, local packages! updated\n", "stale dependency code linked")
            passed("transitive implementation edit invalidates the executable")
            result = run(["test"], success=False)
            require(b"unexpected stdout" in result.stderr and not build_report()["complete"], "output mismatch was not a failed test")
            passed("test output mismatch fails the package test")

            before = digest(executable(output / "bin/hello"))
            source.write_text("module Message where\nthis is invalid @@@\n")
            run(["build"], success=False)
            require(digest(executable(output / "bin/hello")) == before and not build_report()["complete"], "failed rebuild replaced the working executable")
            source.write_bytes(original_bytes)
            run(["build"])
            passed("failed compilation preserves the last successful binary")

            artifact = output / "cache" / initial["builds"][0]["key"]
            (artifact / "unit.mlfo").write_text("corrupted")
            run(["build"])
            require(not build_report()["builds"][0]["cached"], "corrupt checked object was reused")
            require(subprocess.check_output([executable(output / "bin/hello")]) == b"Hello, local packages!\n", "cache repair failed")
            passed("tampered object is rebuilt and checked")

            # Same executable bytes, different path: tool selection is part of
            # the cache identity, rather than an ambient PATH assumption.
            alternate = executable(work / "other compiler")
            shutil.copy2(args.compiler, alternate)
            run(["--compiler", str(alternate), "build"])
            require(all(not b["cached"] for b in build_report()["builds"]), "compiler selection did not invalidate cache")
            passed("compiler identity participates in cache keys")

            run(["lock"])
            run(["--locked", "build"])
            source.write_text(original + "\n-- changed local dependency\n")
            result = run(["--locked", "build"], success=False)
            require(b"lock is stale" in result.stderr, "locked build accepted changed sources")
            source.write_bytes(original_bytes)
            passed("locked build rejects changed local sources")

            # An undeclared import cannot be satisfied by the working directory.
            (work / "Ambient.emlf").write_text("module Ambient where\nx = 0\n")
            main_source = package / "Main.emlf"
            main_source.write_text(main_source.read_text().replace("import Greeting", "import Ambient\nimport Greeting"))
            result = run(["build"], success=False)
            require(b"not declared" in result.stderr, "ambient module escaped package isolation")
            main_source.write_text((ROOT / "examples/packages/Main.emlf").read_text())
            passed("undeclared ambient imports fail before compilation")

            edit(manifest, lambda d: d["executables"]["hello"].update(link="source"))
            edit(manifest, lambda d: d["tests"]["hello"].update(link="source"))
            run(["build"])
            run(["test"])
            require(subprocess.check_output([executable(output / "bin/hello")]) == b"Hello, local packages!\n", "whole-program build changed semantics")
            passed("whole-program local package mode on both backends")

            (package / "Echo.emlf").write_text('''module Echo where
import Private
main = do
  prefix <- getArg 0
  line <- getLine
  putStrLn (identity (prefix ++ line))
''')
            (package / "Private.emlf").write_text("module Private (identity) where\nidentity x = x\n")
            edit(manifest, lambda d: d.update(tests={"echo": {"main": "Echo.emlf", "modules": {"Private": "Private.emlf"},
                 "arguments": ["prefix:"], "stdin": "hello\n", "stdout": "prefix:hello\n"}}))
            run(["test"])
            require(build_report()["tests"][0]["backends"] == ["interpreter", "llvm"], "echo missed a backend")
            passed("private target modules, program arguments, and stdin on both backends")

            result = run(["run", "hello", "--", "unused"])
            require(result.stdout == b"Hello, local packages!\n", "run mixed build diagnostics into program stdout")
            passed("run forwards arguments and keeps program stdout clean")

            # Command tests are argv based and must propagate nonzero exits.
            edit(manifest, lambda d: d.update(tests={"failure": {"command": [sys.executable, "-c", "raise SystemExit(17)"]}}))
            run(["test"], success=False)
            require(not build_report()["complete"] and build_report()["commands"][-1]["exit_code"] == 17, "command test failure was swallowed")
            passed("external test exit status is propagated")

            # The checkout's local BDWGC works without a bdw-gc.pc file or an
            # exported prefix, including inside command-test subprocesses.
            configured_gc = os.environ.get("MLF_GC_PREFIX")
            installations = list((ROOT / "dist-newstyle/bootstrap-deps").glob("bdwgc-*-install"))
            require(configured_gc or len(installations) == 1, "select a BDWGC installation for package tests")
            gc = Path(configured_gc).resolve() if configured_gc else installations[0].resolve()
            bundled_gc = package / "dist-newstyle/bootstrap-deps/bdwgc-test-install"
            bundled_gc.parent.mkdir(parents=True)
            directory_alias(bundled_gc, gc, prefix[0])
            edit(manifest, lambda d: d["executables"]["hello"].update(profile="compiler"))
            edit(manifest, lambda d: d.update(tests={"gc": {"requires": ["hello"], "command": [
                sys.executable, "-c",
                "import os,pathlib,subprocess,sys; "
                "assert pathlib.Path(os.environ['MLF_GC_PREFIX']).resolve() == pathlib.Path(sys.argv[1]); "
                "assert subprocess.check_output([sys.argv[2]]) == b'Hello, local packages!\\n'",
                str(gc), "{bin:hello}"]}}))
            environment = os.environ.copy()
            environment.pop("MLF_GC_PREFIX", None)
            run(["test"], env=environment)
            library = gc / ("lib/libgc.dll.a" if os.name == "nt" else "lib/libgc.a")
            require(any(library.as_posix() in row["flags"] for row in build_report()["native_inputs"]),
                    "checkout BDWGC was not used to build the executable")
            passed("checkout BDWGC discovery and command-test inheritance without an exported prefix")
            environment["MLF_GC_PREFIX"] = str(work / "missing environment prefix")
            run(["--gc-prefix", str(gc), "test"], env=environment)
            passed("explicit BDWGC prefix overrides the environment and reaches test subprocesses")

            # A compiler checkout must prefer its built compiler over an older
            # emlf on PATH, while retaining explicit compiler overrides.
            edit(manifest, lambda d: d.update(name="mlf-compiler", executables={
                **d["executables"], "emlf": {"main": "Main.emlf"}}))
            local_compiler = executable(output / "bin/emlf")
            if os.name == "nt":
                shutil.copy2(args.compiler, local_compiler)
            else:
                local_compiler.symlink_to(args.compiler)
            old_bin = work / "old installation"
            old_bin.mkdir()
            old_compiler = executable(old_bin / "emlf")
            marker = work / "old compiler selected"
            if os.name == "nt":
                mock_source = work / "old-compiler.c"
                mock_source.write_text('#include <stdio.h>\n#include <stdlib.h>\n#include <wchar.h>\n'
                    'int main(void) { FILE *f = _wfopen(_wgetenv(L"MLF_PACKAGE_TEST_MARKER"), L"wb"); '
                    'if (!f) return 98; fputs("used", f); fclose(f); return 99; }\n', encoding="utf-8")
                clang = initial["toolchain"]["clang"]["path"]
                subprocess.run([clang, mock_source, "-o", old_compiler], check=True)
            else:
                old_compiler.write_text("#!/bin/sh\nprintf used > " + shlex.quote(str(marker)) + "\nexit 99\n")
                old_compiler.chmod(0o755)
            environment = os.environ.copy()
            environment.pop("MLF_COMPILER", None)
            environment["MLF_PACKAGE_TEST_MARKER"] = str(marker)
            environment["PATH"] = str(old_bin) + os.pathsep + environment["PATH"]
            checkout_command = [prefix[0], "--manifest", str(manifest), "--build-dir", str(output),
                                "--runtime", str(ROOT / "runtime/mlf_runtime.c")]
            result = subprocess.run([*checkout_command, "build", "--target", "hello"],
                                    cwd=work, capture_output=True, timeout=180, env=environment)
            require(result.returncode == 0, result.stderr.decode(errors="replace"))
            require(not marker.exists(), "default checkout build selected the older compiler on PATH")
            expected_compiler = local_compiler if os.name == "nt" else args.compiler
            require(build_report()["toolchain"]["compiler"]["path"] == expected_compiler.as_posix(),
                    "default checkout build did not select its local compiler")
            passed("checkout compiler selection takes precedence over an older compiler on PATH")
            result = subprocess.run([*checkout_command, "--compiler", str(old_compiler), "build", "--target", "hello"],
                                    cwd=work, capture_output=True, timeout=180, env=environment)
            require(result.returncode != 0 and marker.exists() and b"(99)" in result.stderr,
                    "explicit compiler selection did not override the checkout default")
            passed("explicit compiler selection overrides a locally built compiler")

        report["complete"] = True
        print(f"{len(report['cases'])} package integration cases passed", flush=True)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["error"] = str(error)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        write_json(args.output / "verification.json", report)


if __name__ == "__main__":
    raise SystemExit(main())
