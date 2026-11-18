"""Bounded nontermination smoke check, not a general divergence proof."""
import json,os,signal,subprocess,sys,time
exe,out=sys.argv[1:]; rows=[]
for side in ['original','candidate']:
 p=None;row=dict(side=side)
 try:
  p=subprocess.Popen([exe,'cycle-'+side],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
  try:
   stdout,stderr=p.communicate(timeout=1.0);raise RuntimeError('cycle unexpectedly returned '+str(p.returncode))
  except subprocess.TimeoutExpired:
   os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate(timeout=2)
   assert p.returncode==-signal.SIGKILL and stdout==b'' and stderr==b''
   try:os.killpg(p.pid,0)
   except ProcessLookupError:pass
   else:raise RuntimeError('cycle process group survived')
   row.update(bounded_timeout=True,cleanup=True,exit=p.returncode)
 finally:
  if p is not None and p.poll() is None:
   os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
 rows.append(row)
with open(out,'x') as f:json.dump(dict(scope='one second divergence smoke check only',rows=rows),f,indent=2)
