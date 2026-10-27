#!/usr/bin/env python3
"""Read-only provenance verification for the frozen 14-module benchmark.

The only write is a compact evidence JSON. Run between timed experiments:
hashing the toolchain and installed libraries reads approximately 1.1 GB.
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[1]
B = W.parent / 'pr25-latest-benchmark-work-20261026'
P = B / 'setup/fixed-producer-2/producer'
S = W.parent / 'pr25-latest-benchmark-fixed-20261026'
EXPECTED_RECEIPT = '74fa044142da0aaea60e591a57cf189c7ec152acef7f6c1fd5fda98376ec3416'
EXPECTED_COMPILER = 'ded7b23d144b817d95b297f3c6f6e18de2f91b656f3e5a6390f28dc9e17ef91a'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=W / 'evidence/provenance-audit.json')
    args = parser.parse_args()
    require(not args.output.exists(), 'Refusing to replace an existing audit: ' + str(args.output))
    started = time.monotonic()
    result = {
        'format': 'mlf-crates-provenance-audit-v1',
        'complete': False,
        'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'recipe_sha256': sha(__file__),
        'producer_receipt_path': str(P / 'receipt.json'),
        'expected_producer_receipt_sha256': EXPECTED_RECEIPT,
        'purpose': 'Input provenance only; no compilation, benchmark, or semantic-test claim.',
    }
    pins = {}
    categories = {}
    bytes_read = 0
    checked = 0

    def add(path, digest, category):
        path = str(Path(path).absolute())
        require(len(digest) == 64 and all(c in '0123456789abcdef' for c in digest),
                'Malformed SHA-256 in trusted inventory: ' + path)
        require(path not in pins or pins[path] == digest, 'Conflicting trusted pins: ' + path)
        pins[path] = digest
        categories[category] = categories.get(category, 0) + 1

    def identified(entry, category):
        add(entry['path'], entry['sha256'], category)

    try:
        raw = (P / 'receipt.json').read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        result['observed_producer_receipt_sha256'] = digest
        require(digest == EXPECTED_RECEIPT, 'Qualified producer receipt differs from trusted handoff')
        producer = json.loads(raw)
        require(producer['complete'] is True and producer['optimization'] == '2',
                'Producer is not the completed -O2 build')
        frozen_raw = (W / 'frozen.json').read_bytes()
        frozen = json.loads(frozen_raw)
        result['frozen_manifest_sha256'] = hashlib.sha256(frozen_raw).hexdigest()
        require(frozen['producer_receipt_sha256'] == EXPECTED_RECEIPT,
                'Frozen manifest names a different producer receipt')
        require(frozen['compiler_sha256'] == EXPECTED_COMPILER,
                'Frozen manifest names a different baseline compiler')
        require(len(frozen['modules']) == 14 and len(frozen['order']) == 14 and
                set(frozen['order']) == set(frozen['modules']), 'Invalid 14-module inventory')
        add(P / 'receipt.json', EXPECTED_RECEIPT, 'producer_receipt')
        identified(producer['ghc'], 'ghc_launcher')
        identified(producer['toolchain']['actual_ghc'], 'actual_ghc')
        identified(producer['ghc_settings'], 'ghc_settings')
        for category in ['toolchain', 'installed_dependencies']:
            for path, digest in producer[category]['files'].items():
                add(path, digest, category)
        for category in ['resolved_modules', 'resolved_host_modules', 'host_inputs',
                         'configuration_inputs']:
            for entry in producer[category].values():
                identified(entry, category)
        add(S / 'shared-sources.json', producer['manifest_sha256'], 'source_root_manifest')
        require(frozen['ghc'] == producer['ghc']['path'] and
                frozen['ghc_sha256'] == producer['ghc']['sha256'], 'Frozen GHC identity differs')
        add(frozen['compiler'], EXPECTED_COMPILER, 'baseline_compiler')
        for module, entry in frozen['modules'].items():
            require(producer['resolved_modules'][module]['sha256'] == entry['sha256'],
                    'Frozen target source differs from producer: ' + module)
            identified(entry, 'frozen_target_sources')
        target_stems = {name.replace('.', '/') for name in frozen['modules']}
        expected_copies = {path.removeprefix('objects/'): digest
                          for path, digest in producer['object_inputs'].items()
                          if path.startswith('objects/') and
                          Path(path).suffix in ['.hi', '.o'] and
                          Path(path).name not in ['Main.hi', 'Main.o'] and
                          str(Path(path.removeprefix('objects/')).with_suffix('')) not in target_stems}
        require(frozen['ghc_dependency_files'] == expected_copies,
                'Copied GHC dependency inventory differs from producer inputs')
        observed_copies = {str(path.relative_to(W / 'ghc-dependencies'))
                           for path in (W / 'ghc-dependencies').rglob('*') if path.is_file()}
        require(observed_copies == set(expected_copies), 'Unexpected/missing copied GHC dependency files')
        for path, digest in expected_copies.items():
            add(P / 'objects' / path, digest, 'original_ghc_dependency_objects')
            add(W / 'ghc-dependencies' / path, digest, 'copied_ghc_dependency_objects')
        for path, digest in frozen['artifacts'].items():
            add(path, digest, 'frozen_mlf_artifacts')
        for dependency in frozen['dependencies']:
            require(frozen['artifacts'].get(dependency['path']) == dependency['metadata'],
                    'MLF direct dependency metadata pin differs')
            object_path = str(Path(dependency['path']).with_suffix('.mlfco'))
            require(frozen['artifacts'].get(object_path) == dependency['object'],
                    'MLF direct dependency object pin differs')
        for path, expected in sorted(pins.items()):
            require(sha(path) == expected, 'Hash mismatch: ' + path)
            bytes_read += Path(path).stat().st_size
            checked += 1
        # A receipt or inventory changed during verification must not pass.
        require(sha(P / 'receipt.json') == EXPECTED_RECEIPT, 'Producer receipt changed during audit')
        require(sha(W / 'frozen.json') == result['frozen_manifest_sha256'],
                'Frozen manifest changed during audit')
        result.update(complete=True, actual_ghc=producer['toolchain']['actual_ghc'],
                      ghc_settings=producer['ghc_settings'], baseline_compiler_sha256=EXPECTED_COMPILER,
                      source_roots=json.loads((S / 'shared-sources.json').read_text())['source_roots'],
                      target_modules=sorted(frozen['modules']),
                      pin_inventory_sha256=hashlib.sha256(json.dumps(pins, sort_keys=True,
                          separators=(',', ':')).encode()).hexdigest())
    except Exception as error:
        result['error'] = type(error).__name__ + ': ' + str(error)
    result.update(category_entry_counts=categories, unique_pinned_files=len(pins),
                  unique_files_verified=checked, bytes_hashed=bytes_read,
                  elapsed_seconds=time.monotonic() - started)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(args.output.name + '.tmp')
    temporary.write_text(json.dumps(result, indent=2) + '\n')
    temporary.replace(args.output)
    print(json.dumps(result, indent=2))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    sys.exit(main())
