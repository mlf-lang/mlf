#!/usr/bin/env python3
"""Exercise the actual production receipt helpers without extracting/re-emitting source.

The maintained shared test imports Tests.BuildReceipts, exactly the module used
by Tests.CompilerTests. Supply a shared-aware compiler or a direct-host binary.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--compiler', type=Path)
    mode.add_argument('--executable', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = root / 'tests/shared/MLF/Tests/BuildReceipts.hs'
    tool = (args.compiler or args.executable).resolve(strict=True)
    inputs = [source, root/'tests/Tests/BuildReceipts.hs', root/'tests/Tests/CompilerTests.hs',
              root/'shared-sources.json', Path(__file__).resolve()]
    inputs += sorted((root/'libraries/mlf-foundation').rglob('*.hs'))
    inputs += sorted((root/'libraries/mlf-package-core').rglob('*.hs'))
    hashes = {str(p.relative_to(root)): digest(p) for p in inputs}
    result = {'complete': False, 'mode': 'interpreted-shared-source' if args.compiler else 'direct-host',
              'tool': str(tool), 'tool_sha256': digest(tool), 'inputs': hashes, 'cases': []}
    environment = dict(os.environ, GC_FREE_SPACE_DIVISOR='1')
    try:
        if args.compiler:
            check = subprocess.run([str(tool),'--implementation-identity'], capture_output=True, timeout=10)
            if check.returncode or not check.stdout.startswith(b'MLF/shared-haskell-v1 '):
                raise ValueError('A shared-aware compiler is required; build the frozen native bridge or the direct GHC compiler first.')
            prefix = [str(tool), '-i', str(root/'tests'), '-i', str(root/'libraries/mlf-foundation'),
                      '-i', str(root/'libraries/mlf-package-core'), '--run', str(source), '--']
        else:
            prefix = [str(tool)]
        for name in ['first-and-second','reject-null','reject-object','reject-string','reject-prepared-null']:
            command = prefix+[name]
            completed = subprocess.run(command,cwd=root,env=environment,capture_output=True,timeout=300)
            (output/(name+'.stdout')).write_bytes(completed.stdout)
            (output/(name+'.stderr')).write_bytes(completed.stderr)
            result['cases'].append({'name':name,'command':command,'exit_code':completed.returncode,
                'stdout_sha256':digest(output/(name+'.stdout')),'stderr_sha256':digest(output/(name+'.stderr'))})
            if name=='first-and-second':
                if completed.returncode or completed.stderr or completed.stdout!=b'[0]\n[0,7]\nmissing map builds\nexisting map reused\npartial map builds\n':
                    raise ValueError('Receipt append or focused-Core preparation contract failed')
            elif completed.returncode!=1 or (b'expected JSON object' if name=='reject-prepared-null' else b'expected JSON array') not in completed.stderr:
                raise ValueError('Malformed existing receipt was not rejected: '+name)
            print('PASS suite-build receipts: '+name,flush=True)
        if digest(tool)!=result['tool_sha256'] or any(digest(root/p)!=h for p,h in hashes.items()):
            raise ValueError('Source or tool changed during receipt tests')
        result['complete']=True
    finally:
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
