#!/usr/bin/env python3
"""Bounded synthetic and pure admission, never an interpreter qualification."""
import os
from pathlib import Path
import subprocess
import sys
import qualification_source as source

ROOT = source.ROOT
OUT = ROOT / ".mlf-build/utf8-qualification"

def main():
    source.snapshot(OUT / "admission-source.json")
    subprocess.run([sys.executable, "-B", str(ROOT / "tools/testing/prepare_history_refs.py")],
                   cwd=ROOT, check=True, timeout=30)
    scripts = ("test_utf8_batch_contract.py", "test_utf8_batch_worker.py",
               "test_direct_bounded_entry.py", "test_qualify_utf8_only.py",
               "test_qualification_stage.py")
    for optimized in (False, True):
        mode = "optimized" if optimized else "normal"
        for script in scripts:
            env = dict(os.environ)
            if script == "test_direct_bounded_entry.py":
                env["MLF_UTF8_TEST_EVIDENCE"] = str(OUT / ("managed-synthetic-"+mode))
            if script == "test_qualification_stage.py":
                env["QUALIFICATION_SYNTHETIC_OUTPUT"] = str(OUT / ("outer-synthetic-"+mode))
            argv = [sys.executable, *(["-O"] if optimized else []), "-B",
                    str(ROOT / "tools/shared" / script)]
            print("+ "+repr(argv), flush=True)
            subprocess.run(argv, cwd=ROOT, env=env, check=True, timeout=50)
    subprocess.run(["git", "diff", "--check", source.BASE, "HEAD", "--"],
                   cwd=ROOT, check=True, timeout=10)

if __name__ == "__main__":
    main()
