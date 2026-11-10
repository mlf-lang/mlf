#!/usr/bin/env python3
"""Discard only this workflow's two pinned GHC install inputs, after validation.

This is not a general cleanup tool. Run immediately after make install, with no
concurrent installer. Never touch the installed prefix, caches, or build evidence.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys

VERSION = "9.14.1"
ARCHIVE = "ghc-9.14.1.tar.xz"
STAGING = "ghc-9.14.1-x86_64-unknown-linux"
URL = "https://downloads.haskell.org/~ghc/9.14.1/ghc-9.14.1-x86_64-deb12-linux.tar.xz"
SHA256 = "60f7ab75f28df892729fbaff3a54f58ee3ad7e731929f1b2f3eb0208f73de841"


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def identity(path):
    s = path.lstat()
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def canonical_directory(path):
    require(path.is_absolute() and path != Path("/"), f"Unsafe directory: {path}")
    require(path.resolve(strict=True) == path, f"Symlink or noncanonical path: {path}")
    s = path.lstat()
    require(stat.S_ISDIR(s.st_mode) and s.st_uid == os.getuid(),
            f"Directory must be owned by this runner: {path}")
    require(not s.st_mode & 0o022, f"Directory is writable by other users: {path}")


def check_mounts(paths):
    # st_dev alone misses same-filesystem bind mounts. GitHub's Linux runner
    # exposes their mount points here; fail closed if that evidence is absent.
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        field = line.split()[4]
        mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m[1], 8)), field))
        require(not any(mount == p or p in mount.parents for p in paths),
                f"Mount inside a protected path: {mount}")


def no_staging_reference(data, source):
    for name in (ARCHIVE, STAGING):
        require(name.encode() not in data, f"Installed staging reference in {source}")


def tree_snapshot(root, device, installed=False):
    """Inspect without following directory links; fingerprint paths and inode identity metadata.

    Also hash and scan runtime inputs: wrappers, executables, settings and package
    records/cache. Package dump and ghc-pkg check verify resolved package paths.
    """
    digest = hashlib.sha256()
    count = allocated = scanned = 0
    def walk_error(error):
        raise error
    for directory, dirs, files in os.walk(root, followlinks=False, onerror=walk_error):
        dirs.sort()
        files.sort()
        paths = [Path(directory)] + [Path(directory) / n for n in dirs + files]
        for path in paths:
            # A real subdirectory is handled on its own walk iteration.
            if path != Path(directory) and path.is_dir() and not path.is_symlink():
                continue
            s = path.lstat()
            before = identity(path)
            require(s.st_dev == device, f"Cross-device entry: {path}")
            require(s.st_uid == os.getuid(), f"Foreign-owned entry: {path}")
            relative = str(path.relative_to(root))
            digest.update(json.dumps([relative, before]).encode() + b"\n")
            count += 1
            allocated += s.st_blocks * 512
            if stat.S_ISLNK(s.st_mode):
                target = path.resolve(strict=True)
                require(target == root or root in target.parents,
                        f"Symlink escapes its own tree: {path}")
                digest.update(os.readlink(path).encode() + b"\n")
            elif stat.S_ISREG(s.st_mode):
                require(s.st_nlink == 1, f"Hard-linked file: {path}")
                if installed:
                    with path.open("rb") as source:
                        prefix = source.read(2)
                        runtime = (prefix == b"#!" or s.st_mode & 0o111 or
                                   "bin" in path.relative_to(root).parts or
                                   path.suffix == ".conf" or
                                   path.name in ("settings", "platformConstants", "package.cache"))
                        if runtime:
                            scanned += 1
                            source.seek(0)
                            tail = b""
                            while chunk := source.read(1024 * 1024):
                                no_staging_reference(tail + chunk, path)
                                digest.update(chunk)
                                tail = (tail + chunk)[-max(len(ARCHIVE), len(STAGING)):]
                    require(identity(path) == before, f"File changed while reading: {path}")
            else:
                require(stat.S_ISDIR(s.st_mode), f"Special file: {path}")
    return {"sha256": digest.hexdigest(), "entries": count,
            "allocated_bytes": allocated, "runtime_files_scanned": scanned}


def same_tree_snapshot(before, after):
    # Allocation accounting may change without an inode or content change.
    # Keep both complete snapshots in the receipt; ignore only this statistic.
    return ({key: value for key, value in before.items() if key != "allocated_bytes"} ==
            {key: value for key, value in after.items() if key != "allocated_bytes"})


def command(prefix, executable, *args):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GHC_")}
    env["GHC_ENVIRONMENT"] = "-"
    result = subprocess.run([str(prefix / "bin" / executable), *args],
                            cwd=prefix, env=env, text=True, capture_output=True, timeout=60)
    require(result.returncode == 0,
            f"{executable} {' '.join(args)} failed ({result.returncode}): {result.stderr[:2000]}")
    require(not result.stderr.strip(), f"{executable} diagnostics: {result.stderr[:2000]}")
    no_staging_reference(result.stdout.encode(), executable)
    return result.stdout.strip()


def installed_check(prefix):
    version = command(prefix, "ghc", "--numeric-version")
    require(version == VERSION, f"Unexpected installed GHC version: {version}")
    libdir = Path(command(prefix, "ghc", "--print-libdir"))
    canonical_directory(libdir)
    require(prefix in libdir.parents, "GHC libdir is outside the installed prefix")
    require((libdir / "settings").is_file(), "Installed settings missing")
    database = libdir / "package.conf.d"
    require(database.is_dir() and (database / "package.cache").is_file() and
            any(database.glob("*.conf")), "Installed package database incomplete")
    info = command(prefix, "ghc", "--info")
    options = (f"--global-package-db={database}", "--global", "--no-user-package-db")
    packages = command(prefix, "ghc-pkg", *options, "list", "--simple-output").split()
    require(f"ghc-{VERSION}" in packages and any(p.startswith("base-") for p in packages),
            "Installed ghc/base packages missing")
    dump = command(prefix, "ghc-pkg", *options, "dump", "--expand-pkgroot")
    require(dump, "Installed package dump is empty")
    command(prefix, "ghc-pkg", *options, "check")
    return {"version": version, "libdir": str(libdir), "package_count": len(packages),
            "info_sha256": hashlib.sha256(info.encode()).hexdigest(),
            "package_dump_sha256": hashlib.sha256(dump.encode()).hexdigest(),
            "package_check": "passed"}


def cleanup(root, receipt, save):
    canonical_directory(root)
    archive, staging, prefix = (root / ARCHIVE, root / STAGING, root / "ghc")
    receipt.update(scope=[str(archive), str(staging)], preserved_prefix=str(prefix),
                   download_url=URL, archive_sha256_expected=SHA256,
                   free_bytes_before=shutil.disk_usage(root).free, removed=[])
    save()
    canonical_directory(staging)
    canonical_directory(prefix)
    require(shutil.rmtree.avoids_symlink_attacks, "Symlink-safe deletion is unavailable")
    check_mounts((archive, staging, prefix))
    device = root.stat().st_dev
    a = archive.lstat()
    require(stat.S_ISREG(a.st_mode) and a.st_uid == os.getuid() and
            a.st_nlink == 1 and a.st_dev == device, "Archive must be an owned, singly linked regular file")
    archive_identity = identity(archive)
    with archive.open("rb") as source:
        archive_hash = hashlib.file_digest(source, "sha256").hexdigest()
    receipt["archive_sha256_actual"] = archive_hash
    receipt["archive_bytes"] = a.st_size
    require(archive_hash == SHA256, "Pinned archive SHA256 mismatch")
    require(identity(archive) == archive_identity, "Archive changed during verification")
    stage_snapshot = tree_snapshot(staging, device)
    before = tree_snapshot(prefix, device, installed=True)
    receipt.update(staging=stage_snapshot, installed_tree_before=before)
    receipt["installed_before"] = installed_check(prefix)
    receipt["installed_tree_validated"] = tree_snapshot(prefix, device, installed=True)
    require(same_tree_snapshot(before, receipt["installed_tree_validated"]),
            "Installed files changed during validation")
    receipt["status"] = "validated"
    save()
    # Recheck the exact owned inputs immediately before the only two removals.
    check_mounts((archive, staging, prefix))
    require(identity(archive) == archive_identity, "Archive changed before cleanup")
    receipt["staging_before_cleanup"] = tree_snapshot(staging, device)
    require(same_tree_snapshot(stage_snapshot, receipt["staging_before_cleanup"]),
            "Staging changed before cleanup")
    canonical_directory(root)
    root_identity = identity(root)[:2]
    parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        require((os.fstat(parent).st_dev, os.fstat(parent).st_ino) == root_identity,
                "Runner temporary directory changed")
        receipt.update(status="cleanup-started", cleanup_started=True)
        save()
        shutil.rmtree(STAGING, dir_fd=parent)
        receipt["removed"].append(str(staging))
        save()
        require(identity(archive) == archive_identity, "Archive changed during staging cleanup")
        os.unlink(ARCHIVE, dir_fd=parent)
        receipt["removed"].append(str(archive))
        save()
    finally:
        os.close(parent)
    require(not os.path.lexists(staging) and not os.path.lexists(archive), "Install inputs remain")
    receipt["installed_after"] = installed_check(prefix)
    receipt["installed_tree_after"] = tree_snapshot(prefix, device, installed=True)
    require(receipt["installed_after"] == receipt["installed_before"], "Installed checks changed after cleanup")
    require(same_tree_snapshot(before, receipt["installed_tree_after"]), "Installed files changed after cleanup")
    receipt.update(status="complete", free_bytes_after=shutil.disk_usage(root).free)
    save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    root = Path(os.environ.get("RUNNER_TEMP", ""))
    output = args.receipt.absolute()
    # Evidence belongs outside RUNNER_TEMP and is never overwritten.
    require(root.is_absolute(), "RUNNER_TEMP must be an absolute directory")
    require(output.resolve() == output and root not in output.parents,
            "Receipt must be canonical and outside RUNNER_TEMP")
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt = {"schema": 1, "status": "validating"}
    with output.open("x") as stream:
        def save():
            stream.seek(0)
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        try:
            cleanup(root, receipt, save)
        except Exception as error:
            receipt.update(status="failed" if receipt.get("cleanup_started") else "refused",
                           reason=str(error))
            if root.is_dir():
                receipt["free_bytes_after"] = shutil.disk_usage(root).free
            save()
            raise
    print(f"Verified installed GHC {VERSION}; removed only {ARCHIVE} and {STAGING}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"GHC install-input cleanup stopped: {error}", file=sys.stderr)
        sys.exit(1)
