#!/usr/bin/env python3
import hashlib,json,re
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
out=W/'evidence/fingerprint-2-rts-screening.json';assert not out.exists()
build=W/'compilers/fingerprint-2-rts/receipt.json';b=json.loads(build.read_text());assert b['complete'] and b['non_main_objects_byte_identical']
rows=[]
for label in ['profile-fingerprint-2-rts-default-1','profile-fingerprint-2-rts-A16m-1']:
 p=W/'runs'/label;r=json.loads((p/'receipt.json').read_text());s=(p/'stderr').read_text()
 assert r['complete'] and r['byte_identical_to_prior'] and r['query_report']['inferred_groups']==544 and r['query_report']['reused_groups']==0
 def number(pattern):return int(re.search(pattern,s).group(1).replace(',',''))
 phases={name:{'cpu_seconds_rounded':float(cpu),'elapsed_seconds_rounded':float(wall)} for name,cpu,wall in re.findall(r'^\s*(INIT|MUT|GC|EXIT|Total)\s+time\s+([\d.]+)s\s+\(\s*([\d.]+)s elapsed\)',s,re.M)}
 rows.append(dict(label=label,wall_seconds=r['wall_seconds'],GHCRTS=r['environment']['GHCRTS'],max_individual_child_rss_bytes=r['max_individual_child_rss_bytes'],allocated_bytes=number(r'([\d,]+) bytes allocated in the heap'),copied_bytes=number(r'([\d,]+) bytes copied during GC'),sampled_max_residency_bytes=number(r'([\d,]+) bytes maximum residency'),phases=phases,receipt_sha256=sha(p/'receipt.json'),stderr_sha256=sha(p/'stderr')))
j=dict(complete=True,kind='Single-process RTS configuration screening; not accepted production optimization',build_receipt_sha256=sha(build),non_main_object_files_identical=len(b['unchanged_non_main_object_files']),samples=rows,A16m_to_default_wall_ratio=rows[1]['wall_seconds']/rows[0]['wall_seconds'],decision='Do not promote A16m: this screen reduced GC but increased overall wall and mutator time. Original production RTS policy unchanged.',limits=['One sample per configuration, not a median or ABBA causal claim.','Ordinary source-level medians remain separate.','RTS elapsed/cpu times rounded; maximum residency is sampled at major GC, not continuous peak.','The printed %GC 0.0 field is not used; explicit GC and total timings are retained.','Both runs inferred544/reused0 and checked artifacts are byte-identical.'],recipe_sha256=sha(__file__))
out.write_text(json.dumps(j,indent=2)+'\n');print(json.dumps(j,indent=2))
