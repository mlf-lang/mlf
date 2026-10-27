#!/usr/bin/env python3
"""Exact late-CCS reconciliation; no sampled-share-to-wall extrapolation."""
import argparse,collections,gzip,hashlib,json,re,statistics
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--profile',type=Path,required=True);p.add_argument('--ordinary',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert not a.output.exists();a.output.mkdir(parents=True)
sha=lambda f:hashlib.file_digest(Path(f).open('rb'),'sha256').hexdigest()
lines=a.profile.read_text().splitlines();header={}
for s in lines[:12]:
 m=re.search(r'total time\s*=\s*([\d.]+) secs\s*\((\d+) ticks @ (\d+) us, (\d+) processor',s)
 if m:header.update(rounded_cpu_seconds=float(m[1]),ticks=int(m[2]),tick_us=int(m[3]),processors=int(m[4]))
 m=re.search(r'total alloc\s*=\s*([\d,]+) bytes',s)
 if m:header['bytes']=int(m[1].replace(',',''))
assert len(header)==5
start=next(i for i,s in enumerate(lines) if s.startswith('COST CENTRE') and 'entries' in s)+1
rx=re.compile(r'^( *)(\S+)\s+(\S+)\s+(.+?)\s+(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s*$')
nodes=[];stack=[]
for ln,s in enumerate(lines[start:],start+1):
 if not s.strip():continue
 m=rx.fullmatch(s);assert m,(ln,s)
 indent,cc,module,src,ident,entries,pt,pa,it,ia,ticks,nbytes=m.groups();depth=len(indent)
 while stack and nodes[stack[-1]]['depth']>=depth:stack.pop()
 parent=stack[-1] if stack else None
 assert depth==(nodes[parent]['depth']+1 if parent is not None else 0)
 n=dict(index=len(nodes),parent=parent,depth=depth,module=module,cc=cc,source=src,ccs_id=int(ident),entries=int(entries),ticks=int(ticks),bytes=int(nbytes),subtree_ticks=int(ticks),subtree_bytes=int(nbytes),inherited_tick_percent=float(it),inherited_byte_percent=float(ia),children=[])
 if parent is not None:nodes[parent]['children'].append(n['index'])
 nodes.append(n);stack.append(n['index'])
assert sum(n['ticks'] for n in nodes)==header['ticks'] and sum(n['bytes'] for n in nodes)==header['bytes']
for n in reversed(nodes):
 if n['parent'] is not None:
  for k in ['subtree_ticks','subtree_bytes']:nodes[n['parent']][k]+=n[k]
for n in nodes:
 assert abs(n['subtree_ticks']/header['ticks']*100-n['inherited_tick_percent'])<=.05001
 assert abs(n['subtree_bytes']/header['bytes']*100-n['inherited_byte_percent'])<=.05001
empty=lambda:dict(ticks=0,bytes=0,entries=0,stacks=0)
exclusive=collections.defaultdict(empty);modules=collections.defaultdict(empty);outer=collections.defaultdict(empty)
active=collections.Counter();stack=[]
for n in nodes:
 while stack and stack[-1]['depth']>=n['depth']:
  x=stack.pop();active[(x['module'],x['cc'])]-=1
 key=(n['module'],n['cc'])
 for d in [exclusive[key],modules[n['module']]]:
  for k in ['ticks','bytes','entries']:d[k]+=n[k]
  d['stacks']+=1
 if not active[key]:
  d=outer[key];d['ticks']+=n['subtree_ticks'];d['bytes']+=n['subtree_bytes'];d['stacks']+=1
 active[key]+=1;stack.append(n)
flat_start=next(i for i,s in enumerate(lines) if s.startswith('COST CENTRE'))+1
flat_rx=re.compile(r'^(\S+)\s+(\S+)\s+(.+?)\s+([\d.]+)\s+([\d.]+)\s+(\d+)\s+(\d+)\s*$');flat=0
for s in lines[flat_start:start-2]:
 m=flat_rx.fullmatch(s)
 if m:
  cc,mod,src,pt,pa,t,b=m.groups();d=exclusive[(mod,cc)]
  assert d['ticks']==int(t) and d['bytes']==int(b);flat+=1
def table(d):return [dict(module=k[0],cc=k[1],**v) for k,v in sorted(d.items(),key=lambda kv:-kv[1]['ticks'])]
ordinary=[]
for f in a.ordinary:
 j=json.loads(f.read_text());assert j['complete'] and j['byte_identical_to_prior']
 assert j['query_report']['inferred_groups']==544 and j['query_report']['reused_groups']==0
 ordinary.append(dict(path=str(f),sha256=sha(f),wall_seconds=j['wall_seconds']))
r=json.loads((a.profile.parent/'receipt.json').read_text());assert r['complete'] and r['byte_identical_to_prior']
assert r['query_report']['inferred_groups']==544 and r['query_report']['reused_groups']==0
med=statistics.median(j['wall_seconds'] for j in ordinary)
report=dict(format='exact-candidate-late-ccs-v1',profile=str(a.profile),profile_sha256=sha(a.profile),header=header,parsed_rows=len(nodes),flat_exact_rows_verified=flat,
 reconciliation='All exclusive integer ticks/bytes sum exactly to header; inherited columns agree within rounding.',
 exclusive_functions=table(exclusive),exclusive_modules=[dict(module=k,**v) for k,v in sorted(modules.items(),key=lambda kv:-kv[1]['ticks'])],
 function_outer_root_subtrees_NOT_ADDITIVE=table(outer),ordinary=ordinary,
 diagnostic_wall_seconds=r['wall_seconds'],ordinary_median_seconds=med,diagnostic_wall_ratio=r['wall_seconds']/med,
 query_validation=dict(inferred=544,reused=0,checked_bytes_identical=True),
 caveats=['CCS follows lazy evaluation ownership, not exact chronological stages.', 'Subtree functions overlap and are NOT additive.', 'Do not multiply shares by ordinary wall or divide diagnostic timings by overhead ratio.', 'Allocated bytes exclude profiling overhead per GHC header and are not retained memory.', 'Late profiling has separately measured whole-program overhead.'],
 recipe_sha256=sha(__file__))
(a.output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
with gzip.GzipFile(filename='',mode='wb',fileobj=(a.output/'ccs-tree.json.gz').open('wb'),mtime=0) as out:out.write(json.dumps(dict(header=header,nodes=nodes),separators=(',',':')).encode())
(a.output/'recipe.py').write_bytes(Path(__file__).read_bytes())
print(json.dumps({k:v for k,v in report.items() if k not in ['exclusive_functions','exclusive_modules','function_outer_root_subtrees_NOT_ADDITIVE']},indent=2))
