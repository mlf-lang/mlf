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
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'testing'))
import events


CASES = ('first-and-second', 'reject-null', 'reject-object', 'reject-string', 'reject-prepared-null')
PREFIX = 'release/build-receipts/'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--compiler', type=Path)
    mode.add_argument('--executable', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    exact = os.environ.get('MLF_TEST_EXACT') if os.environ.get('MLF_TEST_SUITE') == 'release-build-receipts' else None
    if exact and exact not in (PREFIX + name for name in (*CASES, 'unchanged-inputs')):
        parser.error('unknown receipt test: ' + exact)
    planned = (exact.removeprefix(PREFIX),) if exact else (*CASES, 'unchanged-inputs')
    root = Path(__file__).resolve().parents[2]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = root / 'tests/shared/MLF/Tests/BuildReceipts.hs'
    tool = (args.compiler or args.executable).resolve(strict=True)
    inputs = [source, root/'tests/shared/Tests/BuildReceipts.hs', root/'tests/Tests/CompilerTests.hs',
              root/'shared-sources.json', Path(__file__).resolve()]
    inputs += sorted((root/'libraries/mlf-foundation').rglob('*.hs'))
    inputs += sorted((root/'libraries/mlf-package-core').rglob('*.hs'))
    hashes = {str(p.relative_to(root)): digest(p) for p in inputs}
    result = {'complete': False, 'scope': 'focused' if exact else 'full',
              'mode': 'interpreted-shared-source' if args.compiler else 'direct-host',
              'tool': str(tool), 'tool_sha256': digest(tool), 'inputs': hashes, 'cases': []}
    environment = dict(os.environ, GC_FREE_SPACE_DIVISOR='1')
    try:
        if args.compiler:
            check = subprocess.run([str(tool),'--implementation-identity'], capture_output=True, timeout=10)
            if check.returncode or not check.stdout.startswith(b'MLF/shared-haskell-v1 '):
                raise ValueError('A shared-aware compiler is required; build the frozen native bridge or the direct GHC compiler first.')
            prefix = [str(tool), '-i', str(root/'tests/shared'), '-i', str(root/'tests'), '-i', str(root/'libraries/mlf-foundation'),
                      '-i', str(root/'libraries/mlf-package-core'), '--run', str(source), '--']
        else:
            prefix = [str(tool)]
        for name in CASES:
            if name not in planned:
                continue
            identity = PREFIX + name
            events.start(identity)
            command = prefix+[name]
            try:
                completed = subprocess.run(command,cwd=root,env=environment,capture_output=True,timeout=300)
            except subprocess.TimeoutExpired as error:
                events.result(identity, 'timeout', detail=str(error))
                raise
            (output/(name+'.stdout')).write_bytes(completed.stdout)
            (output/(name+'.stderr')).write_bytes(completed.stderr)
            observed = {'name':name,'command':command,'exit_code':completed.returncode,
                'stdout_sha256':digest(output/(name+'.stdout')),'stderr_sha256':digest(output/(name+'.stderr'))}
            result['cases'].append(observed)
            if name=='first-and-second':
                passed = completed.returncode == 0 and not completed.stderr and completed.stdout == b'[0]\n[0,7]\nmissing map builds\nexisting map reused\npartial map builds\n'
            else:
                diagnostic = b'expected JSON object' if name == 'reject-prepared-null' else b'expected JSON array'
                passed = completed.returncode == 1 and diagnostic in completed.stderr
            events.result(identity, 'pass' if passed else 'fail', detail=observed)
            if not passed:
                raise ValueError('Build receipt contract failed: ' + name)
            print('PASS suite-build receipts: '+name,flush=True)
        unchanged = digest(tool) == result['tool_sha256'] and all(digest(root/p) == h for p,h in hashes.items())
        if 'unchanged-inputs' in planned:
            events.result(PREFIX + 'unchanged-inputs', 'pass' if unchanged else 'fail')
        if not unchanged:
            raise ValueError('Source or tool changed during receipt tests')
        result['complete']=True
    finally:
        (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    main()
