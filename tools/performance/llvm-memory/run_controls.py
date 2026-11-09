#!/usr/bin/env python3
"""Frozen full host owner versus candidate plus independent Unicode list oracle."""
from pathlib import Path
import argparse,subprocess,shutil,types
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
OWNER='host/ghc/MLF/Host/Base.hs';PARENT='9dfcd6625775819568eaaa5065f8dd1431df52f8'
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--producer',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--optimization',choices=['0','2'],required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);producer=a.producer.resolve()
 hp=ROOT/'tools/performance/a1-private-index/helper.py';H=types.ModuleType('h');H.__file__=str(hp);exec(compile(hp.read_bytes(),str(hp),'exec'),H.__dict__)
 limits=dict(address_space_per_process_bytes=6*1024**3,disk_free_floor_bytes=5*1024**3,host_available_floor_bytes=3*1024**3,max_work_bytes=3*1024**3,process_tree_rss_bytes=5*1024**3,wall_seconds=600)
 record=dict(complete=False,optimization=a.optimization,commands=[]);save=lambda:H.save(out/'receipt.json',record);save()
 with H.SerialLock(ROOT/'.mlf-build'):
  auth=H.authenticate(producer,ROOT);objects=out/'objects';shutil.copytree(producer/'objects',objects);src=out/'source';src.mkdir()
  old=subprocess.check_output(['git','show',PARENT+':'+OWNER],cwd=ROOT);new=(ROOT/OWNER).read_bytes()
  for name,raw in [('LegacyBase',old),('CandidateBase',new)]:
   before=b'module MLF.Host.Base';after=('module '+name).encode();H.require(raw.count(before)==1,'unique module header');adapted=raw.replace(before,after);H.require(adapted.replace(after,before)==raw,'header-only inverse');(src/(name+'.hs')).write_bytes(adapted)
  shutil.copy2(HERE/'Main.hs',src/'Main.hs');pins=H.file_pins(src);pins.update({str(p):H.sha(p) for p in [Path(__file__),ROOT/OWNER,HERE/'Main.hs']});record['inputs']=pins;record['parent_ref']=PARENT;save()
  flags=[];i=0
  while i<len(auth['flags']):
   f=auth['flags'][i]
   if f in ['-odir','-hidir']:i+=2
   elif f.startswith('-i'):i+=1
   else:flags.append('-O'+a.optimization if f in ['-O0','-O2'] else f);i+=1
  flags+=['-i','-i'+str(objects),'-odir',str(objects),'-hidir',str(objects)]
  def run(label,cmd):record['commands'].append(H.Runner(out,limits).run(cmd,ROOT,out/label));save()
  for name in ['LegacyBase','CandidateBase','Main']:run('compile-'+name,[auth['ghc']['path'],*flags,'-c',src/(name+'.hs')])
  binary=out/'controls';run('link',[auth['ghc']['path'],*flags,*sorted(objects.rglob('*.o')),producer/'host.o',producer/'supervisor.o','-o',binary]);run('run',[binary]);H.require((out/'run/stdout').read_bytes()==b'PASS 94 Unicode fixtures: every scalar, block-boundary slices, exact bounds errors\n','complete fixture inventory');H.check_pins(pins);H.require(H.authenticate(producer,ROOT)==auth,'producer unchanged');record['complete']=True;save();print('PASS Unicode controls O'+a.optimization)
if __name__=='__main__':main()
