#!/usr/bin/env python3
"""Losslessly archive only this task's completed fresh-target query outputs.

Never touches dependencies, source trees, checked crate artifacts or prior task
evidence. Run serially between experiments. Every file is verified byte-for-byte
before removal of its redundant uncompressed copy; archives are never reused as
target inference input. Explicit --remove-verified-copies is required.
"""
import argparse,gzip,hashlib,json,shutil,tarfile,time
from pathlib import Path
W=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
p=argparse.ArgumentParser();p.add_argument('labels',nargs='+');p.add_argument('--remove-verified-copies',action='store_true');a=p.parse_args()
for label in a.labels:
 assert '/' not in label and label not in ['.','..']
 run=W/'runs'/label;receipt=run/'receipt.json';r=json.loads(receipt.read_text())
 assert r['complete'] and r['side']=='mlf' and r['target_cache_initially_absent'] and r['byte_identical_to_prior']
 assert r['frozen_sha256']==sha(W/'frozen.json') and r['query_report']['inferred_groups']==544 and r['query_report']['reused_groups']==0
 guard=W/'guards'/label/'bounded-receipt.json';g=json.loads(guard.read_text())
 assert g['complete'] and g['exit_code']==0 and g['terminal_descendants_empty']
 root=run/'queries';assert root.is_dir() and not root.is_symlink()
 archive=run/'queries.tar.gz';record=run/'queries-archive.json';assert not archive.exists() and not record.exists()
 files={};dirs=[]
 for f in sorted(root.rglob('*')):
  assert not f.is_symlink() and f.resolve().is_relative_to(root.resolve()),f
  rel=str(f.relative_to(run))
  if f.is_dir():dirs.append(rel)
  else:
   assert f.is_file(),f
   files[rel]=dict(sha256=sha(f),bytes=f.stat().st_size)
 pins={str(receipt):sha(receipt),str(guard):sha(guard),str(run/'unit.mlfci'):sha(run/'unit.mlfci'),str(run/'unit.mlfco'):sha(run/'unit.mlfco')}
 j=dict(complete=False,label=label,scope='Lossless archival of completed task-owned query outputs only; not reused for inference',
        inputs=pins,files=files,directories=['queries',*dirs],recipe_sha256=sha(__file__),copies_removed=False)
 def save():record.write_text(json.dumps(j,indent=2)+'\n')
 save();started=time.monotonic()
 with archive.open('xb') as raw,gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0,compresslevel=1) as compressed,tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT) as tar:
  tar.add(root,arcname='queries',recursive=False)
  for name in sorted([*dirs,*files]):tar.add(run/name,arcname=name,recursive=False)
 observed={};observed_dirs=[]
 with tarfile.open(archive,'r:gz') as tar:
  for member in tar:
   assert not member.issym() and not member.islnk()
   if member.isdir():observed_dirs.append(member.name);continue
   assert member.isfile() and member.name in files
   stream=tar.extractfile(member);observed[member.name]=dict(sha256=hashlib.file_digest(stream,'sha256').hexdigest(),bytes=member.size)
 assert observed==files and sorted(observed_dirs)==sorted(j['directories'])
 for name,v in files.items():assert sha(run/name)==v['sha256'] and (run/name).stat().st_size==v['bytes']
 for path,h in pins.items():assert sha(path)==h
 j.update(archive=str(archive),archive_sha256=sha(archive),archive_bytes=archive.stat().st_size,original_file_bytes=sum(v['bytes'] for v in files.values()),all_member_hashes_verified=True)
 save()
 if a.remove_verified_copies:
  shutil.rmtree(root);assert not root.exists();j['copies_removed']=True
 j.update(complete=True,elapsed_seconds=time.monotonic()-started);save()
 print(json.dumps({k:v for k,v in j.items() if k not in ['files','directories','inputs']},indent=2),flush=True)
