#!/usr/bin/env python3
"""Audit actual GHC -ddump-types output for shared literal generalization."""
import argparse,hashlib,json,pathlib,re

def audit(log,manifest):
    shared={m['module']:m['path'] for m in manifest['modules']}
    module=None;in_signatures=False;name=None;ty=[];signatures=[];seen=set()
    def save():
        if name and module in shared:
            signatures.append({'module':module,'path':shared[module],'name':name,'inferred':' '.join(ty).strip()})
    for line in log.splitlines():
        match=re.search(r'Compiling\s+([\w.]+)\s+\(',line)
        if match:
            save();name=None;module=match[1];in_signatures=False
            if module in shared:seen.add(module)
        elif line=='TYPE SIGNATURES':in_signatures=True
        elif in_signatures:
            match=re.match(r'^  (\S+) ::\s*(.*)',line)
            if match:save();name=match[1];ty=[match[2]]
            elif line.startswith('    '):ty.append(line.strip())
            else:save();name=None;in_signatures=False
    save()
    generalized=[s for s in signatures if re.search(r'\.(?:IsString|Num|Fractional)\b',s['inferred'])]
    return {'shared_module_count':len(shared),'seen_module_count':len(seen),'missing_modules':sorted(set(shared)-seen),'top_level_signature_count':len(signatures),'generalized':generalized}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=pathlib.Path);parser.add_argument('manifest',type=pathlib.Path);parser.add_argument('report',type=pathlib.Path)
    parser.add_argument('--require-concrete',action='store_true')
    args=parser.parse_args();report=audit(args.log.read_text(),json.loads(args.manifest.read_text()))
    report.update(format=1,log_sha256=hashlib.sha256(args.log.read_bytes()).hexdigest(),manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest())
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='generalized'}|{'generalized_count':len(report['generalized'])}))
    if report['missing_modules'] or (args.require_concrete and report['generalized']):raise SystemExit(1)
if __name__=='__main__':main()
