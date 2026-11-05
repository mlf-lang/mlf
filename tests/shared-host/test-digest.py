#!/usr/bin/env python3
"""Compare real host SHA paths against hashlib, including errors and chunk edges."""
import argparse, hashlib, random, subprocess, tempfile
from pathlib import Path
root = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser(); p.add_argument('--cc', default='cc'); args = p.parse_args()
with tempfile.TemporaryDirectory(prefix='mlf-digest-') as tmp:
    out = Path(tmp)
    for variant, flags in [('native', []), ('portable', ['-DMLF_TEST_FORCE_PORTABLE_SHA256=1'])]:
        subprocess.run([args.cc, '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', *flags,
                        '-I'+str(root/'runtime'), str(root/'tests/shared-host/DigestProbe.c'),
                        str(root/'runtime/mlf_process_supervisor.c'), '-o', str(out/variant)], check=True)
    cases = {'empty': b'', 'abc': b'abc', 'allbytes': bytes(range(256))}
    rng = random.Random(94821)
    for size in [55, 56, 63, 64, 65, 65535, 65536, 65537, 131137, 1048579]:
        cases[str(size)] = bytes(rng.randrange(256) for _ in range(size))
    for name, data in cases.items():
        path = out/name; path.write_bytes(data); want = hashlib.sha256(data).hexdigest()+'\n'
        for variant in ['native', 'portable']:
            result = subprocess.run([out/variant, path], capture_output=True, text=True)
            assert result.returncode == 0 and result.stdout == want, (name, variant, result.stderr)
    for path, message in [(out/'missing', 'IO error: fileDigest failed'),
                          (out, 'IO error: fileDigest failed'),
                          ('--nul-test', 'file path contains NUL')]:
        for variant in ['native', 'portable']:
            result = subprocess.run([out/variant, path], capture_output=True, text=True)
            assert result.returncode == 1 and result.stderr.strip() == message, (path, variant, result.stderr)
print('digest native and portable controls passed')
