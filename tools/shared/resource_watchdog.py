#!/usr/bin/env python3
"""Linux process-tree watchdog promoted from the reviewed cloud qualification runner.

Tracks descendant identities as well as process groups. It does not modify
producer receipts; resource failure is never a successful negative control."""
import argparse,errno,json,os,resource,shutil,signal,stat,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output-root',type=Path);p.add_argument('--workspace-root',type=Path);p.add_argument('--workspace-limit-mib',type=int,default=0);p.add_argument('--seconds',type=int,default=600);p.add_argument('--address-space-mib',type=int,default=1024);p.add_argument('--rss-mib',type=int,default=1024);p.add_argument('--max-output-mib',type=int,default=0);p.add_argument('--disk-free-mib',type=int,default=768);p.add_argument('out',type=Path);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
if not a.command or min(a.seconds,a.address_space_mib,a.rss_mib,a.disk_free_mib)<=0 or a.max_output_mib<0 or a.workspace_limit_mib<0 or bool(a.workspace_root)!=bool(a.workspace_limit_mib):p.error('positive limits and a command are required')
output_root=(a.output_root or a.out).resolve(strict=True)
workspace_root=a.workspace_root.resolve(strict=True) if a.workspace_root else None
if not a.out.resolve().is_relative_to(output_root):p.error('command logs must be inside monitored output root')
if workspace_root and not output_root.is_relative_to(workspace_root):p.error('output must be inside monitored workspace')
address_limit=a.address_space_mib*1024**2;limit=a.rss_mib*1024**2;floor=3*1024**3;disk_floor=a.disk_free_mib*1024**2
receipt={'output_root':str(output_root),'workspace_root':str(workspace_root) if workspace_root else None,'complete':False,'command':a.command,'limits':{'wall_seconds':a.seconds,'address_space_per_process':address_limit,'process_tree_rss_bytes':limit,'host_available_floor':floor,'disk_free_floor':disk_floor,'max_output_bytes':a.max_output_mib*1024**2 if a.max_output_mib else None,'workspace_allocated_bytes':a.workspace_limit_mib*1024**2 if workspace_root else None},'samples':[]}
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
 owned |= {pid for pid,info in table.items() if info[1]==proc.pid}
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
 temporary=a.out/'bounded-receipt.json.tmp'
 temporary.write_text(json.dumps(receipt,indent=2)+'\n')
 temporary.replace(a.out/'bounded-receipt.json')
def stop():
 if proc is None:return
 began=time.monotonic();owned=descendants()
 def identities(rows):return [{'pid':pid,'start_time':info[2],'process_group':info[1]} for pid,info in sorted(rows.items())]
 record={'initial':identities(owned),'drained':False,'remaining':[]}
 receipt['teardown']=record
 groups={proc.pid}|{info[1] for pid,info in owned.items() if info[1] in tracked}
 for group in groups:
  try:os.killpg(group,signal.SIGTERM)
  except ProcessLookupError:pass
 try:proc.wait(timeout=2)
 except subprocess.TimeoutExpired:pass
 for pid in descendants():
  try:os.kill(pid,signal.SIGKILL)
  except ProcessLookupError:pass
 try:proc.wait(timeout=2)
 except subprocess.TimeoutExpired:pass
 deadline=time.monotonic()+3
 remaining=descendants()
 while remaining and time.monotonic()<deadline:
  time.sleep(.05);remaining=descendants()
 record.update(remaining=identities(remaining),drained=not remaining,seconds=time.monotonic()-began)
def output_bytes(root):
 # Atomic cache publication may remove a descendant between walk steps.
 # Only that missing-child race is tolerated; the monitored root and all
 # other traversal failures remain fatal, including a root lost mid-scan.
 def validate_root():
  if not stat.S_ISDIR(root.stat().st_mode):raise NotADirectoryError(str(root))
 validate_root()
 root_absolute=Path(os.path.abspath(root))
 enumerated_children=set()
 def traversal_error(error):
  if isinstance(error,FileNotFoundError) and error.errno==errno.ENOENT and error.filename is not None:
   missing=Path(os.path.abspath(error.filename))
   if missing in enumerated_children and missing!=root_absolute and root_absolute in missing.parents:return
  raise error
 total=0
 for directory, dirs, files in os.walk(root,followlinks=False,onerror=traversal_error):
  enumerated_children.update(Path(os.path.abspath(Path(directory)/name)) for name in dirs)
  for name in files:
   try:info=(Path(directory)/name).lstat()
   except FileNotFoundError:continue
   if stat.S_ISREG(info.st_mode):total+=info.st_size
 validate_root()
 return total
