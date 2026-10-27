#!/usr/bin/env python3
"""Review completed P3 evidence and author portable patch/append-only v3 plan.

No compilers/tests, large CCS parsing, compression, extraction, Library or source
mutation. The full ZIP byte validation occurs later in the packaging recipe.
"""
import hashlib
import json
import statistics
import subprocess
import zipfile
from pathlib import Path

W = Path(__file__).resolve().parents[1]
S = W.parent / 'mlf-crates-prefix-source-20261026'
P = W / 'candidates/prefix-3/producer'
C = W / 'candidates/prefix-3'
BASE = 'aa11ffd318a2efa5be9805524710d0677eedb86f'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(relative):
    return json.loads((W / relative).read_text())


def write(path, value):
    assert not path.exists(), path
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    assert subprocess.check_output(['git', '-C', str(S), 'rev-parse', 'HEAD'], text=True).strip() == BASE
    prod = json.loads((P / 'receipt.json').read_text())
    assert prod['complete'] and prod['optimization'] == '2' and not prod['typecheck_only']
    producer_hash = sha(P / 'receipt.json')
    assert producer_hash == '3fd51a1697fcffaf2716225be9d1a51351c38032d18d3573fed9d19bc53c3b5f'
    pins = {}
    for group in ['shared_inputs', 'host_inputs', 'configuration_inputs', 'builtin_verification_helpers']:
        for value in prod[group].values():
            path = Path(value['path'])
            assert path.is_relative_to(S) and sha(path) == value['sha256']
            pins[str(path)] = value['sha256']
    assert len(pins) == 174
    assert len(prod['inferred_shared_interfaces']) == 121 and len(prod['outputs']) == 13
    assert all(not x['unresolved_literal_constraints'] for x in prod['inferred_shared_interfaces'].values())
    for command in prod['commands']:
        assert command['exit_code'] == 0 and sha(command['log']) == command['log_sha256']
    assert (P / 'shared-profile.log').read_text().strip() == 'PASS shared syntax/name resolution: 121 modules'
    builtin = json.loads((P / 'builtin-verification/receipt.json').read_text())
    assert builtin['complete'] and builtin['exact_regeneration'] and builtin['candidate_verified']
    compiler_hash = sha(P / 'bin/emlf')
    assert compiler_hash == prod['outputs']['emlf']['sha256']

    locks = read('candidates/prefix-3/locks/receipt.json')
    assert locks['complete'] and locks['producer_reauthenticated_after'] and locks['immutable_nonlock_inputs_verified_after']
    assert locks['producer_sha256'] == producer_hash and len(locks['roots']) == 6
    for root in locks['roots']:
        assert root['complete'] and sha(root['lock_path']) == root['after_lock']
        assert sha(root['manifest']) == root['manifest_sha256']
        for action in ['lock', 'plan']:
            command = root[action]
            assert command['exit'] == 0
            for name in ['receipt', 'stdout', 'stderr']:
                assert sha(command[name]) == command[name + '_sha256']
    for relative, digest in locks['actual_final_lock_hashes'].items():
        assert sha(S / relative) == digest

    controls = read('validation/prefix-3/receipt.json')
    assert controls['complete'] and controls['result'] == {'complete': True, 'differential_controls': 922}
    assert controls['producer_receipt_sha256'] == producer_hash
    assert controls['authentication_before'] and controls['authentication_after'] and controls['copied_object_pins_verified']
    assert not controls['compiler_modules_rebuilt'] and len(controls['compiled_modules']) == 3 and len(controls['new_object_files']) == 6
    assert all(command['exit_code'] == 0 for command in controls['commands'])
    assert (W / 'validation/prefix-3/controls.stderr').read_bytes() == b''
    assert json.loads((W / 'validation/prefix-3/controls.stdout').read_text()) == controls['result']
    for path, digest in controls['test_input_sha256'].items():
        assert sha(path) == digest
    scoped = read('validation/prefix-3-scoped/receipt.json')
    assert scoped['complete'] and scoped['authenticated_before'] and scoped['authenticated_after']
    assert scoped['immutable_inputs_verified_after'] and scoped['producer_receipt_sha256'] == producer_hash
    assert len(scoped['frontend_modes_passed']) == 3
    assert scoped['provenance']['distinct_methods'] == 86 and scoped['provenance']['builtin_verifier_methods_included'] == 17
    assert not scoped['provenance']['separate_builtin_reexecution'] and scoped['source_smoke']['cases'] == 5
    assert sha(scoped['provenance']['receipt']) == scoped['provenance']['sha256']
    for command in scoped['commands']:
        assert command['state'] == 'passed' and command['exit_code'] == 0
        for name in ['stdout', 'stderr']:
            path = W / 'validation/prefix-3-scoped' / (command['name'] + '.' + name)
            assert sha(path) == command[name + '_sha256']
            if name == 'stderr':
                assert path.read_bytes() == b''
    for mode, expected in scoped['expected_frontend_stdout'].items():
        assert (W / 'validation/prefix-3-scoped' / ('shared-frontend-' + mode + '.stdout')).read_text() == expected

    source_check = read('validation/prefix-3-source-crates/receipt.json')
    assert source_check['complete'] and source_check['producer_authenticated_before'] and source_check['producer_authenticated_after']
    assert source_check['target_cache_initially_absent'] and source_check['immutable_inputs_verified_after']
    assert not source_check['performance_sample'] and not source_check['full_compiler_bootstrap']
    assert len(source_check['modules']) == 14
    assert source_check['query_report']['inferred_groups'] == 576 and source_check['query_report']['reused_groups'] == 0
    assert all(command['exit_code'] == 0 for command in source_check['commands'])
    for path, digest in source_check['source_pins'].items():
        assert sha(path) == digest

    performance = read('evidence/candidate-prefix-3-performance.json')
    background = read('evidence/prefix-3-background-exposure.json')
    assert not background['clean_exclusive_ABBA_claim'] and not performance['goal_met']
    for path, digest in performance['inputs'].items():
        assert sha(path) == digest
    samples = {}

    def run_review(label, expected_compiler=None):
        receipt = W / 'runs' / label / 'receipt.json'
        r = json.loads(receipt.read_text())
        guard = read('guards/' + label + '/bounded-receipt.json')
        assert r['complete'] and r['exit_code'] == 0 and r['immutable_inputs_verified_after']
        assert r['frozen_sha256'] == sha(W / 'frozen.json')
        assert guard['complete'] and guard['exit_code'] == 0 and guard['terminal_descendants_empty']
        if expected_compiler is not None:
            assert r['compiler_sha256'] == expected_compiler
        if r['side'] == 'mlf':
            assert r['target_cache_initially_absent'] and r['byte_identical_to_prior']
            assert r['query_report']['inferred_groups'] == 544 and r['query_report']['reused_groups'] == 0
        return {'label': label, 'wall_seconds': r['wall_seconds'], 'receipt_sha256': sha(receipt),
                'guard_receipt_sha256': sha(W / 'guards' / label / 'bounded-receipt.json'),
                'max_individual_child_rss_bytes': r['max_individual_child_rss_bytes'],
                'guard_peak_tree_rss_bytes': guard['peak_group_rss'], 'compiler_sha256': r['compiler_sha256']}

    for side in ['mlf', 'ghc']:
        samples[side] = [run_review('prefix-3-' + side + '-' + str(n), compiler_hash if side == 'mlf' else None) for n in [1, 2, 3]]
        assert [x['wall_seconds'] for x in samples[side]] == [x['wall_seconds'] for x in performance['samples'][side]]
    medians = {side: statistics.median(x['wall_seconds'] for x in values) for side, values in samples.items()}
    assert medians == performance['medians']
    assert medians['mlf'] / medians['ghc'] == performance['ratio_to_contemporaneous_ghc']
    quiet = run_review('prefix-3-control-clean-1', compiler_hash)
    quiet_auth = read('runs/prefix-3-control-clean-1/candidate-authentication.json')
    assert quiet_auth['complete'] and quiet_auth['authentication_before'] and quiet_auth['authentication_after']
    assert quiet_auth['qualified_producer_receipt_sha256'] == producer_hash
    screen_build = read('compilers/screen-prefix-index-4-r2/receipt.json')
    assert screen_build['complete'] and not screen_build['qualified'] and screen_build['seed_receipt_sha256'] == producer_hash
    screen = run_review('screen-prefix-index-4-r2-mlf-1', screen_build['binary_sha256'])
    screen_summary = read('evidence/prefix-index-4-screen.json')
    assert screen_summary['complete'] and not screen_summary['qualified_candidate'] and not screen_summary['accepted']
    assert screen_summary['recipe_sha256'] == sha(W / 'recipes/summarize_index_screen.py')
    for row, result in zip(screen_summary['rows'], [screen, quiet], strict=True):
        assert row['label'] == result['label'] and row['wall_seconds'] == result['wall_seconds']
        assert row['receipt_sha256'] == result['receipt_sha256'] and row['guard_sha256'] == result['guard_receipt_sha256']

    archive_guard = read('guards/archive-completed-3/bounded-receipt.json')
    assert archive_guard['complete'] and archive_guard['exit_code'] == 0 and archive_guard['terminal_descendants_empty']
    archived_labels = archive_guard['command'][3:]
    assert len(archived_labels) == 13 and len(set(archived_labels)) == 13
    archives = []
    for label in archived_labels:
        record_path = W / 'runs' / label / 'queries-archive.json'
        record = json.loads(record_path.read_text())
        assert record['complete'] and record['copies_removed'] and record['all_member_hashes_verified']
        assert record['recipe_sha256'] == sha(W / 'recipes/archive_completed_queries.py')
        archive_path = Path(record['archive'])
        assert archive_path == W / 'runs' / label / 'queries.tar.gz'
        assert not (archive_path.parent / 'queries').exists()
        assert sha(archive_path) == record['archive_sha256'] and archive_path.stat().st_size == record['archive_bytes']
        assert sum(item['bytes'] for item in record['files'].values()) == record['original_file_bytes']
        archives.append({key: record[key] for key in ['label', 'archive_sha256', 'archive_bytes', 'original_file_bytes', 'all_member_hashes_verified']}
                        | {'receipt_sha256': sha(record_path), 'compressed_archive_hash_reverified': True})
    assert all((W / 'runs' / f'baseline-mlf-{n}' / 'queries').is_dir() for n in [1, 2, 3])

    ancestry_path = W / 'candidates/prefix-index-4/base-prefix-3-before-locks.patch'
    ancestry_hash = sha(ancestry_path)
    assert ancestry_hash == '6a22ec8d14b769348723cf28e7c773229c6ab4c21010ee42f9a95408f07b3db3'
    ancestry_copy = C / 'pre-lock-source-ancestry.patch'
    assert not ancestry_copy.exists()
    ancestry_copy.write_bytes(ancestry_path.read_bytes())
    patch_path = C / 'pr25-plus-fixes-plus-namespace-plus-fingerprint-plus-prefix-plus-locks.patch'
    assert not patch_path.exists()
    patch_path.write_bytes(subprocess.check_output(['git', '-C', str(S), 'diff', '--binary', 'HEAD']))
    check = subprocess.run(['git', '-C', str(W.parent / 'pr25-latest-benchmark-20261026'), 'apply', '--check', str(patch_path)], capture_output=True, text=True)
    assert check.returncode == 0, check.stderr
    changed = subprocess.check_output(['git', '-C', str(S), 'diff', '--name-only', 'HEAD'], text=True).splitlines()
    assert len(changed) == 16 and not any('Lexer' in name for name in changed)

    review = {
        'format': 'mlf-crates-candidate3-final-review-v1', 'complete': True, 'candidate': 'prefix-3',
        'status': 'accepted scoped optimization; observed performance with background-exposure caveat; goal not met',
        'base_commit': BASE,
        'portable_patch': {'path': str(patch_path), 'sha256': sha(patch_path), 'bytes': patch_path.stat().st_size,
                           'paths': changed, 'git_apply_check_against_pristine_base': True},
        'preserved_prelock_ancestry': {'original': str(ancestry_path), 'copy': str(ancestry_copy), 'sha256': ancestry_hash},
        'producer_receipt_sha256': producer_hash, 'compiler_sha256': compiler_hash,
        'verified_current_source_pins': pins,
        'producer_scope': {'actual_inferred_interfaces': 121, 'shared_syntax': 121, 'tools': 13, 'canonical_builtin_fresh_regeneration': True},
        'samples': samples, 'observed_medians': medians, 'observed_ratio': medians['mlf'] / medians['ghc'],
        'three_times_target_seconds': 3 * medians['ghc'], 'goal_met': False,
        'background_exposure': {'receipt_sha256': sha(W / 'evidence/prefix-3-background-exposure.json'),
                                'clean_exclusive_ABBA_claim': False, 'description': background['description'],
                                'no_penalty_subtraction_or_adjusted_median': True},
        'quiet_control': {**quiet, 'sample_count': 1, 'not_a_median_or_final_goal_verification': True},
        'frozen_performance_target': {'modules': 14, 'inferred_groups': 544, 'reused_groups': 0,
                                      'checked_hashes_identical_to_reference_all_three_and_quiet_control': True},
        'controls': {'independent_prefix_checks': 922, 'receipt_sha256': sha(W / 'validation/prefix-3/receipt.json'),
                     'scoped_receipt_sha256': sha(W / 'validation/prefix-3-scoped/receipt.json'),
                     'frontend_modes': 3, 'provenance_distinct_methods': 86,
                     'builtin_verifier_methods_included_once': 17, 'source_smoke_cases': 5},
        'actual_optimized_source_validation': {'receipt_sha256': sha(W / 'validation/prefix-3-source-crates/receipt.json'),
             'modules': 14, 'inferred_groups': 576, 'reused_groups': 0, 'metadata_reload_passed': True,
             'performance_sample': False, 'artifacts': source_check['artifacts'],
             'input_distinction': 'Actual optimized source, not unchanged performance input; different checked artifact bytes expected.'},
        'locks': {'receipt_sha256': sha(W / 'candidates/prefix-3/locks/receipt.json'), 'roots': 6,
                  'all_lock_and_offline_locked_plan_commands_exit_zero': True,
                  'actual_final_lock_hashes': locks['actual_final_lock_hashes']},
        'negative_graph_screen_appendix': {**screen, 'build_receipt_sha256': sha(W / 'compilers/screen-prefix-index-4-r2/receipt.json'),
             'summary_sha256': sha(W / 'evidence/prefix-index-4-screen.json'),
             'qualified': False, 'accepted': False, 'sample_count': 1,
             'interpretation': 'One graph-overlay screen was slower than one quiet P3 control; no observed gain, no causal effect or candidate4 acceptance claim. Not included in P3 medians.'},
        'query_archival_extension': {'runs': archives, 'new_archives': 13, 'previously_recorded_in_v2': 6,
             'guard_receipt_sha256': sha(W / 'guards/archive-completed-3/bounded-receipt.json'),
             'archive_bodies_included': False,
             'scope': 'Storage-only lossless archival; writer verified every member byte before removing redundant expanded copies. Compressed archive hashes rechecked here, not decompressed again. Checked units remain outside archival, no archive reuse for inference. Original three baseline query directories remain expanded.'},
        'historical_authorship_status': 'Frozen candidate/control/oracle manifests and DESIGN.txt predate execution; their not-built/not-run text is intentionally preserved. Completed receipts and this review supersede those status descriptions only.',
        'limits': [
            'Three observed samples per compiler are not a clean exclusive ABBA causal experiment; short read-only parsers/file comparisons overlapped parts of the sequence. No exact timing penalty is inferred.',
            'The later quiet control is one sample, not a replacement median. Final decisive goal verification requires a quiet serialized comparison.',
            'GHC plain -O2 objects versus MLF independently checked xMLF and query-cache publication are asymmetric endpoints.',
            'No target inference reuse, dependency builds excluded, OS page cache not flushed.',
            'Receipt/source review only, not a new replay of tests or rehash of every large artifact; checked byte equality is established by authenticated completed run receipts.',
            'No full 74-module MLF compiler bootstrap, native-unit/parity/LLVM-runtime campaign, complete repository qualification or self-host fixed-point claim.',
            'No new P3 cost-centre/phase profile is claimed. The inherited v2 profile describes candidate2, not candidate3.',
        ],
    }
    review_path = C / 'candidate3-final-review.json'
    write(review_path, review)
    results_path = C / 'RESULTS-candidate3.txt'
    assert not results_path.exists()
    results_path.write_text('''MLF-CRATES CANDIDATE 3 — SCOPED QUALIFICATION; GOAL NOT MET

Pinned PR25 aa11ffd318a2efa5be9805524710d0677eedb86f + approved fixes +
accepted namespace/fingerprint changes, then immutable datatype-prefix sharing.
Exact structural equality guards reused encodings; mismatches fall back to the
actual declaration. Existing public no-pool APIs retain their original route;
the optimized pool is enabled only for parsed/decoded file-producer inputs.
Checks, format bytes, source keys and negative-state fallback remain controlled.
No Lexer change, removed checks or target inference reuse.

Same frozen 14 source modules, reused authenticated dependencies:
  GHC 9.14.1 plain -O2: 8.375098285, 7.592379489, 7.986013657 s
  GHC-hosted MLF:      93.838002607, 88.601739724, 88.175150620 s
  OBSERVED medians:   GHC 7.986013657 s; MLF 88.601739724 s
  OBSERVED ratio:     11.0946141003x; current 3x threshold 23.958040971 s

Mandatory measurement caveat: short read-only research parsers/file comparisons
overlapped parts of this sequence. These samples are preserved, NOT represented
as a clean exclusive causal ABBA experiment; no estimated penalty is subtracted.
A later quiet P3 control took 88.335022101 s: ONE sample, not a new median or
final goal proof. GHC emits -O2 objects; MLF independently checked xMLF plus
query-cache files. Endpoints differ; OS page cache was not flushed.
Every P3 performance/control target run inferred 544 groups, reused 0, and
matched the reference checked artifact bytes.

Qualification passed: official GHC producer (121 inferred interfaces, 121 shared
syntax modules, 13 tools, exact builtin regeneration); 922 independent prefix
byte/digest/Unicode/error/laziness controls; three maintained frontend modes;
86 DISTINCT provenance methods INCLUDING 17 builtin methods once; five source
smoke cases; six authentic offline locks and --locked plans.
Separately, MLF compiled the ACTUAL optimized 14-module source (576 inferred,
0 reused), independently checked it and reloaded metadata. This is different
input for source compatibility, NOT a performance sample or full bootstrap.

Negative appendix only: the unqualified candidate4 graph-overlay screen took
89.407815682 s versus the one quiet P3 control's 88.335022101 s. No observed gain;
one sample each cannot establish a causal effect. Candidate4 is NOT accepted
and does not enter P3 medians or the portable accepted-source patch.

No new P3 phase profile is claimed; the inherited v2 profile is candidate2's.
No full 74-module MLF compiler bootstrap, native-unit/parity/LLVM-runtime or
self-host fixed-point claim. Work toward <=3x continues separately.

Storage-only archival: 13 further completed run query directories (P3, controls,
diagnostic profiles and the negative screen) were losslessly archived; with six
recorded in v2, 19 are locally restorable. Every member was verified before
redundant expanded copies were removed. Original baseline query directories
remain expanded. Only archive manifests/receipts enter this package, not archive
bodies; checked unit artifacts are untouched and no archives are reused for inference.

Portable full patch applies to pristine pinned PR25:
  ''' + patch_path.name + '\n  SHA256 ' + sha(patch_path) + '''
The original 6a22ec8d... pre-lock patch used as candidate4 ancestry is untouched
and copied as pre-lock-source-ancestry.patch. Detailed pins and caveats are in
candidate3-final-review.json. Historical pre-run control status text is retained
unchanged; completed receipts and this review supersede that status only.
''')

    previous = W / 'deliverables/mlf-crates-profile-20261026-v2.zip'
    previous_receipt = read('deliverables/mlf-crates-profile-20261026-v2.receipt.json')
    assert previous_receipt['complete'] and previous_receipt['total_members'] == 704
    assert sha(previous) == previous_receipt['sha256'] == '939d83caeedcb9f325f97f09129d9d78506903d7c795127e83bc62c74eb72a14'
    with zipfile.ZipFile(previous) as archive:
        # Read only the small manifest; full old-member hashing is deferred.
        manifest_bytes = archive.read('CANDIDATE2-MANIFEST.json')
        old_manifest = json.loads(manifest_bytes)
        base_members = {**old_manifest['original_members'], **old_manifest['candidate2_files'],
                        'CANDIDATE2-MANIFEST.json': {'sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'bytes': len(manifest_bytes)}}
        assert len(base_members) == 704 and set(archive.namelist()) == set(base_members)
        assert all(archive.getinfo(name).file_size == entry['bytes'] for name, entry in base_members.items())

    files = set()

    def add(relative):
        path = W / relative
        assert path.is_file() and not path.is_symlink(), relative
        assert path.stat().st_size < 64 * 1024 * 1024, relative
        files.add(relative)

    def tree(relative):
        for path in (W / relative).rglob('*'):
            if path.is_file():
                add(str(path.relative_to(W)))

    for path in [patch_path, ancestry_copy, review_path, results_path, C / 'pre-generation-full.patch']:
        add(str(path.relative_to(W)))
    tree('candidates/prefix-3/builtin-generation')
    tree('candidates/prefix-3/locks')
    for path in P.iterdir():
        if path.is_file() and (path.suffix in ['.log', '.json', '.txt']):
            add(str(path.relative_to(W)))
    tree('candidates/prefix-3/producer/builtin-verification')
    for path in (W / 'optimization-research/prefix').iterdir():
        if path.is_file() and path.name not in ['provisional-s2-base.patch', 'provisional-s2-base.json']:
            add(str(path.relative_to(W)))
    for name in ['receipt.json', 'build.stdout', 'build.stderr', 'controls.stdout', 'controls.stderr']:
        add('validation/prefix-3/' + name)
    tree('validation/prefix-3-scoped')
    for name in ['receipt.json', 'recipe.py', 'crate.spec', 'compile.stdout', 'compile.stderr', 'metadata-reload.stdout', 'metadata-reload.stderr']:
        add('validation/prefix-3-source-crates/' + name)
    run_labels = ['prefix-3-' + side + '-' + str(n) for side in ['mlf', 'ghc'] for n in [1, 2, 3]]
    run_labels += ['prefix-3-control-clean-1', 'screen-prefix-index-4-r2-mlf-1', 'fingerprint-2-controlA-1', 'fingerprint-2-controlA-2']
    for label in run_labels:
        for name in ['receipt.json', 'recipe.py', 'stdout', 'stderr', 'crate.spec', 'candidate-authentication.json']:
            if (W / 'runs' / label / name).is_file():
                add('runs/' + label + '/' + name)
        add('guards/' + label + '/bounded-receipt.json')
    for label in ['prefix-3-generate', 'prefix-3-qualified', 'prefix-3-controls', 'prefix-3-scoped', 'prefix-3-source-crates', 'prefix-3-locks', 'screen-prefix-index-4-r2-build', 'screen-prefix-index-4-build', 'archive-completed-3']:
        for name in ['bounded-receipt.json', 'build.log']:
            if (W / 'guards' / label / name).is_file():
                add('guards/' + label + '/' + name)
    for name in ['receipt.json', 'recipe.py', 'build.log']:
        add('compilers/screen-prefix-index-4-r2/' + name)
        if (W / 'compilers/screen-prefix-index-4' / name).is_file():
            add('compilers/screen-prefix-index-4/' + name)
    for label in archived_labels:
        add('runs/' + label + '/queries-archive.json')
    for relative in ['evidence/candidate-prefix-3-performance.json', 'evidence/prefix-3-background-exposure.json',
                     'evidence/prefix-index-4-screen.json', 'recipes/summarize_index_screen.py',
                     'recipes/archive_completed_queries.py',
                     'recipes/prepare_candidate3_milestone.py', 'recipes/package_candidate3_milestone.py',
                     'recipes/run_scoped_frontend_controls.py']:
        add(relative)
    additions = [{'source_path': str(W / relative), 'archive_path': 'candidate3/' + relative,
                  'sha256': sha(W / relative), 'bytes': (W / relative).stat().st_size} for relative in sorted(files)]
    assert not any('/queries/' in entry['archive_path'] or entry['archive_path'].endswith(('queries.tar.gz', '.o', '.hi')) for entry in additions)
    plan = {
        'format': 'mlf-crates-candidate3-package-plan-v1', 'review_complete': True,
        'scope': 'All preoptimization/candidate1/candidate2 evidence preserved byte-identically, plus scoped candidate3 source/controls/observed timings and mandatory background caveat. One quiet control and a negative unqualified candidate4 screen are not medians or acceptance/goal proof.',
        'base_archive': {'path': str(previous), 'sha256': sha(previous), 'members': base_members},
        'additions': additions,
        'limits': {'max_members': 1100, 'max_added_member_bytes': 64 * 1024 * 1024,
                   'max_total_uncompressed_bytes': 288 * 1024 * 1024, 'max_archive_bytes': 48 * 1024 * 1024},
        'exclusions': ['All query-cache bodies/archives, compiler binaries and .o/.hi files, large target/dependency artifacts.',
                       'No new large CCS data or candidate3 profile; existing version2 evidence is preserved.',
                       'Unaccepted candidate4 implementation is not part of the accepted source patch; only explicitly negative screening build/run receipts retained.',
                       'Private notes, transfer credentials, unrelated bootstrap and in-progress research.'],
        'suggested_output': str(W / 'deliverables/mlf-crates-profile-20261026-v3.zip'),
        'library_action': 'Not performed. Parent owns serial compression/validation and later replacement of libfile_45e997db214c819189d53d311b1aa13a at expected current version2.',
    }
    assert 704 + len(additions) + 1 <= plan['limits']['max_members']
    base_bytes = sum(x['bytes'] for x in base_members.values())
    added_bytes = sum(x['bytes'] for x in additions)
    assert base_bytes + added_bytes + 1024 * 1024 < plan['limits']['max_total_uncompressed_bytes']
    plan_path = W / 'deliverables/candidate3-package-plan.json'
    write(plan_path, plan)
    receipt = {'complete': True, 'compression_performed': False, 'previous_zip_modified': False, 'library_invoked': False,
               'plan': str(plan_path), 'plan_sha256': sha(plan_path),
               'recipe_sha256': sha(W / 'recipes/package_candidate3_milestone.py'), 'review_recipe_sha256': sha(__file__),
               'previous_archive_members': 704, 'added_files': len(additions), 'planned_total_members': 704 + len(additions) + 1,
               'added_uncompressed_bytes': added_bytes, 'previous_uncompressed_bytes': base_bytes,
               'review_sha256': sha(review_path), 'results_sha256': sha(results_path), 'portable_patch_sha256': sha(patch_path)}
    write(W / 'deliverables/candidate3-package-plan-receipt.json', receipt)
    assert sha(ancestry_path) == ancestry_hash and sha(previous) == previous_receipt['sha256']
    assert patch_path.read_bytes() == subprocess.check_output(['git', '-C', str(S), 'diff', '--binary', 'HEAD'])
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
