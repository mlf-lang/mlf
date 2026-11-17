#!/usr/bin/env python3
"""Authenticate a qualification checkout, not a literal baseline-built binary."""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BASE = "09e3fb20d7105da53639f6c8817a6a11d4f01ec1"
BASE_TREE = "ab756f0a1de2ef91e6d76e9b99593f303ac07521"
BRANCH = "refs/heads/codex/pr51-utf8-o0-qualification-20261117-run02"
ALLOW = [".github/workflows/utf8-o0-qualification.yml","docs/utf8-o0-qualification-2026-11-17.md","tools/shared/qualification_checks.py","tools/shared/qualification_install.sh","tools/shared/qualification_run.py","tools/shared/qualification_source.py","tools/shared/qualification_stage.py","tools/shared/qualify_utf8_only.py","tools/shared/test_qualification_stage.py","tools/shared/test_qualify_utf8_only.py","tools/shared/test_utf8_batch_contract.py","tools/shared/utf8_batch_contract.py","tools/shared/utf8_batch_worker.py"]

def require(value, message):
    if not value:
        raise RuntimeError(message)

def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30,
                                   env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})

def parse_tree(raw):
    result = {}
    for row in raw.split(b"\0"):
        if not row:
            continue
        meta, name = row.split(b"\t", 1)
        mode, kind, identity = meta.decode("ascii").split(" ")
        path = name.decode("utf-8")
        require(mode in ("100644", "100755") and kind == "blob", "regular tracked source required")
        require(path not in result and not Path(path).is_absolute()
                and ".." not in Path(path).parts, "unsafe or repeated tracked path")
        result[path] = dict(mode=mode, blob=identity)
    require(0 < len(result) <= 6000, "bounded tracked inventory")
    return result

def snapshot(output):
    output = Path(output)
    require(not os.path.lexists(output), "fresh source proof required")
    head = git("rev-parse", "HEAD").decode().strip()
    require(head == os.environ.get("GITHUB_SHA")
            and os.environ.get("GITHUB_REF") == BRANCH
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_REPOSITORY") == "mlf-lang/mlf",
            "exact independent push identity required")
    require(git("rev-parse", BASE+"^{tree}").decode().strip() == BASE_TREE, "fixed baseline tree")
    require(git("rev-list", "--parents", "-n", "1", head).decode().split() == [head, BASE],
            "one direct child of fixed baseline required")
    before = parse_tree(git("ls-tree", "-rz", "--full-tree", BASE))
    after = parse_tree(git("ls-tree", "-rz", "--full-tree", head))
    changes = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
    require(changes == set(ALLOW), "qualification changed an unreviewed file or omitted a reviewed delta")
    require(not git("diff", "--name-only", "-z", "HEAD", "--"),
            "tracked working tree must equal qualification commit")
    inputs, total = {}, 0
    for name, identity in sorted(after.items()):
        path = ROOT / name
        metadata = path.lstat()
        require(stat.S_ISREG(metadata.st_mode) and path.resolve(strict=True) == path
                and metadata.st_size <= 32 * 1024**2, "bounded regular source: "+name)
        total += metadata.st_size
        require(total <= 128 * 1024**2, "tracked source bound")
        raw = path.read_bytes()
        blob = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
        require(blob == identity["blob"], "working source differs from committed blob: "+name)
        require(bool(metadata.st_mode & 0o111) == (identity["mode"] == "100755"),
                "working executable mode differs: "+name)
        inputs[name] = {**identity, "bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest(),
                        "baseline_identical":identity == before.get(name)}
    require(not git("diff", "--name-only", "-z", "HEAD", "--"), "source drift during snapshot")
    record = dict(complete=True, baseline_commit=BASE, baseline_tree=BASE_TREE,
                  qualification_commit=head, changed_paths=sorted(changes), tracked_inputs=inputs,
                  tracked_bytes=total, source_scope="full tracked checkout except explicit test/workflow delta",
                  producer_scope="qualification commit producer; production inputs identical to baseline, not literal baseline binary")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2)+"\n")
    return record

if __name__ == "__main__":
    require(len(sys.argv) == 2, "one fresh output path required")
    snapshot(sys.argv[1])
