#!/usr/bin/env python3
"""Fixed four-run MLF/GHC/GHC/MLF native endpoint comparison, no replacement."""
from pathlib import Path
import argparse,json,hashlib,math,subprocess,sys,shutil
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,value):p.write_text(json.dumps(value,sort_keys=True,indent=2)+'\n')
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['producer','workload','setup','reference-prefix','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);qualifier=ROOT/'tools/performance/full-compiler/qualify.py';worker=qualifier.with_name('worker.py');work=json.loads(a.workload.read_text())
 pins={**work['input_files'],**{str(f.resolve()):sha(f) for f in [Path(__file__),qualifier,worker,a.workload,a.setup,a.producer/'receipt.json',ROOT/'host/ghc/MLF/Host/Base.hs']}}
 for f in a.setup.parent.rglob('*'):
  if f.is_file():pins[str(f.resolve())]=sha(f)
 for f in [qualifier,worker,Path(__file__)]:shutil.copy2(f,out/f.name)
 plan={'order':['mlf-native','ghc-native','ghc-native','mlf-native'],'purpose':'descriptive native-endpoint comparison','primary':'geometric MLF/GHC wall ratio over two adjacent pairs','qualification_metadata':'Each underlying qualifier retains performance_samples=0 because it is an endpoint qualification, not an optimization-effect confirmation sample. This plan explicitly designates their ordinary endpoint wall observations as the four comparison measurements.','replacement_or_extension':False,'ordinary_flags':'GHC9.14.1 O2 j1; Clang ordinary O2 serial; existing 5GiB RSS,5GiB disk floor,3GiB host floor,600s wall per complete endpoint','inputs':pins};save(out/'plan.json',plan)
 record={'complete':False,'plan_sha256':sha(out/'plan.json'),'runs':[]};save(out/'receipt.json',record)
 for i,lane in enumerate(plan['order']):
  for path,digest in pins.items():
   if sha(path)!=digest:raise ValueError('frozen input changed '+path)
  dest=out/(str(i)+'-'+lane);cmd=[sys.executable,'-B',str(qualifier),'--workload',str(a.workload.resolve()),'--setup',str(a.setup.resolve()),'--producer',str(a.producer.resolve()),'--producer-source',str(ROOT),'--lane',lane,'--output',str(dest)]
  if lane=='mlf-native':cmd+=['--reference-prefix',str(a.reference_prefix.resolve())]
  result=subprocess.run(cmd,cwd=ROOT,capture_output=True);(out/(str(i)+'.stdout')).write_bytes(result.stdout);(out/(str(i)+'.stderr')).write_bytes(result.stderr)
  row={'position':i,'lane':lane,'exit_code':result.returncode,'receipt':str(dest/'receipt.json'),'receipt_sha256':sha(dest/'receipt.json')};record['runs'].append(row);save(out/'receipt.json',record)
  if result.returncode:raise RuntimeError('native comparison failed; no replacement: '+str(dest))
  d=json.loads((dest/'receipt.json').read_text())
  if not d['complete']:raise ValueError('incomplete endpoint')
  row.update(wall_seconds=d['endpoint_wall_seconds'],stages=d['stages'],peak_rss_bytes=d['commands'][0]['sampled_process_tree_peak_rss_bytes']);save(out/'receipt.json',record);print('PASS',i,lane,row['wall_seconds'],flush=True)
 for path,digest in pins.items():
  if sha(path)!=digest:raise ValueError('frozen input changed '+path)
 ratios=[]
 for pair in [record['runs'][:2],record['runs'][2:]]:
  times={x['lane']:x['wall_seconds'] for x in pair};ratios.append(times['mlf-native']/times['ghc-native'])
 record.update(complete=True,pair_ratios=ratios,geometric_ratio=math.exp(sum(map(math.log,ratios))/2),geometric_seconds={lane:math.exp(sum(math.log(x['wall_seconds']) for x in record['runs'] if x['lane']==lane)/2) for lane in ['mlf-native','ghc-native']});save(out/'receipt.json',record)
 print('PASS closed native comparison',record['geometric_ratio'])
if __name__=='__main__':main()
