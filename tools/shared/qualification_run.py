#!/usr/bin/env python3
"""One explicit target, never a full-direct or full-native suite result."""
import json
import sys
from pathlib import Path
import qualification_source as source
import qualify_candidate_only as candidate
import qualify_header_only as header

ROOT=source.ROOT
OUT=ROOT/".mlf-build/header-candidate-qualification"
def main():
    source.require(len(sys.argv)==2 and sys.argv[1] in ("candidate","header"),"one fixed target required")
    target=sys.argv[1]
    before=source.snapshot(OUT/(target+"-source-before.json"))
    selected=candidate if target=="candidate" else header
    selected.qualify(ROOT/".mlf-build/shared-ghc/receipt.json",
                     ROOT/".mlf-build/shared-ghc/bin",OUT/(target+"-target"),"clang")
    after=source.snapshot(OUT/(target+"-source-after.json"))
    source.require(before==after,"qualification tracked inputs changed")
    path=OUT/(target+"-source-bound-result.json")
    source.require(not path.exists(),"fresh source-bound result")
    path.write_text(json.dumps(dict(complete=True,
        qualification_commit=after["qualification_commit"],
        baseline_commit=source.BASE,target=target,
        full_direct_suite_qualified=False,full_native_suite_qualified=False),
        indent=2)+"\n")
if __name__=="__main__":main()
