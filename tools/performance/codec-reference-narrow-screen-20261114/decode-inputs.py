#!/usr/bin/env python3
"""Recover and verify four exact binary payloads; does not run the fixture."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output-dir', type=Path)
args = parser.parse_args()
archive = Path(__file__).resolve().parent
destination = args.output_dir or archive / 'inputs'
destination.mkdir(parents=True, exist_ok=True)
manifest = json.loads((archive / 'inputs/manifest.json').read_text())
for item in manifest['payloads']:
    data = base64.b64decode((archive / item['stored_file']).read_bytes())
    assert len(data) == item['bytes']
    assert hashlib.sha256(data).hexdigest() == item['sha256']
    target = destination / Path(item['decoded_file']).name
    if target.exists():
        assert target.read_bytes() == data, 'Refusing to overwrite different existing input'
    else:
        target.write_bytes(data)
print('Verified four inputs, 464763 bytes. No fixture or compiler executed.')
