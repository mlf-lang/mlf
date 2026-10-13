#!/usr/bin/env python3
"""Build a pinned local BDWGC dependency and print bootstrap linker flags."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request

VERSION = "8.2.12"
SHA256 = "42e5194ad06ab6ffb806c83eb99c03462b495d979cda782f3c72c08af833cd4e"
URL = f"https://github.com/bdwgc/bdwgc/releases/download/v{VERSION}/gc-{VERSION}.tar.gz"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--flags", action="store_true", help="emit JSON cflags/libs (the default)")
    parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    directory = root / "dist-newstyle" / "bootstrap-deps"
    prefix = directory / f"bdwgc-{VERSION}-install"
    source = directory / f"gc-{VERSION}"
    archive = directory / f"gc-{VERSION}.tar.gz"
    stamp = prefix / "mlf-build.json"
    manifest = {"version": VERSION, "sha256": SHA256, "system": platform.system(),
                "machine": platform.machine(), "cc": os.environ.get("CC", "cc")}
    library = prefix / "lib" / "libgc.a"
    cached = (library.exists() and stamp.exists() and json.loads(stamp.read_text()) == manifest)
    if not cached:
        directory.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            temporary = archive.with_suffix(".download")
            request = urllib.request.Request(URL, headers={"User-Agent": "mlf-bootstrap/1"})
            with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
            temporary.replace(archive)
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual != SHA256:
            raise RuntimeError(f"BDWGC archive checksum mismatch: {actual}; expected {SHA256}")
        if not (source / "configure").exists():
            with tarfile.open(archive) as package:
                # The upstream release archive is pinned by its published hash.
                # Still reject path traversal before extracting into our build tree.
                for member in package.getmembers():
                    target = (directory / member.name).resolve()
                    if directory.resolve() not in target.parents:
                        raise RuntimeError(f"unsafe archive member: {member.name}")
                    if member.issym() or member.islnk():
                        resolved = (target.parent / member.linkname).resolve()
                        if directory.resolve() not in resolved.parents:
                            raise RuntimeError(f"unsafe archive link: {member.name}")
                if sys.version_info >= (3, 12):
                    package.extractall(directory, filter="data")
                else:
                    package.extractall(directory)
        log_path = directory / "bdwgc-build.log"
        with log_path.open("w") as log:
            commands = [
                ["./configure", "--disable-shared", "--enable-static", "--disable-threads",
                 "--disable-docs", "--with-libatomic-ops=none", f"--prefix={prefix}"],
                ["make", "-j2"], ["make", "check", "-j2"], ["make", "install"],
            ]
            for command in commands:
                result = subprocess.run(command, cwd=source, stdout=log, stderr=subprocess.STDOUT)
                if result.returncode:
                    raise RuntimeError(f"BDWGC build failed: {' '.join(command)}; see {log_path}")
        stamp.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    libraries = [str(library)]
    if platform.system() == "Linux":
        libraries += ["-ldl"]
    print(json.dumps({"cflags": [f"-I{prefix / 'include'}"], "libs": libraries}))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"bootstrap GC: {error}", file=sys.stderr)
        sys.exit(1)
