#!/usr/bin/env python3
"""Materialize only authored finite file controls under one NEW output directory.
This script does not invoke a compiler. Parent owns guarded execution.
"""
import argparse,hashlib,json
from pathlib import Path
D=Path(__file__).resolve().parent
def pack(xs):return ''.join(str(len(x))+':'+x for x in xs)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--builtin-prefix',required=True,type=Path);a=p.parse_args()
 # Parent authenticates the existing shared dependency receipt and both files
 # before/after execution. Its pathname is part of exact artifact identity.
 builtin=a.builtin_prefix.resolve()
 dependency_files=[Path(str(builtin)+suffix) for suffix in ['.mlfci','.mlfco']]
 assert all(q.is_file() for q in dependency_files),'existing authenticated shared builtin required'
 dependency_pins={str(q):sha(q) for q in dependency_files}
 out=a.output.resolve();assert not out.exists();out.mkdir();cases=json.loads((D/'file-cases.json').read_text());rows=[]
 for c in cases['cases']:
  root=out/c['name'];root.mkdir();src=root/'src';src.mkdir();sources=[]
  for module,contents in sorted(c['modules'].items()):
   path=src/(module.replace('.','/')+'.emlf');path.parent.mkdir(parents=True,exist_ok=True)
   if module not in c.get('missing_modules',[]):path.write_text(contents)
   sources.append((module,str(path)))
  item={'name':c['name'],'expected_type':c['expected_type'],'required_error_fragments':c.get('required_error_fragments',[]),'source_pins':{path:sha(Path(path)) for _,path in sources if Path(path).is_file()},'missing_sources':[path for _,path in sources if not Path(path).exists()],'runs':[]}
  if 'exact_error' in c:item['exact_error']=c['exact_error']
  if 'exact_error_template' in c:
   message=c['exact_error_template']
   for module,path in sources:message=message.replace('{source:'+module+'}',path)
   item['exact_error']=message
  for method in ['old','session']:
   work=root/method;work.mkdir();cache=work/'queries';cache.mkdir();prefix=work/'unit';spec=work/'crate.spec'
   spec.write_text(pack(['MLF-CRATE-1',c.get('identity','session-control/'+c['name']),'Main','true',pack([pack(list(pair)) for pair in sources]),pack([]),str(cache),str(builtin)]))
   item['runs'].append({'implementation':method,'spec':str(spec),'spec_sha256':sha(spec),'prefix':str(prefix),'cache':str(cache),'argv':[method,str(spec),str(prefix),c['expected_type']]})
  rows.append(item)
 receipt={'complete':True,'materialization_only':True,'compiler_executed':False,'shared_builtin_prefix':str(builtin),'shared_dependency_pins':dependency_pins,'file_cases_sha256':sha(D/'file-cases.json'),'cases':rows,'artifact_comparison_suffixes':['.mlfci','.mlfco','.queries'],'success_stdout':'PASS file checked <expected_type>\n','negative_stdout':'Exact complete baseline P3 REJECT line, with authored fragments/exact_error also enforced','cold_requirement':'Every successful side starts with an empty own cache; require inferred>0,reused==0 in query report. No shared mutable output paths.'}
 (out/'materialized.json').write_text(json.dumps(receipt,indent=2)+'\n')
 print('PASS materialized nine independent parsed-file controls')
if __name__=='__main__':main()
