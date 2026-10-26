#!/usr/bin/env python3
"""Identify the nongenerated, host-independent builtin preparation closure."""
import hashlib
import json
from pathlib import Path
import re


def source_identity(root):
    root = Path(root).resolve()
    manifest = json.loads((root / 'shared-sources.json').read_text())
    sources = {row['module']: row['path'] for row in manifest['modules']}
    pending, closure = ['MLF.Entry.BuiltinPrelude'], {}
    while pending:
        name = pending.pop()
        if name == 'MLF.Primitive' or name in closure:
            continue
        if name in ['MLF.BuiltinPreludeData', 'MLF.PreparedLibraryData']:
            raise RuntimeError('fresh builtin producer depends on generated data')
        path = root / sources[name]
        data = path.read_bytes()
        closure[name] = {'path': sources[name], 'sha256': hashlib.sha256(data).hexdigest()}
        pending.extend(re.findall(r'^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)', data.decode(), re.M))
    inputs = {'format': 'builtin-source-v1', 'modules': closure,
              'source_syntax': manifest['source_syntax'],
              'frontend_semantics': manifest['frontend_semantics'],
              'primitive_abi': manifest['primitive_abi'],
              'builtin_interface': manifest['builtin_interface']}
    identity = 'builtin-source-v1:' + hashlib.sha256(json.dumps(
        inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return identity, inputs


if __name__ == '__main__':
    import sys
    print(source_identity(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])[0])
