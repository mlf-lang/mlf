#!/usr/bin/env python3
"""Focused flag-absent CLI regression against independently rebuilt pinned PR25."""
import argparse,json,subprocess
from pathlib import Path
import prepare
BASE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
compiler=prepare.build_identity()['binary']
commands=[['--help'],['--version'],['--implementation-identity']]
for prelude in [[],['--no-prelude']]:
 for fixture in ['unit','unsigned_ring','mutual_ring','concrete_identity','ignored_bottom','hidden_capture','nominal_unit','unsupported_poly','unsupported_scalar','bad_type','bad_parse']:
  commands.append(prelude+['--expr',(BASE/'fixtures'/(fixture+'.emlf')).read_text()])
records=[]
for argv in commands:
 old=subprocess.run([str(a.baseline),*argv],capture_output=True,timeout=30)
 new=subprocess.run([compiler,*argv],capture_output=True,timeout=30)
 assert (old.returncode,old.stdout,old.stderr)==(new.returncode,new.stdout,new.stderr),argv
 records.append({'argv':argv,'exit_code':new.returncode,'stdout':new.stdout.decode(),'stderr':new.stderr.decode()})
a.output.write_text(json.dumps({'status':'passed','scope':'25 focused flag-absent CLI comparisons, not whole upstream suite','baseline_binary_sha256':prepare.sha(a.baseline),'trial_binary_sha256':prepare.sha(compiler),'records':records},indent=2)+'\n');print(a.output)
