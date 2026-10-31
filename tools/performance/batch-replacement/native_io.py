#!/usr/bin/env python3
"""Run the unchanged focused native IO regression with a private Int64 fixture."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
SHARED = ROOT / 'tools/shared'
FIXTURE = SHARED / 'fixtures/native/IOActionSharing.hs'
DRIVER = SHARED / 'test_io_action_sharing.py'
PRODUCER = ROOT / '.mlf-build/batch-replacement-20261101/producer'
GMP_LIB = Path('/opt/homebrew/opt/gmp/lib')
GMP_INCLUDE = Path('/opt/homebrew/opt/gmp/include')
GC = Path('/opt/homebrew/opt/bdw-gc')
CLANG = Path('/usr/bin/clang')
EXPECTED_FIXTURE = '8e62f21c3b5bd41499d620276951e0488aa745e40cb45d09cb8658153f100658'
EXPECTED_DRIVER = 'f36d8aae4a013349c60be1c45c951277a9536c70d2feb36ba596869360b6facd'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adapt(original):
    # These are the complete numeric identity type edits; every other byte is
    # preserved except for the import required to name that Haskell type.
    changes = [(b'name :: Integer -> T.XName', b'name :: Int64 -> T.XName'),
               (b'v :: Integer -> T.XErased', b'v :: Int64 -> T.XErased'),
               (b'bind :: T.XErased -> Integer -> T.XErased -> T.XErased',
                b'bind :: T.XErased -> Int64 -> T.XErased -> T.XErased'),
               (b'import Control.Monad (forM_, unless)\n',
                b'import Data.Int (Int64)\nimport Control.Monad (forM_, unless)\n')]
    adapted = original
    for old, new in changes:
        if adapted.count(old) != 1:
            raise ValueError('fixture adaptation anchor missing or ambiguous: ' + repr(old))
        adapted = adapted.replace(old, new, 1)
    reverse = adapted
    for old, new in reversed(changes):
        if reverse.count(new) != 1:
            raise ValueError('fixture reverse anchor missing or ambiguous: ' + repr(new))
        reverse = reverse.replace(new, old, 1)
    if reverse != original:
        raise ValueError('fixture adaptation is not exactly reversible')
    return adapted, changes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='new directory below repository root')
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output == ROOT or output.is_relative_to(PRODUCER) or PRODUCER.is_relative_to(output):
        parser.error('output must be a separate new directory below the repository root')
    output.mkdir(parents=True, exist_ok=False)
    ledger_path = output / 'adapter-ledger.json'
    original = FIXTURE.read_bytes()
    if hashlib.sha256(original).hexdigest() != EXPECTED_FIXTURE or digest(DRIVER) != EXPECTED_DRIVER:
        raise ValueError('original fixture or unchanged driver differs from reviewed input')
    adapted, changes = adapt(original)
    private = output / 'fixture/IOActionSharing.hs'
    private.parent.mkdir()
    private.write_bytes(adapted)
    tracked = [Path(__file__).resolve(), DRIVER, FIXTURE, private, SHARED / 'build.py',
               SHARED / 'test_direct.py', CLANG.resolve(strict=True),
               (GMP_LIB / 'libgmp.dylib').resolve(strict=True), (GMP_INCLUDE / 'gmp.h').resolve(strict=True), (GC / 'lib/libgc.a').resolve(strict=True)]
    pins = {str(p): digest(p) for p in tracked}
    ledger = {'format': 1, 'complete': False, 'status': 'running', 'inputs_sha256': pins,
              'producer_receipt': str(PRODUCER / 'receipt.json'), 'private_fixture': str(private),
              'changes': [{'from': a.decode(), 'to': b.decode()} for a,b in changes],
              'round_trip_verified': True, 'clang': str(CLANG), 'gc_prefix': str(GC),
              'environment_overrides': {'LIBRARY_PATH': str(GMP_LIB), 'CPATH': str(GMP_INCLUDE)},
              'scope': 'Focused native IO checks; private numeric identity adapter; system linker closure not fully pinned.'}
    def save():
        temp = ledger_path.with_suffix('.json.new')
        temp.write_text(json.dumps(ledger, indent=2) + '\n')
        temp.replace(ledger_path)
    save()
    old_argv = sys.argv
    old_library_path = os.environ.get('LIBRARY_PATH')
    old_cpath = os.environ.get('CPATH')
    try:
        sys.path.insert(0, str(SHARED))
        spec = importlib.util.spec_from_file_location('unchanged_io_action_sharing', DRIVER)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.FIXTURE = private
        os.environ['LIBRARY_PATH'] = str(GMP_LIB)
        os.environ['CPATH'] = str(GMP_INCLUDE)
        sys.argv = [str(DRIVER), '--build-receipt', str(PRODUCER / 'receipt.json'),
                    '--output', str(output / 'driver'), '--gc-prefix', str(GC), '--clang', str(CLANG)]
        module.main()
        receipt = json.loads((output / 'driver/receipt.json').read_text())
        if not receipt.get('complete') or receipt.get('status') != 'passed' or len(receipt.get('native_cases_passed', [])) != 18:
            raise ValueError('unchanged driver did not pass the complete native inventory')
        ledger['driver_receipt_sha256'] = digest(output / 'driver/receipt.json')
        ledger.update(complete=True, status='passed')
    except BaseException as error:
        ledger.update(complete=False, status='failed', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        sys.argv = old_argv
        if old_library_path is None:
            os.environ.pop('LIBRARY_PATH', None)
        else:
            os.environ['LIBRARY_PATH'] = old_library_path
        if old_cpath is None:
            os.environ.pop('CPATH', None)
        else:
            os.environ['CPATH'] = old_cpath
        changed = [p for p, sha in pins.items() if not Path(p).is_file() or digest(p) != sha]
        if changed:
            ledger.update(complete=False, status='invalidated', changed_inputs=changed)
            save()
            raise ValueError('adapter inputs changed: ' + ', '.join(changed))
        ledger['immutable_inputs_verified_after'] = True
        save()


if __name__ == '__main__':
    main()
