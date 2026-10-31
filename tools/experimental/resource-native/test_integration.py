#!/usr/bin/env python3
"""Focused actual surface source -> checked IR -> native differential regression.
This is not the complete upstream qualification suite or a benchmark.
"""
import argparse,json,subprocess,sys
from pathlib import Path
import run_native
BASE=Path(__file__).resolve().parent
NORMAL=['unit','unsigned_ring','mutual_ring','concrete_identity','ignored_bottom','hidden_capture','nominal_unit']
NEGATIVE={'unsupported_poly':'unsupported runtime representation','unsupported_scalar':'ResourceExport: unsupported fragment','bad_type':'Inference:','bad_parse':'Parsing:'}
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--build-parent',type=Path,required=True);args=p.parse_args();records=[]
    for name in NORMAL+['blackhole']:
        for fine in [False,True]:
            for borrow in [False,True]:
                r=run_native.run_source(BASE/'fixtures'/(name+'.emlf'),groups=fine,borrows=borrow,no_prelude=True,build_parent=args.build_parent)
                assert r['status']==('fault' if name=='blackhole' else 'complete')
                if name=='blackhole':assert r['native']['fault']=='BUSY'
                records.append({'source':name,'fine':fine,'borrow':borrow,'status':r['status'],'memory':r['native']['memory'],'receipt':str(Path(r['build_directory'])/'receipt.json')})
    for name,diagnostic in NEGATIVE.items():
        try:run_native.run_source(BASE/'fixtures'/(name+'.emlf'),no_prelude=True,build_parent=args.build_parent)
        except ValueError as e:assert diagnostic in str(e);records.append({'source':name,'rejected':str(e)})
        else:raise AssertionError('unsupported source accepted: '+name)
    for name in ['unsigned_ring','hidden_capture','ignored_bottom']:
        r=run_native.run_source(BASE/'fixtures'/(name+'.emlf'),groups=True,borrows=True,no_prelude=True,profile='sanitized',build_parent=args.build_parent);assert r['status']=='complete';records.append({'source':name,'sanitized':True,'receipt':str(Path(r['build_directory'])/'receipt.json')})
    args.output.write_text(json.dumps({'status':'passed','scope':'focused; not full upstream campaign','normal_sources':7,'blackholes':1,'four_mode_native_runs':32,'source_rejections':4,'additional_sanitized':3,'records':records},indent=2)+'\n');print(args.output)
if __name__=='__main__':main()
