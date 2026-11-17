#!/usr/bin/env python3
"""A source-bound UTF8-only run. No full-direct PASS is manufactured."""
import json
import sys
from pathlib import Path
import qualification_source as source
import qualify_utf8_only as utf8

ROOT = source.ROOT
OUT = ROOT / ".mlf-build/utf8-qualification"

def main():
    before = source.snapshot(OUT / "target-source-before.json")
    utf8.qualify(ROOT / ".mlf-build/shared-ghc/receipt.json",
                 ROOT / ".mlf-build/shared-ghc/bin", OUT / "target", "clang")
    after = source.snapshot(OUT / "target-source-after.json")
    source.require(before == after, "qualification tracked inputs changed")
    path = OUT / "source-bound-target.json"
    source.require(not path.exists(), "fresh source-bound result")
    path.write_text(json.dumps(dict(complete=True,
        qualification_commit=after["qualification_commit"],
        baseline_commit=source.BASE, target="full UTF8 only",
        full_direct_suite_qualified=False), indent=2)+"\n")

if __name__ == "__main__":
    main()
