#!/usr/bin/env python3
"""Task-local extension of the reviewed Linux process-tree watchdog.

Tracks descendant identities as well as process groups. It does not modify
producer receipts; resource failure is never a successful negative control.
--output-root includes actual run/build outputs without precreating a cold path.
An initially absent output root is allowed only until its first observation.
"""
import argparse,errno,json,os,resource,shutil,signal,stat,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=600);p.add_argument('--address-space-mib',type=int,default=1024);p.add_argument('--rss-mib',type=int,default=1024);p.add_argument('--max-output-mib',type=int,default=0);p.add_argument('--disk-free-mib',type=int,default=768);p.add_argument('--output-root',type=Path);p.add_argument('out',type=Path);p.add_argument('command',nargs=argparse.REMAINDER);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
if not a.command or min(a.seconds,a.address_space_mib,a.rss_mib,a.disk_free_mib)<=0 or a.max_output_mib<0:p.error('positive limits and a command are required')
address_limit=a.address_space_mib*1024**2;limit=a.rss_mib*1024**2;floor=3*1024**3;disk_floor=a.disk_free_mib*1024**2
receipt={'complete':False,'command':a.command,'limits':{'wall_seconds':a.seconds,'address_space_per_process':address_limit,'process_tree_rss_bytes':limit,'host_available_floor':floor,'disk_free_floor':disk_floor,'max_output_bytes':a.max_output_mib*1024**2 if a.max_output_mib else None},'samples':[]}
proc=None;start=time.monotonic();reason=None
guard_root=Path(os.path.abspath(a.out))
selected_root=Path(os.path.abspath(a.output_root)) if a.output_root else guard_root
# Count the guard log as before, adding actual outputs without double counting.
output_roots=[guard_root] if selected_root==guard_root or guard_root in selected_root.parents else [selected_root] if selected_root in guard_root.parents else [guard_root,selected_root]
declared_roots=list(dict.fromkeys([guard_root,selected_root]))
root_seen={str(root):root.exists() for root in declared_roots}
receipt['output_roots']=[str(root) for root in output_roots]
receipt['output_roots_initially_absent']=[path for path,seen in root_seen.items() if not seen]
receipt['process_visibility']='Owned descendants visible in this watchdog PID namespace; not a global host audit.'
try:receipt['pid_namespace']=os.readlink('/proc/self/ns/pid')
except OSError:receipt['pid_namespace']=None

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
def validate_output_root(root):
 try:info=root.lstat()
 except FileNotFoundError:
  if root==selected_root and not root_seen[str(root)]:return False
  raise
 if not stat.S_ISDIR(info.st_mode):raise NotADirectoryError(str(root))
 root_seen[str(root)]=True
 return True
def output_bytes(root):
 # Atomic cache publication may remove a descendant between walk steps.
 # Only that missing-child race is tolerated; the monitored root and all
 # other traversal failures remain fatal, including a root lost mid-scan.
 def validate_root():
  return validate_output_root(root)
 if not validate_root():return 0
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
def disk_available(root):
 # Before a cold output exists, check its nearest existing filesystem ancestor.
 current=root
 while not current.exists():
  parent=current.parent
  if parent==current:raise FileNotFoundError(str(root))
  current=parent
 return shutil.disk_usage(current).free
def sample_and_check():
 # A selected child root is checked even when its bytes are counted by a parent.
 for root in declared_roots:validate_output_root(root)
 sample={'seconds':time.monotonic()-start,'group_rss':rss(proc.pid),'host_available':available(),'disk_free':min(disk_available(root) for root in output_roots)}
 if a.max_output_mib:
  sample['output_bytes']=sum(output_bytes(root) for root in output_roots)
 receipt['samples'].append(sample);save()
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
 if min(disk_available(root) for root in output_roots)<disk_floor:raise RuntimeError('disk free below floor before start')
 with (a.out/'build.log').open('wb') as log:
  proc=subprocess.Popen(a.command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=restrict)
  receipt['process_group']=proc.pid
  while proc.poll() is None:
   sample_and_check()
   time.sleep(0.2)
  receipt['exit_code']=proc.returncode
  sample_and_check()  # A fast exit cannot bypass final disk/output safeguards.
  if descendants():raise RuntimeError('descendants remained after command completion')
  receipt['complete']=proc.returncode==0
except BaseException as exc:
 reason=type(exc).__name__+': '+str(exc)
 try:stop()
 except BaseException as cleanup_error:receipt['cleanup_error']=type(cleanup_error).__name__+': '+str(cleanup_error)
finally:
 # SIGKILL delivery is asynchronous. Establish a bounded terminal observation.
 remaining=descendants()
 deadline=time.monotonic()+2
 while remaining and time.monotonic()<deadline:
  time.sleep(0.05);remaining=descendants()
 receipt['terminal_descendants']=[{'pid':pid,'ppid':info[0],'pgid':info[1],
   'start_ticks':info[2],'rss_bytes':info[3],'state':info[4]} for pid,info in sorted(remaining.items())]
 receipt['terminal_descendants_empty']=not bool(remaining)
 receipt['output_roots_seen']=root_seen
 receipt['tracked_process_count']=len(tracked)
 if remaining:
  receipt['complete']=False
  if reason is None:reason='RuntimeError: descendants remained after cleanup observation'
 receipt['reason']=reason;receipt['elapsed_seconds']=time.monotonic()-start
 receipt['peak_group_rss']=max((x['group_rss'] for x in receipt['samples']),default=0)
 if proc is not None:receipt['exit_code']=proc.returncode
 save();print(json.dumps({k:v for k,v in receipt.items() if k!='samples'}))
raise SystemExit(0 if receipt['complete'] else 1)
