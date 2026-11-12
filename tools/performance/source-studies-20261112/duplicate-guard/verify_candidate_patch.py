"""Check a pinned patch against source bytes without editing any source file."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

SOURCE_PATH = "libraries/mlf-crates/Bootstrap/OpenFragment.hs"
SOURCE_SHA256 = "e392aae043afc2c13cda16e00caa6a3562dc5180d78dce27f699da7046c57c8b"
CHECKER_SHA256 = "5c299a3617d07a9d7fe89f88039134491630eee256dbdd57ebe8270e41f78f1c"
REMOVAL = '    ensure (all (\\p -> S.null (T.freeVars (snd p))) owned) "open fragment exports an open type";\n'


def verify(source_bytes, checker_bytes, patch_bytes):
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError("OpenFragment source does not match pinned bytes")
    if hashlib.sha256(checker_bytes).hexdigest() != CHECKER_SHA256:
        raise ValueError("independent checker does not match pinned bytes")
    source = source_bytes.decode("utf-8")
    if source.count(REMOVAL) != 1:
        raise ValueError("expected one exact duplicate guard")
    candidate = source.replace(REMOVAL, "", 1)
    expected = (f"diff --git a/{SOURCE_PATH} b/{SOURCE_PATH}\n" +
                "".join(difflib.unified_diff(source.splitlines(keepends=True),
                                             candidate.splitlines(keepends=True),
                                             fromfile="a/" + SOURCE_PATH,
                                             tofile="b/" + SOURCE_PATH)))
    if patch_bytes.decode("utf-8") != expected:
        raise ValueError("patch is not exactly the one-line candidate")
    return {"source_path": SOURCE_PATH, "source_sha256": SOURCE_SHA256,
            "checker_source_sha256": CHECKER_SHA256,
            "candidate_text_sha256": hashlib.sha256(candidate.encode()).hexdigest(),
            "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
            "removed_executable_lines": 1, "added_executable_lines": 0,
            "source_files_written": False, "haskell_executed": False,
            "test_scope": "Exact source-byte and unified-diff comparison only"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--checker", required=True)
    parser.add_argument("--patch", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(Path(args.source).read_bytes(),
                            Path(args.checker).read_bytes(),
                            Path(args.patch).read_bytes()), indent=2))
