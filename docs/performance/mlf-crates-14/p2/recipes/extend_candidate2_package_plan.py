#!/usr/bin/env python3
"""Review completed RTS/archive evidence and extend the unexecuted v2 plan.

Reads/hashes existing outputs only. Does not run compilers, compress, extract,
delete, mutate source trees, modify either existing ZIP, or call Library.
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

W = Path(__file__).resolve().parents[1]


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(relative):
    return json.loads((W / relative).read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    plan_path = W / 'deliverables/candidate2-package-plan.json'
    review_path = W / 'candidates/fingerprint-2/candidate2-final-review.json'
    results_path = W / 'candidates/fingerprint-2/RESULTS-candidate2.txt'
    plan_receipt_path = W / 'deliverables/candidate2-package-plan-receipt.json'
    before = {str(p.relative_to(W)): sha(p)
              for p in [plan_path, review_path, results_path, plan_receipt_path]}
    assert before[str(plan_path.relative_to(W))] == '36b5fe4e3ece9886da912ac419623b23dd02eed88d4561243a98980552313873'
    plan = json.loads(plan_path.read_text())
    assert len(plan['base_archive']['members']) == 409
    assert len(plan['additions']) == 265
    assert not Path(plan['suggested_output']).exists(), 'v2 packaging already executed'
    assert sha(plan['base_archive']['path']) == plan['base_archive']['sha256']
    for entry in plan['additions']:
        assert sha(entry['source_path']) == entry['sha256'], entry['source_path']
        assert Path(entry['source_path']).stat().st_size == entry['bytes']

    screening = read('evidence/fingerprint-2-rts-screening.json')
    build = read('compilers/fingerprint-2-rts/receipt.json')
    assert screening['complete'] and build['complete']
    assert build['authentication_before'] and build['authentication_after']
    assert build['non_main_objects_byte_identical'] and build['exit_code'] == 0
    assert sha(W / 'compilers/fingerprint-2-rts/receipt.json') == screening['build_receipt_sha256']
    assert sha(W / 'compilers/fingerprint-2-rts/recipe.py') == build['recipe_sha256']
    assert sha(W / 'recipes/summarize_rts_screening.py') == screening['recipe_sha256']
    assert sha(Path(build['producer']) / 'receipt.json') == build['producer_receipt_sha256']
    object_pins = build['unchanged_non_main_object_files']
    extensions = Counter(Path(name).suffix for name in object_pins)
    assert extensions == {'.o': 125, '.hi': 125}
    for relative, digest in object_pins.items():
        assert sha(Path(build['producer']) / 'objects' / relative) == digest
        assert sha(W / 'compilers/fingerprint-2-rts/objects' / relative) == digest
    assert sha(W / 'compilers/fingerprint-2-rts/emlf') == build['binary_sha256']

    additions = [
        'evidence/fingerprint-2-rts-screening.json',
        'recipes/summarize_rts_screening.py',
        'compilers/fingerprint-2-rts/receipt.json',
        'compilers/fingerprint-2-rts/recipe.py',
        'compilers/fingerprint-2-rts/build.log',
    ]
    rts_rows = []
    for row in screening['samples']:
        label = row['label']
        run = W / 'runs' / label
        r = json.loads((run / 'receipt.json').read_text())
        guard = read('guards/' + label + '/bounded-receipt.json')
        assert r['complete'] and r['exit_code'] == 0 and r['byte_identical_to_prior']
        assert r['target_cache_initially_absent'] and r['immutable_inputs_verified_after']
        assert r['query_report']['inferred_groups'] == 544 and r['query_report']['reused_groups'] == 0
        assert r['frozen_sha256'] == sha(W / 'frozen.json')
        assert r['compiler_sha256'] == build['binary_sha256']
        assert row['receipt_sha256'] == sha(run / 'receipt.json')
        assert row['stderr_sha256'] == sha(run / 'stderr')
        assert row['wall_seconds'] == r['wall_seconds']
        assert row['GHCRTS'] == r['environment']['GHCRTS']
        assert guard['complete'] and guard['exit_code'] == 0 and guard['terminal_descendants_empty']
        stderr = (run / 'stderr').read_text()
        for field, suffix in [('allocated_bytes', 'allocated in the heap'),
                              ('copied_bytes', 'copied during GC'),
                              ('sampled_max_residency_bytes', 'maximum residency')]:
            value = int(re.search(r'([\d,]+) bytes ' + suffix, stderr).group(1).replace(',', ''))
            assert value == row[field]
        phases = {name: {'cpu_seconds_rounded': float(cpu), 'elapsed_seconds_rounded': float(elapsed)}
                  for name, cpu, elapsed in re.findall(
                      r'^\s*(INIT|MUT|GC|EXIT|Total)\s+time\s+([\d.]+)s\s+\(\s*([\d.]+)s elapsed\)', stderr, re.M)}
        assert phases == row['phases']
        additions += ['runs/' + label + '/' + name
                      for name in ['receipt.json', 'recipe.py', 'stdout', 'stderr', 'crate.spec']]
        additions.append('guards/' + label + '/bounded-receipt.json')
        rts_rows.append({**row, 'guard_receipt_sha256': sha(W / 'guards' / label / 'bounded-receipt.json')})
    assert [x['GHCRTS'] for x in rts_rows] == ['-T -s', '-A16m -T -s']
    assert len(rts_rows) == 2
    assert rts_rows[1]['wall_seconds'] / rts_rows[0]['wall_seconds'] == screening['A16m_to_default_wall_ratio']

    labels = [f'{candidate}-mlf-{number}' for candidate in ['namespace-filter-1', 'fingerprint-2']
              for number in [1, 2, 3]]
    archive_rows = []
    for label in labels:
        relative = 'runs/' + label + '/queries-archive.json'
        r = read(relative)
        assert r['complete'] and r['label'] == label and r['copies_removed'] and r['all_member_hashes_verified']
        assert r['recipe_sha256'] == sha(W / 'recipes/archive_completed_queries.py')
        archive = Path(r['archive'])
        assert archive == W / 'runs' / label / 'queries.tar.gz'
        assert archive.is_file() and not (archive.parent / 'queries').exists()
        assert sha(archive) == r['archive_sha256'] and archive.stat().st_size == r['archive_bytes']
        assert sum(x['bytes'] for x in r['files'].values()) == r['original_file_bytes']
        for path, digest in r['inputs'].items():
            assert sha(path) == digest
        archive_rows.append({k: r[k] for k in ['label', 'archive_sha256', 'archive_bytes',
                            'original_file_bytes', 'all_member_hashes_verified', 'copies_removed']}
                            | {'archive_receipt_sha256': sha(W / relative),
                               'member_files': len(r['files']), 'directories': len(r['directories']),
                               'compressed_file_hash_reverified_now': True})
        additions.append(relative)
    failed = read('guards/archive-completed-1/bounded-receipt.json')
    succeeded = read('guards/archive-completed-2/bounded-receipt.json')
    assert not failed['complete'] and failed['exit_code'] == 1 and failed['terminal_descendants_empty']
    assert succeeded['complete'] and succeeded['exit_code'] == 0 and succeeded['terminal_descendants_empty']
    assert failed['command'][3] == 'baseline-mlf-1'
    assert succeeded['command'][3:] == labels
    failure_text = (W / 'guards/archive-completed-1/build.log').read_text()
    assert "KeyError: 'terminal_descendants_empty'" in failure_text
    assert 'terminal_descendants_empty' not in read('guards/baseline-mlf-1/bounded-receipt.json')
    baseline_state = []
    for number in [1, 2, 3]:
        run = W / 'runs' / f'baseline-mlf-{number}'
        assert (run / 'queries').is_dir()
        assert not (run / 'queries.tar.gz').exists() and not (run / 'queries-archive.json').exists()
        baseline_state.append(run.name)
    additions.append('recipes/archive_completed_queries.py')
    for attempt in [1, 2]:
        additions += [f'guards/archive-completed-{attempt}/{name}'
                      for name in ['build.log', 'bounded-receipt.json']]
    additions.append('recipes/extend_candidate2_package_plan.py')
    assert len(additions) == 29 and len(set(additions)) == 29

    review = json.loads(review_path.read_text())
    review['negative_rts_screen'] = {
        'summary_sha256': sha(W / 'evidence/fingerprint-2-rts-screening.json'),
        'diagnostic_build_receipt_sha256': sha(W / 'compilers/fingerprint-2-rts/receipt.json'),
        'source_object_and_interface_files_reverified_identical': 250,
        'object_files': 125, 'interface_files': 125,
        'samples': rts_rows,
        'decision': 'A16m not adopted; production RTS configuration unchanged.',
        'scope': 'One diagnostic run per configuration, not a median, not an ABBA causal claim, and excluded from accepted source-level medians.',
        'memory_limits': 'RTS maximum residency is sampled at major GC, not process RSS; explicit rounded RTS timings retained, not the printed %GC field.',
    }
    review['completed_query_archival'] = {
        'recipe_sha256': sha(W / 'recipes/archive_completed_queries.py'),
        'scope': 'Six completed task-owned candidate query directories only; no reuse for inference; query archive bodies excluded from Library package.',
        'runs': archive_rows,
        'initial_attempt': {
            'status': 'failed before any query/archive writes; watchdog log/receipt retained',
            'cause': "KeyError: terminal_descendants_empty missing from first old baseline guard receipt",
            'receipt_sha256': sha(W / 'guards/archive-completed-1/bounded-receipt.json'),
            'log_sha256': sha(W / 'guards/archive-completed-1/build.log'),
        },
        'second_attempt': {
            'status': 'complete; exactly the six candidate run labels, owned descendants empty',
            'receipt_sha256': sha(W / 'guards/archive-completed-2/bounded-receipt.json'),
            'log_sha256': sha(W / 'guards/archive-completed-2/build.log'),
        },
        'baseline_expanded_query_directories_observed_intact_no_archive_or_record': baseline_state,
        'verification_limits': 'Archive producer verified every member and directory against originals before removing redundant copies. This review rehashed compressed archives and pinned input receipts/checked artifacts, but did not decompress them again or rehash all expanded baseline query bytes.',
    }
    results = results_path.read_text() + (
        'Negative RTS screen (diagnostic only): default -T -s took 100.468738793 s;\n'
        '-A16m -T -s took 113.845159469 s, one run each, NOT medians. GC elapsed\n'
        'fell from 14.088 to 10.665 s but total wall increased; A16m was NOT adopted.\n'
        'The diagnostic relink retained 125 .o + 125 .hi files byte-identically.\n'
        'Both screens inferred 544/0 and preserved checked bytes. RTS sampled\n'
        'residency and rounded GC time are not ordinary process peak RSS.\n\n'
        'Storage-only archival: the six completed candidate1/candidate2 query\n'
        'directories are locally restorable from hash-verified lossless archives;\n'
        'all member bytes were checked before redundant expanded copies were removed.\n'
        'Archives are NOT inference inputs and their bodies are NOT in this package.\n'
        'The first attempt stopped on a missing old baseline guard field BEFORE\n'
        'query/archive writes; all three baseline query directories remain expanded.\n'
        'Failure and successful six-directory archival receipts are both preserved.\n'
    )

    # Retain the unexecuted planning state outside the delivered append-only ZIP.
    for path in [plan_path, review_path, results_path, plan_receipt_path]:
        backup = path.with_name(path.name + '.before-rts-archive')
        assert not backup.exists()
        backup.write_bytes(path.read_bytes())
    write(review_path, review)
    results_path.write_text(results)
    for entry in plan['additions']:
        if entry['source_path'] in [str(review_path), str(results_path)]:
            entry.update(sha256=sha(entry['source_path']), bytes=Path(entry['source_path']).stat().st_size)
    for relative in additions:
        path = W / relative
        assert path.is_file() and not path.is_symlink()
        plan['additions'].append({'source_path': str(path), 'archive_path': 'candidate2/' + relative,
                                 'sha256': sha(path), 'bytes': path.stat().st_size})
    plan['additions'].sort(key=lambda entry: entry['archive_path'])
    assert len({entry['archive_path'] for entry in plan['additions']}) == 294
    assert all(not entry['archive_path'].endswith('queries.tar.gz') for entry in plan['additions'])
    plan['scope'] += ' Also preserves the negative single-run RTS configuration screen and lossless archival receipts; neither changes accepted medians or inference policy.'
    plan['exclusions'].append('The six locally restorable queries.tar.gz bodies and redundant expanded query contents; archive manifests/receipts only are included.')
    plan['extension_review'] = {'recipe_sha256': sha(__file__), 'superseded_plan_sha256': before[str(plan_path.relative_to(W))],
                                'negative_rts_not_adopted': True, 'query_archive_bodies_excluded': True,
                                'compression_performed': False, 'library_invoked': False}
    write(plan_path, plan)
    receipt = json.loads(plan_receipt_path.read_text())
    receipt.update(plan_sha256=sha(plan_path), added_files=len(plan['additions']),
                   planned_total_members=409 + len(plan['additions']) + 1,
                   added_uncompressed_bytes=sum(entry['bytes'] for entry in plan['additions']),
                   extension_recipe_sha256=sha(__file__), superseded_files=before,
                   negative_rts_screen_included=True, archive_receipts_included=6,
                   query_archive_bodies_excluded=True, all_409_base_members_unchanged=True)
    assert receipt['planned_total_members'] <= plan['limits']['max_members']
    assert receipt['added_uncompressed_bytes'] + receipt['previous_uncompressed_bytes'] + 1048576 < plan['limits']['max_total_uncompressed_bytes']
    assert sha(plan['base_archive']['path']) == plan['base_archive']['sha256']
    write(plan_receipt_path, receipt)
    print(json.dumps({**receipt, 'review_sha256': sha(review_path), 'results_sha256': sha(results_path)}, indent=2))


if __name__ == '__main__':
    main()
