#!/usr/bin/env python3
"""Record the unsuccessful, single-pair bulk-index screen without promotion."""
import hashlib,json
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
labels=['screen-prefix-index-4-r2-mlf-1','prefix-3-control-clean-1']
rows=[]
for label in labels:
 p=W/'runs'/label/'receipt.json';r=json.loads(p.read_text())
 g=W/'guards'/label/'bounded-receipt.json';guard=json.loads(g.read_text())
 assert r['complete'] and r['target_cache_initially_absent'] and r['byte_identical_to_prior']
 assert r['query_report']['inferred_groups']==544 and r['query_report']['reused_groups']==0
 assert guard['complete'] and guard['terminal_descendants_empty']
 rows.append(dict(label=label,wall_seconds=r['wall_seconds'],started_utc=r['started_utc'],
   max_individual_child_rss_bytes=r['max_individual_child_rss_bytes'],
   inferred_groups=544,reused_groups=0,checked_artifacts=r['output_artifacts'],
   receipt_sha256=sha(p),guard_sha256=sha(g)))
out=W/'evidence'/'prefix-index-4-screen.json';assert not out.exists()
record=dict(complete=True,qualified_candidate=False,accepted=False,
 scope='Frozen 14 mlf-crates modules, dependency-reused, target-inference cold, serial threads',
 method='One source-overlay diagnostic screen followed by one qualified P3 control; not a median or causal ABBA result',
 conclusion='No measured gain in this single pair; do not promote the bulk reverse-index implementation from this evidence',
 rows=rows,screen_divided_by_control=rows[0]['wall_seconds']/rows[1]['wall_seconds'],
 pending='The 2985 authored differential controls were not executed; official producer qualification was not performed',
 failed_first_build='Preserved screen-prefix-index-4 build failed on one extra closing parenthesis before any target run; r2 changes that character only',
 endpoint_asymmetry='GHC comparator produces -O2 objects; MLF produces independently checked xMLF and query caches',
 recipe_sha256=sha(__file__))
out.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record,indent=2))