def allocated_bytes(root):
 # Count allocated bytes once per inode, including directories and symlinks.
 # Do not follow symlinks into unrelated output trees or count shared Git history twice.
 seen=set();total=0
 def add(path):
  nonlocal total
  info=path.lstat();identity=(info.st_dev,info.st_ino)
  if identity not in seen:seen.add(identity);total+=info.st_blocks*512
 if not root.is_dir():raise NotADirectoryError(str(root))
 def traversal_error(error):
  if not isinstance(error,FileNotFoundError):raise error
 for directory,dirs,files in os.walk(root,followlinks=False,onerror=traversal_error):
  add(Path(directory))
  for name in dirs+files:
   try:add(Path(directory)/name)
   except FileNotFoundError:pass
 if not root.is_dir():raise FileNotFoundError(str(root))
 return total
def sample_and_check():
 sample={'seconds':time.monotonic()-start,'group_rss':rss(proc.pid),'host_available':available(),'disk_free':shutil.disk_usage(a.out).free}
 if a.max_output_mib:
  sample['output_bytes']=output_bytes(output_root)
 if workspace_root:sample['workspace_allocated_bytes']=allocated_bytes(workspace_root)
 receipt['samples'].append(sample);save()
 if workspace_root and sample['workspace_allocated_bytes']>a.workspace_limit_mib*1024**2:raise RuntimeError('workspace allocated-byte limit')
 if sample.get('output_bytes',0)>a.max_output_mib*1024**2 and a.max_output_mib:raise RuntimeError('output growth limit')
 if sample['seconds']>=a.seconds:raise RuntimeError('wall-time limit')
 if sample['group_rss']>limit:raise RuntimeError('process-group RSS limit')
 if sample['host_available']<floor:raise RuntimeError('host memory floor')
 if sample['disk_free']<disk_floor:raise RuntimeError('disk free floor')
def interrupted(signum, frame):
 raise RuntimeError('watchdog interrupted by signal '+str(signum))
signal.signal(signal.SIGTERM,interrupted)
try:
 if available()<floor:raise RuntimeError('host available memory below floor before start')
 if shutil.disk_usage(a.out).free<disk_floor:raise RuntimeError('disk free below floor before start')
 if a.max_output_mib and output_bytes(output_root)>a.max_output_mib*1024**2:raise RuntimeError('output growth limit before start')
 if workspace_root and allocated_bytes(workspace_root)>a.workspace_limit_mib*1024**2:raise RuntimeError('workspace allocated-byte limit before start')
 with (a.out/'build.log').open('wb') as log:
  proc=subprocess.Popen(a.command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=restrict)
  receipt['process_group']=proc.pid
  while proc.poll() is None:
   sample_and_check()
   time.sleep(0.2)
  receipt['exit_code']=proc.returncode
  sample_and_check()  # A fast exit cannot bypass final disk/output safeguards.
  remaining=descendants()
  receipt['final_owned_descendants']=[{'pid':pid,'start_time':info[2]} for pid,info in sorted(remaining.items())]
  if remaining:raise RuntimeError('descendants remained after command completion')
  receipt['complete']=proc.returncode==0
except BaseException as exc:
 reason=type(exc).__name__+': '+str(exc);stop()
 if receipt.get('teardown',{}).get('drained') is False:reason+='; owned descendants not drained'
finally:
 receipt['reason']=reason;receipt['elapsed_seconds']=time.monotonic()-start
 receipt['peak_group_rss']=max((x['group_rss'] for x in receipt['samples']),default=0)
 if proc is not None:receipt['exit_code']=proc.returncode
 save();print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}))
raise SystemExit(0 if receipt['complete'] else 1)
