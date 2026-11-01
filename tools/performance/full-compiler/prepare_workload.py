#!/usr/bin/env python3
"""Freeze the complete emlf shared import closure, without building or timing."""
from pathlib import Path
import argparse,hashlib,json,re


def freeze(source,label):
    source=source.resolve()
    manifest=json.loads((source/'shared-sources.json').read_text())
    known={x['module']:x for x in manifest['modules']}
    if len(known)!=len(manifest['modules']):raise ValueError('duplicate shared module')
    active=set();seen=set();outside=set();order=[]
    def visit(name):
        if name in seen:return
        if name not in known:outside.add(name);return
        if name in active:raise ValueError('cyclic shared imports: '+name)
        active.add(name)
        for dependency in re.findall(r'(?m)^\s*import\s+(?:qualified\s+)?([A-Z][\w.]*)',(source/known[name]['path']).read_text()):
            visit(dependency)
        active.remove(name);seen.add(name);order.append(name)
    entry='MLF.Entry.Emlf';visit(entry)
    if not order or outside!={'MLF.Primitive'}:raise ValueError('unexpected external source dependencies')
    rows=[]
    for name in order:
        path=source/known[name]['path'];raw=path.read_bytes()
        rows.append({'module':name,'relative':known[name]['path'],'source':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    return {'format':'full-emlf-source-closure-v1','baseline_ref':label,'entry':entry,'modules':rows,'module_count':len(rows),'source_bytes':sum(x['bytes'] for x in rows),'nonshared_imports':sorted(outside),'freshness':f'All listed {len(rows)} shared modules compile fresh in each leg; no target query/object reuse. Only primitive/host adapters, installed GHC packages and builtin/runtime may be fixed dependencies.','input_files':{x['source']:x['sha256'] for x in rows},'exclusions':'Other executables, tests and unreachable shared modules are outside emlf compiler entry closure.'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--label',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();value=freeze(a.source,a.label)
    with a.output.open('x') as output:json.dump(value,output,sort_keys=True,indent=2);output.write('\n')
    print(json.dumps({key:value[key] for key in ['module_count','source_bytes','entry']}))


if __name__=='__main__':main()
