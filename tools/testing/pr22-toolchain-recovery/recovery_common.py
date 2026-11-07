"""Linux-only task-local recovery helpers. No system installs or automatic cleanup."""
import argparse
import hashlib
import pathlib
import shutil
import subprocess
import sys
import urllib.request

GIB=1024**3

def verify(path, expected_sha, expected_size=None):
    path=pathlib.Path(path)
    if path.is_symlink() or not path.is_file(): raise ValueError('ordinary archive file required')
    with path.open('rb') as stream: actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=expected_sha or (expected_size is not None and path.stat().st_size!=expected_size):
        raise ValueError('archive SHA256/size mismatch; refusing extraction')
    return path.stat().st_size


def check_resources(root, extra_bytes):
    if sys.platform!='linux': raise ValueError('Linux task-local recovery only')
    if shutil.disk_usage(root).free < 8*GIB+extra_bytes:
        raise ValueError('8 GiB free-disk floor plus operation reserve unavailable')
    available=None
    for line in pathlib.Path('/proc/meminfo').read_text().splitlines():
        if line.startswith('MemAvailable:'): available=int(line.split()[1])*1024
    if available is None or available<3*GIB: raise ValueError('3 GiB available-memory floor unavailable')


def new_output(output, reserve):
    root=pathlib.Path(output).absolute()
    if root.exists() or root.is_symlink(): raise ValueError('--output must not already exist')
    parent=root.parent.resolve(strict=True)
    if parent!=root.parent: raise ValueError('output parent must be canonical, without symlinks')
    for ancestor in (parent,*parent.parents):
        if (ancestor/'.git').exists() or (ancestor/'.git').is_symlink():
            raise ValueError('output must be outside any Git repository or worktree')
    check_resources(parent,reserve)
    root.mkdir()
    (root/'downloads').mkdir()
    return root


def download_verified(url,target,expected_sha,expected_size=None):
    # Exclusive creation. Interrupted or mismatched bytes are retained for review;
    # subsequent runs require a different fresh output, never trust partial data.
    with target.open('xb') as dst, urllib.request.urlopen(url,timeout=180) as src:
        if expected_size is None:
            raise ValueError('explicit archive byte bound required')
        count=0
        while chunk:=src.read(min(1024**2,expected_size+1-count)):
            count+=len(chunk)
            if count>expected_size:
                raise ValueError('download exceeds pinned archive byte bound')
            dst.write(chunk)
    return verify(target,expected_sha,expected_size)


def extract_verified(archive,prefix,sha,size):
    verify(archive,sha,size)
    subprocess.run(['dpkg-deb','--extract',str(archive),str(prefix)],check=True)


def arguments(description):
    parser=argparse.ArgumentParser(description=description)
    parser.add_argument('--output',required=True,help='New, absent task-local directory; never the repository or system prefix')
    return parser.parse_args()
