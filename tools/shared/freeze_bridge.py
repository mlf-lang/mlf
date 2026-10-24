#!/usr/bin/env python3
"""Development-only: freeze pre-cutover legacy sources before their one-time move.

Never called by a normal build. The source-complete archive and reviewable patch
are committed inputs, not reverse translations of shared Haskell files.
"""
from pathlib import Path
import argparse
import gzip
import hashlib
import io
import json
import subprocess
import tarfile

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
BASE = '2f8584423fa3055ca96d1479734357f742c9b3df'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=DEFAULT_ROOT,
                        help='isolated maintained legacy bridge checkout')
    parser.add_argument('--destination', type=Path,
                        default=DEFAULT_ROOT / 'bootstrap/shared-haskell-v1-bridge')
    options = parser.parse_args()
    ROOT = options.source_root.resolve(strict=True)
    DEST = options.destination.resolve()
    if (ROOT / 'bootstrap/MLF/Entry/Emlf.hs').exists():
        raise SystemExit('bridge source root must contain maintained legacy .emlf sources, not the final .hs tree')
    required = ['bootstrap/Main.emlf', 'libraries/mlf-frontend/Bootstrap/Parser.emlf']
    if not all((ROOT / name).is_file() for name in required):
        raise SystemExit('legacy bridge source root is incomplete')
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--',
        'bootstrap', 'libraries', 'package', 'runtime', 'scripts/bootstrap-async.sh'], cwd=ROOT, text=True)
    if any(line and not line.startswith('bootstrap/shared-haskell-v1-bridge/') for line in untracked.splitlines()):
        raise SystemExit('stage legacy bridge source additions before freezing so the review patch is complete')
    sources = []
    for directory in ['bootstrap', 'libraries', 'package', 'runtime']:
        sources.extend(p for p in (ROOT / directory).rglob('*')
                       if p.is_file() and not str(p.relative_to(ROOT)).startswith('bootstrap/shared-haskell-v1-bridge/'))
    sources.extend(ROOT / p for p in ['VERSION', 'scripts/bootstrap-async.sh'])
    files = {str(p.relative_to(ROOT)): p.read_bytes() for p in sorted(sources)}
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    files['bridge-inputs.sha256'] = ''.join(h + '  ' + name + '\n' for name, h in manifest.items()).encode()
    DEST.mkdir(parents=True, exist_ok=True)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w', format=tarfile.PAX_FORMAT) as out:
        for name, data in sorted(files.items()):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = 0o755 if name.endswith('.sh') else 0o644
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ''
            out.addfile(info, io.BytesIO(data))
    packed = gzip.compress(archive.getvalue(), compresslevel=9, mtime=0)
    (DEST / 'source.tar.gz').write_bytes(packed)
    digest = hashlib.sha256(packed).hexdigest()
    (DEST / 'source.tar.gz.sha256').write_text(digest + '  source.tar.gz\n')
    patch = subprocess.check_output(['git', 'diff', '--binary', BASE, '--', 'bootstrap', 'libraries', 'package', 'runtime', 'scripts/bootstrap-async.sh'], cwd=ROOT)
    (DEST / 'compatibility.patch').write_bytes(patch)
    (DEST / 'manifest.json').write_text(json.dumps({'format':1,'base_commit':BASE,
        'pre_cutover_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'archive_sha256':digest,'patch_sha256':hashlib.sha256(patch).hexdigest(),
        'source_syntax':'legacy-emlf-v1','purpose':'source-complete released-native-seed bridge',
        'files':manifest},indent=2,sort_keys=True)+'\n')
    print(DEST)


if __name__ == '__main__':
    main()
