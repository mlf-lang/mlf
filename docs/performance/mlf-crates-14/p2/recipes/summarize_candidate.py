#!/usr/bin/env python3
"""Summarize complete frozen full-target samples, not component timings."""
import argparse,hashlib,json,statistics
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('candidate');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert not a.output.exists()
P=W/'candidates'/a.candidate/'producer'
r=json.loads((P/'receipt.json').read_text());assert r['complete']
samples={};pins={str(P/'receipt.json'):sha(P/'receipt.json')}
for side in ['mlf','ghc']:
    samples[side]=[]
    for i in [1,2,3]:
        run=W/'runs'/f'{a.candidate}-{side}-{i}';j=json.loads((run/'receipt.json').read_text())
        assert j['complete'] and j['immutable_inputs_verified_after']
        pins[str(run/'receipt.json')]=sha(run/'receipt.json')
        if side=='mlf':
            auth=json.loads((run/'candidate-authentication.json').read_text());assert auth['complete']
            assert j['byte_identical_to_prior'] and j['target_cache_initially_absent']
            assert j['query_report']['inferred_groups']==544 and j['query_report']['reused_groups']==0
            pins[str(run/'candidate-authentication.json')]=sha(run/'candidate-authentication.json')
        else:assert j['plain_o2'] and len(j['compiled_modules'])==14 and j['dependency_objects_unchanged']
        samples[side].append({k:j[k] for k in ['label','wall_seconds','child_user_seconds','child_system_seconds','max_individual_child_rss_bytes']})
medians={side:statistics.median(j['wall_seconds'] for j in ss) for side,ss in samples.items()}
j=dict(format='full14-candidate-performance-v1',candidate=a.candidate,
       status='performance_complete_qualification_status_separate',samples=samples,medians=medians,
       ratio_to_contemporaneous_ghc=medians['mlf']/medians['ghc'],three_times_target_seconds=3*medians['ghc'],
       goal_met=medians['mlf']<=3*medians['ghc'],all_mlf_checked_artifacts_identical=True,all_mlf_544_inferred_0_reused=True,
       samples_interleaved_between_compilers=True,inputs=pins,recipe_sha256=sha(__file__),
       caveats=['GHC plain -O2 objects versus MLF independently checked xMLF plus query-cache files: asymmetric endpoints.',
                'Separate version medians are not ABBA-paired optimization effect estimates.',
                'No full native compiler bootstrap or complete repository qualification is implied.'])
a.output.write_text(json.dumps(j,indent=2)+'\n');print(json.dumps({k:v for k,v in j.items() if k not in ['samples','inputs']},indent=2))
