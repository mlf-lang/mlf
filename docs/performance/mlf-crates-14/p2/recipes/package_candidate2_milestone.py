#!/usr/bin/env python3
"""Build a NEW candidate-2 ZIP from a reviewed, hash-pinned inclusion plan.

Never overwrites the saved profile ZIP and never calls Library. Run serially,
outside measured compiler runs: this command decompresses/recompresses evidence.
All 409 previous archive members (407 payloads and two manifests) remain byte-identical.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


def sha(path):
    return hashlib.file_digest(Path(path).open('rb'), 'sha256').hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and '..' not in path.parts and '\\' not in name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan_path = args.plan.resolve(strict=True)
    plan = json.loads(plan_path.read_text())
    if plan.get('format') != 'mlf-crates-candidate2-package-plan-v1' or not plan.get('review_complete'):
        raise ValueError('reviewed candidate2 plan required')
    original = Path(plan['base_archive']['path']).resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output == original:
        raise ValueError('output must be a new file, never the saved profile archive')
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt_path = output.with_suffix('.receipt.json')
    if receipt_path.exists():
        raise ValueError('refusing to overwrite an earlier packaging receipt')
    receipt = {'complete': False, 'plan_sha256': sha(plan_path), 'recipe_sha256': sha(__file__),
               'output': str(output), 'original_archive_untouched': True,
               'scope': 'preoptimization and candidate1 evidence plus accepted candidate2; no candidate3/4 claim'}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')

    save()
    try:
        if sha(original) != plan['base_archive']['sha256']:
            raise ValueError('original profile archive changed')
        base = plan['base_archive']['members']
        additions = plan['additions']
        extra_manifest = 'CANDIDATE2-MANIFEST.json'
        names = list(base) + [entry['archive_path'] for entry in additions] + [extra_manifest]
        limits = plan['limits']
        if len(names) != len(set(names)) or any(not safe_name(name) for name in names):
            raise ValueError('duplicate or unsafe archive member')
        if len(names) > limits['max_members']:
            raise ValueError('member count exceeds reviewed bound')
        total = sum(entry['bytes'] for entry in base.values())
        for entry in additions:
            path = Path(entry['source_path']).resolve(strict=True)
            if path.stat().st_size != entry['bytes'] or sha(path) != entry['sha256']:
                raise ValueError('candidate2 input changed: '+str(path))
            if entry['bytes'] > limits['max_added_member_bytes']:
                raise ValueError('candidate2 input exceeds per-member bound')
            total += entry['bytes']
        public = {'format': 'mlf-crates-profile-plus-candidate2-v1', 'version': 2,
                  'scope': plan['scope'], 'base_archive_sha256': plan['base_archive']['sha256'],
                  'previous_payload_count': 407, 'original_total_members_preserved': 409,
                  'original_members': base,
                  'candidate2_files': {entry['archive_path']: {'sha256': entry['sha256'], 'bytes': entry['bytes']}
                                       for entry in additions},
                  'results': 'candidate2/candidates/fingerprint-2/RESULTS-candidate2.txt',
                  'review': 'candidate2/candidates/fingerprint-2/candidate2-final-review.json',
                  'preservation': 'Both previous manifests and all 407 payload files are unchanged; this separate manifest describes the candidate2 extension.',
                  'exclusions': plan['exclusions']}
        manifest_bytes = (json.dumps(public, indent=2) + '\n').encode()
        total += len(manifest_bytes)
        if total > limits['max_total_uncompressed_bytes']:
            raise ValueError('uncompressed size exceeds reviewed bound')
        with zipfile.ZipFile(original) as old:
            if set(old.namelist()) != set(base) or len(old.infolist()) != 409:
                raise ValueError('original member inventory changed')
            with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as new:
                for name, entry in base.items():
                    data = old.read(name)
                    if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                        raise ValueError('original member bytes differ: '+name)
                    new.writestr(old.getinfo(name), data)
                for entry in additions:
                    new.write(entry['source_path'], entry['archive_path'])
                new.writestr(extra_manifest, manifest_bytes)
        if output.stat().st_size > limits['max_archive_bytes']:
            raise ValueError('compressed archive exceeds reviewed bound; retain partial evidence and review')
        with zipfile.ZipFile(output) as check:
            if check.testzip() is not None or set(check.namelist()) != set(names) or len(check.infolist()) != len(names):
                raise ValueError('ZIP integrity/member inventory failed')
            for name, entry in base.items():
                if hashlib.sha256(check.read(name)).hexdigest() != entry['sha256']:
                    raise ValueError('original member preservation failed: '+name)
            for entry in additions:
                if hashlib.sha256(check.read(entry['archive_path'])).hexdigest() != entry['sha256']:
                    raise ValueError('candidate2 member verification failed')
            if check.read(extra_manifest) != manifest_bytes:
                raise ValueError('candidate2 manifest verification failed')
        if sha(original) != plan['base_archive']['sha256'] or sha(plan_path) != receipt['plan_sha256']:
            raise ValueError('base archive or plan changed during packaging')
        for entry in additions:
            if sha(entry['source_path']) != entry['sha256']:
                raise ValueError('candidate2 input changed during packaging')
        receipt.update(complete=True, bytes=output.stat().st_size, sha256=sha(output),
                       original_members_preserved=409, previous_payloads_preserved=407,
                       candidate2_added_files=len(additions), total_members=len(names),
                       uncompressed_bytes=total, all_member_hashes_verified=True)
    except BaseException as error:
        receipt['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        save()
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
