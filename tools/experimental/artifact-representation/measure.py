#!/usr/bin/env python3
"""Opt-in reproduction wrapper for one fixed historical base; not a general benchmark."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

BASE = {
    "objects.pack": (2146709, "a31a1e9385efb6b8d203159d1376d68e071dbadae1d2587dec70ade259470b19"),
    "objects.index": (31862, "3e970e8fef4afbb52a9ccf02f7039a36a280ba0f121816319b607fb71e9c1c27"),
    "manifest.json": (3457, "b2774a3859348abf12bb307e14472c64e4c2ae3a478b3b27c6890ba2f9876eec"),
}
CODE = {
    "representation.py": "5676ef360ec21a4c5ace9185fc23a907a0995f50c54fac7934f171f656c8c783",
    "overlay.py": "a54c41438366f3a2c8fb2688ddb33ebf170f9d8664b9693753aa6ec08e2cfed1",
    "read_update_experiment.py": "54f56ff317f2d844228f7d0b3d9fe6c8479e8eca7a37f73509b11aeebb407edc",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pinned_module(name):
    path = Path(__file__).with_name(name)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == CODE[name], "experiment code identity mismatch: " + name)
    spec = importlib.util.spec_from_file_location("fixed_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-dir", required=True, type=Path, help="the exact previously verified component-lists bundle")
    parser.add_argument("--output-dir", required=True, type=Path, help="new directory; its parent must already exist")
    parser.add_argument("--run-fixed-experiment", action="store_true", help="explicitly opt in to the 20 fixed diagnostic read observations")
    args = parser.parse_args(argv)
    try:
        require(args.run_fixed_experiment, "explicit --run-fixed-experiment opt-in required")
        base, output = args.base_dir.absolute(), args.output_dir.absolute()
        require(base.resolve() == base and output.resolve() == output, "paths must not traverse symlinks")
        require(not output.exists() and not output.is_symlink(), "output directory already exists")
        for name, (length, digest) in BASE.items():
            path = base / name
            require(path.is_file() and not path.is_symlink() and path.stat().st_size == length,
                    "expected fixed baseline file: " + name)
            with path.open("rb") as stream:
                raw = stream.read(length + 1)
            require(len(raw) == length and hashlib.sha256(raw).hexdigest() == digest,
                    "expected fixed baseline digest: " + name)
        codec = pinned_module("representation.py")
        overlay = pinned_module("overlay.py")
        experiment = pinned_module("read_update_experiment.py")
        codec.WRITE_BUDGET = 3 * 1024 * 1024  # A tighter bound than the baseline writer.
        result = experiment.execute(codec, overlay, base, output)
        encoded = (json.dumps(result, indent=2) + "\n").encode()
        require(len(encoded) <= 256 * 1024, "report-size limit")
        with (output / "measure-result.json").open("xb") as stream:
            stream.write(encoded)
        print(json.dumps(dict(complete=result["complete"], report_sha256=hashlib.sha256(encoded).hexdigest(),
                              note="Small fixed diagnostics, not compiler/cold-cache performance qualification.")))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, "error: " + str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
