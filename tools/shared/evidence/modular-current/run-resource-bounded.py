#!/usr/bin/env python3
"""Resource-bounded local qualification runner; does not modify source receipts."""
import argparse,json,os,resource,shutil,signal,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=600);p.add_argument('--address-space-mib',type=int,default=1024);p.add_argument('--rss-mib',type=int,default=1024);p.add_argument('--max-output-mib',type=int,default=0);p.add_argument('out',type=Path);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
address_limit=a.address_space_mib*1024**2;limit=a.rss_mib*1024**2;floor=3*1024**3;disk_floor=768*1024**2
receipt={'complete':False,'command':a.command,'limits':{'wall_seconds':a.seconds,'address_space_per_process':address_limit,'process_tree_rss_bytes':limit,'host_available_floor':floor,'disk_free_floor':disk_floor,'max_output_bytes':a.max_output_mib*1024**2 if a.max_output_mib else None},'samples':[]}
proc=None;start=time.monotonic();reason=None

def available():
 for line in Path('/proc/meminfo').read_text().splitlines():
  if line.startswith('MemAvailable:'):return int(line.split()[1])*1024
 raise RuntimeError('Cannot measure host available memory')
tracked = {}
def descendants():
 table = {}
 for path in Path('/proc').iterdir():
  if not path.name.isdigit():continue
  try:
   fields=(path/'stat').read_text().split(') ',1)[1].split()
   table[int(path.name)] = (int(fields[1]),int(fields[2]),fields[19],int((path/'statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE'),fields[0])
  except (FileNotFoundError,ProcessLookupError,PermissionError):pass
 if proc is None:return {}
 owned = {pid for pid,identity in tracked.items() if pid in table and table[pid][2]==identity}
 if proc.pid in table:owned.add(proc.pid)
 while True:
  added={pid for pid,info in table.items() if info[0] in owned}-owned
  if not added:break
  owned |= added
 for pid in owned:tracked[pid]=table[pid][2]
 return {pid:table[pid] for pid in owned if table[pid][4]!='Z'}
def rss(pgid):
 return sum(info[3] for info in descendants().values())
def restrict():
 resource.setrlimit(resource.RLIMIT_AS,(address_limit,address_limit));resource.setrlimit(resource.RLIMIT_CPU,(a.seconds,a.seconds))
def save():
 (a.out/'bounded-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
def stop():
 if proc is None:return
 owned=descendants()
 groups={proc.pid}|{info[1] for pid,info in owned.items() if info[1] in tracked}
 for group in groups:
  try:os.killpg(group,signal.SIGTERM)
  except ProcessLookupError:pass
 try:proc.wait(timeout=2)
 except subprocess.TimeoutExpired:pass
 for pid in descendants():
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
 if proc.poll() is None:proc.wait()
try:
 if available()<floor:raise RuntimeError('host available memory below floor before start')
 if shutil.disk_usage(a.out).free<disk_floor:raise RuntimeError('disk free below floor before start')
 with (a.out/'build.log').open('wb') as log:
  proc=subprocess.Popen(a.command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=restrict)
  receipt['process_group']=proc.pid
  while proc.poll() is None:
   sample={'seconds':time.monotonic()-start,'group_rss':rss(proc.pid),'host_available':available(),'disk_free':shutil.disk_usage(a.out).free};receipt['samples'].append(sample);save()
   if a.max_output_mib:
    size=sum(p.stat().st_size for p in a.out.rglob('*') if p.is_file() and not p.is_symlink());sample['output_bytes']=size
    if size>a.max_output_mib*1024**2:raise RuntimeError('output growth limit')
   if sample['seconds']>=a.seconds:raise RuntimeError('wall-time limit')
   if sample['group_rss']>limit:raise RuntimeError('process-group RSS limit')
   if sample['host_available']<floor:raise RuntimeError('host memory floor')
   if sample['disk_free']<disk_floor:raise RuntimeError('disk free floor')
   time.sleep(0.2)
  receipt['exit_code']=proc.returncode
  if descendants():raise RuntimeError('descendants remained after command completion')
  receipt['complete']=proc.returncode==0
except BaseException as exc:
 reason=type(exc).__name__+': '+str(exc);stop()
finally:
 receipt['reason']=reason;receipt['elapsed_seconds']=time.monotonic()-start
 receipt['peak_group_rss']=max((x['group_rss'] for x in receipt['samples']),default=0)
 if proc is not None:receipt['exit_code']=proc.returncode
 save();print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}))
raise SystemExit(0 if receipt['complete'] else 1)
