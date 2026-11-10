#!/usr/bin/env python3
"""Expand only saturated Graph.readDense uses, preserving the public helper.

Input is exact f9 Graph. No writes, partial applications, GHC pragmas, primitive
implementations or compiler flags are changed. Emits a reversible site manifest.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

ORIGINAL='9df4833f55f0826181f8e1e974dc0672753e9462de0d134f64fc3f8c6f6e8a7f'
OWNER='libraries/mlf-inference/Bootstrap/Graph.hs'
PATTERN=re.compile(r'\breadDense\s+([A-Za-z_][A-Za-z_0-9]*)\s+([A-Za-z_][A-Za-z_0-9]*)\s+([A-Za-z_][A-Za-z_0-9]*)')
def sha(raw):return hashlib.sha256(raw).hexdigest()

def transform(raw):
 assert sha(raw)==ORIGINAL,'exact frozen Graph required'
 text=raw.decode();matches=list(PATTERN.finditer(text))
 assert len(matches)==55 and len(re.findall(r'\breadDense\b',text))==56
 assert matches[0].group()=='readDense low array identity' and text[matches[0].end():].startswith(' = readSTArray array (identity - low);')
 calls=matches[1:];assert len(calls)==54
 changes=[];delta=0
 for m in calls:
  low,array,identity=m.groups()
  assert low=='low' and text[m.end():].startswith((')',';')),'only saturated variable-argument calls'
  prior=list(re.finditer(r'^  ([A-Za-z_][A-Za-z_0-9]*) ::',text[:m.start()],re.M))
  owner=prior[-1].group(1)
  replacement=f'readSTArray {array} ({identity} - {low})'
  changes.append(dict(line=text.count('\n',0,m.start())+1,function=owner,
    original_start=m.start(),transformed_start=m.start()+delta,before=m.group(),after=replacement))
  delta+=len(replacement)-len(m.group())
 result=text
 for row in reversed(changes):
  a=row['original_start'];result=result[:a]+row['after']+result[a+len(row['before']):]
 restored=result
 for row in reversed(changes):
  a=row['transformed_start'];assert restored[a:a+len(row['after'])]==row['after']
  restored=restored[:a]+row['before']+restored[a+len(row['after']):]
 assert restored==text and len(re.findall(r'\breadDense\b',result))==2
 # The sibling parent-replay candidate is deliberately absent.
 assert 'ST.bindE (densePlaces state ps)' in result
 return result.encode(),dict(baseline_ref='f9bdb40a659bfdff4cbb782d438afbb0417dd2e1',owner=OWNER,
    before_sha256=sha(raw),after_sha256=sha(result.encode()),saturated_calls=54,
    public_helper_unchanged=True,write_helpers_and_calls_unchanged=True,
    parent_replay_candidate_included=False,reversible_exact_bytes=True,sites=changes)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,required=True)
 p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();raw=(a.source/OWNER).read_bytes();changed,manifest=transform(raw)
 a.output.mkdir(parents=True,exist_ok=False)
 (a.output/'Graph.hs').write_bytes(changed)
 (a.output/'sites.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({k:v for k,v in manifest.items() if k!='sites'},indent=2))
if __name__=='__main__':main()
