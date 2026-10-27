#!/usr/bin/env python3
import hashlib,json,statistics
from pathlib import Path
W=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
arms={}
for arm,prefix in [('ghc','baseline-make-ghc-'),('mlf','baseline-mlf-')]:
 rows=[]
 for i in range(1,4):
  name=prefix+str(i); p=W/'runs'/name/'receipt.json';r=json.loads(p.read_text());g=json.loads((W/'guards'/name/'bounded-receipt.json').read_text())
  assert r['complete'] and g['complete'] and r['immutable_inputs_verified_after']
  row={k:r.get(k) for k in ['label','wall_seconds','child_user_seconds','child_system_seconds','max_individual_child_rss_bytes','byte_identical_to_prior']}
  row.update(receipt_sha256=sha(p),sampled_peak_process_tree_rss_bytes=g['peak_group_rss'])
  if arm=='mlf':
   q=r['query_report'];assert q['inferred_groups']==544 and q['reused_groups']==0 and len(q['groups'])==544
   assert r['byte_identical_to_prior']
   row.update(inferred_groups=544,reused_groups=0,output_artifacts=r['output_artifacts'])
  else:assert len(r['compiled_modules'])==14 and r['dependency_objects_unchanged']
  rows.append(row)
 times=[r['wall_seconds'] for r in rows];median=statistics.median(times)
 arms[arm]=dict(samples=rows,median_wall_seconds=median,range_seconds=[min(times),max(times)],mad_seconds=statistics.median(abs(t-median) for t in times))
result=dict(format=1,scope='Same frozen14 mlf-crates modules; compiled dependencies reused, target inference cold',
 variant='PR25+approved local fixes',frozen_manifest_sha256=sha(W/'frozen.json'),arms=arms,
 mlf_over_ghc=arms['mlf']['median_wall_seconds']/arms['ghc']['median_wall_seconds'],
 goal_mlf_wall_seconds=3*arms['ghc']['median_wall_seconds'],target_met=False,
 flags='GHC9.14.1 --make -no-link -j1 -O2 -fpedantic-bottoms -fno-state-hack; baseline MLF producer uses same optimization/demand flags, default serial RTS; no OS cache flush.',
 asymmetry='GHC emits optimized native objects; MLF emits independently checked xMLF crate and persists new query results, not native objects.',
 caveats=['3 samples describe this host; no confidence interval.','First MLF run predates CPU/rusage instrumentation; CPU not retroactively invented.','All cold-group counts and byte identity independently post-audited, including first run.','First batch watchdog output-growth root covered logs only; RSS,wall,AS,hostmemory and global disk-reserve guards were active. Fixed watchdog monitors actual outputs for subsequent runs.','GHC one-shot10.9417s and verbose--make9.0096s exploratory results excluded from ordinary median.','Historical user128.58/5.67 measurements have no independently verified command/revision and were not pooled.'])
out=W/'evidence/baseline-summary.json';out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['mlf_over_ghc','goal_mlf_wall_seconds','target_met']},indent=2))
