#!/usr/bin/env python3
"""Freeze a strict B0 intersection; no build, source rewriting or target reuse."""
from pathlib import Path
import argparse
from common import BASE, COUNTS, HERE, H, row, topological, validate


def compiler_plan(source, workload):
    w = H.load(workload)
    H.require(w['format'] == 'full-emlf-source-closure-v1' and w['entry'] == 'MLF.Entry.Emlf',
              'requires original B0 frozen workload')
    H.require(w['module_count'] == len(w['modules']) == 90 and w['source_bytes'] == 5233364,
              'requires exact current 90 module workload')
    H.require(w['input_files'] == {r['source']: r['sha256'] for r in w['modules']},
              'B0 pins disagree')
    by_module = {r['module']: r for r in w['modules']}
    H.require(len(by_module) == 90, 'duplicate B0 module')
    slices, manifests, used = [], [], set()
    for name in sorted(set(COUNTS)-{'entry'}):
        path = source/'libraries'/name/'mlf-package.json'
        manifest = H.load(path)
        manifests.append(path)
        H.require(manifest['name'] == name, 'package identity differs')
        selected = []
        for module, relative in manifest['library']['modules'].items():
            if module not in by_module:
                continue
            item = by_module[module]
            H.require(Path(item['source']) == (path.parent/relative).resolve(), 'package source differs')
            H.require(module not in used, 'duplicate package ownership')
            used.add(module)
            selected.append(item)
        slices.append(dict(name=name, entry='', modules=sorted(selected,key=lambda x:x['module']),
                           dependencies=sorted(manifest.get('dependencies', {}))))
    root = source/'mlf-package.json'
    manifests.append(root)
    target = H.load(root)['executables']['emlf']
    entry = dict(target['modules'])
    entry['MLF.Entry.Emlf'] = target['main']
    H.require(set(entry) == set(by_module)-used, 'root entry inventory differs')
    for module, relative in entry.items():
        H.require(Path(by_module[module]['source']) == (source/relative).resolve(), 'root source differs')
    slices.append(dict(name='entry', entry='MLF.Entry.Emlf', dependencies=sorted(target['dependencies']),
                       modules=[by_module[name] for name in sorted(entry)]))
    return dict(format='fresh-split-v1', kind='compiler90', baseline_commit=BASE,
                source=str(source), workload=str(workload), workload_sha256=H.sha(workload),
                module_count=90, source_bytes=5233364, slices=topological(slices),
                static_pins={str(p): H.sha(p) for p in [workload, source/'shared-sources.json', *manifests]})


def fixture_plan():
    slices = []
    for name, module, deps in [('model','Model',[]), ('facade','Facade',['model']),
                               ('entry','Main',['model','facade'])]:
        path = HERE/'fixture'/(module+'.hs')
        slices.append(dict(name=name, entry='Main' if name == 'entry' else '', dependencies=deps,
                           modules=[row(module,path,'fixture/'+path.name)]))
    return dict(format='fresh-split-v1',kind='fixture',source=str(HERE),
                module_count=3,source_bytes=sum(s['modules'][0]['bytes'] for s in slices),
                slices=topological(slices),static_pins={})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['compiler90','fixture'], required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--workload', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.kind == 'compiler90':
        H.require(args.source and args.workload, 'compiler source and original B0 workload required')
        plan = compiler_plan(args.source.resolve(), args.workload.resolve())
    else:
        plan = fixture_plan()
    validate(plan)
    H.require(not args.output.exists(), 'never overwrite a frozen plan')
    H.save(args.output,plan)
    print(plan['kind'],plan['module_count'],plan['source_bytes'],H.sha(args.output))

if __name__ == '__main__':
    main()
